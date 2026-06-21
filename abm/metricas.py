import numpy as np
import pandas as pd
from parametros import G_RENDA, IDADE_TRABALHO_INICIO, IDADE_APOSENTADORIA


def calcular_gini(valores: np.ndarray) -> float:
    c = np.sort(valores[valores > 0])
    n = len(c)
    if n < 2 or c.sum() == 0:
        return 0.0
    coef = (2 * np.dot(np.arange(1, n + 1), c)) / (n * c.sum()) - (n + 1) / n
    return float(np.clip(coef, 0.0, 1.0))


def calcular_shares(valores: np.ndarray) -> tuple:
    c = np.sort(valores[valores >= 0])
    n = len(c)
    total = c.sum()
    if n == 0 or total == 0:
        return 0.0, 0.0, 0.0
    return (
        float(c[int(0.99 * n):].sum() / total),
        float(c[int(0.90 * n):].sum() / total),
        float(c[int(0.50 * n):].sum() / total),
    )


def calcular_percentis_extras(valores: np.ndarray, percentis: list, suffix: str = '_riqueza') -> dict:
    """Retorna valores em percentis arbitrarios com sufixo customizavel."""
    c = np.sort(valores[valores >= 0])
    n = len(c)
    if n == 0:
        return {f'p{p}{suffix}': 0.0 for p in percentis}
    return {f'p{p}{suffix}': float(c[min(int(p / 100 * n), n - 1)]) for p in percentis}


def calcular_shares_e_percentis(valores: np.ndarray) -> tuple:
    """Em uma so passada: shares cumulativos, shares exclusivos e thresholds de riqueza.

    Retorna:
      (share_top1, share_top10, share_top50,
       share_top10_excl_top1, share_top50_excl_top10,
       p50_riqueza, p90_riqueza, p99_riqueza)
    """
    c = np.sort(valores[valores >= 0])
    n = len(c)
    if n == 0:
        return (0.0,) * 8
    total = c.sum()
    idx50 = int(0.50 * n)
    idx90 = int(0.90 * n)
    idx99 = min(int(0.99 * n), n - 1)
    p50_v = float(c[idx50])
    p90_v = float(c[idx90])
    p99_v = float(c[idx99])
    if total == 0:
        return (0.0, 0.0, 0.0, 0.0, 0.0, p50_v, p90_v, p99_v)
    top1  = float(c[idx99:].sum() / total)
    top10 = float(c[idx90:].sum() / total)
    top50 = float(c[idx50:].sum() / total)
    top10_excl_top1  = float(c[idx90:idx99].sum() / total)
    top50_excl_top10 = float(c[idx50:idx90].sum() / total)
    return (top1, top10, top50,
            top10_excl_top1, top50_excl_top10,
            p50_v, p90_v, p99_v)


def coletar_metricas(pop: dict, mercado: dict, t: int) -> dict:
    vivo = pop['vivo']
    n_vivos = int(vivo.sum())
    cap_fin  = pop['capital'][vivo]
    valor_re = pop['n_imoveis'][vivo].astype(np.float64) * mercado['preco']
    divida   = pop['divida_imovel'][vivo]
    # Riqueza liquida = capital + imoveis - divida hipotecaria
    riqueza  = cap_fin + valor_re - divida

    gini_fin   = calcular_gini(cap_fin)
    gini_total = calcular_gini(riqueza)
    (top1, top10, top50,
     top10_excl_top1, top50_excl_top10,
     p50_riq, p90_riq, p99_riq) = calcular_shares_e_percentis(riqueza)
    # Percentis intermediarios no topo (P91 a P98) — granularidade dentro do top 10%
    percentis_extras = calcular_percentis_extras(riqueza, list(range(91, 99)))
    # Versao paralela: capital financeiro APENAS (sem imoveis) — para diagnostico
    percentis_fin = calcular_percentis_extras(
        cap_fin, [50] + list(range(90, 100)), suffix='_capfin'
    )

    n_prop = int((pop['n_imoveis'][vivo] > 0).sum())
    divida_media = float(divida.mean()) if n_vivos > 0 else 0.0

    # Rent como % da renda total de trabalho (todos os agentes em idade ativa)
    # Usa renda corrente (base × crescimento acumulado)
    fator_g = (1 + G_RENDA) ** t
    mask_ativo = vivo & (pop['idade'] >= 18) & (pop['idade'] < 65)
    renda_trabalho_total = float((pop['renda_base'][mask_ativo] * fator_g).sum()) if mask_ativo.any() else 1.0
    rent_total = float(mercado.get('rent_total_ano', 0.0))
    frac_rent = rent_total / max(renda_trabalho_total, 1.0)

    gini_imob = calcular_gini(valor_re)

    out: dict = {
        'ano':              t,
        'populacao':        n_vivos,
        'gini_financeiro':  round(gini_fin, 4),
        'gini_total':       round(gini_total, 4),
        'gini_imobiliario': round(gini_imob, 4),
        'share_top1':              round(top1, 4),
        'share_top10':             round(top10, 4),
        'share_top50':             round(top50, 4),
        'share_top10_excl_top1':   round(top10_excl_top1, 4),
        'share_top50_excl_top10':  round(top50_excl_top10, 4),
        'p50_riqueza':             p50_riq,
        'p90_riqueza':             p90_riq,
        'p99_riqueza':             p99_riq,
        **percentis_extras,
        **percentis_fin,
        'preco_imovel':       round(mercado['preco'], 0),
        'n_total_mercado':    int(mercado.get('n_total', 0)),
        'n_detidos_total':    int(pop['n_imoveis'][vivo].sum()),
        'n_proprietarios':    n_prop,
        'taxa_propriedade': round(n_prop / max(n_vivos, 1), 4),
        'riqueza_media':    float(riqueza.mean()) if n_vivos > 0 else 0.0,
        'capital_medio':    float(cap_fin.mean()) if n_vivos > 0 else 0.0,
        'riqueza_imob_media': float(valor_re.mean()) if n_vivos > 0 else 0.0,
        'divida_media':     divida_media,
        'rent_total_ano':   round(rent_total, 0),
        'frac_rent_renda':  round(frac_rent, 4),
        'n_renters':        int(mercado.get('n_renters_ano', 0)),
    }

    for c in range(3):
        mask_c = vivo & (pop['classe'] == c)
        if mask_c.any():
            n_im_c = pop['n_imoveis'][mask_c]
            riq_c = (
                pop['capital'][mask_c]
                + n_im_c.astype(np.float64) * mercado['preco']
                - pop['divida_imovel'][mask_c]
            )
            out[f'riqueza_media_c{c}']  = float(riq_c.mean())
            out[f'pop_c{c}']            = int(mask_c.sum())
            out[f'n_imoveis_c{c}']      = int(n_im_c.sum())            # total de imoveis detidos pela classe
            out[f'n_proprietarios_c{c}'] = int((n_im_c > 0).sum())     # individuos com >=1 imovel

            ativo_c = (pop['idade'][mask_c] >= IDADE_TRABALHO_INICIO) & \
                      (pop['idade'][mask_c] < IDADE_APOSENTADORIA)
            renda_c = np.where(ativo_c, pop['renda_base'][mask_c] * fator_g, 0.0)
            juros_c = pop['capital'][mask_c] * pop['retorno'][mask_c].astype(np.float64)
            out[f'renda_diaria_mediana_c{c}'] = float(np.median(renda_c + juros_c)) / 365
        else:
            out[f'riqueza_media_c{c}']  = 0.0
            out[f'pop_c{c}']            = 0
            out[f'n_imoveis_c{c}']      = 0
            out[f'n_proprietarios_c{c}'] = 0
            out[f'renda_diaria_mediana_c{c}'] = 0.0

    return out


def snapshot_piramide(pop: dict, t: int) -> pd.DataFrame:
    """Contagem de agentes vivos por grupo quinquenal (0-4, 5-9, ..., 85-89)."""
    vivo = pop['vivo']
    idades = pop['idade'][vivo]
    grupos = np.minimum(idades // 5, 17)   # 18 grupos até 85-89
    contagens = np.bincount(grupos, minlength=18)
    faixas = [f"{g*5}-{g*5+4}" for g in range(18)]
    return pd.DataFrame({'ano': t, 'faixa': faixas, 'n': contagens})


def snapshot_distribuicao(pop: dict, mercado: dict, t: int) -> pd.DataFrame:
    vivo = pop['vivo']
    percentis = [10, 25, 50, 75, 90, 99]
    rows = []
    for c in range(3):
        mask = vivo & (pop['classe'] == c)
        riqueza = (
            pop['capital'][mask]
            + pop['n_imoveis'][mask].astype(np.float64) * mercado['preco']
            - pop['divida_imovel'][mask]
        )
        if len(riqueza) == 0:
            continue
        row = {'ano': t, 'classe': c, 'n': len(riqueza), 'media': float(riqueza.mean())}
        for p in percentis:
            row[f'p{p}'] = float(np.percentile(riqueza, p))
        rows.append(row)
    return pd.DataFrame(rows)
