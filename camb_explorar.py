"""
Exploração básica do CAMB — Cosmologia padrão ΛCDM e variações simples.

IMPORTANTE: todos os gráficos mostram APENAS curvas teóricas calculadas
pelo CAMB (Boltzmann code). Nenhum dado observacional é plotado.

Eixo x principal: redshift z  (não-linear com o tempo)
Eixo x superior:  t [Gyr] — tempo cósmico calculado pelo modelo ΛCDM padrão.
                  A relação z ↔ t depende do modelo; o eixo superior usa o
                  ΛCDM (Planck 2018) como referência.

Parâmetros explorados:
  - H(z), q(z), Ω_b(z), D_L, D_A, χ, Ω_cdm(z), Ω_DE(z), a(z)

Nota: a(z) = 1/(1+z) é puramente geométrico — igual para todos os modelos.
"""

import camb
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

MODELOS = {
    "ΛCDM padrão\n(Planck 2018)": dict(H0=67.4, ombh2=0.0224, omch2=0.120, w=-1.0),
    "Ω_m baixo\n(Ω_m ≈ 0.20)":   dict(H0=67.4, ombh2=0.0224, omch2=0.070, w=-1.0),
    "Ω_m alto\n(Ω_m ≈ 0.40)":    dict(H0=67.4, ombh2=0.0224, omch2=0.180, w=-1.0),
    "w = −0.8\n(quintessência)":  dict(H0=67.4, ombh2=0.0224, omch2=0.120, w=-0.8),
    "w = −1.2\n(phantom)":        dict(H0=67.4, ombh2=0.0224, omch2=0.120, w=-1.2),
}

CORES = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
Z_MAX = 4.0
N_Z   = 500


def criar_resultados(params):
    pars = camb.CAMBparams()
    pars.set_cosmology(H0=params["H0"], ombh2=params["ombh2"], omch2=params["omch2"])
    pars.set_dark_energy(w=params["w"])
    pars.set_matter_power(redshifts=[0], kmax=2.0)
    return camb.get_background(pars)


def calcular_grandezas(results, z_arr, w):
    H_z = results.hubble_parameter(z_arr)
    H0  = results.hubble_parameter(0)
    E2  = (H_z / H0) ** 2

    chi = results.comoving_radial_distance(z_arr)
    D_L = results.luminosity_distance(z_arr)
    D_A = results.angular_diameter_distance(z_arr)
    t_z = results.physical_time(z_arr)          # Gyr

    dz    = 1e-4
    dH_dz = (results.hubble_parameter(z_arr + dz) -
              results.hubble_parameter(z_arr - dz)) / (2 * dz)
    q_z = -1 + (1 + z_arr) * dH_dz / H_z

    Omega_b0   = results.get_Omega("baryon", z=0)
    Omega_cdm0 = results.get_Omega("cdm",    z=0)
    Omega_DE0  = results.get_Omega("de",     z=0)

    Omega_b_z   = Omega_b0   * (1 + z_arr) ** 3            / E2
    Omega_cdm_z = Omega_cdm0 * (1 + z_arr) ** 3            / E2
    Omega_DE_z  = Omega_DE0  * (1 + z_arr) ** (3*(1 + w))  / E2
    a_z         = 1.0 / (1.0 + z_arr)

    return dict(H=H_z, chi=chi, D_L=D_L, D_A=D_A, q=q_z, t=t_z,
                Ob=Omega_b_z, Ocdm=Omega_cdm_z, Ode=Omega_DE_z, a=a_z)


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

z = np.linspace(0, Z_MAX, N_Z)
dados = {}
t_ref = None  # t(z) do modelo ΛCDM padrão — usado como referência no eixo superior

print("Calculando modelos...\n")
for i, (nome, params) in enumerate(MODELOS.items()):
    results = criar_resultados(params)
    dados[nome] = calcular_grandezas(results, z, params["w"])
    if i == 0:
        t_ref = dados[nome]["t"].copy()
    H0_val = results.hubble_parameter(0)
    Om0    = results.get_Omega("cdm", z=0) + results.get_Omega("baryon", z=0)
    ODE0   = results.get_Omega("de",  z=0)
    nome_ascii = nome.replace("\n", " ").encode("ascii", "replace").decode()
    print(f"  {nome_ascii:35s}  H0={H0_val:.1f}  Om0={Om0:.3f}  ODE0={ODE0:.3f}  w={params['w']}")

print("\nPronto. Gerando graficos...")

# ---------------------------------------------------------------------------
# Eixo secundário com tempo cósmico
# ---------------------------------------------------------------------------

def adicionar_eixo_tempo(ax, fontsize=7):
    """
    Adiciona eixo superior com t [Gyr] usando o modelo ΛCDM padrão como referência.
    t_ref decresce com z, logo revertemos para usar np.interp (exige xp crescente).
    """
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())

    # t_ref[0] ≈ 13.8 Gyr (z=0), t_ref[-1] ≈ 1.5 Gyr (z=Z_MAX)
    t_min = t_ref[-1]
    t_max = t_ref[0]

    t_candidates = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    t_ticks = [t for t in t_candidates if t_min + 0.4 <= t <= t_max - 0.4]

    if t_ticks:
        # t_ref[::-1] cresce de ~1.5 a ~13.8; z[::-1] decresce de Z_MAX a 0
        z_at_t = np.interp(t_ticks, t_ref[::-1], z[::-1])
        ax2.set_xticks(z_at_t)
        ax2.set_xticklabels([str(t) for t in t_ticks], fontsize=fontsize)
    else:
        ax2.set_xticks([])

    ax2.set_xlabel("t [Gyr]  (ref. ΛCDM)", fontsize=fontsize, labelpad=2)
    ax2.tick_params(top=True, labelsize=fontsize, length=3)
    return ax2

# ---------------------------------------------------------------------------
# Gráficos — grade 3×3
# ---------------------------------------------------------------------------
# [0,0] H(z)      [0,1] q(z)      [0,2] Ω_b(z)
# [1,0] D_L       [1,1] D_A       [1,2] χ
# [2,0] Ω_cdm(z)  [2,1] Ω_DE(z)  [2,2] a(z)

fig = plt.figure(figsize=(17, 13))
fig.suptitle(
    "Evolucao de Parametros Cosmologicos — CAMB  |  curvas teoricas  "
    "|  eixo superior: t [Gyr] (ref. LCDM Planck 2018)",
    fontsize=12, fontweight="bold", y=1.005,
)

gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.70, wspace=0.38)

ax_H    = fig.add_subplot(gs[0, 0])
ax_q    = fig.add_subplot(gs[0, 1])
ax_Ob   = fig.add_subplot(gs[0, 2])
ax_DL   = fig.add_subplot(gs[1, 0])
ax_DA   = fig.add_subplot(gs[1, 1])
ax_chi  = fig.add_subplot(gs[1, 2])
ax_Ocdm = fig.add_subplot(gs[2, 0])
ax_Ode  = fig.add_subplot(gs[2, 1])
ax_a    = fig.add_subplot(gs[2, 2])

nomes = list(MODELOS.keys())

for i, nome in enumerate(nomes):
    d   = dados[nome]
    lbl = nome.replace("\n", " ")
    c   = CORES[i]
    lw  = 2.2 if i == 0 else 1.5
    ls  = "-" if i == 0 else ["--", "-.", ":", (0, (3, 1, 1, 1))][i - 1]
    kw  = dict(color=c, lw=lw, ls=ls, label=lbl)

    ax_H.plot(z,    d["H"],    **kw)
    ax_q.plot(z,    d["q"],    **kw)
    ax_Ob.plot(z,   d["Ob"],   **kw)
    ax_DL.plot(z,   d["D_L"],  **kw)
    ax_DA.plot(z,   d["D_A"],  **kw)
    ax_chi.plot(z,  d["chi"],  **kw)
    ax_Ocdm.plot(z, d["Ocdm"], **kw)
    ax_Ode.plot(z,  d["Ode"],  **kw)
    ax_a.plot(d["t"], d["a"],  **kw)   # x = tempo cósmico (Gyr)

# Linhas de referência em q(z)
ax_q.axhline(0,    color="gray", lw=0.9, ls="--")
ax_q.axhline(-0.5, color="gray", lw=0.5, ls=":")


def fmt(ax, xlabel, ylabel, title, ylim=None):
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=20)
    if ylim:
        ax.set_ylim(*ylim)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=8)
    adicionar_eixo_tempo(ax)


fmt(ax_H,    "z", "H(z)  [km/s/Mpc]", "Taxa de Hubble  H(z)")
fmt(ax_q,    "z", "q(z)",              "Param. desaceleração  q(z)")
fmt(ax_Ob,   "z", "Ω_b(z)",            "Densidade bariônica  Ω_b(z)")
fmt(ax_DL,   "z", "D_L  [Mpc]",        "Distância de luminosidade  D_L")
fmt(ax_DA,   "z", "D_A  [Mpc]",        "Distância angular  D_A")
fmt(ax_chi,  "z", "χ  [Mpc]",          "Distância comóvel  χ")
fmt(ax_Ocdm, "z", "Ω_cdm(z)",          "Matéria escura  Ω_cdm(z)",  ylim=(0, 1.05))
fmt(ax_Ode,  "z", "Ω_DE(z)",           "Energia escura  Ω_DE(z)",   ylim=(0, 1.05))
# Painel a(t): eixo principal = t [Gyr], eixo secundário = z
ax_a.set_ylabel("a = 1/(1+z)", fontsize=9)
ax_a.set_xlabel("t  [Gyr]", fontsize=9)
ax_a.set_title("Fator de escala  a(t)", fontsize=10, fontweight="bold", pad=20)
ax_a.set_ylim(0, 1.05)
ax_a.grid(True, alpha=0.3)
ax_a.tick_params(labelsize=8)

# Eixo superior com z (usando t_ref do ΛCDM como referência de posição)
ax_a_top = ax_a.twiny()
ax_a_top.set_xlim(ax_a.get_xlim())
z_ticks  = [4, 3, 2, 1.5, 1, 0.5, 0]
t_at_z   = np.interp(z_ticks, z, t_ref)    # t_ref[i] = t(z[i]), z crescente ok
ax_a_top.set_xticks(t_at_z)
ax_a_top.set_xticklabels([str(zv) for zv in z_ticks], fontsize=7)
ax_a_top.set_xlabel("z  (ref. ΛCDM)", fontsize=7, labelpad=2)
ax_a_top.tick_params(top=True, labelsize=7, length=3)

# Legenda no painel H(z)
handles, labels = ax_H.get_legend_handles_labels()
ax_H.legend(handles, labels, fontsize=7.5, loc="upper left",
            framealpha=0.92, ncol=1)

plt.savefig("camb_evolucao_parametros.png", dpi=150, bbox_inches="tight")
print("Grafico salvo em  camb_evolucao_parametros.png")
plt.show()
