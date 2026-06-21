import numpy as np
from parametros import *


def _sortear_poupanca(classes: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    taxa = np.zeros(len(classes), dtype=np.float32)
    for i, c in enumerate(classes):
        frac_zero = FRAC_POUPANCA_ZERO.get(int(c), 0.0)
        if frac_zero > 0 and rng.random() < frac_zero:
            taxa[i] = 0.0
            continue
        lo, hi = POUPANCA_POR_CLASSE[int(c)]
        taxa[i] = rng.uniform(lo, hi) if hi > lo else lo
    return taxa


def inicializar(rng: np.random.Generator) -> tuple:
    """
    Retorna (pop, proximo_id, filhos_por_pai).
    pop: dict de arrays pre-alocados com BUFFER_AGENTES slots.
    """
    n = N_AGENTES_INICIAL
    buf = BUFFER_AGENTES

    pop = {
        'capital':       np.zeros(buf, dtype=np.float64),
        'renda_base':    np.zeros(buf, dtype=np.float64),
        'taxa_poupanca': np.zeros(buf, dtype=np.float32),
        'retorno':       np.zeros(buf, dtype=np.float32),
        'classe':        np.full(buf, -1, dtype=np.int8),
        'idade':         np.zeros(buf, dtype=np.int16),
        'id_pai':        np.full(buf, -1, dtype=np.int32),
        'vivo':          np.zeros(buf, dtype=bool),
        'ano_nasc':      np.full(buf, -9999, dtype=np.int16),
        'n_imoveis':     np.zeros(buf, dtype=np.int16),
        # Saldo devedor da hipoteca residencial (so 1o imovel pode ter divida).
        # Inicializa em 0 — propriedades pre-existentes em t=0 sao consideradas quitadas.
        'divida_imovel': np.zeros(buf, dtype=np.float64),
    }

    classes = rng.choice(3, size=n, p=PROPORCAO_CLASSES).astype(np.int8)

    # Pirâmide etária brasileira: sorteia grupo quinquenal depois posição no grupo
    grupos = rng.choice(18, size=n, p=PIRAMIDE_ETARIA_BR)
    idades = (grupos * 5 + rng.integers(0, 5, size=n)).astype(np.int16)
    idades = np.clip(idades, 0, 89)

    capitais = np.zeros(n, dtype=np.float64)
    rendas   = np.zeros(n, dtype=np.float64)
    for c in range(3):
        mask = classes == c
        if not mask.any():
            continue
        params_k = CAPITAL_INICIAL_POR_CLASSE[c]
        mu_r, sig_r = RENDA_POR_CLASSE[c]
        if params_k is not None:
            mu_k, sig_k = params_k
            capitais[mask] = rng.lognormal(np.log(mu_k), sig_k, size=mask.sum())
        rendas[mask] = rng.lognormal(np.log(mu_r), sig_r, size=mask.sum())

    poupancas = _sortear_poupanca(classes, rng)
    retornos  = np.array([RETORNO_POR_CLASSE[int(c)] for c in classes], dtype=np.float32)

    pop['classe'][:n]       = classes
    pop['idade'][:n]        = idades
    pop['capital'][:n]      = capitais
    pop['renda_base'][:n]   = rendas
    pop['taxa_poupanca'][:n]= poupancas
    pop['retorno'][:n]      = retornos
    pop['vivo'][:n]         = True
    pop['ano_nasc'][:n]     = -idades

    return pop, n, {}  # filhos_por_pai começa vazio


def criar_agente(pop: dict, proximo_id: int, filhos_por_pai: dict,
                 classe: int, ano: int, id_pai: int,
                 rng: np.random.Generator) -> int:
    """Preenche o slot proximo_id e retorna proximo_id+1. Se buffer cheio, retorna proximo_id."""
    if proximo_id >= BUFFER_AGENTES:
        return proximo_id

    i = proximo_id
    mu_r, sig_r = RENDA_POR_CLASSE[classe]

    pop['classe'][i]       = classe
    pop['idade'][i]        = 0
    pop['capital'][i]      = 0.0
    pop['renda_base'][i]   = rng.lognormal(np.log(mu_r), sig_r)
    pop['taxa_poupanca'][i]= _sortear_poupanca(np.array([classe], dtype=np.int8), rng)[0]
    pop['retorno'][i]      = RETORNO_POR_CLASSE[classe]
    pop['n_imoveis'][i]    = 0
    pop['divida_imovel'][i]= 0.0
    pop['id_pai'][i]       = id_pai
    pop['vivo'][i]         = True
    pop['ano_nasc'][i]     = ano

    if id_pai >= 0:
        filhos_por_pai.setdefault(id_pai, []).append(i)

    return proximo_id + 1
