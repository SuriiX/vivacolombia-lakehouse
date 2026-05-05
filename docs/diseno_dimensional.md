# Diseño Dimensional — VivaColombia Mini-Lakehouse

> Documento de respuesta a las 5 preguntas del Paso 1 del Taller #3.
> Equipo: Juan Pablo Cañas Sepúlveda · Owen David Pérez Sánchez — ITM 2026

---

## Pregunta 1 — Proceso de negocio

**Comportamiento de reservas confirmadas de vuelos VivaColombia por ruta, canal y período.**

Se modela el proceso de captación de ingresos por reservas: desde que el pasajero confirma una compra hasta que el vuelo se ejecuta (o se cancela). Es el proceso central del negocio operacional construido en los Módulos 1 y 2 sobre CockroachDB + Redis. No se modela el seat-locking de Redis (eso es operacional); se modela el resultado: la reserva confirmada.

---

## Pregunta 2 — Granularidad

**Una fila en `fact_reservas` = una reserva confirmada (un pasajero, un vuelo, un acto de compra).**

Pasa la regla de oro: la frase es única, sin "depende". Si una reserva incluye varios pasajeros (familia), se generan tantas filas como pasajeros — manteniendo la atomicidad. Una cancelación posterior no genera fila nueva: actualiza el flag `es_cancelada` en la fila original (decisión académica para simplificar; en producción se modelaría con accumulating snapshot).

---

## Pregunta 3 — Dimensiones

Se definen **5 dimensiones** (mínimo exigido: 3, incluyendo `DIM_TIEMPO` obligatoria):

| Dimensión | Atributos principales | SCD |
|---|---|---|
| `DIM_TIEMPO` | `tiempo_sk`, `fecha`, `anio`, `trimestre`, `mes`, `mes_nombre`, `dia`, `dia_semana`, `dia_nombre`, `es_fin_semana`, `es_temporada_alta` | Tipo 0 (no cambia) |
| `DIM_VUELO` | `vuelo_sk`, `vuelo_id`, `numero_vuelo`, `aeronave`, `capacidad_asientos`, `aerolinea` | Tipo 1 (overwrite — la aeronave cambia rara vez) |
| `DIM_RUTA` | `ruta_sk`, `ruta_id`, `origen_iata`, `origen_ciudad`, `destino_iata`, `destino_ciudad`, `distancia_km`, `internacional_flag` | Tipo 1 |
| `DIM_PASAJERO` | `pasajero_sk`, `pasajero_id`, `pais_residencia`, `segmento` (frecuente / ocasional / nuevo), `valido_desde`, `valido_hasta`, `activo` | **Tipo 2** ✅ |
| `DIM_CANAL` | `canal_sk`, `canal_id`, `nombre` (web / app / agencia / call_center), `digital_flag` | Tipo 1 |

**Por qué `DIM_PASAJERO` es SCD Tipo 2:** el segmento del pasajero cambia con el tiempo (ocasional → frecuente cuando supera 5 vuelos en 12 meses). Si sobrescribiéramos el atributo perderíamos la capacidad de responder "¿cuántos ingresos generó este pasajero cuando todavía era ocasional vs cuando ya era frecuente?". El SCD2 preserva esa historia con `valido_desde / valido_hasta / activo`.

---

## Pregunta 4 — Métricas (hechos)

| Métrica | Tipo | Justificación |
|---|---|---|
| `precio_pagado` | **Aditiva** | Suma válida en cualquier dimensión: ingresos del mes, por ruta, por canal, por pasajero. |
| `asientos_reservados` | **Aditiva** | Conteo de asientos vendidos suma en cualquier dimensión. |
| `descuento_aplicado` | **Aditiva** | Útil para calcular descuento total aplicado por canal o temporada. |
| `dias_anticipacion_reserva` | **No aditiva** | Solo tiene sentido como `AVG()`. Sumar días entre reservas no significa nada. |
| `es_cancelada` (0/1) | **Aditiva como conteo** | `SUM(es_cancelada)` = total cancelaciones. `AVG(es_cancelada) * 100` = tasa de cancelación %. |

Saldo o inventario de asientos disponibles **no se modela en el fact** porque es semi-aditivo (no suma en tiempo) y para esta granularidad agregaría complejidad innecesaria. Si se necesita, se construye una snapshot fact aparte en una iteración futura.

---

## Pregunta 5 — Estrategia SCD para `DIM_PASAJERO`

**SCD Tipo 2 con flag de actividad y rango de validez:**

```sql
-- Esquema de DIM_PASAJERO con SCD Tipo 2
pasajero_sk | pasajero_id | segmento   | pais_residencia | valido_desde | valido_hasta | activo
------------|-------------|------------|-----------------|--------------|--------------|--------
       1    | PAX-000001  | ocasional  | CO              | 2024-01-01   | 2025-08-14   | false
       2    | PAX-000001  | frecuente  | CO              | 2025-08-15   | 9999-12-31   | true
       3    | PAX-000002  | nuevo      | US              | 2025-03-22   | 9999-12-31   | true
```

**Reglas de operación:**

1. La `fact_reservas` siempre referencia el `pasajero_sk` que estaba **activo en el momento de la reserva** (lookup por `fecha_reserva BETWEEN valido_desde AND valido_hasta`).
2. Cuando un pasajero cambia de segmento, el job de Gold:
   - Cierra la fila vigente: `valido_hasta = fecha_cambio - 1 día`, `activo = false`.
   - Inserta nueva fila: `pasajero_sk` nuevo, mismo `pasajero_id`, nuevo `segmento`, `valido_desde = fecha_cambio`, `valido_hasta = '9999-12-31'`, `activo = true`.
3. Análisis posibles que esto habilita:
   - Ingresos por segmento del pasajero **al momento del vuelo** (no su segmento actual).
   - Tasa de retención: ¿qué porcentaje de pasajeros "ocasionales" pasaron a "frecuentes" en menos de 12 meses?
   - Comportamiento pre/post cambio de segmento del mismo `pasajero_id`.

**Nota académica:** En este corte del taller, generamos los pasajeros sintéticamente y para la mayoría habrá una sola versión. Dejamos en el código de `transform_gold.py` una función `simular_cambios_segmento()` que crea segundas versiones para ~15% de los pasajeros, garantizando que la rúbrica vea el SCD2 funcionando con datos.

---

## Diagrama Estrella

Ver archivo `modelo_dimensional.svg` (también renderizable como PNG):

```
                          ┌──────────────┐
                          │  DIM_TIEMPO  │
                          │  tiempo_sk   │
                          └──────┬───────┘
                                 │
                                 │
┌──────────────┐         ┌───────▼────────┐         ┌──────────────┐
│  DIM_VUELO   │◀────────│  FACT_RESERVAS │────────▶│  DIM_RUTA    │
│  vuelo_sk    │         │                │         │  ruta_sk     │
└──────────────┘         │  reserva_id    │         └──────────────┘
                         │  tiempo_sk     │
                         │  vuelo_sk      │
┌──────────────┐         │  ruta_sk       │         ┌──────────────┐
│ DIM_PASAJERO │◀────────│  pasajero_sk   │────────▶│  DIM_CANAL   │
│ pasajero_sk  │  SCD2   │  canal_sk      │         │  canal_sk    │
└──────────────┘         │  ────────────  │         └──────────────┘
                         │  precio_pagado │
                         │  asientos      │
                         │  descuento     │
                         │  dias_antic.   │
                         │  es_cancelada  │
                         └────────────────┘
```
