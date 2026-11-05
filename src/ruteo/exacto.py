"""Solver exacto del VRPTW: MILP de dos índices resuelto con Gurobi.

Modelo (arcos x[i, j] binarios, i ≠ j, 0 = depósito):
  - cada cliente tiene exactamente un arco de entrada y uno de salida;
  - salen del depósito a lo más `vehiculos` camiones (y al menos ⌈demanda total / capacidad⌉);
  - t[i] ∈ [inicio[i], fin[i]] es la hora de inicio de servicio; si se usa el arco (i, j),
    t[j] ≥ t[i] + servicio[i] + dist[i, j] (big-M ajustado por arco, que además elimina subtours);
  - q[i] ∈ [demanda[i], capacidad] es la carga acumulada al salir de i; si se usa (i, j) entre
    clientes, q[j] ≥ q[i] + demanda[j] (MTZ de carga).
Objetivo: minimizar la distancia total.

Antes de construir el modelo se eliminan los arcos imposibles (por ventana horaria o por
capacidad) y las restricciones redundantes (big-M = 0, o carga total que cabe en un camión).
Con la licencia pip de Gurobi (limitada a 2000 variables y 2000 restricciones) eso alcanza
para versiones recortadas de las instancias de Solomon; para instancias más grandes hace falta
una licencia académica (y fijar `LIMITE_VARIABLES = LIMITE_RESTRICCIONES = None`).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import gurobipy as gp
from gurobipy import GRB

from .evaluacion import distancia_ruta, evaluar
from .instancia import Instancia

# Límites de la licencia de tamaño restringido que trae `pip install gurobipy`.
LIMITE_VARIABLES: int | None = 2000
LIMITE_RESTRICCIONES: int | None = 2000


@dataclass
class ResultadoExacto:
    """Resultado de Gurobi. `cota` es la cota inferior probada y `gap` la brecha relativa
    (incumbente − cota) / incumbente que reporta Gurobi: 0 significa óptimo probado."""
    rutas: list[list[int]]
    distancia: float | None
    cota: float | None
    gap: float | None
    estado: str
    segundos: float


@dataclass
class _Estructura:
    """Arcos y restricciones que sobreviven a la poda (se cuentan antes de construir)."""
    arcos: list[tuple[int, int]]
    tiempo: list[tuple[int, int, float]]   # (i, j, M_ij) con j cliente
    regreso: list[tuple[int, float]]       # (i, M_i0): volver al depósito antes de su cierre
    carga: list[tuple[int, int]]           # (i, j) entre clientes
    usa_carga: bool
    min_vehiculos: int

    @property
    def n_variables(self) -> int:
        n = len({j for _, j in self.arcos if j})
        return len(self.arcos) + n + (n if self.usa_carga else 0)

    @property
    def n_restricciones(self) -> int:
        n = len({j for _, j in self.arcos if j})
        return (2 * n + 1 + (self.min_vehiculos > 1) + len(self.tiempo) + len(self.regreso)
                + len(self.carga))


def _estructura(inst: Instancia) -> _Estructura:
    n, Q = inst.n_clientes, inst.capacidad
    a, b, s, d, q = inst.inicio, inst.fin, inst.servicio, inst.dist, inst.demanda
    usa_carga = int(q[1:].sum()) > Q
    arcos, tiempo, regreso, carga = [], [], [], []
    for i in range(n + 1):
        for j in range(n + 1):
            if i == j:
                continue
            if i and j and q[i] + q[j] > Q:
                continue  # dos clientes que no caben juntos en un camión
            if j:
                # Desde el depósito se sale en inicio[0]; desde un cliente, a lo más temprano
                # tras atender en inicio[i]. Si así ya no se llega antes del cierre, se poda.
                if a[i] + s[i] + d[i, j] > b[j]:
                    continue
                tope_i = a[0] if i == 0 else b[i]  # el depósito parte en inicio[0]
                M = max(0.0, tope_i + s[i] + d[i, j] - a[j])
                if M > 0:  # con M = 0 la restricción se cumple siempre: es redundante
                    tiempo.append((i, j, M))
                if i and usa_carga:
                    carga.append((i, j))
            else:
                if a[i] + s[i] + d[i, 0] > b[0]:
                    continue
                M = max(0.0, b[i] + s[i] + d[i, 0] - b[0])
                if M > 0:
                    regreso.append((i, M))
            arcos.append((i, j))
    min_veh = max(1, math.ceil(int(q[1:].sum()) / Q)) if n else 0
    return _Estructura(arcos, tiempo, regreso, carga, usa_carga, min_veh)


def tamano_modelo(inst: Instancia) -> tuple[int, int]:
    """(variables, restricciones) del modelo tras la poda, sin construirlo."""
    e = _estructura(inst)
    return e.n_variables, e.n_restricciones


def cabe_en_licencia(inst: Instancia) -> bool:
    nv, nr = tamano_modelo(inst)
    return ((LIMITE_VARIABLES is None or nv <= LIMITE_VARIABLES)
            and (LIMITE_RESTRICCIONES is None or nr <= LIMITE_RESTRICCIONES))


def _rutas_desde_arcos(sucesor: dict[int, list[int]]) -> list[list[int]]:
    rutas = []
    for primero in sucesor.get(0, []):
        ruta, actual, vistos = [], primero, set()
        while actual != 0 and actual not in vistos:
            vistos.add(actual)
            ruta.append(actual)
            siguientes = sucesor.get(actual, [])
            actual = siguientes[0] if siguientes else 0
        rutas.append(ruta)
    return rutas


def resolver_exacto(inst: Instancia, limite_seg: float = 60.0,
                    solucion_inicial: list[list[int]] | None = None,
                    verbose: bool = False) -> ResultadoExacto:
    """Resuelve el VRPTW de forma exacta (o hasta `limite_seg`) con Gurobi.

    `solucion_inicial` (rutas de clientes, sin depósito) se entrega como MIP start.
    Estados: "OPTIMAL", "TIME_LIMIT" (con incumbente), "SIN_SOLUCION" (se acabó el tiempo sin
    solución factible) o "INFEASIBLE".
    """
    e = _estructura(inst)
    nv, nr = e.n_variables, e.n_restricciones
    if ((LIMITE_VARIABLES is not None and nv > LIMITE_VARIABLES)
            or (LIMITE_RESTRICCIONES is not None and nr > LIMITE_RESTRICCIONES)):
        raise ValueError(
            f"El modelo de {inst.nombre} tendría {nv} variables y {nr} restricciones tras la "
            f"poda, y la licencia limitada de gurobipy admite {LIMITE_VARIABLES} variables y "
            f"{LIMITE_RESTRICCIONES} restricciones. Use menos clientes (Instancia.recortar) o "
            "una licencia académica de Gurobi para instancias más grandes.")

    n = inst.n_clientes
    a, b, s, d, q = inst.inicio, inst.fin, inst.servicio, inst.dist, inst.demanda
    if n == 0:
        return ResultadoExacto([], 0.0, 0.0, 0.0, "OPTIMAL", 0.0)
    # Las restricciones de tiempo eliminan los subtours solo si cada arco entre clientes toma
    # tiempo (servicio + viaje > 0); si no, deben hacerlo las de carga, con demanda positiva.
    for i, j in e.arcos:
        if i and j and s[i] + d[i, j] <= 0 and not (e.usa_carga and q[j] > 0):
            raise ValueError(
                f"El arco {i}→{j} de {inst.nombre} no toma tiempo (servicio + distancia = 0): "
                "con esta formulación podrían aparecer subtours.")
    t0 = time.perf_counter()
    with gp.Env(empty=True) as env:
        env.setParam("OutputFlag", 1 if verbose else 0)
        env.start()
        with gp.Model(f"vrptw-{inst.nombre}", env=env) as m:
            m.Params.TimeLimit = limite_seg
            x = m.addVars(e.arcos, vtype=GRB.BINARY, name="x",
                          obj=[float(d[i, j]) for i, j in e.arcos])
            clientes = range(1, n + 1)
            t = m.addVars(clientes, lb={i: float(a[i]) for i in clientes},
                          ub={i: float(b[i]) for i in clientes}, name="t")
            if e.usa_carga:
                carga = m.addVars(clientes, lb={i: float(q[i]) for i in clientes},
                                  ub=float(inst.capacidad), name="q")
            m.ModelSense = GRB.MINIMIZE

            m.addConstrs((x.sum("*", j) == 1 for j in clientes), name="entra")
            m.addConstrs((x.sum(i, "*") == 1 for i in clientes), name="sale")
            m.addConstr(x.sum(0, "*") <= inst.vehiculos, name="flota")
            if e.min_vehiculos > 1:
                m.addConstr(x.sum(0, "*") >= e.min_vehiculos, name="flota_min")
            for i, j, M in e.tiempo:
                ti = float(a[0]) if i == 0 else t[i]
                m.addConstr(t[j] >= ti + float(s[i] + d[i, j]) - M * (1 - x[i, j]),
                            name=f"tiempo[{i},{j}]")
            for i, M in e.regreso:
                m.addConstr(t[i] + float(s[i] + d[i, 0]) <= float(b[0]) + M * (1 - x[i, 0]),
                            name=f"regreso[{i}]")
            for i, j in e.carga:
                m.addConstr(carga[j] >= carga[i] + float(q[j])
                            - inst.capacidad * (1 - x[i, j]), name=f"carga[{i},{j}]")

            if solucion_inicial is not None:
                usados = {(u, v) for r in solucion_inicial if r
                          for u, v in zip([0, *r], [*r, 0])}
                for arco, var in x.items():
                    var.Start = 1.0 if arco in usados else 0.0

            m.optimize()
            segundos = time.perf_counter() - t0

            if m.Status in (GRB.INFEASIBLE, GRB.INF_OR_UNBD):
                return ResultadoExacto([], None, None, None, "INFEASIBLE", segundos)
            if m.SolCount == 0:
                cota = m.ObjBound if m.Status == GRB.TIME_LIMIT else None
                return ResultadoExacto([], None, cota, None, "SIN_SOLUCION", segundos)

            sucesor: dict[int, list[int]] = {}
            for (i, j), var in x.items():
                if var.X > 0.5:
                    sucesor.setdefault(i, []).append(j)
            rutas = _rutas_desde_arcos(sucesor)
            ev = evaluar(inst, rutas)
            if not ev.factible:  # red de seguridad: no debería ocurrir con la poda y el big-M
                raise RuntimeError(f"Gurobi entregó rutas no factibles para {inst.nombre}: "
                                   + "; ".join(ev.violaciones[:3]))
            estado = {GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT"}.get(
                m.Status, f"GUROBI_{m.Status}")
            return ResultadoExacto(rutas, sum(distancia_ruta(inst, r) for r in rutas),
                                   float(m.ObjBound), float(m.MIPGap), estado, segundos)
