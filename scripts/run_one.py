"""
Corre el agente sobre un único lead e imprime, por cada llamada al modelo:
  - tokens de reasoning_content, completion, prompt y total
  - tiempo de la llamada
  - finish_reason
Además muestra los parámetros exactos que se envían y el resumen de pasos.

Uso: python scripts/run_one.py --lead_id 57
"""
import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
os.environ.setdefault("MODEL_ID", os.environ.get("MODEL_ID", "Qwen3.6-35B-A3B-4bit"))

parser = argparse.ArgumentParser()
parser.add_argument("--lead_id", type=int, required=True)
cli = parser.parse_args()

from src.agent.loop import TEMPERATURE, TOP_P, _client, run_agent  # noqa: E402
from src.agent.tools import DB_PATH  # noqa: E402

# ── Cargar lead ───────────────────────────────────────────────────────────────
con = sqlite3.connect(str(DB_PATH))
con.row_factory = sqlite3.Row
row = con.execute("SELECT * FROM inbound_leads WHERE id=?", (cli.lead_id,)).fetchone()
con.close()
if row is None:
    sys.exit(f"Lead #{cli.lead_id} no encontrado.")
lead = dict(row)

# ── Parámetros que se envían ──────────────────────────────────────────────────
print(f"\n{'─'*60}")
print(f"  Lead #{cli.lead_id}: {lead['nombre']} / {lead['empresa']}")
print(f"{'─'*60}")
print(f"  Parámetros de llamada al modelo:")
print(f"    temperature : {TEMPERATURE}")
print(f"    top_p       : {TOP_P}")
print(f"    max_tokens  : (no enviado — usa el default del servidor)")
print(f"{'─'*60}\n")

# ── Monkey-patch para instrumentar cada llamada ───────────────────────────────
call_log: list[dict] = []
_orig_create = _client.chat.completions.create

def _instrumented_create(**kwargs):
    t0 = time.time()
    response = _orig_create(**kwargs)
    elapsed = round(time.time() - t0, 2)

    choice  = response.choices[0]
    usage   = response.usage
    raw_msg = choice.message.model_dump()

    reasoning_text = raw_msg.get("reasoning_content") or ""
    # Aproximación de tokens de reasoning si el servidor no los reporta aparte
    reasoning_tokens = (
        getattr(usage, "completion_tokens_details", None) and
        getattr(usage.completion_tokens_details, "reasoning_tokens", None)
    ) or len(reasoning_text.split())

    entry = {
        "finish_reason":     choice.finish_reason,
        "reasoning_tokens":  reasoning_tokens,
        "completion_tokens": usage.completion_tokens,
        "prompt_tokens":     usage.prompt_tokens,
        "total_tokens":      usage.total_tokens,
        "elapsed_s":         elapsed,
        "n_tool_calls":      len(choice.message.tool_calls or []),
    }
    call_log.append(entry)

    n = len(call_log)
    print(f"  Llamada #{n}")
    print(f"    finish_reason      : {entry['finish_reason']}")
    print(f"    reasoning_tokens   : {entry['reasoning_tokens']}")
    print(f"    completion_tokens  : {entry['completion_tokens']}")
    print(f"    prompt_tokens      : {entry['prompt_tokens']}")
    print(f"    total_tokens       : {entry['total_tokens']}")
    print(f"    tiempo             : {entry['elapsed_s']} s")
    print(f"    tool_calls en resp : {entry['n_tool_calls']}")
    print()
    return response

# ── Ejecutar ──────────────────────────────────────────────────────────────────
with patch.object(_client.chat.completions, "create", side_effect=_instrumented_create):
    trace = run_agent(lead)

# ── Resumen ───────────────────────────────────────────────────────────────────
print(f"{'─'*60}")
print(f"  Resultado final")
print(f"    decisión   : {trace['decision']}")
print(f"    owner      : {trace['owner']}")
print(f"    n_steps    : {trace['n_steps']}")
print(f"    llamadas   : {len(call_log)}")
print(f"    total_s    : {trace['elapsed_s']}")
print(f"{'─'*60}\n")
