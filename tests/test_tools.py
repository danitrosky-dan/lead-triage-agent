"""
Tests de las herramientas del agente y de la guardia de consistencia del loop.
Requiere: pytest, rapidfuzz, pydantic.
Fixture test_db definida en conftest.py (SQLite en tmp_path).
"""

import sqlite3

import pytest
from pydantic import ValidationError

from src.agent.loop import _check_consistency
from src.agent.tools import (
    buscar_duplicado,
    calcular_score_icp,
    enriquecer_empresa,
    registrar_decision,
)


# ── buscar_duplicado ──────────────────────────────────────────────────────────

class TestBuscarDuplicado:
    def test_exacto(self, test_db):
        r = buscar_duplicado(
            "juan.perez@andinamineral.cl", "Juan Pérez", "Andina Minerales S.A.",
            db_path=test_db,
        )
        assert r["es_duplicado"] is True
        assert r["tipo"] == "exacto"
        assert r["owner"] == "Ana Torres"
        assert r["similitud"] == 100.0
        assert r["contacto"]["nombre"] == "Juan Pérez"

    def test_exacto_case_insensitive(self, test_db):
        r = buscar_duplicado(
            "JUAN.PEREZ@ANDINAMINERAL.CL", "Juan Pérez", "Andina Minerales S.A.",
            db_path=test_db,
        )
        assert r["es_duplicado"] is True
        assert r["tipo"] == "exacto"

    def test_fuzzy_typo_en_email(self, test_db):
        # "peerez" en lugar de "perez" → similitud ~96 %
        r = buscar_duplicado(
            "juan.peerez@andinamineral.cl", "Juan Pérez", "Andina Minerales S.A.",
            db_path=test_db,
        )
        assert r["es_duplicado"] is True
        assert r["tipo"] == "fuzzy"
        assert r["similitud"] >= 85.0
        assert r["owner"] == "Ana Torres"

    def test_sin_match(self, test_db):
        r = buscar_duplicado(
            "nadie@empresa-desconocida.xyz", "Persona Desconocida", "Corp Fantasma",
            db_path=test_db,
        )
        assert r["es_duplicado"] is False
        assert r["tipo"] is None
        assert r["contacto"] is None
        assert r["owner"] is None


# ── enriquecer_empresa ────────────────────────────────────────────────────────

class TestEnriquecerEmpresa:
    def test_encontrada_exacta(self, test_db):
        r = enriquecer_empresa("Andina Minerales S.A.", db_path=test_db)
        assert r["encontrada"] is True
        assert r["sector"] == "mineria"
        assert r["pais"] == "Chile"
        assert r["empleados"] == 1500
        assert r["similitud"] == 100.0

    def test_encontrada_fuzzy_sin_sufijo(self, test_db):
        # El LLM podría escribir "Andina Minerales" sin "S.A."
        r = enriquecer_empresa("Andina Minerales", db_path=test_db)
        assert r["encontrada"] is True
        assert r["sector"] == "mineria"

    def test_no_encontrada(self, test_db):
        r = enriquecer_empresa(
            "Empresa Completamente Desconocida XYZ Corp 2099", db_path=test_db
        )
        assert r["encontrada"] is False
        assert r["sector"] is None
        assert r["pais"] is None
        assert r["empleados"] is None


# ── calcular_score_icp ────────────────────────────────────────────────────────
# La nueva firma toma lead_id y nombre_empresa; lee sector/pais/empleados/cargo
# desde la DB de test. Ver conftest.py para los datos disponibles.

class TestCalcularScoreICP:
    def test_score_100_todas_dimensiones(self, test_db):
        # lead #1: Andina Minerales, Gerente General → mineria/Chile/1500 → 100
        r = calcular_score_icp(1, "Andina Minerales S.A.", db_path=test_db)
        assert r["score"] == 100
        assert r["desglose"] == {"sector": 40, "pais": 20, "tamano": 20, "cargo": 20}
        assert r["criterio_excluyente"] is None
        assert r["cargo_excluyente"] is False

    def test_criterio_excluyente_sector(self, test_db):
        # lead #4: Retail Andino → sector retail → criterio_excluyente
        r = calcular_score_icp(4, "Retail Andino", db_path=test_db)
        assert r["criterio_excluyente"] == "sector"

    def test_cargo_excluyente_practicante(self, test_db):
        # lead #5: Andina Minerales, cargo=Practicante → cargo_excluyente
        r = calcular_score_icp(5, "Andina Minerales S.A.", db_path=test_db)
        assert r["cargo_excluyente"] is True
        assert r["desglose"]["cargo"] == 0

    def test_score_parcial_sin_tamano_sin_cargo(self, test_db):
        # lead #6: Mini Minera (50 emp < 200), Coordinador Técnico → sector+pais, sin tamano ni cargo
        r = calcular_score_icp(6, "Mini Minera S.A.", db_path=test_db)
        assert r["score"] == 60
        assert r["desglose"]["tamano"] == 0
        assert r["desglose"]["cargo"] == 0

    def test_coo_no_dispara_en_coordinador(self, test_db):
        # Regresión: "coo" no debe hacer substring match con "coordinador"
        r = calcular_score_icp(6, "Mini Minera S.A.", db_path=test_db)
        assert r["desglose"]["cargo"] == 0
        assert r["score"] == 60   # sector+pais, sin tamano ni cargo

    def test_empresa_no_encontrada_devuelve_error(self, test_db):
        # nombre_empresa que no existe → error dict sin excepción
        r = calcular_score_icp(1, "Empresa Fantasma XYZ", db_path=test_db)
        assert "error" in r


# ── registrar_decision ────────────────────────────────────────────────────────

class TestRegistrarDecision:
    def test_calificado_calcula_owner_por_pais(self, test_db):
        # lead #1 → Andina Minerales S.A. → Chile → Ana Torres
        r = registrar_decision(
            1, "calificado",
            "Score 100, minería Chile, gerente general.",
            db_path=test_db,
        )
        assert r["ok"] is True
        assert r["owner"] == "Ana Torres"

    def test_revision_owner_es_cola_revision(self, test_db):
        r = registrar_decision(
            3, "revision",
            "Empresa no encontrada en CRM.",
            motivo="empresa_desconocida",
            db_path=test_db,
        )
        assert r["ok"] is True
        assert r["owner"] == "cola_revision"

    def test_duplicado_calcula_owner_del_contacto(self, test_db):
        # lead #1 tiene el mismo email que el contacto existente → owner Ana Torres
        r = registrar_decision(
            1, "duplicado",
            "Email idéntico al contacto #1 en CRM.",
            db_path=test_db,
        )
        assert r["ok"] is True
        assert r["owner"] == "Ana Torres"

    def test_descartado_owner_vacio(self, test_db):
        r = registrar_decision(
            1, "descartado",
            "Sector agricultura, criterio excluyente activo.",
            db_path=test_db,
        )
        assert r["ok"] is True
        assert r["owner"] == ""

    def test_revision_sin_motivo_lanza_error(self, test_db):
        with pytest.raises(ValidationError):
            registrar_decision(1, "revision", "sin motivo", db_path=test_db)

    def test_datos_contradictorios_sin_evidencia_lanza_error(self, test_db):
        with pytest.raises(ValidationError):
            registrar_decision(
                1, "revision", "contradicción",
                motivo="datos_contradictorios",
                db_path=test_db,
            )

    def test_decision_invalida_lanza_validation_error(self, test_db):
        with pytest.raises(ValidationError):
            registrar_decision(1, "inventada", "test", db_path=test_db)


# ── Guardia de consistencia (_check_consistency) ─────────────────────────────

def _base_state(**overrides):
    """run_state mínimo con todos los campos que espera _check_consistency."""
    state = {
        "called_tools":             [],
        "buscar_duplicado_result":  None,
        "enriquecer_empresa_result": None,
        "score_result":             None,
    }
    state.update(overrides)
    return state


class TestConsistencyGuard:

    def test_rechaza_calificado_sin_calcular_score(self):
        state = _base_state()
        args  = {"lead_id": 1, "decision": "calificado", "owner": "Ana Torres", "razonamiento": "x"}
        err   = _check_consistency(args, state)
        assert err is not None
        assert "calcular_score_icp" in err

    def test_rechaza_calificado_score_bajo_umbral(self):
        state = _base_state(
            called_tools=["calcular_score_icp"],
            score_result={"score": 40, "criterio_excluyente": None, "cargo_excluyente": False},
        )
        args = {"lead_id": 1, "decision": "calificado", "owner": "Ana Torres", "razonamiento": "x"}
        err  = _check_consistency(args, state)
        assert err is not None
        assert "40" in err

    def test_rechaza_revision_sin_motivo(self):
        # El LLM no pasa 'owner'; la guardia verifica que 'revision' lleve motivo
        state = _base_state()
        args  = {"lead_id": 1, "decision": "revision", "razonamiento": "x"}
        err   = _check_consistency(args, state)
        assert err is not None
        assert "motivo" in err

    def test_acepta_revision_con_motivo_empresa_desconocida(self):
        # revision + empresa no encontrada + motivo correcto → aceptado
        state = _base_state(
            enriquecer_empresa_result={"encontrada": False, "nombre_encontrado": None},
        )
        args = {
            "lead_id": 1, "decision": "revision", "razonamiento": "x",
            "motivo": "empresa_desconocida",
        }
        err = _check_consistency(args, state)
        assert err is None

    def test_rechaza_calificado_con_criterio_excluyente(self):
        # criterio_excluyente activo → la guardia rechaza 'calificado'
        state = _base_state(
            called_tools=["calcular_score_icp"],
            score_result={"score": 80, "criterio_excluyente": "sector", "cargo_excluyente": False},
        )
        args = {"lead_id": 1, "decision": "calificado", "razonamiento": "x"}
        err  = _check_consistency(args, state)
        assert err is not None
        assert "descartado" in err

    def test_acepta_descartado(self):
        # descartado sin restricciones adicionales → aceptado
        state = _base_state()
        args  = {"lead_id": 1, "decision": "descartado", "razonamiento": "x"}
        err   = _check_consistency(args, state)
        assert err is None

    def test_rechaza_score_en_rango_revision_si_score_sobre_umbral(self):
        # score >= UMBRAL_CALIFICADO (70) → el motivo correcto no es score_en_rango_revision
        state = _base_state(
            called_tools=["calcular_score_icp"],
            score_result={"score": 80, "criterio_excluyente": None, "cargo_excluyente": False},
        )
        args = {
            "lead_id": 1, "decision": "revision", "owner": "cola_revision",
            "razonamiento": "x", "motivo": "score_en_rango_revision",
        }
        err = _check_consistency(args, state)
        assert err is not None
        assert "calificado" in err

    def test_rechaza_empresa_desconocida_si_empresa_encontrada(self):
        # enriquecer_empresa devolvió encontrada=True → motivo empresa_desconocida inválido
        state = _base_state(
            enriquecer_empresa_result={"encontrada": True, "nombre_encontrado": "Andina Minerales S.A."},
        )
        args = {
            "lead_id": 1, "decision": "revision", "owner": "cola_revision",
            "razonamiento": "x", "motivo": "empresa_desconocida",
        }
        err = _check_consistency(args, state)
        assert err is not None
        assert "encontró" in err or "empresa_desconocida" in err

    def test_rechaza_datos_contradictorios_sin_evidencia(self):
        # datos_contradictorios sin campo evidencia → la guardia debe rechazarlo
        state = _base_state()
        args = {
            "lead_id": 1, "decision": "revision", "owner": "cola_revision",
            "razonamiento": "x", "motivo": "datos_contradictorios",
        }
        err = _check_consistency(args, state)
        assert err is not None
        assert "evidencia" in err
