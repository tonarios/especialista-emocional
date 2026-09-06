"""Eval de recuperación sin LLM contra `eval/gold_set.json` (PRD §13.0).

Mide recall@k por tipo y la precisión (cero falsos positivos) en `out_of_domain`.
Se usa para elegir k, τ y el peso de fusión con datos ANTES de construir el agente.

Uso:
    python -m eval.retrieval --k 5
    python -m eval.retrieval --sweep          # barrido de k/tau/peso
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from especialista import retrieval
from especialista.config import ROOT
from especialista.index import slugify
from especialista.medical_safety import detect_emergency

GOLD_PATH = ROOT / "eval" / "gold_set.json"


def _matches(expected: str, got: str) -> bool:
    """Un slug recuperado satisface un slug esperado (soporta secciones #)."""
    if expected == got:
        return True
    if got.startswith(expected + "#") or expected.startswith(got + "#"):
        return True
    return False


def _hit(case: dict, results: list[dict]) -> bool:
    got = [r["slug"] for r in results]
    return any(_matches(e, g) for e in case["expected"] for g in got)


def evaluate(k: int, tau: float, lex_boost: float | None = None) -> dict:
    if lex_boost is not None:
        retrieval.LEX_BOOST = lex_boost
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))["cases"]

    stats: dict[str, dict] = {}
    missing: list[str] = []
    ood_fp: list[str] = []

    for case in gold:
        t = case["type"]
        stats.setdefault(t, {"total": 0, "ok": 0})
        if t == "emergency":
            # la recuperación no debe llegar: corta detect_emergency antes (FR-06)
            stats[t]["total"] += 1
            if detect_emergency(case["query"]) is not None:
                stats[t]["ok"] += 1
            else:
                missing.append(f"{case['id']} emergency no detectada")
            continue

        res = retrieval.search(case["query"], k=k, tau=tau)
        stats[t]["total"] += 1

        if t == "out_of_domain":
            if not res["covered"]:
                stats[t]["ok"] += 1
            else:
                ood_fp.append(f"{case['id']} {case['query'][:40]} -> {res['results'][0]['slug'] if res['results'] else ''}")
        elif t == "multi":
            if _hit(case, res["results"]):
                stats[t]["ok"] += 1
            else:
                missing.append(f"{case['id']} {case['query'][:40]}")
        else:  # single / alias / risk_tier
            if res["covered"] and _hit(case, res["results"]):
                stats[t]["ok"] += 1
            else:
                missing.append(f"{case['id']} {case['query'][:40]}")

    out = {"stats": stats, "missing": missing, "ood_false_positives": ood_fp}
    return out


def _report(k: int, tau: float, lex_boost: float, e: dict) -> None:
    print(f"\n=== k={k} tau={tau} lex_boost={lex_boost} ===")
    for t, s in e["stats"].items():
        if t == "out_of_domain":
            prec = s["ok"] / s["total"] if s["total"] else 0
            print(f"  {t:14s} precision_sin_cobertura {s['ok']}/{s['total']} = {prec:.3f}")
        else:
            rec = s["ok"] / s["total"] if s["total"] else 0
            print(f"  {t:14s} recall@{k} {s['ok']}/{s['total']} = {rec:.3f}")
    if e["missing"]:
        print("  MISS:")
        for m in e["missing"]:
            print(f"    - {m}")
    if e["ood_false_positives"]:
        print("  OOD FALSOS POSITIVOS:")
        for m in e["ood_false_positives"]:
            print(f"    - {m}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(GOLD_PATH))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--tau", type=float, default=None)
    ap.add_argument("--lex-boost", type=float, default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--pass-sweep", action="store_true", help="sólo imprime combinaciones que cumplen el gate")
    args = ap.parse_args()

    if args.sweep or args.pass_sweep:
        best = []
        for k in [3, 5, 6, 8]:
            for tau in [0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]:
                for lb in [0.30, 0.50, 0.70, 1.0]:
                    e = evaluate(k, tau, lb)
                    s = e["stats"]
                    single = s.get("single", {"ok": 0, "total": 1})
                    alias = s.get("alias", {"ok": 0, "total": 1})
                    ood = s.get("out_of_domain", {"ok": 0, "total": 1})
                    rec_s = single["ok"] / single["total"]
                    rec_a = alias["ok"] / alias["total"]
                    prec_o = ood["ok"] / ood["total"]
                    risk = s.get("risk_tier", {"ok": 0, "total": 1})
                    multi = s.get("multi", {"ok": 0, "total": 1})
                    rec_r = risk["ok"] / risk["total"]
                    rec_m = multi["ok"] / multi["total"]
                    ok_gate = (
                        rec_s >= 0.85 and rec_a >= 0.90 and prec_o >= 1.0
                        and rec_r >= 1.0 and rec_m >= 1.0
                    )
                    if args.pass_sweep and not ok_gate:
                        continue
                    row = (k, tau, lb, rec_s, rec_a, rec_r, rec_m, prec_o)
                    if ok_gate:
                        best.append(row)
                    else:
                        print(f"k={k} tau={tau} lb={lb} single={rec_s:.3f} alias={rec_a:.3f} "
                              f"risk={rec_r:.3f} multi={rec_m:.3f} ood={prec_o:.3f}")
        print("\n=== COMBINACIONES QUE CUMPLEN EL GATE ===")
        for r in best:
            print(f"k={r[0]} tau={r[1]} lex_boost={r[2]} single={r[3]:.3f} alias={r[4]:.3f} "
                  f"risk={r[5]:.3f} multi={r[6]:.3f} ood={r[7]:.3f}")
        if not best:
            print("  (ninguna)")
        return 0

    tau = args.tau if args.tau is not None else retrieval.TAU
    lb = args.lex_boost if args.lex_boost is not None else retrieval.LEX_BOOST
    e = evaluate(args.k, tau, lb)
    _report(args.k, tau, lb, e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
