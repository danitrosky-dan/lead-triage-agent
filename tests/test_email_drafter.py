"""
Tests de las validaciones determinísticas del redactor de correos.
No requieren LLM ni servidor; solo Python puro y SQLite en tmp_path.
"""

import sqlite3

import pytest
from pydantic import ValidationError

from src.email.drafter import (
    EmailDraft,
    ResultadoBorrador,
    _EMAIL_CFG,
    _check_firma,
    _check_language,
    _check_mentions_empresa,
    _check_no_fabricated_numbers,
    _check_subject_words,
    _check_word_count,
    _ensure_email_drafts_schema,
    _save_draft,
    validate_draft,
)


# ── _check_word_count ─────────────────────────────────────────────────────────

class TestWordCount:
    def test_dentro_del_limite(self):
        limit = _EMAIL_CFG["max_palabras"]
        assert _check_word_count(" ".join(["x"] * limit)) is None

    def test_excede_limite(self):
        limit = _EMAIL_CFG["max_palabras"]
        assert _check_word_count(" ".join(["x"] * (limit + 1))) is not None

    def test_reporta_numero_de_palabras(self):
        limit = _EMAIL_CFG["max_palabras"]
        result = _check_word_count(" ".join(["x"] * (limit + 10)))
        assert result is not None
        assert str(limit + 10) in result


# ── _check_subject_words ──────────────────────────────────────────────────────

class TestSubjectWords:
    def test_dentro_del_limite(self):
        limit = _EMAIL_CFG["max_palabras_asunto"]
        assert _check_subject_words(" ".join(["x"] * limit)) is None

    def test_excede_limite(self):
        limit = _EMAIL_CFG["max_palabras_asunto"]
        assert _check_subject_words(" ".join(["x"] * (limit + 1))) is not None

    def test_reporta_numero_de_palabras(self):
        result = _check_subject_words(" ".join(["x"] * 10))
        assert result is not None
        assert "10" in result


# ── _check_language ───────────────────────────────────────────────────────────

class TestLanguage:
    def test_espanol_ok_para_no_brasil(self):
        assert _check_language("estimado señor, nuestros servicios para usted", "Chile") is None

    def test_portugues_detectado_para_no_brasil(self):
        result = _check_language("você pode nos contatar", "Chile")
        assert result is not None
        assert "você" in result

    def test_prezado_detectado_para_no_brasil(self):
        result = _check_language("Prezado Carlos, vim conferir", "Peru")
        assert result is not None

    def test_portugues_ok_para_brasil(self):
        assert _check_language("você pode nos contatar prezado", "Brasil") is None

    def test_espanol_detectado_para_brasil(self):
        result = _check_language("estimado señor, para usted nuestros servicios", "Brasil")
        assert result is not None

    def test_texto_neutro_pasa_en_ambos(self):
        neutro = "Hola, gracias por su interés en nuestra empresa y sector."
        assert _check_language(neutro, "Chile") is None
        assert _check_language(neutro, "Brasil") is None


# ── _check_mentions_empresa ───────────────────────────────────────────────────

class TestMentionsEmpresa:
    def test_menciona_empresa(self):
        assert _check_mentions_empresa(
            "Hola, vi que trabaja en Andina Minerales", "Andina Minerales S.A."
        ) is None

    def test_no_menciona_empresa(self):
        result = _check_mentions_empresa("Hola, cómo estás hoy", "Andina Minerales S.A.")
        assert result is not None

    def test_menciona_token_parcial(self):
        assert _check_mentions_empresa(
            "Vi que trabaja en Patagonia Wind.", "Patagonia Wind S.A."
        ) is None

    def test_empresa_solo_sufijo_legal_no_falla(self):
        # Sin tokens que verificar → no puede fallar
        assert _check_mentions_empresa("cualquier texto", "S.A.") is None

    def test_case_insensitive(self):
        assert _check_mentions_empresa(
            "solar austral es líder en renovables", "Solar Austral S.A."
        ) is None


# ── _check_firma ──────────────────────────────────────────────────────────────

class TestFirma:
    def test_firma_correcta(self):
        cuerpo = "...atentamente,\nAna Torres\nSDR LatAm"
        assert _check_firma(cuerpo, "Ana Torres") is None

    def test_firma_con_tilde_normalizada(self):
        # El cuerpo escribe "Luis Mendez" sin tilde, owner tiene "Luis Méndez"
        cuerpo = "...saludos,\nLuis Mendez"
        assert _check_firma(cuerpo, "Luis Méndez") is None

    def test_firma_incorrecta(self):
        cuerpo = "...atentamente,\nLuis Méndez\nSDR LatAm"
        result = _check_firma(cuerpo, "Ana Torres")
        assert result is not None
        assert "Ana Torres" in result

    def test_owner_vacio_no_falla(self):
        assert _check_firma("cualquier texto", "") is None

    def test_owner_none_no_falla(self):
        assert _check_firma("cualquier texto", None) is None


# ── _check_no_fabricated_numbers ─────────────────────────────────────────────

class TestFabricatedNumbers:
    def test_sin_cifras(self):
        assert _check_no_fabricated_numbers("texto sin números", ["valor"]) is None

    def test_cifra_de_entrada_ok(self):
        assert _check_no_fabricated_numbers("tienen 1500 empleados", [1500]) is None

    def test_cifra_inventada(self):
        result = _check_no_fabricated_numbers("30% de ahorro comprobado", ["empresa"])
        assert result is not None
        assert "30" in result

    def test_cifra_en_contenido_ok(self):
        assert _check_no_fabricated_numbers("Informe 2024", ["Informe 2024"]) is None

    def test_cifra_de_empleados_entero_ok(self):
        assert _check_no_fabricated_numbers("equipo de 400 personas", [400]) is None

    def test_varias_cifras_una_inventada(self):
        # 1500 está en inputs, 99 no
        result = _check_no_fabricated_numbers(
            "con 1500 empleados y 99 proyectos activos", [1500, "Chile"]
        )
        assert result is not None
        assert "99" in result


# ── validate_draft (integración de todas las validaciones) ───────────────────

class TestValidateDraft:
    def _make_ok_draft(self):
        return EmailDraft(
            asunto="Oportunidad para Andina Minerales",
            cuerpo=(
                "Vi que descargó nuestro whitepaper sobre minería en Chile. "
                "Para empresas del sector como Andina Minerales, "
                "podemos aportar inteligencia de mercado accionable. "
                "¿Tiene disponibilidad esta semana para conversar?\n\n"
                "Ana Torres"
            ),
        )

    def test_borrador_valido_pasa(self):
        draft = self._make_ok_draft()
        result = validate_draft(
            draft, "Chile", "Andina Minerales S.A.", "Ana Torres",
            ["whitepaper", 1500, "mineria", "Chile"],
        )
        assert result is None

    def test_falla_por_longitud_cuerpo(self):
        cuerpo = "Ana Torres Andina Minerales " + "palabra " * 120
        draft = EmailDraft(asunto="Asunto corto", cuerpo=cuerpo)
        result = validate_draft(draft, "Chile", "Andina Minerales S.A.", "Ana Torres", [])
        assert result is not None

    def test_falla_por_asunto_largo(self):
        draft = EmailDraft(
            asunto="una dos tres cuatro cinco seis siete ocho nueve",
            cuerpo="Ana Torres Andina Minerales breve texto.",
        )
        result = validate_draft(draft, "Chile", "Andina Minerales S.A.", "Ana Torres", [])
        assert result is not None

    def test_falla_por_idioma_portugues_en_espanol(self):
        draft = EmailDraft(
            asunto="Oportunidad",
            cuerpo="Você pode entrar em contato. Andina Minerales. Ana Torres",
        )
        result = validate_draft(draft, "Chile", "Andina Minerales S.A.", "Ana Torres", [])
        assert result is not None

    def test_falla_por_empresa_no_mencionada(self):
        draft = EmailDraft(
            asunto="Oportunidad en minería",
            cuerpo="Gran oportunidad para su empresa en el sector.\n\nAna Torres",
        )
        result = validate_draft(draft, "Chile", "Andina Minerales S.A.", "Ana Torres", [])
        assert result is not None

    def test_falla_por_firma_incorrecta(self):
        draft = EmailDraft(
            asunto="Oportunidad",
            cuerpo="Texto breve con Andina Minerales.\n\nLuis Méndez",
        )
        result = validate_draft(draft, "Chile", "Andina Minerales S.A.", "Ana Torres", [])
        assert result is not None

    def test_falla_por_cifra_inventada(self):
        draft = EmailDraft(
            asunto="Oportunidad",
            cuerpo="Andina Minerales puede reducir costos en 35%.\n\nAna Torres",
        )
        result = validate_draft(draft, "Chile", "Andina Minerales S.A.", "Ana Torres", [])
        assert result is not None


# ── Tests solicitados explícitamente ─────────────────────────────────────────

class TestNuevosRequisitos:
    def test_cta_duracion_de_config_no_es_fabricada(self):
        # cta_duracion_minutos (20) está en input_values → "20 minutos" debe pasar
        cta = _EMAIL_CFG["cta_duracion_minutos"]
        result = _check_no_fabricated_numbers(
            f"propongo una llamada de {cta} minutos", [cta]
        )
        assert result is None

    def test_cifra_inventada_crecimiento_se_rechaza(self):
        result = _check_no_fabricated_numbers(
            "crecimiento de 35% en el sector", ["empresa", "Chile"]
        )
        assert result is not None
        assert "35" in result

    def test_solar_austral_aprobado_para_sa(self):
        # "Solar Austral" en texto debe aprobar empresa "Solar Austral S.A."
        assert _check_mentions_empresa(
            "Solar Austral es líder en renovables", "Solar Austral S.A."
        ) is None

    def test_normalizacion_sin_tilde_aprobado(self):
        # Texto sin tilde debe aprobar empresa con tilde
        assert _check_mentions_empresa(
            "Cordoba Mineria lidera el sector", "Córdoba Minería S.A."
        ) is None


# ── EmailDraft: validación Pydantic ──────────────────────────────────────────

class TestEmailDraftModel:
    def test_asunto_vacio_lanza_error(self):
        with pytest.raises(ValidationError):
            EmailDraft(asunto="   ", cuerpo="Cuerpo válido")

    def test_cuerpo_vacio_lanza_error(self):
        with pytest.raises(ValidationError):
            EmailDraft(asunto="Asunto válido", cuerpo="")

    def test_draft_valido(self):
        d = EmailDraft(asunto="Hola", cuerpo="Texto")
        assert d.asunto == "Hola"
        assert d.cuerpo == "Texto"


# ── _save_draft + _ensure_email_drafts_schema ─────────────────────────────────

class TestSaveDraft:
    def test_save_ok_primera(self, tmp_path):
        db = tmp_path / "test.db"
        resultado = ResultadoBorrador(
            lead_id=1, asunto="Asunto", cuerpo="Cuerpo",
            estado="ok_primera", intentos=1,
        )
        _save_draft(resultado, run_id="r1", db_path=db)
        con = sqlite3.connect(str(db))
        row = con.execute("SELECT * FROM email_drafts WHERE lead_id=1").fetchone()
        con.close()
        assert row is not None
        # (id, lead_id, run_id, asunto, cuerpo, estado, intentos, fallo, timestamp)
        assert row[3] == "Asunto"
        assert row[4] == "Cuerpo"
        assert row[5] == "ok_primera"
        assert row[6] == 1
        assert row[7] is None

    def test_save_requiere_revision_con_fallo(self, tmp_path):
        db = tmp_path / "test.db"
        resultado = ResultadoBorrador(
            lead_id=2, asunto=None, cuerpo=None,
            estado="requiere_revision", intentos=2, fallo="asunto muy largo",
        )
        _save_draft(resultado, run_id=None, db_path=db)
        con = sqlite3.connect(str(db))
        row = con.execute("SELECT * FROM email_drafts WHERE lead_id=2").fetchone()
        con.close()
        assert row is not None
        assert row[5] == "requiere_revision"
        assert row[6] == 2
        assert row[7] == "asunto muy largo"

    def test_schema_idempotente(self, tmp_path):
        db = tmp_path / "test.db"
        con = sqlite3.connect(str(db))
        _ensure_email_drafts_schema(con)
        _ensure_email_drafts_schema(con)  # segunda llamada no debe fallar
        con.close()
