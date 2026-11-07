"""
Evalúa el agente sobre el set dev o test.

Uso:
    python eval/run_eval.py --set dev  --model Qwen3.6-35B-A3B-4bit
    python eval/run_eval.py --set dev  --model Qwen3.6-35B-A3B-4bit --runs 3
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Evalúa el agente de triage.")
parser.add_argument("--set",   choices=["dev", "test"], required=True)
parser.add_argument("--model", required=True, help="MODEL_ID para oMLX")
parser.add_argument("--runs",  type=int, default=3,
                    help="Número de ejecuciones para estabilidad (default: 3)")
args = parser.parse_args()

# MODEL_ID debe setearse ANTES de importar loop (variable de módulo en import time)
os.environ["MODEL_ID"] = args.model

ROOT     = Path(__file__).resolve().parent.parent
EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(EVAL_DIR))

from src.agent.loop import TEMPERATURE, TOP_P, run_agent   # noqa: E402
from src.agent.tools import DB_PATH                        # noqa: E402
from eval_helpers import compute_metrics, preflight_check  # noqa: E402

# ── Preflight: verificar que el modelo existe antes de procesar nada ──────────
preflight_check(args.model, os.environ["OMLX_BASE_URL"], os.environ["OMLX_API_KEY"])

# ── Rutas ─────────────────────────────────────────────────────────────────────
EVAL_DIR    = ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Cargar datos ──────────────────────────────────────────────────────────────
split_data = json.loads((EVAL_DIR / "split.json").read_text())
lead_ids   = split_data[args.set]

gt: dict[int, dict] = {}
with open(EVAL_DIR / "ground_truth.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        gt[int(row["lead_id"])] = row

con = sqlite3.connect(str(DB_PATH))
con.row_factory = sqlite3.Row
leads_db = {r["id"]: dict(r) for r in con.execute("SELECT * FROM inbound_leads")}
con.close()

DECISIONS = ["calificado", "revision", "descartado", "duplicado"]

today      = date.today().isoformat()
safe_model = args.model.replace("/", "-")


# ── Función para evaluar un run ───────────────────────────────────────────────
def run_once(run_num: int, total_runs: int) -> list[dict]:
    if total_runs > 1:
        print(f"\n── Run {run_num}/{total_runs} ──────────────────────────────────────")

    run_id = f"{args.set}_{safe_model}_{today}_R{run_num}"
    records = []
    for i, lid in enumerate(lead_ids, 1):
        lead     = leads_db[lid]
        expected = gt[lid]

        prefix = f"  [{i:>2}/{len(lead_ids)}]" + (f" R{run_num}" if total_runs > 1 else "")
        print(f"{prefix} lead #{lid:<3}  {expected['case_type']:<25} … ", end="", flush=True)

        try:
            trace     = run_agent(lead, run_id=run_id)
            run_error = False
        except Exception as exc:
            trace = {
                "decision":     "revision",
                "owner":        "cola_revision",
                "razonamiento": f"ERROR en run_agent: {exc}",
                "n_steps":      0,
                "elapsed_s":    0.0,
                "steps":        [],
                "error_sistema": True,
                "fallback_tipo": None,
            }
            run_error = True

        consistency_blocks = sum(
            1
            for step in trace["steps"]
            for tc   in step["tool_calls"]
            if tc["name"] == "registrar_decision"
            and "Consistencia:" in str(tc.get("result", {}).get("error", ""))
        )

        error_sistema = trace.get("error_sistema", False)
        step_limit    = trace.get("fallback_tipo") == "step_limit"

        correct_decision = trace["decision"] == expected["decision"]
        correct_owner    = trace["owner"]     == expected["owner_esperado"]
        tipo_error = (
            "error_sistema"  if error_sistema else
            "decision+owner" if not correct_decision and not correct_owner else
            "decision"       if not correct_decision else
            "owner"          if not correct_owner    else
            None
        )

        mark = (
            "✗s" if error_sistema else
            "✓"  if tipo_error is None else
            ("✗d" if "decision" in tipo_error else "✗o")
        )
        print(f"{mark}  {trace['decision']:<14}  owner={trace['owner']!r:<18} ({trace['elapsed_s']:.1f}s)")

        records.append({
            "run":                run_num,
            "run_id":             run_id,
            "lead_id":            lid,
            "case_type":          expected["case_type"],
            "decision_gt":        expected["decision"],
            "decision_agent":     trace["decision"],
            "owner_gt":           expected["owner_esperado"],
            "owner_agent":        trace["owner"],
            "razonamiento":       trace["razonamiento"],
            "n_steps":            trace["n_steps"],
            "elapsed_s":          trace["elapsed_s"],
            "consistency_blocks": consistency_blocks,
            "correct_decision":   correct_decision,
            "correct_owner":      correct_owner,
            "tipo_error":         tipo_error,
            "run_error":          run_error,
            "error_sistema":      error_sistema,
            "step_limit":         step_limit,
        })
    return records


# ── Ejecutar N runs ───────────────────────────────────────────────────────────
print(f"\nEvaluando  set={args.set!r}  modelo={args.model!r}  runs={args.runs}  "
      f"({len(lead_ids)} leads × {args.runs})\n")

all_records: list[list[dict]] = []
for run_num in range(1, args.runs + 1):
    all_records.append(run_once(run_num, args.runs))

per_run = [compute_metrics(r) for r in all_records]
flat    = [rec for run in all_records for rec in run]   # todos los records aplanados

# ── Agregados estadísticos ────────────────────────────────────────────────────
def agg(key: str):
    vals = [m[key] for m in per_run]
    return sum(vals) / len(vals), min(vals), max(vals)


def fmt_agg(key: str, as_pct=False, decimals=1) -> str:
    mean, lo, hi = agg(key)
    if as_pct:
        if lo == hi:
            return f"{mean*100:.{decimals}f}%"
        return f"{mean*100:.{decimals}f}%  [{lo*100:.{decimals}f}%, {hi*100:.{decimals}f}%]"
    if lo == hi:
        return f"{mean:.{decimals}f}"
    return f"{mean:.{decimals}f}  [{lo:.{decimals}f}, {hi:.{decimals}f}]"


# Confusion matrix agregada — columnas incluyen error_sistema
PRED_COLS = DECISIONS + ["error_sistema"]
confusion: dict[str, dict[str, int]] = {d: {p: 0 for p in PRED_COLS} for d in DECISIONS}
for r in flat:
    real = r["decision_gt"]
    pred = r["decision_agent"] if r["decision_agent"] in PRED_COLS else "revision"
    confusion[real][pred] += 1

# Accuracy por case_type — solo leads válidos (excluye error_sistema)
by_case_agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0})
for r in flat:
    if not r.get("error_sistema", False):
        by_case_agg[r["case_type"]]["n"]       += 1
        by_case_agg[r["case_type"]]["correct"] += r["correct_decision"]

errors_all   = [r for r in flat if r["tipo_error"] is not None]
dec_errors   = [r for r in errors_all if "decision" in r["tipo_error"]]
owner_errors = [r for r in errors_all if "owner"    in r["tipo_error"]]

# ── Reporte Markdown ──────────────────────────────────────────────────────────
def pct(num, den):
    return f"{100*num/den:.1f}%" if den else "—"


run_tag    = f"x{args.runs}" if args.runs > 1 else ""
stem       = f"{args.set}_{safe_model}_{today}{run_tag}"
report_path = RESULTS_DIR / f"{stem}.md"
errors_path = RESULTS_DIR / f"{stem}_errors.csv"

invalido = any(
    m["n_error_sistema"] / m["n"] > 0.1
    for m in per_run if m["n"] > 0
)
# Promedio de n_valid para etiqueta de accuracy
mean_valid = sum(m["n_valid"] for m in per_run) / len(per_run)
valid_label = (
    f"{int(mean_valid)} válidos de {per_run[0]['n']}"
    if mean_valid == per_run[0]["n_valid"]
    else f"~{mean_valid:.0f} válidos de {per_run[0]['n']}"
)

md = []
runs_label = f"{args.runs} run{'s' if args.runs > 1 else ''}"
md += [
    "# Evaluación del agente",
    "",
    f"**Set:** {args.set}  |  **Modelo:** `{args.model}`  |  **Fecha:** {today}  |  **Runs:** {args.runs}",
    f"**Temperatura:** {TEMPERATURE}  |  **top_p:** {TOP_P}",
    "",
]
if invalido:
    md += [
        "> **[INVALIDO]** Mas del 10 % de los leads de al menos un run son errores "
        "de sistema. Los resultados no son representativos.",
        "",
    ]
md += [
    f"## Resumen ejecutivo  _{runs_label}_",
    "",
    "| Métrica | Valor |" if args.runs == 1 else "| Métrica | Media  [min, max] |",
    "|---|---|",
    f"| Leads por run | {per_run[0]['n']} |",
    f"| Accuracy de decisión  ({valid_label}) | {fmt_agg('acc_decision', as_pct=True)} |",
    f"| Accuracy de owner  ({valid_label}) | {fmt_agg('acc_owner', as_pct=True)} |",
    f"| Tasa de escalamiento (revision) | {fmt_agg('escalation_rate', as_pct=True)} |",
    f"| Guardia de consistencia activada | {fmt_agg('consistency', decimals=1)} |",
    f"| Fallbacks por límite de pasos | {fmt_agg('n_step_limit', decimals=1)} |",
    f"| Errores de sistema | {fmt_agg('n_error_sistema', decimals=1)} |",
    f"| Pasos promedio | {fmt_agg('avg_steps', decimals=2)} |",
    f"| Latencia promedio | {fmt_agg('avg_latency', decimals=1)} s/lead |",
    f"| Errores por run | {fmt_agg('n_errors', decimals=1)} |",
    "",
]

if args.runs > 1:
    md += [
        "## Resultado por run",
        "",
        "| Run | Acc. decisión | Acc. owner | Dup. F1 | Pasos | Latencia | Errores |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, m in enumerate(per_run, 1):
        md.append(
            f"| {i} | {m['acc_decision']*100:.1f}% | {m['acc_owner']*100:.1f}% "
            f"| {m['dup_f1']*100:.0f}% | {m['avg_steps']:.1f} "
            f"| {m['avg_latency']:.1f}s | {m['n_errors']} |"
        )
    md.append("")

md += [
    "## Accuracy por case\\_type",
    "",
    "| case_type | n | correctos | accuracy |",
    "|---|---|---|---|",
]
for ct in sorted(by_case_agg):
    d = by_case_agg[ct]
    md.append(f"| {ct} | {d['n']} | {d['correct']} | {pct(d['correct'], d['n'])} |")

md += [
    "",
    "## Matriz de confusión  _(agregada)_",
    "",
    "Filas = decisión esperada · Columnas = decisión del agente",
    "",
]
header = ["**real \\ pred**"] + [f"**{d}**" for d in PRED_COLS]
md.append("| " + " | ".join(header) + " |")
md.append("|" + "|".join(["---"] * (len(PRED_COLS) + 1)) + "|")
for d_real in DECISIONS:
    cells = [f"**{d_real}**"] + [str(confusion[d_real][p]) for p in PRED_COLS]
    md.append("| " + " | ".join(cells) + " |")

tp_all = sum(m["tp"] for m in per_run)
fp_all = sum(m["fp"] for m in per_run)
fn_all = sum(m["fn"] for m in per_run)
p_all  = tp_all / (tp_all + fp_all) if (tp_all + fp_all) else 0
r_all  = tp_all / (tp_all + fn_all) if (tp_all + fn_all) else 0
f1_all = 2 * p_all * r_all / (p_all + r_all) if (p_all + r_all) else 0

md += [
    "",
    "## Detección de duplicados",
    "",
    "| Métrica | Valor |",
    "|---|---|",
    f"| True positives | {tp_all} |",
    f"| False positives | {fp_all} |",
    f"| False negatives | {fn_all} |",
    f"| Precision | {p_all*100:.1f}% |",
    f"| Recall | {r_all*100:.1f}% |",
    f"| F1 | {f1_all*100:.1f}% |",
    "",
]

md += [f"## Errores ({len(errors_all)} en total)", ""]
if errors_all:
    md.append(f"Ver `{errors_path.name}` para el detalle completo.")

if dec_errors:
    md += ["", f"### Errores de decisión ({len(dec_errors)})", ""]
    md.append("| run | lead\\_id | case\\_type | esperado | obtenido | razonamiento |")
    md.append("|---|---|---|---|---|---|")
    for e in dec_errors:
        razón = e["razonamiento"][:90].replace("|", "\\|").replace("\n", " ")
        md.append(f"| {e['run']} | {e['lead_id']} | {e['case_type']} "
                  f"| {e['decision_gt']} | {e['decision_agent']} | {razón}… |")

if owner_errors:
    md += ["", f"### Errores de owner ({len(owner_errors)})  _(decisión correcta)_", ""]
    md.append("| run | lead\\_id | case\\_type | decisión | owner esperado | owner obtenido |")
    md.append("|---|---|---|---|---|---|")
    for e in owner_errors:
        md.append(f"| {e['run']} | {e['lead_id']} | {e['case_type']} "
                  f"| {e['decision_agent']} | {e['owner_gt']} | {e['owner_agent']} |")

if not errors_all:
    md.append("*Sin errores.*")

report_path.write_text("\n".join(md), encoding="utf-8")

# ── CSV de errores ────────────────────────────────────────────────────────────
if errors_all:
    with open(errors_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "run", "lead_id", "case_type", "tipo_error",
            "decision_esperada", "decision_obtenida",
            "owner_esperado", "owner_obtenido",
            "razonamiento_agente",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for e in errors_all:
            w.writerow({
                "run":               e["run"],
                "lead_id":           e["lead_id"],
                "case_type":         e["case_type"],
                "tipo_error":        e["tipo_error"],
                "decision_esperada": e["decision_gt"],
                "decision_obtenida": e["decision_agent"],
                "owner_esperado":    e["owner_gt"],
                "owner_obtenido":    e["owner_agent"],
                "razonamiento_agente": e["razonamiento"],
            })

# ── Resumen en consola ────────────────────────────────────────────────────────
SEP = "═" * 62
print(f"\n{SEP}")
invalido_tag = "  [INVALIDO]" if invalido else ""
print(f"  {args.set.upper()} / {args.model}  ({runs_label}){invalido_tag}")
print(SEP)
print(f"  Accuracy decisión  : {fmt_agg('acc_decision', as_pct=True)}  ({valid_label})")
print(f"  Accuracy owner     : {fmt_agg('acc_owner', as_pct=True)}  ({valid_label})")
print(f"  Duplicados P/R/F1  : {p_all*100:.0f}% / {r_all*100:.0f}% / {f1_all*100:.0f}%")
print(f"  Escalamiento       : {fmt_agg('escalation_rate', as_pct=True)}")
print(f"  Guardia activada   : {fmt_agg('consistency', decimals=1)}")
print(f"  Pasos / latencia   : {fmt_agg('avg_steps', decimals=1)} pasos · {fmt_agg('avg_latency', decimals=1)} s/lead")
print(f"  Errores            : {len(errors_all)} (en {args.runs} run(s))")
print(f"  Temperatura/top_p  : {TEMPERATURE} / {TOP_P}")
print(f"  Reporte            : {report_path.relative_to(ROOT)}")
if errors_all:
    print(f"  Errores CSV        : {errors_path.relative_to(ROOT)}")
print(f"{SEP}\n")
