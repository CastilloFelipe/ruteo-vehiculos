"""Descarga las 56 instancias VRPTW de Solomon y sus mejores soluciones conocidas.

    python scripts/descargar_solomon.py

Fuente: repositorio PyVRP/Instances (https://github.com/PyVRP/Instances), que distribuye
las instancias originales de Solomon (1987) y las mejores soluciones conocidas publicadas.
Los archivos quedan en data/solomon/ y se versionan (pesan ~200 KB en total).
"""
import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/PyVRP/Instances/main/VRPTW/Solomon/"
DESTINO = Path(__file__).resolve().parents[1] / "data" / "solomon"
FAMILIAS = {"C1": 9, "C2": 8, "R1": 12, "R2": 11, "RC1": 8, "RC2": 8}


def nombres() -> list[str]:
    return [f"{f}{i:02d}" for f, n in FAMILIAS.items() for i in range(1, n + 1)]


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre in nombres():
        for ext in (".vrp", ".sol"):
            ruta = DESTINO / f"{nombre}{ext}"
            if ruta.exists():
                continue
            try:
                with urllib.request.urlopen(BASE + nombre + ext, timeout=30) as r:
                    ruta.write_bytes(r.read())
            except Exception as e:  # noqa: BLE001
                sys.exit(f"No se pudo descargar {nombre}{ext}: {e}")
    print(f"{len(nombres())} instancias en {DESTINO}")


if __name__ == "__main__":
    main()
