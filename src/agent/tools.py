"""
Herramientas del agente: funciones Python + schemas JSON para tool calling.

Cada herramienta expone:
  - una función Python invocable (lógica determinística)
  - un schema JSON (formato OpenAI) para que el LLM pueda pedirla

TOOLS_LIST y dispatch() son los puntos de entrada para el loop del agente.
"""

import sqlite3
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ValidationError
from rapidfuzz import fuzz, process

from .rules import (
    _ACCENT,
    _cargo_tokens,
    CARGOS_DECISORES,
    CARGOS_EXCLUYENTES_KW,
    CRITERIOS_EXCLUYENTES,
    EMPLEADOS_MINIMO,
    FALLBACK_OWNER,
    PAISES_OBJETIVO,
    ROUTING,
    SECTORES_OBJETIVO,
    calc_score,
)

# Ruta por defecto a la DB (relativa a este archivo en src/agent/)
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "crm.db"

# Umbral mínimo de similitud para declarar match fuzzy
_FUZZY_EMAIL_THRESHOLD   = 85   # fuzz.ratio sobre email
_FUZZY_EMPRESA_THRESHOLD = 75   # fuzz.token_sort_ratio sobre nombre de empresa


# ── 1. buscar_duplicado ───────────────────────────────────────────────────────

def buscar_duplicado(
    email: str,
    nombre: str,
    empresa: str,
    db_path: Path = DB_PATH,
) -> dict:
    """Detecta si el lead ya existe en crm_contacts (exacto o fuzzy por email)."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    # 1. Match exacto por email (case-insensitive)
    row = con.execute(
        "SELECT * FROM crm_contacts WHERE LOWER(email) = LOWER(?)", (email,)
    ).fetchone()
    if row:
        con.close()
        contacto = dict(row)
        return {
            "es_duplicado": True,
            "tipo": "exacto",
            "contacto": contacto,
            "owner": contacto["owner"],
            "similitud": 100.0,
        }

    # 2. Match fuzzy sobre todos los emails del CRM
    contacts = [dict(r) for r in con.execute("SELECT * FROM crm_contacts")]
    con.close()

    if not contacts:
        return {"es_duplicado": False, "tipo": None, "contacto": None, "owner": None, "similitud": 0.0}

    emails_lower = [c["email"].lower() for c in contacts]
    result = process.extractOne(email.lower(), emails_lower, scorer=fuzz.ratio)

    if result and result[1] >= _FUZZY_EMAIL_THRESHOLD:
        contacto = contacts[result[2]]
        return {
            "es_duplicado": True,
            "tipo": "fuzzy",
            "contacto": contacto,
            "owner": contacto["owner"],
            "similitud": round(result[1], 1),
        }

    best_sim = round(result[1], 1) if result else 0.0
    return {"es_duplicado": False, "tipo": None, "contacto": None, "owner": None, "similitud": best_sim}


BUSCAR_DUPLICADO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "buscar_duplicado",
        "description": (
            "Busca si el lead ya existe en el CRM comparando email (exacto o fuzzy). "
            "Llamar siempre como primera herramienta al procesar un lead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email":   {"type": "string", "description": "Email del lead inbound"},
                "nombre":  {"type": "string", "description": "Nombre completo del lead"},
                "empresa": {"type": "string", "description": "Empresa declarada por el lead"},
            },
            "required": ["email", "nombre", "empresa"],
        },
    },
}


# ── 2. enriquecer_empresa ────────────────────────────────────────────────────

def enriquecer_empresa(
    nombre_empresa: str,
    db_path: Path = DB_PATH,
) -> dict:
    """Busca la empresa en companies con matching fuzzy y devuelve sector, país y empleados."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    companies = [dict(r) for r in con.execute("SELECT * FROM companies")]
    con.close()

    if not companies:
        return {"encontrada": False, "nombre_encontrado": None, "sector": None,
                "pais": None, "empleados": None, "similitud": 0.0}

    nombres = [c["nombre"] for c in companies]
    result = process.extractOne(
        nombre_empresa, nombres, scorer=fuzz.token_sort_ratio
    )

    if result and result[1] >= _FUZZY_EMPRESA_THRESHOLD:
        comp = next(c for c in companies if c["nombre"] == result[0])
        return {
            "encontrada": True,
            "nombre_encontrado": comp["nombre"],
            "sector":    comp["sector"],
            "pais":      comp["pais"],
            "empleados": comp["empleados"],
            "similitud": round(result[1], 1),
        }

    return {
        "encontrada": False,
        "nombre_encontrado": None,
        "sector":    None,
        "pais":      None,
        "empleados": None,
        "similitud": round(result[1], 1) if result else 0.0,
    }


ENRIQUECER_EMPRESA_SCHEMA = {
    "type": "function",
    "function": {
        "name": "enriquecer_empresa",
        "description": (
            "Busca la empresa del lead en el CRM con matching fuzzy y devuelve "
            "sector, país y número de empleados. Usar antes de calcular el score ICP."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nombre_empresa": {
                    "type": "string",
                    "description": "Nombre de la empresa tal como aparece en el formulario del lead",
                },
            },
            "required": ["nombre_empresa"],
        },
    },
}


# ── 3. calcular_score_icp ────────────────────────────────────────────────────

def calcular_score_icp(
    sector: str,
    pais: str,
    empleados: int,
    cargo: str,
) -> dict:
    """Calcula el score ICP, el desglose por dimensión y los criterios excluyentes."""
    empleados = int(empleados) if empleados is not None else 0

    sector_norm = sector.lower().translate(_ACCENT) if sector else ""
    score = calc_score(sector, pais, empleados, cargo)
    desglose = {
        "sector": 40 if sector_norm and sector_norm in SECTORES_OBJETIVO else 0,
        "pais":   20 if pais and pais in PAISES_OBJETIVO else 0,
        "tamano": 20 if empleados >= EMPLEADOS_MINIMO else 0,
        "cargo":  20 if _cargo_tokens(cargo) & CARGOS_DECISORES else 0,
    }
    cargo_excluyente     = bool(_cargo_tokens(cargo) & CARGOS_EXCLUYENTES_KW)
    criterio_excluyente  = (
        "sector"
        if sector and sector_norm not in SECTORES_OBJETIVO
        else None
    )
    return {
        "score":               score,
        "desglose":            desglose,
        "criterio_excluyente": criterio_excluyente,
        "cargo_excluyente":    cargo_excluyente,
    }


CALCULAR_SCORE_ICP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calcular_score_icp",
        "description": (
            "Calcula el score ICP (0-100) del lead y el desglose por dimensión "
            "(sector, país, tamaño, cargo). También informa si hay criterios excluyentes activos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sector":    {"type": "string",  "description": "Sector de la empresa"},
                "pais":      {"type": "string",  "description": "País de la empresa"},
                "empleados": {"type": "integer", "description": "Número de empleados"},
                "cargo":     {"type": "string",  "description": "Cargo del lead"},
            },
            "required": ["sector", "pais", "empleados", "cargo"],
        },
    },
}


# ── 4. asignar_owner ─────────────────────────────────────────────────────────

def asignar_owner(
    pais: str,
    decision: str,
    owner_existente: Optional[str] = None,
) -> dict:
    """Determina el SDR responsable según país y decisión."""
    if decision == "duplicado":
        return {
            "owner": owner_existente or "",
            "razon": "duplicado: se conserva el owner del contacto existente en CRM",
        }
    if decision == "descartado":
        return {"owner": "", "razon": "descartado: sin asignación de SDR"}

    owner = ROUTING.get(pais, FALLBACK_OWNER)
    razon = (
        f"routing por país '{pais}' → {owner}"
        if pais in ROUTING
        else f"país '{pais}' sin SDR asignado → {FALLBACK_OWNER}"
    )
    return {"owner": owner, "razon": razon}


ASIGNAR_OWNER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "asignar_owner",
        "description": (
            "Determina el SDR responsable del lead según país y decisión. "
            "Para duplicados devuelve el owner del contacto existente."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pais":     {"type": "string", "description": "País del lead"},
                "decision": {
                    "type": "string",
                    "enum": ["calificado", "revision", "descartado", "duplicado"],
                },
                "owner_existente": {
                    "type": "string",
                    "description": "Owner actual si el lead es duplicado (opcional)",
                },
            },
            "required": ["pais", "decision"],
        },
    },
}


# ── 5. registrar_decision ────────────────────────────────────────────────────

class _DecisionRecord(BaseModel):
    lead_id:      int
    decision:     Literal["calificado", "revision", "descartado", "duplicado"]
    owner:        str
    razonamiento: str


def registrar_decision(
    lead_id: int,
    decision: str,
    owner: str,
    razonamiento: str,
    db_path: Path = DB_PATH,
) -> dict:
    """Valida con Pydantic y persiste la decisión del agente en agent_decisions."""
    record = _DecisionRecord(
        lead_id=lead_id, decision=decision, owner=owner, razonamiento=razonamiento
    )

    con = sqlite3.connect(str(db_path))
    con.execute("""
        CREATE TABLE IF NOT EXISTS agent_decisions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id      INTEGER NOT NULL,
            decision     TEXT    NOT NULL,
            owner        TEXT    NOT NULL,
            razonamiento TEXT    NOT NULL,
            timestamp    TEXT    DEFAULT (datetime('now'))
        )
    """)
    cur = con.execute(
        "INSERT INTO agent_decisions (lead_id, decision, owner, razonamiento) VALUES (?,?,?,?)",
        (record.lead_id, record.decision, record.owner, record.razonamiento),
    )
    con.commit()
    decision_id = cur.lastrowid
    con.close()
    return {"ok": True, "decision_id": decision_id}


REGISTRAR_DECISION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "registrar_decision",
        "description": (
            "Registra la decisión final del agente con trazabilidad completa. "
            "Llamar siempre al finalizar el triage de un lead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id":  {"type": "integer", "description": "ID del lead en inbound_leads"},
                "decision": {
                    "type": "string",
                    "enum": ["calificado", "revision", "descartado", "duplicado"],
                },
                "owner": {
                    "type": "string",
                    "description": "SDR asignado; vacío si descartado",
                },
                "razonamiento": {
                    "type": "string",
                    "description": (
                        "Explicación del agente: qué herramientas usó, qué encontró "
                        "y por qué tomó esta decisión"
                    ),
                },
            },
            "required": ["lead_id", "decision", "owner", "razonamiento"],
        },
    },
}


# ── Dispatch ──────────────────────────────────────────────────────────────────

TOOLS_LIST = [
    BUSCAR_DUPLICADO_SCHEMA,
    ENRIQUECER_EMPRESA_SCHEMA,
    CALCULAR_SCORE_ICP_SCHEMA,
    ASIGNAR_OWNER_SCHEMA,
    REGISTRAR_DECISION_SCHEMA,
]

_FN_MAP = {
    "buscar_duplicado":   buscar_duplicado,
    "enriquecer_empresa": enriquecer_empresa,
    "calcular_score_icp": calcular_score_icp,
    "asignar_owner":      asignar_owner,
    "registrar_decision": registrar_decision,
}
_DB_TOOLS = {"buscar_duplicado", "enriquecer_empresa", "registrar_decision"}


def dispatch(name: str, args: dict, db_path: Path = DB_PATH) -> dict:
    """Enruta una tool call del LLM a la función Python correspondiente."""
    fn = _FN_MAP[name]
    if name in _DB_TOOLS:
        return fn(**args, db_path=db_path)
    return fn(**args)
