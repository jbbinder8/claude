"""
Exploração básica do CAMB — Cosmologia padrão ΛCDM e variações simples.

IMPORTANTE: todos os gráficos mostram APENAS curvas teóricas calculadas
pelo CAMB (Boltzmann code). Nenhum dado observacional é plotado.
O CAMB integra as equações de Friedmann e Boltzmann dado um conjunto
de parâmetros cosmológicos e retorna grandezas como H(z), distâncias,
densidades, etc. Para comparar com observações seria preciso sobrepor
pontos de supernovas Ia, BAO, CMB shift, etc. — o que não é feito aqui.

Parâmetros explorados (em função de redshift z):
  - Taxa de Hubble H(z)
  - Parâmetro de desaceleração q(z)
  - Densidade total de matéria Ω_m(z)
  - Distâncias: luminosidade D_L, angular D_A, comóvel χ
  - Densidade de matéria escura (CDM) Ω_cdm(z)
  - Densidade de energia escura Ω_DE(z)

Variações testadas:
  1. ΛCDM padrão (Planck 2018)
  2. Baixa densidade de matéria (Ω_m ≈ 0.20)
  3. Alta densidade de matéria (Ω_m ≈ 0.40)
  4. Energia escura com w = -0.8  (quintessência)
  5. Energia escura com w = -1.2  (phantom)
"""

import camb
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ---------------------------------------------------------------------------
# Configuração dos modelos
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


def criar_resultados(params: dict):
    """Roda o CAMB e devolve o objeto de resultados."""
    pars = camb.CAMBparams()
    pars.set_cosmology(
        H0=params["H0"],
        ombh2=params["ombh2"],
        omch2=params["omch2"],
    )
    pars.set_dark_energy(w=params["w"])
    pars.set_matter_power(redshifts=[0], kmax=2.0)
    return camb.get_background(pars)


def calcular_grandezas(results, z_arr, w):
    """Extrai grandezas cosmológicas para o array de redshifts."""
    H_z = results.hubble_parameter(z_arr)          # km/s/Mpc
    H0  = results.hubble_parameter(0)
    E2  = (H_z / H0) ** 2                          # E(z)² = [H(z)/H0]²

    chi = results.comoving_radial_distance(z_arr)  # Mpc
    D_L = results.luminosity_distance(z_arr)       # Mpc
    D_A = results.angular_diameter_distance(z_arr) # Mpc

    # Parâmetro de desaceleração q(z) via derivada numérica de H(z)
    dz    = 1e-4
    dH_dz = (results.hubble_parameter(z_arr + dz) -
              results.hubble_parameter(z_arr - dz)) / (2 * dz)
    q_z   = -1 + (1 + z_arr) * dH_dz / H_z

    # Densidades adimensionais no presente
    Omega_cdm0 = results.get_Omega("cdm",    z=0)
    Omega_b0   = results.get_Omega("baryon", z=0)
    Omega_DE0  = results.get_Omega("de",     z=0)

    Omega_m0 = Omega_cdm0 + Omega_b0

    # Evolução com z (equações de Friedmann, universo plano)
    # matéria ∝ (1+z)³, energia escura ∝ (1+z)^{3(1+w)}
    Omega_m_z   = Omega_m0  * (1 + z_arr) ** 3            / E2
    Omega_cdm_z = Omega_cdm0 * (1 + z_arr) ** 3           / E2
    Omega_DE_z  = Omega_DE0  * (1 + z_arr) ** (3*(1 + w)) / E2

    return dict(
        H=H_z, chi=chi, D_L=D_L, D_A=D_A, q=q_z,
        Om=Omega_m_z, Ocdm=Omega_cdm_z, Ode=Omega_DE_z,
    )


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

z = np.linspace(0, Z_MAX, N_Z)
dados = {}

print("Calculando modelos...\n")
for nome, params in MODELOS.items():
    results = criar_resultados(params)
    dados[nome] = calcular_grandezas(results, z, params["w"])
    H0_val = results.hubble_parameter(0)
    Om0    = results.get_Omega("cdm", z=0) + results.get_Omega("baryon", z=0)
    ODE0   = results.get_Omega("de", z=0)
    nome_ascii = nome.replace("\n", " ").encode("ascii", "replace").decode()
    print(f"  {nome_ascii:35s}  H0={H0_val:.1f}  Om0={Om0:.3f}  ODE0={ODE0:.3f}  w={params['w']}")

print("\nPronto. Gerando graficos...")

# ---------------------------------------------------------------------------
# Gráficos — grade 3×3
# ---------------------------------------------------------------------------
# Layout:
#  [0,0] H(z)       [0,1] q(z)      [0,2] Ω_m(z) total
#  [1,0] D_L        [1,1] D_A       [1,2] χ comóvel
#  [2,0] Ω_cdm(z)   [2,1] Ω_DE(z)  [2,2] q(z) detalhe hoje

fig = plt.figure(figsize=(16, 12))
fig.suptitle(
    "Evolucao de Parametros Cosmologicos — CAMB  |  curvas 100% teoricas (sem dados obs.)",
    fontsize=13, fontweight="bold", y=0.99,
)

gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.44, wspace=0.35)

ax_H    = fig.add_subplot(gs[0, 0])
ax_q    = fig.add_subplot(gs[0, 1])
ax_Om   = fig.add_subplot(gs[0, 2])
ax_DL   = fig.add_subplot(gs[1, 0])
ax_DA   = fig.add_subplot(gs[1, 1])
ax_chi  = fig.add_subplot(gs[1, 2])
ax_Ocdm = fig.add_subplot(gs[2, 0])
ax_Ode  = fig.add_subplot(gs[2, 1])
ax_qz   = fig.add_subplot(gs[2, 2])

nomes = list(MODELOS.keys())

for i, nome in enumerate(nomes):
    d   = dados[nome]
    lbl = nome.replace("\n", " ")
    c   = CORES[i]
    lw  = 2.2 if i == 0 else 1.5
    ls  = "-" if i == 0 else ["--", "-.", ":", (0, (3, 1, 1, 1))][i - 1]

    kw = dict(color=c, lw=lw, ls=ls, label=lbl)

    ax_H.plot(z,    d["H"],    **kw)
    ax_q.plot(z,    d["q"],    **kw)
    ax_Om.plot(z,   d["Om"],   **kw)
    ax_DL.plot(z,   d["D_L"],  **kw)
    ax_DA.plot(z,   d["D_A"],  **kw)
    ax_chi.plot(z,  d["chi"],  **kw)
    ax_Ocdm.plot(z, d["Ocdm"], **kw)
    ax_Ode.plot(z,  d["Ode"],  **kw)
    ax_qz.plot(z,   d["q"],    **kw)

# Referências em q(z)
for ax in [ax_q, ax_qz]:
    ax.axhline(0,    color="gray", lw=0.9, ls="--", label="q=0 (transição)")
    ax.axhline(-0.5, color="gray", lw=0.5, ls=":",  label="q=-0.5 (ΛCDM hoje)")

# Referência em Ω_DE(z=0)
ax_Ode.axvline(0, color="gray", lw=0.6, ls=":")


def fmt(ax, xlabel, ylabel, title, ylim=None):
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold")
    if ylim:
        ax.set_ylim(*ylim)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=8)


fmt(ax_H,    "z", "H(z)  [km/s/Mpc]", "Taxa de Hubble  H(z)")
fmt(ax_q,    "z", "q(z)",              "Param. desaceleração  q(z)")
fmt(ax_Om,   "z", "Ω_m(z)",            "Densidade total de matéria  Ω_m(z)", ylim=(0, 1.05))
fmt(ax_DL,   "z", "D_L  [Mpc]",        "Distância de luminosidade  D_L")
fmt(ax_DA,   "z", "D_A  [Mpc]",        "Distância angular  D_A")
fmt(ax_chi,  "z", "χ  [Mpc]",          "Distância comóvel  χ")
fmt(ax_Ocdm, "z", "Ω_cdm(z)",          "Densidade de matéria escura  Ω_cdm(z)", ylim=(0, 1.05))
fmt(ax_Ode,  "z", "Ω_DE(z)",           "Densidade de energia escura  Ω_DE(z)",  ylim=(0, 1.05))
fmt(ax_qz,   "z", "q(z)",              "q(z)  detalhe  (z < 4)")

# Legenda no painel H(z) — único painel com todos os modelos identificados
handles, labels = ax_H.get_legend_handles_labels()
ax_H.legend(handles, labels, fontsize=7.5, loc="upper left",
            framealpha=0.92, ncol=1)

plt.savefig("camb_evolucao_parametros.png", dpi=150, bbox_inches="tight")
print("Grafico salvo em  camb_evolucao_parametros.png")
plt.show()
