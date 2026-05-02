"""
main.py — Orquestrador do projeto siconfi_receitas.

Modo padrão (sem --modulos): lança 3 subprocessos em paralelo:
    • dca + rreo  (sequenciais num mesmo processo)
    • siops
    • siope
  Aguarda os 3 e roda consolidação ao final.

Modo direto (--modulos especificado): executa os módulos informados
  sequencialmente no processo corrente. Grava log detalhado em
  output/receitas/log_<modulos>.txt automaticamente.

Uso:
    python -m siconfi_receitas.main                                # paralelo (padrão)
    python -m siconfi_receitas.main --modulos dca rreo             # direto, 2 módulos
    python -m siconfi_receitas.main --modulos siops                # direto, 1 módulo
    python -m siconfi_receitas.main --modulos siope                # direto, 1 módulo
    python -m siconfi_receitas.main --modulos dca rreo siops siope # direto, todos sequencial
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from .common import obter_entes
from . import dca, rreo, siops, siope, consolidar as _consolidar


MODULOS_DISPONIVEIS = {
    "dca"  : dca.baixar,
    "rreo" : rreo.baixar,
    "siops": siops.baixar,
    "siope": siope.baixar,
}

_GRUPOS_PARALELOS = [["dca", "rreo"], ["siops"], ["siope"]]

DIR_SAIDA = Path("output/receitas")


# ---------------------------------------------------------------------------
# Tee — duplica stdout para arquivo de log
# ---------------------------------------------------------------------------

class _Tee:
    """Escreve simultaneamente no stream original e em um arquivo de log."""

    def __init__(self, original, arquivo):
        self._orig = original
        self._arq  = arquivo

    def write(self, data):
        self._orig.write(data)
        self._arq.write(data)

    def flush(self):
        self._orig.flush()
        self._arq.flush()

    def isatty(self):
        return self._orig.isatty()


# ---------------------------------------------------------------------------
# Modo direto — executa módulos sequencialmente neste processo
# ---------------------------------------------------------------------------

def _executar_direto(modulos: list[str]):
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    log_path   = DIR_SAIDA / f"log_{'_'.join(modulos)}.txt"
    log_file   = open(log_path, "w", encoding="utf-8", buffering=1)
    stdout_orig = sys.stdout
    sys.stdout  = _Tee(stdout_orig, log_file)

    try:
        print("=" * 70)
        print("siconfi_receitas — extrator de receitas fiscais")
        print(f"Módulos: {modulos}")
        print("=" * 70)

        entes_df = obter_entes()

        resultados = {}
        for nome in modulos:
            t0 = time.time()
            resultados[nome] = MODULOS_DISPONIVEIS[nome](entes_df=entes_df)
            print(f"\n[{nome.upper()}] Tempo: {(time.time() - t0) / 60:.1f} min\n")

        print("=" * 70)
        print("Resumo:")
        for nome, linhas in resultados.items():
            print(f"  {nome.upper():<8}: {len(linhas):>8} registros")
        print("=" * 70)

    finally:
        sys.stdout = stdout_orig
        log_file.close()


# ---------------------------------------------------------------------------
# Modo paralelo — lança subprocessos e consolida ao final
# ---------------------------------------------------------------------------

def _executar_paralelo():
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    modulo = "siconfi_receitas.main"

    print("=" * 70)
    print("siconfi_receitas — modo paralelo")
    print(f"Grupos: {[' + '.join(g) for g in _GRUPOS_PARALELOS]}")
    print("=" * 70)

    processos = []
    for grupo in _GRUPOS_PARALELOS:
        cmd = [python, "-m", modulo, "--modulos"] + grupo
        p   = subprocess.Popen(cmd)
        processos.append((grupo, p))
        print(f"  Lançado: {(' + '.join(grupo)).upper():<20} PID {p.pid}")

    print()
    erros = []
    for grupo, p in processos:
        rc    = p.wait()
        label = (" + ".join(grupo)).upper()
        if rc != 0:
            erros.append(grupo)
            print(f"  [ERRO] {label}: exit code {rc}")
        else:
            print(f"  [OK]   {label}")

    print()
    if erros:
        print(f"[PARALELO] {len(erros)} grupo(s) com erro — consolidação abortada.")
        sys.exit(1)

    _consolidar.consolidar()


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main(modulos: list[str] | None = None):
    invalidos = [m for m in (modulos or []) if m not in MODULOS_DISPONIVEIS]
    if invalidos:
        raise ValueError(f"Módulos desconhecidos: {invalidos}. Disponíveis: {list(MODULOS_DISPONIVEIS)}")

    if modulos is None:
        _executar_paralelo()
    else:
        _executar_direto(modulos)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrator de receitas SICONFI/SIOPS")
    parser.add_argument(
        "--modulos", nargs="+",
        choices=list(MODULOS_DISPONIVEIS.keys()),
        help=(
            "Módulos a executar. Sem este argumento: lança 3 processos em paralelo "
            "(dca+rreo / siops / siope) e consolida ao final. "
            "Com este argumento: executa os módulos informados sequencialmente "
            "neste processo (ex: --modulos dca rreo siops siope roda tudo em sequência)."
        ),
    )
    args = parser.parse_args()
    main(modulos=args.modulos)
