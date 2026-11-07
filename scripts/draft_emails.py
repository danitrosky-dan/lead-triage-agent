"""
Genera correos para todos los leads calificados de la última corrida de test.
Uso: python scripts/draft_emails.py [--run-id <id>]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.email.drafter import DB_PATH, redactar_correo  # noqa: E402


def _last_test_run(db_path: Path) -> str | None:
    con = sqlite3.connect(str(db_path))
    row = con.execute(
        "SELECT run_id FROM agent_decisions "
        "WHERE run_id LIKE 'test%' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    return row[0] if row else None


def _clear_drafts_for_run(run_id: str, db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("DELETE FROM email_drafts WHERE run_id=?", (run_id,))
        con.commit()
    except sqlite3.OperationalError:
        pass  # tabla no existe todavía
    finally:
        con.close()


def _calificados_de_run(run_id: str, db_path: Path) -> list[int]:
    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT DISTINCT lead_id FROM agent_decisions "
        "WHERE decision='calificado' AND run_id=? ORDER BY lead_id",
        (run_id,),
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None,
                        help="run_id a usar (default: última corrida test_*)")
    args = parser.parse_args()

    run_id = args.run_id or _last_test_run(DB_PATH)
    if not run_id:
        print("No se encontraron corridas de test en la base de datos.")
        sys.exit(1)

    _clear_drafts_for_run(run_id, DB_PATH)
    lead_ids = _calificados_de_run(run_id, DB_PATH)
    if not lead_ids:
        print(f"No hay leads calificados para run_id='{run_id}'.")
        sys.exit(0)

    print(f"Corrida: {run_id}")
    print(f"Leads calificados: {len(lead_ids)}\n")

    ok_primera = ok_reintento = requiere_revision = saltados = 0

    for lid in lead_ids:
        try:
            resultado = redactar_correo(lid, run_id=run_id)
        except ValueError as exc:
            print(f"  [skip] lead #{lid}: {exc}")
            saltados += 1
            continue

        tag = {
            "ok_primera":       "[ok] ",
            "ok_reintento":     "[~ok]",
            "requiere_revision": "[rev]",
        }.get(resultado.estado, "[?]  ")

        fallo_txt = f" — {resultado.fallo}" if resultado.fallo else ""
        print(f"  {tag} lead #{lid}: {resultado.estado}{fallo_txt}")

        if resultado.estado == "ok_primera":
            ok_primera += 1
        elif resultado.estado == "ok_reintento":
            ok_reintento += 1
        else:
            requiere_revision += 1

    total = ok_primera + ok_reintento + requiere_revision
    print(f"\nTotal procesados : {total}  (saltados: {saltados})")
    print(f"  Primera vez    : {ok_primera}")
    print(f"  Con reintento  : {ok_reintento}")
    print(f"  Requiere rev.  : {requiere_revision}")


if __name__ == "__main__":
    main()
