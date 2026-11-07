"""
Agent loop: llama al modelo, ejecuta tool_calls y repite hasta que
registrar_decision sea invocado (o se alcance MAX_STEPS).
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .rules import UMBRAL_CALIFICADO
from .tools import DB_PATH, TOOLS_LIST, dispatch, registrar_decision

# ── Configuración ─────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

_client   = OpenAI(base_url=os.environ["OMLX_BASE_URL"], api_key=os.environ["OMLX_API_KEY"])
_MODEL_ID = os.environ["MODEL_ID"]

# system_prompt.md sin "s" como pide la tarea; busca también la variante "systems_"
_prompt_candidates = [_ROOT / "prompts" / "system_prompt.md",
                      _ROOT / "prompts" / "systems_prompt.md"]
_PROMPT_PATH = next((p for p in _prompt_candidates if p.exists()), _prompt_candidates[0])
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_LOG_PATH = _ROOT / "logs" / "traces.jsonl"
_LOG_PATH.parent.mkdir(exist_ok=True)

MAX_STEPS = 8


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_lead(lead: dict) -> str:
    return (
        "Procesa este lead:\n"
        f"- ID: {lead['id']}\n"
        f"- Nombre: {lead['nombre']}\n"
        f"- Email: {lead['email']}\n"
        f"- Cargo: {lead['cargo']}\n"
        f"- Empresa: {lead['empresa']}\n"
        f"- País: {lead['pais']}\n"
        f"- Contenido descargado: {lead.get('contenido', '')}\n"
    )


def _check_consistency(args: dict, run_state: dict) -> str | None:
    """
    Valida que registrar_decision sea coherente con los resultados vistos en
    esta ejecución. Devuelve un mensaje de error para el modelo, o None si OK.
    """
    decision = args.get("decision", "")

    if decision == "calificado":
        if "calcular_score_icp" not in run_state["called_tools"]:
            return (
                "Consistencia: debes llamar a calcular_score_icp antes de "
                "registrar 'calificado'. Llama a esa herramienta primero."
            )
        sr = run_state.get("score_result")
        if sr:
            if sr.get("criterio_excluyente"):
                return (
                    f"Consistencia: criterio excluyente '{sr['criterio_excluyente']}' "
                    "activo — la decisión correcta es 'descartado', no 'calificado'."
                )
            if sr.get("cargo_excluyente"):
                return (
                    "Consistencia: el cargo es excluyente — "
                    "la decisión correcta es 'descartado', no 'calificado'."
                )
            if sr["score"] < UMBRAL_CALIFICADO:
                return (
                    f"Consistencia: score ICP {sr['score']} < umbral {UMBRAL_CALIFICADO}. "
                    "Usa 'revision' o 'descartado' según las reglas."
                )

    if decision == "duplicado":
        dr = run_state.get("buscar_duplicado_result")
        if not dr or not dr.get("es_duplicado"):
            return (
                "Consistencia: buscar_duplicado no reportó duplicado en este lead. "
                "No puedes registrar la decisión 'duplicado'."
            )

    return None


def _write_trace(entry: dict) -> None:
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Loop principal ────────────────────────────────────────────────────────────

def run_agent(lead: dict, db_path: Path = DB_PATH) -> dict:
    """
    Ejecuta el agente sobre un lead.

    Devuelve un dict con:
      decision, owner, razonamiento, steps (lista de pasos con tool_calls),
      n_steps, elapsed_s.
    """
    t0 = time.time()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": _format_lead(lead)},
    ]

    run_state: dict = {
        "called_tools":           [],   # nombres de tools ejecutadas con éxito
        "buscar_duplicado_result": None,
        "score_result":            None,
    }
    steps:      list = []
    final_args: dict | None = None

    for step_n in range(1, MAX_STEPS + 1):

        response = _client.chat.completions.create(
            model=_MODEL_ID,
            messages=messages,
            tools=TOOLS_LIST,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # reasoning_content es específico de Qwen3; puede no existir
        raw_msg   = msg.model_dump()
        reasoning = raw_msg.get("reasoning_content") or ""

        step: dict = {"n": step_n, "reasoning": reasoning, "tool_calls": []}

        # ── Reconstruir el mensaje del asistente para el historial ────────────
        assistant_entry: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id":   tc.id,
                    "type": "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            # Respuesta de texto plano sin herramientas (inesperado pero manejable)
            steps.append(step)
            break

        # ── Ejecutar cada tool_call del paso ──────────────────────────────────
        for tc in msg.tool_calls:
            name = tc.function.name

            # 1. Parsear JSON de argumentos
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as exc:
                result = {"error": f"Argumentos JSON inválidos: {exc}"}
                messages.append({
                    "role":        "tool",
                    "tool_call_id": tc.id,
                    "content":     json.dumps(result),
                })
                step["tool_calls"].append({
                    "name": name, "args": tc.function.arguments, "result": result,
                })
                continue

            # 2. Guardia de consistencia (solo registrar_decision)
            if name == "registrar_decision":
                err = _check_consistency(args, run_state)
                if err:
                    result = {"error": err}
                    messages.append({
                        "role":        "tool",
                        "tool_call_id": tc.id,
                        "content":     json.dumps(result),
                    })
                    step["tool_calls"].append({"name": name, "args": args, "result": result})
                    continue

            # 3. Ejecutar herramienta; errores van de vuelta al modelo
            try:
                result = dispatch(name, args, db_path=db_path)
            except Exception as exc:
                result = {"error": str(exc)}

            messages.append({
                "role":        "tool",
                "tool_call_id": tc.id,
                "content":     json.dumps(result, ensure_ascii=False),
            })
            step["tool_calls"].append({"name": name, "args": args, "result": result})

            # 4. Actualizar run_state solo si no hubo error
            if "error" not in result:
                run_state["called_tools"].append(name)
                if name == "buscar_duplicado":
                    run_state["buscar_duplicado_result"] = result
                elif name == "calcular_score_icp":
                    run_state["score_result"] = result
                elif name == "registrar_decision":
                    final_args = args   # guardia ya pasó → es coherente

        steps.append(step)

        if final_args is not None:
            break  # registrar_decision completado → fin del loop

    # ── Límite de pasos alcanzado ─────────────────────────────────────────────
    if final_args is None:
        final_args = {
            "lead_id":      lead["id"],
            "decision":     "revision",
            "owner":        "cola_revision",
            "razonamiento": "Límite de pasos alcanzado sin decisión final.",
        }
        try:
            registrar_decision(**final_args, db_path=db_path)
        except Exception:
            pass  # best-effort

    elapsed = round(time.time() - t0, 2)

    trace = {
        "lead_id":      lead["id"],
        "ts":           datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "steps":        steps,
        "decision":     final_args["decision"],
        "owner":        final_args["owner"],
        "razonamiento": final_args["razonamiento"],
        "n_steps":      len(steps),
        "elapsed_s":    elapsed,
    }
    _write_trace(trace)
    return trace
