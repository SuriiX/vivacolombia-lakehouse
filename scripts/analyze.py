"""
scripts/analyze.py — Paso 5a: 5 consultas analíticas sobre Gold con DuckDB.

Cada consulta mide su tiempo de ejecución (ms) y muestra resultados.
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD = PROJECT_ROOT / "lakehouse" / "gold"


def _setup_views(con: duckdb.DuckDBPyConnection) -> None:
    for tabla in ("fact_reservas", "dim_tiempo", "dim_vuelo", "dim_ruta",
                  "dim_canal", "dim_pasajero"):
        con.execute(
            f"CREATE OR REPLACE VIEW {tabla} AS "
            f"SELECT * FROM read_parquet('{GOLD}/{tabla}.parquet')"
        )


QUERIES: dict[str, str] = {
    "Q1 — Ingresos y reservas por mes y trimestre": """
        SELECT t.anio, t.trimestre, t.mes, t.mes_nombre,
               COUNT(*)                            AS reservas,
               SUM(f.precio_pagado)                AS ingresos_cop,
               AVG(f.precio_pagado)                AS ticket_promedio,
               SUM(f.es_cancelada)                 AS canceladas,
               ROUND(SUM(f.es_cancelada)*100.0/COUNT(*), 2) AS tasa_cancel_pct
        FROM fact_reservas f
        JOIN dim_tiempo t ON f.tiempo_sk = t.tiempo_sk
        GROUP BY t.anio, t.trimestre, t.mes, t.mes_nombre
        ORDER BY t.anio, t.mes
    """,
    "Q2 — Ocupación % por ruta (últimos 12 meses)": """
        WITH reservas_por_ruta AS (
            SELECT r.ruta_id, r.origen_iata, r.destino_iata,
                   r.internacional_flag,
                   SUM(f.asientos_reservados) AS asientos_vendidos
            FROM fact_reservas f
            JOIN dim_ruta   r ON f.ruta_sk   = r.ruta_sk
            JOIN dim_tiempo t ON f.tiempo_sk = t.tiempo_sk
            WHERE t.fecha >= DATE '2025-05-01'
              AND f.es_cancelada = 0
            GROUP BY r.ruta_id, r.origen_iata, r.destino_iata, r.internacional_flag
        ),
        capacidad_por_ruta AS (
            SELECT v.ruta_id, SUM(v.capacidad_asientos) AS asientos_disponibles
            FROM dim_vuelo  v
            JOIN dim_tiempo t ON DATE_TRUNC('day', v.fecha_vuelo) = t.fecha
            WHERE t.fecha >= DATE '2025-05-01'
            GROUP BY v.ruta_id
        )
        SELECT r.origen_iata || '→' || r.destino_iata AS ruta,
               r.internacional_flag,
               r.asientos_vendidos,
               c.asientos_disponibles,
               ROUND(r.asientos_vendidos * 100.0 / c.asientos_disponibles, 1) AS ocupacion_pct
        FROM reservas_por_ruta r
        JOIN capacidad_por_ruta c USING (ruta_id)
        ORDER BY ocupacion_pct DESC
    """,
    "Q3 — Conversión por canal (confirmadas vs canceladas)": """
        SELECT c.nombre AS canal, c.digital_flag,
               COUNT(*)                            AS total_reservas,
               SUM(1 - f.es_cancelada)             AS confirmadas,
               SUM(f.es_cancelada)                 AS canceladas,
               ROUND(SUM(1 - f.es_cancelada)*100.0/COUNT(*), 2) AS conversion_pct,
               SUM(f.precio_pagado)                AS ingresos_cop
        FROM fact_reservas f
        JOIN dim_canal c ON f.canal_sk = c.canal_sk
        GROUP BY c.nombre, c.digital_flag
        ORDER BY ingresos_cop DESC
    """,
    "Q4 — Ventana media de reserva por temporada y segmento": """
        SELECT t.es_temporada_alta,
               p.segmento,
               COUNT(*)                       AS reservas,
               ROUND(AVG(f.dias_anticipacion), 1) AS dias_anticipacion_avg,
               ROUND(AVG(f.precio_pagado), 0)  AS ticket_promedio
        FROM fact_reservas f
        JOIN dim_tiempo    t ON f.tiempo_sk    = t.tiempo_sk
        JOIN dim_pasajero  p ON f.pasajero_sk  = p.pasajero_sk
        WHERE f.es_cancelada = 0
        GROUP BY t.es_temporada_alta, p.segmento
        ORDER BY t.es_temporada_alta DESC, dias_anticipacion_avg DESC
    """,
    "Q5 — Picos de reserva por día de la semana × hora del día": """
        SELECT t.dia_nombre,
               EXTRACT(HOUR FROM f.fecha_reserva) AS hora,
               COUNT(*) AS reservas
        FROM fact_reservas f
        JOIN dim_tiempo t ON f.tiempo_sk = t.tiempo_sk
        WHERE t.dia_semana IN (0, 4, 5, 6)         -- lun, vie, sab, dom
        GROUP BY t.dia_nombre, hora
        ORDER BY reservas DESC
        LIMIT 15
    """,
}


def main() -> None:
    print("=" * 70)
    print(" ANALYZE — 5 consultas analíticas sobre Gold (DuckDB)")
    print("=" * 70)

    con = duckdb.connect()
    _setup_views(con)

    for nombre, sql in QUERIES.items():
        t0 = time.perf_counter()
        df = con.execute(sql).fetchdf()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"\n>>> {nombre}   [{elapsed_ms:7.1f} ms · {len(df)} filas]")
        # Imprimir compacto: head 12 filas para no saturar consola
        with_pad = df.head(12).to_string(index=False)
        print(with_pad)
        if len(df) > 12:
            print(f"... ({len(df) - 12} filas más omitidas)")

    print("\nAnálisis completo.")


if __name__ == "__main__":
    main()
