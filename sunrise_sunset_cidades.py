"""
Comparativo de nascer e pôr do sol entre cidades ao longo do ano.
Cada cidade em horário local próprio.
Dependências: astral, matplotlib, pytz, numpy
    pip install astral matplotlib pytz numpy
"""

from astral import LocationInfo
from astral.sun import sun
from datetime import date, timedelta

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pytz

# ── Cidades ───────────────────────────────────────────────────────────────────
CIDADES = [
    {
        "nome":  "Curitiba",
        "lat":   -25.4284, "lon": -49.2733,
        "tz":    "America/Sao_Paulo",
        "cor":   "#f4a261",
    },
    {
        "nome":  "Rio de Janeiro",
        "lat":   -22.9068, "lon": -43.1729,
        "tz":    "America/Sao_Paulo",
        "cor":   "#2ec4b6",
    },
    {
        "nome":  "Ushuaia",
        "lat":   -54.8019, "lon": -68.3030,
        "tz":    "America/Argentina/Ushuaia",
        "cor":   "#e63946",
    },
    {
        "nome":  "Miami",
        "lat":    25.7617, "lon": -80.1918,
        "tz":    "America/New_York",
        "cor":   "#f1c0e8",
    },
    {
        "nome":  "New York",
        "lat":    40.7128, "lon": -74.0060,
        "tz":    "America/New_York",
        "cor":   "#a8dadc",
    },
    {
        "nome":  "Paris",
        "lat":    48.8566, "lon":   2.3522,
        "tz":    "Europe/Paris",
        "cor":   "#cdb4db",
    },
    {
        "nome":  "Berlim",
        "lat":    52.5200, "lon":  13.4050,
        "tz":    "Europe/Berlin",
        "cor":   "#b5e48c",
    },
]

ANO   = 2025
start = date(ANO, 1, 1)
days  = [start + timedelta(days=i) for i in range(365)]


def to_hours(dt):
    return dt.hour + dt.minute / 60 + dt.second / 3600


# ── Calcular nascer e pôr para cada cidade ────────────────────────────────────
for c in CIDADES:
    loc = LocationInfo(
        name=c["nome"],
        latitude=c["lat"],
        longitude=c["lon"],
        timezone=c["tz"],
    )
    tz    = pytz.timezone(c["tz"])
    rises, sets = [], []
    for d in days:
        try:
            s = sun(loc.observer, date=d, tzinfo=tz)
            rises.append(to_hours(s["sunrise"]))
            sets.append(to_hours(s["sunset"]))
        except Exception:
            rises.append(np.nan)
            sets.append(np.nan)
    c["rises"]    = rises
    c["sets"]     = sets
    c["duration"] = [
        s - r if not (np.isnan(s) or np.isnan(r)) else np.nan
        for r, s in zip(rises, sets)
    ]


def label_line(ax, days, values, nome, cor):
    """Escreve o nome da cidade ao final da linha, com anti-sobreposição leve."""
    # Pega o último valor válido
    last_val = next((v for v in reversed(values) if not np.isnan(v)), None)
    if last_val is None:
        return
    ax.text(
        days[-1] + timedelta(days=4), last_val,
        nome, color=cor, fontsize=8.5, va="center", ha="left",
        clip_on=False,
    )


# ── Gráfico ───────────────────────────────────────────────────────────────────
BG    = "#0d1117"
PANEL = "#11151c"

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
fig.patch.set_facecolor(BG)

for ax in (ax1, ax2):
    ax.set_facecolor(PANEL)
    ax.tick_params(colors="#ccc")
    for spine in ax.spines.values():
        spine.set_edgecolor("#2d333b")
    ax.grid(linestyle="--", alpha=0.15, color="white")

# ── Subplot 1: Duração do dia ─────────────────────────────────────────────────
for c in CIDADES:
    ax1.plot(days, c["duration"], color=c["cor"], lw=2)
    label_line(ax1, days, c["duration"], c["nome"], c["cor"])

# Linha de referência: 12h (equinócio)
ax1.axhline(12, color="#555", linestyle="--", lw=0.8, alpha=0.7)
ax1.text(days[3], 12.15, "12h (equinócio)", color="#888", fontsize=7.5)

ax1.set_title(f"Comparativo Solar entre Cidades — {ANO}",
              fontsize=14, fontweight="bold", color="white", pad=10)
ax1.set_ylabel("Duração do dia (horas)", color="#ccc", fontsize=11)

all_dur = [v for c in CIDADES for v in c["duration"] if not np.isnan(v)]
ax1.set_ylim(min(all_dur) - 0.4, max(all_dur) + 0.4)
ax1.yaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f"{int(x)}h{int(round(x % 1 * 60)):02d}")
)

# ── Subplot 2: Pôr do sol ─────────────────────────────────────────────────────
for c in CIDADES:
    ax2.plot(days, c["sets"], color=c["cor"], lw=2)
    label_line(ax2, days, c["sets"], c["nome"], c["cor"])

ax2.set_ylabel("Pôr do sol (hora local)", color="#ccc", fontsize=11)
ax2.set_xlabel("Mês", color="#ccc", fontsize=11)

all_sets = [v for c in CIDADES for v in c["sets"] if not np.isnan(v)]
ax2.set_ylim(min(all_sets) - 0.4, max(all_sets) + 0.4)
ax2.yaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f"{int(x):02d}:{int(round(x % 1 * 60)):02d}")
)

# Eixo X: limita até dez/31 (os rótulos ficam além, com clip_on=False)
ax2.set_xlim(days[0], days[-1])
ax2.xaxis.set_major_locator(mdates.MonthLocator())
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

# Margem direita para os rótulos não serem cortados
fig.subplots_adjust(right=0.84)

plt.savefig("sunrise_sunset_cidades.png", dpi=150, facecolor=BG,
            bbox_inches="tight")
print("Gráfico salvo em sunrise_sunset_cidades.png")
plt.show()
