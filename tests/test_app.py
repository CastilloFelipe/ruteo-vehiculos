"""Tests de la app de Streamlit: cada vista se dibuja sin excepciones con y sin resultados."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ruteo.instancia import cargar, nombres

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
VISTAS = ["Inicio", "Resolver una instancia", "Caso Santiago", "Benchmark", "Exacto vs heurística"]


def _csv_sinteticos(carpeta: Path) -> None:
    rng = np.random.default_rng(0)
    filas = []
    for n in nombres():
        bks = 1000 + 100 * rng.random()
        g = np.sort(rng.random(3) * 0.2)[::-1]
        filas.append({"instancia": n, "familia": n[:-2], "bks_distancia": bks, "bks_rutas": 10,
                      "insercion_distancia": bks * (1 + g[0]), "insercion_rutas": 12,
                      "local_distancia": bks * (1 + g[1]), "local_rutas": 11,
                      "alns_distancia": bks * (1 + g[2]), "alns_rutas": 10,
                      "gap_insercion": g[0], "gap_local": g[1], "gap_alns": g[2],
                      "local_segundos": 0.5, "alns_segundos": 10.0})
    pd.DataFrame(filas).to_csv(carpeta / "benchmark.csv", index=False)
    pd.DataFrame([
        {"instancia": "C101-25", "n_clientes": 25, "estado": "OPTIMAL", "optimo": 191.3,
         "cota": 191.3, "gap_gurobi": 0.0, "segundos_gurobi": 1.2, "alns_distancia": 191.3,
         "gap_alns_vs_optimo": 0.0},
        {"instancia": "R101-25", "n_clientes": 25, "estado": "OPTIMAL", "optimo": 617.1,
         "cota": 617.1, "gap_gurobi": 0.0, "segundos_gurobi": 3.4, "alns_distancia": 620.0,
         "gap_alns_vs_optimo": 620.0 / 617.1 - 1},
        {"instancia": "R201-50", "n_clientes": 50, "estado": "TIME_LIMIT", "optimo": 800.0,
         "cota": 760.0, "gap_gurobi": 0.05, "segundos_gurobi": 120.0, "alns_distancia": 801.0,
         "gap_alns_vs_optimo": 801.0 / 800.0 - 1},
        {"instancia": "RC201-50", "n_clientes": 50, "estado": "NO_CABE",
         "detalle": "El modelo no cabe en la licencia", "alns_distancia": 900.0},
    ]).to_csv(carpeta / "exacto.csv", index=False)


def _app(monkeypatch, carpeta: Path) -> AppTest:
    monkeypatch.setenv("RUTEO_RESULTADOS", str(carpeta))
    at = AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=60)
    return at.run()


@pytest.mark.parametrize("con_resultados", [False, True], ids=["sin_csv", "con_csv"])
def test_cada_vista_se_dibuja(monkeypatch, tmp_path, con_resultados):
    if con_resultados:
        _csv_sinteticos(tmp_path)
    at = _app(monkeypatch, tmp_path)
    for vista in VISTAS:
        at.radio(key="vista").set_value(vista).run()
        assert not at.exception, (vista, [e.value for e in at.exception])
        avisos = " ".join(i.value for i in at.info)
        if con_resultados and vista in ("Benchmark", "Inicio"):
            assert "Todavía no hay resultados del benchmark" not in avisos
        if not con_resultados and vista in ("Benchmark", "Inicio"):
            assert "Todavía no hay resultados del benchmark" in avisos


def test_resolver_insercion_en_instancia_recortada(monkeypatch, tmp_path):
    at = _app(monkeypatch, tmp_path)
    at.radio(key="vista").set_value("Resolver una instancia").run()
    at.selectbox(key="res_inst").set_value("C101")
    at.toggle(key="res_recortar").set_value(True).run()
    at.slider(key="res_n").set_value(15)
    at.radio(key="res_metodo").set_value("Inserción")
    at.button(key="res_boton").click().run()
    assert not at.exception, [e.value for e in at.exception]
    (sol,) = at.session_state["soluciones"].values()
    assert sorted(c for r in sol["rutas"] for c in r) == list(range(1, 16))
    assert len(at.dataframe) >= 2  # tabla de rutas y horario de la ruta elegida
    assert not any("violaciones" in w.value for w in at.warning)


def test_animacion_tiene_frames_y_un_vehiculo_por_ruta():
    from animacion import figura_animada
    from ruteo.heuristicas import insercion

    inst = cargar("C101").recortar(15)
    rutas = insercion(inst)
    fig = figura_animada(inst, rutas)
    assert len(fig.frames) >= 100
    vehiculos = [d for d in fig.data if d.meta == "vehiculo"]
    assert len(vehiculos) == len([r for r in rutas if r])
    # En t = 0 todos están en el depósito; al final, todos de vuelta en el depósito.
    deposito = list(inst.coords[0])
    ultimo = fig.frames[-1].data
    for d in vehiculos:
        assert [d.x[0], d.y[0]] == pytest.approx(deposito)
    finales = [f for f in ultimo if f.x is not None and len(f.x) == 1]
    assert all([f.x[0], f.y[0]] == pytest.approx(deposito, abs=0.01) for f in finales)
