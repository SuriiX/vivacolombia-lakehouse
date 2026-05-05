{{ config(materialized='table') }}

SELECT DISTINCT ON (vuelo_id)
    vuelo_id,
    numero_vuelo,
    ruta_id,
    CAST(fecha_vuelo AS TIMESTAMP)        AS fecha_vuelo,
    TRIM(aeronave)                        AS aeronave,
    CAST(capacidad_asientos AS INTEGER)   AS capacidad_asientos,
    aerolinea
FROM read_parquet('../lakehouse/bronze/vuelos_latest.parquet')
WHERE vuelo_id IS NOT NULL
  AND ruta_id  IS NOT NULL
  AND fecha_vuelo IS NOT NULL
