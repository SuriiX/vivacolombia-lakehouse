{{ config(materialized='table') }}

SELECT
    ROW_NUMBER() OVER (ORDER BY ruta_id) AS ruta_sk,
    ruta_id, origen_iata, origen_ciudad,
    destino_iata, destino_ciudad,
    distancia_km, internacional_flag
FROM {{ ref('silver_rutas') }}
