{{ config(materialized='table') }}

SELECT DISTINCT ON (canal_id)
    CAST(canal_id AS INTEGER)  AS canal_id,
    UPPER(TRIM(nombre))        AS nombre,
    CAST(digital_flag AS BOOLEAN) AS digital_flag,
    categoria
FROM read_parquet('../lakehouse/bronze/canales_latest.parquet')
