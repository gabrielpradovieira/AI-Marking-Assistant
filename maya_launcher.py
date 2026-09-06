"""Finds Maya, and drives maya_worker.py as a subprocess.

Runs the whole batch of model files in ONE mayapy session (startup is ~25s,
so starting it per-file would be far too slow). If mayapy hangs or crashes
outright, this restarts it only for the files that never got a result -
ordinary per-file problems (corrupt scene, one bad mesh) are retried inside
maya_worker.py itself and never reach this restart path.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAYA_INSTALL_ROOT = Path("C:/Program Files/Autodesk")
MAYA_STARTUP_BUFFER_SECONDS = 60  # generous allowance for mayapy.exe startup (~25s observed)
MAX_RESTARTS = 3


def find_mayapy() -> Path | None:
    """Scans C:\\Program Files\\Autodesk\\Maya*\\bin\\mayapy.exe and returns
    the highest version found, or None if Maya isn't installed."""
    if not MAYA_INSTALL_ROOT.exists():
        return None
    candidates = list(MAYA_INSTALL_ROOT.glob("Maya*/bin/mayapy.exe"))
    if not candidates:
        return None

    def version_key(p: Path) -> int:
        m = re.search(r"Maya(\d+)", str(p))
        return int(m.group(1)) if m else 0

    candidates.sort(key=version_key, reverse=True)
    return candidates[0]


def get_maya_version_label(mayapy_path: Path) -> str:
    m = re.search(r"Maya(\d+)", str(mayapy_path))
    return f"Maya {m.group(1)}" if m else "Maya (version unknown)"


def worker_script_path() -> Path:
    """Path to maya_worker.py, whether running from source or as a
    PyInstaller-frozen exe (where it's bundled as --add-data and extracted
    to sys._MEIPASS at runtime)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "maya_worker.py"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "maya_worker.py"


def run_maya_batch(
    mayapy_path: Path,
    jobs: list[dict],
    timeout_per_file: int = 60,
    on_progress=None,
    max_restarts: int = MAX_RESTARTS,
    worker_path: Path | None = None,
) -> dict[str, dict]:
    """Runs every job (each: competitor/model_path/triangle_budget) through
    maya_worker.py. Returns {competitor: result_dict}.

    on_progress, if given, is called as on_progress(event, competitor):
      - ("maya_starting", None) once, before the first mayapy launch
      - ("competitor_done", competitor_number) after each result lands
    """
    worker_path = worker_path or worker_script_path()
    remaining = list(jobs)
    all_results: dict[str, dict] = {}
    restarts = 0
    started = False

    with tempfile.TemporaryDirectory(prefix="sc2026_marking_") as tmp:
        tmp_path = Path(tmp)

        while remaining:
            jobs_path = tmp_path / f"jobs_{restarts}.json"
            results_path = tmp_path / f"results_{restarts}.json"
            jobs_path.write_text(json.dumps({"jobs": remaining}), encoding="utf-8")

            if on_progress and not started:
                on_progress("maya_starting", None)
                started = True

            total_timeout = MAYA_STARTUP_BUFFER_SECONDS + timeout_per_file * len(remaining) + 30
            cmd = [
                str(mayapy_path), str(worker_path),
                "--input", str(jobs_path), "--output", str(results_path),
                "--timeout", str(timeout_per_file),
            ]
            try:
                proc = subprocess.run(cmd, timeout=total_timeout, capture_output=True, text=True)
                process_crashed = proc.returncode != 0
            except subprocess.TimeoutExpired:
                process_crashed = True

            partial: dict[str, dict] = {}
            if results_path.exists():
                try:
                    partial = json.loads(results_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    partial = {}

            all_results.update(partial)
            if on_progress:
                for competitor in partial:
                    on_progress("competitor_done", competitor)

            still_remaining = [j for j in remaining if j["competitor"] not in partial]

            if not still_remaining:
                break

            if not process_crashed:
                # mayapy exited cleanly but didn't produce a result for
                # everything - treat the gap as a failure rather than loop.
                for j in still_remaining:
                    all_results[j["competitor"]] = {
                        "status": "error", "error": "No result produced by Maya worker",
                    }
                    if on_progress:
                        on_progress("competitor_done", j["competitor"])
                break

            restarts += 1
            if restarts > max_restarts:
                for j in still_remaining:
                    all_results[j["competitor"]] = {
                        "status": "error", "error": "Maya restart limit exceeded",
                    }
                    if on_progress:
                        on_progress("competitor_done", j["competitor"])
                break

            # The next unprocessed job is the most likely culprit for the
            # crash - skip it, and restart mayapy for whatever is left.
            culprit = still_remaining[0]
            all_results[culprit["competitor"]] = {
                "status": "error", "error": "Maya crashed or became unresponsive while processing this file",
            }
            if on_progress:
                on_progress("competitor_done", culprit["competitor"])
            remaining = still_remaining[1:]

    return all_results
