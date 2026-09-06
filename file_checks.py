"""Folder walking, filename/deadline checks for the marking tool.

This module never touches Maya or PSD internals - it only looks at the
filesystem: which competitor folders exist, which deliverable files are
present, whether names match the configured pattern, and whether files were
modified on time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MODEL_EXTENSIONS = (".mb", ".ma", ".max")
CONCEPT_EXTENSIONS = (".psd",)
DELIVERABLES_DIR_NAME = "deliverables"


@dataclass
class CompetitorFiles:
    competitor_number: str
    competitor_dir: Path
    deliverables_dir: Path | None  # None only if the folder truly has no files
    deliverables_dir_found: bool
    concept_path: Path | None
    model_path: Path | None

    @property
    def model_extension(self) -> str | None:
        return self.model_path.suffix.lower() if self.model_path else None

    @property
    def is_max_file(self) -> bool:
        return self.model_extension == ".max"


def discover_competitors(submissions_root: Path) -> list[CompetitorFiles]:
    """Each immediate subfolder of submissions_root is one competitor. The
    subfolder name is used verbatim as the competitor number (e.g. '07')."""
    submissions_root = Path(submissions_root)
    results: list[CompetitorFiles] = []
    for entry in sorted(submissions_root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        results.append(_discover_one(entry))
    return results


def _find_deliverables_dir(competitor_dir: Path) -> tuple[Path | None, bool]:
    for child in competitor_dir.iterdir():
        if child.is_dir() and child.name.lower() == DELIVERABLES_DIR_NAME:
            return child, True
    return None, False


def _first_file_with_ext(directory: Path, extensions: tuple[str, ...]) -> Path | None:
    matches: list[Path] = []
    for ext in extensions:
        matches.extend(directory.rglob(f"*{ext}"))
    if not matches:
        return None
    matches.sort(key=lambda p: str(p).lower())
    return matches[0]


def _discover_one(competitor_dir: Path) -> CompetitorFiles:
    competitor_number = competitor_dir.name
    deliverables_dir, found = _find_deliverables_dir(competitor_dir)
    search_dir = deliverables_dir if deliverables_dir is not None else competitor_dir

    concept_path = _first_file_with_ext(search_dir, CONCEPT_EXTENSIONS)
    model_path = _first_file_with_ext(search_dir, MODEL_EXTENSIONS)

    return CompetitorFiles(
        competitor_number=competitor_number,
        competitor_dir=competitor_dir,
        deliverables_dir=deliverables_dir,
        deliverables_dir_found=found,
        concept_path=concept_path,
        model_path=model_path,
    )


def expand_filename_pattern(pattern: str, competitor_number: str) -> str:
    """Substitute {n} in a configured filename pattern with the competitor
    number taken from the folder name."""
    return pattern.replace("{n}", competitor_number)


def filename_matches(actual_path: Path | None, pattern: str, competitor_number: str) -> bool:
    if actual_path is None:
        return False
    expected = expand_filename_pattern(pattern, competitor_number)
    return actual_path.name == expected  # case-sensitive, exact match


def get_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def submitted_on_time(path: Path | None, deadline: datetime) -> bool:
    if path is None or not path.exists():
        return False
    return get_mtime(path) <= deadline
