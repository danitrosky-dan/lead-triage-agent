"""
Segunda etapa del agente: redactar correos para leads calificados.
Independiente del loop de triage (v1 congelada).
"""

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Literal, Optional

import yaml
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, model_validator
from rapidfuzz import fuzz, process

_ROOT        = Path(__file__).resolve().parent.parent.parent
DB_PATH      = _ROOT / "data" / "crm.db"
_PROMPT_PATH = _ROOT / "prompts" / "email_prompt.md"
_CONFIG_PATH = _ROOT / "config" / "business_rules.yaml"
_MODEL_ENV   = "MODEL_ID"
TEMPERATURE  = 0.6
TOP_P        = 0.95

_FUZZY_EMPRESA_THRESHOLD = 75
_ACCENT = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")

# Sufijos legales normalizados (minúsculas, sin tildes) que se ignoran
# en la validación de mención de empresa.
_LEGAL_SUFFIXES = {
    "s.a.", "s.a",
    "spa",           # SpA
    "ltda.", "ltda",
    "s.a.c.",        # Sociedad Anónima Cerrada (Perú)
    "s.r.l.", "s.r.l",
    "corp.", "corp",
    "inc.", "inc",
    "c.v.",          # S.A. de C.V. (México)
    "de",            # partícula en "S.A. de C.V."
}


# ── Config desde YAML ─────────────────────────────────────────────────────────

def _load_email_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        email = (data or {}).get("email") or {}
        return {
            "cta_duracion_minutos": int(email.get("cta_duracion_minutos", 20)),
            "max_palabras":         int(email.get("max_palabras", 120)),
            "max_palabras_asunto":  int(email.get("max_palabras_asunto", 8)),
        }
    except Exception:
        return {"cta_duracion_minutos": 20, "max_palabras": 120, "max_palabras_asunto": 8}


_EMAIL_CFG = _load_email_config()


# ── Pydantic models ───────────────────────────────────────────────────────────

class EmailDraft(BaseModel):
    asunto: str
    cuerpo: str

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.asunto.strip():
            raise ValueError("asunto vacío")
        if not self.cuerpo.strip():
            raise ValueError("cuerpo vacío")
        return self


EstadoBorrador = Literal["ok_primera", "ok_reintento", "requiere_revision"]


class ResultadoBorrador(BaseModel):
    lead_id:  int
    asunto:   Optional[str]
    cuerpo:   Optional[str]
    estado:   EstadoBorrador
    intentos: int
    fallo:    Optional[str] = None


# ── Validaciones determinísticas ──────────────────────────────────────────────

_PT_MARKERS = {"você", "vocês", "prezado", "prezada"}
_ES_MARKERS = {"usted", "estimado", "estimada"}


def _check_word_count(cuerpo: str) -> Optional[str]:
    n     = len(cuerpo.split())
    limit = _EMAIL_CFG["max_palabras"]
    if n > limit:
        return f"cuerpo tiene {n} palabras (máximo {limit})"
    return None


def _check_subject_words(asunto: str) -> Optional[str]:
    n     = len(asunto.split())
    limit = _EMAIL_CFG["max_palabras_asunto"]
    if n > limit:
        return f"asunto tiene {n} palabras (máximo {limit})"
    return None


def _check_language(text: str, pais: str) -> Optional[str]:
    lower = text.lower()
    if pais == "Brasil":
        for marker in _ES_MARKERS:
            if marker in lower:
                return f"idioma incorrecto: '{marker}' en correo para Brasil (usar portugués)"
    else:
        for marker in _PT_MARKERS:
            if marker in lower:
                return f"idioma incorrecto: '{marker}' en correo para país no-Brasil (usar español)"
    return None


def _norm(s: str) -> str:
    """Lowercase + strip accents; usado para comparaciones case/accent-insensitive."""
    return s.lower().translate(_ACCENT)


def _check_mentions_empresa(text: str, empresa: str) -> Optional[str]:
    """Verifica que el cuerpo mencione la empresa (sin tildes, sin sufijos legales)."""
    tokens    = [_norm(t) for t in empresa.split() if _norm(t) not in _LEGAL_SUFFIXES]
    text_norm = _norm(text)
    if tokens and not any(t in text_norm for t in tokens):
        return f"el correo no menciona la empresa '{empresa}'"
    return None


def _check_firma(cuerpo: str, owner: Optional[str]) -> Optional[str]:
    if not owner:
        return None
    if _norm(owner) not in _norm(cuerpo):
        return f"firma incorrecta: no aparece el nombre del SDR '{owner}'"
    return None


def _check_no_fabricated_numbers(text: str, input_values: list) -> Optional[str]:
    input_text    = " ".join(str(v) for v in input_values if v is not None)
    input_numbers = set(re.findall(r"\d+", input_text))
    text_numbers  = set(re.findall(r"\d+", text))
    fabricated    = text_numbers - input_numbers
    if fabricated:
        return f"cifras no presentes en los datos de entrada: {sorted(fabricated)}"
    return None


def validate_draft(
    draft: EmailDraft,
    pais: str,
    empresa: str,
    owner: Optional[str],
    input_values: list,
) -> Optional[str]:
    """Aplica todas las validaciones; devuelve la descripción del primer fallo o None."""
    full_text = draft.asunto + " " + draft.cuerpo
    checks = [
        _check_word_count(draft.cuerpo),
        _check_subject_words(draft.asunto),
        _check_language(full_text, pais),
        _check_mentions_empresa(draft.cuerpo, empresa),
        _check_firma(draft.cuerpo, owner),
        _check_no_fabricated_numbers(full_text, input_values),
    ]
    return next((c for c in checks if c), None)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_email_drafts_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS email_drafts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id   INTEGER NOT NULL,
            run_id    TEXT,
            asunto    TEXT,
            cuerpo    TEXT,
            estado    TEXT NOT NULL,
            intentos  INTEGER NOT NULL DEFAULT 1,
            fallo     TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)


def _save_draft(resultado: ResultadoBorrador, run_id: Optional[str], db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    _ensure_email_drafts_schema(con)
    con.execute(
        "INSERT INTO email_drafts (lead_id, run_id, asunto, cuerpo, estado, intentos, fallo) "
        "VALUES (?,?,?,?,?,?,?)",
        (resultado.lead_id, run_id, resultado.asunto, resultado.cuerpo,
         resultado.estado, resultado.intentos, resultado.fallo),
    )
    con.commit()
    con.close()


def _read_lead_data(lead_id: int, db_path: Path) -> Optional[dict]:
    """Lee datos del lead, empresa (fuzzy match) y owner desde la última decisión calificado."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        lead = con.execute(
            "SELECT * FROM inbound_leads WHERE id=?", (lead_id,)
        ).fetchone()
        if not lead:
            return None
        lead = dict(lead)

        decision_row = con.execute(
            "SELECT decision, owner FROM agent_decisions "
            "WHERE lead_id=? AND decision='calificado' ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        if not decision_row:
            return None

        companies = [dict(r) for r in con.execute(
            "SELECT nombre, sector, pais, empleados FROM companies"
        )]
    finally:
        con.close()

    owner: str = decision_row["owner"]
    empresa_data: dict = {}
    if companies:
        result = process.extractOne(
            lead["empresa"],
            [c["nombre"] for c in companies],
            scorer=fuzz.token_sort_ratio,
        )
        if result and result[1] >= _FUZZY_EMPRESA_THRESHOLD:
            comp = next(c for c in companies if c["nombre"] == result[0])
            empresa_data = {
                "sector":    comp["sector"],
                "pais":      comp["pais"],
                "empleados": comp["empleados"],
            }

    return {**lead, "owner": owner, "empresa_data": empresa_data}


# ── LLM helpers ───────────────────────────────────────────────────────────────

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        load_dotenv(_ROOT / ".env")
        _client = OpenAI(
            base_url=os.environ["OMLX_BASE_URL"],
            api_key=os.environ["OMLX_API_KEY"],
        )
    return _client


def _build_user_message(data: dict, fallo_previo: Optional[str] = None) -> str:
    comp     = data.get("empresa_data", {})
    cta_min  = _EMAIL_CFG["cta_duracion_minutos"]
    lines = [
        "Lead:",
        f"- Nombre: {data['nombre']}",
        f"- Cargo: {data['cargo']}",
        f"- Empresa: {data['empresa']}",
        f"- País: {data['pais']}",
        f"- Contenido descargado: {data.get('contenido', '')}",
        "",
        "Empresa:",
        f"- Sector: {comp.get('sector', 'desconocido')}",
        f"- Empleados: {comp.get('empleados', 'desconocido')}",
        "",
        f"SDR asignado: {data['owner']}",
        f"Duración propuesta para la llamada: {cta_min} minutos",
        "",
        'Responde ÚNICAMENTE con JSON sin markdown: {"asunto": "...", "cuerpo": "..."}',
    ]
    if fallo_previo:
        lines += ["", f"INTENTO ANTERIOR FALLÓ. Corrígelo: {fallo_previo}"]
    return "\n".join(lines)


def _call_llm(user_message: str, system_prompt: str, client: OpenAI) -> Optional[EmailDraft]:
    response = client.chat.completions.create(
        model=os.environ[_MODEL_ENV],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        temperature=TEMPERATURE,
        top_p=TOP_P,
    )
    raw = response.choices[0].message.content or ""
    try:
        return EmailDraft(**json.loads(raw))
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return EmailDraft(**json.loads(match.group()))
    except Exception:
        return None


# ── Función principal ─────────────────────────────────────────────────────────

def redactar_correo(
    lead_id: int,
    run_id: Optional[str] = None,
    db_path: Path = DB_PATH,
    client: Optional[OpenAI] = None,
) -> ResultadoBorrador:
    """
    Redacta el correo para un lead calificado.
    Lanza ValueError si el lead no existe o no tiene decisión 'calificado'.
    Guarda el borrador en email_drafts y lo devuelve.
    """
    if client is None:
        client = _get_client()

    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    data = _read_lead_data(lead_id, db_path)
    if data is None:
        raise ValueError(
            f"lead_id={lead_id} no encontrado o sin decisión 'calificado'"
        )

    pais         = data["pais"]
    empresa      = data["empresa"]
    owner        = data["owner"]
    comp         = data.get("empresa_data", {})
    input_values = [
        data.get("nombre"), data.get("email"), data.get("cargo"),
        empresa, pais, data.get("contenido"),
        comp.get("sector"), comp.get("empleados"),
        _EMAIL_CFG["cta_duracion_minutos"],   # permite el número de la duración de llamada
    ]

    # ── Intento 1 ─────────────────────────────────────────────────────────────
    draft1 = _call_llm(_build_user_message(data), system_prompt, client)
    fallo1: Optional[str] = (
        "el modelo no devolvió JSON válido" if draft1 is None
        else validate_draft(draft1, pais, empresa, owner, input_values)
    )

    if fallo1 is None:
        resultado = ResultadoBorrador(
            lead_id=lead_id, asunto=draft1.asunto, cuerpo=draft1.cuerpo,
            estado="ok_primera", intentos=1,
        )
        _save_draft(resultado, run_id, db_path)
        return resultado

    # ── Intento 2 (reintento con fallo indicado) ──────────────────────────────
    draft2 = _call_llm(_build_user_message(data, fallo_previo=fallo1), system_prompt, client)
    fallo2: Optional[str] = (
        "el modelo no devolvió JSON válido" if draft2 is None
        else validate_draft(draft2, pais, empresa, owner, input_values)
    )

    if fallo2 is None:
        resultado = ResultadoBorrador(
            lead_id=lead_id, asunto=draft2.asunto, cuerpo=draft2.cuerpo,
            estado="ok_reintento", intentos=2,
        )
        _save_draft(resultado, run_id, db_path)
        return resultado

    # ── Ambos intentos fallaron ───────────────────────────────────────────────
    best = draft2 or draft1
    resultado = ResultadoBorrador(
        lead_id=lead_id,
        asunto=best.asunto if best else None,
        cuerpo=best.cuerpo if best else None,
        estado="requiere_revision",
        intentos=2,
        fallo=fallo2,
    )
    _save_draft(resultado, run_id, db_path)
    return resultado
