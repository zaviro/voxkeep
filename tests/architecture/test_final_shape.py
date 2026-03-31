from __future__ import annotations

import ast
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "voxkeep"
LEGACY_PREFIXES = ("voxkeep.core.", "voxkeep.infra.", "voxkeep.services.")
ALLOWED_LEGACY_FILES = {
    "core/__init__.py",
    "infra/__init__.py",
    "infra/asr/__init__.py",
    "infra/audio/__init__.py",
    "infra/storage/__init__.py",
    "infra/vad/__init__.py",
    "infra/wake/__init__.py",
    "services/__init__.py",
}


def _module_name_for(path: Path) -> str:
    return ".".join(path.relative_to(SRC_ROOT).with_suffix("").parts)


def _imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def _legacy_import_violations(package: str) -> list[str]:
    root = SRC_ROOT / package
    violations: list[str] = []
    for path in root.rglob("*.py"):
        module_name = _module_name_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported in _imported_names(tree):
            if imported.startswith(LEGACY_PREFIXES):
                violations.append(f"{module_name} -> {imported}")
    return sorted(violations)


def _legacy_runtime_files() -> list[str]:
    legacy_files: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT).as_posix()
        if rel.startswith("__pycache__/"):
            continue
        if rel.split("/", 1)[0] not in {"core", "infra", "services"}:
            continue
        if rel in ALLOWED_LEGACY_FILES:
            continue
        legacy_files.append(rel)
    return legacy_files


def test_shared_does_not_import_legacy_layers() -> None:
    assert _legacy_import_violations("shared") == []


def test_bootstrap_does_not_import_legacy_layers() -> None:
    assert _legacy_import_violations("bootstrap") == []


def test_repository_has_no_legacy_runtime_files() -> None:
    assert _legacy_runtime_files() == []
