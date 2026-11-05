"""Animación de vehículos recorriendo sus rutas (figura de Plotly con frames).

El tiempo es el real del horario de cada ruta: todos los vehículos salen del depósito en t = 0;
entre paradas avanzan en línea recta a velocidad constante (salida = fin del servicio anterior,
llegada = `llegada`), y se quedan detenidos en el cliente mientras esperan que abra la ventana y
mientras lo atienden.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from ruteo.evaluacion import horario

PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TINTA = "#1f2430"
GRIS = "#b8bec8"
VEHICULO = "🚚"  # marcador de cada camioneta de reparto en la animación


def _trayectoria(inst, ruta: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tiempos y posiciones clave de una ruta: salida del depósito, y por cada parada la llegada
    y el fin del servicio (entre ambos el vehículo está detenido)."""
    t, nodos = [0.0], [0]
    for f in horario(inst, ruta):
        t += [f["llegada"], f["fin"]]
        nodos += [f["cliente"], f["cliente"]]
    xy = inst.coords[nodos]
    return np.asarray(t), xy[:, 0], xy[:, 1]


def figura_animada(inst, rutas: list[list[int]], n_frames: int = 120,
                   duracion_ms: int = 60) -> go.Figure:
    rutas = [list(r) for r in rutas if len(r)]
    xy = inst.coords
    trays = [_trayectoria(inst, r) for r in rutas]
    t_max = max((tr[0][-1] for tr in trays), default=0.0) or 1.0
    tiempos = np.linspace(0.0, t_max, n_frames)

    # Momento en que termina el servicio de cada cliente (para pintarlo con el color de su ruta).
    clientes = [c for r in rutas for c in r]
    atendido = np.full(len(clientes), np.inf)
    color_cliente = []
    for k, r in enumerate(rutas):
        for f in horario(inst, r)[:-1]:
            atendido[clientes.index(f["cliente"])] = f["fin"]
        color_cliente += [PALETA[k % len(PALETA)]] * len(r)
    color_cliente = np.asarray(color_cliente, dtype=object)

    fig = go.Figure()
    # 1. Rutas completas, tenues (estáticas). Llevan la leyenda.
    for k, r in enumerate(rutas):
        nodos = [0, *r, 0]
        fig.add_trace(go.Scatter(x=xy[nodos, 0], y=xy[nodos, 1], mode="lines", name=f"Ruta {k + 1}",
                                 legendgroup=f"r{k}", hoverinfo="skip",
                                 line=dict(color=PALETA[k % len(PALETA)], width=1.5), opacity=0.3))
    # 2. Número de orden de cada parada (estático): la dirección se lee sin reproducir.
    orden_x, orden_y, orden_txt, orden_col = [], [], [], []
    for k, r in enumerate(rutas):
        for i, c in enumerate(r):
            orden_x.append(xy[c, 0])
            orden_y.append(xy[c, 1])
            orden_txt.append(str(i + 1))
            orden_col.append(PALETA[k % len(PALETA)])
    fig.add_trace(go.Scatter(x=orden_x, y=orden_y, mode="text", text=orden_txt, showlegend=False,
                             textposition="top right", hoverinfo="skip",
                             textfont=dict(size=10, color=orden_col)))
    # 3. Depósito (estático).
    fig.add_trace(go.Scatter(x=[xy[0, 0]], y=[xy[0, 1]], mode="markers", name="Depósito",
                             marker=dict(symbol="square", size=15, color=TINTA,
                                         line=dict(color="white", width=2)),
                             hovertemplate="Depósito<extra></extra>"))
    animadas_desde = len(fig.data)

    def _estado(t: float):
        tramos, camiones = [], []
        for kt, kx, ky in trays:
            px, py = np.interp(t, kt, kx), np.interp(t, kt, ky)
            hasta = np.searchsorted(kt, t, side="right")
            tramos.append((np.append(kx[:hasta], px), np.append(ky[:hasta], py)))
            camiones.append((px, py))
        colores = np.where(atendido <= t + 1e-9, color_cliente, GRIS)
        return tramos, camiones, colores

    tramos, camiones, colores = _estado(0.0)
    # 4. Tramo ya recorrido de cada ruta (animado).
    for k, (tx, ty) in enumerate(tramos):
        fig.add_trace(go.Scatter(x=tx, y=ty, mode="lines", legendgroup=f"r{k}", showlegend=False,
                                 hoverinfo="skip", line=dict(color=PALETA[k % len(PALETA)], width=3)))
    # 5. Clientes: grises hasta que se atienden (animado).
    fig.add_trace(go.Scatter(x=xy[clientes, 0], y=xy[clientes, 1], mode="markers", showlegend=False,
                             marker=dict(size=9, color=colores, line=dict(color="white", width=1)),
                             text=[f"Cliente {c}" for c in clientes],
                             hovertemplate="%{text}<extra></extra>"))
    # 6. Un vehículo por ruta (animado).
    for k, (px, py) in enumerate(camiones):
        fig.add_trace(go.Scatter(x=[px], y=[py], mode="markers+text", text=[VEHICULO],
                                 textposition="middle center", textfont=dict(size=20),
                                 marker=dict(size=26, color=PALETA[k % len(PALETA)], opacity=0.35),
                                 name=f"Vehículo {k + 1}", meta="vehiculo", legendgroup=f"r{k}",
                                 showlegend=False, hovertemplate=f"Vehículo {k + 1}<extra></extra>"))
    indices = list(range(animadas_desde, len(fig.data)))

    # Los frames se arman como diccionarios simples (sin la validación de plotly, que con
    # cientos de trazas por frame tarda segundos).
    frames = []
    for t in tiempos:
        tramos, camiones, colores = _estado(float(t))
        datos = [{"type": "scatter", "x": np.round(tx, 2).tolist(), "y": np.round(ty, 2).tolist()}
                 for tx, ty in tramos]
        datos.append({"type": "scatter", "marker": {"color": colores.tolist()}})
        datos += [{"type": "scatter", "x": [round(float(px), 2)], "y": [round(float(py), 2)]}
                  for px, py in camiones]
        frames.append({"data": datos, "traces": indices, "name": f"{t:.0f}"})

    margen = 0.06 * float(np.ptp(xy, axis=0).max() or 1.0)
    jugar = dict(frame=dict(duration=duracion_ms, redraw=False), fromcurrent=True,
                 transition=dict(duration=0), mode="immediate")
    pausar = dict(frame=dict(duration=0, redraw=False), transition=dict(duration=0), mode="immediate")
    fig.update_layout(
        height=600, margin=dict(l=10, r=10, t=50, b=90), separators=",.",
        plot_bgcolor="white", paper_bgcolor="white", font=dict(color=TINTA),
        title=dict(text="Recorrido de los vehículos (el control indica el tiempo t)", x=0),
        legend=dict(font=dict(size=11)),
        updatemenus=[dict(type="buttons", direction="left", x=0, y=-0.06, xanchor="left",
                          yanchor="top", pad=dict(t=0, r=10), showactive=False,
                          buttons=[dict(label="▶ Reproducir", method="animate", args=[None, jugar]),
                                   dict(label="❚❚ Pausa", method="animate", args=[[None], pausar])])],
        sliders=[dict(active=0, x=0.22, len=0.78, y=-0.03, yanchor="top", pad=dict(t=0),
                      currentvalue=dict(prefix="t = ", font=dict(size=12)),
                      steps=[dict(label=f["name"], method="animate",
                                  args=[[f["name"]], dict(frame=dict(duration=0, redraw=False),
                                                       mode="immediate", transition=dict(duration=0))])
                             for f in frames])])
    fig.update_xaxes(range=[xy[:, 0].min() - margen, xy[:, 0].max() + margen],
                     gridcolor="#eceef2", zeroline=False, constrain="domain")
    fig.update_yaxes(range=[xy[:, 1].min() - margen, xy[:, 1].max() + margen],
                     gridcolor="#eceef2", zeroline=False, scaleanchor="x", scaleratio=1)
    figura = fig.to_dict()
    figura["frames"] = frames
    return go.Figure(figura, _validate=False)
