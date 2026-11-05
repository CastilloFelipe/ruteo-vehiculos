"""Corre el benchmark completo y guarda los resultados en resultados/.

    python scripts/benchmark.py --segundos 10 --procesos 4

1. Las 56 instancias de Solomon (100 clientes): inserción, búsqueda local y ALNS, comparados
   con la mejor solución conocida -> resultados/benchmark.csv
2. Versiones recortadas a 25 y 50 clientes de una instancia por familia: óptimo exacto con
   Gurobi vs ALNS -> resultados/exacto.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from ruteo.evaluacion import evaluar  # noqa: E402
from ruteo.instancia import cargar, mejor_conocida, nombres  # noqa: E402

SALIDA = RAIZ / "resultados"
FAMILIAS_EXACTO = ["C101", "C201", "R101", "R201", "RC101", "RC201"]


def familia(nombre: str) -> str:
    return nombre[:-2]


def _una(args: tuple[str, float, int]) -> dict:
    from ruteo.heuristicas import alns, busqueda_local, insercion

    nombre, segundos, semilla = args
    inst = cargar(nombre)
    _, bks = mejor_conocida(nombre)
    bks_rutas = len(mejor_conocida(nombre)[0])
    fila = {"instancia": nombre, "familia": familia(nombre), "bks_distancia": bks,
            "bks_rutas": bks_rutas}
    t0 = time.perf_counter()
    r_ins = insercion(inst)
    r_loc = busqueda_local(inst, r_ins)
    t_loc = time.perf_counter() - t0
    r_alns, _ = alns(inst, segundos=segundos, semilla=semilla, rutas_iniciales=r_loc)
    for etiqueta, rutas in (("insercion", r_ins), ("local", r_loc), ("alns", r_alns)):
        ev = evaluar(inst, rutas)
        if not ev.factible:
            raise RuntimeError(f"{nombre} {etiqueta}: solución infactible {ev.violaciones}")
        fila[f"{etiqueta}_distancia"] = ev.distancia
        fila[f"{etiqueta}_rutas"] = ev.n_rutas
        fila[f"gap_{etiqueta}"] = ev.distancia / bks - 1
    fila["local_segundos"] = t_loc
    fila["alns_segundos"] = segundos
    print(f"  {nombre}: inserción {fila['gap_insercion']:+.1%} · local {fila['gap_local']:+.1%} "
          f"· ALNS {fila['gap_alns']:+.1%}", flush=True)
    return fila


def benchmark(segundos: float, procesos: int, semilla: int) -> pd.DataFrame:
    with ProcessPoolExecutor(procesos) as ex:
        filas = list(ex.map(_una, [(n, segundos, semilla) for n in nombres()]))
    return pd.DataFrame(filas)


def exacto(n: int, limite: float, segundos_alns: float, semilla: int) -> pd.DataFrame:
    from ruteo.exacto import resolver_exacto
    from ruteo.heuristicas import alns

    filas = []
    for nombre in FAMILIAS_EXACTO:
        inst = cargar(nombre).recortar(n)
        r_alns, _ = alns(inst, segundos=segundos_alns, semilla=semilla)
        d_alns = evaluar(inst, r_alns).distancia
        try:
            res = resolver_exacto(inst, limite_seg=limite, solucion_inicial=r_alns)
        except ValueError as e:
            filas.append({"instancia": inst.nombre, "n_clientes": n, "estado": "NO_CABE",
                          "detalle": str(e), "alns_distancia": d_alns})
            continue
        filas.append({"instancia": inst.nombre, "n_clientes": n, "estado": res.estado,
                      "optimo": res.distancia, "cota": res.cota, "gap_gurobi": res.gap,
                      "segundos_gurobi": res.segundos, "alns_distancia": d_alns,
                      "gap_alns_vs_optimo": (d_alns / res.distancia - 1) if res.distancia else None})
        print(f"  {inst.nombre}: Gurobi {res.estado} {res.distancia} · ALNS {d_alns:.1f}", flush=True)
    return pd.DataFrame(filas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segundos", type=float, default=10.0, help="Tiempo de ALNS por instancia")
    ap.add_argument("--procesos", type=int, default=4)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--n-exacto", type=int, nargs="+", default=[25, 50])
    ap.add_argument("--limite-gurobi", type=float, default=120.0)
    ap.add_argument("--solo", choices=["benchmark", "exacto"])
    ap.add_argument("--archivo", default="benchmark.csv",
                    help="Nombre del CSV del benchmark dentro de resultados/")
    a = ap.parse_args()
    SALIDA.mkdir(exist_ok=True)
    if a.solo in (None, "benchmark"):
        print("Benchmark Solomon (56 instancias)...")
        b = benchmark(a.segundos, a.procesos, a.semilla)
        b.to_csv(SALIDA / a.archivo, index=False)
        print(b.groupby("familia")[["gap_insercion", "gap_local", "gap_alns"]].mean().round(4))
    if a.solo in (None, "exacto"):
        print(f"Exacto con Gurobi ({a.n_exacto} clientes)...")
        e = pd.concat([exacto(n, a.limite_gurobi, min(a.segundos, 5.0), a.semilla)
                       for n in a.n_exacto], ignore_index=True)
        e.to_csv(SALIDA / "exacto.csv", index=False)
    print(f"Resultados en {SALIDA}")


if __name__ == "__main__":
    main()
