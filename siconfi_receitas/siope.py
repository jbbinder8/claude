"""
siope.py — Módulo SIOPE (Sistema de Informações sobre Orçamentos Públicos em Educação).

PENDENTE: o código de acesso ao SIOPE será fornecido pelo usuário.

Este módulo deverá extrair (quando implementado):
  • ICMS                — estados       (anual, 2019-2025)
  • ISS                 — municípios    (anual, 2019-2025)
  • Cota-Parte do ICMS  — municípios    (anual, 2019-2025)

A função baixar() segue a mesma assinatura dos outros módulos para que
o orquestrador (main.py) possa chamá-la de forma uniforme.
"""

from pathlib import Path

DIR_SAIDA  = Path("output/siope")
CSV_SAIDA  = DIR_SAIDA / "receitas_siope.csv"


def baixar(entes_df=None) -> list:
    """
    Placeholder — implementar quando o código SIOPE for fornecido.
    Retorna lista vazia para não bloquear o orquestrador.
    """
    print("\n[SIOPE] Módulo ainda não implementado — aguardando código fonte.")
    print(f"[SIOPE] Quando implementado, saída em: {CSV_SAIDA}")
    return []
