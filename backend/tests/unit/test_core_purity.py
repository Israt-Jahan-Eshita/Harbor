"""Static AST check verifying app/core/ has zero network, LLM, DB, or API imports."""

from __future__ import annotations

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "app" / "core"

FORBIDDEN_TOP_LEVEL = {
    "httpx",
    "requests",
    "urllib",
    "urllib3",
    "aiohttp",
    "socket",
    "groq",
    "google",
    "sqlalchemy",
    "alembic",
    "pywebpush",
    "fastmcp",
    "fastapi",
}

FORBIDDEN_APP_PREFIXES = (
    "app.llm",
    "app.api",
    "app.db",
    "app.models",
    "app.config",
    "app.mcp",
)


def test_core_has_no_network_db_or_llm_imports() -> None:
    py_files = list(CORE_DIR.glob("*.py"))
    assert len(py_files) > 0
    violations: list[str] = []

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in FORBIDDEN_TOP_LEVEL or alias.name.startswith(FORBIDDEN_APP_PREFIXES):
                        violations.append(f"{py_file.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in FORBIDDEN_TOP_LEVEL or node.module.startswith(FORBIDDEN_APP_PREFIXES):
                    violations.append(f"{py_file.name}: from {node.module} import ...")

    assert violations == [], f"Forbidden imports in core/: {violations}"
