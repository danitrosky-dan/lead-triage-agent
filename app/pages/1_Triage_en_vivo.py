"""
Página 1: Triage en vivo.
Elige un lead existente o ingresa uno nuevo, ejecuta el agente y muestra
el trace completo paso a paso.
"""
import json
import sys
from pathlib import Path

import streamlit as st

# ── Paths ─────────────────────────────────────────────────────────────────────
_APP_DIR  = Path(__file__).resolve().parent.parent
_ROOT     = _APP_DIR.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_APP_DIR))

from db import get_all_leads, get_lead, insert_lead  # noqa: E402

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Triage en vivo", page_icon="⚡", layout="wide")
st.title("⚡ Triage en vivo")

# ── Helpers ───────────────────────────────────────────────────────────────────
_DECISION_COLOR = {
    "calificado":   "🟢",
    "revision":     "🟡",
    "descartado":   "🔴",
    "duplicado":    "🔵",
    "error_sistema":"⚫",
}

_MOTIVO_LABEL = {
    "score_en_rango_revision":  "Score en rango de revisión",
    "empresa_desconocida":      "Empresa desconocida",
    "datos_contradictorios":    "Datos contradictorios",
}


def _fmt_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def _render_trace(trace: dict) -> None:
    decision = trace.get("decision", "?")
    owner    = trace.get("owner", "")
    icon     = _DECISION_COLOR.get(decision, "⚪")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Decisión", f"{icon} {decision}")
    col2.metric("Owner / SDR", owner or "—")
    col3.metric("Pasos", trace.get("n_steps", 0))
    col4.metric("Latencia", f"{trace.get('elapsed_s', 0):.1f} s")

    if trace.get("fallback_tipo"):
        st.warning(f"Fallback activado: `{trace['fallback_tipo']}`")

    st.markdown("**Razonamiento final del agente:**")
    st.info(trace.get("razonamiento", "—"))

    st.markdown("---")
    st.markdown("#### Pasos del agente")

    for step in trace.get("steps", []):
        n         = step.get("n", "?")
        reasoning = step.get("reasoning", "")
        tcs       = step.get("tool_calls", [])

        with st.expander(f"Paso {n}  —  {len(tcs)} tool call(s)", expanded=(n == 1)):
            if reasoning:
                st.markdown("**Razonamiento interno (thinking):**")
                st.markdown(
                    f"<div style='background:#f8f9fa;padding:8px;border-radius:4px;"
                    f"font-size:0.85em;white-space:pre-wrap'>{reasoning[:2000]}"
                    f"{'…' if len(reasoning) > 2000 else ''}</div>",
                    unsafe_allow_html=True,
                )

            if not tcs:
                st.caption("Sin tool calls en este paso.")
                continue

            for tc in tcs:
                name   = tc.get("name", "?")
                args   = tc.get("args", {})
                result = tc.get("result", {})
                is_err = "error" in result or "error_sistema" in result

                badge_color = "#dc3545" if is_err else "#0d6efd"
                st.markdown(
                    f"<span style='background:{badge_color};color:white;"
                    f"padding:2px 8px;border-radius:4px;font-size:0.85em'>"
                    f"🔧 {name}</span>",
                    unsafe_allow_html=True,
                )

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Args:**")
                    st.code(_fmt_json(args), language="json")
                with c2:
                    st.markdown("**Resultado:**")
                    st.code(_fmt_json(result), language="json")


# ── Session state ─────────────────────────────────────────────────────────────
if "trace" not in st.session_state:
    st.session_state.trace = None
if "email_result" not in st.session_state:
    st.session_state.email_result = None
if "processed_lead_id" not in st.session_state:
    st.session_state.processed_lead_id = None

# ── Lead selection ────────────────────────────────────────────────────────────
tab_existente, tab_nuevo = st.tabs(["Lead existente", "Nuevo lead (formulario)"])

with tab_existente:
    leads = get_all_leads()
    lead_options = {f"#{l['id']} — {l['nombre']} ({l['empresa']}, {l['pais']})": l for l in leads}
    sel_label = st.selectbox("Seleccionar lead", list(lead_options.keys()))
    lead_sel  = lead_options[sel_label]

    with st.expander("Ver datos del lead", expanded=False):
        c1, c2 = st.columns(2)
        c1.text_input("Nombre",   lead_sel["nombre"],  disabled=True)
        c1.text_input("Email",    lead_sel["email"],   disabled=True)
        c1.text_input("Cargo",    lead_sel["cargo"],   disabled=True)
        c2.text_input("Empresa",  lead_sel["empresa"], disabled=True)
        c2.text_input("País",     lead_sel["pais"],    disabled=True)
        c2.text_input("Contenido", lead_sel.get("contenido", ""), disabled=True)

    if st.button("▶ Ejecutar agente", key="btn_existente", type="primary"):
        st.session_state.trace = None
        st.session_state.email_result = None
        st.session_state.processed_lead_id = None
        try:
            from src.agent.loop import run_agent  # import tardío: requiere .env
            with st.spinner(f"Procesando lead #{lead_sel['id']}…  (~25 s en promedio)"):
                trace = run_agent(lead_sel)
            st.session_state.trace            = trace
            st.session_state.processed_lead_id = lead_sel["id"]
            st.rerun()
        except Exception as exc:
            st.error(f"Error al ejecutar el agente: {exc}")
            st.info("Verifica que el servidor oMLX esté corriendo y que .env tenga las variables correctas.")

with tab_nuevo:
    st.caption("Los datos se guardan en la DB como lead sintético antes de procesar.")

    paises = ["Chile", "Peru", "Mexico", "Colombia", "Brasil", "Argentina"]

    with st.form("form_nuevo_lead"):
        fc1, fc2 = st.columns(2)
        nombre   = fc1.text_input("Nombre",  placeholder="Ej: María González")
        email    = fc1.text_input("Email",   placeholder="Ej: mgonzalez@empresa.cl")
        cargo    = fc1.text_input("Cargo",   placeholder="Ej: Directora de Operaciones")
        empresa  = fc2.text_input("Empresa", placeholder="Ej: Minera Atacama S.A.")
        pais     = fc2.selectbox("País", paises)
        contenido = fc2.text_input("Contenido descargado", placeholder="Ej: Ebook: Digitalización en Minería")
        submitted = st.form_submit_button("▶ Guardar y ejecutar agente", type="primary")

    if submitted:
        if not all([nombre, email, cargo, empresa]):
            st.warning("Completa al menos: nombre, email, cargo y empresa.")
        else:
            st.session_state.trace = None
            st.session_state.email_result = None
            try:
                from src.agent.loop import run_agent
                new_id = insert_lead(nombre, email, cargo, empresa, pais, contenido)
                new_lead = get_lead(new_id)
                with st.spinner(f"Procesando lead #{new_id}…  (~25 s en promedio)"):
                    trace = run_agent(new_lead)
                st.session_state.trace            = trace
                st.session_state.processed_lead_id = new_id
                st.rerun()
            except Exception as exc:
                st.error(f"Error al ejecutar el agente: {exc}")
                st.info("Verifica que el servidor oMLX esté corriendo.")

# ── Mostrar resultados ────────────────────────────────────────────────────────
if st.session_state.trace is not None:
    trace = st.session_state.trace
    st.markdown("---")
    st.markdown("## Resultado del triage")
    _render_trace(trace)

    # ── Borrador de correo (solo si calificado) ───────────────────────────────
    if trace.get("decision") == "calificado":
        st.markdown("---")
        st.markdown("### ✉ Borrador de correo")

        if st.session_state.email_result is None:
            if st.button("Redactar correo", key="btn_email"):
                try:
                    from src.email.drafter import redactar_correo
                    lid = st.session_state.processed_lead_id
                    with st.spinner("Redactando correo…"):
                        result = redactar_correo(lead_id=lid)
                    st.session_state.email_result = result
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error al redactar correo: {exc}")
        else:
            er = st.session_state.email_result
            estado_color = {
                "ok_primera":        "🟢 Aprobado en primer intento",
                "ok_reintento":      "🟡 Aprobado tras reintento",
                "requiere_revision": "🔴 Requiere revisión manual",
            }
            st.markdown(
                f"**Estado:** {estado_color.get(er.estado, er.estado)}  "
                f"| **Intentos:** {er.intentos}"
            )
            if er.fallo:
                st.warning(f"Fallo de validación: {er.fallo}")
            if er.asunto:
                st.text_input("Asunto", er.asunto, disabled=True)
            if er.cuerpo:
                st.text_area("Cuerpo", er.cuerpo, height=200, disabled=True)

            if st.button("Volver a redactar", key="btn_remail"):
                st.session_state.email_result = None
                st.rerun()
