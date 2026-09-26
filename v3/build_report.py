"""Assemble v3/Airframe_Analysis_v3.html from the template, data-generated figures and the catalog, then print to PDF."""

import json
import os
import random
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
FIGS = Path(os.environ.get("AIRFRAME_FIGS", HERE / "figs"))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

cat = json.loads((ROOT / "catalog" / "error_catalog.json").read_text(encoding="utf-8"))
rows = ['<table><tr><th>Category</th><th style="width:60px">Entries</th><th style="width:90px">Seen in data</th><th>Seen here (examples)</th></tr>']
for cid, name in cat["categories"].items():
    es = [e for e in cat["entries"] if e["category"] == cid]
    seen = [e for e in es if e["dataset"]["seen"]]
    ex = "; ".join(f"{e['id']} {e['name']}" for e in seen[:3])
    rows.append(f"<tr><td><b>{cid}</b> {name}</td><td>{len(es)}</td><td>{len(seen)}</td><td>{ex}</td></tr>")
rows.append("</table>")

t = (HERE / "report_template.html").read_text(encoding="utf-8")
t = t.replace("{{FIG_TIMELINE}}", (FIGS / "fig_timeline.svg").read_text(encoding="utf-8"))
t = t.replace("{{FIG_PROBES}}", (FIGS / "fig_probes.svg").read_text(encoding="utf-8"))
t = t.replace("{{CAT_TABLE}}", "\n".join(rows))
t = t.replace("{{N_ENTRIES}}", str(len(cat["entries"]))).replace("{{N_CATS}}", str(len(cat["categories"])))
assert "{{" not in t, "unfilled placeholder"
html = HERE / "Airframe_Analysis_v3.html"
html.write_text(t, encoding="utf-8")

pdf = HERE / "Airframe_Analysis_v3.pdf"
tmp = os.path.join(os.environ["TEMP"], f"edgepdf_{random.randint(0, 1 << 30)}")
subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={tmp}",
                f"--print-to-pdf={pdf}", html.as_uri()], capture_output=True, timeout=120)
print(html.name, pdf.name, pdf.stat().st_size, "bytes")
