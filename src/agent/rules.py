"""
Reglas de negocio determinísticas extraídas de config/business_rules.yaml.
Única fuente de verdad para scoring, decisión y routing.
Importar desde aquí; nunca duplicar estas constantes en otros módulos.
"""

# ── Mapa de normalización de tildes (reutilizable) ───────────────────────────
_ACCENT = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")

# ── ICP ───────────────────────────────────────────────────────────────────────
SECTORES_OBJETIVO = {"mineria", "energia", "infraestructura"}
PAISES_OBJETIVO   = {"Chile", "Peru", "Mexico", "Colombia", "Brasil", "Argentina"}
EMPLEADOS_MINIMO  = 200

CARGOS_DECISORES = {
    "gerente",   "gerenta",   "gerentes",   "gerentas",
    "director",  "directora", "directores", "directoras",
    "vp",        "head",
    "jefe",      "jefa",      "jefes",      "jefas",
    "ceo",       "cfo",       "coo",
}

CRITERIOS_EXCLUYENTES = {"sector"}   # si falla → descartado, sin importar el score

CARGOS_EXCLUYENTES_KW = {
    "estudiante", "estudiantes",
    "practicante", "practicantes",
    "proveedor", "proveedora", "proveedores", "proveedoras",
    "alumno", "alumna", "alumnos", "alumnas",
}

UMBRAL_CALIFICADO = 70
UMBRAL_REVISION   = 50

# ── Routing SDR ───────────────────────────────────────────────────────────────
ROUTING = {
    "Chile":     "Ana Torres",
    "Argentina": "Ana Torres",
    "Peru":      "Luis Méndez",
    "Colombia":  "Luis Méndez",
    "Brasil":    "Carla Souza",
    "Mexico":    "Jorge Ramírez",
}
FALLBACK_OWNER = "cola_revision"

# ── Funciones determinísticas ─────────────────────────────────────────────────
def _cargo_tokens(cargo: str) -> set:
    """Tokeniza cargo en palabras minúsculas sin tildes.
    Evita falsos positivos por substring (coo ⊂ coordinador)
    y falsos negativos por tilde (Gérente ≠ gerente)."""
    return set((cargo or "").lower().translate(_ACCENT).split())


def calc_score(sector: str, pais: str, empleados: int, cargo: str) -> int:
    """Devuelve score ICP 0-100 según los pesos del YAML."""
    s = 0
    # Normalizar tilde en sector: "minería" → "mineria" para comparar con el set
    sector_norm = sector.lower().translate(_ACCENT) if sector else ""
    if sector_norm and sector_norm in SECTORES_OBJETIVO: s += 40
    if pais         and pais in PAISES_OBJETIVO:         s += 20
    if empleados    and empleados >= EMPLEADOS_MINIMO:   s += 20
    if _cargo_tokens(cargo) & CARGOS_DECISORES:          s += 20
    return s


def calc_decision_owner(
    score: int,
    pais: str,
    sector: str,
    cargo: str,
    case: str,
    crm_owner: str = None,
) -> tuple:
    """
    Aplica las reglas del YAML en orden de prioridad y devuelve (decision, owner).

    Prioridades:
    1. duplicado            → 'duplicado', owner del contacto existente
    2. empresa_desconocida / datos_contradictorios → 'revision', cola_revision
    3. cargo excluyente     → 'descartado'
    4. sector excluyente    → 'descartado'
    5. scoring normal       (calificado_requiere_cargo_decisor: false)
    """
    if case in ("duplicado_exacto", "duplicado_fuzzy"):
        return "duplicado", crm_owner or ""
    if case in ("empresa_desconocida", "datos_contradictorios"):
        return "revision", FALLBACK_OWNER
    if _cargo_tokens(cargo) & CARGOS_EXCLUYENTES_KW:
        return "descartado", ""
    sector_norm = sector.lower().translate(_ACCENT) if sector else ""
    if sector is not None and sector_norm not in SECTORES_OBJETIVO:
        return "descartado", ""
    if score >= UMBRAL_CALIFICADO:
        return "calificado", ROUTING.get(pais, FALLBACK_OWNER)
    if score >= UMBRAL_REVISION:
        return "revision", FALLBACK_OWNER
    return "descartado", ""
