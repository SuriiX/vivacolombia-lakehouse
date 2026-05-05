{{ config(materialized='table') }}

-- Fact con todas las claves surrogadas resueltas.

WITH r AS (
    SELECT *,
           DATE_TRUNC('day', fecha_reserva) AS fecha_solo
    FROM {{ ref('silver_reservas') }}
),
v AS (
    SELECT vuelo_id, ruta_id FROM {{ ref('silver_vuelos') }}
)
SELECT
    r.reserva_id,
    dt.tiempo_sk,
    dv.vuelo_sk,
    dr.ruta_sk,
    dp.pasajero_sk,
    dc.canal_sk,
    r.fecha_reserva,
    r.fecha_vuelo_pretendida,
    r.precio_pagado,
    r.asientos_reservados,
    r.descuento_aplicado,
    r.dias_anticipacion,
    r.es_cancelada
FROM r
LEFT JOIN v                       ON r.vuelo_id    = v.vuelo_id
LEFT JOIN {{ ref('dim_tiempo') }} dt ON CAST(r.fecha_solo AS DATE) = dt.fecha
LEFT JOIN {{ ref('dim_vuelo') }}  dv ON r.vuelo_id  = dv.vuelo_id
LEFT JOIN {{ ref('dim_ruta') }}   dr ON v.ruta_id   = dr.ruta_id
LEFT JOIN {{ ref('dim_canal') }}  dc ON r.canal_id  = dc.canal_id
LEFT JOIN {{ ref('dim_pasajero') }} dp
       ON r.pasajero_id = dp.pasajero_id
      AND r.fecha_reserva BETWEEN dp.valido_desde AND dp.valido_hasta
WHERE dt.tiempo_sk IS NOT NULL
  AND dv.vuelo_sk  IS NOT NULL
  AND dr.ruta_sk   IS NOT NULL
  AND dp.pasajero_sk IS NOT NULL
  AND dc.canal_sk  IS NOT NULL
