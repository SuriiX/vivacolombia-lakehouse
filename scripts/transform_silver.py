"""
scripts/transform_silver.py — Paso 3: Bronze → Silver.

Silver = datos limpios y tipados. NO hay reglas de negocio aquí (eso va en Gold).
Solo se resuelven nulos, tipos, duplicados, formatos inconsistentes y
filas inválidas (montos negativos, FKs huérfanas).

Genera además docs/reporte_calidad_silver.txt para el entregable de la rúbrica.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRONZE = PROJECT_ROOT / "lakehouse" / "bronze"
SILVER = PROJECT_ROOT / "lakehouse" / "silver"
DOCS   = PROJECT_ROOT / "docs"
SILVER.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)

REPORTE_PATH = DOCS / "reporte_calidad_silver.txt"

con = duckdb.connect()
reporte_lines: list[str] = []


def log(msg: str) -> None:
    print(msg)
    reporte_lines.append(msg)


# ─────────────────────────────────────────────────────────────────────


def _read_bronze(tabla: str) -> pd.DataFrame:
    return con.execute(
        f"SELECT * FROM read_parquet('{BRONZE}/{tabla}_latest.parquet')"
    ).fetchdf()


def _save_silver(df: pd.DataFrame, tabla: str) -> None:
    out = SILVER / f"{tabla}_silver.parquet"
    df.to_parquet(out, index=False)
    log(f"  ✓ {tabla:<14} {len(df):>8,} filas → {out.name}")


# ─────────────────────────────────────────────────────────────────────


def limpiar_rutas() -> None:
    df = _read_bronze("rutas")
    df["origen_iata"] = df["origen_iata"].str.upper().str.strip()
    df["destino_iata"] = df["destino_iata"].str.upper().str.strip()
    df = df.drop_duplicates(subset=["ruta_id"])
    _save_silver(df, "rutas")


def limpiar_canales() -> None:
    df = _read_bronze("canales")
    df["nombre"] = df["nombre"].str.upper().str.strip()
    df = df.drop_duplicates(subset=["canal_id"])
    _save_silver(df, "canales")


def limpiar_vuelos() -> None:
    df = _read_bronze("vuelos")
    df["fecha_vuelo"] = pd.to_datetime(df["fecha_vuelo"])
    df["aeronave"] = df["aeronave"].str.strip()
    df = df.dropna(subset=["vuelo_id", "ruta_id", "fecha_vuelo"])
    df = df.drop_duplicates(subset=["vuelo_id"])
    _save_silver(df, "vuelos")


def limpiar_pasajeros() -> None:
    df = _read_bronze("pasajeros")
    df["pais_residencia"] = df["pais_residencia"].str.upper().str.strip()
    df["segmento"] = df["segmento"].str.lower().str.strip()
    df["fecha_alta"] = pd.to_datetime(df["fecha_alta"])
    df = df.drop_duplicates(subset=["pasajero_id"])
    _save_silver(df, "pasajeros")


def limpiar_pagos() -> None:
    df = _read_bronze("pagos")
    df["medio_pago"] = df["medio_pago"].str.upper().str.strip()
    df["estado_pago"] = df["estado_pago"].str.upper().str.strip()
    df["monto"] = pd.to_numeric(df["monto"], errors="coerce")
    df = df.dropna(subset=["pago_id", "reserva_id", "monto"])
    df = df[df["monto"] > 0]
    df = df.drop_duplicates(subset=["pago_id"])
    _save_silver(df, "pagos")


def limpiar_reservas() -> tuple[int, int]:
    """Devuelve (filas_bronze, filas_silver) para el reporte de calidad."""
    df_raw = _read_bronze("reservas")
    n0 = len(df_raw)
    log(f"\n  Reservas Bronze cargadas: {n0:,}")

    df = df_raw.copy()

    # Tipos
    df["fecha_reserva"] = pd.to_datetime(df["fecha_reserva"])
    df["fecha_vuelo_pretendida"] = pd.to_datetime(df["fecha_vuelo_pretendida"])
    df["precio_pagado"] = pd.to_numeric(df["precio_pagado"], errors="coerce")
    df["asientos_reservados"] = pd.to_numeric(df["asientos_reservados"], errors="coerce", downcast="integer")
    df["descuento_aplicado"] = pd.to_numeric(df["descuento_aplicado"], errors="coerce").fillna(0.0)
    df["es_cancelada"] = pd.to_numeric(df["es_cancelada"], errors="coerce").fillna(0).astype(int)
    df["estado"] = df["estado"].str.upper().str.strip()

    # Resolución de nulos en canal_id (default a CALL_CENTER = 4 — el menos digital)
    n_nulos_canal = df["canal_id"].isna().sum()
    df["canal_id"] = df["canal_id"].fillna(4).astype(int)
    log(f"  • Nulos en canal_id resueltos: {n_nulos_canal:,} → default '4' (CALL_CENTER)")

    # Eliminar filas con FKs faltantes o monto inválido
    pre = len(df)
    df = df.dropna(subset=["reserva_id", "pasajero_id", "vuelo_id", "fecha_reserva", "precio_pagado"])
    log(f"  • Filas con FK/monto nulo eliminadas: {pre - len(df):,}")

    pre = len(df)
    df = df[df["precio_pagado"] > 0]
    log(f"  • Filas con precio ≤ 0 eliminadas:    {pre - len(df):,}")

    pre = len(df)
    df = df[df["dias_anticipacion"] >= 0]
    log(f"  • Filas con anticipación negativa:    {pre - len(df):,}")

    # Deduplicación
    pre = len(df)
    df = df.drop_duplicates(subset=["reserva_id"])
    log(f"  • Duplicados (reserva_id) eliminados: {pre - len(df):,}")

    _save_silver(df, "reservas")
    return n0, len(df)


# ─────────────────────────────────────────────────────────────────────


def main() -> None:
    log("=" * 60)
    log(f" SILVER  — limpieza y tipado   ({datetime.now():%Y-%m-%d %H:%M})")
    log("=" * 60)

    limpiar_rutas()
    limpiar_canales()
    limpiar_vuelos()
    limpiar_pasajeros()
    limpiar_pagos()
    n_bronze, n_silver = limpiar_reservas()

    pct_retenido = (n_silver / n_bronze) * 100 if n_bronze else 0
    monto_total = con.execute(
        f"SELECT SUM(precio_pagado) FROM read_parquet('{SILVER}/reservas_silver.parquet')"
    ).fetchone()[0]

    log("\n=== REPORTE DE CALIDAD SILVER ===")
    log(f"Filas Bronze (reservas)  : {n_bronze:>10,}")
    log(f"Filas Silver (reservas)  : {n_silver:>10,}")
    log(f"Filas eliminadas         : {n_bronze - n_silver:>10,}")
    log(f"Porcentaje retenido      : {pct_retenido:>9.1f}%")
    log(f"Monto total reservado    : ${monto_total:>16,.0f} COP")

    REPORTE_PATH.write_text("\n".join(reporte_lines), encoding="utf-8")
    print(f"\nReporte de calidad guardado en {REPORTE_PATH}")


if __name__ == "__main__":
    main()
