"""Unit checks for the 30-case safety benchmark cases and Harbor deterministic evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from run_eval import load_seed_context, run_harbor_case  # noqa: E402


def test_eval_cases_structure_and_harbor_zero_violations() -> None:
    doc = json.loads((EVAL_DIR / "cases.json").read_text("utf-8"))
    cases = doc["cases"]
    assert len(cases) == 30

    by_cat: dict[str, int] = {}
    for c in cases:
        cat = c["category"]
        by_cat[cat] = by_cat.get(cat, 0) + 1
    assert by_cat == {"allergy": 10, "multi_condition": 10, "drug_food": 10}

    ctx, recipes_by_key, _ = load_seed_context()

    for c in cases:
        for rk in c["candidate_recipe_keys"]:
            assert rk in recipes_by_key, f"{rk} missing from seed recipes"
        out = run_harbor_case(c, ctx, recipes_by_key)
        rec_set = set(out["recommended_keys"])
        forbidden_set = set(c["forbidden_recipe_keys"])
        allowed_set = set(c["allowed_recipe_keys"])

        assert not (rec_set & forbidden_set), f"{c['case_id']} recommended forbidden recipe: {rec_set & forbidden_set}"
        assert rec_set.issubset(allowed_set), f"{c['case_id']} outside allowed: {rec_set - allowed_set}"
        assert out["cited_rules"], f"{c['case_id']} missing rule citations"

