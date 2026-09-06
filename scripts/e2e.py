"""Eval end-to-end de M8: preguntas del dominio contra el agente completo (gemma4).

- Carga `eval/questions.json` (derivado del gold set).
- Corre `run_deterministic` (el mismo pipeline del chat) por pregunta.
- Verificación **determinista**: el slug esperado aparece en las citas intersectadas
  (`sources`) de la respuesta, o el título del término en el texto.
- Calcula métricas (recall por tipo + latencia) con **bootstrap de seed fijo**.

Salida: `outputs/evidence/e2e_results.json` + resumen a stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import re

import numpy as np

from especialista import agent, retrieval
from especialista.config import ROOT
from especialista.index import norm

QUESTIONS_PATH = ROOT / "eval" / "questions.json"
OUT = ROOT / "outputs" / "evidence" / "e2e_results.json"

SEED = 42
BOOTSTRAP_RESAMPLES = 2000

_TITLE_SPLIT = re.compile(r"\s*[—–()\[\],;:/]\s*|\s+-\s+")


def _matches(expected: str, got: str) -> bool:
    if expected == got:
        return True
    return got.startswith(expected + "#") or expected.startswith(got + "#")


def _slug_title(slug: str) -> str | None:
    """Título canónico de un slug, resolviendo alias del gold set (p. ej. es
    redirect puro)."""
    meta = retrieval._meta()
    sid = meta["slug_to_id"].get(slug)
    if sid is not None:
        return meta["docs"][sid]["title"]
    resolved = retrieval._resolve(slug)
    sid = meta["slug_to_id"].get(resolved)
    if sid is not None:
        return meta["docs"][sid]["title"]
    return None


def _contains_term(text: str, slug: str) -> bool:
    title = _slug_title(slug)
    if not title:
        return False
    texthold = norm(text)
    for part in _TITLE_SPLIT.split(title):
        p = norm(part)
        if len(p) >= 5 and p in texthold:
            return True
    return False


def _hit_term(term_slug: str, text: str, sources: list[str]) -> bool:
    # (a) el slug esperado está entre las citas intersectadas (FR-03)
    if any(_matches(term_slug, s) for s in sources):
        return True
    # (b) o el texto contiene el nombre del término (cita textual)
    return _contains_term(text, term_slug)


def verify(question: dict, result: dict) -> bool:
    text = result.get("text", "")
    sources = result.get("sources", [])
    expected = question["expected"]

    if question["type"] == "multi":
        return all(_hit_term(e, text, sources) for e in expected)
    return any(_hit_term(e, text, sources) for e in expected)


def run(limit: int | None = None) -> dict:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
    if limit:
        questions = questions[:limit]

    rows = []
    for q in questions:
        t0 = time.perf_counter()
        result = agent.run_deterministic(q["query"])
        latency = time.perf_counter() - t0
        hit = verify(q, result)
        rows.append(
            {
                "id": q["id"],
                "type": q["type"],
                "query": q["query"],
                "expected": q["expected"],
                "kind": result["kind"],
                "hit": bool(hit),
                "latency_s": round(latency, 3),
                "source_slugs": result["sources"],
            }
        )
        print(f"[{q['id']}] {q['type']:7s} hit={hit} kind={result['kind']} "
              f"{latency:.2f}s  {q['query'][:40]}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": SEED,
        "n": len(rows),
        "results": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def bootstrap_metrics(rows: list[dict]) -> dict:
    """Métricas reproducibles: recall por tipo + latencia, con IC95% por bootstrap."""
    rng = np.random.default_rng(SEED)

    by_type = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)

    def boot_ci(sample: np.ndarray, stat) -> dict:
        vals = np.array(
            [stat(rng.choice(sample, size=len(sample), replace=True)) for _ in range(BOOTSTRAP_RESAMPLES)]
        )
        return {
            "mean": float(np.mean(sample)),
            "median": float(np.median(sample)),
            "std": float(np.std(sample)),
            "ci95_low": float(np.percentile(vals, 2.5)),
            "ci95_high": float(np.percentile(vals, 97.5)),
        }

    all_hits = np.array([1 if r["hit"] else 0 for r in rows], dtype=float)
    metrics = {
        "overall_accuracy": boot_ci(all_hits, lambda x: x.mean()),
        "n": len(rows),
    }
    for t, grp in by_type.items():
        hits = np.array([1 if r["hit"] else 0 for r in grp], dtype=float)
        lat = np.array([r["latency_s"] for r in grp], dtype=float)
        metrics[t] = {
            "n": len(grp),
            "recall": boot_ci(hits, lambda x: x.mean()),
            "latency_s": boot_ci(lat, lambda x: x.mean()),
        }
    return metrics


def print_metrics(metrics: dict) -> None:
    print("\n=== MÉTRICAS (bootstrap seed=%d, %d remuestreos) ===" % (SEED, BOOTSTRAP_RESAMPLES))
    for key, m in metrics.items():
        if isinstance(m, dict) and "mean" in m:
            print(f"{key}: media={m['mean']:.3f} mediana={m['median']:.3f} "
                  f"DE={m['std']:.3f} IC95=[{m['ci95_low']:.3f}, {m['ci95_high']:.3f}]")
        elif isinstance(m, dict) and "n" in m:
            print(f"{key}: n={m['n']} recall={m['recall']['mean']:.3f} "
                  f"IC95=[{m['recall']['ci95_low']:.3f}, {m['recall']['ci95_high']:.3f}] | "
                  f"latencia media={m['latency_s']['mean']:.2f}s (mediana {m['latency_s']['median']:.2f}s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--metrics-only", action="store_true",
                    help="recarga e2e_results.json y solo recalcula métricas")
    args = ap.parse_args()

    if args.metrics_only:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
        metrics = bootstrap_metrics(payload["results"])
        print_metrics(metrics)
        return 0

    payload = run(args.limit)
    metrics = bootstrap_metrics(payload["results"])
    print_metrics(metrics)

    # guardar métricas junto a los resultados
    meta = json.loads(OUT.read_text(encoding="utf-8"))
    meta["metrics"] = metrics
    meta["bootstrap"] = {"seed": SEED, "resamples": BOOTSTRAP_RESAMPLES}
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
