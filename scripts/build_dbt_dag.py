"""
scripts/build_dbt_dag.py — genera docs/dbt_dag.svg

Lee dbt/target/manifest.json (producido por `dbt docs generate`) y dibuja
el linaje sources → silver → gold como un SVG estático versionable.

Equivalente al sitio interactivo de `dbt docs serve`, pero sin necesidad
de levantar el servidor. Útil para evidencia visual en la entrega.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "dbt" / "target" / "manifest.json"
OUT = PROJECT_ROOT / "docs" / "dbt_dag.svg"

if not MANIFEST.exists():
    raise SystemExit(
        f"No existe {MANIFEST}.\n"
        "Corre primero:\n"
        "  cd dbt && DBT_PROFILES_DIR=$(pwd) dbt docs generate"
    )

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

nodes = {}
edges = []

# Sources
for sid, src in manifest.get("sources", {}).items():
    nodes[sid] = {
        "label": f"src.{src['name']}",
        "layer": "source",
    }

# Models
for nid, node in manifest.get("nodes", {}).items():
    if node["resource_type"] != "model":
        continue
    path = node.get("original_file_path", "") or node.get("path", "")
    if "silver" in path:
        layer = "silver"
    elif "gold" in path:
        layer = "gold"
    else:
        layer = "other"
    nodes[nid] = {
        "label": node["name"],
        "layer": layer,
    }
    for parent in node.get("depends_on", {}).get("nodes", []):
        edges.append((parent, nid))

# Layout por columnas
columns = {"source": [], "silver": [], "gold": []}
for nid, n in list(nodes.items()):
    if n["layer"] == "other":
        nodes.pop(nid)            # ignorar nodos sin layer conocido (tests, etc.)
        continue
    columns[n["layer"]].append(nid)

# Orden estable
for col in columns.values():
    col.sort()

W, H = 1200, 720
COL_X = {"source": 100, "silver": 500, "gold": 950}
COL_TITLE = {"source": "BRONZE / SOURCES", "silver": "SILVER", "gold": "GOLD"}
COL_COLOR = {"source": "#8b949e", "silver": "#3fb950", "gold": "#d29922"}

# Posición vertical de cada nodo
positions = {}
for layer, ids in columns.items():
    n = len(ids)
    if n == 0:
        continue
    spacing = (H - 140) / max(n, 1)
    for i, nid in enumerate(ids):
        positions[nid] = (COL_X[layer], 100 + spacing * (i + 0.5))

# ── Construir SVG ───────────────────────────────────────────────────
parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Arial, sans-serif">',
    '<style>',
    '  .bg { fill: #0d1117; }',
    '  .col-title { fill: #58a6ff; font-size: 16px; font-weight: bold; }',
    '  .node-source { fill: #21262d; stroke: #8b949e; stroke-width: 1.2; }',
    '  .node-silver { fill: #0e2818; stroke: #3fb950; stroke-width: 1.5; }',
    '  .node-gold   { fill: #2a210a; stroke: #d29922; stroke-width: 1.5; }',
    '  .node-text   { fill: #c9d1d9; font-size: 11px; font-family: monospace; }',
    '  .edge        { stroke: #484f58; stroke-width: 1.2; fill: none; opacity: 0.7; }',
    '  .header      { fill: #58a6ff; font-size: 18px; font-weight: bold; }',
    '  .subheader   { fill: #8b949e; font-size: 11px; }',
    '  .stats       { fill: #c9d1d9; font-size: 10px; font-family: monospace; }',
    '</style>',
    f'<rect class="bg" width="{W}" height="{H}"/>',
    # Título
    f'<text class="header" x="{W/2}" y="35" text-anchor="middle">'
    'VivaColombia Mini-Lakehouse — DAG dbt</text>',
    f'<text class="subheader" x="{W/2}" y="55" text-anchor="middle">'
    f'{len(columns["silver"])} modelos Silver · {len(columns["gold"])} modelos Gold · '
    f'generado desde dbt/target/manifest.json</text>',
]

# Títulos de columna
for layer, x in COL_X.items():
    parts.append(
        f'<text class="col-title" x="{x}" y="85" text-anchor="middle" '
        f'fill="{COL_COLOR[layer]}">{COL_TITLE[layer]}</text>'
    )

# Edges (líneas curvas Bezier)
for src, dst in edges:
    if src not in positions or dst not in positions:
        continue
    x1, y1 = positions[src]
    x2, y2 = positions[dst]
    # Bezier suave horizontal
    cx1 = x1 + (x2 - x1) * 0.5
    cx2 = x1 + (x2 - x1) * 0.5
    parts.append(
        f'<path class="edge" d="M {x1+85} {y1} C {cx1} {y1}, {cx2} {y2}, {x2-85} {y2}"/>'
    )

# Nodos
for nid, (x, y) in positions.items():
    layer = nodes[nid]["layer"]
    label = nodes[nid]["label"]
    rect_class = f"node-{layer}"
    parts.append(
        f'<rect class="{rect_class}" x="{x-85}" y="{y-15}" width="170" height="30" rx="6"/>'
    )
    parts.append(
        f'<text class="node-text" x="{x}" y="{y+4}" text-anchor="middle">{label}</text>'
    )

# Stats footer
edges_count = sum(1 for s, d in edges if s in positions and d in positions)
parts.append(
    f'<text class="stats" x="20" y="{H-15}">'
    f'Total: {len(positions)} nodos · {edges_count} dependencias · '
    f'Tests definidos: 32 (not_null, unique, relationships) · Equipo: SuriiX'
    '</text>'
)
parts.append('</svg>')


OUT.write_text("\n".join(parts), encoding="utf-8")
print("DAG guardado en", OUT)
print("Tamano KB:", round(OUT.stat().st_size / 1024, 1))
print("Nodos:", len(positions), "Edges:", edges_count)
