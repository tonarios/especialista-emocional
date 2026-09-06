"""Guardarraíles de entrada: validación de prompt injection y saneamiento.

Heurística determinista (regex + límites) que se aplica ANTES de enviar el
mensaje al LLM. Dos niveles:
  - BLOCK  : score >= BLOCK_THRESHOLD -> se rechaza el turno (HTTP 403) y se
             registra en audit_log.
  - SANITIZE: score bajo -> se limpian caracteres de control/zero-width y
             sigue adelante.

No es un clasificador ML: es una primera capa barata, auditable y sin
dependencias externas, combinada con el instruction hardening del agente.

(La skill `medical-safety` extiende esta lista con patrones de inyección
específicos del dominio emocional/médico.)
"""
from __future__ import annotations

import re
import unicodedata

MAX_MESSAGE_CHARS = 4000

# (patrón, peso) — pesos suman; el umbral decide bloqueo.
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    # Manipulación directa de instrucciones (es/en)
    (re.compile(r"ignora\s+(todas?\s+)?(las\s+|tus\s+|mis\s+)?instrucciones", re.I), 4),
    (re.compile(r"ignora\s+(todo\s+lo\s+anterior|lo\s+que\s+te\s+dije)", re.I), 3),
    (re.compile(r"olvida\s+(todo|todas\s+las\s+instrucciones|tu\s+rol|que\s+eres)", re.I), 4),
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I), 4),
    (re.compile(r"disrega(rd|de)\s+(all\s+)?(previous|prior|above)", re.I), 4),
    # Exfiltración del prompt/instrucciones del sistema
    (re.compile(r"(reveal|show|print|muestra|revela|imprime|dime).{0,30}(system\s*prompt|instrucciones\s+(del\s+)?sistema|prompt\s+del\s+sistema|tu\s+prompt)", re.I), 4),
    (re.compile(r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions)", re.I), 3),
    # Suplantación de rol / jailbreak conocido
    (re.compile(r"a\s+partir\s+de\s+ahora\s+(eres|actúa\s+como|actua\s+como)", re.I), 3),
    (re.compile(r"\b(actua|actúa)\s+como\s+un\b", re.I), 3),
    (re.compile(r"from\s+now\s+on\s+(you\s+are|pretend|behave)", re.I), 3),
    (re.compile(r"\bDAN\b|\bjailbreak\b|developer\s+mode", re.I), 3),
    (re.compile(r"you\s+have\s+no\s+(restrictions|rules|filters)", re.I), 3),
    (re.compile(r"sin\s+(restricciones|límites|limites|reglas|filtros)", re.I), 3),
    # Marcado estructural para falsificar el turno del sistema
    (re.compile(r"<\s*/?\s*(system|assistant|tool)\s*>", re.I), 5),
    (re.compile(r"\bSYSTEM\s*:", re.M), 4),
    # Intento de acceso a datos de otros usuarios (aislamiento)
    (re.compile(r"(dame|muestra|lista|give\s?me|show|list).{0,40}(datos|conversaciones|sesiones|perfiles?|historial)\s+(de\s+)?(otro|otros|todos\s+los)\s+(usuario|usuarios)", re.I), 4),
    # Petición de prescripción / diagnóstico forzado (fuera del rol, FR-06/07)
    (re.compile(r"(rec[eé]ta(me)?|prescr[ií]be(me)?|dame\s+.*\s+(dosis|medicamento|f[aá]rmaco|antibi[oó]tico))", re.I), 4),
    (re.compile(r"(diagnost[ií]came|hazme\s+un\s+diagn[oó]stico|diagn[oó]sticame)", re.I), 4),
    (re.compile(r"\b(dime|dame)\s+(cu[aá]nto|qu[eé]\s+dosis)", re.I), 4),
]

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028\u2029\u2060\ufeff]")

BLOCK_THRESHOLD = 4


class InjectionBlocked(Exception):
    """El mensaje fue rechazado por el detector de prompt injection."""

    def __init__(self, reasons: list[str], score: int):
        self.reasons = reasons
        self.score = score
        super().__init__(f"prompt injection bloqueado (score={score}): {reasons}")


def sanitize(message: str) -> str:
    """Elimina caracteres de control y zero-width usados para evadir filtros."""
    cleaned = _CONTROL_RE.sub("", message)
    return unicodedata.normalize("NFKC", cleaned)


def check_prompt_injection(message: str) -> tuple[str, list[str], int]:
    """Valida el mensaje del usuario antes del LLM.

    Returns:
        (mensaje_saneado, razones, score)

    Raises:
        InjectionBlocked: si el score alcanza el umbral de bloqueo.
    """
    if len(message) > MAX_MESSAGE_CHARS:
        raise InjectionBlocked([f"mensaje excede {MAX_MESSAGE_CHARS} caracteres"], BLOCK_THRESHOLD)
    reasons: list[str] = []
    score = 0
    for pattern, weight in _INJECTION_PATTERNS:
        if pattern.search(message):
            reasons.append(pattern.pattern[:60])
            score += weight
    if score >= BLOCK_THRESHOLD:
        raise InjectionBlocked(reasons, score)
    return sanitize(message), reasons, score
