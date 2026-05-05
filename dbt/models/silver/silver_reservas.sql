{{
  config(materialized='table')
}}

-- Silver de reservas: limpio, tipado, deduplicado.
-- Equivalente SQL del script Python scripts/transform_silver.py.

WITH bronze AS (
    SELECT *
    FROM read_parquet('../lakehouse/bronze/reservas_latest.parquet')
),
limpiado AS (
    SELECT
        reserva_id,
        pasajero_id,
        vuelo_id,
        COALESCE(canal_id, 4)                AS canal_id,        -- default CALL_CENTER
        CAST(fecha_reserva           AS TIMESTAMP) AS fecha_reserva,
        CAST(fecha_vuelo_pretendida  AS TIMESTAMP) AS fecha_vuelo_pretendida,
        CAST(dias_anticipacion       AS INTEGER)   AS dias_anticipacion,
        CAST(precio_pagado           AS DOUBLE)    AS precio_pagado,
        CAST(asientos_reservados     AS INTEGER)   AS asientos_reservados,
        COALESCE(CAST(descuento_aplicado AS DOUBLE), 0.0)  AS descuento_aplicado,
        CAST(es_cancelada            AS INTEGER)   AS es_cancelada,
        UPPER(TRIM(estado))                  AS estado
    FROM bronze
    WHERE reserva_id      IS NOT NULL
      AND pasajero_id     IS NOT NULL
      AND vuelo_id        IS NOT NULL
      AND fecha_reserva   IS NOT NULL
      AND precio_pagado   IS NOT NULL
      AND precio_pagado   > 0
      AND dias_anticipacion >= 0
)
SELECT DISTINCT ON (reserva_id) *
FROM limpiado
