"""Identify tracked assets that are not referenced anywhere else in the repo."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_ROOTS = ("samples",)
DEFAULT_EXTENSIONS = (".pdf",)
DEFAULT_GLOBS = ("debug_*.py", "fix_*.py")


@dataclass(slots=True)
class ScanConfig:
    """Configuration for an orphan scan."""

    roots: tuple[str, ...]
    extensions: tuple[str, ...]
    globs: tuple[str, ...]


@dataclass(slots=True)
class ScanResult:
    """Result of scanning for orphaned assets."""

    candidates: list[Path]
    text_files: list[Path]
    orphans: list[Path]


def _git_ls_files() -> list[Path]:
    """Return the list of tracked files."""

    completed = subprocess.run(
        ["git", "ls-files"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return [Path(line) for line in completed.stdout.splitlines() if line]


def _is_text_file(path: Path) -> bool:
    """Heuristically detect whether ``path`` is a text file."""

    try:
        with path.open("rb") as handle:
            chunk = handle.read(1024)
    except OSError:
        return False

    if b"\0" in chunk:
        return False

    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _load_text_files(paths: Iterable[Path]) -> list[tuple[Path, str]]:
    """Read the text content for each path."""

    contents: list[tuple[Path, str]] = []
    for path in paths:
        try:
            data = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        contents.append((path, data))
    return contents


def _iter_candidates(
    tracked: Sequence[Path],
    config: ScanConfig,
) -> list[Path]:
    """Collect files that should be inspected for references."""

    candidates: list[Path] = []
    root_set = {root.rstrip("/") for root in config.roots}
    for path in tracked:
        if path.is_dir():
            continue

        if any(path.match(pattern) for pattern in config.globs):
            candidates.append(path)
            continue

        suffix = path.suffix.lower()
        if suffix and suffix in config.extensions:
            if any(str(path).startswith(f"{root}/") or str(path) == root for root in root_set):
                candidates.append(path)
    return candidates


def scan_for_orphans(config: ScanConfig) -> ScanResult:
    """Scan the repository for files that are not referenced anywhere else."""

    tracked = _git_ls_files()
    text_files = [path for path in tracked if _is_text_file(path)]
    text_contents = _load_text_files(text_files)
    candidates = _iter_candidates(tracked, config)

    orphans: list[Path] = []
    for candidate in candidates:
        candidate_str = str(candidate)
        referenced = False
        for text_path, content in text_contents:
            if text_path == candidate:
                continue
            if candidate_str in content:
                referenced = True
                break
        if not referenced:
            orphans.append(candidate)

    return ScanResult(candidates=candidates, text_files=text_files, orphans=orphans)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        dest="roots",
        action="append",
        help="Directory root to inspect (default: samples)",
    )
    parser.add_argument(
        "--ext",
        dest="extensions",
        action="append",
        help="File extension (including dot) to consider (default: .pdf)",
    )
    parser.add_argument(
        "--glob",
        dest="globs",
        action="append",
        help="Additional glob pattern for candidate files (default: debug_*.py, fix_*.py)",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="List all candidates instead of only orphaned files.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = ScanConfig(
        roots=tuple(args.roots or DEFAULT_ROOTS),
        extensions=tuple(ext.lower() for ext in (args.extensions or DEFAULT_EXTENSIONS)),
        globs=tuple(args.globs or DEFAULT_GLOBS),
    )

    result = scan_for_orphans(config)

    if args.show_all:
        print("Candidates:")
        for path in result.candidates:
            print(f"  - {path}")

    if result.orphans:
        print("Orphaned files detected:")
        for path in result.orphans:
            print(f"  - {path}")
    else:
        print("No orphaned files detected.")

    print()
    print(
        f"Scanned {len(result.candidates)} candidate(s) against {len(result.text_files)} text file(s)."
    )


if __name__ == "__main__":
    main()
