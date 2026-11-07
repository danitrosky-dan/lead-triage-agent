"""
Funciones puras de evaluación, extraídas para ser testeables sin ejecutar run_eval.py.
"""

import sys


def compute_metrics(records: list[dict]) -> dict:
    """
    Calcula métricas sobre los records de un run.
    Los leads con error_sistema se excluyen de accuracy, escalamiento y duplicados;
    se reportan aparte en n_error_sistema.
    """
    valid = [r for r in records if not r.get("error_sistema", False)]
    n_total         = len(records)
    n_valid         = len(valid)
    n_error_sistema = n_total - n_valid
    n_step_limit    = sum(r.get("step_limit", False) for r in records)

    if n_valid == 0:
        return {
            "n": n_total, "n_valid": 0, "n_error_sistema": n_error_sistema,
            "n_step_limit": n_step_limit,
            "acc_decision": 0.0, "acc_owner": 0.0,
            "dup_precision": 0.0, "dup_recall": 0.0, "dup_f1": 0.0,
            "escalation_rate": 0.0, "consistency": 0,
            "avg_steps": 0.0, "avg_latency": 0.0, "total_elapsed": 0.0,
            "n_errors": 0, "tp": 0, "fp": 0, "fn": 0,
        }

    n_correct = sum(r["correct_decision"] for r in valid)
    n_owner   = sum(r["correct_owner"]    for r in valid)

    true_dups = {r["lead_id"] for r in valid if r["decision_gt"]    == "duplicado"}
    pred_dups = {r["lead_id"] for r in valid if r["decision_agent"] == "duplicado"}
    tp = len(true_dups & pred_dups)
    fp = len(pred_dups - true_dups)
    fn = len(true_dups - pred_dups)
    dup_prec = tp / (tp + fp) if (tp + fp) else 0.0
    dup_rec  = tp / (tp + fn) if (tp + fn) else 0.0
    dup_f1   = 2 * dup_prec * dup_rec / (dup_prec + dup_rec) if (dup_prec + dup_rec) else 0.0

    n_rev     = sum(r["decision_agent"] == "revision" for r in valid)
    cons      = sum(r["consistency_blocks"] for r in valid)
    avg_steps = sum(r["n_steps"]   for r in valid) / n_valid
    avg_lat   = sum(r["elapsed_s"] for r in valid) / n_valid
    tot_lat   = sum(r["elapsed_s"] for r in valid)
    errors    = [r for r in valid if r.get("tipo_error") is not None]

    return {
        "n":               n_total,
        "n_valid":         n_valid,
        "n_error_sistema": n_error_sistema,
        "n_step_limit":    n_step_limit,
        "acc_decision":    n_correct / n_valid,
        "acc_owner":       n_owner   / n_valid,
        "dup_precision":   dup_prec,
        "dup_recall":      dup_rec,
        "dup_f1":          dup_f1,
        "escalation_rate": n_rev / n_valid,
        "consistency":     cons,
        "avg_steps":       avg_steps,
        "avg_latency":     avg_lat,
        "total_elapsed":   tot_lat,
        "n_errors":        len(errors),
        "tp": tp, "fp": fp, "fn": fn,
    }


def preflight_check(model_id: str, base_url: str, api_key: str, client=None) -> None:
    """
    Verifica que model_id existe en el servidor antes de iniciar la evaluación.
    Llama a sys.exit(1) si el modelo no existe o no hay conexión.
    client: inyección de dependencia para tests (si None, crea un OpenAI client).
    """
    if client is None:
        from openai import OpenAI
        client = OpenAI(base_url=base_url, api_key=api_key)
    try:
        available = [m.id for m in client.models.list()]
    except Exception as exc:
        print(f"\nERROR preflight: no se pudo conectar al servidor oMLX ({exc}).")
        print("Verifica que el servidor esté corriendo y que OMLX_BASE_URL sea correcto.")
        sys.exit(1)
    if model_id not in available:
        lista = ", ".join(available) if available else "(ninguno)"
        print(f"\nERROR preflight: modelo '{model_id}' no disponible en el servidor.")
        print(f"Modelos disponibles: {lista}")
        sys.exit(1)
