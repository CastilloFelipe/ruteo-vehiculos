"""El solver exacto debe probar optimalidad en instancias recortadas, entregar rutas factibles
según el evaluador y reportar la misma distancia que este calcula."""
import pytest

from ruteo.evaluacion import evaluar
from ruteo.exacto import resolver_exacto
from ruteo.instancia import cargar

CASOS = [("C101", 10), ("R101", 12), ("RC101", 10)]


@pytest.fixture(scope="module")
def resultados():
    return {(nombre, n): resolver_exacto(cargar(nombre).recortar(n), limite_seg=20)
            for nombre, n in CASOS}


@pytest.mark.parametrize("nombre,n", CASOS)
def test_optimo_es_factible_y_su_distancia_coincide(resultados, nombre, n):
    inst = cargar(nombre).recortar(n)
    res = resultados[(nombre, n)]
    assert res.estado == "OPTIMAL"
    ev = evaluar(inst, res.rutas)
    assert ev.factible, ev.violaciones
    assert ev.distancia == pytest.approx(res.distancia, abs=1e-6)
    assert res.gap == pytest.approx(0, abs=1e-4)
    assert res.cota <= res.distancia + 1e-6


@pytest.mark.parametrize("nombre,n", CASOS)
def test_solucion_inicial_factible_da_el_mismo_optimo(resultados, nombre, n):
    inst = cargar(nombre).recortar(n)
    # Una ruta por cliente es factible en estas instancias (cada cliente es alcanzable).
    inicial = [[c] for c in range(1, n + 1)]
    assert evaluar(inst, inicial).factible
    res = resolver_exacto(inst, limite_seg=20, solucion_inicial=inicial)
    assert res.estado == "OPTIMAL"
    assert res.distancia == pytest.approx(resultados[(nombre, n)].distancia, abs=1e-6)


def test_instancia_completa_excede_la_licencia():
    with pytest.raises(ValueError, match="licencia académica"):
        resolver_exacto(cargar("C101"))


# ------------------------------------------------------------------ verificación independiente

def _ruta_factible(inst, ruta) -> bool:
    """Simulación propia (sin usar el código bajo prueba) de capacidad y ventanas."""
    if sum(inst.demanda[c] for c in ruta) > inst.capacidad:
        return False
    t, prev = float(inst.inicio[0]), 0
    for c in ruta:
        t = max(t + inst.servicio[prev] + inst.dist[prev, c], float(inst.inicio[c]))
        if t > inst.fin[c] + 1e-6:
            return False
        prev = c
    return t + inst.servicio[prev] + inst.dist[prev, 0] <= inst.fin[0] + 1e-6


def _optimo_fuerza_bruta(inst) -> float:
    """Mejor orden factible de cada subconjunto (todas las permutaciones) y luego la mejor
    partición en rutas, por programación dinámica sobre subconjuntos."""
    from itertools import permutations

    n = inst.n_clientes
    ruta_min = {}
    for mascara in range(1, 1 << n):
        clientes = [c + 1 for c in range(n) if mascara >> c & 1]
        mejor = float("inf")
        for orden in permutations(clientes):
            if _ruta_factible(inst, orden):
                camino = [0, *orden, 0]
                mejor = min(mejor, sum(inst.dist[u, v] for u, v in zip(camino, camino[1:])))
        ruta_min[mascara] = mejor
    f = [0.0] + [float("inf")] * ((1 << n) - 1)
    for mascara in range(1, 1 << n):
        bajo = mascara & -mascara  # la ruta que contiene al cliente de menor índice
        sub = mascara
        while sub:
            if sub & bajo:
                f[mascara] = min(f[mascara], ruta_min[sub] + f[mascara ^ sub])
            sub = (sub - 1) & mascara
    return f[-1]


@pytest.mark.parametrize("nombre", ["C101", "R101", "RC101", "R201"])
def test_optimo_de_gurobi_coincide_con_fuerza_bruta(nombre):
    inst = cargar(nombre).recortar(7)
    res = resolver_exacto(inst, limite_seg=20)
    assert res.estado == "OPTIMAL"
    assert res.distancia == pytest.approx(_optimo_fuerza_bruta(inst), abs=1e-6)


def test_sin_tiempo_entre_clientes_se_rechaza():
    import numpy as np

    from dataclasses import replace

    base = cargar("C101").recortar(3)
    dist = base.dist.copy()
    dist[1, 2] = dist[2, 1] = 0.0  # dos clientes en el mismo punto, sin tiempo de servicio
    inst = replace(base, servicio=np.zeros_like(base.servicio), dist=dist)
    with pytest.raises(ValueError):
        resolver_exacto(inst, limite_seg=5)
