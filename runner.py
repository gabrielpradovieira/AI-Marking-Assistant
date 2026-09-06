"""Orchestrates one full marking run: file checks, PSD parsing, the Maya
batch, scoring, Excel export, and the run log. This is the one function
main.py's background thread calls - it knows nothing about Qt.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import file_checks
import maya_launcher
import psd_utils
import scoring
from config import ToolConfig
from excel_export import CompetitorResult, export_results


@dataclass
class RunOutcome:
    competitor_results: list[CompetitorResult]
    excel_path: Path | None
    log_path: Path | None
    maya_available: bool


def parse_deadline(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str.strip()} {time_str.strip()}", "%d/%m/%Y %H:%M")


def run_marking(cfg: ToolConfig, mayapy_path: Path | None, on_progress=None) -> RunOutcome:
    """on_progress(event, data), if given, is called with:
      ("phase", "file_checks" | "maya_starting" | "scoring" | "done")
      ("competitor_progress", (index, total, competitor_number))   - file-check phase
      ("competitor_progress_maya", competitor_number)              - as each Maya result lands
    """
    log_lines: list[str] = []

    def log(msg: str) -> None:
        log_lines.append(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")

    def progress(event, data=None) -> None:
        if on_progress:
            on_progress(event, data)

    submissions_root = Path(cfg.submissions_folder)
    concept_deadline = parse_deadline(cfg.concept_deadline_date, cfg.concept_deadline_time)
    model_deadline = parse_deadline(cfg.model_deadline_date, cfg.model_deadline_time)

    log(f"Run started. Submissions folder: {submissions_root}")
    competitors = file_checks.discover_competitors(submissions_root)
    log(f"Found {len(competitors)} competitor folder(s).")

    progress("phase", "file_checks")
    raw_by_competitor: dict[str, scoring.RawMeasurements] = {}
    maya_jobs: list[dict] = []

    for idx, c in enumerate(competitors, start=1):
        progress("competitor_progress", (idx, len(competitors), c.competitor_number))

        concept_exists = c.concept_path is not None and c.concept_path.exists()
        model_exists = c.model_path is not None and c.model_path.exists()
        concept_mtime = file_checks.get_mtime(c.concept_path) if concept_exists else None
        model_mtime = file_checks.get_mtime(c.model_path) if model_exists else None

        concept_filename_ok = file_checks.filename_matches(
            c.concept_path, cfg.concept_filename_pattern, c.competitor_number)
        model_filename_ok = file_checks.filename_matches(
            c.model_path, cfg.model_filename_pattern, c.competitor_number)

        psd_error = None
        psd_width = psd_height = None
        psd_ppi = None
        if concept_exists:
            try:
                info = psd_utils.read_psd(c.concept_path)
                psd_width, psd_height = info.width, info.height
                psd_ppi = info.ppi_horizontal
            except Exception as exc:
                psd_error = f"PSD parse error: {exc}"
                log(f"Competitor {c.competitor_number}: {psd_error}")
        else:
            psd_error = "Concept file missing"

        if not model_exists:
            maya_status = "missing_model"
        elif c.is_max_file:
            maya_status = "max_unsupported"
            log(f"Competitor {c.competitor_number}: model is .max - Maya cannot open it, "
                f"manual marking required for D1-D6.")
        else:
            maya_status = "pending"
            maya_jobs.append({
                "competitor": c.competitor_number,
                "model_path": str(c.model_path),
                "triangle_budget": cfg.triangle_budget,
            })

        raw_by_competitor[c.competitor_number] = scoring.RawMeasurements(
            competitor_number=c.competitor_number,
            concept_path_name=c.concept_path.name if c.concept_path else None,
            model_path_name=c.model_path.name if c.model_path else None,
            concept_exists=concept_exists,
            model_exists=model_exists,
            concept_mtime=concept_mtime,
            model_mtime=model_mtime,
            concept_deadline=concept_deadline,
            model_deadline=model_deadline,
            deliverables_dir_found=c.deliverables_dir_found,
            concept_filename_ok=concept_filename_ok,
            model_filename_ok=model_filename_ok,
            psd_error=psd_error,
            psd_width=psd_width,
            psd_height=psd_height,
            psd_ppi=psd_ppi,
            canvas_width=cfg.canvas_width,
            canvas_height=cfg.canvas_height,
            required_ppi=cfg.required_ppi,
            triangle_budget=cfg.triangle_budget,
            maya_status=maya_status,
        )

    maya_available = mayapy_path is not None
    maya_results: dict[str, dict] = {}
    if maya_jobs and maya_available:
        def maya_progress(event, data):
            if event == "maya_starting":
                progress("phase", "maya_starting")
            elif event == "competitor_done":
                progress("competitor_progress_maya", data)

        log(f"Starting Maya for {len(maya_jobs)} model file(s)...")
        maya_results = maya_launcher.run_maya_batch(mayapy_path, maya_jobs, on_progress=maya_progress)
        log("Maya phase complete.")
    elif maya_jobs and not maya_available:
        log("Maya not available - D1-D6 will show as NOT RUN for competitors with a model file.")

    for competitor_number, result in maya_results.items():
        m = raw_by_competitor[competitor_number]
        if result.get("status") == "ok":
            m.maya_status = "ok"
            m.triangles = result.get("triangles")
            m.ngon_count = result.get("ngon_count")
            m.inverted_normals = result.get("inverted_normals")
            m.inverted_check_failed = bool(result.get("inverted_normals_check_failed"))
            m.construction_history = result.get("construction_history")
            m.history_details = result.get("history_details")
            m.image_planes = result.get("image_planes")
            m.extra_cameras = result.get("extra_cameras") or []
            m.references = result.get("references") or []
            m.hidden_objects = result.get("hidden_objects") or []
            m.shell_candidates = result.get("shell_candidates") or []
        else:
            m.maya_status = "error"
            m.maya_error = result.get("error")
            log(f"Competitor {competitor_number}: Maya error - {m.maya_error}")

    for m in raw_by_competitor.values():
        if m.maya_status == "pending":
            m.maya_status = "not_run"

    progress("phase", "scoring")
    competitor_results: list[CompetitorResult] = []
    for c in competitors:
        m = raw_by_competitor[c.competitor_number]
        aspects = scoring.score_competitor(m)
        competitor_results.append(CompetitorResult(c.competitor_number, aspects))
        total = scoring.automated_total(aspects)
        log(f"Competitor {c.competitor_number}: automated total {total}/{scoring.AUTOMATED_MAX_TOTAL}")

    excel_path = None
    try:
        excel_path = export_results(competitor_results, submissions_root)
        log(f"Excel exported to {excel_path}")
    except Exception as exc:
        log(f"Excel export FAILED: {exc}")

    log_path = None
    try:
        log_path = submissions_root / "run_log.txt"
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    except OSError:
        pass

    progress("phase", "done")
    return RunOutcome(
        competitor_results=competitor_results,
        excel_path=excel_path,
        log_path=log_path,
        maya_available=maya_available,
    )
