"""Guardarraíles de seguridad médica (FR-05/05a/05b/06, NFR-02/02b).

Mecanismos DETERMINISTAS, no instrucciones de prompt:

- `detect_emergency(text)`: evalúa `rag/emergency_patterns.json` sobre el mensaje
  del usuario ANTES de cualquier recuperación (FR-06). Si hay match, el agente no
  recupera ni interpreta; responde con la derivación del grupo.
- `template_for(risk_tier)`: plantilla de respuesta por nivel de riesgo (FR-05a).
  Para los 7 niveles elevados la derivación médica ENCABEZA y la lectura emocional
  va después, marcada como *reflexión complementaria*. Para `estandar`, disclaimer
  al pie. El mapeo tier→plantilla vive en `rag/risk_tiers.json` (fuente de verdad).
- `causal_patterns(text)`: detecta lenguaje causal prohibido (FR-05b). El registro
  obligatorio es asociativo ("el diccionario relaciona X con...", "una lectura
  posible es...").

Plantillas versionadas: `EMERGENCY_TEMPLATE` (FR-06, genérico) y
`SIN_COBERTURA_TEMPLATE` (FR-09b).
"""
from __future__ import annotations

import json
import re
import unicodedata

from especialista.config import ROOT

EMERGENCY_PATTERNS_PATH = ROOT / "rag" / "emergency_patterns.json"
RISK_TIERS_PATH = ROOT / "rag" / "risk_tiers.json"


def _norm(text: str) -> str:
    """Minúsculas + sin tildes (NFKD), para comparación acrítica y sin acentos."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


# ── Emergencias (FR-06) ──────────────────────────────────────────
_groups_cache: list[dict] | None = None


def load_emergency_groups() -> list[dict]:
    """Grupos de emergencia de `rag/emergency_patterns.json` (artefacto versionado)."""
    global _groups_cache
    if _groups_cache is None:
        data = json.loads(EMERGENCY_PATTERNS_PATH.read_text(encoding="utf-8"))
        _groups_cache = data["groups"]
    return _groups_cache


def detect_emergency(text: str) -> dict | None:
    """Devuelve el grupo de emergencia que matchea, o None.

    Se evalúa de forma determinista ANTES de la recuperación (FR-06, NFR-02b).
    El orden de los grupos importa: el primero que matchea gana (ideación
    suicida va primero).
    """
    n = _norm(text)
    for group in load_emergency_groups():
        for raw in group["patterns"]:
            pattern = re.compile(_norm(raw), re.IGNORECASE)
            if pattern.search(n):
                return {
                    "group_id": group["id"],
                    "name": group["name"],
                    "response": group["response"],
                }
    return None


# ── Plantillas por nivel de riesgo (FR-05a) ──────────────────────
_REFERRAL_TEMPLATES: dict[str, str] = {
    "derivacion_fuerte": (
        "Antes de hablar del significado emocional, una aclaración importante: "
        "`{termino}` es una condición que requiere seguimiento médico. Te recomiendo "
        "consultar con un profesional de la salud para una valoración clínica adecuada; "
        "este espacio no sustituye esa atención.\n\n"
        "Si lo deseas, lo que sigue es solo una **reflexión complementaria** desde el "
        "diccionario emocional, que no pretende explicar el origen del síntoma:\n\n"
        "{lectura}\n\n"
        "Recuerda: este contenido es de autoconocimiento y reflexión; no es consejo ni "
        "diagnóstico médico."
    ),
    "derivacion_salud_mental": (
        "Antes de continuar, algo importante: `{termino}` es una condición que se "
        "beneficia del acompañamiento de un profesional de la salud mental. Te "
        "recomiendo contactar a un psicólogo o psiquiatra, o a tu médico de cabecera. "
        "No estás solo/a en esto y la ayuda adecuada marca la diferencia.\n\n"
        "Si lo deseas, la siguiente lectura es solo una **reflexión complementaria** "
        "desde el diccionario emocional, no un diagnóstico:\n\n"
        "{lectura}\n\n"
        "Recuerda: este contenido es de autoconocimiento y reflexión; no es consejo ni "
        "diagnóstico médico."
    ),
    "derivacion_pediatrica": (
        "Una aclaración importante antes de continuar: cuando se trata de la salud de un "
        "bebé o un niño, la primera recomendación es siempre consultar a un pediatra. "
        "La lectura emocional no sustituye la valoración médica infantil.\n\n"
        "Si lo deseas, lo que sigue es solo una **reflexión complementaria** desde el "
        "diccionario emocional:\n\n"
        "{lectura}\n\n"
        "Recuerda: este contenido es de autoconocimiento y reflexión; no es consejo ni "
        "diagnóstico médico."
    ),
    "estandar": (
        "{lectura}\n\n"
        "Recuerda: este contenido es una interpretación emocional desde el diccionario y "
        "tiene fines de autoconocimiento y reflexión. No es consejo ni diagnóstico "
        "médico; ante dudas de salud, consulta a un profesional sanitario."
    ),
}

_policy_cache: dict | None = None


def _load_policy() -> dict:
    global _policy_cache
    if _policy_cache is None:
        _policy_cache = json.loads(RISK_TIERS_PATH.read_text(encoding="utf-8"))["policy"]
    return _policy_cache


def template_for(risk_tier: str) -> str:
    """Plantilla de respuesta para un nivel de riesgo.

    El mapeo tier→plantilla vive en `rag/risk_tiers.json`. Para los 7 niveles
    elevados la derivación médica encabeza; para `estandar` va el disclaimer al pie.
    Falla explícitamente ante un nivel desconocido (contrato con risk_tiers.json).
    """
    policy = _load_policy()
    if risk_tier not in policy:
        raise ValueError(f"Nivel de riesgo desconocido: {risk_tier}")
    return _REFERRAL_TEMPLATES[policy[risk_tier]["template"]]


# ── Lenguaje causal prohibido (FR-05b) ───────────────────────────
# Patrones en ASCII (se aplican sobre texto normalizado sin acentos).
_CAUSAL_PATTERNS: list[str] = [
    r"esto\s+ocurre\s+porque",
    r"esto\s+(pasa|sucede)\s+porque",
    r"tu\s+cuerpo\s+te\s+(dice|esta\s+diciendo)",
    r"tu\s+organismo\s+te\s+(dice|esta\s+diciendo)",
    r"la\s+causa\s+emocional\s+de\s+(tu|tus)",
    r"la\s+causa\s+de\s+tu\s+\w+\s+es\b",
    r"(es|esta|estan)\s+causad[oa]s?\s+por",
    r"te\s+esta\s+diciendo\s+que",
    r"significa\s+que\s+tu\s+\w+\s+(necesit|pid|reclam|quier|tiene|esta|anda)",
    r"tu\s+\w+\s+se\s+enferm\w*\s+porque",
    r"tu\s+\w+\s+se\s+manifiesta\s+porque",
]


def causal_patterns(text: str) -> list[str]:
    """Devuelve las frases de lenguaje causal prohibido encontradas (FR-05b).

    El registro obligatorio es asociativo ("el diccionario relaciona X con…",
    "una lectura posible es…"), nunca causal. Lista vacía = sin hallazgos.
    """
    n = _norm(text)
    found: list[str] = []
    for raw in _CAUSAL_PATTERNS:
        m = re.search(raw, n, re.IGNORECASE)
        if m:
            found.append(m.group(0))
    return found


# ── Plantillas versionadas ───────────────────────────────────────
EMERGENCY_TEMPLATE = (
    "Detecto una posible situación de emergencia. Por favor contacta de inmediato con "
    "los servicios de emergencia de tu país. No voy a ofrecer una interpretación "
    "emocional en esta situación."
)

SIN_COBERTURA_TEMPLATE = (
    "No encontré en el diccionario un término que se corresponda de forma clara con lo "
    "que describes, así que prefiero no inventar una interpretación que podría no "
    "encajar. Si me precisas el síntoma o la parte del cuerpo, busco de nuevo. Y ante "
    "dudas de salud, consulta a un profesional sanitario."
)
