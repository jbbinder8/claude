"""
Azimute solar em Curitiba ao longo do dia — uma linha por mês (dia 21).
O eixo Y usa Norte como 0°: positivo = Leste, negativo = Oeste.
Dependências: astral, matplotlib, numpy, pytz
    pip install astral matplotlib numpy pytz
"""

from astral import LocationInfo
from astral.sun import sun, azimuth as solar_azimuth
from datetime import date, timedelta

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pytz

CURITIBA = LocationInfo(
    name="Curitiba",
    latitude=-25.4284,
    longitude=-49.2733,
    timezone="America/Sao_Paulo",
)
TZ  = pytz.timezone("America/Sao_Paulo")
ANO = 2025

MESES = [
    ( 1, "Janeiro"),   ( 2, "Fevereiro"), ( 3, "Março"),    ( 4, "Abril"),
    ( 5, "Maio"),      ( 6, "Junho"),     ( 7, "Julho"),    ( 8, "Agosto"),
    ( 9, "Setembro"),  (10, "Outubro"),   (11, "Novembro"), (12, "Dezembro"),
]

# Cores sazonais — hemisfério sul: verão = dez/jan/fev, inverno = jun/jul/ago
CORES = [
    "#FF6B35",  # Jan  - verão
    "#FF9F1C",  # Fev  - verão
    "#FFCA3A",  # Mar  - outono
    "#8AC926",  # Abr  - outono
    "#1982C4",  # Mai  - fim outono
    "#4361EE",  # Jun  - inverno
    "#9B5DE5",  # Jul  - inverno
    "#4895EF",  # Ago  - fim inverno
    "#43AA8B",  # Set  - primavera
    "#90BE6D",  # Out  - primavera
    "#F9C74F",  # Nov  - fim primavera
    "#F94144",  # Dez  - verão
]

BG    = "#0d1117"
PANEL = "#11151c"

fig, ax = plt.subplots(figsize=(14, 8))
fig.patch.set_facecolor(BG)
ax.set_facecolor(PANEL)
ax.tick_params(colors="#ccc")
for spine in ax.spines.values():
    spine.set_edgecolor("#2d333b")

STEP_MIN = 10  # amostragem a cada 10 minutos

for (mes, nome), cor in zip(MESES, CORES):
    d    = date(ANO, mes, 21)
    s    = sun(CURITIBA.observer, date=d, tzinfo=TZ)
    rise = s["sunrise"]
    sset = s["sunset"]

    times_h, azis = [], []
    t = rise
    while t <= sset:
        azis.append(solar_azimuth(CURITIBA.observer, t))
        times_h.append(t.hour + t.minute / 60 + t.second / 3600)
        t += timedelta(minutes=STEP_MIN)

    # Remove descontinuidade em 0°/360° (Norte):
    # curva vai de ~+90° (Leste) → 0° (Norte) → valores negativos (Oeste)
    azi_unwrapped = np.rad2deg(np.unwrap(np.deg2rad(azis)))

    ax.plot(times_h, azi_unwrapped, color=cor, lw=2)

    # Rótulo ao fim da linha (por do sol) — lado direito
    ax.text(
        times_h[-1] + 0.15, azi_unwrapped[-1],
        nome, color=cor, fontsize=8.5, va="center", ha="left", clip_on=False,
    )
    # Rótulo no início da linha (nascer do sol) — lado esquerdo
    ax.text(
        times_h[0] - 0.15, azi_unwrapped[0],
        nome, color=cor, fontsize=8.5, va="center", ha="right", clip_on=False,
    )

# ── Linhas de referência das direções ────────────────────────────────────────
DIRS = [
    ( 135, 0.30),
    (  90, 0.45),
    (  45, 0.25),
    (   0, 0.65),
    ( -45, 0.25),
    ( -90, 0.45),
    (-135, 0.30),
]
for grau, alpha in DIRS:
    ax.axhline(grau, color="#adb5bd", linestyle=":", lw=0.8, alpha=alpha)

# ── Formatação ────────────────────────────────────────────────────────────────
ax.set_title(
    f"Azimute Solar em Curitiba — dia 21 de cada mês ({ANO})",
    fontsize=14, fontweight="bold", color="white", pad=12,
)
ax.set_xlabel("Hora local (BRT, UTC−3)", color="#ccc", fontsize=11)
ax.set_ylabel("Direção do sol (Norte = 0°)", color="#ccc", fontsize=11)

ax.xaxis.set_major_formatter(
    ticker.FuncFormatter(lambda x, _: f"{int(x):02d}:{int(round(x % 1 * 60)):02d}")
)
ax.xaxis.set_major_locator(ticker.MultipleLocator(1))

TICKS  = [ 135,   90,   45,   0,  -45,  -90, -135]
LABELS = [
    "Sudeste\n(135°)",
    "Leste\n(90°)",
    "Nordeste\n(45°)",
    "Norte\n(0°)",
    "Noroeste\n(315°)",
    "Oeste\n(270°)",
    "Sudoeste\n(225°)",
]

# Eixo Y direito (principal)
ax.set_yticks(TICKS)
ax.set_yticklabels(LABELS, color="#ccc", fontsize=8.5)
ax.set_ylim(-145, 145)

# Eixo Y esquerdo espelhado com os mesmos rótulos
ax2 = ax.twinx()
ax2.set_facecolor(PANEL)
ax2.set_ylim(ax.get_ylim())
ax2.set_yticks(TICKS)
ax2.set_yticklabels(LABELS, color="#ccc", fontsize=8.5)
ax2.tick_params(colors="#ccc")
for spine in ax2.spines.values():
    spine.set_edgecolor("#2d333b")

ax.grid(axis="x", linestyle="--", alpha=0.12, color="white")
ax.grid(axis="y", linestyle=":", alpha=0.0)  # linhas já desenhadas manualmente

# Anotação explicativa
ax.text(
    0.01, 0.01,
    "Curitiba (25°S): o sol cruza o Norte (~0°) ao meio-dia solar.\n"
    "Valores positivos = lado leste; negativos = lado oeste.",
    transform=ax.transAxes, color="#888", fontsize=7.5, va="bottom",
)

fig.subplots_adjust(right=0.83)
plt.savefig("azimute_solar_curitiba.png", dpi=150, facecolor=BG, bbox_inches="tight")
print("Gráfico salvo em azimute_solar_curitiba.png")
plt.show()
