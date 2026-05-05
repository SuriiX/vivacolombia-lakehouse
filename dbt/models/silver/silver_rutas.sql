{{ config(materialized='table') }}

SELECT DISTINCT ON (ruta_id)
    ruta_id,
    UPPER(TRIM(origen_iata))   AS origen_iata,
    origen_ciudad,
    UPPER(TRIM(destino_iata))  AS destino_iata,
    destino_ciudad,
    CAST(distancia_km AS INTEGER) AS distancia_km,
    CAST(internacional_flag AS BOOLEAN) AS internacional_flag
FROM read_parquet('../lakehouse/bronze/rutas_latest.parquet')
