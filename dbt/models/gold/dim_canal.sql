{{ config(materialized='table') }}

SELECT
    ROW_NUMBER() OVER (ORDER BY canal_id) AS canal_sk,
    canal_id, nombre, digital_flag, categoria
FROM {{ ref('silver_canales') }}
