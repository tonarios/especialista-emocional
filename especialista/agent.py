"""Agente de dominio (FR-01..07, §9): `LlmAgent` ADK 2.x + runner determinista.

Dos caminos de conversación:

1. **Determinista (default, §9):** el backend orquesta el turno SIN delegar la
   iteración al LLM — detecta emergencia e injection antes, extrae los síntomas
   con UNA llamada de salida estructurada, lanza N recuperaciones **en paralelo**,
   elige la plantilla por `risk_tier` y sintetiza en UNA llamada final. Es el
   camino testeable en pytest sin depender del "humor" de gemma4.

2. **Tool-calling (alternativo):** un `LlmAgent` ADK con las tools
   `search_dictionary`, `get_user_profile` y `record_consultation`, por si el
   LLM quiere decidir 1..N recuperaciones por sí mismo.

Citación intersectada (§9): el modelo emite los slugs **usados**; el backend los
intersecta con lo recuperado antes de devolver `sources[]`.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from especialista import audit as audit_mod
from especialista import medical_safety, retrieval
from especialista.config import ROOT, settings

SYSTEM_INSTRUCTION_PATH = ROOT / "especialista" / "system_instruction.md"

SYSTEM_INSTRUCTION = SYSTEM_INSTRUCTION_PATH.read_text(encoding="utf-8")

_SIN_COBERTURA = medical_safety.SIN_COBERTURA_TEMPLATE


def _litellm_model() -> str:
    """Modelo normalizado para LiteLlm (>1.84): Ollama usa el endpoint /api/chat."""
    m = settings.llm_model
    if m.startswith("ollama/"):
        return "ollama_chat/" + m[len("ollama/") :]
    return m


def _ollama_model_name() -> str:
    """Nombre del modelo sin el prefijo de proveedor (`ollama/gemma4:latest` → `gemma4:latest`)."""
    m = settings.llm_model
    return m[len("ollama/") :] if m.startswith("ollama/") else m


def _ollama_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
    """Compatibilidad: delega en el proveedor activo (Ollama o Vertex).

    Se conserva el nombre porque los tests lo monkeypatchean. La lógica vive en
    `especialista.providers`, que es el único punto que sabe contra qué modelo
    se está hablando.
    """
    from especialista import providers

    return providers.chat(messages, max_tokens=max_tokens, temperature=temperature)


# ── Tools (contrato ADK, funciones puras con type hints) ──────────
def search_dictionary(query: str, k: int = 5) -> str:
    """Recupera los términos del diccionario relevantes a `query` (FR-09/09b).

    Devuelve contexto delimitado y etiquetado por documento, o la cadena
    «SIN COBERTURA» si nada supera el umbral τ.
    """
    res = retrieval.search(query, k=k)
    if not res["covered"]:
        return "SIN COBERTURA"
    return retrieval.format_for_llm(res["results"])


def get_user_profile(tool_context=None) -> str:
    """Historial de consultas del usuario (FR-13/17)."""
    from especialista import memory

    user_id = _user_id_from(tool_context)
    try:
        profile = memory.get_profile(user_id)
        consultations = profile["consultations"]
        if not consultations:
            return "Sin historial de consultas previas."
        lines = [f"- {c.get('ts', '?')}: {c.get('symptom', [])} -> {c.get('term', [])}" for c in consultations[-10:]]
        return "Historial de consultas:\n" + "\n".join(lines)
    except Exception:
        return "Sin historial de consultas previas."


def record_consultation(symptoms: list[str], terms: list[str], tool_context=None) -> str:
    """Persiste la consulta en el perfil del portador (FR-14/17)."""
    from especialista import memory

    user_id = _user_id_from(tool_context)
    try:
        memory.record_consultation(user_id, symptoms, terms)
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def _user_id_from(tool_context) -> str:
    if tool_context is not None:
        state = getattr(tool_context, "state", None)
        if state:
            uid = state.get("user_id")
            if uid:
                return uid
    return "default"


# ── Construcción del LlmAgent (camino tool-calling alternativo) ──
def build_agent():
    """Construye el `LlmAgent` ADK 2.x con gemma4 vía LiteLlm y sus tools."""
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm

    return LlmAgent(
        model=LiteLlm(model=_litellm_model()),
        name="especialista",
        description="Especialista en significados emocionales de síntomas y enfermedades.",
        instruction=SYSTEM_INSTRUCTION,
        tools=[search_dictionary, get_user_profile, record_consultation],
    )


# ── Callers LiteLlm (deterministic path) ──────────────────────────
def _complete(system: str, user: str, max_tokens: int = 700, temperature: float = 0.2) -> str:
    return _ollama_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )


_EXTRACT_PROMPT = (
    "Extrae de la consulta los síntomas o enfermedades mencionados, cada uno como "
    "una frase corta de búsqueda (ej. «dolor de garganta», «insomnio»). Devuelve "
    "SOLO un array JSON de strings. Si solo hay uno, devuelve un array con un "
    "elemento. Si no hay ningún síntoma, devuelve []."
)


def extract_symptoms(message: str) -> list[str]:
    """Una llamada de salida estructurada para partir la consulta (FR-04)."""
    raw = _complete(_EXTRACT_PROMPT, message, max_tokens=200, temperature=0.0)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(s).strip() for s in parsed if str(s).strip()][:4]
    except json.JSONDecodeError:
        pass
    # fallback determinista: el mensaje completo como una sola consulta
    return [message.strip()]


def _synthesize(context: str, instruction: str) -> str:
    user = (
        "A partir de los siguientes documentos del diccionario, escribe SOLO la "
        "lectura emocional integrada (asociativa, nunca causal). No escribas "
        "saludo, preámbulo ni disclaimer (el backend ya añade eso), y no pongas "
        "slugs dentro del texto. Si el contexto incluye un historial de consultas "
        "previas del usuario, puedes personalizar la lectura mencionándolo de forma "
        "natural. Al final, en una sola línea aparte, lista los "
        "slugs que realmente usaste: `FUENTES: slug1, slug2, ...`\n\n"
        f"{context}"
    )
    return _complete(instruction, user, max_tokens=900, temperature=0.3)


# ── Memoria del usuario (FR-13/14) ────────────────────────────────
_MEMORY_MARKERS = (
    "ultima consulta", "ultimo sintoma", "ultima enfermedad", "ultima vez",
    "ultimo que", "cual fue mi", "cual fue lo ultimo", "que fue lo ultimo",
    "mi historial", "historial", "recordas", "recuerdas", "te consulte",
    "te pregunte", "consultas anteriores", "enfermedad anterior",
    "que te habia", "me has preguntado", "lo que te he",
)


def _format_history(consultations: list[dict]) -> str:
    if not consultations:
        return ""
    lines = []
    for c in consultations[-10:]:
        ts = str(c.get("ts", ""))[:10]
        symptom = ", ".join(c.get("symptom", []) or [])
        term = ", ".join(c.get("term", []) or [])
        if not symptom and not term:
            continue
        suffix = f" (términos: {term})" if term else ""
        lines.append(f"- {ts}: {symptom}{suffix}")
    return "\n".join(lines)


def _is_memory_question(message: str) -> bool:
    from especialista.index import norm

    n = " " + norm(message) + " "
    return any(marker in n for marker in _MEMORY_MARKERS)


def _memory_answer(message: str, history_text: str, user_id: str) -> dict:
    """Responde una pregunta sobre el propio historial sin recuperar (FR-13)."""
    if history_text:
        answer = _complete(
            SYSTEM_INSTRUCTION,
            "Tienes acceso al historial de consultas que este usuario ha registrado "
            "contigo. A continuación está SU historial (es real, úsalo y respóndele "
            "a partir de él; no inventes entradas que no estén listadas ni hagas una "
            "lectura emocional nueva):\n\n"
            f"{history_text}\n\nPregunta del usuario: {message}",
            max_tokens=320, temperature=0.2,
        ).strip()
        answer = _strip_sources_line(answer)
        audit_mod.audit("chat_memory", user_email=user_id, status=200)
        return {"kind": "respuesta", "text": answer, "sources": [],
                "risk_tier": None, "termino": None, "detail": "memory"}
    audit_mod.audit("chat_memory", user_email=user_id, status=200)
    return {"kind": "respuesta", "text":
            "Todavía no tengo consultas registradas tuyas. Cuéntame un síntoma o "
            "una enfermedad y la iré guardando para recordarla en futuras "
            "conversaciones.", "sources": [], "risk_tier": None, "termino": None,
            "detail": "memory_empty"}


# ── Orquestación determinista del turno ───────────────────────────
_SOURCES_RE = re.compile(r"FUENTES\s*:\s*(.*)", re.I)


def run_deterministic(
    message: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    k: int = 5,
) -> dict:
    """Orquesta un turno completo del lado del backend (NFR-02b, §9).

    Devuelve un dict con: `kind`, `text`, `sources`, `risk_tier`, `termino`,
    `audit_action`. `kind` ∈ {emergency, blocked, sin_cobertura, respuesta}.
    """
    user_id = user_id or "default"

    # 1) Prompt injection ANTES del LLM (NFR-01).
    from especialista import guardrails

    try:
        clean_message, reasons, score = guardrails.check_prompt_injection(message)
    except guardrails.InjectionBlocked as exc:
        audit_mod.audit("chat_blocked_injection", user_email=user_id, status=403,
                        detail={"reasons": exc.reasons, "score": exc.score})
        return {"kind": "blocked", "text": "", "sources": [], "risk_tier": None,
                "termino": None, "detail": "prompt injection"}

    # 2) Emergencia ANTES de recuperar (FR-06, NFR-02b).
    emergency = medical_safety.detect_emergency(clean_message)
    if emergency is not None:
        audit_mod.audit("chat_emergency", user_email=user_id, status=200,
                        detail={"group_id": emergency["group_id"]})
        return {"kind": "emergency", "text": emergency["response"], "sources": [],
                "risk_tier": None, "termino": None, "detail": emergency["group_id"]}

    # Memoria del portador (FR-13): se lee cada turno para personalizar.
    from especialista import memory

    try:
        history = memory.get_profile(user_id).get("consultations", [])
    except Exception:
        history = []
    history_text = _format_history(history)

    # Pregunta sobre su propio historial → responder desde la memoria, SIN recuperar.
    if _is_memory_question(clean_message):
        return _memory_answer(clean_message, history_text, user_id)

    # 3) Multi-hop determinista: extraer síntomas → N recuperaciones en paralelo.
    symptoms = extract_symptoms(clean_message)
    if not symptoms:
        symptoms = [clean_message]

    searches: list[tuple[str, dict]] = []
    with ThreadPoolExecutor(max_workers=len(symptoms)) as ex:
        futures = {ex.submit(retrieval.search, q, k): q for q in symptoms}
        for fut in futures:
            q = futures[fut]
            searches.append((q, fut.result()))

    # 4) Agregación: SOLO cuentan las búsquedas con cobertura (FR-09b).
    retrieved: list[dict] = []
    for _, res in searches:
        if res["covered"]:
            retrieved.extend(res["results"])

    if not retrieved:
        # Pregunta sobre el propio historial (FR-13): responder desde la memoria.
        if _is_memory_question(clean_message):
            return _memory_answer(clean_message, history_text, user_id)

        audit_mod.audit("chat_sin_cobertura", user_email=user_id, status=200)
        return {"kind": "sin_cobertura", "text": _SIN_COBERTURA, "sources": [],
                "risk_tier": None, "termino": None, "detail": "sin cobertura"}

    # deduplicar por slug y ordenar por score desc
    seen: set[str] = set()
    ordered: list[dict] = []
    for doc in retrieved:
        if doc["slug"] not in seen:
            seen.add(doc["slug"])
            ordered.append(doc)
    ordered.sort(key=lambda d: d.get("score", 0.0), reverse=True)

    top = ordered[0]
    risk_tier = top["risk_tier"]
    termino = top["title"]

    # 5) Plantilla por risk_tier elegida en backend (FR-05a), nunca por el prompt.
    template = medical_safety.template_for(risk_tier)

    # 6) Síntesis (UNA llamada) con contexto delimitado + historial (FR-13).
    context = retrieval.format_for_llm(ordered[:k])
    if history_text:
        context = f"<historial>\n{history_text}\n</historial>\n\n" + context
    syn = _synthesize(context, SYSTEM_INSTRUCTION)

    # 7) Citación intersectada: slugs usados (del modelo) ∩ recuperados.
    used_slugs = _extract_used_slugs(syn, ordered)
    text = _strip_sources_line(syn)

    # 8) Ensamblar plantilla y renderizar.
    try:
        final_text = template.format(termino=termino, lectura=text)
    except KeyError:
        final_text = text

    # 9) Registrar la consulta en el perfil del portador (FR-14/17) y auditar.
    try:
        memory.record_consultation(user_id, symptoms, used_slugs)
    except Exception:
        pass
    audit_mod.audit("chat", user_email=user_id, status=200,
                    detail={"risk_tier": risk_tier,
                            "sources": used_slugs,
                            "session_id": session_id})

    return {"kind": "respuesta", "text": final_text, "sources": used_slugs,
            "risk_tier": risk_tier, "termino": termino, "detail": ""}


def _extract_used_slugs(syn: str, retrieved: list[dict]) -> list[str]:
    """Slugs que el modelo citó, intersectados con lo recuperado (§9)."""
    available = {d["slug"] for d in retrieved}
    used: list[str] = []
    m = _SOURCES_RE.search(syn)
    if not m:
        return used
    for token in m.group(1).split(","):
        slug = token.strip().strip(".- ").lower()
        # normalizar por si el modelo usa el título en lugar del slug
        if slug in available:
            used.append(slug)
        else:
            match = _slug_from_title(slug, retrieved)
            if match:
                used.append(match)
    return _dedupe(used)


def _slug_from_title(token: str, retrieved: list[dict]) -> str | None:
    from especialista.index import norm

    t = norm(token)
    for d in retrieved:
        if norm(d["title"]) == t or norm(d["title"].split(" (")[0]) == t:
            return d["slug"]
    return None


def _strip_sources_line(syn: str) -> str:
    return _SOURCES_RE.sub("", syn).strip()


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for it in items:
        if it not in out:
            out.append(it)
    return out


def source_objects(slugs: list[str]) -> list[dict]:
    """Slugs usados → `[{title, slug}]` para la UI (FR-03/§10)."""
    meta = retrieval._meta()
    sid = meta["slug_to_id"]
    docs = meta["docs"]
    out: list[dict] = []
    for slug in slugs:
        idx = sid.get(slug)
        if idx is None:
            out.append({"title": slug, "slug": slug})
        else:
            out.append({"title": docs[idx]["title"], "slug": slug})
    return out
