"""
scripts/extract.py — Paso 2: Extracción a la zona Bronze.

Modo de operación:
  • EXTRACT_MODE=cockroach  → lee desde CockroachDB usando DB_URL
  • EXTRACT_MODE=synthetic  → genera datos sintéticos representativos
                              del dominio VivaColombia (default si no hay DB)

Bronze es inmutable: cada corrida deja archivos timestampeados en
  lakehouse/bronze/<tabla>_<YYYYMMDD_HHMM>.parquet
junto con un alias <tabla>_latest.parquet que apunta al más reciente.

Equipo: Juan Pablo Cañas Sepúlveda · Owen David Pérez Sánchez
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRONZE = PROJECT_ROOT / "lakehouse" / "bronze"
BRONZE.mkdir(parents=True, exist_ok=True)

EXTRACT_MODE = os.environ.get("EXTRACT_MODE", "synthetic").lower()
DB_URL = os.environ.get(
    "DB_URL",
    "postgresql://root@localhost:26257/vivacolombia_db?sslmode=disable",
)
N_RESERVAS = int(os.environ.get("N_RESERVAS", "500000"))
SEED = int(os.environ.get("SYNTH_SEED", "42"))

FECHA_EXTRACCION = datetime.now()
SUFFIX = FECHA_EXTRACCION.strftime("%Y%m%d_%H%M")

# Catálogo de rutas de VivaColombia (datos realistas del dominio)
RUTAS_CATALOG = [
    # (origen_iata, origen_ciudad, destino_iata, destino_ciudad, distancia_km, internacional)
    ("BOG", "Bogotá",       "MDE", "Medellín",     245,  False),
    ("BOG", "Bogotá",       "CTG", "Cartagena",    657,  False),
    ("BOG", "Bogotá",       "CLO", "Cali",         289,  False),
    ("BOG", "Bogotá",       "BAQ", "Barranquilla", 700,  False),
    ("BOG", "Bogotá",       "SMR", "Santa Marta",  705,  False),
    ("BOG", "Bogotá",       "MIA", "Miami",        2440, True),
    ("MDE", "Medellín",     "CTG", "Cartagena",    540,  False),
    ("MDE", "Medellín",     "MIA", "Miami",        2280, True),
    ("MDE", "Medellín",     "CLO", "Cali",         330,  False),
    ("CLO", "Cali",         "MIA", "Miami",        2580, True),
    ("CTG", "Cartagena",    "MIA", "Miami",        1660, True),
    ("BOG", "Bogotá",       "MEX", "Ciudad de México", 3160, True),
]

CANALES_CATALOG = [
    # (canal_id, nombre, digital_flag, categoria)
    (1, "WEB",         True,  "online"),
    (2, "APP_MOVIL",   True,  "online"),
    (3, "AGENCIA",     False, "presencial"),
    (4, "CALL_CENTER", False, "telefonico"),
    (5, "AEROPUERTO",  False, "presencial"),
]

AERONAVES = ["A320", "A319", "A320neo"]
AEROLINEA = "VivaColombia"
SEGMENTOS = ["nuevo", "ocasional", "frecuente"]
SEGMENTO_PROBS = [0.30, 0.55, 0.15]
PAISES_RESIDENCIA = ["CO", "US", "MX", "VE", "EC", "PE", "ES"]
PAIS_PROBS        = [0.78, 0.10, 0.04, 0.03, 0.02, 0.02, 0.01]

# ─────────────────────────────────────────────────────────────────────
# Helpers comunes
# ─────────────────────────────────────────────────────────────────────


def _save_bronze(df: pd.DataFrame, nombre: str) -> Path:
    """Guarda con timestamp y crea/actualiza alias _latest.parquet."""
    df = df.copy()
    df["_extraido_en"] = FECHA_EXTRACCION
    df["_fuente"] = EXTRACT_MODE
    timestamped = BRONZE / f"{nombre}_{SUFFIX}.parquet"
    latest = BRONZE / f"{nombre}_latest.parquet"
    df.to_parquet(timestamped, index=False)
    shutil.copyfile(timestamped, latest)
    print(f"  ✓ {nombre:<22} {len(df):>8,} filas → {timestamped.name}")
    return timestamped


# ─────────────────────────────────────────────────────────────────────
# Modo 1: extracción real desde CockroachDB
# ─────────────────────────────────────────────────────────────────────


def extraer_cockroach() -> None:
    """Extrae las tablas operacionales del módulo VivaColombia."""
    from sqlalchemy import create_engine

    print(f"[CockroachDB] conectando a {DB_URL.split('@')[-1]}")
    engine = create_engine(DB_URL)

    queries = {
        "rutas":      "SELECT * FROM rutas",
        "vuelos":     "SELECT * FROM vuelos",
        "canales":    "SELECT * FROM canales",
        "pasajeros":  "SELECT * FROM pasajeros",
        "reservas":   "SELECT * FROM reservas",
        "pagos":      "SELECT * FROM pagos",
    }
    for nombre, sql in queries.items():
        df = pd.read_sql(sql, engine)
        _save_bronze(df, nombre)


# ─────────────────────────────────────────────────────────────────────
# Modo 2: generación sintética (Plan B oficial — sección 5.3 de la guía)
# ─────────────────────────────────────────────────────────────────────


def generar_sinteticos(n_reservas: int = N_RESERVAS, seed: int = SEED) -> None:
    """Genera datasets sintéticos coherentes para el dominio VivaColombia."""
    rng = np.random.default_rng(seed)
    print(f"[synthetic] seed={seed}  reservas objetivo={n_reservas:,}")

    # ── DIM-source: rutas ──────────────────────────────────────────
    rutas = pd.DataFrame(
        RUTAS_CATALOG,
        columns=[
            "origen_iata", "origen_ciudad", "destino_iata",
            "destino_ciudad", "distancia_km", "internacional_flag",
        ],
    )
    rutas.insert(0, "ruta_id", [f"RUT-{i:03d}" for i in range(1, len(rutas) + 1)])
    _save_bronze(rutas, "rutas")

    # ── DIM-source: canales ────────────────────────────────────────
    canales = pd.DataFrame(
        CANALES_CATALOG,
        columns=["canal_id", "nombre", "digital_flag", "categoria"],
    )
    _save_bronze(canales, "canales")

    # ── DIM-source: vuelos (uno cada día por ruta) ─────────────────
    inicio = pd.Timestamp("2024-01-01")
    fin    = pd.Timestamp("2026-04-30")
    fechas_vuelo = pd.date_range(inicio, fin, freq="D")

    vuelos_records = []
    vuelo_id = 0
    for f in fechas_vuelo:
        for _, ruta in rutas.iterrows():
            vuelo_id += 1
            aeronave = rng.choice(AERONAVES)
            capacidad = {"A320": 180, "A319": 156, "A320neo": 186}[aeronave]
            vuelos_records.append({
                "vuelo_id": f"VC-{vuelo_id:07d}",
                "numero_vuelo": f"VC{rng.integers(100, 999)}",
                "ruta_id": ruta["ruta_id"],
                "fecha_vuelo": f,
                "aeronave": aeronave,
                "capacidad_asientos": capacidad,
                "aerolinea": AEROLINEA,
            })
    vuelos = pd.DataFrame(vuelos_records)
    _save_bronze(vuelos, "vuelos")

    # ── DIM-source: pasajeros ──────────────────────────────────────
    n_pasajeros = max(20_000, n_reservas // 25)
    pasajeros = pd.DataFrame({
        "pasajero_id": [f"PAX-{i:07d}" for i in range(1, n_pasajeros + 1)],
        "pais_residencia": rng.choice(PAISES_RESIDENCIA, n_pasajeros, p=PAIS_PROBS),
        "segmento": rng.choice(SEGMENTOS, n_pasajeros, p=SEGMENTO_PROBS),
        "fecha_alta": pd.to_datetime(
            rng.choice(pd.date_range(inicio, fin - timedelta(days=1)).astype("int64"), n_pasajeros)
        ),
    })
    _save_bronze(pasajeros, "pasajeros")

    # ── FACT-source: reservas ──────────────────────────────────────
    # Distribución temporal con estacionalidad (peak en jul/dic)
    base = pd.date_range(inicio, fin - timedelta(days=1), freq="h")
    pesos = np.ones(len(base))
    pesos[(base.month == 7)] *= 1.7         # vacaciones mitad de año
    pesos[(base.month == 12)] *= 1.9        # diciembre
    pesos[(base.month == 1)] *= 1.4         # enero
    pesos[(base.dayofweek >= 5)] *= 1.25    # fin de semana
    pesos = pesos / pesos.sum()

    fechas_reserva = rng.choice(base.astype("int64"), size=n_reservas, p=pesos)
    fechas_reserva = pd.to_datetime(fechas_reserva)

    # Cada reserva apunta a un vuelo futuro (1..120 días en el futuro)
    dias_anticipacion = rng.integers(1, 120, size=n_reservas)
    fechas_vuelo_pretendidas = fechas_reserva + pd.to_timedelta(dias_anticipacion, unit="D")

    # Map a un vuelo real cercano (mismo día, ruta aleatoria)
    vuelos_idx = vuelos.set_index(vuelos["fecha_vuelo"].dt.date.astype(str))
    vuelos_por_dia = vuelos.groupby(vuelos["fecha_vuelo"].dt.date)["vuelo_id"].apply(list).to_dict()

    vuelo_ids = []
    for f in fechas_vuelo_pretendidas:
        candidatos = vuelos_por_dia.get(f.date())
        if not candidatos:
            # Fallback: el último día disponible
            candidatos = vuelos_por_dia[max(vuelos_por_dia.keys())]
        vuelo_ids.append(rng.choice(candidatos))

    # Precio dependiente de la ruta (internacional cuesta más)
    vuelo_to_ruta = vuelos.set_index("vuelo_id")["ruta_id"].to_dict()
    ruta_internacional = rutas.set_index("ruta_id")["internacional_flag"].to_dict()
    es_internacional = np.array([ruta_internacional[vuelo_to_ruta[v]] for v in vuelo_ids])
    base_precio = np.where(es_internacional, 850_000, 280_000)
    precio_pagado = (
        base_precio
        * rng.lognormal(mean=0.0, sigma=0.25, size=n_reservas)
    ).round(0)

    asientos_reservados = rng.choice([1, 1, 1, 2, 2, 3, 4], size=n_reservas)
    descuento_aplicado = np.where(
        rng.random(n_reservas) < 0.18,
        (precio_pagado * rng.uniform(0.05, 0.30, size=n_reservas)).round(0),
        0.0,
    )
    canal_ids = rng.choice([1, 2, 3, 4, 5], size=n_reservas, p=[0.40, 0.32, 0.13, 0.08, 0.07])
    pasajero_ids_chosen = rng.choice(pasajeros["pasajero_id"].values, size=n_reservas)

    # Cancelaciones: 8% global, mayor en internacionales (10%)
    p_cancela = np.where(es_internacional, 0.10, 0.07)
    es_cancelada = (rng.random(n_reservas) < p_cancela).astype(int)

    # Estado derivado
    estado = np.where(es_cancelada == 1, "CANCELADA", "CONFIRMADA")

    # Inyectar problemas de calidad para que Silver tenga algo que limpiar
    # (~0.5% nulos en canal, ~0.2% duplicados, ~0.1% precios negativos)
    null_canal_idx = rng.choice(n_reservas, size=n_reservas // 200, replace=False)
    bad_price_idx  = rng.choice(n_reservas, size=n_reservas // 1000, replace=False)
    canal_ids_serializable: list = canal_ids.astype(object).tolist()
    for i in null_canal_idx:
        canal_ids_serializable[i] = None
    precio_pagado[bad_price_idx] = -precio_pagado[bad_price_idx]

    reservas = pd.DataFrame({
        "reserva_id": [f"RES-{i:09d}" for i in range(1, n_reservas + 1)],
        "pasajero_id": pasajero_ids_chosen,
        "vuelo_id": vuelo_ids,
        "canal_id": canal_ids_serializable,
        "fecha_reserva": fechas_reserva,
        "fecha_vuelo_pretendida": fechas_vuelo_pretendidas,
        "dias_anticipacion": dias_anticipacion,
        "precio_pagado": precio_pagado,
        "asientos_reservados": asientos_reservados,
        "descuento_aplicado": descuento_aplicado,
        "es_cancelada": es_cancelada,
        "estado": estado,
    })

    # Inyectar duplicados exactos (~0.2%)
    dup_count = max(1, n_reservas // 500)
    dup_idx = rng.choice(n_reservas, size=dup_count, replace=False)
    duplicados = reservas.iloc[dup_idx].copy()
    reservas = pd.concat([reservas, duplicados], ignore_index=True)

    _save_bronze(reservas, "reservas")

    # ── FACT-source: pagos (1:1 con reservas confirmadas) ──────────
    confirmadas = reservas[reservas["estado"] == "CONFIRMADA"].copy()
    confirmadas["pago_id"] = [f"PAG-{i:09d}" for i in range(1, len(confirmadas) + 1)]
    confirmadas["medio_pago"] = rng.choice(
        ["TARJETA_CREDITO", "TARJETA_DEBITO", "PSE", "EFECTIVO"],
        size=len(confirmadas),
        p=[0.55, 0.20, 0.18, 0.07],
    )
    confirmadas["estado_pago"] = "EXITOSO"
    pagos = confirmadas[["pago_id", "reserva_id", "medio_pago", "estado_pago", "precio_pagado"]]
    pagos = pagos.rename(columns={"precio_pagado": "monto"})
    _save_bronze(pagos, "pagos")


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 60)
    print(f" EXTRACT → Bronze   (modo: {EXTRACT_MODE})")
    print("=" * 60)
    if EXTRACT_MODE == "cockroach":
        extraer_cockroach()
    else:
        generar_sinteticos()
    print("\nBronze completo en", BRONZE)


if __name__ == "__main__":
    main()
