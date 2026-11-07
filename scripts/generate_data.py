"""
Genera datos sintéticos reproducibles para el Lead Triage Agent.
Seed = 42. Escribe data/crm.db y eval/ground_truth.csv.
"""

import csv
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

# Permite importar src.agent.rules cuando el script se ejecuta directamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.rules import (  # noqa: E402
    _ACCENT, SECTORES_OBJETIVO, PAISES_OBJETIVO, EMPLEADOS_MINIMO,
    CARGOS_DECISORES, CARGOS_EXCLUYENTES_KW,
    UMBRAL_CALIFICADO, UMBRAL_REVISION, ROUTING, FALLBACK_OWNER,
    calc_score, calc_decision_owner,
)

SEED    = 42
DB_PATH = Path("data/crm.db")
GT_PATH = Path("eval/ground_truth.csv")

rng = random.Random(SEED)

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
GT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Vocabulario ───────────────────────────────────────────────────────────────
NOMBRES = [
    "Carlos","María","Juan","Ana","Luis","Sofía","Pedro","Carla",
    "Miguel","Valentina","Diego","Fernanda","Andrés","Camila","Roberto",
    "Paola","Javier","Isabel","Marcos","Lucía","Tomás","Renata",
    "Guillermo","Natalia","Felipe","Patricia","Ricardo","Daniela",
]
APELLIDOS = [
    "González","Rodríguez","Martínez","López","Pérez","Sánchez",
    "Ramírez","Torres","Flores","Vargas","Castro","Morales",
    "Jiménez","Herrera","Medina","Reyes","Ortiz","Silva","Ramos","Vega",
    "Muñoz","Pinto","Aguirre","Espinoza","Fuentes","Núñez","Bravo",
]
CARGOS_DECISOR = [
    "Gerente General",        "Gerenta General",
    "Director de Operaciones","Directora de Operaciones",
    "VP Comercial",
    "Head of Procurement",
    "Jefe de Proyectos",      "Jefa de Proyectos",
    "CEO", "CFO", "COO",
    "Director de Compras",    "Directora de Compras",
    "Gerente de Desarrollo",  "Gerenta de Desarrollo",
    "Gerente de Operaciones", "Gerenta de Operaciones",
    "Director Técnico",       "Directora Técnica",
    "Jefa de Área",
]
CARGOS_AMBIGUOS = [
    "Analista de Proyectos","Consultor Senior","Asistente de Gerencia",
    "Coordinador Técnico","Especialista en Licitaciones",
    "Técnico de Operaciones","Ejecutivo de Cuentas","Analista de Datos",
]
# Cargos excluyentes: todos coinciden con alguna keyword de cargos_excluyentes del YAML
CARGOS_EXCLUIBLES = [
    "Estudiante",
    "Alumno",             "Alumna",
    "Proveedor de Equipos","Proveedora de Equipos",
    "Practicante",
]
CONTENIDOS = [
    "Whitepaper: Gestión de Activos Mineros",
    "Guía: Eficiencia Energética en LatAm",
    "Reporte: Infraestructura Vial 2025",
    "Ebook: Digitalización en Minería",
    "Webinar: Energías Renovables en Chile",
    "Caso de Estudio: Proyecto Litio",
    "Informe: Mercado Eléctrico Colombia",
    "Checklist: Due Diligence de Proveedores",
]

# ── Helpers ───────────────────────────────────────────────────────────────────
_ACCENT = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")

def slugify(text):
    return text.translate(_ACCENT).lower().replace(" ", ".")

def make_domain(slug, pais):
    tld = "cl" if pais == "Chile" else ("br" if pais == "Brasil" else "com")
    return f"{slug}.{tld}"

def make_email(nombre, dominio):
    return f"{slugify(nombre)}@{dominio}"

def typo_email(email):
    """Introduce un typo en la parte local: duplica u omite un carácter."""
    local, domain = email.split("@", 1)
    if len(local) < 3:
        return f"{local}xx@{domain}"
    original = local
    for _ in range(10):
        idx = rng.randint(1, len(original) - 2)
        if rng.random() < 0.5:
            local = original[:idx] + original[idx] + original[idx:]
        else:
            local = original[:idx] + original[idx + 1:]
        if local != original:
            break
    return f"{local}@{domain}"

# ── Tabla companies (~90) ─────────────────────────────────────────────────────
def _make_co(pref, suf, pais, sector, emp, sfx="S.A."):
    slug = slugify(f"{pref}{suf}")
    return {
        "nombre":    f"{pref} {suf} {sfx}".strip(),
        "sector":    sector,
        "pais":      pais,
        "empleados": emp,
        "dominio":   make_domain(slug, pais),
    }

MINERIA_DATA = [
    ("Andina","Minerales","Chile",1500), ("Cordillera","Minería","Chile",800),
    ("Altiplano","Recursos","Peru",2200), ("Quebrada","Extracción","Chile",450),
    ("Cerro","Cobre","Chile",3400), ("Veta","Litio","Argentina",600),
    ("Roca","Oro","Peru",900), ("Puna","Minerales","Argentina",350),
    ("Sur","Minería","Chile",1100), ("Norte","Recursos","Peru",1800),
    ("Atacama","Litio","Chile",2500), ("Collahuasi","Cobre","Chile",1200),
    ("Sierra","Minería","Colombia",700), ("Orinoco","Recursos","Colombia",450),
    ("Minas","Gerais","Brasil",5000), ("Rio","Mineração","Brasil",3200),
    ("Zacatecas","Plata","Mexico",850), ("Sonora","Cobre","Mexico",1400),
    ("Titicaca","Recursos","Peru",600), ("Patagónica","Minería","Argentina",320),
    ("Llano","Extracción","Colombia",480), ("Norcenter","Minerales","Peru",950),
    ("Altamira","Mining","Chile",1700), ("Volcán","Recursos","Peru",2100),
    ("Gran","Minera","Brasil",4100),
]
ENERGIA_DATA = [
    ("Solar","Austral","Chile",400), ("Hidro","Andina","Chile",2200),
    ("Termo","Cordillera","Chile",1500), ("Volta","Energía","Brasil",3800),
    ("Electra","Renovables","Mexico",700), ("Nexus","Power","Colombia",500),
    ("Lumina","Grid","Argentina",850), ("Eólica","Sur","Argentina",350),
    ("Pacific","Energy","Chile",600), ("Caribe","Solar","Colombia",420),
    ("Amazona","Hidro","Brasil",2900), ("Yucatán","Eólica","Mexico",480),
    ("Andacollo","Generación","Chile",310), ("Titicaca","Power","Peru",550),
    ("Paraná","Electric","Brasil",1800), ("Noreste","Energía","Mexico",750),
    ("Andes","Renovables","Peru",290), ("Costamar","Solar","Colombia",230),
    ("Patagonia","Wind","Argentina",410), ("Central","Eléctrica","Chile",1100),
]
INFRA_DATA = [
    ("Vial","Andina","Chile",850), ("Obras","Civiles","Chile",1200),
    ("Metro","Sur","Brasil",4500), ("Puerto","Pacífico","Peru",1700),
    ("Ruta","Norte","Mexico",950), ("Urbana","Constructora","Colombia",600),
    ("Civil","Ingeniería","Argentina",400), ("Puentes","del Sur","Chile",300),
    ("Ferrocarril","Central","Brasil",3200), ("Autopistas","del Norte","Mexico",1100),
    ("Acueducto","Andino","Colombia",450), ("Terminal","Marítimo","Peru",800),
    ("Concesiones","Viales","Argentina",650), ("Subterráneo","Lima","Peru",2100),
    ("Edificaciones","Pacifico","Chile",500),
]
# Sector objetivo, país fuera de ICP → score 60-80 (sin descartado por sector)
OUT_COUNTRY_DATA = [
    ("Ibérica","Minería","España","mineria",800),
    ("Texas","Energy","USA","energia",5000),
    ("Yungas","Minerales","Bolivia","mineria",450),
    ("Quito","Obras","Ecuador","infraestructura",300),
    ("Asunción","Power","Paraguay","energia",250),
    ("Montevideo","Vial","Uruguay","infraestructura",320),
    ("La Paz","Extracción","Bolivia","mineria",380),
]
# Sector objetivo, país OK, empleados < 200 → score 60 con cargo ambiguo
SMALL_DATA = [
    ("Micro","Minera","Chile","mineria",50),
    ("Petit","Solar","Argentina","energia",80),
    ("Startup","Infra","Peru","infraestructura",120),
    ("Mini","Copper","Chile","mineria",150),
    ("Nano","Power","Mexico","energia",90),
]
# Sector fuera de ICP, país OK → criterio excluyente → descartado
OUT_SECTOR_DATA = [
    ("Agro","Chile","Chile","agricultura",600),
    ("Retail","Andino","Peru","retail",1200),
    ("TechPunta","Digital","Mexico","tecnologia",2000),
    ("Finanzas","Sur","Colombia","finanzas",400),
    ("Turismo","Patagónico","Argentina","turismo",300),
    ("AgroNorte","Corp","Chile","agricultura",450),
    # Nuevas: banca, educación, retail, consultoras (inbound realista)
    ("Banco","Andino","Chile","finanzas",2000),
    ("Crédito","del Sur","Peru","finanzas",1500),
    ("Fondo","Capital","Mexico","finanzas",800),
    ("Universidad","del Norte","Chile","educacion",1200),
    ("Instituto","Tecnológico","Mexico","educacion",600),
    ("Comercial","Andina","Chile","retail",3000),
    ("Retail","del Pacífico","Colombia","retail",2500),
    ("Consultoría","Estratégica","Chile","consultoria",400),
    ("Asesores","del Norte","Mexico","consultoria",250),
    ("Management","Partners","Colombia","consultoria",180),
    ("Telecomunicaciones","Sur","Brasil","telecomunicaciones",5000),
    ("EdTech","Latam","Argentina","educacion",300),
]

companies_raw = []
for p, s, pais, emp in MINERIA_DATA:
    companies_raw.append(_make_co(p, s, pais, "mineria", emp))
for p, s, pais, emp in ENERGIA_DATA:
    companies_raw.append(_make_co(p, s, pais, "energia", emp))
for p, s, pais, emp in INFRA_DATA:
    companies_raw.append(_make_co(p, s, pais, "infraestructura", emp))
for p, s, pais, sector, emp in OUT_COUNTRY_DATA:
    companies_raw.append(_make_co(p, s, pais, sector, emp))
for p, s, pais, sector, emp in SMALL_DATA:
    companies_raw.append(_make_co(p, s, pais, sector, emp, sfx="Ltda."))
for p, s, pais, sector, emp in OUT_SECTOR_DATA:
    companies_raw.append(_make_co(p, s, pais, sector, emp, sfx=""))

companies       = [{"id": i + 1, **c} for i, c in enumerate(companies_raw)]
company_by_name = {c["nombre"]: c for c in companies}

# Sub-pools reutilizados en la generación de leads
in_icp = [
    c for c in companies
    if c["sector"] in SECTORES_OBJETIVO
    and c["pais"] in PAISES_OBJETIVO
    and c["empleados"] >= EMPLEADOS_MINIMO
]
out_country_pool = [
    c for c in companies
    if c["sector"] in SECTORES_OBJETIVO
    and c["pais"] not in PAISES_OBJETIVO
    and c["empleados"] >= EMPLEADOS_MINIMO
]
small_pool = [
    c for c in companies
    if c["sector"] in SECTORES_OBJETIVO
    and c["pais"] in PAISES_OBJETIVO
    and c["empleados"] < EMPLEADOS_MINIMO
]
out_sector_pool = [
    c for c in companies
    if c["sector"] not in SECTORES_OBJETIVO
]

# ── Tabla crm_contacts (60) ───────────────────────────────────────────────────
crm_contacts    = []
used_crm_emails = set()

for i in range(60):
    comp  = rng.choice(in_icp)
    name  = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    email = make_email(name, comp["dominio"])
    ctr   = 1
    while email in used_crm_emails:
        email = f"{slugify(name)}{ctr}@{comp['dominio']}"
        ctr  += 1
    used_crm_emails.add(email)
    crm_contacts.append({
        "id":      i + 1,
        "nombre":  name,
        "email":   email,
        "cargo":   rng.choice(CARGOS_DECISOR),
        "empresa": comp["nombre"],
        "pais":    comp["pais"],
        "owner":   ROUTING.get(comp["pais"], FALLBACK_OWNER),
    })

# ── Tabla inbound_leads (100) ─────────────────────────────────────────────────
leads     = []
lead_meta = []
lead_id   = 1

def add_lead(nombre, email, cargo, empresa, pais, case,
             es_duplicado=False, contradictorio=False, crm_owner=None):
    global lead_id
    leads.append({
        "id": lead_id, "nombre": nombre, "email": email, "cargo": cargo,
        "empresa": empresa, "pais": pais, "contenido": rng.choice(CONTENIDOS),
    })
    lead_meta.append({
        "id": lead_id, "case": case, "es_duplicado": es_duplicado,
        "contradictorio": contradictorio, "crm_owner": crm_owner,
    })
    lead_id += 1

# A: Duplicados exactos (10) — email idéntico al del CRM → decision=duplicado
contacts_a     = rng.sample(crm_contacts, 10)
contacts_a_ids = {c["id"] for c in contacts_a}
for contact in contacts_a:
    add_lead(contact["nombre"], contact["email"], contact["cargo"],
             contact["empresa"], contact["pais"],
             case="duplicado_exacto", es_duplicado=True, crm_owner=contact["owner"])

# B: Duplicados fuzzy (8) — typo en email, mismo nombre/empresa → decision=duplicado
remaining = [c for c in crm_contacts if c["id"] not in contacts_a_ids]
for contact in rng.sample(remaining, 8):
    add_lead(contact["nombre"], typo_email(contact["email"]), contact["cargo"],
             contact["empresa"], contact["pais"],
             case="duplicado_fuzzy", es_duplicado=True, crm_owner=contact["owner"])

# C: Empresa fuera del ICP (12) — ninguna debe quedar calificado
#    6 out-of-sector → sector excluyente → descartado
for _ in range(6):
    comp = rng.choice(out_sector_pool)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_DECISOR + CARGOS_AMBIGUOS),
             comp["nombre"], comp["pais"], case="fuera_icp")
#    4 out-of-country + cargo AMBIGUO (no decisor) → score 60 → revision
#    (con decisor el score sería 80 → calificado, lo cual violaría la regla de consistencia)
for _ in range(4):
    comp = rng.choice(out_country_pool)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_AMBIGUOS),
             comp["nombre"], comp["pais"], case="fuera_icp")
#    2 pequeña + cargo ambiguo → score 60 → revision
for _ in range(2):
    comp = rng.choice(small_pool)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_AMBIGUOS),
             comp["nombre"], comp["pais"], case="fuera_icp")

# D: Empresa desconocida (8) — nombre no existe en companies → decision=revision
UNKNOWN_COS = [
    ("Fantasma Mining",      "fantasmamining.cl",    "Chile"),
    ("Inexistente Solar",    "inexistentesolar.com", "Peru"),
    ("Ghost Infrastructure", "ghostinfra.com",       "Mexico"),
    ("Unknown Energy",       "unknownenergy.co",     "Colombia"),
    ("Empresa Fantasma",     "fantasma.com.br",      "Brasil"),
    ("NoName Corp",          "noname.com",           "Argentina"),
    ("Xxxxxxx SA",           "xxxxxxx.cl",           "Chile"),
    ("Acme Latam",           "acmelatam.net",        "Peru"),
]
for unk_nombre, unk_dominio, unk_pais in UNKNOWN_COS:
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, unk_dominio),
             rng.choice(CARGOS_DECISOR + CARGOS_AMBIGUOS),
             unk_nombre, unk_pais, case="empresa_desconocida")

# E: Cargo ambiguo (8) — empresa in-ICP, cargo sin keyword decisora
#    score = 40+20+20+0 = 80 → calificado (caso de borde: buen ICP, cargo no claro)
for _ in range(8):
    comp = rng.choice(in_icp)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_AMBIGUOS),
             comp["nombre"], comp["pais"], case="cargo_ambiguo")

# F: Datos contradictorios (7) — email con dominio .cl pero pais declarado ≠ Chile
chile_cos        = [c for c in in_icp if c["pais"] == "Chile"]
PAISES_DISTINTOS = ["Peru","Mexico","Colombia","Argentina","Brasil","Peru","Mexico"]
for pais_lead in PAISES_DISTINTOS:
    comp = rng.choice(chile_cos)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_DECISOR),
             comp["nombre"], pais_lead,
             case="datos_contradictorios", contradictorio=True)

# G: Leads normales (47) — mezcla realista de inbound
#    G1 (20): in-ICP + cargo decisor → score 100 → calificado
for _ in range(20):
    comp = rng.choice(in_icp)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_DECISOR),
             comp["nombre"], comp["pais"], case="normal")

#    G2 (8): in-ICP + cargo ambiguo (sin CARGOS_EXCLUIBLES que activan cargo_excluyente)
#    score = 40+20+20+0 = 80 → calificado (calificado_requiere_cargo_decisor: false)
for _ in range(8):
    comp = rng.choice(in_icp)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_AMBIGUOS),
             comp["nombre"], comp["pais"], case="normal")

#    G3 (4): out-of-country o empresa pequeña + cargo ambiguo → score 60 → revision
g3_pool = out_country_pool + small_pool
for _ in range(4):
    comp = rng.choice(g3_pool)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(CARGOS_AMBIGUOS),
             comp["nombre"], comp["pais"], case="normal")

#    G4 (15): sector fuera de objetivo + cargos variados incluyendo excluibles
#    → sector excluyente o cargo excluyente → descartado
all_cargos = CARGOS_DECISOR + CARGOS_AMBIGUOS + CARGOS_EXCLUIBLES
for _ in range(15):
    comp = rng.choice(out_sector_pool)
    name = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
    add_lead(name, make_email(name, comp["dominio"]),
             rng.choice(all_cargos),
             comp["nombre"], comp["pais"], case="normal")

assert len(leads) == 100, f"Se esperaban 100 leads, hay {len(leads)}"

# ── Ground truth ──────────────────────────────────────────────────────────────
# Fuente de verdad: datos de la empresa en DB (no el formulario del lead).
# Para empresa_desconocida (comp=None): sector/empleados desconocidos, se usa
# el país declarado en el formulario para el score.
# Para datos_contradictorios: se usa el país real de la empresa (DB) para el
# score, pero la decisión se override a revision por las reglas del YAML.
meta_by_id = {m["id"]: m for m in lead_meta}
ground_truth = []

for lead in leads:
    meta = meta_by_id[lead["id"]]
    comp = company_by_name.get(lead["empresa"])

    if comp:
        sector     = comp["sector"]
        empleados  = comp["empleados"]
        pais_score = comp["pais"]
    else:
        sector     = None
        empleados  = None
        pais_score = lead["pais"]

    score = calc_score(sector, pais_score, empleados, lead["cargo"])
    dec, owner = calc_decision_owner(score, pais_score, sector, lead["cargo"], meta["case"], meta["crm_owner"])

    ground_truth.append({
        "lead_id":        lead["id"],
        "case_type":      meta["case"],
        "es_duplicado":   meta["es_duplicado"],
        "score_icp":      score,
        "decision":       dec,
        "owner_esperado": owner,
    })

# ── Chequeo de consistencia ───────────────────────────────────────────────────
lead_by_id  = {l["id"]: l for l in leads}
bad_fuera   = [g for g in ground_truth if g["case_type"] == "fuera_icp" and g["decision"] == "calificado"]
if bad_fuera:
    print(f"\n⚠️  ALERTA: {len(bad_fuera)} lead(s) fuera_icp con decision=calificado.")
    print("   Ningún lead fuera_icp debería quedar calificado. Detalles:")
    for g in bad_fuera:
        lead = lead_by_id[g["lead_id"]]
        comp = company_by_name.get(lead["empresa"], {})
        print(f"   lead_id={g['lead_id']}  empresa={lead['empresa']}"
              f"  sector={comp.get('sector','?')}  pais={comp.get('pais','?')}"
              f"  empleados={comp.get('empleados','?')}  cargo={lead['cargo']}"
              f"  score={g['score_icp']}")
    raise SystemExit(1)
print("✓ Consistencia OK: ningún lead fuera_icp tiene decision=calificado")

# ── Comparación old-scoring → new-scoring ────────────────────────────────────
# Old = substring matching, solo formas masculinas, sin normalización de tildes.
# New = token matching, formas femeninas/plurales, normalización de tildes.
_OLD_DECISORES = {"gerente", "director", "vp", "head", "jefe", "ceo", "cfo", "coo"}

changed_scores = []
for g in ground_truth:
    lead = lead_by_id[g["lead_id"]]
    comp = company_by_name.get(lead["empresa"])
    sec  = comp["sector"]    if comp else None
    emp  = comp["empleados"] if comp else None
    ps   = comp["pais"]      if comp else lead["pais"]

    old_s = 0
    if sec and sec.lower() in SECTORES_OBJETIVO: old_s += 40
    if ps  and ps in PAISES_OBJETIVO:            old_s += 20
    if emp and emp >= EMPLEADOS_MINIMO:          old_s += 20
    if any(kw in (lead["cargo"] or "").lower() for kw in _OLD_DECISORES): old_s += 20

    if old_s != g["score_icp"]:
        changed_scores.append({
            "lead_id":     g["lead_id"],
            "cargo":       lead["cargo"],
            "score_antes": old_s,
            "score_ahora": g["score_icp"],
            "delta":       g["score_icp"] - old_s,
            "decision":    g["decision"],
        })

# ── Escribir SQLite ───────────────────────────────────────────────────────────
DB_PATH.unlink(missing_ok=True)
con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.executescript("""
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
cur.executemany(
    "INSERT INTO companies VALUES (:id,:nombre,:sector,:pais,:empleados,:dominio)",
    companies,
)
cur.executemany(
    "INSERT INTO crm_contacts VALUES (:id,:nombre,:email,:cargo,:empresa,:pais,:owner)",
    crm_contacts,
)
cur.executemany(
    "INSERT INTO inbound_leads VALUES (:id,:nombre,:email,:cargo,:empresa,:pais,:contenido)",
    leads,
)
con.commit()
con.close()

# ── Escribir ground truth CSV ─────────────────────────────────────────────────
with open(GT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=["lead_id","case_type","es_duplicado","score_icp","decision","owner_esperado"]
    )
    writer.writeheader()
    writer.writerows(ground_truth)

# ── Resumen ───────────────────────────────────────────────────────────────────
print(f"\nEmpresas : {len(companies)}")
print(f"Contactos CRM : {len(crm_contacts)}")
print(f"Leads inbound : {len(leads)}")
print(f"DB       : {DB_PATH}")
print(f"GT CSV   : {GT_PATH}")

print("\n── Leads por tipo de caso ──────────────────────────────────────────────")
for case, n in sorted(Counter(m["case"] for m in lead_meta).items()):
    print(f"  {case:<25}  {n:>3}")

print("\n── Distribución de decisiones ──────────────────────────────────────────")
dec_counts = Counter(g["decision"] for g in ground_truth)
for dec in ["calificado","revision","descartado","duplicado"]:
    n = dec_counts.get(dec, 0)
    print(f"  {dec:<15}  {n:>3}")

print("\n── Decisión × caso (para verificar lógica) ─────────────────────────────")
from collections import defaultdict
case_dec = defaultdict(Counter)
for g in ground_truth:
    case_dec[g["case_type"]][g["decision"]] += 1
for case in sorted(case_dec):
    breakdown = "  ".join(f"{d}={n}" for d, n in sorted(case_dec[case].items()))
    print(f"  {case:<25}  {breakdown}")

print("\n── Leads con score distinto tras el fix (old → new scoring) ───────────")
subieron = [c for c in changed_scores if c["delta"] > 0]
bajaron  = [c for c in changed_scores if c["delta"] < 0]
print(f"  Total cambiados : {len(changed_scores)}")
print(f"  ↑ +20  forma fem./plural ahora reconocida : {len(subieron)}")
print(f"  ↓ -20  falso positivo substring corregido : {len(bajaron)}")
if changed_scores:
    print()
    for c in sorted(changed_scores, key=lambda x: x["delta"]):
        arrow = "↑" if c["delta"] > 0 else "↓"
        print(f"  {arrow}  lead_id={c['lead_id']:>3}  "
              f"{c['score_antes']:>3} → {c['score_ahora']:>3}  "
              f"decision={c['decision']:<12}  cargo='{c['cargo']}'")

print("\n── Score ICP (excluye duplicados y empresa desconocida) ────────────────")
scored = [
    g["score_icp"] for g in ground_truth
    if g["case_type"] not in ("duplicado_exacto", "duplicado_fuzzy", "empresa_desconocida")
]
score_dist = Counter(scored)
print(f"  min={min(scored)}  max={max(scored)}  media={sum(scored)/len(scored):.1f}")
for s in sorted(score_dist):
    bar = "█" * score_dist[s]
    print(f"    {s:>3} pts: {score_dist[s]:>2}  {bar}")
