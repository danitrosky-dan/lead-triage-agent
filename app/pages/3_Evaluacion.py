"""
Página 3: Evaluación — test v1 (prompt congelado).
Muestra métricas, matriz de confusión, errores por origen y estadísticas
de correos. Los datos se reconstruyen desde la DB + ground_truth.csv.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_ROOT    = _APP_DIR.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_APP_DIR))

from db import get_test_decisions, get_email_stats  # noqa: E402

st.set_page_config(page_title="Evaluación", page_icon="📊", layout="wide")
st.title("📊 Evaluación — test v1")
st.caption("Modelo: Qwen3.6-35B-A3B-4bit  |  70 leads × 3 runs  |  prompt congelado (tag prompt-v1)")

# ── Cargar datos ──────────────────────────────────────────────────────────────
_EVAL_DIR = _ROOT / "eval"
_GT_PATH  = _EVAL_DIR / "ground_truth.csv"
_SPLIT    = json.loads((_EVAL_DIR / "split.json").read_text())["test"]

gt: dict[int, dict] = {}
with open(_GT_PATH, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        lid = int(row["lead_id"])
        if lid in _SPLIT:
            gt[lid] = row

decisions = get_test_decisions()

# Agrupar por run
by_run: dict[str, dict[int, dict]] = defaultdict(dict)
for d in decisions:
    by_run[d["run_id"]][d["lead_id"]] = d

# ── Métricas por run ──────────────────────────────────────────────────────────
DECISIONS = ["calificado", "revision", "descartado", "duplicado"]
PRED_COLS = DECISIONS + ["error_sistema"]


def _run_metrics(run_decisions: dict[int, dict]) -> dict:
    records = []
    for lid in _SPLIT:
        g   = gt.get(lid)
        d   = run_decisions.get(lid)
        if not g or not d:
            continue
        correct_dec   = d["decision"] == g["decision"]
        correct_owner = d["owner"]    == g["owner_esperado"]
        records.append({
            "lead_id":          lid,
            "case_type":        g["case_type"],
            "decision_gt":      g["decision"],
            "decision_agent":   d["decision"],
            "owner_gt":         g["owner_esperado"],
            "owner_agent":      d["owner"],
            "correct_decision": correct_dec,
            "correct_owner":    correct_owner,
            "error_sistema":    d["decision"] == "error_sistema",
        })
    valid = [r for r in records if not r["error_sistema"]]
    n     = len(valid)
    if n == 0:
        return {"n": 0, "acc_dec": 0, "acc_own": 0, "records": records}
    true_dups = {r["lead_id"] for r in valid if r["decision_gt"]    == "duplicado"}
    pred_dups = {r["lead_id"] for r in valid if r["decision_agent"] == "duplicado"}
    tp = len(true_dups & pred_dups)
    fp = len(pred_dups - true_dups)
    fn = len(true_dups - pred_dups)
    return {
        "n":       n,
        "acc_dec": sum(r["correct_decision"] for r in valid) / n,
        "acc_own": sum(r["correct_owner"]    for r in valid) / n,
        "dup_tp":  tp, "dup_fp": fp, "dup_fn": fn,
        "records": records,
    }


run_ids = sorted(by_run.keys())
metrics = {rid: _run_metrics(by_run[rid]) for rid in run_ids}
all_records = [r for m in metrics.values() for r in m["records"]]
valid_all   = [r for r in all_records if not r["error_sistema"]]
n_total     = len(valid_all)

# ── Resumen ejecutivo ─────────────────────────────────────────────────────────
st.markdown("## Resumen ejecutivo")

acc_dec_vals = [m["acc_dec"] for m in metrics.values() if m["n"] > 0]
acc_own_vals = [m["acc_own"] for m in metrics.values() if m["n"] > 0]
mean_dec     = sum(acc_dec_vals) / len(acc_dec_vals) if acc_dec_vals else 0
mean_own     = sum(acc_own_vals) / len(acc_own_vals) if acc_own_vals else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Acc. decisión (media)", f"{mean_dec*100:.1f}%",
          delta=f"[{min(acc_dec_vals)*100:.1f}%–{max(acc_dec_vals)*100:.1f}%]")
m2.metric("Acc. owner (media)",    f"{mean_own*100:.1f}%",
          delta=f"[{min(acc_own_vals)*100:.1f}%–{max(acc_own_vals)*100:.1f}%]")

# Duplicados agregados
tp_all = sum(m.get("dup_tp", 0) for m in metrics.values())
fp_all = sum(m.get("dup_fp", 0) for m in metrics.values())
fn_all = sum(m.get("dup_fn", 0) for m in metrics.values())
prec   = tp_all / (tp_all + fp_all) if (tp_all + fp_all) else 0
rec    = tp_all / (tp_all + fn_all) if (tp_all + fn_all) else 0
f1     = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
m3.metric("Recall duplicados", f"{rec*100:.0f}%")
m4.metric("F1 duplicados",     f"{f1*100:.1f}%")

# ── Tabla por run ─────────────────────────────────────────────────────────────
st.markdown("### Resultado por run")
run_rows = []
for i, rid in enumerate(run_ids, 1):
    m = metrics[rid]
    run_rows.append({
        "Run":           f"R{i}",
        "Acc. decisión": f"{m['acc_dec']*100:.1f}%",
        "Acc. owner":    f"{m['acc_own']*100:.1f}%",
        "Dup. P":        f"{m.get('dup_tp', 0) / (m.get('dup_tp', 0) + m.get('dup_fp', 1))*100:.0f}%",
        "Dup. R":        f"{m.get('dup_tp', 0) / (m.get('dup_tp', 0) + m.get('dup_fn', 1))*100:.0f}%",
        "Errores":       sum(1 for r in m["records"] if r["decision_gt"] != r["decision_agent"] and not r["error_sistema"]),
    })
st.dataframe(pd.DataFrame(run_rows), width="stretch", hide_index=True)

# ── Accuracy por case_type ────────────────────────────────────────────────────
st.markdown("### Accuracy por case_type")
by_case: dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0})
for r in valid_all:
    by_case[r["case_type"]]["n"]       += 1
    by_case[r["case_type"]]["correct"] += r["correct_decision"]

ct_rows = []
for ct in sorted(by_case):
    d = by_case[ct]
    ct_rows.append({
        "case_type":  ct,
        "n":          d["n"],
        "correctos":  d["correct"],
        "accuracy":   f"{d['correct']/d['n']*100:.1f}%" if d["n"] else "—",
        "acc_num":    d["correct"] / d["n"] if d["n"] else 0,
    })

ct_df = pd.DataFrame(ct_rows)
# Style accuracy column with gradient
styled = (
    ct_df.drop(columns=["acc_num"])
    .style.background_gradient(
        subset=None, axis=None,
    )
)
# Simple bar-style display
st.dataframe(
    ct_df.drop(columns=["acc_num"]),
    width="stretch",
    hide_index=True,
)

# ── Matriz de confusión ───────────────────────────────────────────────────────
st.markdown("### Matriz de confusión  _(agregada, 3 runs)_")
st.caption("Filas = decisión esperada · Columnas = decisión del agente")

confusion: dict[str, dict[str, int]] = {d: {p: 0 for p in PRED_COLS} for d in DECISIONS}
for r in valid_all:
    real = r["decision_gt"]
    pred = r["decision_agent"] if r["decision_agent"] in PRED_COLS else "revision"
    confusion[real][pred] += 1

cm_data = {col: [confusion[row][col] for row in DECISIONS] for col in PRED_COLS}
cm_df   = pd.DataFrame(cm_data, index=DECISIONS)
cm_df.index.name = "real \\ pred"


def _style_confusion(val, row_idx, col_name):
    if row_idx == col_name:
        return "background-color: #c6efce; color: #276221; font-weight: bold"
    if val > 0:
        return "background-color: #fce4e4; color: #9c0006"
    return ""


styled_cm = cm_df.style.apply(
    lambda col: [
        (
            "background-color: #c6efce; color: #276221; font-weight: bold"
            if DECISIONS[i] == col.name
            else ("background-color: #fce4e4; color: #9c0006" if col.iloc[i] > 0 else "")
        )
        for i in range(len(col))
    ],
    axis=0,
)
st.dataframe(styled_cm, width="content")

# ── Errores por origen ────────────────────────────────────────────────────────
st.markdown("### Errores por origen del error")
st.caption("Clasificación manual de los 9 errores (6 leads únicos, 9 instancias en 3 runs)")

origin_data = pd.DataFrame([
    {
        "Origen":          "Orquestación (texto plano sin tool_calls → step_limit)",
        "Leads únicos":    4,
        "Instancias":      5,
        "Leads":           "#43, #78, #80, #94",
        "Reproducible":    "No (1–2/3 runs)",
    },
    {
        "Origen":          "Herramienta determinística (umbral fuzzy demasiado bajo)",
        "Leads únicos":    1,
        "Instancias":      3,
        "Leads":           "#72",
        "Reproducible":    "Sí (3/3 runs)",
    },
    {
        "Origen":          "Juicio del LLM (regla 'contenido no es criterio' ignorada)",
        "Leads únicos":    1,
        "Instancias":      1,
        "Leads":           "#45",
        "Reproducible":    "No (1/3 runs)",
    },
])
st.dataframe(origin_data, width="stretch", hide_index=True)

with st.expander("Detalle de errores por lead"):
    error_data = pd.DataFrame([
        {"Lead": "#43", "case_type": "cargo_ambiguo",        "Esperado": "calificado",  "Obtenido": "revision",  "Runs fallidas": "1/3 (R1)", "Causa": "Texto plano en paso 1 → step_limit"},
        {"Lead": "#45", "case_type": "cargo_ambiguo",        "Esperado": "calificado",  "Obtenido": "revision",  "Runs fallidas": "1/3 (R1)", "Causa": "LLM usó contenido como evidencia de datos_contradictorios (regla ignorada)"},
        {"Lead": "#72", "case_type": "normal",                "Esperado": "calificado",  "Obtenido": "duplicado", "Runs fallidas": "3/3",      "Causa": "buscar_duplicado devuelve 87.5% > umbral 85% (Natalia Sánchez vs Natalia Silva, mismo dominio)"},
        {"Lead": "#78", "case_type": "normal",                "Esperado": "calificado",  "Obtenido": "revision",  "Runs fallidas": "1/3 (R1)", "Causa": "Texto plano en paso 1 → step_limit"},
        {"Lead": "#80", "case_type": "normal",                "Esperado": "calificado",  "Obtenido": "revision",  "Runs fallidas": "1/3 (R3)", "Causa": "Texto plano en paso 3 (tras 2 tools) → step_limit"},
        {"Lead": "#94", "case_type": "normal",                "Esperado": "descartado",  "Obtenido": "revision",  "Runs fallidas": "2/3 (R1, R2)", "Causa": "Texto plano en paso 1 → step_limit"},
    ])
    st.dataframe(error_data, width="stretch", hide_index=True)

# ── Estadísticas de correos ───────────────────────────────────────────────────
st.markdown("### Estadísticas de correos")
email_stats = get_email_stats()

if email_stats["total"] == 0:
    st.info("No hay borradores de correo generados aún.")
else:
    ec1, ec2, ec3 = st.columns(3)
    ec1.metric("Correos generados", email_stats["total"])

    by_estado = {r["estado"]: r for r in email_stats["by_estado"]}
    ok1  = by_estado.get("ok_primera",        {})
    ok2  = by_estado.get("ok_reintento",       {})
    fail = by_estado.get("requiere_revision",  {})

    n_ok1  = ok1.get("n", 0)
    n_ok2  = ok2.get("n", 0)
    n_fail = fail.get("n", 0)

    ec2.metric(
        "Aprobados al primer intento",
        f"{n_ok1}  ({n_ok1/email_stats['total']*100:.0f}%)",
    )
    ec3.metric(
        "Requieren revisión manual",
        f"{n_fail}  ({n_fail/email_stats['total']*100:.0f}%)",
    )

    estado_df = pd.DataFrame([
        {
            "Estado":         "✅ ok_primera",
            "n":              n_ok1,
            "Avg. intentos":  round(ok1.get("avg_intentos", 0), 2),
            "% del total":    f"{n_ok1/email_stats['total']*100:.1f}%",
        },
        {
            "Estado":         "🔄 ok_reintento",
            "n":              n_ok2,
            "Avg. intentos":  round(ok2.get("avg_intentos", 0), 2),
            "% del total":    f"{n_ok2/email_stats['total']*100:.1f}%",
        },
        {
            "Estado":         "⚠️ requiere_revision",
            "n":              n_fail,
            "Avg. intentos":  round(fail.get("avg_intentos", 0), 2),
            "% del total":    f"{n_fail/email_stats['total']*100:.1f}%",
        },
    ])
    st.dataframe(estado_df, width="stretch", hide_index=True)

    with st.expander("Últimos 10 correos generados"):
        recent = email_stats["recent"][:10]
        for em in recent:
            with st.container(border=True):
                hd1, hd2 = st.columns([3, 1])
                hd1.markdown(
                    f"**#{em['lead_id']} — {em['nombre']}** ({em['empresa']}, {em['pais']})"
                )
                badge = {"ok_primera": "🟢", "ok_reintento": "🟡", "requiere_revision": "🔴"}
                hd2.markdown(badge.get(em["estado"], "⚪") + " " + em["estado"])

                if em.get("asunto"):
                    st.text_input("Asunto", em["asunto"],
                                  key=f"asunto_{em['id']}", disabled=True)
                if em.get("cuerpo"):
                    st.text_area("Cuerpo", em["cuerpo"], height=120,
                                 key=f"cuerpo_{em['id']}", disabled=True)
                if em.get("fallo"):
                    st.warning(f"Fallo: {em['fallo']}")
