"""
Lead Triage Agent — Dashboard Streamlit.
Punto de entrada: streamlit run app/app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Lead Triage Agent",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Lead Triage Agent")
st.markdown(
    """
    Agente de IA para triage de leads inbound B2B
    _(contexto: información de negocios sobre minería, energía e infraestructura en LatAm)_

    ---

    ### Páginas disponibles

    | Página | Descripción |
    |--------|-------------|
    | **1 · Triage en vivo** | Elige un lead existente o ingresa uno nuevo, ejecuta el agente y revisa cada herramienta, razonamiento, decisión y borrador de correo. |
    | **2 · Cola de revisión** | Leads en estado `revision`. Aprobar, reclasificar o descartar con un clic; la decisión humana queda guardada en `human_overrides`. |
    | **3 · Evaluación** | Métricas de test v1 (95,7 % decisión · 97,1 % owner), matriz de confusión, desglose de errores por origen y estadísticas de correos. |

    Usa el menú de la izquierda para navegar.
    """,
    unsafe_allow_html=False,
)

st.info(
    "Todo el contenido es **sintético y ficticio**. "
    "El modelo corre en oMLX local (Qwen3.6-35B-A3B-4bit).",
    icon="ℹ️",
)
