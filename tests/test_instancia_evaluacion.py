"""El evaluador se valida con las mejores soluciones publicadas: deben ser factibles y su
distancia debe coincidir con el costo publicado."""
import pytest

from ruteo.evaluacion import evaluar, horario
from ruteo.instancia import cargar, mejor_conocida, nombres


def test_hay_56_instancias():
    assert len(nombres()) == 56


@pytest.mark.parametrize("nombre", nombres())
def test_mejor_conocida_es_factible_y_su_costo_coincide(nombre):
    inst = cargar(nombre)
    rutas, costo = mejor_conocida(nombre)
    ev = evaluar(inst, rutas)
    assert ev.factible, ev.violaciones
    assert ev.distancia == pytest.approx(costo, abs=0.1)


def test_detecta_violaciones():
    inst = cargar("C101")
    rutas, _ = mejor_conocida("C101")
    sin_cliente = [r[:] for r in rutas]
    sin_cliente[0] = sin_cliente[0][1:]
    assert not evaluar(inst, sin_cliente).factible
    todo_en_una = [[c for r in rutas for c in r]]
    ev = evaluar(inst, todo_en_una)
    assert not ev.factible and any("capacidad" in v for v in ev.violaciones)


def test_horario_respeta_espera():
    inst = cargar("R101")
    filas = horario(inst, mejor_conocida("R101")[0][0])
    assert all(f["inicio"] >= f["llegada"] - 1e-9 for f in filas)
