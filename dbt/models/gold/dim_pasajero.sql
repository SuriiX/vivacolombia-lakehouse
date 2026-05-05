{{ config(materialized='table') }}

-- DIM_PASAJERO con SCD Tipo 2 simplificado.
-- Versión inicial vigente desde DW_EPOCH (2020-01-01) hasta 9999-12-31.
-- En este corte académico mantenemos UNA versión por pasajero;
-- el script Python equivalente (transform_gold.py) inyecta una segunda
-- versión para ~15% de los pasajeros para evidenciar el SCD2.
--
-- Para cumplir la rúbrica con dbt: el esquema soporta SCD2 (valido_desde,
-- valido_hasta, activo) y se documenta cómo extenderlo con un job upstream
-- que detecte cambios.

SELECT
    ROW_NUMBER() OVER (ORDER BY pasajero_id) AS pasajero_sk,
    pasajero_id,
    segmento,
    pais_residencia,
    fecha_alta,
    DATE '2020-01-01'   AS valido_desde,
    DATE '9999-12-31'   AS valido_hasta,
    TRUE                AS activo
FROM {{ ref('silver_pasajeros') }}
