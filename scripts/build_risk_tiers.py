"""Construye rag/risk_tiers.json a partir de data/*.md.

Clasifica cada término del diccionario en un nivel de riesgo clínico. El nivel
se guarda en meta.json junto al vector y CAMBIA EL COMPORTAMIENTO de respuesta
del agente (NFR-02b): en niveles altos la derivación médica encabeza la
respuesta y la lectura emocional se ofrece como reflexión complementaria, nunca
como explicación causal del síntoma.

La clasificación es por patrón sobre el slug — deliberadamente sobre-inclusiva.
Un falso positivo cuesta un párrafo de derivación de más; un falso negativo
cuesta una lectura emocional confiada sobre un síntoma oncológico. Los ajustes
manuales van en OVERRIDES.

Uso:  python scripts/build_risk_tiers.py
"""

from __future__ import annotations

import json
import pathlib
import re
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "rag" / "risk_tiers.json"

# Orden = precedencia. Un slug cae en el primer nivel que coincide.
#
# Los patrones se anclan al INICIO DE TOKEN del slug (los slugs son
# palabras separadas por guiones). Sin ese anclaje, la coincidencia por
# subcadena produce falsos positivos silenciosos: "femenino" contiene "nino",
# "bebedores"/"beber" contienen "bebe", "obsesion" contiene "sesion".
# Los patrones que terminan en (?=-|$) exigen token completo.
TIERS: dict[str, str] = {
    "oncologico": (
        r"cancer|tumor|carcinoma|leucemia|linfoma|metastasi|sarcoma|melanoma"
        r"|mieloma|neoplas|hodgkin|adenocarcinoma"
    ),
    "cardio_cerebrovascular": (
        r"infarto|corazon|cardiac|angina|arteri|ictus|embolia|aneurism|trombo"
        r"|hipertens|taquicard|arritmi|apoplej|accidente-cerebro"
    ),
    # Incluye autolesión (automutilacion) — junto a suicidio, la categoría más
    # crítica del corpus. Deliberadamente NO incluye angustia, ansiedad, estrés,
    # insomnio ni burnout: son el núcleo temático del diccionario y forzar
    # derivación en cada consulta de ansiedad haría el producto inservible.
    # La frontera es "diagnóstico clínico" vs "estado emocional".
    "psiquiatrico": (
        r"suicid|autolit|automutil|autolesion|depresion|psicosi|esquizofren"
        r"|bipolar|anorexi|bulimi|adiccion|toxicoman|droga|alcoholis|panico"
        r"|paranoi|demenci|alzheimer|locura|neurosis|obsesion|melancoli"
        r"|hipocondria|agorafobia|claustrofobia"
    ),
    "obstetrico": (
        r"embarazo|aborto|parto|eclampsi|feto|placent|lactanci|esteril"
        r"|infertil|menopaus"
    ),
    # nino/bebe exigen token completo (ver nota de anclaje arriba).
    "pediatrico": (
        r"nino(?:s)?(?=-|$)|bebe(?:s)?(?=-|$)|infantil|lactante|recien-nacido"
        r"|adolescen|autism"
    ),
    "infeccioso_agudo": (
        r"meningitis|sepsis|septic|neumonia|tuberculosi|sida|vih|hepatitis"
        r"|peritonitis|apendicitis"
    ),
    "metabolico_grave": (
        r"diabet|epilep|convulsi|coma|insuficiencia-renal|cirrosis|tiroid"
    ),
}

# Morfemas médicos que aparecen legítimamente EN MEDIO de un token compuesto
# ("fibrosarcoma", "bronconeumonia", "hipotiroidismo", "paratiroides"). Se
# buscan sin anclaje. Solo van aquí morfemas largos y distintivos: los cortos
# anclados existen justamente porque sin anclaje arrasan — "sida" coincide con
# "obesidad"/"necesidades"/"callosidades", "coma" con "glaucoma"/"toxicomania".
INFIX: dict[str, str] = {
    "oncologico": r"sarcoma|carcinoma",
    "infeccioso_agudo": r"neumonia",
    "metabolico_grave": r"tiroid",
}

# Política de respuesta por nivel. La consume la instrucción de sistema del
# agente y los tests de tests/test_medical_safety.py.
POLICY = {
    "oncologico": {
        "lead_with_referral": True,
        "allow_causal_language": False,
        "template": "derivacion_fuerte",
    },
    "cardio_cerebrovascular": {
        "lead_with_referral": True,
        "allow_causal_language": False,
        "template": "derivacion_fuerte",
    },
    "psiquiatrico": {
        "lead_with_referral": True,
        "allow_causal_language": False,
        "template": "derivacion_salud_mental",
    },
    "obstetrico": {
        "lead_with_referral": True,
        "allow_causal_language": False,
        "template": "derivacion_fuerte",
    },
    "pediatrico": {
        "lead_with_referral": True,
        "allow_causal_language": False,
        "template": "derivacion_pediatrica",
    },
    "infeccioso_agudo": {
        "lead_with_referral": True,
        "allow_causal_language": False,
        "template": "derivacion_fuerte",
    },
    "metabolico_grave": {
        "lead_with_referral": True,
        "allow_causal_language": False,
        "template": "derivacion_fuerte",
    },
    "estandar": {
        "lead_with_referral": False,
        "allow_causal_language": False,  # nunca, en ningún nivel
        "template": "estandar",
    },
}

OVERRIDES: dict[str, str] = {
    # Falsos positivos del patrón "nino|bebe" y similares van aquí.
    # p. ej. "nino-interior": "estandar"
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def classify(slug: str) -> str:
    if slug in OVERRIDES:
        return OVERRIDES[slug]
    n = norm(slug)
    for tier, pat in TIERS.items():
        if re.search(rf"(?:^|-)(?:{pat})", n):
            return tier
        infix = INFIX.get(tier)
        if infix and re.search(infix, n):
            return tier
    return "estandar"


def main() -> int:
    slugs = [f.stem for f in sorted(DATA.glob("*.md"))]
    assigned = {s: classify(s) for s in slugs}

    by_tier: dict[str, list[str]] = {t: [] for t in list(TIERS) + ["estandar"]}
    for slug, tier in assigned.items():
        by_tier[tier].append(slug)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_generated_by": "scripts/build_risk_tiers.py",
        "_corpus_docs": len(slugs),
        "policy": POLICY,
        "counts": {t: len(v) for t, v in by_tier.items()},
        # "estandar" se omite de la lista: es el default, y listarlo duplicaría
        # 1.100+ slugs en el JSON sin aportar nada.
        "tiers": {t: v for t, v in by_tier.items() if t != "estandar"},
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    elevated = sum(len(v) for t, v in by_tier.items() if t != "estandar")
    for tier in TIERS:
        print(f"  {tier:24} {len(by_tier[tier]):5}")
    print(f"  {'-' * 30}")
    print(f"  {'riesgo elevado':24} {elevated:5}  ({elevated / len(slugs) * 100:.1f}%)")
    print(f"  {'estandar':24} {len(by_tier['estandar']):5}")
    print(f"\nescrito: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
