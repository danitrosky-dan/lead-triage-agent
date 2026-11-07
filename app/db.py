"""
Utilidades de DB compartidas entre páginas de la app Streamlit.
"""
import sqlite3
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "crm.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


# ── Leads ─────────────────────────────────────────────────────────────────────

def get_all_leads() -> list[dict]:
    con = _connect()
    rows = con.execute("SELECT * FROM inbound_leads ORDER BY id").fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_lead(lead_id: int) -> dict | None:
    con = _connect()
    row = con.execute("SELECT * FROM inbound_leads WHERE id=?", (lead_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def insert_lead(nombre: str, email: str, cargo: str,
                empresa: str, pais: str, contenido: str) -> int:
    con = _connect()
    cur = con.execute(
        "INSERT INTO inbound_leads (nombre, email, cargo, empresa, pais, contenido) "
        "VALUES (?,?,?,?,?,?)",
        (nombre, email, cargo, empresa, pais, contenido),
    )
    con.commit()
    lead_id = cur.lastrowid
    con.close()
    return lead_id


# ── Cola de revisión ──────────────────────────────────────────────────────────

def ensure_human_overrides_schema() -> None:
    con = sqlite3.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS human_overrides (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id      INTEGER NOT NULL,
            lead_id          INTEGER NOT NULL,
            decision_humana  TEXT    NOT NULL,
            notas            TEXT,
            timestamp        TEXT    DEFAULT (datetime('now'))
        )
    """)
    con.commit()
    con.close()


def get_revision_queue() -> list[dict]:
    """Un entry por lead: la decisión de revisión más reciente sin override humano."""
    ensure_human_overrides_schema()
    con = _connect()
    rows = con.execute("""
        SELECT
            ad.id          AS decision_id,
            ad.lead_id,
            ad.motivo,
            ad.evidencia,
            ad.owner,
            ad.razonamiento,
            ad.timestamp,
            ad.run_id,
            il.nombre,
            il.email,
            il.cargo,
            il.empresa,
            il.pais,
            il.contenido
        FROM agent_decisions ad
        JOIN inbound_leads il ON il.id = ad.lead_id
        WHERE ad.decision = 'revision'
          AND ad.id = (
              SELECT MAX(id) FROM agent_decisions ad2
              WHERE ad2.lead_id = ad.lead_id
                AND ad2.decision = 'revision'
          )
          AND ad.lead_id NOT IN (
              SELECT DISTINCT lead_id FROM human_overrides
          )
        ORDER BY ad.timestamp DESC
    """).fetchall()
    con.close()
    return [dict(r) for r in rows]


def save_human_override(decision_id: int, lead_id: int,
                        decision_humana: str, notas: str = "") -> None:
    ensure_human_overrides_schema()
    con = sqlite3.connect(str(DB_PATH))
    con.execute(
        "INSERT INTO human_overrides (decision_id, lead_id, decision_humana, notas) "
        "VALUES (?,?,?,?)",
        (decision_id, lead_id, decision_humana, notas),
    )
    con.commit()
    con.close()


def get_human_overrides() -> list[dict]:
    ensure_human_overrides_schema()
    con = _connect()
    rows = con.execute("""
        SELECT ho.*, il.nombre, il.empresa
        FROM human_overrides ho
        JOIN inbound_leads il ON il.id = ho.lead_id
        ORDER BY ho.timestamp DESC
    """).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── Email drafts ──────────────────────────────────────────────────────────────

def get_email_stats() -> dict:
    con = _connect()
    by_estado = [
        dict(r) for r in con.execute(
            "SELECT estado, COUNT(*) as n, AVG(intentos) as avg_intentos "
            "FROM email_drafts GROUP BY estado"
        ).fetchall()
    ]
    total  = con.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0]
    recent = [
        dict(r) for r in con.execute(
            "SELECT ed.*, il.nombre, il.empresa, il.pais "
            "FROM email_drafts ed "
            "JOIN inbound_leads il ON il.id = ed.lead_id "
            "ORDER BY ed.id DESC LIMIT 20"
        ).fetchall()
    ]
    con.close()
    return {"by_estado": by_estado, "total": total, "recent": recent}


# ── Eval ──────────────────────────────────────────────────────────────────────

def get_test_decisions() -> list[dict]:
    """Decisión final por lead × run de los 3 runs de test (v1 congelada)."""
    con = _connect()
    rows = con.execute("""
        SELECT lead_id, decision, owner, run_id
        FROM agent_decisions
        WHERE run_id LIKE 'test_%'
        ORDER BY run_id, lead_id
    """).fetchall()
    con.close()
    return [dict(r) for r in rows]
