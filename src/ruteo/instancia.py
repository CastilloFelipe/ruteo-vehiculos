"""Lectura de instancias VRPTW (formato VRPLIB de PyVRP/Instances) y mejores soluciones conocidas.

Convención de índices: 0 es el depósito y 1..n los clientes (igual que en los archivos .sol).
Distancias euclidianas truncadas a un decimal (convención DIMACS 2021, la que usan las
mejores soluciones conocidas publicadas).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

DATOS = Path(__file__).resolve().parents[2] / "data" / "solomon"


@dataclass
class Instancia:
    nombre: str
    capacidad: int
    vehiculos: int
    coords: np.ndarray    # (n+1, 2)
    demanda: np.ndarray   # (n+1,) depósito = 0
    inicio: np.ndarray    # (n+1,) apertura de la ventana horaria
    fin: np.ndarray       # (n+1,) cierre de la ventana horaria
    servicio: np.ndarray  # (n+1,) tiempo de atención; depósito = 0
    dist: np.ndarray      # (n+1, n+1) distancia = tiempo de viaje

    @property
    def n_clientes(self) -> int:
        return len(self.demanda) - 1

    def recortar(self, n: int) -> "Instancia":
        """Primeros n clientes (para resolver de forma exacta versiones pequeñas)."""
        k = n + 1
        return Instancia(f"{self.nombre}-{n}", self.capacidad, self.vehiculos,
                         self.coords[:k], self.demanda[:k], self.inicio[:k], self.fin[:k],
                         self.servicio[:k], self.dist[:k, :k])


def _secciones(texto: str) -> tuple[dict[str, str], dict[str, list[list[float]]]]:
    cabecera, secciones, actual = {}, {}, None
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea == "EOF":
            continue
        if linea.endswith("_SECTION"):
            actual = linea
            secciones[actual] = []
        elif ":" in linea and actual is None:
            k, v = linea.split(":", 1)
            cabecera[k.strip()] = v.strip()
        elif actual:
            secciones[actual].append([float(t) for t in linea.split()])
    return cabecera, secciones


def leer_instancia(ruta: str | Path) -> Instancia:
    ruta = Path(ruta)
    cab, sec = _secciones(ruta.read_text())
    coords = np.array([f[1:3] for f in sec["NODE_COORD_SECTION"]], dtype=float)
    demanda = np.array([f[1] for f in sec["DEMAND_SECTION"]], dtype=int)
    tw = np.array([f[1:3] for f in sec["TIME_WINDOW_SECTION"]], dtype=float)
    servicio = np.full(len(coords), float(cab.get("SERVICE_TIME", 0)))
    servicio[0] = 0.0
    dif = coords[:, None, :] - coords[None, :, :]
    # Convención DIMACS (la de las mejores soluciones publicadas): truncar a un decimal.
    dist = np.floor(np.sqrt((dif ** 2).sum(-1)) * 10) / 10
    return Instancia(cab["NAME"], int(cab["CAPACITY"]), int(cab.get("VEHICLES", len(coords))),
                     coords, demanda, tw[:, 0], tw[:, 1], servicio, dist)


def leer_solucion(ruta: str | Path) -> tuple[list[list[int]], float]:
    """Rutas (listas de clientes, sin depósito) y costo publicado de un archivo .sol."""
    rutas, costo = [], float("nan")
    for linea in Path(ruta).read_text().splitlines():
        if linea.startswith("Route"):
            rutas.append([int(t) for t in linea.split(":", 1)[1].split()])
        elif linea.lower().startswith("cost"):
            costo = float(linea.split()[1])
    return rutas, costo


def nombres() -> list[str]:
    return sorted(p.stem for p in DATOS.glob("*.vrp"))


def cargar(nombre: str) -> Instancia:
    return leer_instancia(DATOS / f"{nombre}.vrp")


def mejor_conocida(nombre: str) -> tuple[list[list[int]], float]:
    return leer_solucion(DATOS / f"{nombre}.sol")
