"""Tests del caso Santiago: instancia válida y reproducible, clientes factibles, heurísticas
factibles, horario con salida tardía, mapa de fondo y la vista de la app."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from ruteo import heuristicas as h
from ruteo import santiago
from ruteo.evaluacion import TOL, evaluar, horario

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))


@pytest.fixture(scope="module")
def caso40():
    return santiago.crear_caso(40, 2026)


@pytest.mark.parametrize("n", [15, 40, 60])
def test_forma_y_valores_de_la_instancia(n):
    caso = santiago.crear_caso(n, 2026)
    inst = caso.inst
    assert inst.n_clientes == n
    assert caso.latlon.shape == (n + 1, 2) and inst.coords.shape == (n + 1, 2)
    assert inst.dist.shape == (n + 1, n + 1)
    for arr in (inst.demanda, inst.inicio, inst.fin, inst.servicio):
        assert arr.shape == (n + 1,)
    assert len(caso.comunas) == len(caso.tipo_ventana) == n + 1
    assert set(caso.comunas[1:]) <= set(santiago.COMUNAS)
    assert tuple(caso.latlon[0]) == santiago.DEPOSITO
    # Todos los puntos caen dentro de Santiago.
    assert caso.latlon[:, 0].min() > -33.70 and caso.latlon[:, 0].max() < -33.30
    assert caso.latlon[:, 1].min() > -70.85 and caso.latlon[:, 1].max() < -70.45
    assert np.array_equal(inst.dist, inst.dist.T) and not np.diag(inst.dist).any()
    assert np.array_equal(inst.dist, np.floor(inst.dist * 10 + 1e-6) / 10)  # un decimal
    assert (inst.capacidad, inst.vehiculos) == (40, 15)
    assert inst.demanda[0] == 0 and inst.demanda[1:].min() >= 1 and inst.demanda[1:].max() <= 6
    assert inst.servicio[0] == 0 and np.all(inst.servicio[1:] == 8)
    assert (inst.inicio[0], inst.fin[0]) == (0, 600)
    for c in range(1, n + 1):
        assert inst.fin[c] <= 600 - 8 - inst.dist[c, 0]  # alcanza a volver antes de las 18:00
        tipo = caso.tipo_ventana[c]
        if tipo == "Mañana":
            assert inst.inicio[c] == 60 and inst.fin[c] <= 300
        elif tipo == "Tarde":
            assert inst.inicio[c] == 360 and inst.fin[c] > 360
        else:
            assert tipo == "Todo el día" and inst.inicio[c] == 60


def test_clientes_repartidos_en_muchas_comunas_y_ventanas():
    caso = santiago.crear_caso(60, 2026)
    assert len(set(caso.comunas[1:])) >= 15
    assert set(caso.tipo_ventana[1:]) == {"Mañana", "Tarde", "Todo el día"}


def test_tiempo_de_viaje_en_minutos():
    # 10 km en línea recta hacia el norte: 10 × 1,35 / 28 km/h = 28,93 minutos → 28,9.
    norte = santiago.DEPOSITO[0] + math.degrees(10 / santiago.RADIO_TIERRA_KM)
    m = santiago.minutos_de_viaje(np.array([santiago.DEPOSITO, (norte, santiago.DEPOSITO[1])]))
    assert m[0, 1] == m[1, 0] == pytest.approx(28.9)
    assert santiago.km(60) == pytest.approx(28.0)
    assert santiago.crear_caso(15).km(30) == pytest.approx(14.0)


def test_hora_del_dia():
    assert santiago.hora(0) == "08:00"
    assert santiago.hora(125.9) == "10:05"
    assert santiago.hora(600) == "18:00"


def test_reproducible_por_semilla():
    a, b = santiago.crear_caso(30, 7), santiago.crear_caso(30, 7)
    for x, y in zip((a.latlon, a.inst.dist, a.inst.demanda, a.inst.inicio, a.inst.fin),
                    (b.latlon, b.inst.dist, b.inst.demanda, b.inst.inicio, b.inst.fin)):
        assert np.array_equal(x, y)
    assert a.comunas == b.comunas and a.tipo_ventana == b.tipo_ventana
    assert not np.array_equal(a.latlon, santiago.crear_caso(30, 8).latlon)
    inst, latlon = santiago.crear_caso(30, 7)  # también se desempaca como (instancia, lat-lon)
    assert np.array_equal(latlon, a.latlon) and np.array_equal(inst.dist, a.inst.dist)


@pytest.mark.parametrize("semilla", [0, 1, 7, 2026])
def test_cada_cliente_se_puede_atender_solo(semilla):
    inst = santiago.crear_caso(60, semilla).inst
    ev = evaluar(inst, [[c] for c in range(1, inst.n_clientes + 1)])
    assert ev.factible, ev.violaciones


def test_heuristicas_entregan_planes_factibles(caso40):
    inst = caso40.inst
    rutas = h.insercion(inst)
    ev_ins = evaluar(inst, rutas)
    assert ev_ins.factible, ev_ins.violaciones
    mejor, _ = h.alns(inst, segundos=60, semilla=1, max_iter=50)
    ev = evaluar(inst, mejor)
    assert ev.factible, ev.violaciones
    assert ev.distancia <= ev_ins.distancia + 1e-6


def test_salida_tardia_no_cambia_el_regreso_ni_rompe_ventanas(caso40):
    inst = caso40.inst
    for r in h.insercion(inst):
        base = horario(inst, r)
        salida, filas = santiago.salida_y_horario(inst, r)
        assert salida >= 0 and salida == int(salida)
        assert [f["cliente"] for f in filas] == [*r, 0]
        assert filas[-1]["llegada"] == pytest.approx(base[-1]["llegada"])
        assert filas[0]["llegada"] == pytest.approx(salida + inst.dist[0, r[0]])
        for f in filas:
            assert inst.inicio[f["cliente"]] - TOL <= f["inicio"] <= inst.fin[f["cliente"]] + TOL
        assert sum(f["espera"] for f in filas) <= sum(f["espera"] for f in base) + 1e-6


def test_animacion_en_el_mapa(caso40):
    import mapa

    inst = caso40.inst
    rutas = h.insercion(inst)
    horarios = [santiago.salida_y_horario(inst, r) for r in rutas]
    fig = mapa.figura_animada_calles(inst, caso40.latlon, rutas, horarios,
                                     ["Centro"] + ["Cliente"] * inst.n_clientes, santiago.hora)
    assert len(fig.frames) >= 100
    vehiculos = [d for d in fig.data if d.meta == "vehiculo"]
    assert len(vehiculos) == len(rutas)
    assert fig.layout.sliders[0].steps[0].label == "08:00"
    # Antes de la primera salida, todas las camionetas siguen en el centro de distribución.
    deposito = mapa.mercator_km(caso40.latlon[:1])[0]
    t_max = max(f[-1]["llegada"] for _, f in horarios)
    k = int(min(s for s, _ in horarios) / t_max * (len(fig.frames) - 1))
    camiones = [d for d in fig.frames[k].data if d.x is not None and len(d.x) == 1]
    assert len(camiones) == len(rutas)
    assert all([d.x[0], d.y[0]] == pytest.approx(deposito, abs=0.01) for d in camiones)
    # La tesela de OpenStreetMap que contiene al depósito (fórmula estándar) está en el fondo y
    # cubre su posición.
    lat, lon = santiago.DEPOSITO
    z = int(fig.layout.images[0].source.split("/")[-3])
    tx = int((lon + 180) / 360 * 2 ** z)
    ty = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** z)
    (img,) = [i for i in fig.layout.images if i.source.endswith(f"/{z}/{tx}/{ty}.png")]
    assert img.x <= deposito[0] <= img.x + img.sizex
    assert img.y - img.sizey <= deposito[1] <= img.y


def test_mapa_de_calles_usa_openstreetmap(caso40):
    import mapa

    textos = ["Centro"] + ["Cliente"] * caso40.inst.n_clientes
    fig = mapa.fig_mapa_calles(caso40.latlon, h.insercion(caso40.inst), textos, "Plan")
    capa = fig.layout.map if mapa._MAPLIBRE else fig.layout.mapbox
    assert capa.style == "open-street-map"
    assert {d.type for d in fig.data} == {"scattermap" if mapa._MAPLIBRE else "scattermapbox"}
    sin_ruta = mapa.fig_mapa_calles(caso40.latlon, [], textos, "Clientes")
    assert any(d.name == "Clientes" and len(d.lat) == 40 for d in sin_ruta.data)


def test_vista_caso_santiago(monkeypatch, tmp_path):
    monkeypatch.setenv("RUTEO_RESULTADOS", str(tmp_path))
    at = AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=60).run()
    at.radio(key="vista").set_value("Caso Santiago").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Planificar el día" in i.value for i in at.info)
    at.slider(key="stgo_n").set_value(15)
    at.radio(key="stgo_metodo").set_value("Inserción")
    at.button(key="stgo_boton").click().run()
    assert not at.exception, [e.value for e in at.exception]
    (plan,) = at.session_state["santiago"].values()
    assert sorted(c for r in plan["rutas"] for c in r) == list(range(1, 16))
    assert len(plan["animacion"].frames) >= 100
    assert [m.label for m in at.metric] == ["Camionetas", "Minutos de manejo", "Km aprox.",
                                            "Regreso de la última"]
    assert len(at.dataframe[0].value) == len(plan["rutas"])
    assert not at.warning
    # En la siguiente ejecución (cualquier interacción) el plan y su animación siguen ahí.
    animacion = plan["animacion"]
    at.run()
    assert not at.exception and len(at.dataframe) == 1
    (plan,) = at.session_state["santiago"].values()
    assert plan["animacion"] is animacion  # no se vuelve a armar
