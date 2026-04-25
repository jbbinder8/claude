#!/usr/bin/env python3
"""
Teste: ICMS do Paraná (estado) + ISS e Cota-Parte ICMS de Curitiba
Todos os anos: 2019-2025
"""

import requests
import pandas as pd
import os

BASE_URL    = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
ANOS        = list(range(2019, 2026))
COLUNA_ALVO = "Receitas Brutas Realizadas"

# Houve mudança de plano de contas em 2022
CONTAS = {
    "E": {
        2019: {"RO1.1.1.8.02.1.0": "ICMS"},
        2020: {"RO1.1.1.8.02.1.0": "ICMS"},
        2021: {"RO1.1.1.8.02.1.0": "ICMS"},
        2022: {"RO1.1.1.4.50.1.0": "ICMS"},
        2023: {"RO1.1.1.4.50.1.0": "ICMS"},
        2024: {"RO1.1.1.4.50.1.0": "ICMS"},
        2025: {"RO1.1.1.4.50.1.0": "ICMS"},
    },
    "M": {
        2019: {"RO1.1.1.8.02.3.0": "ISS", "RO1.7.2.8.01.1.0": "Cota-Parte ICMS"},
        2020: {"RO1.1.1.8.02.3.0": "ISS", "RO1.7.2.8.01.1.0": "Cota-Parte ICMS"},
        2021: {"RO1.1.1.8.02.3.0": "ISS", "RO1.7.2.8.01.1.0": "Cota-Parte ICMS"},
        2022: {"RO1.1.1.4.51.1.0": "ISS", "RO1.7.2.1.50.0.0": "Cota-Parte ICMS"},
        2023: {"RO1.1.1.4.51.1.0": "ISS", "RO1.7.2.1.50.0.0": "Cota-Parte ICMS"},
        2024: {"RO1.1.1.4.51.1.0": "ISS", "RO1.7.2.1.50.0.0": "Cota-Parte ICMS"},
        2025: {"RO1.1.1.4.51.1.0": "ISS", "RO1.7.2.1.50.0.0": "Cota-Parte ICMS"},
    },
}

ENTES = [
    {"cod_ibge": 41,      "esfera": "E", "nome": "Parana (estado)"},
    {"cod_ibge": 4106902, "esfera": "M", "nome": "Curitiba"},
]

def buscar(cod_ibge, ano):
    r = requests.get(BASE_URL + "dca", params={
        "an_exercicio": ano,
        "no_anexo"    : "DCA-Anexo I-C",
        "id_ente"     : cod_ibge,
        "limit"       : 500,
    }, timeout=60)
    return r.json().get("items", []) if r.status_code == 200 else []

linhas = []
for ente in ENTES:
    cod, esfera, nome = ente["cod_ibge"], ente["esfera"], ente["nome"]
    for ano in ANOS:
        contas_alvo = CONTAS[esfera][ano]
        items = buscar(cod, ano)
        achou = [i for i in items
                 if i.get("cod_conta") in contas_alvo
                 and i.get("coluna") == COLUNA_ALVO]
        for i in achou:
            linhas.append({
                "ente"      : nome,
                "esfera"    : "Estado" if esfera == "E" else "Municipio",
                "co_uf"     : i.get("uf"),
                "cod_ibge"  : cod,
                "ano"       : ano,
                "indicador" : contas_alvo[i["cod_conta"]],
                "valor"     : i.get("valor") or 0,
            })
        status = ", ".join(
            f"{contas_alvo[i['cod_conta']]}: R$ {i.get('valor',0):>16,.0f}" for i in achou
        ) or "sem dado"
        print(f"  {nome:<20} {ano}  {status}")

df = pd.DataFrame(linhas)
print("\n--- Resultado completo ---")
print(df.to_string(index=False))

os.makedirs("siconfi_dca", exist_ok=True)
csv = "siconfi_dca/teste_parana_curitiba.csv"
df.to_csv(csv, sep=";", decimal=",", index=False, encoding="utf-8-sig")
print(f"\nSalvo em: {csv}")
