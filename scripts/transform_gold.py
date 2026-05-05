"""
scripts/transform_gold.py — Paso 4: Silver → Gold (modelo estrella).

Construye el modelo dimensional documentado en docs/diseno_dimensional.md:

  • DIM_TIEMPO     (Tipo 0)
  • DIM_VUELO      (Tipo 1)
  • DIM_RUTA       (Tipo 1)
  • DIM_CANAL      (Tipo 1)
  • DIM_PASAJERO   (Tipo 2 — SCD con valido_desde / valido_hasta / activo)
  • FACT_RESERVAS  (granularidad: 1 reserva confirmada o cancelada)

DuckDB lee directo los Parquet resultantes para el Paso 5 de análisis.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SILVER = PROJECT_ROOT / "lakehouse" / "silver"
GOLD   = PROJECT_ROOT / "lakehouse" / "gold"
GOLD.mkdir(parents=True, exist_ok=True)

con = duckdb.connect()

SCD2_CHANGE_PCT = 0.15  # ~15% de pasajeros tienen cambio de segmento (para mostrar SCD2)
SEED = 42


def _read_silver(tabla: str) -> pd.DataFrame:
    return con.execute(
        f"SELECT * FROM read_parquet('{SILVER}/{tabla}_silver.parquet')"
    ).fetchdf()


def _save_gold(df: pd.DataFrame, tabla: str) -> None:
    out = GOLD / f"{tabla}.parquet"
    df.to_parquet(out, index=False)
    print(f"  ✓ {tabla:<22} {len(df):>8,} filas → {out.name}")


# ─────────────────────────────────────────────────────────────────────
# DIM_TIEMPO
# ─────────────────────────────────────────────────────────────────────


def construir_dim_tiempo(reservas: pd.DataFrame, vuelos: pd.DataFrame) -> pd.DataFrame:
    fmin = min(reservas["fecha_reserva"].min(), vuelos["fecha_vuelo"].min())
    fmax = max(reservas["fecha_vuelo_pretendida"].max(), vuelos["fecha_vuelo"].max())
    fechas = pd.date_range(start=fmin.normalize(), end=fmax.normalize(), freq="D")

    dim = pd.DataFrame({
        "tiempo_sk":       range(1, len(fechas) + 1),
        "fecha":           fechas,
        "anio":            fechas.year,
        "trimestre":       fechas.quarter,
        "mes":             fechas.month,
        "mes_nombre":      fechas.strftime("%B"),
        "dia":             fechas.day,
        "dia_semana":      fechas.dayofweek,            # 0 = lunes
        "dia_nombre":      fechas.strftime("%A"),
        "es_fin_semana":   fechas.dayofweek >= 5,
        "es_temporada_alta": fechas.month.isin([1, 7, 12]),
    })
    return dim


# ─────────────────────────────────────────────────────────────────────
# DIM_VUELO, DIM_RUTA, DIM_CANAL  (Tipo 1)
# ─────────────────────────────────────────────────────────────────────


def construir_dim_vuelo(vuelos: pd.DataFrame) -> pd.DataFrame:
    dim = vuelos[[
        "vuelo_id", "numero_vuelo", "ruta_id", "fecha_vuelo",
        "aeronave", "capacidad_asientos", "aerolinea",
    ]].copy()
    dim.insert(0, "vuelo_sk", range(1, len(dim) + 1))
    return dim


def construir_dim_ruta(rutas: pd.DataFrame) -> pd.DataFrame:
    dim = rutas[[
        "ruta_id", "origen_iata", "origen_ciudad",
        "destino_iata", "destino_ciudad", "distancia_km", "internacional_flag",
    ]].copy()
    dim.insert(0, "ruta_sk", range(1, len(dim) + 1))
    return dim


def construir_dim_canal(canales: pd.DataFrame) -> pd.DataFrame:
    dim = canales[["canal_id", "nombre", "digital_flag", "categoria"]].copy()
    dim.insert(0, "canal_sk", range(1, len(dim) + 1))
    return dim


# ─────────────────────────────────────────────────────────────────────
# DIM_PASAJERO con SCD Tipo 2
# ─────────────────────────────────────────────────────────────────────


def construir_dim_pasajero_scd2(pasajeros: pd.DataFrame) -> pd.DataFrame:
    """
    Materializa SCD Tipo 2.

    Para ~SCD2_CHANGE_PCT de los pasajeros simulamos un cambio de segmento
    (ocasional → frecuente, nuevo → ocasional) en una fecha intermedia.
    Esto deja registros con dos versiones para evidenciar el SCD2 en queries.
    """
    rng = np.random.default_rng(SEED)
    base = pasajeros.copy()

    # Versión inicial: vigente desde fecha-base del DW (anterior a cualquier
    # operación del sistema) hasta 9999-12-31. Esto evita huérfanos cuando una
    # reserva es anterior a la fecha_alta sintética (caso académico).
    DW_EPOCH = pd.Timestamp("2020-01-01")
    v1 = base[["pasajero_id", "segmento", "pais_residencia", "fecha_alta"]].copy()
    v1["valido_desde"] = DW_EPOCH
    v1["valido_hasta"] = pd.Timestamp("9999-12-31")
    v1["activo"] = True

    # Pasajeros que cambian: 15% al azar de los que NO son ya 'frecuente'
    cambiables = base[base["segmento"] != "frecuente"]
    n_cambios = int(len(cambiables) * SCD2_CHANGE_PCT)
    ids_cambian = rng.choice(cambiables["pasajero_id"].values, size=n_cambios, replace=False)

    # Fecha del cambio: aleatoria entre fecha_alta + 90 días y 2026-04-30
    map_alta = base.set_index("pasajero_id")["fecha_alta"].to_dict()
    fechas_cambio = []
    for pid in ids_cambian:
        f0 = map_alta[pid] + pd.Timedelta(days=90)
        f1 = pd.Timestamp("2026-04-30")
        if f0 >= f1:
            fechas_cambio.append(f0)
        else:
            delta_days = (f1 - f0).days
            fechas_cambio.append(f0 + pd.Timedelta(days=int(rng.integers(0, delta_days))))
    df_cambios = pd.DataFrame({"pasajero_id": ids_cambian, "fecha_cambio": fechas_cambio})

    # Cerrar la versión 1 de los que cambian
    v1 = v1.merge(df_cambios, on="pasajero_id", how="left")
    cambian_mask = v1["fecha_cambio"].notna()
    v1.loc[cambian_mask, "valido_hasta"] = v1.loc[cambian_mask, "fecha_cambio"] - pd.Timedelta(days=1)
    v1.loc[cambian_mask, "activo"] = False
    v1 = v1.drop(columns=["fecha_cambio"])

    # Versión 2 de los que cambian (segmento promovido)
    promocion = {"nuevo": "ocasional", "ocasional": "frecuente"}
    v2_base = base[base["pasajero_id"].isin(ids_cambian)].copy()
    v2_base = v2_base.merge(df_cambios, on="pasajero_id")
    v2 = v2_base[["pasajero_id", "pais_residencia", "fecha_cambio"]].copy()
    v2["segmento"] = v2_base["segmento"].map(promocion).fillna("frecuente")
    v2["fecha_alta"] = v2_base["fecha_alta"]   # se conserva original
    v2["valido_desde"] = v2_base["fecha_cambio"]
    v2["valido_hasta"] = pd.Timestamp("9999-12-31")
    v2["activo"] = True

    dim = pd.concat([v1, v2], ignore_index=True)
    dim = dim.sort_values(["pasajero_id", "valido_desde"]).reset_index(drop=True)
    dim.insert(0, "pasajero_sk", range(1, len(dim) + 1))

    cols = [
        "pasajero_sk", "pasajero_id", "segmento", "pais_residencia",
        "fecha_alta", "valido_desde", "valido_hasta", "activo",
    ]
    return dim[cols]


# ─────────────────────────────────────────────────────────────────────
# FACT_RESERVAS
# ─────────────────────────────────────────────────────────────────────


def construir_fact(
    reservas: pd.DataFrame,
    dim_tiempo: pd.DataFrame,
    dim_vuelo: pd.DataFrame,
    dim_ruta: pd.DataFrame,
    dim_canal: pd.DataFrame,
    dim_pasajero: pd.DataFrame,
    vuelos: pd.DataFrame,
) -> pd.DataFrame:

    fact = reservas.copy()
    fact["fecha_solo"] = fact["fecha_reserva"].dt.normalize()

    # Lookup tiempo_sk (por fecha de reserva)
    fact = fact.merge(
        dim_tiempo[["tiempo_sk", "fecha"]],
        left_on="fecha_solo", right_on="fecha", how="left",
    ).drop(columns=["fecha"])

    # Lookup vuelo_sk
    fact = fact.merge(
        dim_vuelo[["vuelo_sk", "vuelo_id"]],
        on="vuelo_id", how="left",
    )

    # Lookup ruta_sk (vía vuelo → ruta_id)
    vuelo_to_ruta = vuelos.set_index("vuelo_id")["ruta_id"].to_dict()
    fact["ruta_id"] = fact["vuelo_id"].map(vuelo_to_ruta)
    fact = fact.merge(
        dim_ruta[["ruta_sk", "ruta_id"]],
        on="ruta_id", how="left",
    )

    # Lookup canal_sk
    fact = fact.merge(
        dim_canal[["canal_sk", "canal_id"]],
        on="canal_id", how="left",
    )

    # Lookup pasajero_sk respetando SCD2 (versión activa AT fecha_reserva)
    # Estrategia eficiente: hacer un merge con la versión activa cuya
    # ventana [valido_desde, valido_hasta] contenga fecha_reserva.
    pasaj = dim_pasajero[["pasajero_sk", "pasajero_id", "valido_desde", "valido_hasta"]].copy()
    fact_with_pas = fact[["reserva_id", "pasajero_id", "fecha_reserva"]].merge(
        pasaj, on="pasajero_id", how="left",
    )
    valid_mask = (
        (fact_with_pas["fecha_reserva"] >= fact_with_pas["valido_desde"])
        & (fact_with_pas["fecha_reserva"] <= fact_with_pas["valido_hasta"])
    )
    fact_with_pas = fact_with_pas[valid_mask][["reserva_id", "pasajero_sk"]]
    fact = fact.merge(fact_with_pas, on="reserva_id", how="left")

    # Construir tabla final con SOLO claves surrogadas + métricas
    fact_final = fact[[
        "reserva_id",
        "tiempo_sk", "vuelo_sk", "ruta_sk", "pasajero_sk", "canal_sk",
        "fecha_reserva", "fecha_vuelo_pretendida",
        "precio_pagado", "asientos_reservados", "descuento_aplicado",
        "dias_anticipacion", "es_cancelada",
    ]].copy()

    # Validar integridad referencial — alarma temprana
    n_orfanos = fact_final[
        fact_final[["tiempo_sk", "vuelo_sk", "ruta_sk", "pasajero_sk", "canal_sk"]].isna().any(axis=1)
    ].shape[0]
    if n_orfanos > 0:
        print(f"  ⚠ {n_orfanos:,} filas con SK NULL — revisar dimensiones")
        fact_final = fact_final.dropna(
            subset=["tiempo_sk", "vuelo_sk", "ruta_sk", "pasajero_sk", "canal_sk"]
        )
    return fact_final


# ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 60)
    print(f" GOLD — modelo dimensional   ({datetime.now():%Y-%m-%d %H:%M})")
    print("=" * 60)

    reservas  = _read_silver("reservas")
    vuelos    = _read_silver("vuelos")
    rutas     = _read_silver("rutas")
    canales   = _read_silver("canales")
    pasajeros = _read_silver("pasajeros")

    dim_tiempo    = construir_dim_tiempo(reservas, vuelos)
    _save_gold(dim_tiempo, "dim_tiempo")

    dim_vuelo     = construir_dim_vuelo(vuelos)
    _save_gold(dim_vuelo, "dim_vuelo")

    dim_ruta      = construir_dim_ruta(rutas)
    _save_gold(dim_ruta, "dim_ruta")

    dim_canal     = construir_dim_canal(canales)
    _save_gold(dim_canal, "dim_canal")

    dim_pasajero  = construir_dim_pasajero_scd2(pasajeros)
    _save_gold(dim_pasajero, "dim_pasajero")

    fact = construir_fact(
        reservas, dim_tiempo, dim_vuelo, dim_ruta, dim_canal, dim_pasajero, vuelos
    )
    _save_gold(fact, "fact_reservas")

    # Stats SCD2
    n_pasajeros_unicos = dim_pasajero["pasajero_id"].nunique()
    n_filas_dim = len(dim_pasajero)
    n_con_dos_versiones = (
        dim_pasajero.groupby("pasajero_id").size().pipe(lambda s: (s > 1).sum())
    )
    print(
        f"\n  SCD2 dim_pasajero: {n_pasajeros_unicos:,} pasajeros únicos · "
        f"{n_filas_dim:,} filas totales · "
        f"{n_con_dos_versiones:,} con ≥2 versiones históricas"
    )
    print("\nGold completo en", GOLD)


if __name__ == "__main__":
    main()
