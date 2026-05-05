"""
scripts/benchmark.py — Paso 5b: Benchmark OLTP row-store vs Columnar.

Ejecuta la misma consulta agregada (volumen mensual) en:
  • SQLite — row-store local, proxy del OLTP (CockroachDB / PostgreSQL).
    SQLite NO es PostgreSQL, pero ambos son motores por filas; sirve como
    referencia honesta del costo de un agregado en row-store.
  • DuckDB — motor columnar embebido leyendo Parquet (Gold).

Nota didáctica: si tienen CockroachDB del Módulo 2 corriendo, fijen
COCKROACH_URL y descomentan el bloque indicado al final.

Salida: docs/benchmark_resultados.txt (insumo para README).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SILVER = PROJECT_ROOT / "lakehouse" / "silver"
GOLD   = PROJECT_ROOT / "lakehouse" / "gold"
DOCS   = PROJECT_ROOT / "docs"
DOCS.mkdir(parents=True, exist_ok=True)

OUT_REPORT = DOCS / "benchmark_resultados.txt"

REPEAT = 3            # promedio de 3 corridas (descartando primer warmup)
SQLITE_PATH = "/tmp/vivacolombia_oltp.db"


# ─────────────────────────────────────────────────────────────────────


def cargar_sqlite_desde_silver() -> None:
    """Crea SQLite y le carga las reservas Silver para simular el OLTP."""
    Path(SILVER / "reservas_silver.parquet").exists()
    df = duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{SILVER}/reservas_silver.parquet')"
    ).fetchdf()
    # SQLite no maneja datetimes en parquet directo — castear a string ISO
    df["fecha_reserva"] = pd.to_datetime(df["fecha_reserva"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    df["fecha_vuelo_pretendida"] = pd.to_datetime(df["fecha_vuelo_pretendida"]).dt.strftime("%Y-%m-%d")
    conn = sqlite3.connect(SQLITE_PATH)
    df.to_sql("reservas", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fecha ON reservas(fecha_reserva)")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM reservas").fetchone()[0]
    conn.close()
    print(f"  SQLite cargado: {n:,} reservas en {SQLITE_PATH}")


def medir_sqlite(query: str) -> tuple[float, int]:
    conn = sqlite3.connect(SQLITE_PATH)
    times = []
    rows = 0
    for i in range(REPEAT + 1):
        t0 = time.perf_counter()
        cur = conn.execute(query)
        result = cur.fetchall()
        elapsed = (time.perf_counter() - t0) * 1000
        if i > 0:                  # descartar warmup
            times.append(elapsed)
        rows = len(result)
    conn.close()
    return sum(times) / len(times), rows


def medir_duckdb(query: str, con: duckdb.DuckDBPyConnection) -> tuple[float, int]:
    times = []
    rows = 0
    for i in range(REPEAT + 1):
        t0 = time.perf_counter()
        df = con.execute(query).fetchdf()
        elapsed = (time.perf_counter() - t0) * 1000
        if i > 0:
            times.append(elapsed)
        rows = len(df)
    return sum(times) / len(times), rows


# ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print(" BENCHMARK — SQLite (row-store, proxy OLTP) vs DuckDB (columnar)")
    print("=" * 70)
    print(f"  REPEAT={REPEAT} (promedio sin warmup)")

    cargar_sqlite_desde_silver()

    con = duckdb.connect()
    con.execute(
        f"CREATE OR REPLACE VIEW fact_reservas AS "
        f"SELECT * FROM read_parquet('{GOLD}/fact_reservas.parquet')"
    )
    con.execute(
        f"CREATE OR REPLACE VIEW dim_tiempo AS "
        f"SELECT * FROM read_parquet('{GOLD}/dim_tiempo.parquet')"
    )

    # ── Query A — agregado mensual (clásico OLAP) ────────────────────
    Q_SQLITE_A = """
        SELECT strftime('%Y', fecha_reserva)  AS anio,
               strftime('%m', fecha_reserva)  AS mes,
               COUNT(*)                       AS reservas,
               SUM(precio_pagado)             AS ingresos
        FROM reservas
        WHERE estado = 'CONFIRMADA'
        GROUP BY anio, mes
        ORDER BY anio, mes
    """
    Q_DUCKDB_A = """
        SELECT t.anio, t.mes,
               COUNT(*)                AS reservas,
               SUM(f.precio_pagado)    AS ingresos
        FROM fact_reservas f
        JOIN dim_tiempo    t ON f.tiempo_sk = t.tiempo_sk
        WHERE f.es_cancelada = 0
        GROUP BY t.anio, t.mes
        ORDER BY t.anio, t.mes
    """

    # ── Query B — full-scan agregando solo dos columnas ─────────────
    Q_SQLITE_B = "SELECT COUNT(*), SUM(precio_pagado) FROM reservas"
    Q_DUCKDB_B = "SELECT COUNT(*), SUM(precio_pagado) FROM fact_reservas"

    resultados = []
    for label, q_sqlite, q_duckdb in [
        ("Agregado mensual (group by)", Q_SQLITE_A, Q_DUCKDB_A),
        ("Full-scan COUNT+SUM",          Q_SQLITE_B, Q_DUCKDB_B),
    ]:
        t_sql, n_sql = medir_sqlite(q_sqlite)
        t_dk,  n_dk  = medir_duckdb(q_duckdb, con)
        factor = t_sql / t_dk if t_dk > 0 else float("inf")
        resultados.append((label, t_sql, n_sql, t_dk, n_dk, factor))

    # ── Reporte ──────────────────────────────────────────────────────
    lines = []
    lines.append(f"{'Query':45} {'SQLite (ms)':>14} {'DuckDB (ms)':>14} {'Factor':>10}")
    lines.append("-" * 90)
    for label, t_sql, n_sql, t_dk, n_dk, factor in resultados:
        lines.append(f"{label:45} {t_sql:>14.2f} {t_dk:>14.2f} {factor:>9.2f}x")

    text = "\n".join(lines)
    print("\n" + text)
    OUT_REPORT.write_text(text + "\n", encoding="utf-8")
    print(f"\nReporte guardado en {OUT_REPORT}")

    # ── Análisis honesto ─────────────────────────────────────────────
    print("\n--- Lectura honesta del resultado ---")
    print(
        "Con ~200K filas y un dataset que cabe en RAM, la diferencia es \n"
        "moderada — DuckDB suele ganar 2-10x en queries con muchos GROUP BY.\n"
        "El beneficio columnar se dispara con datasets más grandes (>1M filas)\n"
        "y queries que escanean muchas filas pero pocas columnas, porque \n"
        "Parquet solo lee las columnas referenciadas y aprovecha compresión."
    )

    # ── BLOQUE OPCIONAL para CockroachDB real ────────────────────────
    # Si tienen el cluster del Módulo 2 corriendo, descomenten esto:
    #
    # import os
    # from sqlalchemy import create_engine
    # url = os.environ.get("COCKROACH_URL")
    # if url:
    #     engine = create_engine(url)
    #     t0 = time.perf_counter()
    #     pd.read_sql("SELECT EXTRACT(YEAR FROM fecha_reserva) y, "
    #                 "EXTRACT(MONTH FROM fecha_reserva) m, COUNT(*), SUM(precio_pagado) "
    #                 "FROM reservas WHERE estado='CONFIRMADA' GROUP BY 1,2", engine)
    #     print(f"CockroachDB real: {(time.perf_counter()-t0)*1000:.2f} ms")


if __name__ == "__main__":
    main()
