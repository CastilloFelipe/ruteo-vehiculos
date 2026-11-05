"""Caso ilustrativo: un día de reparto de última milla en Santiago de Chile.

Un centro de distribución genérico en la zona logística de Pudahuel (sector ENEA) reparte
paquetes a clientes de 20 comunas, cada uno con su ventana de entrega. El caso es
**ilustrativo**, no un dato real:

- los clientes son sintéticos: se ubican al azar (con semilla) alrededor del centro aproximado
  de cada comuna, con un desvío de ~0,6 km;
- el tiempo de viaje sale de la distancia en línea recta (haversine) × 1,35 de factor de
  rodeo, a 28 km/h promedio. No usa la red vial real ni el tráfico.

Unidades: el tiempo se mide en minutos desde las 08:00, cuando abre el centro. La matriz `dist`
de la instancia es el tiempo de viaje en minutos, truncado a un decimal (convención DIMACS).
Como las heurísticas minimizan `dist`, aquí minimizan los minutos de manejo; los km se obtienen
con `km(minutos)`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .evaluacion import horario
from .instancia import Instancia

# Centro de distribución genérico en la zona logística de Pudahuel / ENEA (lat, lon).
DEPOSITO = (-33.4400, -70.7700)
NOMBRE_DEPOSITO = "Centro de distribución (Pudahuel)"

# Centro aproximado de cada comuna (lat, lon). Solo sirve para ubicar clientes sintéticos.
COMUNAS: dict[str, tuple[float, float]] = {
    "Santiago Centro": (-33.4430, -70.6540),
    "Providencia": (-33.4290, -70.6110),
    "Ñuñoa": (-33.4560, -70.5970),
    "Las Condes": (-33.4120, -70.5680),
    "Vitacura": (-33.3880, -70.5790),
    "Lo Barnechea": (-33.3550, -70.5180),
    "La Reina": (-33.4450, -70.5420),
    "Peñalolén": (-33.4850, -70.5520),
    "Macul": (-33.4900, -70.6000),
    "La Florida": (-33.5260, -70.5850),
    "Puente Alto": (-33.6050, -70.5760),
    "San Miguel": (-33.4970, -70.6510),
    "San Bernardo": (-33.5920, -70.7000),
    "Maipú": (-33.5110, -70.7560),
    "Estación Central": (-33.4600, -70.6950),
    "Independencia": (-33.4160, -70.6650),
    "Recoleta": (-33.4060, -70.6400),
    "Conchalí": (-33.3850, -70.6740),
    "Huechuraba": (-33.3720, -70.6390),
    "Quilicura": (-33.3640, -70.7300),
}

RADIO_TIERRA_KM = 6371.0
DESVIO_KM = 0.6          # desviación estándar del cliente respecto del centro de su comuna, por eje
FACTOR_RODEO = 1.35      # km por calle / km en línea recta
VELOCIDAD_KMH = 28.0     # velocidad urbana promedio
KM_POR_MINUTO = VELOCIDAD_KMH / 60

HORA_INICIO = 8          # el minuto 0 son las 08:00
CIERRE = 600             # el centro cierra a las 18:00 (600 minutos después)
SERVICIO = 8.0           # minutos por entrega
CAPACIDAD = 40           # bultos por camioneta
VEHICULOS = 15
DEMANDA_MAX = 6          # cada cliente pide entre 1 y 6 bultos

# Tipos de ventana: (nombre, apertura, cierre en minutos desde las 08:00, probabilidad).
VENTANAS = (("Mañana", 60, 300, 0.40),       # 09:00 a 13:00
            ("Tarde", 360, 600, 0.35),       # 14:00 a 18:00
            ("Todo el día", 60, 600, 0.25))  # 09:00 a 18:00


@dataclass
class CasoSantiago:
    inst: Instancia
    latlon: np.ndarray       # (n+1, 2) latitud y longitud; 0 = centro de distribución
    comunas: list[str]       # (n+1) comuna de cada punto; 0 = Pudahuel
    tipo_ventana: list[str]  # (n+1) "Mañana", "Tarde" o "Todo el día"; 0 = "Jornada"
    km_por_minuto: float = KM_POR_MINUTO

    def km(self, minutos: float) -> float:
        """Km aproximados recorridos en `minutos` de manejo."""
        return minutos * self.km_por_minuto

    def __iter__(self):
        """Permite desempacar `inst, latlon = crear_caso()`."""
        return iter((self.inst, self.latlon))


def km(minutos: float) -> float:
    """Km aproximados recorridos en `minutos` de manejo (a la velocidad promedio del caso)."""
    return minutos * KM_POR_MINUTO


def hora(minutos: float) -> str:
    """Minutos desde las 08:00 → hora del día "HH:MM" (se trunca al minuto)."""
    total = HORA_INICIO * 60 + math.floor(minutos + 1e-9)
    return f"{total // 60:02d}:{total % 60:02d}"


def haversine_km(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distancia en línea recta (km) entre cada punto de `a` y cada punto de `b` (lat, lon en grados)."""
    la1, lo1 = np.radians(a[:, 0])[:, None], np.radians(a[:, 1])[:, None]
    la2, lo2 = np.radians(b[:, 0])[None, :], np.radians(b[:, 1])[None, :]
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def minutos_de_viaje(latlon: np.ndarray) -> np.ndarray:
    """Tiempo de viaje en minutos: línea recta × rodeo a la velocidad promedio, truncado a un decimal."""
    minutos = haversine_km(latlon, latlon) * FACTOR_RODEO / VELOCIDAD_KMH * 60
    return np.floor(minutos * 10) / 10


def crear_caso(n_clientes: int = 40, semilla: int = 2026) -> CasoSantiago:
    """Genera el caso: clientes, ventanas, pedidos y la matriz de tiempos de viaje.

    La misma semilla da siempre el mismo caso. El resultado se puede desempacar como
    `inst, latlon = crear_caso(...)`; también trae la comuna y el tipo de ventana de cada cliente.
    """
    if n_clientes < 1:
        raise ValueError("Se necesita al menos un cliente.")
    rng = np.random.default_rng(semilla)
    nombres = list(COMUNAS)
    elegidas = [nombres[i] for i in rng.integers(len(nombres), size=n_clientes)]
    centros = np.array([COMUNAS[c] for c in elegidas])
    desvio = rng.normal(0.0, DESVIO_KM, size=(n_clientes, 2))  # km hacia el norte y hacia el este
    lat = centros[:, 0] + np.degrees(desvio[:, 0] / RADIO_TIERRA_KM)
    lon = centros[:, 1] + np.degrees(desvio[:, 1] / (RADIO_TIERRA_KM * np.cos(np.radians(centros[:, 0]))))
    latlon = np.vstack([DEPOSITO, np.column_stack([lat, lon])])
    minutos = minutos_de_viaje(latlon)

    tipos = rng.choice(len(VENTANAS), size=n_clientes, p=[v[3] for v in VENTANAS])
    demanda = np.concatenate([[0], rng.integers(1, DEMANDA_MAX + 1, size=n_clientes)])
    servicio = np.full(n_clientes + 1, SERVICIO)
    servicio[0] = 0.0
    inicio = np.zeros(n_clientes + 1)
    fin = np.full(n_clientes + 1, float(CIERRE))
    for c, k in enumerate(tipos, start=1):
        _, apertura, cierre, _ = VENTANAS[k]
        inicio[c] = apertura
        # Se recorta el cierre para que la camioneta alcance a entregar y volver antes de las 18:00.
        fin[c] = min(cierre, math.floor(CIERRE - SERVICIO - minutos[c, 0]))
    # Cada cliente debe poder atenderse solo (ir, entregar y volver a tiempo).
    if np.any(np.maximum(minutos[0, 1:], inicio[1:]) > fin[1:]):
        raise RuntimeError("Hay clientes que no se alcanzan a atender dentro de la jornada.")

    # Coordenadas planas en km respecto del centro de distribución (x al este, y al norte).
    lat0, lon0 = np.radians(DEPOSITO)
    coords = np.column_stack([
        (np.radians(latlon[:, 1]) - lon0) * RADIO_TIERRA_KM * math.cos(lat0),
        (np.radians(latlon[:, 0]) - lat0) * RADIO_TIERRA_KM])
    inst = Instancia(f"Santiago-{n_clientes}", CAPACIDAD, VEHICULOS, coords, demanda.astype(int),
                     inicio, fin, servicio, minutos)
    return CasoSantiago(inst, latlon, ["Pudahuel", *elegidas],
                        ["Jornada", *(VENTANAS[k][0] for k in tipos)])


def salida_y_horario(inst: Instancia, ruta: list[int]) -> tuple[float, list[dict]]:
    """Hora de salida del depósito y horario de una ruta, saliendo lo más tarde posible.

    `evaluacion.horario` supone que todas las camionetas salen en el minuto 0 y esperan en la
    puerta del cliente si llegan antes de que abra su ventana. Aquí la camioneta sale lo más
    tarde posible sin atrasar su regreso ni pasarse de ninguna ventana (holgura hacia adelante
    de Savelsbergh): la espera se hace en el depósito. La ruta, los minutos de manejo y la hora
    de regreso no cambian. La salida se trunca al minuto.

    Devuelve (salida, filas) con las mismas columnas que `evaluacion.horario`.
    """
    espera, holgura = 0.0, math.inf
    for f in horario(inst, ruta)[:-1]:
        espera += f["espera"]
        holgura = min(holgura, espera + inst.fin[f["cliente"]] - f["inicio"])
    salida = float(math.floor(min(espera, holgura) + 1e-9))
    t, previo, filas = salida, 0, []
    for c in [*ruta, 0]:
        llegada = t + inst.dist[previo, c]
        inicio = max(llegada, inst.inicio[c])
        filas.append({"cliente": c, "llegada": llegada, "inicio": inicio,
                      "fin": inicio + inst.servicio[c], "espera": inicio - llegada})
        t, previo = inicio + inst.servicio[c], c
    return salida, filas
