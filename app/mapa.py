"""Figuras sobre el mapa de calles de OpenStreetMap (vista Caso Santiago).

- `fig_mapa_calles`: rutas en un mapa interactivo (`go.Scattermap`, MapLibre; si la versión de
  plotly no lo tiene, `go.Scattermapbox`). No necesita token.
- `figura_animada_calles`: la misma animación de `animacion.figura_animada`, con el mapa de
  fondo. Los mapas de MapLibre dibujan el texto con fuentes descargadas que no traen emojis, así
  que la 🚚 no se vería sobre un Scattermap. Por eso la animación usa un gráfico normal en
  coordenadas Web Mercator (km) con las teselas de OpenStreetMap como imágenes de fondo: el
  navegador las descarga igual que lo haría el mapa interactivo.
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go

from animacion import PALETA, TINTA, figura_animada

TESELAS = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ATRIBUCION = "© colaboradores de OpenStreetMap"
RADIO_MERCATOR_KM = 6378.137  # Web Mercator (EPSG:3857)
MUNDO_KM = 2 * math.pi * RADIO_MERCATOR_KM
GRIS = "#8a93a3"
_MAPLIBRE = hasattr(go, "Scattermap")  # plotly >= 5.24


def mercator_km(latlon: np.ndarray) -> np.ndarray:
    """(lat, lon) en grados → (x, y) Web Mercator en km. Es conforme: con escala 1:1 en ambos
    ejes, las formas locales se ven como en el mapa."""
    latlon = np.asarray(latlon, dtype=float)
    lat, lon = np.radians(latlon[:, 0]), np.radians(latlon[:, 1])
    return np.column_stack([RADIO_MERCATOR_KM * lon, RADIO_MERCATOR_KM * np.arcsinh(np.tan(lat))])


def zoom_teselas(alto_km: float, alto_px: float) -> int:
    """Nivel de zoom de las teselas (de 256 px) que se ven cerca de su tamaño original
    (`alto_km` del mapa ocupan `alto_px` de pantalla)."""
    z = math.log2(alto_px * MUNDO_KM / (256 * max(alto_km, 1e-6)))
    return int(min(max(round(z), 3), 16))


def teselas(x0: float, x1: float, y0: float, y1: float, z: int) -> list[dict]:
    """Imágenes de layout (una por tesela de OpenStreetMap) que cubren [x0, x1] × [y0, y1] km."""
    lado = MUNDO_KM / 2 ** z
    mitad = MUNDO_KM / 2
    tx = range(math.floor((x0 + mitad) / lado), math.floor((x1 + mitad) / lado) + 1)
    ty = range(math.floor((mitad - y1) / lado), math.floor((mitad - y0) / lado) + 1)
    return [dict(source=TESELAS.format(z=z, x=i, y=j), xref="x", yref="y",
                 x=-mitad + i * lado, y=mitad - j * lado, sizex=lado, sizey=lado,
                 xanchor="left", yanchor="top", sizing="stretch", layer="below")
            for i in tx for j in ty if 0 <= i < 2 ** z and 0 <= j < 2 ** z]


def _atribucion(fig: go.Figure) -> None:
    fig.add_annotation(text=ATRIBUCION, xref="paper", yref="paper", x=1, y=0, xanchor="right",
                       yanchor="bottom", showarrow=False, font=dict(size=10, color=TINTA),
                       bgcolor="rgba(255,255,255,0.75)")


def fondo_osm(fig: go.Figure, alto_px: float = 480, ancho_max: float = 2.6) -> go.Figure:
    """Pone el mapa de OpenStreetMap de fondo en una figura cartesiana en Web Mercator (km).

    Toma los rangos de los ejes de la figura. Con escala 1:1, un eje puede ensancharse para
    llenar el gráfico: las teselas cubren hasta `ancho_max` veces el alto a lo ancho y 1,5
    veces el alto a lo alto (las que quedan fuera del gráfico no se ven).
    """
    (x0, x1), (y0, y1) = fig.layout.xaxis.range, fig.layout.yaxis.range
    cx, cy, alto = (x0 + x1) / 2, (y0 + y1) / 2, y1 - y0
    ancho = max(x1 - x0, ancho_max * alto)
    z = zoom_teselas(alto, alto_px)
    alto = 1.5 * alto  # en pantallas angostas lo que se ensancha es el eje y
    fig.update_layout(images=teselas(cx - ancho / 2, cx + ancho / 2, cy - alto / 2, cy + alto / 2, z),
                      plot_bgcolor="#f2efe9")
    sin_marcas = dict(showgrid=False, showticklabels=False, ticks="", title=None, zeroline=False,
                      constrain="range")
    fig.update_xaxes(**sin_marcas)
    fig.update_yaxes(**sin_marcas)
    _atribucion(fig)
    return fig


def figura_animada_calles(inst, latlon: np.ndarray, rutas: list[list[int]],
                          horarios: list[tuple[float, list[dict]]], textos: list[str],
                          formato_tiempo, alto: int = 650) -> go.Figure:
    """Animación de las camionetas sobre el mapa de calles (el control indica la hora)."""
    fig = figura_animada(inst, rutas, xy=mercator_km(latlon), horarios=horarios, textos=textos,
                         formato_tiempo=formato_tiempo, prefijo_tiempo="Hora: ",
                         titulo="Recorrido de las camionetas (el control indica la hora)",
                         rotulo="Camioneta", deposito="Centro de distribución", alto=alto)
    return fondo_osm(fig, alto_px=alto - 140)


def _encuadre(latlon: np.ndarray, alto_px: float, ancho_px: float = 900) -> tuple[dict, float]:
    """Centro y zoom de MapLibre (teselas de 512 px) para que todos los puntos quepan."""
    xy = mercator_km(latlon)
    (x0, y0), (x1, y1) = xy.min(axis=0), xy.max(axis=0)
    dx, dy = max(x1 - x0, 1e-3) * 1.15, max(y1 - y0, 1e-3) * 1.15
    z = math.log2(min(ancho_px / dx, alto_px / dy) * MUNDO_KM / 512)
    lat = math.degrees(math.atan(math.sinh((y0 + y1) / 2 / RADIO_MERCATOR_KM)))
    lon = math.degrees((x0 + x1) / 2 / RADIO_MERCATOR_KM)
    return dict(lat=lat, lon=lon), math.floor(z * 10) / 10


def fig_mapa_calles(latlon: np.ndarray, rutas: list[list[int]], textos: list[str], titulo: str,
                    rotulo: str = "Camioneta", alto: int = 560) -> go.Figure:
    """Rutas sobre un mapa interactivo de OpenStreetMap. Los clientes que no están en ninguna
    ruta se dibujan en gris (sirve para mostrar el caso antes de resolverlo)."""
    Traza = go.Scattermap if _MAPLIBRE else go.Scattermapbox
    fig = go.Figure()
    for k, r in enumerate(rutas):
        nodos = [0, *r, 0]
        color = PALETA[k % len(PALETA)]
        fig.add_trace(Traza(lat=latlon[nodos, 0], lon=latlon[nodos, 1], mode="lines+markers",
                            name=f"{rotulo} {k + 1}", line=dict(color=color, width=3),
                            marker=dict(size=10, color=color), text=[textos[c] for c in nodos],
                            hovertemplate=f"%{{text}}<extra>{rotulo} {k + 1}</extra>"))
    en_ruta = {c for r in rutas for c in r}
    libres = [c for c in range(1, len(latlon)) if c not in en_ruta]
    if libres:
        fig.add_trace(Traza(lat=latlon[libres, 0], lon=latlon[libres, 1], mode="markers",
                            name="Clientes", marker=dict(size=10, color=GRIS),
                            text=[textos[c] for c in libres], hovertemplate="%{text}<extra></extra>"))
    # Depósito: círculo oscuro con borde blanco (en estos mapas el marcador solo puede ser círculo).
    fig.add_trace(Traza(lat=[latlon[0, 0]], lon=[latlon[0, 1]], mode="markers", hoverinfo="skip",
                        marker=dict(size=22, color="white"), showlegend=False))
    fig.add_trace(Traza(lat=[latlon[0, 0]], lon=[latlon[0, 1]], mode="markers",
                        name="Centro de distribución", marker=dict(size=16, color=TINTA),
                        text=[textos[0]], hovertemplate="%{text}<extra></extra>"))
    centro, zoom = _encuadre(latlon, alto - 60)
    capa = "map" if _MAPLIBRE else "mapbox"
    fig.update_layout(**{capa: dict(style="open-street-map", center=centro, zoom=zoom)},
                      height=alto, margin=dict(l=10, r=10, t=50, b=10), separators=",.",
                      paper_bgcolor="white", font=dict(color=TINTA), hoverlabel=dict(bgcolor="white"),
                      title=dict(text=titulo, x=0), legend=dict(font=dict(size=11)))
    return fig
