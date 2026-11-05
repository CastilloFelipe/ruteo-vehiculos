"""Heurísticas para VRPTW: inserción constructiva, búsqueda local y ALNS.

Objetivo: minimizar la distancia total (convención DIMACS); no se limita el número de
vehículos. Todas las funciones devuelven soluciones factibles según `evaluacion.evaluar`.

Clave de rendimiento: para cada ruta se guardan dos arreglos sobre la ruta extendida
`ext = [0, *ruta, 0]`:

- `ini[k]`: inicio de servicio en `ext[k]` recorriendo hacia adelante (con espera);
- `tard[k]`: inicio más tardío posible en `ext[k]` sin que el resto de la ruta llegue tarde.

Con ellos, insertar un cliente (o un tramo corto) entre `ext[k]` y `ext[k+1]` es factible
si se llega a tiempo a lo insertado y luego a `ext[k+1]` a más tardar en `tard[k+1]`: la
verificación cuesta O(largo del tramo) en vez de O(largo de la ruta). Lo mismo vale para
quitar un tramo y para el intercambio de colas (2-opt*).
"""
from __future__ import annotations

import math
import random
import time

import numpy as np

from .evaluacion import evaluar
from .instancia import Instancia

EPS = 1e-7
INF = float("inf")


# --------------------------------------------------------------------------------------
# Datos y utilidades de ruta
# --------------------------------------------------------------------------------------

class _Datos:
    """La instancia como listas de Python (el acceso elemento a elemento es más rápido que numpy)."""

    def __init__(self, inst: Instancia):
        self.n = inst.n_clientes
        self.d = np.asarray(inst.dist, dtype=float).tolist()
        self.e = np.asarray(inst.inicio, dtype=float).tolist()
        self.l = np.asarray(inst.fin, dtype=float).tolist()
        self.s = np.asarray(inst.servicio, dtype=float).tolist()
        self.q = np.asarray(inst.demanda, dtype=int).tolist()
        self.Q = int(inst.capacidad)
        self._orden_shaw = None
        self._inst = inst

    def orden_shaw(self) -> list[list[int]]:
        """Para cada cliente, los demás clientes ordenados de más a menos relacionados."""
        if self._orden_shaw is None:
            inst, n = self._inst, self.n
            dist = np.asarray(inst.dist, dtype=float)[1:, 1:]
            e = np.asarray(inst.inicio, dtype=float)[1:]
            q = np.asarray(inst.demanda, dtype=float)[1:]
            rel = (9 * dist / max(dist.max(), 1e-9)
                   + 3 * np.abs(e[:, None] - e[None, :]) / max(np.ptp(e), 1e-9)
                   + 2 * np.abs(q[:, None] - q[None, :]) / max(np.ptp(q), 1e-9))
            np.fill_diagonal(rel, np.inf)
            orden = np.argsort(rel, axis=1, kind="stable")[:, : n - 1] + 1
            self._orden_shaw = [[]] + orden.tolist()
        return self._orden_shaw


def _tiempos(D: _Datos, r: list[int]) -> tuple[list[int], list[float], list[float]]:
    """Ruta extendida, inicios de servicio hacia adelante e inicios más tardíos hacia atrás."""
    d, e, l, s = D.d, D.e, D.l, D.s
    ext = [0, *r, 0]
    m = len(ext)
    ini = [0.0] * m
    t = 0.0
    for k in range(1, m):
        p, c = ext[k - 1], ext[k]
        t += s[p] + d[p][c]
        if t < e[c]:
            t = e[c]
        ini[k] = t
    tard = [0.0] * m
    t = l[0]
    tard[m - 1] = t
    for k in range(m - 2, -1, -1):
        c = ext[k]
        t = t - d[c][ext[k + 1]] - s[c]
        if t > l[c]:
            t = l[c]
        tard[k] = t
    return ext, ini, tard


def _factible_tiempo(D: _Datos, r: list[int]) -> bool:
    d, e, l, s = D.d, D.e, D.l, D.s
    t, p = 0.0, 0
    for c in r:
        t += s[p] + d[p][c]
        if t > l[c] + EPS:
            return False
        if t < e[c]:
            t = e[c]
        p = c
    return t + s[p] + d[p][0] <= l[0] + EPS


def _costo_ruta(D: _Datos, r: list[int]) -> float:
    d = D.d
    total, p = 0.0, 0
    for c in r:
        total += d[p][c]
        p = c
    return total + d[p][0]


def _costo(D: _Datos, rutas: list[list[int]]) -> float:
    return sum(_costo_ruta(D, r) for r in rutas)


def _cabe(D: _Datos, tramo: list[int], ext, ini, tard, kp: int, kn: int) -> bool:
    """¿Es factible en tiempo poner `tramo` entre ext[kp] y ext[kn] (lo de en medio se quita)?"""
    d, e, l, s = D.d, D.e, D.l, D.s
    prev = ext[kp]
    t = ini[kp] + s[prev]
    for c in tramo:
        t += d[prev][c]
        if t > l[c] + EPS:
            return False
        if t < e[c]:
            t = e[c]
        t += s[c]
        prev = c
    return t + d[prev][ext[kn]] <= tard[kn] + EPS


def _mejor_pos(D: _Datos, c: int, ext, ini, tard) -> tuple[float, int]:
    """Inserción factible más barata de c en la ruta: (aumento de distancia, índice en la ruta)."""
    d, s = D.d, D.s
    dc, ec, lc, sc = d[c], D.e[c], D.l[c] + EPS, D.s[c]
    mejor, pos = INF, -1
    for k in range(len(ext) - 1):
        p, n = ext[k], ext[k + 1]
        dp = d[p]
        costo = dp[c] + dc[n] - dp[n]
        if costo >= mejor:
            continue
        t = ini[k] + s[p] + dp[c]
        if t > lc:
            continue
        if t < ec:
            t = ec
        if t + sc + dc[n] > tard[k + 1] + EPS:
            continue
        mejor, pos = costo, k
    return mejor, pos


# --------------------------------------------------------------------------------------
# 1. Inserción constructiva
# --------------------------------------------------------------------------------------

def _construir(D: _Datos, criterio: str) -> list[list[int]]:
    d, l, q, Q = D.d, D.l, D.q, D.Q
    sin_ruta = list(range(1, D.n + 1))
    rutas = []
    while sin_ruta:
        if criterio == "lejano":
            semilla = max(sin_ruta, key=lambda c: (d[0][c], -c))
        else:  # "plazo": el que cierra antes
            semilla = min(sin_ruta, key=lambda c: (l[c], c))
        sin_ruta.remove(semilla)
        r, carga = [semilla], q[semilla]
        while True:
            ext, ini, tard = _tiempos(D, r)
            mejor, elegido = INF, None
            for c in sin_ruta:
                if carga + q[c] > Q:
                    continue
                costo, pos = _mejor_pos(D, c, ext, ini, tard)
                if costo < mejor:
                    mejor, elegido = costo, (c, pos)
            if elegido is None:
                break
            c, pos = elegido
            r.insert(pos, c)
            carga += q[c]
            sin_ruta.remove(c)
        rutas.append(r)
    return rutas


def _insercion(D: _Datos) -> list[list[int]]:
    candidatas = [_construir(D, criterio) for criterio in ("lejano", "plazo")]
    return min(candidatas, key=lambda rs: _costo(D, rs))


def insercion(inst: Instancia) -> list[list[int]]:
    """Inserción secuencial más barata (estilo Solomon I1, criterio = aumento de distancia).

    Abre una ruta con una semilla (el cliente sin ruta más lejano del depósito, o el de
    ventana que cierra antes), inserta repetidamente al cliente cuya inserción factible
    cuesta menos distancia y abre una ruta nueva cuando ninguno cabe. Se prueban ambos
    criterios de semilla y se devuelve la solución más corta.
    """
    return _insercion(_Datos(inst))


# --------------------------------------------------------------------------------------
# 2. Búsqueda local
# --------------------------------------------------------------------------------------

class _BusquedaLocal:
    def __init__(self, D: _Datos, rutas: list[list[int]]):
        self.D = D
        self.R = [list(r) for r in rutas if r]
        self.carga = [sum(D.q[c] for c in r) for r in self.R]
        self.T = [_tiempos(D, r) for r in self.R]

    def _actualizar(self, i: int) -> None:
        self.carga[i] = sum(self.D.q[c] for c in self.R[i])
        self.T[i] = _tiempos(self.D, self.R[i])

    def reubicar(self) -> bool:
        """Or-opt: mueve tramos de 1 a 3 clientes a otra posición (misma ruta u otra)."""
        D, R = self.D, self.R
        d, s, q, Q = D.d, D.s, D.q, D.Q
        mejora = False
        for ia in range(len(R)):
            i = 0
            while i < len(R[ia]):
                aplicado = False
                for k in (1, 2, 3):
                    A = R[ia]
                    if i + k > len(A):
                        break
                    extA, iniA, tardA = self.T[ia]
                    tramo = A[i:i + k]
                    u0, u1 = tramo[0], tramo[-1]
                    p, n = extA[i], extA[i + k + 1]
                    ganancia = d[p][u0] + d[u1][n] - d[p][n]
                    mejor, mov = -EPS, None
                    # A otra ruta: quitar el tramo de A debe seguir siendo factible.
                    if iniA[i] + s[p] + d[p][n] <= tardA[i + k + 1] + EPS:
                        qt = sum(q[c] for c in tramo)
                        for ib in range(len(R)):
                            if ib == ia or self.carga[ib] + qt > Q:
                                continue
                            extB, iniB, tardB = self.T[ib]
                            for j in range(len(extB) - 1):
                                pb, nb = extB[j], extB[j + 1]
                                delta = d[pb][u0] + d[u1][nb] - d[pb][nb] - ganancia
                                if delta < mejor and _cabe(D, tramo, extB, iniB, tardB, j, j + 1):
                                    mejor, mov = delta, (ib, j)
                    # Dentro de la misma ruta.
                    resto = A[:i] + A[i + k:]
                    for j in range(len(resto) + 1):
                        if j == i:
                            continue
                        pb = resto[j - 1] if j > 0 else 0
                        nb = resto[j] if j < len(resto) else 0
                        delta = d[pb][u0] + d[u1][nb] - d[pb][nb] - ganancia
                        if delta < mejor and _factible_tiempo(D, resto[:j] + tramo + resto[j:]):
                            mejor, mov = delta, (ia, j)
                    if mov is not None:
                        ib, j = mov
                        if ib == ia:
                            R[ia] = resto[:j] + tramo + resto[j:]
                        else:
                            R[ia] = resto
                            R[ib] = R[ib][:j] + tramo + R[ib][j:]
                            self._actualizar(ib)
                        self._actualizar(ia)
                        mejora = aplicado = True
                        break
                if not aplicado:
                    i += 1
        return mejora

    def intercambiar(self) -> bool:
        """Swap: intercambia dos clientes de rutas distintas."""
        D, R = self.D, self.R
        d, q, Q = D.d, D.q, D.Q
        mejora = False
        for ia in range(len(R)):
            for i in range(len(R[ia])):
                A = R[ia]
                extA, iniA, tardA = self.T[ia]
                u = A[i]
                pa, na = extA[i], extA[i + 2]
                base_a = d[pa][u] + d[u][na]
                mejor, mov = -EPS, None
                for ib in range(len(R)):
                    if ib == ia:
                        continue
                    B = R[ib]
                    extB, iniB, tardB = self.T[ib]
                    holgura_a = Q - self.carga[ia] + q[u]
                    holgura_b = Q - self.carga[ib]
                    for j in range(len(B)):
                        v = B[j]
                        if q[v] > holgura_a or q[u] > holgura_b + q[v]:
                            continue
                        pb, nb = extB[j], extB[j + 2]
                        delta = (d[pa][v] + d[v][na] - base_a
                                 + d[pb][u] + d[u][nb] - d[pb][v] - d[v][nb])
                        if (delta < mejor and _cabe(D, [v], extA, iniA, tardA, i, i + 2)
                                and _cabe(D, [u], extB, iniB, tardB, j, j + 2)):
                            mejor, mov = delta, (ib, j)
                if mov is not None:
                    ib, j = mov
                    R[ib][j], R[ia][i] = u, R[ib][j]
                    self._actualizar(ia)
                    self._actualizar(ib)
                    mejora = True
        return mejora

    def dos_opt_estrella(self) -> bool:
        """2-opt*: intercambia las colas de dos rutas (A[:i] + B[j:], B[:j] + A[i:])."""
        D, R = self.D, self.R
        d, s, q, Q = D.d, D.s, D.q, D.Q
        mejora = False
        for ia in range(len(R)):
            for ib in range(ia + 1, len(R)):
                A, B = R[ia], R[ib]
                extA, iniA, tardA = self.T[ia]
                extB, iniB, tardB = self.T[ib]
                prefA = [0]
                for c in A:
                    prefA.append(prefA[-1] + q[c])
                prefB = [0]
                for c in B:
                    prefB.append(prefB[-1] + q[c])
                cA, cB = prefA[-1], prefB[-1]
                mejor, mov = -EPS, None
                for i in range(len(A) + 1):
                    a, a2 = extA[i], extA[i + 1]
                    da = d[a]
                    ta = iniA[i] + s[a]
                    base = da[a2]
                    for j in range(len(B) + 1):
                        b, b2 = extB[j], extB[j + 1]
                        delta = da[b2] + d[b][a2] - base - d[b][b2]
                        if delta >= mejor:
                            continue
                        if prefA[i] + cB - prefB[j] > Q or prefB[j] + cA - prefA[i] > Q:
                            continue
                        if ta + da[b2] > tardB[j + 1] + EPS:
                            continue
                        if iniB[j] + s[b] + d[b][a2] > tardA[i + 1] + EPS:
                            continue
                        mejor, mov = delta, (i, j)
                if mov is not None:
                    i, j = mov
                    R[ia], R[ib] = A[:i] + B[j:], B[:j] + A[i:]
                    self._actualizar(ia)
                    self._actualizar(ib)
                    mejora = True
        return mejora

    def dos_opt(self) -> bool:
        """2-opt dentro de cada ruta: invierte un tramo."""
        D, R = self.D, self.R
        d = D.d
        mejora = False
        for ia in range(len(R)):
            seguir = True
            while seguir:
                seguir = False
                A = R[ia]
                ext = self.T[ia][0]
                for i in range(len(A) - 1):
                    p, ci = ext[i], ext[i + 1]
                    for j in range(i + 1, len(A)):
                        cj, n = ext[j + 1], ext[j + 2]
                        if d[p][cj] + d[ci][n] - d[p][ci] - d[cj][n] >= -EPS:
                            continue
                        nueva = A[:i] + A[i:j + 1][::-1] + A[j + 1:]
                        if (_factible_tiempo(D, nueva)
                                and _costo_ruta(D, nueva) < _costo_ruta(D, A) - EPS):
                            R[ia] = nueva
                            self._actualizar(ia)
                            mejora = seguir = True
                            break
                    if seguir:
                        break
        return mejora

    def ejecutar(self) -> list[list[int]]:
        while True:
            mejora = self.reubicar()
            mejora |= self.intercambiar()
            mejora |= self.dos_opt_estrella()
            mejora |= self.dos_opt()
            if not mejora:
                return [r for r in self.R if r]


def _busqueda_local(D: _Datos, rutas: list[list[int]]) -> list[list[int]]:
    return _BusquedaLocal(D, rutas).ejecutar()


def _validar(inst: Instancia, rutas: list[list[int]]) -> None:
    """Las rutas que entrega el usuario deben ser una solución factible y completa."""
    ev = evaluar(inst, rutas)
    if not ev.factible:
        raise ValueError("Las rutas iniciales no son factibles: " + "; ".join(ev.violaciones[:3]))


def busqueda_local(inst: Instancia, rutas: list[list[int]]) -> list[list[int]]:
    """Búsqueda local hasta óptimo local: or-opt (tramos de 1-3, intra e inter-ruta),
    swap inter-ruta, 2-opt* (intercambio de colas) y 2-opt intra-ruta.

    Cada vecindario toma, para cada elemento, el mejor movimiento factible que reduce la
    distancia. `rutas` debe ser factible (si no, ValueError); nunca empeora la distancia y
    elimina las rutas vacías.
    """
    _validar(inst, rutas)
    return _busqueda_local(_Datos(inst), rutas)


# --------------------------------------------------------------------------------------
# 3. ALNS
# --------------------------------------------------------------------------------------

def _quitar(D: _Datos, rutas: list[list[int]], quitar: list[int]) -> tuple[list[list[int]], list[int]]:
    """Saca clientes de las rutas. Si una ruta queda infactible (posible con distancias
    truncadas, que no cumplen la desigualdad triangular), se sacan todos sus clientes."""
    fuera = set(quitar)
    nuevas, pendientes = [], list(quitar)
    for r in rutas:
        if not fuera.intersection(r):
            nuevas.append(r)
            continue
        resto = [c for c in r if c not in fuera]
        if not resto:
            continue
        if _factible_tiempo(D, resto):
            nuevas.append(resto)
        else:
            pendientes.extend(resto)
    return nuevas, pendientes


def _destruir_aleatorio(D, rutas, k, rng):
    return rng.sample(range(1, D.n + 1), k)


def _destruir_peor(D, rutas, k, rng):
    d = D.d
    ahorros = []
    for r in rutas:
        ext = [0, *r, 0]
        for j, c in enumerate(r):
            p, n = ext[j], ext[j + 2]
            ahorros.append((d[p][c] + d[c][n] - d[p][n], c))
    ahorros.sort(reverse=True)
    lista = [c for _, c in ahorros]
    return [lista.pop(int(len(lista) * rng.random() ** 3)) for _ in range(k)]


def _destruir_shaw(D, rutas, k, rng):
    orden = D.orden_shaw()
    fuera = [False] * (D.n + 1)
    elegidos = [rng.randint(1, D.n)]
    fuera[elegidos[0]] = True
    while len(elegidos) < k:
        ref = elegidos[rng.randrange(len(elegidos))]
        libres = [c for c in orden[ref] if not fuera[c]]
        c = libres[int(len(libres) * rng.random() ** 6)]
        fuera[c] = True
        elegidos.append(c)
    return elegidos


_DESTRUIR = (_destruir_aleatorio, _destruir_peor, _destruir_shaw)


def _reparar(D: _Datos, rutas: list[list[int]], pendientes: list[int], regret: bool) -> list[list[int]]:
    """Inserción más barata (greedy) o regret-2; abre rutas nuevas cuando conviene o es necesario."""
    d, q, Q = D.d, D.q, D.Q
    carga = [sum(q[c] for c in r) for r in rutas]
    T = [_tiempos(D, r) for r in rutas]

    def opcion(c, ri):
        if carga[ri] + q[c] > Q:
            return (INF, -1)
        ext, ini, tard = T[ri]
        return _mejor_pos(D, c, ext, ini, tard)

    opciones = {c: [opcion(c, ri) for ri in range(len(rutas))] for c in pendientes}
    pend = list(pendientes)
    while pend:
        mejor_clave, elegido = None, None
        for idx, c in enumerate(pend):
            b1, r1, p1, b2 = d[0][c] + d[c][0], -1, 0, INF  # opción base: ruta nueva
            for ri, (costo, pos) in enumerate(opciones[c]):
                if costo < b1:
                    b2, b1, r1, p1 = b1, costo, ri, pos
                elif costo < b2:
                    b2 = costo
            clave = (b1 - b2, b1) if regret else (b1, 0.0)
            if mejor_clave is None or clave < mejor_clave:
                mejor_clave, elegido = clave, (idx, c, r1, p1)
        idx, c, r1, p1 = elegido
        pend.pop(idx)
        del opciones[c]
        if r1 < 0:
            rutas.append([c])
            carga.append(q[c])
            T.append(_tiempos(D, rutas[-1]))
            r1 = len(rutas) - 1
            for o in pend:
                opciones[o].append(opcion(o, r1))
        else:
            rutas[r1].insert(p1, c)
            carga[r1] += q[c]
            T[r1] = _tiempos(D, rutas[r1])
            for o in pend:
                opciones[o][r1] = opcion(o, r1)
    return rutas


def _ruleta(rng: random.Random, pesos: list[float]) -> int:
    x, acum = rng.random() * sum(pesos), 0.0
    for i, w in enumerate(pesos):
        acum += w
        if x < acum:
            return i
    return len(pesos) - 1


def alns(inst: Instancia, segundos: float = 10.0, semilla: int = 2026,
         rutas_iniciales: list[list[int]] | None = None,
         max_iter: int | None = None) -> tuple[list[list[int]], list[tuple[float, float]]]:
    """Adaptive Large Neighborhood Search (Ropke y Pisinger, 2006) sobre la distancia total.

    Parte de `insercion` + `busqueda_local` (o de `rutas_iniciales`, que deben ser factibles,
    pasadas por la búsqueda local). En cada iteración quita entre ~5 % y ~25 % de los
    clientes con un operador de destrucción (aleatorio, peor costo, Shaw por distancia,
    ventana y demanda) y los reinserta con un operador de reparación (greedy o regret-2),
    ambos elegidos por ruleta con pesos adaptativos (puntajes 33 / 9 / 13 por nuevo
    mejor / mejora del actual / aceptado; reacción 0,1 cada 100 iteraciones). Acepta con
    recocido simulado (temperatura inicial: un 3 % peor se acepta con prob. 0,5; enfría
    exponencialmente hasta 0,2 % de la inicial). Cada nuevo mejor se pule con
    `busqueda_local`.

    Se detiene a los `segundos` de reloj o, si se da `max_iter`, al llegar a ese número de
    iteraciones (lo que ocurra primero). Con `max_iter` el enfriamiento depende de la
    iteración y no del reloj, así que misma `semilla` + mismo `max_iter` (y tiempo
    suficiente) da exactamente el mismo resultado.

    Devuelve (mejores rutas, historial) con historial = [(segundos transcurridos, mejor
    distancia)], un punto por cada mejora; el primero es la solución inicial.
    """
    t0 = time.perf_counter()
    D = _Datos(inst)
    rng = random.Random(semilla)
    if rutas_iniciales is not None:
        _validar(inst, rutas_iniciales)
    inicial = _insercion(D) if rutas_iniciales is None else [list(r) for r in rutas_iniciales]
    actual = _busqueda_local(D, inicial)
    f_actual = _costo(D, actual)
    mejor, f_mejor = actual, f_actual
    historial = [(time.perf_counter() - t0, f_mejor)]
    if D.n < 2:
        return mejor, historial

    q_min = max(1, round(0.05 * D.n))
    q_max = min(D.n, max(q_min, round(0.25 * D.n)))
    temp0 = 0.03 * f_actual / math.log(2) if f_actual > 0 else 1.0
    pesos_d, pesos_r = [1.0] * len(_DESTRUIR), [1.0, 1.0]
    punt_d, punt_r = [0.0] * len(_DESTRUIR), [0.0, 0.0]
    usos_d, usos_r = [0] * len(_DESTRUIR), [0, 0]
    it = 0
    while True:
        transcurrido = time.perf_counter() - t0
        if transcurrido >= segundos or (max_iter is not None and it >= max_iter):
            break
        progreso = it / max_iter if max_iter else transcurrido / max(segundos, 1e-9)
        temp = temp0 * 0.002 ** min(progreso, 1.0)

        od, orp = _ruleta(rng, pesos_d), _ruleta(rng, pesos_r)
        k = rng.randint(q_min, q_max)
        quitar = _DESTRUIR[od](D, actual, k, rng)
        cand, pendientes = _quitar(D, actual, quitar)
        cand = _reparar(D, [r[:] for r in cand], pendientes, regret=orp == 1)
        f = _costo(D, cand)

        if f < f_mejor - EPS:
            cand = _busqueda_local(D, cand)
            f = _costo(D, cand)
            mejor, f_mejor = cand, f
            actual, f_actual = cand, f
            historial.append((time.perf_counter() - t0, f_mejor))
            puntaje = 33.0
        elif f < f_actual - EPS:
            actual, f_actual, puntaje = cand, f, 9.0
        elif rng.random() < math.exp(-(f - f_actual) / temp):
            # Ropke y Pisinger premian solo las soluciones peores aceptadas; aceptar una de
            # igual costo no suma puntaje (si no, los pesos premian movimientos que no cambian nada).
            puntaje = 13.0 if f > f_actual + EPS else 0.0
            actual, f_actual = cand, f
        else:
            puntaje = 0.0

        punt_d[od] += puntaje
        punt_r[orp] += puntaje
        usos_d[od] += 1
        usos_r[orp] += 1
        it += 1
        if it % 100 == 0:
            for pesos, punt, usos in ((pesos_d, punt_d, usos_d), (pesos_r, punt_r, usos_r)):
                for i in range(len(pesos)):
                    if usos[i]:
                        pesos[i] = max(0.9 * pesos[i] + 0.1 * punt[i] / usos[i], 0.05)
                    punt[i], usos[i] = 0.0, 0
    return mejor, historial
