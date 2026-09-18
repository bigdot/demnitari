"""Scrape receipt: which members finished which stage, for a given day.

A daily run writes run/receipt.json marking each member's stage1 (mechanical
scrape) and stage2 (LLM refinement). If a run is partial (e.g. Gemini 503s on
a batch), `scrape --continue` reads the receipt and redoes only the members
whose stages didn't pass — re-fetching just those, not all ~464. `attempts`
caps how many times the CI retry loop keeps going before giving up.
"""

from __future__ import annotations

import json
from pathlib import Path

FISIER = "receipt.json"


def cale(run_dir) -> Path:
    return Path(run_dir) / FISIER


def incarca(run_dir) -> dict | None:
    p = cale(run_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def salveaza(run_dir, rec: dict) -> None:
    p = cale(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def nou(data: str) -> dict:
    return {"data": data, "attempts": 1, "membri": {}}


def marcheaza(rec: dict, uid: str, *, s1: bool | None = None, s2: bool | None = None) -> None:
    stare = rec["membri"].setdefault(uid, {})
    if s1 is not None:
        stare["s1"] = s1
    if s2 is not None:
        stare["s2"] = s2


def incompleti(rec: dict) -> set[str]:
    """uids whose stage1 or stage2 hasn't passed yet."""
    return {uid for uid, s in rec["membri"].items() if not (s.get("s1") and s.get("s2"))}


def e_complet(rec: dict) -> bool:
    return not incompleti(rec)
