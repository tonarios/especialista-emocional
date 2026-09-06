"""Construye rag/aliases.json a partir de data/*.md.

Detecta documentos que son *redirecciones puras* (cuerpo corto que solo apunta a
otro término) y los resuelve a su slug destino. Esos documentos NO deben recibir
un vector propio en el índice FAISS: se registran como alias del destino.

Reglas de detección (sobre el CUERPO, no el título):
  1. "Ver el término correspondiente bajo **X**"
  2. "consulta la sección X en el índice principal"
  3. título con "(ver: X)" Y cuerpo < 300 caracteres

Ojo: 25 documentos llevan "(ver: X)" en el título pero tienen cuerpo propio
sustancial. Esos NO son redirecciones — conservan su vector y además registran
el alias. Por eso la regla 3 exige cuerpo corto.

Uso:  python scripts/build_aliases.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "rag" / "aliases.json"

STUB_MAX_CHARS = 300

REDIRECT_PATTERNS = [
    re.compile(
        r"[Vv]er el t[eé]rmino correspondiente bajo\s*\*{0,2}(.+?)\*{0,2}"
        r"\s*(?:para m[aá]s detalles)?\.?\s*$",
        re.I | re.M,
    ),
    re.compile(r"consulta la secci[oó]n\s+(.+?)\s+en el [ií]ndice principal", re.I),
]
TITLE_ALIAS = re.compile(r"\(\s*[Vv]er[.:]?\s*(.+?)\s*\)")

# Destinos que la normalización automática no resuelve. Revisados a mano contra
# el corpus; la coincidencia difusa por texto NO es segura aquí (produce
# ABSCESO -> "obsesion", LARINGITIS -> "rinitis"), así que se curan explícitamente.
CURATED: dict[str, str | None] = {
    "dolor-de-muelas-ver-dientes-dolores-de": "dientes-dolor-de-o-de-muelas",
    "enfermedad-de-dupuytren": "manos-contractura-de-depuytren",
    "enfermedad-de-friedriech-ver-ataxia-de-friedriech": "ataxia-de-friedreich",
    "enronquecimiento-ver-laringitis": "garganta-laringitis",
    "estomago-cancer-del-ver-cancer-del-estomago": "cancer-de-estomago",
    "fiebre-de-los-henos-ver-alergia-la-fiebre-de-los-henos": (
        "alergia-a-la-fiebre-del-heno-rinitis-alergica"
    ),
    "piedras-en-los-rinones-ver-calculos-y-rinones": (
        "calculos-renales-o-litiasis-urinaria"
    ),
    # El destino existe con varias variantes; se elige la entrada "en general".
    "estrabismo-ver-ojos-estrabismo": "ojos-estrabismo-en-general",
    "globulos-sanguineos-ver-sangre": "sangre-globulos-problemas-en-los",
    # Apuntan a secciones del documento compuesto huesos-en-general.md.
    # El indexador parte ese documento por sección (ver FR-08b), así que el
    # destino real es el chunk correspondiente.
    "dislocacion-ver-hueso-dislocacion": "huesos-en-general#dislocacion",
    "fractura-ver-hueso-fractura-osea": "huesos-en-general#fractura",
    "osteoporosis-ver-huesos-osteoporosis": "huesos-en-general#osteoporosis",
    # Ambiguo: no existe un ABSCESO genérico, solo variantes por órgano.
    "empiema-ver-absceso": None,
    # Huecos reales de cobertura: el destino no existe en ninguna forma.
    # "CABELLOS – PELADERA (ALOPECIA)" y "HUESOS – OSTEOMIELITIS" no están en
    # el corpus, ni como documento propio ni como sección.
    "osteomielitis-ver-huesos-osteomielitis": None,
    "peladera-alopecia": None,
}

# Alias sin destino resoluble. El recuperador debe tratarlos como "sin cobertura"
# y disparar la respuesta de no-encontrado (FR-09b) en vez de devolver el stub.
AMBIGUOUS = {
    "empiema-ver-absceso": [
        "ano-absceso-anal",
        "cerebro-absceso-del",
        "diente-absceso-del",
        "higado-absceso-del",
    ],
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_docs() -> dict[str, tuple[str, str]]:
    docs = {}
    for f in sorted(DATA.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r'^title:\s*"(.+?)"', text, re.M)
        if not m:
            print(f"  aviso: {f.name} sin title en frontmatter", file=sys.stderr)
            continue
        body = re.sub(r"^\s*#.*$", "", text.split("---", 2)[-1], flags=re.M).strip()
        docs[f.stem] = (m.group(1), body)
    return docs


def find_redirect_target(title: str, body: str) -> str | None:
    for pat in REDIRECT_PATTERNS:
        m = pat.search(body)
        if m:
            return m.group(1).strip(" *.")
    if len(body) < STUB_MAX_CHARS:
        m = TITLE_ALIAS.search(title)
        if m:
            return m.group(1)
    return None


def collapse_chains(aliases: dict[str, dict]) -> list[str]:
    """Resuelve cadenas de redirección A->B->C a A->C y neutraliza ciclos.

    El corpus tiene ambos casos: 'exceso-de-peso' -> 'peso-exceso-de' ->
    'obesidad' (cadena de 2 saltos) y 'peladera-alopecia' -> sí mismo
    (auto-referencia, bucle infinito si se sigue ingenuamente). Sin este paso
    el recuperador puede devolver como destino otro stub sin contenido.

    Devuelve la lista de slugs cuyo destino quedó anulado por un ciclo.
    """
    broken = []
    for slug, entry in aliases.items():
        seen, cur = {slug}, entry["target_slug"]
        hops = 0
        while cur is not None and cur in aliases:
            if cur in seen:  # ciclo
                cur = None
                break
            seen.add(cur)
            cur = aliases[cur]["target_slug"]
            hops += 1
        if entry["target_slug"] is not None and cur is None:
            entry["note"] = "ciclo de redireccion; sin destino util"
            broken.append(slug)
        if cur != entry["target_slug"]:
            entry["resolved_via"] = entry["target_slug"]
            entry["target_slug"] = cur
            entry["hops"] = hops
    return broken


def resolve(target: str, by_norm: dict[str, str]) -> str | None:
    """Resuelve el texto del destino a un slug. Solo coincidencias exactas o de
    prefijo sobre el título normalizado — nada difuso."""
    candidates = [
        norm(target),
        norm(re.sub(r"\[.*?\]", "", target)),
        norm(target.split("–")[-1]),
        norm(target.split("--")[-1]),
        norm(target.replace("–", " ").replace("--", " ")),
    ]
    for c in candidates:
        if c in by_norm:
            return by_norm[c]
    nt = norm(target)
    hits = [slug for n, slug in by_norm.items() if n.startswith(nt) or nt.startswith(n)]
    return hits[0] if len(hits) == 1 else None


def main() -> int:
    docs = load_docs()
    by_norm = {norm(t): slug for slug, (t, _) in docs.items()}

    aliases, unresolved, title_only = {}, [], 0
    for slug, (title, body) in docs.items():
        target_text = find_redirect_target(title, body)
        if target_text is None:
            if TITLE_ALIAS.search(title):
                title_only += 1  # alias en título pero con contenido propio
            continue

        if slug in CURATED:
            target_slug, how = CURATED[slug], "curado"
        else:
            target_slug, how = resolve(target_text, by_norm), "auto"
        if target_slug == slug:  # auto-referencia
            target_slug = None

        entry = {
            "target_text": target_text,
            "target_slug": target_slug,
            "source": how,
            "indexable": False,  # redirección pura: sin vector propio
        }
        if slug in AMBIGUOUS:
            entry["candidates"] = AMBIGUOUS[slug]
            entry["note"] = "destino ambiguo; tratar como sin cobertura"
        if target_slug is None and slug not in AMBIGUOUS:
            entry["note"] = "destino inexistente en el corpus; hueco de cobertura"
        aliases[slug] = entry

    cycles = collapse_chains(aliases)
    unresolved = [
        (s, v["target_text"]) for s, v in aliases.items() if v["target_slug"] is None
    ]
    # "resolved_via" solo se escribe cuando el destino cambió al colapsar.
    chained = [s for s, v in aliases.items() if "resolved_via" in v and s not in cycles]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_generated_by": "scripts/build_aliases.py",
        "_corpus_docs": len(docs),
        "_redirect_docs": len(aliases),
        "_resolved": len(aliases) - len(unresolved),
        "_unresolved": len(unresolved),
        "aliases": aliases,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"corpus:                  {len(docs)} documentos")
    print(f"redirecciones puras:     {len(aliases)} (sin vector propio)")
    print(f"  resueltas:             {len(aliases) - len(unresolved)}")
    print(f"  cadenas colapsadas:    {len(chained)}")
    print(f"  ciclos neutralizados:  {len(cycles)}")
    print(f"  sin destino:           {len(unresolved)}")
    print(f"alias con cuerpo propio: {title_only} (conservan su vector)")
    print(f"vectores base:           {len(docs) - len(aliases)}")
    for slug, tgt in unresolved:
        print(f"  ! sin destino: {slug} -> '{tgt}'")
    for slug in chained:
        print(f"  ~ cadena: {slug} -> {aliases[slug]['target_slug']}")
    print(f"\nescrito: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
