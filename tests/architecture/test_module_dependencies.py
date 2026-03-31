from __future__ import annotations

import ast
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "voxkeep"


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


def _find_import_violations() -> list[str]:
    violations: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        module_name = _module_name_for(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        module_parts = module_name.split(".")
        current_module = (
            module_parts[1] if len(module_parts) > 1 and module_parts[0] == "modules" else None
        )
        for imported in _imported_names(tree):
            if module_name.startswith("shared.") and imported.startswith("voxkeep.modules."):
                violations.append(f"{module_name} -> {imported}")
                continue
            if not module_name.startswith("modules."):
                continue
            if not imported.startswith("voxkeep.modules."):
                continue
            imported_parts = imported.split(".")
            imported_module = imported_parts[2] if len(imported_parts) > 2 else None
            if imported_module == current_module:
                continue
            if ".public" not in imported:
                violations.append(f"{module_name} -> {imported}")
    return sorted(violations)


def test_module_boundaries_only_allow_public_cross_module_imports() -> None:
    assert _find_import_violations() == []
