"""Evaluación de soluciones VRPTW: distancia total y verificación de factibilidad.

Reglas (Solomon): cada cliente se visita exactamente una vez; la carga de una ruta no supera
la capacidad; se puede llegar antes de que abra la ventana y esperar, pero el servicio debe
empezar a más tardar al cierre; el camión vuelve al depósito antes de que cierre.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .instancia import Instancia

TOL = 1e-6


@dataclass
class Evaluacion:
    distancia: float
    factible: bool
    n_rutas: int
    violaciones: list[str] = field(default_factory=list)


def distancia_ruta(inst: Instancia, ruta: list[int]) -> float:
    nodos = [0, *ruta, 0]
    return float(inst.dist[nodos[:-1], nodos[1:]].sum())


def horario(inst: Instancia, ruta: list[int]) -> list[dict]:
    """Llegada, inicio y fin de servicio de cada parada (incluye la vuelta al depósito)."""
    t, previo, filas = 0.0, 0, []
    for c in [*ruta, 0]:
        llegada = t + inst.dist[previo, c]
        inicio = max(llegada, inst.inicio[c])
        filas.append({"cliente": c, "llegada": llegada, "inicio": inicio,
                      "fin": inicio + inst.servicio[c], "espera": inicio - llegada})
        t, previo = inicio + inst.servicio[c], c
    return filas


def evaluar(inst: Instancia, rutas: list[list[int]]) -> Evaluacion:
    viol = []
    visitas = np.zeros(inst.n_clientes + 1, dtype=int)
    for r in rutas:
        for c in r:
            if not 1 <= c <= inst.n_clientes:
                viol.append(f"cliente {c} no existe")
            else:
                visitas[c] += 1
    faltan = np.flatnonzero(visitas[1:] == 0) + 1
    repetidos = np.flatnonzero(visitas[1:] > 1) + 1
    if len(faltan):
        viol.append(f"{len(faltan)} clientes sin visitar")
    if len(repetidos):
        viol.append(f"{len(repetidos)} clientes visitados más de una vez")
    for k, r in enumerate(rutas):
        if not r:
            continue
        carga = int(inst.demanda[r].sum())
        if carga > inst.capacidad:
            viol.append(f"ruta {k + 1}: carga {carga} > capacidad {inst.capacidad}")
        for p in horario(inst, r):
            if p["inicio"] > inst.fin[p["cliente"]] + TOL:
                quien = "depósito" if p["cliente"] == 0 else f"cliente {p['cliente']}"
                viol.append(f"ruta {k + 1}: llega tarde a {quien}")
                break
    rutas_usadas = [r for r in rutas if r]
    return Evaluacion(sum(distancia_ruta(inst, r) for r in rutas_usadas), not viol,
                      len(rutas_usadas), viol)
