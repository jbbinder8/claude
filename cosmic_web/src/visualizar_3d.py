"""
Visualizador 3D interativo da teia cósmica — volume rendering contínuo.

Usa go.Volume em vez de isosuperfícies: cada voxel contribui com uma
opacidade proporcional à sua densidade. Filamentos finos aparecem
como névoa azul; halos como pontos brilhantes vermelho/laranja.

Controles no browser:
  - Clique + arrastar   → orbitar
  - Scroll              → zoom
  - Botão direito       → pan
"""

import numpy as np
import plotly.graph_objects as go
import sys
import os
import webbrowser

DENSITY_FILE = os.path.join(os.path.dirname(__file__), 'Data', 'final_density.npy')
OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), 'teia_cosmica_3d.html')
BOX_MPC      = 100.0
MAX_GRID     = 96   # grade máxima para renderização fluida no browser


def carregar_e_reduzir(max_n=MAX_GRID):
    if not os.path.exists(DENSITY_FILE):
        print(f"Arquivo não encontrado: {DENSITY_FILE}")
        print("Rode primeiro: python pmesh.py")
        sys.exit(1)

    rho = np.load(DENSITY_FILE)
    N   = rho.shape[0]
    print(f"Grade original: {N}³  |  max densidade: {rho.max():.1f}")

    # Reduz a grade por block-averaging para manter performance no browser
    step = max(1, N // max_n)
    if step > 1:
        # block-average: preserva filamentos melhor que simples slice
        n_out = N // step
        rho = rho[:n_out*step, :n_out*step, :n_out*step]
        rho = rho.reshape(n_out, step, n_out, step, n_out, step).mean(axis=(1,3,5))
        print(f"Grade reduzida para renderização: {rho.shape[0]}³  (fator {step}x)")
    else:
        print(f"Grade mantida: {N}³")

    return rho


def construir_figura(rho):
    N   = rho.shape[0]
    coords = np.linspace(0, BOX_MPC, N, dtype=np.float32)
    X, Y, Z = np.meshgrid(coords, coords, coords, indexing='ij')

    # Escala log para comprimir o enorme range dinâmico (0 … milhares)
    rho_log = np.log1p(rho).astype(np.float32)
    vmin = float(np.percentile(rho_log[rho_log > 0], 10))
    vmax = float(rho_log.max())

    # Escala de cor: preto → roxo → azul → ciano → branco → amarelo → vermelho
    colorscale = [
        [0.00, '#000000'],
        [0.10, '#1a0050'],
        [0.25, '#0a1aaa'],
        [0.45, '#00aacc'],
        [0.60, '#ffffff'],
        [0.78, '#ffdd00'],
        [0.90, '#ff6600'],
        [1.00, '#cc0000'],
    ]

    # Curva de opacidade: vazio quase invisível, filamentos visíveis, halos opacos
    opacityscale = [
        [0.00, 0.000],
        [0.08, 0.000],
        [0.20, 0.015],
        [0.40, 0.060],
        [0.65, 0.200],
        [0.85, 0.550],
        [1.00, 0.900],
    ]

    vol = go.Volume(
        x=X.flatten(),
        y=Y.flatten(),
        z=Z.flatten(),
        value=rho_log.flatten(),
        isomin=vmin,
        isomax=vmax,
        opacity=0.12,
        surface_count=22,
        colorscale=colorscale,
        opacityscale=opacityscale,
        colorbar=dict(
            title=dict(text='log(1+ρ)', font=dict(color='white')),
            tickfont=dict(color='white'),
            len=0.7,
        ),
        caps=dict(x_show=False, y_show=False, z_show=False),
    )

    fig = go.Figure(data=[vol])
    fig.update_layout(
        title=dict(
            text=f'Teia Cósmica 3D — grade {N}³ renderizada, caixa {BOX_MPC} Mpc/h',
            font=dict(color='white', size=15),
        ),
        paper_bgcolor='black',
        scene=dict(
            bgcolor='black',
            xaxis=dict(title='x [Mpc/h]', color='#888', showbackground=False, gridcolor='#222'),
            yaxis=dict(title='y [Mpc/h]', color='#888', showbackground=False, gridcolor='#222'),
            zaxis=dict(title='z [Mpc/h]', color='#888', showbackground=False, gridcolor='#222'),
            aspectmode='cube',
            camera=dict(eye=dict(x=1.6, y=1.6, z=1.0)),
        ),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def main():
    rho = carregar_e_reduzir()
    print("Construindo volume 3D...")
    fig = construir_figura(rho)
    fig.write_html(OUTPUT_FILE, include_plotlyjs='cdn')
    print(f"Salvo: {OUTPUT_FILE}")
    print("Abrindo no navegador...")
    webbrowser.open('file:///' + OUTPUT_FILE.replace('\\', '/'))


if __name__ == '__main__':
    main()
