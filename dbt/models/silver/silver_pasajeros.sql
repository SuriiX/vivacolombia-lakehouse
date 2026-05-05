{{ config(materialized='table') }}

SELECT DISTINCT ON (pasajero_id)
    pasajero_id,
    UPPER(TRIM(pais_residencia))  AS pais_residencia,
    LOWER(TRIM(segmento))         AS segmento,
    CAST(fecha_alta AS TIMESTAMP) AS fecha_alta
FROM read_parquet('../lakehouse/bronze/pasajeros_latest.parquet')
WHERE pasajero_id IS NOT NULL
