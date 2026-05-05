{{ config(materialized='table') }}

WITH rango AS (
    SELECT
        LEAST(MIN(r.fecha_reserva), MIN(v.fecha_vuelo))    AS fmin,
        GREATEST(MAX(r.fecha_vuelo_pretendida), MAX(v.fecha_vuelo)) AS fmax
    FROM {{ ref('silver_reservas') }} r, {{ ref('silver_vuelos') }} v
),
serie AS (
    SELECT UNNEST(generate_series(
        DATE_TRUNC('day', (SELECT fmin FROM rango)),
        DATE_TRUNC('day', (SELECT fmax FROM rango)),
        INTERVAL 1 DAY
    )) AS fecha
)
SELECT
    ROW_NUMBER() OVER (ORDER BY fecha)        AS tiempo_sk,
    CAST(fecha AS DATE)                       AS fecha,
    EXTRACT(YEAR     FROM fecha)              AS anio,
    EXTRACT(QUARTER  FROM fecha)              AS trimestre,
    EXTRACT(MONTH    FROM fecha)              AS mes,
    STRFTIME(fecha, '%B')                     AS mes_nombre,
    EXTRACT(DAY      FROM fecha)              AS dia,
    EXTRACT(DOW      FROM fecha)              AS dia_semana,
    STRFTIME(fecha, '%A')                     AS dia_nombre,
    CASE WHEN EXTRACT(DOW FROM fecha) IN (0, 6) THEN TRUE ELSE FALSE END AS es_fin_semana,
    CASE WHEN EXTRACT(MONTH FROM fecha) IN (1, 7, 12) THEN TRUE ELSE FALSE END AS es_temporada_alta
FROM serie
