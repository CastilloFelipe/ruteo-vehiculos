"""App de Streamlit del proyecto de ruteo de vehículos con ventanas horarias (VRPTW).

    streamlit run app/streamlit_app.py

Los resultados del benchmark se leen de resultados/ (o de la carpeta en la variable de entorno
RUTEO_RESULTADOS). Ningún resultado está escrito a mano: todo se calcula desde esos CSV o se
resuelve en vivo.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
for _p in (RAIZ / "src", Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import textos  # noqa: E402
from animacion import VEHICULO, figura_animada  # noqa: E402
from mapa import fig_mapa_calles, figura_animada_calles  # noqa: E402
from ruteo import santiago  # noqa: E402
from ruteo.evaluacion import distancia_ruta, evaluar, horario  # noqa: E402
from ruteo.instancia import cargar, mejor_conocida, nombres  # noqa: E402

PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TINTA = "#1f2430"
FAMILIAS = ["C1", "C2", "R1", "R2", "RC1", "RC2"]
METODOS = {"insercion": "Inserción", "local": "Inserción + búsqueda local", "alns": "ALNS"}
VISTAS = ["Inicio", "Resolver una instancia", "Caso Santiago", "Benchmark", "Exacto vs heurística"]
ESTADOS = {"OPTIMAL": "Óptimo demostrado", "TIME_LIMIT": "Límite de tiempo",
           "NO_CABE": "No cabe en la licencia", "SIN_SOLUCION": "Sin solución en el tiempo",
           "INFEASIBLE": "Infactible"}
COLS_BENCHMARK = ["instancia", "familia", "bks_distancia", "bks_rutas",
                  *[f"{m}_{c}" for m in METODOS for c in ("distancia", "rutas")],
                  *[f"gap_{m}" for m in METODOS], "local_segundos", "alns_segundos"]
COLS_EXACTO = ["instancia", "n_clientes", "estado", "alns_distancia"]


# ---------------------------------------------------------------------------- formato

def num(x, d: int = 1) -> str:
    """Número con formato chileno: punto de miles y coma decimal."""
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(x, d: int = 1) -> str:
    return "—" if x is None or pd.isna(x) else f"{num(100 * x, d)} %"


def mostrar_tabla(df: pd.DataFrame, porcentajes=()) -> None:
    """st.dataframe con coma decimal. Se formatea solo el texto; ordenar sigue usando los números."""
    formatos = {c: (lambda x: "—" if pd.isna(x) else f"{num(x, 2)} %") for c in porcentajes}
    for c in df.columns:
        if c not in formatos and pd.api.types.is_float_dtype(df[c]):
            d = 2 if "Segundos" in c else 1
            formatos[c] = lambda x, d=d: "—" if pd.isna(x) else num(x, d)
    st.dataframe(df.style.format(formatos), hide_index=True, width="stretch")


def como_leer(texto: str) -> None:
    with st.expander("¿Cómo leer esta vista?"):
        st.markdown(texto)


# ---------------------------------------------------------------------------- datos

def dir_resultados() -> Path:
    return Path(os.environ.get("RUTEO_RESULTADOS", RAIZ / "resultados"))


@st.cache_data(show_spinner=False)
def _leer_csv(ruta: str, _mtime: float, mtime: float) -> pd.DataFrame:
    return pd.read_csv(ruta)


def leer_resultados(archivo: str, requeridas: list[str]) -> pd.DataFrame | None:
    """CSV de resultados, o None si no existe, está vacío o le faltan columnas."""
    ruta = dir_resultados() / archivo
    if not ruta.is_file():
        return None
    try:
        mtime = ruta.stat().st_mtime
        df = _leer_csv(str(ruta), mtime, mtime)
    except Exception as e:  # noqa: BLE001
        st.warning(f"No se pudo leer `{archivo}`: {e}")
        return None
    faltan = [c for c in requeridas if c not in df.columns]
    if faltan:
        st.warning(f"A `{archivo}` le faltan columnas: {', '.join(faltan)}.")
        return None
    return df if len(df) else None


@st.cache_resource(show_spinner=False)
def instancia(nombre: str, n: int | None = None):
    inst = cargar(nombre)
    return inst.recortar(n) if n is not None and n < inst.n_clientes else inst


@st.cache_data(show_spinner=False)
def record(nombre: str) -> tuple[list[list[int]], float]:
    return mejor_conocida(nombre)


def familia(nombre: str) -> str:
    return nombre.rstrip("0123456789")


# ---------------------------------------------------------------------------- solvers

def resolver_heuristica(inst, metodo: str, segundos: float, semilla: int) -> dict:
    from ruteo import heuristicas as h

    t0 = time.perf_counter()
    historial: list[tuple[float, float]] = []
    if metodo == "insercion":
        rutas = h.insercion(inst)
    elif metodo == "local":
        rutas = h.busqueda_local(inst, h.insercion(inst))
    else:
        rutas, historial = h.alns(inst, segundos=segundos, semilla=semilla)
    return {"rutas": [list(map(int, r)) for r in rutas if len(r)],
            "historial": [(float(t), float(d)) for t, d in historial],
            "segundos": time.perf_counter() - t0}


# ---------------------------------------------------------------------------- gráficos

def _base(fig: go.Figure, alto: int, **kw) -> go.Figure:
    fig.update_layout(height=alto, margin=dict(l=10, r=10, t=50, b=10), separators=",.",
                      plot_bgcolor="white", paper_bgcolor="white", font=dict(color=TINTA),
                      hoverlabel=dict(bgcolor="white"), **kw)
    fig.update_xaxes(gridcolor="#eceef2", zeroline=False, linecolor="#c9ced6")
    fig.update_yaxes(gridcolor="#eceef2", zeroline=False, linecolor="#c9ced6")
    return fig


def fig_mapa(inst, rutas: list[list[int]], titulo: str) -> go.Figure:
    fig = go.Figure()
    xy = inst.coords
    for k, r in enumerate(rutas):
        nodos = [0, *r, 0]
        etiquetas = ["Depósito" if c == 0 else f"Cliente {c}" for c in nodos]
        fig.add_trace(go.Scatter(
            x=xy[nodos, 0], y=xy[nodos, 1], mode="lines+markers", name=f"Ruta {k + 1}",
            line=dict(color=PALETA[k % len(PALETA)], width=2),
            marker=dict(size=8, line=dict(color="white", width=1)), text=etiquetas,
            hovertemplate=f"%{{text}}<extra>Ruta {k + 1}</extra>"))
    fig.add_trace(go.Scatter(
        x=[xy[0, 0]], y=[xy[0, 1]], mode="markers", name="Depósito",
        marker=dict(symbol="square", size=15, color=TINTA, line=dict(color="white", width=2)),
        hovertemplate="Depósito<extra></extra>"))
    _base(fig, 470, title=dict(text=titulo, x=0), showlegend=True,
          legend=dict(font=dict(size=11)))
    fig.update_xaxes(title="x", constrain="domain")
    fig.update_yaxes(title="y", scaleanchor="x", scaleratio=1)
    return fig


def fig_convergencia(historial, segundos: float, bks: float | None) -> go.Figure:
    t = [p[0] for p in historial]
    d = [p[1] for p in historial]
    if t and segundos > t[-1]:
        t, d = [*t, segundos], [*d, d[-1]]
    fig = go.Figure(go.Scatter(x=t, y=d, mode="lines", line_shape="hv", name="ALNS: mejor encontrada",
                               line=dict(color=PALETA[0], width=2),
                               hovertemplate="%{x:.1f} s · %{y:,.1f}<extra></extra>"))
    if bks is not None and t:
        fig.add_trace(go.Scatter(x=[0, t[-1]], y=[bks, bks], mode="lines", name="Mejor conocida",
                                 line=dict(color=PALETA[1], width=2, dash="dash"),
                                 hovertemplate="Mejor conocida: %{y:,.1f}<extra></extra>"))
    _base(fig, 360, title=dict(text="Convergencia de ALNS", x=0),
          showlegend=len(fig.data) >= 2, legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(title="Segundos")
    fig.update_yaxes(title="Distancia total")
    return fig


def fig_horario(inst, ruta: list[int]) -> go.Figure:
    filas = horario(inst, ruta)
    y = [f"{i + 1}. Cliente {f['cliente']}" if f["cliente"] else "Regreso al depósito"
         for i, f in enumerate(filas)]
    c = [f["cliente"] for f in filas]
    a, b = inst.inicio[c], inst.fin[c]
    llegada = [f["llegada"] for f in filas]
    inicio = [f["inicio"] for f in filas]
    espera = [f["espera"] for f in filas]
    serv = [f["fin"] - f["inicio"] for f in filas]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=y, x=b - a, base=a, orientation="h", width=0.75, name="Ventana horaria",
                         marker=dict(color=PALETA[0], opacity=0.25),
                         customdata=list(zip(a, b)),
                         hovertemplate="Ventana %{customdata[0]:.0f}–%{customdata[1]:.0f}<extra></extra>"))
    fig.add_trace(go.Bar(y=y, x=espera, base=llegada, orientation="h", width=0.35, name="Espera",
                         marker=dict(color=PALETA[1]),
                         hovertemplate="Espera %{x:.1f} desde %{base:.1f}<extra></extra>"))
    fig.add_trace(go.Bar(y=y, x=serv, base=inicio, orientation="h", width=0.35, name="Servicio",
                         marker=dict(color=PALETA[2]),
                         hovertemplate="Servicio desde %{base:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(y=y, x=llegada, mode="markers", name="Llegada",
                             marker=dict(symbol="diamond", size=9, color=TINTA,
                                         line=dict(color="white", width=1)),
                             hovertemplate="Llegada %{x:.1f}<extra></extra>"))
    _base(fig, 140 + 28 * len(filas), barmode="overlay", bargap=0.1,
          title=dict(text="Horario de la ruta", x=0), legend=dict(orientation="h", y=1.08 if len(filas) > 6 else 1.2, x=0))
    fig.update_xaxes(title="Tiempo desde la apertura del depósito")
    fig.update_yaxes(autorange="reversed", type="category")
    return fig


def tabla_rutas(inst, rutas) -> pd.DataFrame:
    filas = []
    for k, r in enumerate(rutas):
        h = horario(inst, r)
        filas.append({"Ruta": k + 1, "Clientes": len(r),
                      "Carga": f"{int(inst.demanda[r].sum())} / {inst.capacidad}",
                      "Distancia": round(distancia_ruta(inst, r), 1),
                      "Espera total": round(sum(f["espera"] for f in h), 1),
                      "Regreso": round(h[-1]["llegada"], 1),
                      "Secuencia": " → ".join(map(str, r))})
    return pd.DataFrame(filas)


def tabla_horario(inst, ruta) -> pd.DataFrame:
    filas = []
    for i, f in enumerate(horario(inst, ruta)):
        c = f["cliente"]
        filas.append({"Parada": i + 1, "Cliente": "Depósito" if c == 0 else c,
                      "Demanda": int(inst.demanda[c]),
                      "Ventana": f"{inst.inicio[c]:.0f}–{inst.fin[c]:.0f}",
                      "Llegada": round(f["llegada"], 1), "Espera": round(f["espera"], 1),
                      "Inicio servicio": round(f["inicio"], 1), "Fin servicio": round(f["fin"], 1)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------- vista: Inicio

def conclusiones(bm: pd.DataFrame | None, ex: pd.DataFrame | None) -> None:
    if bm is None:
        st.info(textos.SIN_BENCHMARK)
    else:
        n = len(bm)
        medias = {m: bm[f"gap_{m}"].mean() for m in METODOS}
        cols = st.columns(3)
        for col, (m, etiqueta) in zip(cols, METODOS.items()):
            col.metric(f"Gap promedio · {etiqueta}", pct(medias[m], 2))
        seg = bm["alns_segundos"].median()
        capas = ("Cada capa reduce la brecha." if medias["alns"] <= medias["local"] <= medias["insercion"]
                 else "")
        lineas = [
            f"Sobre **{n} instancias**, ALNS (con {num(seg, 0)} s por instancia) queda en promedio a "
            f"**{pct(medias['alns'], 2)}** de la mejor solución conocida, frente a "
            f"{pct(medias['local'], 2)} de la búsqueda local y {pct(medias['insercion'], 2)} de la "
            f"inserción. {capas}"]
        for m in ("alns", "local"):
            g = bm[f"gap_{m}"]
            lineas.append(f"{METODOS[m]}: a menos de 1 % del récord en **{int((g <= 0.01).sum())} de {n}** "
                          f"instancias y a menos de 5 % en **{int((g <= 0.05).sum())} de {n}**.")
        por_fam = bm.groupby("familia")["gap_alns"].mean().dropna()
        if len(por_fam) >= 2:
            lineas.append(f"La familia más difícil para ALNS es **{por_fam.idxmax()}** (gap medio "
                          f"{pct(por_fam.max(), 2)}) y la más fácil **{por_fam.idxmin()}** "
                          f"({pct(por_fam.min(), 2)}).")
        mas = int((bm["alns_rutas"] > bm["bks_rutas"]).sum())
        menos = int((bm["alns_rutas"] < bm["bks_rutas"]).sum())
        lineas.append(f"En camiones, ALNS usa más que el récord en {mas} instancias, los mismos en "
                      f"{n - mas - menos} y menos en {menos} (el objetivo es solo distancia).")
        st.markdown("\n".join(f"- {t}" for t in lineas))
        with st.expander("Gap promedio por familia"):
            st.dataframe(resumen_familias(bm), hide_index=True, width="stretch")
    if ex is None:
        st.info(textos.SIN_EXACTO)
        return
    lineas = []
    for n_cli, g in ex.groupby("n_clientes"):
        opt = g[g["estado"] == "OPTIMAL"]
        texto = (f"Con **{int(n_cli)} clientes**: Gurobi demostró el óptimo en **{len(opt)} de "
                 f"{len(g)}** instancias")
        if len(opt) and "segundos_gurobi" in opt:
            texto += f" ({num(opt['segundos_gurobi'].mean(), 1)} s en promedio)"
        if len(opt) and "gap_alns_vs_optimo" in opt:
            gaps = opt["gap_alns_vs_optimo"]
            iguales = int((gaps.abs() <= 1e-6).sum())
            texto += (f"; ALNS encontró ese mismo óptimo en **{iguales}** y quedó en promedio a "
                      f"**{pct(gaps.mean(), 2)}** de él")
        otros = g.loc[g["estado"] != "OPTIMAL", "estado"].map(lambda e: ESTADOS.get(e, e))
        if len(otros):
            texto += ". Sin óptimo demostrado: " + ", ".join(
                f"{v} ({k})" for k, v in otros.value_counts().items())
        lineas.append(texto + ".")
    st.markdown("\n".join(f"- {t}" for t in lineas))


def vista_inicio(bm, ex) -> None:
    st.title("Ruteo de vehículos con ventanas horarias")
    st.caption(textos.AUTOR)
    como_leer(textos.LEER_INICIO)

    st.header("¿De qué se trata?")
    izq, der = st.columns([1.1, 1])
    with izq:
        st.markdown(textos.QUE_ES)
    with der:
        rutas, costo = record("C101")
        st.plotly_chart(fig_mapa(instancia("C101"), rutas,
                                 f"Ejemplo: récord de C101 ({len(rutas)} camiones, distancia {num(costo)})"),
                        width="stretch", key="mapa_inicio")
    st.markdown(textos.NIVELES)

    st.header("El benchmark de Solomon")
    st.markdown(textos.SOLOMON)
    st.header("Métodos")
    st.markdown(textos.METODOS)
    st.header("Conclusiones")
    conclusiones(bm, ex)
    st.header("Limitaciones")
    st.markdown(textos.LIMITACIONES)
    st.header("Conceptos")
    for titulo, texto in textos.CONCEPTOS:
        with st.expander(titulo):
            st.markdown(texto)


# ---------------------------------------------------------------------------- vista: Resolver

def vista_resolver() -> None:
    st.title("Resolver una instancia")
    como_leer(textos.LEER_RESOLVER.format(vehiculo=VEHICULO))
    lista = nombres()
    c1, c2, c3 = st.columns([1, 1, 1.4])
    with c1:
        nombre = st.selectbox("Instancia", lista, index=lista.index("C101") if "C101" in lista else 0,
                              key="res_inst")
        completa = instancia(nombre)
        recortar = st.toggle("Recortar a los primeros N clientes", key="res_recortar")
        n = (st.slider("N clientes", 5, completa.n_clientes - 1, 25, key="res_n")
             if recortar else None)
    with c2:
        etiqueta = st.radio("Método", list(METODOS.values()), key="res_metodo")
        metodo = next(m for m, e in METODOS.items() if e == etiqueta)
        segundos = (st.slider("Segundos de ALNS", 1, 30, 5, key="res_seg")
                    if metodo == "alns" else 0)
    with c3:
        inst = instancia(nombre, n)
        st.markdown(f"**{inst.nombre}** · familia {familia(nombre)} · {inst.n_clientes} clientes  \n"
                    f"Capacidad por camión: {inst.capacidad} · demanda total: "
                    f"{int(inst.demanda.sum())}  \nJornada del depósito: "
                    f"{inst.inicio[0]:.0f} a {inst.fin[0]:.0f}")
        boton = st.button("Resolver", type="primary", key="res_boton")

    soluciones = st.session_state.setdefault("soluciones", {})
    clave = (nombre, n, metodo, segundos)
    if boton:
        try:
            with st.spinner("Resolviendo..."):
                soluciones[clave] = resolver_heuristica(inst, metodo, float(segundos), 2026)
        except ImportError as e:
            st.error(f"El módulo de heurísticas no está disponible: {e}")
            return
    sol = soluciones.get(clave)
    bks_rutas, bks = record(nombre) if n is None else (None, None)
    if sol is None:
        st.info("Elige la instancia y el método, y presiona **Resolver**.")
        if bks_rutas:
            st.plotly_chart(fig_mapa(inst, bks_rutas, f"Mejor solución conocida ({num(bks)})"),
                            width="stretch", key="mapa_bks_solo")
        return

    rutas = sol["rutas"]
    ev = evaluar(inst, rutas)
    m1, m2, m3, m4 = st.columns(4)
    dif_d = None if bks is None else round(ev.distancia - bks, 1)
    dif_r = None if bks_rutas is None else ev.n_rutas - len(bks_rutas)
    m1.metric("Distancia total", num(ev.distancia),
              delta=None if dif_d is None else f"{'+' if dif_d > 0 else ''}{num(dif_d)} vs récord",
              delta_color="inverse" if dif_d else "off")
    m2.metric("Camiones", ev.n_rutas,
              delta=None if dif_r is None else f"{dif_r:+d} vs récord",
              delta_color="inverse" if dif_r else "off")
    m3.metric("Gap vs mejor conocida", pct(ev.distancia / bks - 1, 2) if bks else "No aplica",
              help=None if bks else "Los récords publicados son de la instancia completa de 100 clientes.")
    m4.metric("Factible", "Sí" if ev.factible else "No")
    st.caption(f"Tiempo de cómputo: {num(sol['segundos'], 2)} s")
    if not ev.factible:
        st.warning("La solución viola restricciones: " + "; ".join(ev.violaciones))

    izq, der = st.columns(2)
    with izq:
        st.plotly_chart(fig_mapa(inst, rutas, f"{etiqueta}: {num(ev.distancia)}"),
                        width="stretch", key="mapa_sol")
    with der:
        if bks_rutas:
            st.plotly_chart(fig_mapa(inst, bks_rutas, f"Mejor conocida: {num(bks)}"),
                            width="stretch", key="mapa_bks")
        else:
            st.info("Con una instancia recortada no hay récord publicado para comparar: los récords "
                    "de Solomon son para los 100 clientes. Para medir la calidad en instancias "
                    "chicas, ve a la vista **Exacto vs heurística**.")

    st.subheader("Animación del recorrido")
    if "animacion" not in sol:  # se arma una vez por solución (cientos de frames)
        sol["animacion"] = figura_animada(inst, rutas)
    st.plotly_chart(sol["animacion"], width="stretch", key="animacion")

    if metodo == "alns" and sol["historial"]:
        st.plotly_chart(fig_convergencia(sol["historial"], sol["segundos"], bks),
                        width="stretch", key="convergencia")

    st.subheader("Rutas")
    mostrar_tabla(tabla_rutas(inst, rutas))
    st.subheader("Horario de una ruta")
    k = st.selectbox("Ruta", list(range(1, len(rutas) + 1)), format_func=lambda i: f"Ruta {i}",
                     key="res_ruta")
    if k is not None and k <= len(rutas):
        st.plotly_chart(fig_horario(inst, rutas[k - 1]), width="stretch", key="horario")
        mostrar_tabla(tabla_horario(inst, rutas[k - 1]))


# ---------------------------------------------------------------------------- vista: Caso Santiago

@st.cache_resource(show_spinner=False)
def caso_santiago(n: int, semilla: int) -> santiago.CasoSantiago:
    return santiago.crear_caso(n, semilla)


def _bultos(q: int) -> str:
    return f"{q} bulto" if q == 1 else f"{q} bultos"


def textos_santiago(caso, horarios=()) -> list[str]:
    """Texto al pasar el mouse por cada punto: comuna, ventana, bultos y, si ya hay plan, la
    hora de llegada."""
    inst, hora = caso.inst, santiago.hora
    visita = {f["cliente"]: f for _, filas in horarios for f in filas[:-1]}
    textos_ = [f"<b>{santiago.NOMBRE_DEPOSITO}</b><br>Abre {hora(inst.inicio[0])}, "
               f"cierra {hora(inst.fin[0])}"]
    for c in range(1, inst.n_clientes + 1):
        t = (f"<b>Cliente {c} · {caso.comunas[c]}</b><br>"
             f"Ventana {hora(inst.inicio[c])}–{hora(inst.fin[c])} ({caso.tipo_ventana[c].lower()})"
             f"<br>{_bultos(int(inst.demanda[c]))}")
        if c in visita:
            f = visita[c]
            t += f"<br>Llega {hora(f['llegada'])}"
            if f["espera"] >= 1:
                t += f" y entrega {hora(f['inicio'])}"
        textos_.append(t)
    return textos_


def _secuencia(nombres_: list[str]) -> str:
    """Comunas en orden, juntando las repetidas seguidas: "Maipú ×2 → Estación Central"."""
    partes: list[list] = []
    for nom in nombres_:
        if partes and partes[-1][0] == nom:
            partes[-1][1] += 1
        else:
            partes.append([nom, 1])
    return " → ".join(nom if k == 1 else f"{nom} ×{k}" for nom, k in partes)


def tabla_santiago(caso, rutas, horarios) -> pd.DataFrame:
    inst, filas = caso.inst, []
    for k, (r, (salida, h)) in enumerate(zip(rutas, horarios)):
        manejo = distancia_ruta(inst, r)
        filas.append({"Camioneta": k + 1, "Clientes": len(r),
                      "Bultos": f"{int(inst.demanda[r].sum())} / {inst.capacidad}",
                      "Salida": santiago.hora(salida), "Regreso": santiago.hora(h[-1]["llegada"]),
                      "Minutos de manejo": round(manejo, 1), "Km aprox.": round(caso.km(manejo), 1),
                      "Secuencia": _secuencia([caso.comunas[c] for c in r])})
    return pd.DataFrame(filas)


def vista_santiago() -> None:
    st.title("Caso Santiago")
    caja = st.container(border=True)  # se llena más abajo, cuando se conoce el número de clientes
    como_leer(textos.LEER_SANTIAGO.format(vehiculo=VEHICULO))
    c1, c2, c3 = st.columns([1, 1, 1.4])
    with c1:
        n = st.slider("Clientes", 15, 60, 40, key="stgo_n")
        semilla = int(st.number_input("Semilla", min_value=0, max_value=999_999, value=2026, step=1,
                                      key="stgo_semilla",
                                      help="Decide la ubicación, la ventana y el pedido de cada "
                                           "cliente. También es la semilla de ALNS."))
    with c2:
        etiqueta = st.radio("Método", list(METODOS.values()), key="stgo_metodo")
        metodo = next(m for m, e in METODOS.items() if e == etiqueta)
        segundos = (st.slider("Segundos de ALNS", 1, 20, 5, key="stgo_seg")
                    if metodo == "alns" else 0)
    caso = caso_santiago(n, semilla)
    inst = caso.inst
    with c3:
        tipos = caso.tipo_ventana[1:]
        st.markdown(f"**{n} clientes** en {len(set(caso.comunas[1:]))} comunas · "
                    f"{int(inst.demanda.sum())} bultos en total  \n"
                    f"Ventanas: {tipos.count('Mañana')} de mañana, {tipos.count('Tarde')} de "
                    f"tarde y {tipos.count('Todo el día')} todo el día  \n"
                    f"Camionetas de {inst.capacidad} bultos (hay {inst.vehiculos}) · jornada de "
                    f"{santiago.hora(inst.inicio[0])} a {santiago.hora(inst.fin[0])}")
        boton = st.button("Planificar el día", type="primary", key="stgo_boton")
    with caja:
        st.markdown("#### ¿De qué se trata?")
        st.markdown(textos.SANTIAGO_QUE_ES.format(n=n))

    planes = st.session_state.setdefault("santiago", {})
    clave = (n, semilla, metodo, segundos)
    if boton:
        try:
            with st.spinner("Planificando las rutas..."):
                planes[clave] = resolver_heuristica(inst, metodo, float(segundos), semilla)
        except ImportError as e:
            st.error(f"El módulo de heurísticas no está disponible: {e}")
            return
    plan = planes.get(clave)
    if plan is None:
        st.info("Elige el número de clientes y el método, y presiona **Planificar el día**.")
        st.plotly_chart(fig_mapa_calles(caso.latlon, [], textos_santiago(caso),
                                        f"Los {n} clientes del día"),
                        width="stretch", key="stgo_mapa_clientes")
        return

    rutas = plan["rutas"]
    if "horarios" not in plan:  # salida lo más tarde posible: la espera se hace en el centro
        plan["horarios"] = [santiago.salida_y_horario(inst, r) for r in rutas]
    horarios = plan["horarios"]
    ev = evaluar(inst, rutas)
    regreso = max((h[-1]["llegada"] for _, h in horarios), default=0.0)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Camionetas", ev.n_rutas, help=f"De {inst.vehiculos} disponibles.")
    m2.metric("Minutos de manejo", num(ev.distancia), help="Suma de todas las camionetas.")
    m3.metric("Km aprox.", num(caso.km(ev.distancia), 0),
              help=f"Minutos × {num(santiago.VELOCIDAD_KMH, 0)} / 60.")
    m4.metric("Regreso de la última", santiago.hora(regreso))
    st.caption(f"{etiqueta} · {num(plan['segundos'], 2)} s de cómputo · "
               f"{'cumple todas las ventanas y capacidades' if ev.factible else 'no factible'}")
    if not ev.factible:
        st.warning("La solución viola restricciones: " + "; ".join(ev.violaciones))
    if ev.n_rutas > inst.vehiculos:
        st.warning(f"El plan usa {ev.n_rutas} camionetas y hay {inst.vehiculos}: las heurísticas "
                   "no limitan la flota.")

    hover = textos_santiago(caso, horarios)
    st.plotly_chart(fig_mapa_calles(caso.latlon, rutas, hover,
                                    f"{etiqueta}: {ev.n_rutas} camionetas, "
                                    f"{num(ev.distancia)} minutos de manejo"),
                    width="stretch", key="stgo_mapa")
    st.subheader("Animación del día")
    if "animacion" not in plan:  # se arma una vez por plan (cientos de frames)
        plan["animacion"] = figura_animada_calles(inst, caso.latlon, rutas, horarios, hover,
                                                  santiago.hora)
    st.plotly_chart(plan["animacion"], width="stretch", key="stgo_animacion")
    st.subheader("Camionetas")
    mostrar_tabla(tabla_santiago(caso, rutas, horarios))


# ---------------------------------------------------------------------------- vista: Benchmark

def resumen_familias(bm: pd.DataFrame) -> pd.DataFrame:
    gaps = [f"gap_{m}" for m in METODOS]
    fams = [f for f in FAMILIAS if f in set(bm["familia"])] + sorted(
        set(bm["familia"]) - set(FAMILIAS))
    tabla = bm.groupby("familia")[gaps].mean().reindex(fams)
    tabla.loc["Todas"] = bm[gaps].mean()
    tabla.insert(0, "Instancias", [int((bm["familia"] == f).sum()) for f in fams] + [len(bm)])
    tabla = tabla.reset_index().rename(columns={"index": "Familia", "familia": "Familia"})
    for m, e in METODOS.items():
        tabla[e] = tabla.pop(f"gap_{m}").map(lambda x: pct(x, 2))
    return tabla


def vista_benchmark(bm) -> None:
    st.title("Benchmark de Solomon")
    como_leer(textos.LEER_BENCHMARK)
    if bm is None:
        st.info(textos.SIN_BENCHMARK)
        return
    st.caption(f"{len(bm)} instancias · ALNS con {num(bm['alns_segundos'].median(), 0)} s por "
               f"instancia (mediana) · búsqueda local en {num(bm['local_segundos'].mean(), 2)} s "
               "promedio")
    fams = [f for f in FAMILIAS if f in set(bm["familia"])]
    medias = bm.groupby("familia")[[f"gap_{m}" for m in METODOS]].mean().reindex(fams)
    fig = go.Figure()
    for i, (m, e) in enumerate(METODOS.items()):
        fig.add_trace(go.Bar(x=fams, y=100 * medias[f"gap_{m}"], name=e,
                             marker=dict(color=PALETA[i], cornerradius=4),
                             hovertemplate=f"{e} · %{{x}}: %{{y:.2f}} %<extra></extra>"))
    _base(fig, 400, barmode="group", bargap=0.25, bargroupgap=0.08,
          title=dict(text="Gap promedio contra la mejor conocida, por familia", x=0),
          legend=dict(orientation="h", y=-0.15))
    fig.update_yaxes(title="Gap promedio (%)", ticksuffix=" %")
    fig.update_xaxes(title="Familia")
    st.plotly_chart(fig, width="stretch", key="barras_familia")
    st.dataframe(resumen_familias(bm), hide_index=True, width="stretch")

    st.subheader("Detalle por instancia")
    f1, f2 = st.columns([2, 1])
    elegidas = f1.multiselect("Familias", fams, default=fams, key="bm_familias")
    buscar = f2.text_input("Buscar instancia", key="bm_buscar", placeholder="Ej.: R105")
    vista = bm[bm["familia"].isin(elegidas)]
    if buscar:
        vista = vista[vista["instancia"].str.contains(buscar.strip(), case=False, regex=False)]
    tabla = pd.DataFrame({
        "Instancia": vista["instancia"], "Familia": vista["familia"],
        "Récord": vista["bks_distancia"], "Camiones récord": vista["bks_rutas"],
        **{f"{e}": vista[f"{m}_distancia"] for m, e in METODOS.items()},
        **{f"Gap {e}": 100 * vista[f"gap_{m}"] for m, e in METODOS.items()},
        "Camiones ALNS": vista["alns_rutas"]})
    mostrar_tabla(tabla, porcentajes=[f"Gap {e}" for e in METODOS.values()])
    st.caption(f"{len(tabla)} de {len(bm)} instancias. Haz clic en una columna para ordenar.")


# ---------------------------------------------------------------------------- vista: Exacto

def vista_exacto(ex) -> None:
    st.title("Exacto vs heurística")
    como_leer(textos.LEER_EXACTO)
    st.markdown(textos.GAP_OPTIMALIDAD)
    if ex is None:
        st.info(textos.SIN_EXACTO)
    else:
        def col(c: str) -> pd.Series:
            return pd.to_numeric(ex[c], errors="coerce") if c in ex else pd.Series(
                float("nan"), index=ex.index)

        tabla = pd.DataFrame({
            "Instancia": ex["instancia"], "Clientes": ex["n_clientes"],
            "Estado": ex["estado"].map(lambda e: ESTADOS.get(e, e)),
            "Gurobi": col("optimo"), "Cota inferior": col("cota"),
            "Gap Gurobi": 100 * col("gap_gurobi"),
            "Segundos Gurobi": col("segundos_gurobi"), "ALNS": col("alns_distancia"),
            "Gap ALNS vs Gurobi": 100 * col("gap_alns_vs_optimo")})
        mostrar_tabla(tabla, porcentajes=["Gap Gurobi", "Gap ALNS vs Gurobi"])
        if "detalle" in ex:
            for _, f in ex[ex["detalle"].notna()].iterrows():
                st.caption(f"{f['instancia']}: {f['detalle']}")
        _resumen_exacto(ex)

    st.subheader("Pruébalo en vivo")
    st.markdown("Elige una instancia, recórtala a pocos clientes y compara el óptimo de Gurobi "
                "con ALNS. Con la licencia gratuita de Gurobi el modelo debe ser pequeño.")
    lista = nombres()
    c1, c2, c3 = st.columns(3)
    nombre = c1.selectbox("Instancia", lista, index=lista.index("R101") if "R101" in lista else 0,
                          key="ex_inst")
    n = c1.slider("Clientes", 8, 15, 10, key="ex_n")
    limite = c2.slider("Tiempo máximo de Gurobi (s)", 5, 60, 20, key="ex_lim")
    seg = c2.slider("Segundos de ALNS", 1, 10, 2, key="ex_seg")
    c3.write("")
    boton = c3.button("Comparar", type="primary", key="ex_boton")
    inst = instancia(nombre, n)
    resultados = st.session_state.setdefault("exactos", {})
    clave = (nombre, n, limite, seg)
    if boton:
        res: dict = {}
        with st.spinner("Resolviendo con ALNS y con Gurobi..."):
            try:
                res["alns"] = resolver_heuristica(inst, "alns", float(seg), 2026)
            except ImportError as e:
                res["error_alns"] = f"El módulo de heurísticas no está disponible: {e}"
            try:
                from ruteo.exacto import resolver_exacto
                res["exacto"] = resolver_exacto(inst, limite_seg=float(limite))
            except ValueError as e:
                res["error_exacto"] = str(e)
            except Exception as e:  # noqa: BLE001  (gurobipy ausente, licencia, etc.)
                res["error_exacto"] = f"Gurobi no pudo resolver: {e}"
        resultados[clave] = res
    res = resultados.get(clave)
    if res is None:
        st.info("Presiona **Comparar** para resolver.")
        return
    izq, der = st.columns(2)
    ex_res = res.get("exacto")
    with izq:
        st.markdown("#### Gurobi (exacto)")
        if "error_exacto" in res:
            st.error(res["error_exacto"])
        elif ex_res is not None:
            a, b = st.columns(2)
            a.metric("Distancia", num(ex_res.distancia))
            b.metric("Estado", ESTADOS.get(ex_res.estado, ex_res.estado))
            a.metric("Cota inferior", num(ex_res.cota))
            b.metric("Gap de optimalidad", pct(ex_res.gap, 2))
            st.caption(f"{num(ex_res.segundos, 2)} s · {len(ex_res.rutas)} camiones")
            if ex_res.rutas:
                st.plotly_chart(fig_mapa(inst, ex_res.rutas, "Solución de Gurobi"),
                                width="stretch", key="mapa_gurobi")
    with der:
        st.markdown("#### ALNS (heurística)")
        if "error_alns" in res:
            st.error(res["error_alns"])
        else:
            ev = evaluar(inst, res["alns"]["rutas"])
            a, b = st.columns(2)
            a.metric("Distancia", num(ev.distancia))
            b.metric("Factible", "Sí" if ev.factible else "No")
            opt = ex_res.distancia if ex_res is not None and ex_res.distancia else None
            a.metric("Gap vs Gurobi", pct(ev.distancia / opt - 1, 2) if opt else "—")
            b.metric("Camiones", ev.n_rutas)
            st.caption(f"{num(res['alns']['segundos'], 2)} s")
            st.plotly_chart(fig_mapa(inst, res["alns"]["rutas"], "Solución de ALNS"),
                            width="stretch", key="mapa_alns_ex")
    with st.expander("Ver la animación del recorrido (solución de ALNS)"):
        if "alns" in res:
            if "animacion" not in res["alns"]:
                res["alns"]["animacion"] = figura_animada(inst, res["alns"]["rutas"])
            st.plotly_chart(res["alns"]["animacion"], width="stretch", key="animacion_ex")


def _resumen_exacto(ex: pd.DataFrame) -> None:
    lineas = []
    for n_cli, g in ex.groupby("n_clientes"):
        opt = g[g["estado"] == "OPTIMAL"]
        t = f"**{int(n_cli)} clientes**: óptimo demostrado en {len(opt)} de {len(g)}"
        if len(opt) and "gap_alns_vs_optimo" in opt:
            t += f"; ALNS a {pct(opt['gap_alns_vs_optimo'].mean(), 2)} del óptimo en promedio"
        lineas.append(t + ".")
    st.markdown("\n".join(f"- {t}" for t in lineas))


# ---------------------------------------------------------------------------- main

def main() -> None:
    st.set_page_config(page_title="Ruteo de vehículos (VRPTW)", page_icon=":material/local_shipping:",
                       layout="wide")
    with st.sidebar:
        st.markdown("### Ruteo de vehículos")
        st.caption("VRPTW sobre el benchmark de Solomon")
        vista = st.radio("Vista", VISTAS, key="vista", label_visibility="collapsed")
        st.divider()
        st.caption(textos.AUTOR)
    bm = leer_resultados("benchmark.csv", COLS_BENCHMARK)
    ex = leer_resultados("exacto.csv", COLS_EXACTO)
    if vista == "Inicio":
        vista_inicio(bm, ex)
    elif vista == "Resolver una instancia":
        vista_resolver()
    elif vista == "Caso Santiago":
        vista_santiago()
    elif vista == "Benchmark":
        vista_benchmark(bm)
    else:
        vista_exacto(ex)


main()
