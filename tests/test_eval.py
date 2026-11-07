"""
Tests de eval_helpers: compute_metrics y preflight_check.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
from eval_helpers import compute_metrics, preflight_check


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rec(decision_gt, decision_agent, correct_decision=None, correct_owner=True,
         error_sistema=False, step_limit=False, lead_id=1):
    if correct_decision is None:
        correct_decision = (decision_gt == decision_agent) and not error_sistema
    tipo = (
        "error_sistema"  if error_sistema else
        None             if (correct_decision and correct_owner) else
        "decision"
    )
    return {
        "lead_id":           lead_id,
        "case_type":         "normal",
        "decision_gt":       decision_gt,
        "decision_agent":    decision_agent,
        "owner_gt":          "Ana Torres",
        "owner_agent":       "Ana Torres" if correct_owner else "otro",
        "razonamiento":      "test",
        "n_steps":           3,
        "elapsed_s":         10.0,
        "consistency_blocks": 0,
        "correct_decision":  correct_decision,
        "correct_owner":     correct_owner,
        "tipo_error":        tipo,
        "run_error":         False,
        "error_sistema":     error_sistema,
        "step_limit":        step_limit,
    }


# ── compute_metrics ───────────────────────────────────────────────────────────

class TestComputeMetrics:

    def test_excluye_error_sistema_de_accuracy(self):
        records = [
            _rec("calificado", "calificado", lead_id=1),              # correcto
            _rec("calificado", "revision",   lead_id=2),              # decisión errónea
            _rec("calificado", "error_sistema", error_sistema=True, lead_id=3),
        ]
        m = compute_metrics(records)
        assert m["n"] == 3
        assert m["n_valid"] == 2
        assert m["n_error_sistema"] == 1
        # 1 correcto de 2 válidos
        assert m["acc_decision"] == pytest.approx(0.5)

    def test_sin_errores_metricas_normales(self):
        records = [
            _rec("calificado", "calificado", lead_id=1),
            _rec("calificado", "calificado", lead_id=2),
        ]
        m = compute_metrics(records)
        assert m["n"] == 2
        assert m["n_valid"] == 2
        assert m["n_error_sistema"] == 0
        assert m["acc_decision"] == 1.0

    def test_todos_error_sistema_devuelve_ceros(self):
        records = [
            _rec("calificado", "error_sistema", error_sistema=True, lead_id=1),
            _rec("revision",   "error_sistema", error_sistema=True, lead_id=2),
        ]
        m = compute_metrics(records)
        assert m["n_valid"] == 0
        assert m["n_error_sistema"] == 2
        assert m["acc_decision"] == 0.0
        assert m["acc_owner"] == 0.0

    def test_escalation_rate_excluye_errores(self):
        records = [
            _rec("revision",   "revision",      lead_id=1),
            _rec("calificado", "calificado",     lead_id=2),
            _rec("revision",   "error_sistema",  error_sistema=True, lead_id=3),
        ]
        m = compute_metrics(records)
        # 1 revision de 2 válidos
        assert m["escalation_rate"] == pytest.approx(0.5)

    def test_duplicados_excluyen_errores(self):
        # lead #1 debía ser duplicado; lo fue → TP
        # lead #2 debía ser duplicado; fue error_sistema → no cuenta como FN en dup
        records = [
            _rec("duplicado", "duplicado",     lead_id=1),
            _rec("duplicado", "error_sistema", error_sistema=True, lead_id=2),
        ]
        m = compute_metrics(records)
        assert m["tp"] == 1
        assert m["fn"] == 0   # lead #2 excluido; no contamina recall

    def test_conteo_step_limit(self):
        records = [
            _rec("calificado", "revision", step_limit=True, lead_id=1),
            _rec("calificado", "calificado", lead_id=2),
        ]
        m = compute_metrics(records)
        assert m["n_step_limit"] == 1


# ── preflight_check ───────────────────────────────────────────────────────────

class TestPreflightCheck:

    def _client(self, model_ids):
        c = MagicMock()
        c.models.list.return_value = [MagicMock(id=mid) for mid in model_ids]
        return c

    def test_modelo_disponible_no_aborta(self):
        preflight_check("model-a", "http://x/v1", "k", client=self._client(["model-a", "model-b"]))

    def test_modelo_no_disponible_aborta_con_codigo_1(self):
        with pytest.raises(SystemExit) as exc:
            preflight_check("model-x", "http://x/v1", "k", client=self._client(["model-a"]))
        assert exc.value.code == 1

    def test_conexion_fallida_aborta_con_codigo_1(self):
        c = MagicMock()
        c.models.list.side_effect = Exception("Connection refused")
        with pytest.raises(SystemExit) as exc:
            preflight_check("model-a", "http://x/v1", "k", client=c)
        assert exc.value.code == 1

    def test_lista_vacia_aborta(self):
        with pytest.raises(SystemExit) as exc:
            preflight_check("model-a", "http://x/v1", "k", client=self._client([]))
        assert exc.value.code == 1
