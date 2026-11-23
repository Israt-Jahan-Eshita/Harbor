"""Evaluation results endpoint (`GET /eval/results`) serving real measured outputs only."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/eval", tags=["eval"])


def _resolve_eval_dir() -> Path:
    env_dir = os.environ.get("EVAL_DIR")
    if env_dir:
        return Path(env_dir)
    for base in (Path(__file__).resolve().parents[3], Path(__file__).resolve().parents[2]):
        candidate = base / "eval"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[3] / "eval"


EVAL_DIR = _resolve_eval_dir()
EVAL_RESULTS_JSON = EVAL_DIR / "results.json"
EVAL_RESULTS_MD = EVAL_DIR / "results.md"


@router.get("/results")
def get_eval_results():
    """Return measured 30-case evaluation output if run, or an honest not_run status."""
    if EVAL_RESULTS_JSON.exists():
        data = json.loads(EVAL_RESULTS_JSON.read_text(encoding="utf-8"))
        md_text = EVAL_RESULTS_MD.read_text(encoding="utf-8") if EVAL_RESULTS_MD.exists() else ""
        return {"status": "available", "results": data, "markdown": md_text}

    return {
        "status": "not_run_yet",
        "results": None,
        "markdown": "",
        "note_bn": "৩০-কেস ইভ্যালুয়েশন এখনো চালানো হয়নি (ধাপ B18-এ চালানো হবে)।",
        "note_en": "The 30-case evaluation harness has not been run yet (scheduled for step B18).",
    }
