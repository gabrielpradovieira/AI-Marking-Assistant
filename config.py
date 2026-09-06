"""Persistent Test Project configuration.

Saved to %APPDATA%/SC2026MarkingTool/config.json (or, off Windows, the
platform equivalent under the user's home directory) so the Chief Expert
never has to retype the Test Project fields between sessions.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_DIR_NAME = "SC2026MarkingTool"
CONFIG_FILE_NAME = "config.json"

DEFAULTS = {
    "submissions_folder": "",
    "mayapy_path": "",
    "concept_deadline_date": "",  # "DD/MM/YYYY"
    "concept_deadline_time": "12:00",
    "model_deadline_date": "",
    "model_deadline_time": "16:30",
    "triangle_budget": 10000,
    "canvas_width": 3840,
    "canvas_height": 2160,
    "required_ppi": 300,
    "concept_filename_pattern": "ESC2026_TP50_{n}_Digital-Art.psd",
    "model_filename_pattern": "ESC2026_TP50_{n}_Diving_Helmet.mb",
}


@dataclass
class ToolConfig:
    submissions_folder: str = ""
    mayapy_path: str = ""
    concept_deadline_date: str = ""
    concept_deadline_time: str = "12:00"
    model_deadline_date: str = ""
    model_deadline_time: str = "16:30"
    triangle_budget: int = 10000
    canvas_width: int = 3840
    canvas_height: int = 2160
    required_ppi: int = 300
    concept_filename_pattern: str = "ESC2026_TP50_{n}_Digital-Art.psd"
    model_filename_pattern: str = "ESC2026_TP50_{n}_Diving_Helmet.mb"

    @classmethod
    def from_dict(cls, data: dict) -> "ToolConfig":
        merged = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
        return cls(**merged)

    def to_dict(self) -> dict:
        return asdict(self)


def get_config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata)
    else:
        # Non-Windows fallback (e.g. dev/test on Linux/macOS).
        base = Path.home() / ".config"
    return base / APP_DIR_NAME


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE_NAME


def load_config(path: Path | None = None) -> ToolConfig:
    path = path or get_config_path()
    if not path.exists():
        return ToolConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ToolConfig()
    return ToolConfig.from_dict(data)


def save_config(cfg: ToolConfig, path: Path | None = None) -> None:
    path = path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
