import sqlite3
import sys
from pathlib import Path

import pytest

# Permite importar src.agent.* desde los tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def test_db(tmp_path_factory):
    """Base de datos SQLite mínima para tests: 3 empresas, 2 contactos CRM."""
    db = tmp_path_factory.mktemp("db") / "test.db"
    con = sqlite3.connect(str(db))
    con.executescript("""
        CREATE TABLE companies (
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL,
            sector TEXT, pais TEXT, empleados INTEGER, dominio TEXT
        );
        CREATE TABLE crm_contacts (
            id INTEGER PRIMARY KEY, nombre TEXT, email TEXT UNIQUE,
            cargo TEXT, empresa TEXT, pais TEXT, owner TEXT
        );
        CREATE TABLE inbound_leads (
            id INTEGER PRIMARY KEY, nombre TEXT, email TEXT,
            cargo TEXT, empresa TEXT, pais TEXT, contenido TEXT
        );
    """)
    con.executemany("INSERT INTO companies VALUES (?,?,?,?,?,?)", [
        (1, "Andina Minerales S.A.", "mineria",        "Chile",  1500, "andinamineral.cl"),
        (2, "Solar Austral S.A.",    "energia",         "Chile",   400, "solaraustral.cl"),
        (3, "Retail Andino",         "retail",          "Peru",   1200, "retailandino.com"),
    ])
    con.executemany("INSERT INTO crm_contacts VALUES (?,?,?,?,?,?,?)", [
        (1, "Juan Pérez",    "juan.perez@andinamineral.cl",   "Gerente General",  "Andina Minerales S.A.", "Chile", "Ana Torres"),
        (2, "María González","maria.gonzalez@solaraustral.cl","Directora Técnica","Solar Austral S.A.",    "Chile", "Ana Torres"),
    ])
    # Leads inbound para tests de registrar_decision (owner calculado desde DB)
    con.executemany("INSERT INTO inbound_leads VALUES (?,?,?,?,?,?,?)", [
        (1, "Juan Pérez",    "juan.perez@andinamineral.cl",   "Gerente General",  "Andina Minerales S.A.", "Chile", "Whitepaper"),
        (2, "María González","maria.gonzalez@solaraustral.cl","Directora Técnica","Solar Austral S.A.",    "Chile", "Guía"),
        (3, "Pedro Ramírez", "pedro@empresa-desconocida.xyz", "Consultor",        "Corp Fantasma",         "México","Reporte"),
    ])
    con.commit()
    con.close()
    return db
