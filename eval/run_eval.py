"""30-Case Safety Benchmark Runner comparing Plain Groq LLM vs Harbor Deterministic Engine."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from groq import Groq  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core.scoring import score_dishes  # noqa: E402
from app.core.shared_pot import find_shared_pot_dishes  # noqa: E402
from app.core.templates import render_fallback_menu_item  # noqa: E402
from app.core.types import (  # noqa: E402
    DietPresetData,
    DrugFoodRuleData,
    GuestEventData,
    IngredientData,
    MedicineData,
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    StockItemState,
)
from baseline import run_plain_groq_case  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
SEED_DIR = BACKEND_DIR / "app" / "seed"


def load_seed_context() -> tuple[RuleContext, dict[str, RecipeData], dict[str, dict[str, Any]]]:
    """Load pure-Python RuleContext and recipes directly from seed JSON files."""
    ing_raw = json.loads((SEED_DIR / "ingredients.json").read_text("utf-8"))["ingredients"]
    rec_raw = json.loads((SEED_DIR / "recipes.json").read_text("utf-8"))["recipes"]
    rules_raw = json.loads((SEED_DIR / "rules.json").read_text("utf-8"))["rules"]
    presets_raw = json.loads((SEED_DIR / "diet_presets.json").read_text("utf-8"))["presets"]
    drug_map_raw = json.loads((SEED_DIR / "drug_class_map.json").read_text("utf-8"))["classes"]

    ingredients = {row["key"]: IngredientData(**row) for row in ing_raw}
    known_classes = set(drug_map_raw.keys()) | {
        "ace_inhibitor",
        "arb",
        "k_sparing_diuretic",
        "statin_cyp3a4",
        "none_modelled",
    }
    ctx = RuleContext(
        ingredients=ingredients,
        drug_food_rules=[DrugFoodRuleData(**r) for r in rules_raw],
        diet_presets=[DietPresetData(**p) for p in presets_raw],
        known_drug_classes=known_classes,
    )

    recipes_by_key: dict[str, RecipeData] = {}
    recipes_raw_by_key: dict[str, dict[str, Any]] = {}
    for row in rec_raw:
        recipes_raw_by_key[row["key"]] = row
        recipes_by_key[row["key"]] = RecipeData(
            id=row["key"],
            key=row["key"],
            name_bn=row["name_bn"],
            name_en=row["name_en"],
            servings_base=row["servings_base"],
            ingredients=[RecipeIngredientData(**ri) for ri in row["ingredients"]],
            steps_bn=row.get("steps_bn", []),
            split_step_bn=row.get("split_step_bn"),
            split_removes=row.get("split_removes", []),
            taste_score=row.get("taste_score", 0.75),
            category=row.get("category", "mixed"),
            est_cost_bdt=row.get("est_cost_bdt"),
        )
    return ctx, recipes_by_key, recipes_raw_by_key


def run_harbor_case(
    case: dict[str, Any],
    ctx: RuleContext,
    recipes_by_key: dict[str, RecipeData],
) -> dict[str, Any]:
    """Evaluate one benchmark case using Harbor's deterministic core + template fallback."""
    members: list[MemberData] = []
    for idx, m in enumerate(case.get("members", [])):
        meds = [
            MedicineData(
                id=f"med-{idx}-{mi}",
                name_as_written=med["name_as_written"],
                drug_class=med.get("drug_class"),
                verified_by_caregiver=bool(med.get("verified_by_caregiver", True)),
                active=bool(med.get("active", True)),
            )
            for mi, med in enumerate(m.get("medicines", []))
        ]
        members.append(
            MemberData(
                id=f"mem-{idx}",
                name=m["name"],
                role=m.get("role", "patient"),
                age_group=m.get("age_group", "adult"),
                allergies=list(m.get("allergies", [])),
                diet_presets=list(m.get("diet_presets", [])),
                medicines=meds,
            )
        )

    guests = [
        GuestEventData(
            guest_count=int(g.get("guest_count", 1)),
            restrictions=list(g.get("restrictions", [])),
        )
        for g in case.get("guests", [])
    ]

    candidate_recipes = [recipes_by_key[k] for k in case["candidate_recipe_keys"]]
    shared = find_shared_pot_dishes(
        members=members,
        recipes=candidate_recipes,
        context=ctx,
        guests=guests,
        for_date=date(2026, 11, 22),
        meal="dinner",
    )

    # Full neutral pantry stock so safety + taste/season drive the top-3 candidate list
    neutral_stock = {
        ikey: StockItemState(ingredient_key=ikey, raw_qty=5000.0, qty_base=5000.0)
        for ikey in ctx.ingredients
    }
    scored = score_dishes(
        candidates=shared.candidates,
        stock_map=neutral_stock,
        context=ctx,
        current_month=11,
        household_budget_bdt=15000,
        people_count=shared.people_count,
    )
    top_3 = scored[:3]
    cands_by_id = {c.recipe.id: c for c in shared.candidates}
    fallback_exps = [
        render_fallback_menu_item(cands_by_id[d.recipe.id])
        for d in top_3
        if d.recipe.id in cands_by_id
    ]

    recommended_keys = [d.recipe.key for d in top_3]
    cited_rules: list[str] = []
    for exp in fallback_exps:
        cited_rules.extend(exp.get("rule_ids", []))
    for ex in shared.excluded:
        cited_rules.extend(ex.reasons)
    cited_rules = list(dict.fromkeys(cited_rules))

    return {
        "recommended_keys": recommended_keys,
        "excluded_keys": [e.recipe.key for e in shared.excluded],
        "cited_rules": cited_rules,
        "excluded_details": [
            {"key": e.recipe.key, "reasons": e.reasons} for e in shared.excluded
        ],
    }


def _evaluate_run_Outcome(case: dict[str, Any], rec_keys: list[str], cited_rules: list[str]) -> dict[str, bool]:
    forbidden = set(case["forbidden_recipe_keys"])
    allowed = set(case["allowed_recipe_keys"])
    recommended = set(rec_keys)

    unsafe = bool(recommended & forbidden)
    missed_opportunity = bool(allowed) and not bool(recommended)
    all_valid_allowed = recommended.issubset(allowed)
    has_citation = bool(cited_rules)
    return {
        "unsafe": unsafe,
        "missed_opportunity": missed_opportunity,
        "all_valid_allowed": all_valid_allowed,
        "has_citation": has_citation,
    }


def aggregate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {
            "total_runs": 0,
            "unsafe_recommendation_count": 0,
            "unsafe_recommendation_rate": 0.0,
            "rule_citation_rate": 0.0,
            "valid_json_rate": 0.0,
        }
    unsafe_cnt = sum(1 for r in records if r["unsafe"])
    cite_cnt = sum(1 for r in records if r["has_citation"])
    valid_json_cnt = sum(1 for r in records if r.get("valid_json", True))
    missed_cnt = sum(1 for r in records if r["missed_opportunity"])
    return {
        "total_runs": total,
        "unsafe_recommendation_count": unsafe_cnt,
        "unsafe_recommendation_rate": round(unsafe_cnt / total, 4),
        "missed_opportunity_count": missed_cnt,
        "rule_citation_count": cite_cnt,
        "rule_citation_rate": round(cite_cnt / total, 4),
        "valid_json_rate": round(valid_json_cnt / total, 4),
    }


def format_markdown_report(summary: dict[str, Any]) -> str:
    """Render honest ASCII/Markdown benchmark report (zero emojis)."""
    h_all = summary["harbor"]["overall"]
    b_all = summary["baseline"]["overall"]
    h_cat = summary["harbor"]["by_category"]
    b_cat = summary["baseline"]["by_category"]

    def pct(val: float) -> str:
        return f"{val * 100:.1f}%"

    lines = [
        "# Harbor 30-Case Safety Benchmark Results",
        "",
        f"- **Generated (UTC):** `{summary['generated_at']}`",
        f"- **Benchmark Cases:** `{summary['case_count']}` (10 `allergy`, 10 `multi_condition`, 10 `drug_food` — human-authored)",
        f"- **Baseline Model:** `{summary['baseline_model']}` (plain JSON prompt, no core rules or MCP tools, `{summary['runs_per_case']}` runs/case)",
        f"- **Harbor Engine:** Pure-Python deterministic rules (`check_dish_safe`, `find_shared_pot_dishes`) + template grounding",
        "",
        "## Overall Comparison",
        "",
        "| Metric | Plain LLM Baseline | Harbor Engine |",
        "| :--- | ---: | ---: |",
        f"| Total Evaluations | {b_all['total_runs']} | {h_all['total_runs']} |",
        f"| Unsafe Recommendation Rate (Lower Better) | {pct(b_all['unsafe_recommendation_rate'])} ({b_all['unsafe_recommendation_count']}/{b_all['total_runs']}) | {pct(h_all['unsafe_recommendation_rate'])} ({h_all['unsafe_recommendation_count']}/{h_all['total_runs']}) |",
        f"| Explicit Rule Citation Rate (Higher Better) | {pct(b_all['rule_citation_rate'])} ({b_all['rule_citation_count']}/{b_all['total_runs']}) | {pct(h_all['rule_citation_rate'])} ({h_all['rule_citation_count']}/{h_all['total_runs']}) |",
        f"| Valid Structured Output Rate | {pct(b_all['valid_json_rate'])} | {pct(h_all['valid_json_rate'])} |",
        "",
        "## Category Breakdown (Unsafe Recommendation Rate)",
        "",
        "| Category | Plain LLM Baseline | Harbor Engine |",
        "| :--- | ---: | ---: |",
    ]
    for cat, label in (
        ("allergy", "Food Allergies (`A01`-`A10`)"),
        ("multi_condition", "Multi-Condition & Age (`M01`-`M10`)"),
        ("drug_food", "Drug-Food & Fail-Safe (`D01`-`D10`)"),
    ):
        bc = b_cat[cat]
        hc = h_cat[cat]
        lines.append(
            f"| {label} | {pct(bc['unsafe_recommendation_rate'])} ({bc['unsafe_recommendation_count']}/{bc['total_runs']}) | "
            f"{pct(hc['unsafe_recommendation_rate'])} ({hc['unsafe_recommendation_count']}/{hc['total_runs']}) |"
        )

    lines.extend(["", "## Per-Case Measured Outcomes", "", "| Case | Category | Harbor Recs | Harbor Unsafe | Baseline Unsafe Runs | Notes |", "| :--- | :--- | :--- | :---: | :---: | :--- |"])
    for c in summary["per_case"]:
        h_recs = ", ".join(c["harbor"]["recommended_keys"]) or "NONE (Excluded)"
        b_uns = sum(1 for r in c["baseline_runs"] if r["unsafe"])
        b_tot = len(c["baseline_runs"])
        lines.append(
            f"| `{c['case_id']}` | `{c['category']}` | {h_recs} | "
            f"{'YES' if c['harbor']['unsafe'] else 'NO'} | {b_uns}/{b_tot} | {c['title']} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Harbor 30-case safety benchmark.")
    parser.add_argument("--runs", type=int, default=3, help="Number of plain LLM runs per case")
    parser.add_argument("--harbor-only", action="store_true", help="Only evaluate Harbor core deterministically")
    args = parser.parse_args()

    cases_doc = json.loads((EVAL_DIR / "cases.json").read_text("utf-8"))
    cases = cases_doc["cases"]
    ctx, recipes_by_key, recipes_raw_by_key = load_seed_context()

    # Sanity-check every case references valid seed recipe keys
    for c in cases:
        for rk in c["candidate_recipe_keys"]:
            if rk not in recipes_by_key:
                raise KeyError(f"Unknown recipe key '{rk}' in case {c['case_id']}")

    settings = get_settings()
    client = None if args.harbor_only else Groq(api_key=settings.groq_api_key)
    if not args.harbor_only and not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY missing in backend/.env for baseline evaluation.")

    harbor_records: list[dict[str, Any]] = []
    baseline_records: list[dict[str, Any]] = []
    per_case_out: list[dict[str, Any]] = []

    for c_idx, case in enumerate(cases, start=1):
        h_res = run_harbor_case(case, ctx, recipes_by_key)
        h_eval = _evaluate_run_Outcome(case, h_res["recommended_keys"], h_res["cited_rules"])
        harbor_rec = {
            "case_id": case["case_id"],
            "category": case["category"],
            "valid_json": True,
            **h_res,
            **h_eval,
        }
        harbor_records.append(harbor_rec)

        b_runs: list[dict[str, Any]] = []
        if not args.harbor_only and client is not None:
            for r_i in range(1, args.runs + 1):
                b_raw = run_plain_groq_case(
                    client=client,
                    model=settings.llm_model,
                    case=case,
                    recipes_by_key=recipes_raw_by_key,
                )
                b_eval = _evaluate_run_Outcome(case, b_raw["recommended_keys"], b_raw["cited_rules"])
                rec = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "run": r_i,
                    **b_raw,
                    **b_eval,
                }
                b_runs.append(rec)
                baseline_records.append(rec)
                print(
                    f"[{c_idx:02d}/{len(cases)} run {r_i}/{args.runs}] {case['case_id']} -> "
                    f"recs={b_raw['recommended_keys']} unsafe={b_eval['unsafe']} err={b_raw['error']}"
                )
                time.sleep(0.35)

        per_case_out.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "title": case["title"],
                "forbidden_recipe_keys": case["forbidden_recipe_keys"],
                "allowed_recipe_keys": case["allowed_recipe_keys"],
                "harbor": harbor_rec,
                "baseline_runs": b_runs,
            }
        )

    categories = ("allergy", "multi_condition", "drug_food")
    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "runs_per_case": 0 if args.harbor_only else args.runs,
        "baseline_model": settings.llm_model,
        "harbor": {
            "overall": aggregate_metrics(harbor_records),
            "by_category": {
                cat: aggregate_metrics([r for r in harbor_records if r["category"] == cat])
                for cat in categories
            },
        },
        "baseline": {
            "overall": aggregate_metrics(baseline_records),
            "by_category": {
                cat: aggregate_metrics([r for r in baseline_records if r["category"] == cat])
                for cat in categories
            },
        },
        "per_case": per_case_out,
    }

    if args.harbor_only:
        print("Harbor-only dry run:", json.dumps(summary["harbor"], ensure_ascii=False, indent=2))
        return 0

    (EVAL_DIR / "results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (EVAL_DIR / "results.md").write_text(format_markdown_report(summary), encoding="utf-8")
    print("Benchmark finished cleanly! Harbor:", summary["harbor"]["overall"])
    print("Baseline:", summary["baseline"]["overall"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
