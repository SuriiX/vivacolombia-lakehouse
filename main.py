"""
main.py — Pipeline completo del Mini-Lakehouse VivaColombia.

Ejecutar desde la raíz del proyecto:

    python main.py

Lee variables de entorno opcionales:
    EXTRACT_MODE=synthetic|cockroach   (default: synthetic)
    N_RESERVAS=<int>                   (default: 500000)
    DB_URL=<postgresql://...>          (solo si EXTRACT_MODE=cockroach)
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PASOS = [
    ("Extracción → Bronze",      "scripts/extract.py"),
    ("Limpieza   → Silver",      "scripts/transform_silver.py"),
    ("Modelado   → Gold",        "scripts/transform_gold.py"),
    ("Análisis   (5 queries)",   "scripts/analyze.py"),
    ("Benchmark  (OLTP vs cols)", "scripts/benchmark.py"),
]


def main() -> int:
    print("=" * 70)
    print("   MINI-LAKEHOUSE VivaColombia · Pipeline reproducible")
    print("=" * 70)
    t_total = time.perf_counter()

    for nombre, script in PASOS:
        print(f"\n>>> {nombre}")
        t0 = time.perf_counter()
        result = subprocess.run([sys.executable, str(ROOT / script)])
        if result.returncode != 0:
            print(f"\n✘ ERROR en {script}. Pipeline detenido.")
            return result.returncode
        print(f"  ↳ completado en {time.perf_counter() - t0:.1f}s")

    print("\n" + "=" * 70)
    print(f" Pipeline completo en {time.perf_counter() - t_total:.1f}s")
    print(f" Archivos Gold disponibles en: {ROOT / 'lakehouse' / 'gold'}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
