{{ config(materialized='table') }}

SELECT
    ROW_NUMBER() OVER (ORDER BY vuelo_id) AS vuelo_sk,
    vuelo_id, numero_vuelo, ruta_id,
    fecha_vuelo, aeronave, capacidad_asientos, aerolinea
FROM {{ ref('silver_vuelos') }}
