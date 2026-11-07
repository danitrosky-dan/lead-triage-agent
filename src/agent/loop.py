"""
Agent loop: llama al modelo, ejecuta tool_calls y repite hasta que
registrar_decision sea invocado (o se alcance MAX_STEPS).
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from .rules import FALLBACK_OWNER, ROUTING, UMBRAL_CALIFICADO, UMBRAL_REVISION
from .tools import DB_PATH, TOOLS_LIST, _ensure_agent_decisions_schema, dispatch, registrar_decision

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

MAX_STEPS   = 8
TEMPERATURE = 0.6
TOP_P       = 0.95


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
    Valida que registrar_decision sea coherente con los resultados de las
    herramientas de esta ejecución. Devuelve error para el modelo, o None si OK.
    """
    decision = args.get("decision", "")

    # ── calificado ────────────────────────────────────────────────────────────
    if decision == "calificado":
        if "calcular_score_icp" not in run_state["called_tools"]:
            return (
                "Consistencia: llama a calcular_score_icp antes de registrar 'calificado'."
            )
        sr = run_state.get("score_result")
        if sr:
            if sr.get("criterio_excluyente"):
                return (
                    f"Consistencia: criterio excluyente '{sr['criterio_excluyente']}' "
                    "→ la decisión correcta es 'descartado'."
                )
            if sr.get("cargo_excluyente"):
                return "Consistencia: cargo excluyente → la decisión correcta es 'descartado'."
            if sr["score"] < UMBRAL_CALIFICADO:
                return (
                    f"Consistencia: score {sr['score']} < umbral {UMBRAL_CALIFICADO} "
                    "→ usa 'revision' o 'descartado'."
                )

    # ── duplicado ─────────────────────────────────────────────────────────────
    elif decision == "duplicado":
        dr = run_state.get("buscar_duplicado_result")
        if not dr or not dr.get("es_duplicado"):
            return (
                "Consistencia: buscar_duplicado no reportó duplicado. "
                "No puedes registrar 'duplicado'."
            )

    # ── revision: motivo cerrado + verificación de los que se pueden comprobar ─
    elif decision == "revision":
        motivo = args.get("motivo")
        if not motivo:
            return (
                "Consistencia: 'revision' requiere campo motivo. "
                "Valores: score_en_rango_revision | empresa_desconocida | datos_contradictorios."
            )

        if motivo == "score_en_rango_revision":
            sr = run_state.get("score_result")
            if sr is not None:
                s = sr["score"]
                if s >= UMBRAL_CALIFICADO:
                    return (
                        f"Consistencia: motivo='score_en_rango_revision' pero score={s} "
                        f"≥ {UMBRAL_CALIFICADO} → la decisión correcta es 'calificado'."
                    )
                if s < UMBRAL_REVISION:
                    return (
                        f"Consistencia: motivo='score_en_rango_revision' pero score={s} "
                        f"< {UMBRAL_REVISION} → la decisión correcta es 'descartado'."
                    )

        elif motivo == "empresa_desconocida":
            er = run_state.get("enriquecer_empresa_result")
            if er and er.get("encontrada"):
                return (
                    f"Consistencia: motivo='empresa_desconocida' pero enriquecer_empresa "
                    f"encontró '{er.get('nombre_encontrado')}'. Usa otro motivo."
                )

        elif motivo == "datos_contradictorios":
            if not (args.get("evidencia") or "").strip():
                return (
                    "Consistencia: motivo='datos_contradictorios' requiere campo evidencia "
                    "con los dos datos en conflicto."
                )

    return None


def _write_trace(entry: dict) -> None:
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Loop principal ────────────────────────────────────────────────────────────

def _register_error_sistema(lead_id: int, tool_name: str, msg: str,
                             db_path: Path, run_id: str | None) -> None:
    """Persiste un error de sistema en agent_decisions sin pasar por Pydantic."""
    try:
        con = sqlite3.connect(str(db_path))
        _ensure_agent_decisions_schema(con)
        con.execute(
            "INSERT INTO agent_decisions "
            "(lead_id, decision, owner, razonamiento, run_id) VALUES (?,?,?,?,?)",
            (lead_id, "error_sistema", FALLBACK_OWNER,
             f"ERROR de sistema en {tool_name}: {msg}", run_id),
        )
        con.commit()
        con.close()
    except Exception:
        pass  # no ocultar el error original


def run_agent(lead: dict, db_path: Path = DB_PATH, run_id: str | None = None) -> dict:
    """
    Ejecuta el agente sobre un lead.

    Devuelve un dict con:
      decision, owner, razonamiento, steps, n_steps, elapsed_s,
      error_sistema (bool), fallback_tipo (str | None).
    """
    t0 = time.time()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": _format_lead(lead)},
    ]

    run_state: dict = {
        "called_tools":              [],   # nombres de tools ejecutadas con éxito
        "buscar_duplicado_result":    None,
        "enriquecer_empresa_result":  None,
        "score_result":               None,
    }
    steps:       list = []
    final_args:  dict | None = None
    final_owner: str         = ""

    for step_n in range(1, MAX_STEPS + 1):

        response = _client.chat.completions.create(
            model=_MODEL_ID,
            messages=messages,
            tools=TOOLS_LIST,
            tool_choice="auto",
            temperature=TEMPERATURE,
            top_p=TOP_P,
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

            # 3. Ejecutar herramienta
            # ValidationError → args inválidos del LLM → devolver al modelo
            # Cualquier otra excepción → error de sistema → abortar lead
            try:
                result = dispatch(name, args, db_path=db_path, run_id=run_id)
            except ValidationError as exc:
                result = {"error": str(exc)}
            except Exception as exc:
                step["tool_calls"].append({
                    "name": name, "args": args,
                    "result": {"error_sistema": str(exc)},
                })
                steps.append(step)
                _register_error_sistema(lead["id"], name, str(exc), db_path, run_id)
                elapsed = round(time.time() - t0, 2)
                trace = {
                    "lead_id":      lead["id"],
                    "ts":           datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "steps":        steps,
                    "decision":     "error_sistema",
                    "owner":        FALLBACK_OWNER,
                    "razonamiento": f"ERROR de sistema en {name}: {exc}",
                    "n_steps":      len(steps),
                    "elapsed_s":    elapsed,
                    "error_sistema": True,
                    "fallback_tipo": None,
                }
                _write_trace(trace)
                return trace

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
                elif name == "enriquecer_empresa":
                    run_state["enriquecer_empresa_result"] = result
                elif name == "calcular_score_icp":
                    run_state["score_result"] = result
                elif name == "registrar_decision":
                    final_args  = args
                    final_owner = result.get("owner", "")

        steps.append(step)

        if final_args is not None:
            break  # registrar_decision completado → fin del loop

    # ── Límite de pasos alcanzado ─────────────────────────────────────────────
    fallback_tipo = None
    if final_args is None:
        fallback_tipo = "step_limit"
        final_args = {
            "lead_id":      lead["id"],
            "decision":     "revision",
            "motivo":       "empresa_desconocida",
            "razonamiento": "Límite de pasos alcanzado sin decisión final.",
        }
        try:
            result = registrar_decision(**final_args, db_path=db_path, run_id=run_id)
            final_owner = result.get("owner", FALLBACK_OWNER)
        except Exception:
            final_owner = FALLBACK_OWNER

    elapsed = round(time.time() - t0, 2)

    trace = {
        "lead_id":       lead["id"],
        "ts":            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "steps":         steps,
        "decision":      final_args["decision"],
        "owner":         final_owner,
        "razonamiento":  final_args["razonamiento"],
        "n_steps":       len(steps),
        "elapsed_s":     elapsed,
        "error_sistema": False,
        "fallback_tipo": fallback_tipo,
    }
    _write_trace(trace)
    return trace
