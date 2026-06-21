import numpy as np
from parametros import (
    MORT_ANUAL_POR_GRUPO, FERTIL_ANUAL_POR_GRUPO, FERTIL_MULT_CLASSE,
    MAX_IMOVEIS_POR_CLASSE, BUFFER_AGENTES,
)
from populacao import criar_agente


def _grupo_etario(idades: np.ndarray) -> np.ndarray:
    """Mapeia idades para indice de grupo quinquenal (0=0-4, ..., 18=90+)."""
    return np.minimum(idades // 5, 18)


def processar_nascimentos(pop: dict, proximo_id: int, filhos_por_pai: dict,
                           ano: int, rng: np.random.Generator) -> int:
    """Fecundidade estocastica anual por idade e classe (IBGE calibrado)."""
    vivos = pop['vivo']
    grupos = _grupo_etario(pop['idade'])
    taxa_base = FERTIL_ANUAL_POR_GRUPO[grupos]

    classe_idx = np.maximum(pop['classe'], 0)
    mult = FERTIL_MULT_CLASSE[classe_idx]
    mult[pop['classe'] < 0] = 0.0

    taxa_ef = taxa_base * mult
    tem_filho = vivos & (rng.random(BUFFER_AGENTES) < taxa_ef)

    for pai_id in np.where(tem_filho)[0]:
        classe_filho = int(pop['classe'][pai_id])
        novo_id = criar_agente(pop, proximo_id, filhos_por_pai,
                               classe_filho, ano, int(pai_id), rng)
        if novo_id == proximo_id:
            print(f"[aviso] Buffer de agentes cheio no ano {ano}.")
            break
        proximo_id = novo_id

    return proximo_id


def processar_herancas(pop: dict, filhos_por_pai: dict, mercado: dict,
                        rng: np.random.Generator) -> None:
    """Mortalidade estocastica anual (IBGE 2022) com heranca que PRESERVA CLASSE.

    Cadeia de transferencia (por imovel do morto):
      a) Residencia (1o imovel):
         1. Filho elegivel (n_imoveis < MAX da sua classe).
         2. Renter de MESMA CLASSE em idade adulta (preserva propriedade na classe).
         3. Senao: volta ao mercado.
      b) Imoveis de investimento (2o+):
         1. Filhos elegiveis (ordem: menos imoveis primeiro), respeitando MAX.
         2. Outros agentes da MESMA CLASSE abaixo do MAX (preserva propriedade na classe).
         3. Senao: volta ao mercado.

    Capital financeiro -> dividido igualmente entre filhos vivos.
    Divida residual -> filho herda junto; transferencia inter-classe via passo (2) cancela divida.
    """
    vivos = pop['vivo']
    grupos = _grupo_etario(pop['idade'])
    probs = MORT_ANUAL_POR_GRUPO[grupos]
    mortos = vivos & (rng.random(BUFFER_AGENTES) < probs)

    # Pools de agentes elegiveis a receber imovel, por classe.
    # Pre-computados uma vez por ano para eficiencia.
    pool_renters = {c: [] for c in range(3)}   # candidatos a residencia (n_imoveis == 0)
    pool_invest  = {c: [] for c in range(3)}   # candidatos a investimento (n_imoveis < MAX)
    ptr_ren = {c: 0 for c in range(3)}
    ptr_inv = {c: 0 for c in range(3)}
    for c in range(3):
        max_c = MAX_IMOVEIS_POR_CLASSE.get(c, 1)
        idade_ok = (pop['idade'] >= 18) & (pop['idade'] <= 65)
        cand_ren = np.where(
            vivos & (pop['classe'] == c) & (pop['n_imoveis'] == 0) & idade_ok
        )[0].tolist()
        rng.shuffle(cand_ren)
        pool_renters[c] = cand_ren
        cand_inv = np.where(
            vivos & (pop['classe'] == c) & (pop['n_imoveis'] < max_c) & idade_ok
        )[0].tolist()
        rng.shuffle(cand_inv)
        pool_invest[c] = cand_inv

    def _proximo_renter(c: int) -> int:
        """Proximo renter (n_imoveis == 0) vivo da classe c."""
        pool = pool_renters[c]
        p = ptr_ren[c]
        while p < len(pool):
            cand = pool[p]
            p += 1
            if pop['vivo'][cand] and pop['n_imoveis'][cand] == 0:
                ptr_ren[c] = p
                return cand
        ptr_ren[c] = p
        return -1

    def _proximo_invest(c: int) -> int:
        """Proximo agente abaixo do MAX da classe c."""
        max_c = MAX_IMOVEIS_POR_CLASSE.get(c, 1)
        pool = pool_invest[c]
        p = ptr_inv[c]
        while p < len(pool):
            cand = pool[p]
            p += 1
            if pop['vivo'][cand] and pop['n_imoveis'][cand] < max_c:
                ptr_inv[c] = p
                return cand
        ptr_inv[c] = p
        return -1

    for i in np.where(mortos)[0]:
        filhos = [f for f in filhos_por_pai.get(int(i), []) if pop['vivo'][f]]
        n_im = int(pop['n_imoveis'][i])
        divida_residual = float(pop['divida_imovel'][i])
        classe_i = int(np.maximum(pop['classe'][i], 0))

        # 1) Residencia (primeiro imovel)
        if n_im >= 1:
            # 1a) Tenta filho sem imovel e abaixo do MAX
            herdeiro = next((f for f in filhos if pop['n_imoveis'][f] == 0), -1)
            if herdeiro >= 0:
                max_f = MAX_IMOVEIS_POR_CLASSE.get(int(pop['classe'][herdeiro]), 1)
                if pop['n_imoveis'][herdeiro] < max_f:
                    pop['n_imoveis'][herdeiro] += 1
                    pop['divida_imovel'][herdeiro] += divida_residual
                    divida_residual = 0.0
                    n_im -= 1
            # 1b) Sem filho elegivel → renter de mesma classe (preserva classe)
            if n_im >= 1 and herdeiro < 0:
                renter = _proximo_renter(classe_i)
                if renter >= 0:
                    pop['n_imoveis'][renter] += 1
                    # Transferencia informal: divida cancelada (banco eat loss)
                    divida_residual = 0.0
                    n_im -= 1
            # 1c) Se nao achou ninguem: volta ao mercado (n_total inalterado)

        # 2) Imoveis de investimento → filhos (ordem: menos imoveis primeiro)
        if n_im > 0 and filhos:
            filhos_ordem = sorted(filhos, key=lambda f: int(pop['n_imoveis'][f]))
            for f in filhos_ordem:
                if n_im == 0:
                    break
                max_f = MAX_IMOVEIS_POR_CLASSE.get(int(pop['classe'][f]), 1)
                while n_im > 0 and pop['n_imoveis'][f] < max_f:
                    pop['n_imoveis'][f] += 1
                    n_im -= 1

        # 3) Investimentos restantes → outros agentes da MESMA CLASSE abaixo do MAX
        while n_im > 0:
            outro = _proximo_invest(classe_i)
            if outro < 0:
                break   # nenhum elegivel restante; resto volta ao mercado
            pop['n_imoveis'][outro] += 1
            n_im -= 1

        # 4) Capital financeiro: dividido entre filhos
        capital = float(pop['capital'][i])
        pop['n_imoveis'][i]     = 0
        pop['divida_imovel'][i] = 0.0
        pop['vivo'][i]          = False
        pop['capital'][i]       = 0.0

        if filhos:
            heranca = capital / len(filhos)
            for f in filhos:
                pop['capital'][f] += heranca
