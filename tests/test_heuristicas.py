"""Las heurísticas deben entregar soluciones factibles que cubren a todos los clientes, la
búsqueda local nunca empeora, el ALNS no es peor que su punto de partida y es reproducible."""
import pytest

from ruteo.evaluacion import evaluar
from ruteo.heuristicas import alns, busqueda_local, insercion
from ruteo.instancia import cargar

NOMBRES = ["C101", "R101", "RC101", "C201"]


def _instancia(nombre):
    if nombre == "R101-25":
        return cargar("R101").recortar(25)
    return cargar(nombre)


def _cubre_a_todos(inst, rutas):
    return sorted(c for r in rutas for c in r) == list(range(1, inst.n_clientes + 1))


@pytest.fixture(scope="module", params=NOMBRES + ["R101-25"])
def caso(request):
    inst = _instancia(request.param)
    ins = insercion(inst)
    bl = busqueda_local(inst, ins)
    return inst, ins, bl


def test_insercion_es_factible_y_cubre_a_todos(caso):
    inst, ins, _ = caso
    ev = evaluar(inst, ins)
    assert ev.factible, ev.violaciones
    assert _cubre_a_todos(inst, ins)


def test_busqueda_local_es_factible_y_no_empeora(caso):
    inst, ins, bl = caso
    ev = evaluar(inst, bl)
    assert ev.factible, ev.violaciones
    assert _cubre_a_todos(inst, bl)
    assert all(bl), "no debe dejar rutas vacías"
    assert ev.distancia <= evaluar(inst, ins).distancia + 1e-6


def test_busqueda_local_es_un_optimo_local(caso):
    inst, _, bl = caso
    assert evaluar(inst, busqueda_local(inst, bl)).distancia == pytest.approx(
        evaluar(inst, bl).distancia)


@pytest.mark.parametrize("nombre", NOMBRES + ["R101-25"])
def test_alns_factible_no_peor_y_historial_monotono(nombre):
    inst = _instancia(nombre)
    rutas, historial = alns(inst, segundos=2, semilla=1)
    ev = evaluar(inst, rutas)
    assert ev.factible, ev.violaciones
    assert _cubre_a_todos(inst, rutas)
    base = evaluar(inst, busqueda_local(inst, insercion(inst))).distancia
    assert ev.distancia <= base + 1e-6
    tiempos = [t for t, _ in historial]
    distancias = [f for _, f in historial]
    assert tiempos[0] < 1.0
    assert tiempos == sorted(tiempos)
    assert all(b < a for a, b in zip(distancias, distancias[1:]))
    assert distancias[-1] == pytest.approx(ev.distancia)


def test_alns_parte_de_rutas_iniciales():
    inst = cargar("C101")
    base = busqueda_local(inst, insercion(inst))
    rutas, historial = alns(inst, segundos=60, rutas_iniciales=base, max_iter=50)
    assert evaluar(inst, rutas).factible
    assert historial[0][1] == pytest.approx(evaluar(inst, base).distancia)


def test_alns_es_reproducible_con_la_misma_semilla():
    inst = cargar("RC101")
    a = alns(inst, segundos=60, semilla=7, max_iter=300)[0]
    b = alns(inst, segundos=60, semilla=7, max_iter=300)[0]
    assert a == b
