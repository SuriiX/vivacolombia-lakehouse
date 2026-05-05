"""
scripts/persist_for_metabase.py — Paso 7 (Alternativa B).

Materializa la capa Gold en un archivo DuckDB persistente
(lakehouse/analytics.duckdb) para que Metabase Community se conecte vía
JDBC al archivo y construya dashboards sobre el modelo dimensional.

Cómo correr Metabase apuntando a este archivo:
  docker run -d -p 3000:3000 \\
      -v $(pwd)/lakehouse:/lakehouse \\
      metabase/metabase

Luego en http://localhost:3000:
  Add database → DuckDB → File path: /lakehouse/analytics.duckdb
"""

from __future__ import annotations

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD = PROJECT_ROOT / "lakehouse" / "gold"
DB_PATH = PROJECT_ROOT / "lakehouse" / "analytics.duckdb"

# Borramos cualquier archivo previo para que sea idempotente
if DB_PATH.exists():
    DB_PATH.unlink()

con = duckdb.connect(str(DB_PATH))

TABLAS = ["fact_reservas", "dim_tiempo", "dim_vuelo", "dim_ruta", "dim_canal", "dim_pasajero"]
print(f"Persistiendo Gold en {DB_PATH}")
for t in TABLAS:
    con.execute(
        f"CREATE OR REPLACE TABLE {t} AS "
        f"SELECT * FROM read_parquet('{GOLD}/{t}.parquet')"
    )
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  ✓ {t:<22} {n:>10,} filas")

# Vista helper para Metabase: reservas confirmadas con todos los joins ya hechos
con.execute("""
CREATE OR REPLACE VIEW v_reservas_full AS
SELECT
    f.reserva_id, f.precio_pagado, f.asientos_reservados, f.descuento_aplicado,
    f.dias_anticipacion, f.es_cancelada,
    t.fecha, t.anio, t.mes, t.mes_nombre, t.dia_nombre, t.es_temporada_alta,
    v.numero_vuelo, v.aeronave, v.capacidad_asientos,
    r.origen_iata, r.destino_iata, r.internacional_flag,
    r.origen_iata || '→' || r.destino_iata AS ruta,
    p.segmento, p.pais_residencia,
    c.nombre AS canal, c.digital_flag
FROM fact_reservas f
JOIN dim_tiempo    t ON f.tiempo_sk    = t.tiempo_sk
JOIN dim_vuelo     v ON f.vuelo_sk     = v.vuelo_sk
JOIN dim_ruta      r ON f.ruta_sk      = r.ruta_sk
JOIN dim_pasajero  p ON f.pasajero_sk  = p.pasajero_sk
JOIN dim_canal     c ON f.canal_sk     = c.canal_sk
""")
print("  ✓ v_reservas_full (vista para Metabase)")
con.close()
print(f"\nListo. Apunten Metabase al archivo: {DB_PATH}")
