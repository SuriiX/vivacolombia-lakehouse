"""
scripts/build_dashboard.py — genera docs/dashboard_analitico.png

Dashboard estático equivalente al de Metabase, construido con matplotlib
sobre la capa Gold del lakehouse. Útil cuando Docker/Metabase no están
disponibles en el entorno donde se entrega.

Cinco visualizaciones (mismas del Metabase documentado en
docs/metabase_setup.md):

  1. Top 10 rutas por ingresos
  2. Heatmap día de la semana × hora del día (volumen de reservas)
  3. Ingresos mensuales con tendencia (línea)
  4. KPIs: tasa de cancelación, ticket promedio, ventana media
  5. Conversión por canal × segmento (matriz)
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD = PROJECT_ROOT / "lakehouse" / "gold"
OUT  = PROJECT_ROOT / "docs" / "dashboard_analitico.png"

con = duckdb.connect()
for t in ("fact_reservas", "dim_tiempo", "dim_vuelo", "dim_ruta", "dim_canal", "dim_pasajero"):
    con.execute(
        f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM read_parquet('{GOLD}/{t}.parquet')"
    )

# ── Datos para cada panel ───────────────────────────────────────────

# Panel 1: top 10 rutas por ingresos (confirmadas)
df_rutas = con.execute("""
    SELECT r.origen_iata || '→' || r.destino_iata AS ruta,
           r.internacional_flag,
           SUM(f.precio_pagado)/1e6 AS ingresos_M_COP
    FROM fact_reservas f
    JOIN dim_ruta r ON f.ruta_sk = r.ruta_sk
    WHERE f.es_cancelada = 0
    GROUP BY ruta, r.internacional_flag
    ORDER BY ingresos_M_COP DESC
    LIMIT 10
""").fetchdf()

# Panel 2: heatmap día de la semana × hora
df_heat = con.execute("""
    SELECT t.dia_nombre,
           EXTRACT(HOUR FROM f.fecha_reserva) AS hora,
           COUNT(*) AS reservas
    FROM fact_reservas f
    JOIN dim_tiempo t ON f.tiempo_sk = t.tiempo_sk
    GROUP BY t.dia_nombre, hora
    ORDER BY t.dia_nombre, hora
""").fetchdf()
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
day_labels = {"Monday":"Lun","Tuesday":"Mar","Wednesday":"Mié","Thursday":"Jue",
              "Friday":"Vie","Saturday":"Sáb","Sunday":"Dom"}
heat_matrix = df_heat.pivot_table(
    index="dia_nombre", columns="hora", values="reservas", fill_value=0
).reindex(day_order)

# Panel 3: ingresos mensuales
df_monthly = con.execute("""
    SELECT t.anio, t.mes,
           SUM(f.precio_pagado)/1e6 AS ingresos_M_COP,
           COUNT(*) AS reservas
    FROM fact_reservas f
    JOIN dim_tiempo t ON f.tiempo_sk = t.tiempo_sk
    WHERE f.es_cancelada = 0
    GROUP BY t.anio, t.mes
    ORDER BY t.anio, t.mes
""").fetchdf()
df_monthly["periodo"] = df_monthly["anio"].astype(str) + "-" + df_monthly["mes"].astype(str).str.zfill(2)

# Panel 4: KPIs — semántica correcta por métrica
kpis = con.execute("""
    SELECT
        -- tasa de cancelación: % sobre TODAS las reservas
        (SELECT ROUND(SUM(es_cancelada)*100.0/COUNT(*), 2) FROM fact_reservas) AS tasa_cancelacion_pct,
        -- ticket promedio: solo confirmadas (las canceladas no se cobran)
        (SELECT ROUND(AVG(precio_pagado), 0) FROM fact_reservas WHERE es_cancelada=0) AS ticket_promedio,
        -- ventana media de reserva: solo confirmadas
        (SELECT ROUND(AVG(dias_anticipacion), 1) FROM fact_reservas WHERE es_cancelada=0) AS ventana_media_dias,
        -- ingresos totales: solo confirmadas
        (SELECT SUM(precio_pagado)/1e9 FROM fact_reservas WHERE es_cancelada=0) AS ingresos_total_B_COP
""").fetchone()

# Panel 5: conversión por canal × segmento
df_conv = con.execute("""
    SELECT c.nombre AS canal, p.segmento,
           ROUND(SUM(1 - f.es_cancelada)*100.0/COUNT(*), 1) AS conversion_pct
    FROM fact_reservas f
    JOIN dim_canal c    ON f.canal_sk    = c.canal_sk
    JOIN dim_pasajero p ON f.pasajero_sk = p.pasajero_sk
    GROUP BY c.nombre, p.segmento
    ORDER BY c.nombre, p.segmento
""").fetchdf()
conv_matrix = df_conv.pivot_table(index="canal", columns="segmento", values="conversion_pct")

# ── Layout del dashboard ────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "#0d1117",
    "axes.facecolor":   "#161b22",
    "axes.edgecolor":   "#30363d",
    "axes.labelcolor":  "#c9d1d9",
    "axes.titlecolor":  "#58a6ff",
    "axes.titlesize":   12,
    "axes.titleweight": "bold",
    "xtick.color":      "#c9d1d9",
    "ytick.color":      "#c9d1d9",
    "text.color":       "#c9d1d9",
    "font.size":        9,
    "font.family":      "DejaVu Sans",
    "grid.color":       "#21262d",
})

fig = plt.figure(figsize=(16, 10), constrained_layout=True)
gs = fig.add_gridspec(3, 4, height_ratios=[1, 2, 2])

# Header con título
ax_title = fig.add_subplot(gs[0, :])
ax_title.axis("off")
ax_title.text(0.01, 0.65, "VivaColombia · Operación analítica",
              fontsize=22, fontweight="bold", color="#58a6ff")
ax_title.text(0.01, 0.20,
              f"Mini-Lakehouse · DuckDB sobre Parquet · {len(df_monthly)} meses analizados · 200K reservas",
              fontsize=10, color="#8b949e")

# Panel 1: Top rutas (gs[1, 0:2])
ax1 = fig.add_subplot(gs[1, 0:2])
colors = ["#f0883e" if intl else "#3fb950" for intl in df_rutas["internacional_flag"]]
bars = ax1.barh(df_rutas["ruta"][::-1], df_rutas["ingresos_M_COP"][::-1], color=colors[::-1])
ax1.set_title("Top 10 rutas por ingresos (M COP)")
ax1.set_xlabel("Ingresos (millones COP)")
ax1.grid(axis="x", linestyle=":", alpha=0.3)
for bar, val in zip(bars, df_rutas["ingresos_M_COP"][::-1]):
    ax1.text(val + 50, bar.get_y() + bar.get_height()/2,
             f"{val:,.0f}M", va="center", fontsize=8, color="#c9d1d9")
# Leyenda manual
ax1.scatter([], [], c="#3fb950", label="Doméstico", s=80)
ax1.scatter([], [], c="#f0883e", label="Internacional", s=80)
ax1.legend(loc="lower right", framealpha=0.7, facecolor="#0d1117", edgecolor="#30363d")

# Panel 2: Heatmap día × hora (gs[1, 2:4])
ax2 = fig.add_subplot(gs[1, 2:4])
im = ax2.imshow(heat_matrix.values, aspect="auto", cmap="YlOrRd", interpolation="nearest")
ax2.set_xticks(range(0, 24, 2))
ax2.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
ax2.set_yticks(range(7))
ax2.set_yticklabels([day_labels[d] for d in day_order])
ax2.set_title("Picos de reserva — día de la semana × hora")
ax2.set_xlabel("Hora del día")
cbar = fig.colorbar(im, ax=ax2, fraction=0.04)
cbar.ax.tick_params(colors="#c9d1d9")
cbar.set_label("Reservas", color="#c9d1d9")

# Panel 3: Ingresos mensuales (gs[2, 0:2])
ax3 = fig.add_subplot(gs[2, 0:2])
ax3.plot(range(len(df_monthly)), df_monthly["ingresos_M_COP"],
         marker="o", color="#58a6ff", linewidth=2, markersize=4)
ax3.fill_between(range(len(df_monthly)), df_monthly["ingresos_M_COP"], alpha=0.2, color="#58a6ff")
# Tendencia (regresión lineal simple)
x = np.arange(len(df_monthly))
z = np.polyfit(x, df_monthly["ingresos_M_COP"], 1)
ax3.plot(x, np.poly1d(z)(x), "--", color="#f85149", linewidth=1.5, label=f"Tendencia (pendiente {z[0]:+.0f}M/mes)")
step = max(1, len(df_monthly) // 12)
ax3.set_xticks(range(0, len(df_monthly), step))
ax3.set_xticklabels(df_monthly["periodo"][::step], rotation=45, ha="right", fontsize=7)
ax3.set_title("Ingresos mensuales (M COP) y tendencia")
ax3.set_ylabel("Ingresos (M COP)")
ax3.grid(linestyle=":", alpha=0.3)
ax3.legend(loc="upper left", framealpha=0.7, facecolor="#0d1117", edgecolor="#30363d")

# Panel 4: KPIs (gs[2, 2])
ax4 = fig.add_subplot(gs[2, 2])
ax4.axis("off")
ax4.text(0.5, 0.95, "KPIs operativos", ha="center", va="top",
         fontsize=12, fontweight="bold", color="#58a6ff")
kpi_data = [
    ("Tasa de cancelación", f"{kpis[0]:.2f}%", "#f85149"),
    ("Ticket promedio",     f"${kpis[1]/1000:,.0f}K COP", "#3fb950"),
    ("Ventana media reserva", f"{kpis[2]:.1f} días", "#d29922"),
    ("Ingresos totales",    f"${kpis[3]:.1f}B COP", "#58a6ff"),
]
for i, (label, value, color) in enumerate(kpi_data):
    y = 0.78 - i * 0.20
    ax4.text(0.5, y,       value, ha="center", va="center",
             fontsize=20, fontweight="bold", color=color)
    ax4.text(0.5, y - 0.07, label, ha="center", va="center",
             fontsize=9, color="#8b949e")

# Panel 5: Conversión canal × segmento (gs[2, 3])
ax5 = fig.add_subplot(gs[2, 3])
im2 = ax5.imshow(conv_matrix.values, cmap="RdYlGn", vmin=85, vmax=95, aspect="auto")
ax5.set_xticks(range(len(conv_matrix.columns)))
ax5.set_xticklabels(conv_matrix.columns, rotation=20, ha="right", fontsize=8)
ax5.set_yticks(range(len(conv_matrix.index)))
ax5.set_yticklabels(conv_matrix.index, fontsize=8)
ax5.set_title("Conversión % — canal × segmento")
for i in range(len(conv_matrix.index)):
    for j in range(len(conv_matrix.columns)):
        v = conv_matrix.values[i, j]
        if not np.isnan(v):
            ax5.text(j, i, f"{v:.1f}", ha="center", va="center",
                     fontsize=8, color="black", fontweight="bold")

# Footer
fig.text(0.5, 0.005,
         "Fuente: lakehouse/gold/*.parquet  ·  motor: DuckDB embebido  ·  "
         "equivalente al dashboard de Metabase documentado en docs/metabase_setup.md",
         ha="center", fontsize=8, color="#8b949e", style="italic")

OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Dashboard guardado en {OUT}")
print(f"Tamano: {OUT.stat().st_size / 1024:.1f} KB")
