"""
Tests de las herramientas del agente.
Requiere: pytest, rapidfuzz, pydantic.
Fixture test_db definida en conftest.py (SQLite en tmp_path).
"""

import sqlite3

import pytest
from pydantic import ValidationError

from src.agent.tools import (
    asignar_owner,
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

class TestCalcularScoreICP:
    def test_score_100_todas_dimensiones(self):
        r = calcular_score_icp("mineria", "Chile", 1500, "Gerente General")
        assert r["score"] == 100
        assert r["desglose"] == {"sector": 40, "pais": 20, "tamano": 20, "cargo": 20}
        assert r["criterio_excluyente"] is None
        assert r["cargo_excluyente"] is False

    def test_criterio_excluyente_sector(self):
        r = calcular_score_icp("retail", "Chile", 1500, "Gerente General")
        assert r["criterio_excluyente"] == "sector"

    def test_cargo_excluyente_estudiante(self):
        r = calcular_score_icp("mineria", "Chile", 1500, "Estudiante")
        assert r["cargo_excluyente"] is True
        assert r["desglose"]["cargo"] == 0

    def test_score_parcial_sin_tamano_sin_cargo(self):
        # sector+pais OK, empresa pequeña, cargo no decisor
        r = calcular_score_icp("mineria", "Chile", 50, "Analista Senior")
        assert r["score"] == 60
        assert r["desglose"]["tamano"] == 0
        assert r["desglose"]["cargo"] == 0

    def test_coo_no_dispara_en_coordinador(self):
        # Regresión: "coo" no debe hacer substring match con "coordinador"
        r = calcular_score_icp("mineria", "Chile", 1500, "Coordinador Técnico")
        assert r["desglose"]["cargo"] == 0
        assert r["score"] == 80   # sector+pais+tamano, sin cargo


# ── asignar_owner ─────────────────────────────────────────────────────────────

class TestAsignarOwner:
    def test_calificado_chile(self):
        r = asignar_owner("Chile", "calificado")
        assert r["owner"] == "Ana Torres"

    def test_calificado_peru(self):
        r = asignar_owner("Peru", "calificado")
        assert r["owner"] == "Luis Méndez"

    def test_duplicado_usa_owner_existente(self):
        r = asignar_owner("Chile", "duplicado", owner_existente="Luis Méndez")
        assert r["owner"] == "Luis Méndez"

    def test_descartado_sin_owner(self):
        r = asignar_owner("Chile", "descartado")
        assert r["owner"] == ""

    def test_pais_sin_sdr_fallback(self):
        r = asignar_owner("España", "calificado")
        assert r["owner"] == "cola_revision"


# ── registrar_decision ────────────────────────────────────────────────────────

class TestRegistrarDecision:
    def test_guarda_y_recupera(self, test_db):
        r = registrar_decision(
            42, "calificado", "Ana Torres",
            "Lead ICP: minería chilena, gerente general, 1500 empleados.",
            db_path=test_db,
        )
        assert r["ok"] is True
        assert isinstance(r["decision_id"], int)

        con = sqlite3.connect(str(test_db))
        row = con.execute(
            "SELECT * FROM agent_decisions WHERE lead_id = 42"
        ).fetchone()
        con.close()
        assert row is not None
        assert row[2] == "calificado"   # columna decision
        assert row[3] == "Ana Torres"   # columna owner

    def test_decision_invalida_lanza_validation_error(self, test_db):
        with pytest.raises(ValidationError):
            registrar_decision(
                1, "inventada", "Ana Torres", "test", db_path=test_db
            )
