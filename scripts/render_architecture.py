"""Render architecture.drawio through Graphviz without duplicating its labels."""

from pathlib import Path
import json
import subprocess
import xml.etree.ElementTree as ET


root = Path(__file__).resolve().parents[1]
cells = ET.parse(root / "architecture.drawio").findall(".//mxCell")
lines = [
    "digraph architecture {",
    'graph [rankdir=LR, bgcolor="white", pad=0.4, nodesep=0.5, ranksep=0.7];',
    'node [shape=box, style="rounded,filled", fillcolor="#e8f0fe", fontname="DejaVu Sans", fontsize=12];',
    'edge [fontname="DejaVu Sans", fontsize=10, color="#475569"];',
]
for cell in cells:
    attributes = cell.attrib
    if attributes.get("vertex") == "1":
        lines.append(f'{json.dumps(attributes["id"])} [label={json.dumps(attributes["value"])}];')
    elif attributes.get("edge") == "1":
        lines.append(
            f'{json.dumps(attributes["source"])} -> {json.dumps(attributes["target"])} '
            f'[label={json.dumps(attributes.get("value", ""))}];'
        )
lines.append("}")
subprocess.run(
    ["dot", "-Tpng", "-o", str(root / "assets/architecture.png")],
    input="\n".join(lines),
    text=True,
    check=True,
)
print("Rendered assets/architecture.png from architecture.drawio")
