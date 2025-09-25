#!/usr/bin/env python3
"""Analyze Python modules to find files that are not imported by others."""
from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

DEFAULT_SCAN_DIRS = ("api", "engine", "services", "rules")
SKIP_DIR_NAMES = {"tests", "__pycache__", "scripts"}


@dataclass
class ImportEntry:
    """Represents a resolved import relationship."""

    target_module: str
    lineno: int
    raw: str


@dataclass
class ModuleInfo:
    module: str
    path: Path
    references: List[ImportEntry]
    is_entrypoint: bool = False
    parse_error: Optional[str] = None


class ImportCollector(ast.NodeVisitor):
    """Collect import statements and expose them for later resolution."""

    def __init__(self, module: str) -> None:
        self.module = module
        self.entries: List[Tuple[str, int, str, Optional[int], Sequence[str]]] = []
        super().__init__()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self.entries.append(("import", node.lineno, alias.name, None, (alias.name,)))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        names = tuple(alias.name for alias in node.names)
        self.entries.append(("from", node.lineno, node.module or "", node.level, names))
        self.generic_visit(node)


def discover_python_modules(root: Path, scan_dirs: Sequence[str]) -> Dict[str, Path]:
    modules: Dict[str, Path] = {}
    for directory in scan_dirs:
        base = root / directory
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if should_skip(path):
                continue
            rel_path = path.relative_to(root)
            module_name = ".".join(rel_path.with_suffix("").parts)
            modules[module_name] = path
    return modules


def should_skip(path: Path) -> bool:
    if path.name == "__init__.py":
        return True
    for part in path.parts:
        if part in SKIP_DIR_NAMES:
            return True
    return False


def normalize_relative_module(current_module: str, module: str, level: Optional[int]) -> Optional[str]:
    if level is None or level == 0:
        return module or None
    current_parts = current_module.split(".")
    if level > len(current_parts):
        base_parts: List[str] = []
    else:
        base_parts = list(current_parts[:-level])
    if module:
        base_parts.extend(module.split("."))
    if not base_parts:
        return None
    return ".".join(base_parts)


def resolve_imports(
    current_module: str,
    collector: ImportCollector,
    module_map: Dict[str, Path],
) -> Iterable[ImportEntry]:
    for entry_type, lineno, module, level, names in collector.entries:
        raw_statement = format_raw_statement(entry_type, module, level, names)
        if entry_type == "import":
            for name in names:
                yield from resolve_import_name(name, lineno, raw_statement, module_map)
        else:
            base_module = normalize_relative_module(current_module, module, level)
            if not base_module:
                continue
            # Handle star imports by recording the base module if it exists.
            if names == ("*",):
                if base_module in module_map:
                    yield ImportEntry(base_module, lineno, raw_statement)
                continue
            for imported_name in names:
                candidate = f"{base_module}.{imported_name}" if base_module else imported_name
                if candidate in module_map:
                    yield ImportEntry(candidate, lineno, raw_statement)
                    continue
                if base_module in module_map:
                    yield ImportEntry(base_module, lineno, raw_statement)


def resolve_import_name(name: str, lineno: int, raw: str, module_map: Dict[str, Path]) -> Iterable[ImportEntry]:
    candidate = name
    while candidate:
        if candidate in module_map:
            yield ImportEntry(candidate, lineno, raw)
            return
        if "." not in candidate:
            break
        candidate = candidate.rsplit(".", 1)[0]
    # No direct match, so we do not yield anything.
    return


def format_raw_statement(
    entry_type: str, module: str, level: Optional[int], names: Sequence[str]
) -> str:
    if entry_type == "import":
        return f"import {', '.join(names)}"
    dots = "." * (level or 0)
    target = module or ""
    names_part = ", ".join(names)
    return f"from {dots}{target} import {names_part}".strip()


def detect_entrypoint(tree: ast.AST, path: Path) -> bool:
    # Treat files named main.py or containing a __main__ guard as entrypoints.
    if path.name == "main.py":
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if is_main_guard(node):
                return True
    return False


def is_main_guard(node: ast.If) -> bool:
    comparison = node.test
    if isinstance(comparison, ast.Compare):
        left = comparison.left
        comparators = comparison.comparators
        if (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and len(comparators) == 1
            and isinstance(comparators[0], ast.Constant)
            and comparators[0].value == "__main__"
        ):
            return True
    return False


def analyze_modules(root: Path, scan_dirs: Sequence[str], extra_roots: Sequence[str]) -> Dict[str, ModuleInfo]:
    module_map = discover_python_modules(root, scan_dirs)
    info_map: Dict[str, ModuleInfo] = {
        module: ModuleInfo(module=module, path=path, references=[])
        for module, path in module_map.items()
    }
    root_candidates: Set[str] = set(extra_roots)

    for module, path in module_map.items():
        try:
            source = path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - best effort logging
            info_map[module].parse_error = f"Unable to read file: {exc}"
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            info_map[module].parse_error = f"SyntaxError: {exc.msg} (line {exc.lineno})"
            continue

        collector = ImportCollector(module)
        collector.visit(tree)
        info_map[module].is_entrypoint = detect_entrypoint(tree, path) or module in root_candidates

        for entry in resolve_imports(module, collector, module_map):
            info_map[entry.target_module].references.append(
                ImportEntry(target_module=module, lineno=entry.lineno, raw=entry.raw)
            )

    return info_map


def summarize(
    info_map: Dict[str, ModuleInfo], extra_roots: Sequence[str], root: Path
) -> Dict[str, object]:
    stats = {
        "total_modules": len(info_map),
        "modules_with_references": sum(1 for info in info_map.values() if info.references),
        "parse_errors": sum(1 for info in info_map.values() if info.parse_error),
    }
    roots = {info.module for info in info_map.values() if info.is_entrypoint}
    roots.update(extra_roots)

    orphans: List[Dict[str, object]] = []
    modules_payload: List[Dict[str, object]] = []

    for module in sorted(info_map):
        info = info_map[module]
        references_payload = [
            {
                "module": ref.target_module,
                "path": str(info_map[ref.target_module].path.relative_to(root)),
                "lineno": ref.lineno,
                "import": ref.raw,
            }
            for ref in sorted(info.references, key=lambda r: (r.target_module, r.lineno))
        ]
        module_payload = {
            "module": module,
            "path": str(info.path.relative_to(root)),
            "is_entrypoint": info.is_entrypoint,
            "references": references_payload,
        }
        if info.parse_error:
            module_payload["parse_error"] = info.parse_error
        modules_payload.append(module_payload)
        if not info.references and module not in roots:
            orphans.append(
                {
                    "module": module,
                    "path": str(info.path.relative_to(root)),
                    "reason": "No incoming imports",
                }
            )

    stats["entrypoints"] = sorted(roots)
    stats["orphan_count"] = len(orphans)

    return {
        "stats": stats,
        "modules": modules_payload,
        "orphans": orphans,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Find potentially orphaned Python modules.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to project root)",
    )
    parser.add_argument(
        "--dirs",
        nargs="*",
        default=list(DEFAULT_SCAN_DIRS),
        help="Directories to scan for Python modules",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write JSON output (defaults to stdout)",
    )
    parser.add_argument(
        "--extra-root",
        dest="extra_roots",
        action="append",
        default=[],
        help="Treat additional modules as entrypoints (can be repeated)",
    )
    args = parser.parse_args()

    info_map = analyze_modules(args.root, args.dirs, args.extra_roots)
    summary = summarize(info_map, args.extra_roots, args.root)

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
