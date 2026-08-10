"""Enforce the core purity contract by walking the AST.

import-linter covers this in CI, but this test runs everywhere and needs no
extra tooling — so the contract holds even in a bare checkout.

If the core cannot reach the network, a database or a language model, then it
cannot be non-deterministic. That is the whole basis for trusting its output.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent

# Reaching any of these from the core would reintroduce non-determinism,
# hidden I/O, or an LLM into a rupee-producing code path.
FORBIDDEN_ROOTS = {
    # sibling application layers
    "backend.api",
    "backend.agents",
    "backend.db",
    "backend.services",
    "backend.rag",
    "backend.tools",
    "backend.orchestrator",
    "backend.security",
    "backend.evidence",
    "backend.procurement",
    "backend.llm",
    # language models
    "groq",
    "openai",
    "anthropic",
    "langchain",
    "langgraph",
    "transformers",
    "sentence_transformers",
    "fastembed",
    "onnxruntime",
    # network
    "httpx",
    "requests",
    "aiohttp",
    "urllib.request",
    "socket",
    # persistence
    "sqlalchemy",
    "asyncpg",
    "psycopg2",
    "redis",
    "qdrant_client",
    "boto3",
}

# Floats silently lose rupees. Money is Decimal, everywhere, no exceptions.
FLOAT_BANNED = {"float"}


def _core_modules() -> list[Path]:
    return sorted(
        p for p in CORE.rglob("*.py")
        if "tests" not in p.relative_to(CORE).parts
    )


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, stays inside core
                continue
            if node.module:
                names.add(node.module)
    return names


def _violates(imported: str) -> str | None:
    for bad in FORBIDDEN_ROOTS:
        if imported == bad or imported.startswith(bad + "."):
            return bad
    return None


@pytest.mark.parametrize("module", _core_modules(), ids=lambda p: str(p.name))
def test_core_module_imports_nothing_forbidden(module: Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for imported in sorted(_imported_names(tree)):
        bad = _violates(imported)
        assert bad is None, (
            f"{module.relative_to(CORE.parent)} imports '{imported}', which "
            f"breaks the core purity contract (forbidden root: '{bad}').\n"
            f"The core must stay free of I/O, persistence and language models. "
            f"Move this dependency to the calling layer and pass the data in."
        )


@pytest.mark.parametrize("module", _core_modules(), ids=lambda p: str(p.name))
def test_core_uses_no_float_construction(module: Path) -> None:
    """Catch `float(...)` in the core. Money must be Decimal end to end.

    v1 computed tax with floats throughout; the rounding drift is small per
    operation and unbounded across a return.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FLOAT_BANNED
        ):
            pytest.fail(
                f"{module.relative_to(CORE.parent)}:{node.lineno} calls "
                f"float(). Money paths in the core must use Decimal."
            )


def test_core_package_is_discoverable() -> None:
    """Guard against the skeleton silently losing its __init__ files."""
    expected = {"rules", "tax_engine", "eligibility", "costing", "provenance"}
    found = {
        p.name for p in CORE.iterdir()
        if p.is_dir() and (p / "__init__.py").exists() and p.name != "tests"
    }
    assert expected <= found, f"missing core subpackages: {expected - found}"
