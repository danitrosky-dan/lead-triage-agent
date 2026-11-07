"""
Página 2: Cola de revisión.
Muestra leads en estado 'revision', permite a un humano aprobar, reclasificar
o descartar. Las decisiones se guardan en human_overrides.
"""
import sys
from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_ROOT    = _APP_DIR.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_APP_DIR))

from db import get_revision_queue, save_human_override, get_human_overrides  # noqa: E402

st.set_page_config(page_title="Cola de revisión", page_icon="📋", layout="wide")
st.title("📋 Cola de revisión")

# ── Helpers ───────────────────────────────────────────────────────────────────
_MOTIVO_LABEL = {
    "score_en_rango_revision":  "Score en rango de revisión",
    "empresa_desconocida":      "Empresa desconocida",
    "datos_contradictorios":    "Datos contradictorios",
}

_MOTIVO_BADGE = {
    "score_en_rango_revision":  ("🟡", "#fff3cd"),
    "empresa_desconocida":      ("🟠", "#ffe8d6"),
    "datos_contradictorios":    ("🔴", "#fce4e4"),
}


# ── Filtros ───────────────────────────────────────────────────────────────────
queue = get_revision_queue()

col_f1, col_f2 = st.columns([2, 1])
motivos_disp = ["Todos"] + sorted({r["motivo"] for r in queue if r["motivo"]})
filtro_motivo = col_f1.selectbox("Filtrar por motivo", motivos_disp)
filtro_origen = col_f2.selectbox(
    "Origen",
    ["Todos", "Live (sin run_id)", "Eval"],
)

if filtro_motivo != "Todos":
    queue = [r for r in queue if r["motivo"] == filtro_motivo]
if filtro_origen == "Live (sin run_id)":
    queue = [r for r in queue if not r.get("run_id")]
elif filtro_origen == "Eval":
    queue = [r for r in queue if r.get("run_id")]

st.caption(f"{len(queue)} lead(s) pendientes de revisión")

if not queue:
    st.success("Cola vacía — no hay leads pendientes de revisión.")
    st.markdown("---")
else:
    # ── Tabla de acción ───────────────────────────────────────────────────────
    for item in queue:
        lid         = item["lead_id"]
        did         = item["decision_id"]
        motivo      = item.get("motivo") or "—"
        evidencia   = item.get("evidencia") or ""
        razonamiento = item.get("razonamiento") or "—"
        emoji, bg   = _MOTIVO_BADGE.get(motivo, ("⚪", "#f8f9fa"))

        with st.container(border=True):
            header_col, badge_col = st.columns([3, 1])
            header_col.markdown(
                f"**#{lid} — {item['nombre']}**  ·  "
                f"{item['cargo']}  ·  {item['empresa']}  ·  {item['pais']}"
            )
            badge_col.markdown(
                f"<div style='background:{bg};padding:4px 10px;border-radius:6px;"
                f"text-align:center'>{emoji} {_MOTIVO_LABEL.get(motivo, motivo)}</div>",
                unsafe_allow_html=True,
            )

            # Detalles en expander
            with st.expander("Ver detalle del agente", expanded=False):
                dc1, dc2 = st.columns(2)
                dc1.text_input("Email",    item["email"],    key=f"email_{did}",    disabled=True)
                dc1.text_input("Empresa",  item["empresa"],  key=f"empresa_{did}",  disabled=True)
                dc2.text_input("Contenido", item.get("contenido", ""), key=f"cont_{did}", disabled=True)
                if evidencia:
                    st.warning(f"**Evidencia:** {evidencia}")
                st.info(f"**Razonamiento del agente:** {razonamiento}")
                if item.get("run_id"):
                    st.caption(f"Origen: `{item['run_id']}`")

            # Acción humana
            notas_key = f"notas_{did}"
            if notas_key not in st.session_state:
                st.session_state[notas_key] = ""

            ac1, ac2, ac3, ac4 = st.columns([2, 1, 1, 1])
            notas = ac1.text_input(
                "Notas (opcional)",
                key=notas_key,
                placeholder="Ej: revisado manualmente, cliente conocido",
                label_visibility="collapsed",
            )

            if ac2.button("✅ Aprobar (calificado)", key=f"apr_{did}"):
                save_human_override(did, lid, "calificado", st.session_state[notas_key])
                st.success(f"Lead #{lid} aprobado como calificado.")
                st.rerun()

            if ac3.button("🗑 Descartar", key=f"desc_{did}"):
                save_human_override(did, lid, "descartado", st.session_state[notas_key])
                st.success(f"Lead #{lid} descartado.")
                st.rerun()

            if ac4.button("⏸ Dejar pendiente", key=f"pend_{did}"):
                save_human_override(did, lid, "pendiente", st.session_state[notas_key])
                st.info(f"Lead #{lid} marcado como pendiente.")
                st.rerun()

# ── Historial de overrides ────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📜 Historial de decisiones humanas", expanded=False):
    overrides = get_human_overrides()
    if not overrides:
        st.caption("Sin registros aún.")
    else:
        _BADGE = {
            "calificado": "🟢",
            "descartado":  "🔴",
            "pendiente":   "⏸",
        }
        for ov in overrides:
            badge = _BADGE.get(ov["decision_humana"], "⚪")
            st.markdown(
                f"{badge} **#{ov['lead_id']} {ov['nombre']}** ({ov['empresa']}) → "
                f"`{ov['decision_humana']}`"
                + (f"  — _{ov['notas']}_" if ov.get("notas") else "")
                + f"  <small style='color:gray'>{ov['timestamp']}</small>",
                unsafe_allow_html=True,
            )
