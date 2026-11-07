"""
Ejecuta el agente sobre 5 leads de distintos case_type e imprime
la decisión del agente, la esperada, los pasos y el tiempo.
"""

import csv
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.loop import run_agent  # noqa: E402

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "crm.db"
GT_PATH = ROOT / "eval" / "ground_truth.csv"

# ── Cargar ground truth ───────────────────────────────────────────────────────
gt: dict[int, dict] = {}
with open(GT_PATH, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        gt[int(row["lead_id"])] = row

# ── Seleccionar 1 lead por case_type (5 casos representativos) ───────────────
CASE_TYPES = [
    "duplicado_exacto",
    "empresa_desconocida",
    "fuera_icp",
    "cargo_ambiguo",
    "normal",
]

con = sqlite3.connect(str(DB_PATH))
con.row_factory = sqlite3.Row

sample: list[tuple[dict, dict]] = []
for ct in CASE_TYPES:
    for lid, row in gt.items():
        if row["case_type"] == ct:
            lead_row = con.execute(
                "SELECT * FROM inbound_leads WHERE id = ?", (lid,)
            ).fetchone()
            if lead_row:
                sample.append((dict(lead_row), row))
                break

con.close()

# ── Ejecutar agente y comparar ────────────────────────────────────────────────
SEP = "─" * 68

print(f"\n{'═' * 68}")
print("  LEAD TRIAGE AGENT — muestra de 5 leads")
print(f"{'═' * 68}\n")

aciertos = 0
for lead, expected in sample:
    t0 = time.time()
    result = run_agent(lead)
    elapsed = time.time() - t0

    dec_agente   = result["decision"]
    dec_esperada = expected["decision"]
    match        = "✓" if dec_agente == dec_esperada else "✗"
    if dec_agente == dec_esperada:
        aciertos += 1

    # Resumen de pasos (tool_calls por paso)
    pasos_resumen = []
    for step in result["steps"]:
        tools_en_paso = [tc["name"] for tc in step["tool_calls"]]
        pasos_resumen.append(f"  paso {step['n']}: {', '.join(tools_en_paso) or '(sin tool_calls)'}")

    print(SEP)
    print(f"Lead #{lead['id']}  |  case_type: {expected['case_type']}")
    print(f"  Nombre   : {lead['nombre']}")
    print(f"  Empresa  : {lead['empresa']}")
    print(f"  Cargo    : {lead['cargo']}")
    print(f"  País     : {lead['pais']}")
    print()
    print(f"  Decisión agente   : {dec_agente:<12}  {match}  (esperada: {dec_esperada})")
    print(f"  Owner             : {result['owner']}")
    print(f"  Pasos             : {result['n_steps']}  ({elapsed:.1f} s)")
    print(f"  Razonamiento      : {result['razonamiento']}")
    print()
    for p in pasos_resumen:
        print(p)
    print()

print(SEP)
print(f"  Aciertos: {aciertos}/{len(sample)}")
print(f"{'═' * 68}\n")
