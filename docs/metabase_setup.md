# Setup de Metabase Community sobre el Mini-Lakehouse

> Alternativa B del Taller #3 — visualización del Gold sin escribir SQL
> en el dashboard.

## 1. Requisitos previos

- Pipeline corrido al menos una vez (`python main.py`) — debe existir
  `lakehouse/analytics.duckdb` con las tablas Silver y Gold materializadas
  por dbt o por `python scripts/persist_for_metabase.py`.
- **Docker Desktop** instalado (Windows / macOS / Linux).
  Plan B sin Docker: `java -jar metabase.jar` (descargar desde
  metabase.com/start/oss).

## 2. Levantar Metabase con Docker

```bash
# Desde la raíz del proyecto vivacolombia-lakehouse/
docker run -d --name metabase-vc \
  -p 3000:3000 \
  -v "$(pwd)/lakehouse:/lakehouse" \
  metabase/metabase:latest
```

Esperar ~60s la primera vez (Metabase corre migraciones internas) y
luego abrir http://localhost:3000. Crear el admin user
(cualquier email/password locales — no salen del contenedor).

## 3. Conectar Metabase al DuckDB del lakehouse

En *Add database*:

| Campo            | Valor                                  |
|------------------|----------------------------------------|
| Database type    | **DuckDB**                             |
| Display name     | VivaColombia Lakehouse                 |
| Database file    | `/lakehouse/analytics.duckdb`          |

> Nota: Metabase >= 0.50 trae el driver de DuckDB nativo. Si la versión
> que descargaron no lo lista, instalar el plugin
> `duckdb.metabase-driver.jar` en `/plugins/` del contenedor.

## 4. Dashboard sugerido — "VivaColombia · Operación analítica"

Con la vista `v_reservas_full` (creada por dbt y por
`persist_for_metabase.py`) las preguntas se arman sin SQL:

| # | Tipo de visual          | Datos                                                        |
|---|-------------------------|--------------------------------------------------------------|
| 1 | **Mapa de calor**       | `dia_nombre` × `hora` — `count(*)` (picos de reserva)         |
| 2 | **Línea con tendencia** | `fecha` (mensual) — `sum(precio_pagado)` (ingresos en COP)    |
| 3 | **Barra horizontal**    | `ruta` — `count(*)` filtrado a últimos 12 meses               |
| 4 | **KPIs (Single number)**| `avg(dias_anticipacion)`, `count(*) where es_cancelada=1`     |
| 5 | **Tabla pivot**         | `canal` × `segmento` — `sum(precio_pagado)`                   |

## 5. Capturar evidencia para la entrega

Una vez creado el dashboard:

1. *Sharing → Export as PDF* → guardar como `docs/metabase_dashboard.pdf`.
2. Hacer screenshot del dashboard completo y guardar como
   `docs/metabase_dashboard.png`.
3. Anexar ambas en el README principal (sección Resultados).

## 6. Apagar Metabase cuando no se use

```bash
docker stop metabase-vc      # detiene
docker start metabase-vc     # vuelve a arrancar (mantiene preguntas/dashboards)
docker rm -f metabase-vc     # eliminar definitivamente
```
