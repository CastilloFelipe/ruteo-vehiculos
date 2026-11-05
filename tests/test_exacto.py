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
