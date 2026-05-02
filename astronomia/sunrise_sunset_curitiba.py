"""
Nascer e pôr do sol em Curitiba ao longo do ano.
Dependências: astral, matplotlib, pytz
    pip install astral matplotlib pytz
"""

from astral import LocationInfo
from astral.sun import sun
from datetime import date, timedelta

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pytz

CURITIBA = LocationInfo(
    name="Curitiba",
    region="Brazil",
    timezone="America/Sao_Paulo",
    latitude=-25.4284,
    longitude=-49.2733,
)

TZ = pytz.timezone("America/Sao_Paulo")
ANO = 2025

start = date(ANO, 1, 1)
days = [start + timedelta(days=i) for i in range(365)]

sunrises, sunsets, noons = [], [], []
for d in days:
    s = sun(CURITIBA.observer, date=d, tzinfo=TZ)
    sunrises.append(s["sunrise"])
    sunsets.append(s["sunset"])
    noons.append(s["noon"])


def to_hours(dt):
    return dt.hour + dt.minute / 60 + dt.second / 3600


rise_h  = [to_hours(t) for t in sunrises]
set_h   = [to_hours(t) for t in sunsets]
noon_h  = [to_hours(t) for t in noons]
# Meia-noite solar = meio-dia solar + 12h (mod 24)
# Para Curitiba fica perto de 0h; exibe também em +24 para aparecer no topo do gráfico
smid_h       = [(n + 12) % 24 for n in noon_h]          # ~0h (fundo do gráfico)
smid_top_h   = [h + 24 for h in smid_h]                  # ~24h (topo do gráfico)

# ── cores ─────────────────────────────────────────────────────────────────────
BG    = "#0d1117"
NIGHT = "#11151c"
DAY   = "#f5c842"

# ── gráfico ───────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 8))
fig.patch.set_facecolor(BG)
ax.set_facecolor(NIGHT)

# Período noturno antes do nascer e após o pôr — faixas escuras explícitas
ax.fill_between(days, 0,      rise_h, color="#090c12", zorder=1)
ax.fill_between(days, set_h,  24,     color="#090c12", zorder=1)

# Período diurno
ax.fill_between(days, rise_h, set_h, color=DAY, alpha=0.30, zorder=2, label="Período diurno")

# Curvas principais
ax.plot(days, rise_h,    color="#f4a261", lw=2,   zorder=4, label="Nascer do sol")
ax.plot(days, set_h,     color="#e63946", lw=2,   zorder=4, label="Pôr do sol")
ax.plot(days, noon_h,    color="#ffd166", lw=1.5, zorder=4, linestyle="--", label="Meio-dia solar")
# Meia-noite solar: linha no fundo (~0h) e no topo (~24h) — mesmo instante, lados opostos
ax.plot(days, smid_h,    color="#90e0ef", lw=1.5, zorder=4, linestyle=":", label="Meia-noite solar")
ax.plot(days, smid_top_h,color="#90e0ef", lw=1.5, zorder=4, linestyle=":")

# Solstícios
for mes, dia, rotulo, va, ypos in [
    (6,  21, "Solstício de inverno", "top",    23.5),
    (12, 21, "Solstício de verão",   "bottom",  0.5),
]:
    d = date(ANO, mes, dia)
    ax.axvline(d, color="#adb5bd", linestyle="--", lw=0.8, alpha=0.45)
    ax.text(d, ypos, rotulo, ha="center", va=va, fontsize=8, color="#adb5bd")

# ── eixos e formatação ────────────────────────────────────────────────────────
ax.set_title(f"Nascer e Pôr do Sol em Curitiba — {ANO}", fontsize=14,
             fontweight="bold", color="white", pad=12)
ax.set_xlabel("Mês", color="#ccc")
ax.set_ylabel("Hora local (BRT, UTC−3)", color="#ccc")

ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
ax.tick_params(colors="#ccc")

for spine in ax.spines.values():
    spine.set_edgecolor("#2d333b")

ax.yaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f"{int(x) % 24:02d}:00")
)
ax.set_ylim(0, 24)
ax.set_yticks(range(0, 25, 2))

ax.grid(axis="y", linestyle="--", alpha=0.15, color="white")
ax.grid(axis="x", linestyle=":",  alpha=0.15, color="white")
ax.legend(loc="upper left", facecolor="#1c2128", labelcolor="white",
          edgecolor="#2d333b", framealpha=0.9)

plt.tight_layout()
plt.savefig("sunrise_sunset_curitiba.png", dpi=150, facecolor=BG)
print("Gráfico salvo em sunrise_sunset_curitiba.png")
plt.show()
