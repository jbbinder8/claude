"""
main.py — Orquestrador do projeto siconfi_receitas.

Executa os três módulos em sequência, compartilhando a lista de entes
para evitar chamadas duplicadas à API.

Uso:
    # Todos os módulos
    python -m siconfi_receitas.main

    # Apenas um ou dois módulos
    python -m siconfi_receitas.main --modulos dca rreo
    python -m siconfi_receitas.main --modulos siops
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from .common import obter_entes
from . import dca, rreo, siops, consolidar as _consolidar


MODULOS_DISPONIVEIS = {
    "dca"  : dca.baixar,
    "rreo" : rreo.baixar,
    "siops": siops.baixar,
}

_LOG = Path("output/receitas/log_execucao.csv")


def _gravar_log(modulo: str, inicio: float, registros: int):
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    novo = not _LOG.exists()
    with open(_LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["data_hora", "modulo", "duracao_min", "registros"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            modulo.upper(),
            f"{(time.time() - inicio) / 60:.1f}",
            registros,
        ])


def main(modulos: list[str] = None):
    if modulos is None:
        modulos = list(MODULOS_DISPONIVEIS.keys())

    invalidos = [m for m in modulos if m not in MODULOS_DISPONIVEIS]
    if invalidos:
        raise ValueError(f"Módulos desconhecidos: {invalidos}. Disponíveis: {list(MODULOS_DISPONIVEIS)}")

    print("=" * 70)
    print("siconfi_receitas — extrator de receitas fiscais")
    print(f"Módulos selecionados: {modulos}")
    print("=" * 70)

    entes_df = obter_entes()

    resultados = {}
    for nome in modulos:
        t0 = time.time()
        fn = MODULOS_DISPONIVEIS[nome]
        resultados[nome] = fn(entes_df=entes_df)
        duracao = time.time() - t0
        _gravar_log(nome, t0, len(resultados[nome]))
        print(f"\n[{nome.upper()}] Tempo: {duracao/60:.1f} min\n")

    print("=" * 70)
    print("Resumo geral:")
    for nome, linhas in resultados.items():
        print(f"  {nome.upper():<8}: {len(linhas):>8} registros")
    print("=" * 70)

    _consolidar.consolidar()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrator de receitas SICONFI/SIOPS")
    parser.add_argument(
        "--modulos", nargs="+",
        choices=list(MODULOS_DISPONIVEIS.keys()),
        default=list(MODULOS_DISPONIVEIS.keys()),
        help="Módulos a executar (padrão: todos)",
    )
    args = parser.parse_args()
    main(modulos=args.modulos)
