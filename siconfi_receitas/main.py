"""
main.py — Orquestrador do projeto siconfi_receitas.

Executa os três módulos em sequência, compartilhando a lista de entes
para evitar chamadas duplicadas à API.

Uso:
    # Todos os módulos
    python -m siconfi_receitas.main

    # Apenas um ou dois módulos
    python -m siconfi_receitas.main --modulos dca rreo
    python -m siconfi_receitas.main --modulos siope
"""

import argparse
import time

from .common import obter_entes
from . import dca, rreo, siope


MODULOS_DISPONIVEIS = {
    "dca"  : dca.baixar,
    "rreo" : rreo.baixar,
    "siope": siope.baixar,
}


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

    # Carrega entes uma única vez e repassa a todos os módulos
    entes_df = obter_entes()

    resultados = {}
    for nome in modulos:
        t0 = time.time()
        fn = MODULOS_DISPONIVEIS[nome]
        resultados[nome] = fn(entes_df=entes_df)
        elapsed = time.time() - t0
        print(f"\n[{nome.upper()}] Tempo: {elapsed/60:.1f} min\n")

    print("=" * 70)
    print("Resumo geral:")
    for nome, linhas in resultados.items():
        print(f"  {nome.upper():<8}: {len(linhas):>8} registros")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrator de receitas SICONFI/SIOPE")
    parser.add_argument(
        "--modulos", nargs="+",
        choices=list(MODULOS_DISPONIVEIS.keys()),
        default=list(MODULOS_DISPONIVEIS.keys()),
        help="Módulos a executar (padrão: todos)",
    )
    args = parser.parse_args()
    main(modulos=args.modulos)
