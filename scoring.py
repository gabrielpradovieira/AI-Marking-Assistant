"""Marking rules for SC2026 Skill 50.

Every aspect is binary: full marks or zero, per WorldSkills convention. This
module does not walk folders, parse PSDs or talk to Maya - it only turns
already-measured facts into marks, following the table in the build brief.

The 24 official aspects are listed here in competition order (A, B, C, D) so
the Excel "Full Marking Sheet" can be generated straight off this list. Only
11 of them (42 marks) are scored automatically; the rest are left blank for
the Chief Expert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


AUTOMATED = "automated"
MANUAL_OBSERVATION = "manual_observation"
MANUAL_JUDGEMENT = "manual_judgement"

PROVISIONAL_NOTE = "REVIEW"


@dataclass
class AspectDef:
    id: str
    criterion: str  # "A", "B", "C", "D"
    name: str
    max_mark: int
    kind: str


# Official order and marks, per the SC2026 Skill 50 marking scheme.
ASPECT_DEFS: list[AspectDef] = [
    AspectDef("A1", "A", "Submit on time", 3, AUTOMATED),
    AspectDef("A2", "A", "Folder names", 1, AUTOMATED),
    AspectDef("A3", "A", "Filenames", 1, AUTOMATED),
    AspectDef("B1", "B", "Polite behaviour", 2, MANUAL_OBSERVATION),
    AspectDef("B2", "B", "Problem-solving", 3, MANUAL_OBSERVATION),
    AspectDef("C1", "C", "Scale indication", 4, MANUAL_JUDGEMENT),
    AspectDef("C2", "C", "Image size / aspect", 4, AUTOMATED),
    AspectDef("C3", "C", "PPI", 4, AUTOMATED),
    AspectDef("C4", "C", "3/4 view", 5, MANUAL_JUDGEMENT),
    AspectDef("C5", "C", "Highlights", 4, MANUAL_JUDGEMENT),
    AspectDef("C6", "C", "Shadows", 4, MANUAL_JUDGEMENT),
    AspectDef("C7", "C", "Style match", 5, MANUAL_JUDGEMENT),
    AspectDef("C8", "C", "Creativity", 5, MANUAL_JUDGEMENT),
    AspectDef("C9", "C", "Functionality", 5, MANUAL_JUDGEMENT),
    AspectDef("D1", "D", "Scene organisation", 5, AUTOMATED),
    AspectDef("D2", "D", "Triangle budget", 6, AUTOMATED),
    AspectDef("D3", "D", "No n-gons", 6, AUTOMATED),
    AspectDef("D4", "D", "No inverted normals", 4, AUTOMATED),
    AspectDef("D5", "D", "No stray geometry", 4, AUTOMATED),
    AspectDef("D6", "D", "No modifiers / history", 4, AUTOMATED),
    AspectDef("D7", "D", "Resembles reference", 6, MANUAL_JUDGEMENT),
    AspectDef("D8", "D", "Quad distribution", 5, MANUAL_JUDGEMENT),
    AspectDef("D9", "D", "Edgeflow", 5, MANUAL_JUDGEMENT),
    AspectDef("D10", "D", "Materials", 5, MANUAL_JUDGEMENT),
]

AUTOMATED_IDS = [a.id for a in ASPECT_DEFS if a.kind == AUTOMATED]
AUTOMATED_MAX_TOTAL = sum(a.max_mark for a in ASPECT_DEFS if a.kind == AUTOMATED)
BEHAVIOUR_MAX_TOTAL = sum(a.max_mark for a in ASPECT_DEFS if a.kind == MANUAL_OBSERVATION)
JUDGEMENT_MAX_TOTAL = sum(a.max_mark for a in ASPECT_DEFS if a.kind == MANUAL_JUDGEMENT)
GRAND_MAX_TOTAL = sum(a.max_mark for a in ASPECT_DEFS)

# Column order for the Summary sheet / results table.
SUMMARY_COLUMNS = AUTOMATED_IDS


@dataclass
class AspectResult:
    id: str
    criterion: str
    name: str
    kind: str
    max_mark: int
    measured_value: str
    passed: bool | None  # None = manual (blank) or not run
    marks_awarded: int | None  # None = manual (blank)
    notes: str
    provisional: bool = False


@dataclass
class RawMeasurements:
    competitor_number: str

    # --- A: files / timing ---
    concept_path_name: str | None
    model_path_name: str | None
    concept_exists: bool
    model_exists: bool
    concept_mtime: datetime | None
    model_mtime: datetime | None
    concept_deadline: datetime
    model_deadline: datetime
    deliverables_dir_found: bool
    concept_filename_ok: bool
    model_filename_ok: bool

    # --- C: PSD ---
    psd_error: str | None = None
    psd_width: int | None = None
    psd_height: int | None = None
    psd_ppi: float | None = None
    canvas_width: int = 0
    canvas_height: int = 0
    required_ppi: float = 0.0

    # --- D: Maya ---
    triangle_budget: int = 0
    maya_status: str = "not_run"  # "ok" | "not_run" | "error" | "max_unsupported" | "missing_model"
    maya_error: str | None = None
    triangles: int | None = None
    ngon_count: int | None = None
    inverted_normals: int | None = None
    inverted_check_failed: bool = False
    construction_history: bool | None = None
    history_details: str | None = None
    image_planes: int | None = None
    extra_cameras: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    hidden_objects: list[str] = field(default_factory=list)
    shell_candidates: list[str] = field(default_factory=list)


def _result(defn: AspectDef, measured: str, passed: bool | None, notes: str = "",
            provisional: bool = False) -> AspectResult:
    marks = defn.max_mark if passed else 0
    return AspectResult(
        id=defn.id, criterion=defn.criterion, name=defn.name, kind=defn.kind,
        max_mark=defn.max_mark, measured_value=measured, passed=passed,
        marks_awarded=marks, notes=notes, provisional=provisional,
    )


def _manual_blank(defn: AspectDef) -> AspectResult:
    note = "OBSERVATION — CE" if defn.kind == MANUAL_OBSERVATION else "JUDGEMENT — CE"
    return AspectResult(
        id=defn.id, criterion=defn.criterion, name=defn.name, kind=defn.kind,
        max_mark=defn.max_mark, measured_value="", passed=None,
        marks_awarded=None, notes=note,
    )


_DEFS_BY_ID = {a.id: a for a in ASPECT_DEFS}


def _score_a1(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["A1"]
    parts = []
    if not m.concept_exists:
        parts.append("concept missing")
    elif m.concept_mtime and m.concept_mtime > m.concept_deadline:
        parts.append(f"concept late ({m.concept_mtime:%Y-%m-%d %H:%M} > {m.concept_deadline:%Y-%m-%d %H:%M})")
    if not m.model_exists:
        parts.append("model missing")
    elif m.model_mtime and m.model_mtime > m.model_deadline:
        parts.append(f"model late ({m.model_mtime:%Y-%m-%d %H:%M} > {m.model_deadline:%Y-%m-%d %H:%M})")

    passed = m.concept_exists and m.model_exists and not parts
    if passed:
        measured = (
            f"concept {m.concept_mtime:%Y-%m-%d %H:%M}, "
            f"model {m.model_mtime:%Y-%m-%d %H:%M}"
        )
    else:
        measured = "; ".join(parts) if parts else "not submitted"
    return _result(d, measured, passed)


def _score_a2(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["A2"]
    measured = "Deliverables folder present" if m.deliverables_dir_found else "Deliverables folder missing"
    return _result(d, measured, m.deliverables_dir_found)


def _score_a3(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["A3"]
    passed = m.concept_filename_ok and m.model_filename_ok
    bits = []
    bits.append(f"concept: {m.concept_path_name or 'missing'}")
    bits.append(f"model: {m.model_path_name or 'missing'}")
    return _result(d, "; ".join(bits), passed)


def _score_c2(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["C2"]
    if m.psd_error or m.psd_width is None or m.psd_height is None:
        return _result(d, m.psd_error or "PSD not readable", False)
    measured = f"{m.psd_width}x{m.psd_height}"
    passed = (m.psd_width == m.canvas_width) and (m.psd_height == m.canvas_height)
    return _result(d, measured, passed)


def _score_c3(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["C3"]
    if m.psd_error or m.psd_ppi is None:
        return _result(d, m.psd_error or "PSD not readable", False)
    measured = f"{m.psd_ppi:g} ppi"
    passed = abs(m.psd_ppi - m.required_ppi) <= 0.5
    return _result(d, measured, passed)


def _maya_not_available(m: RawMeasurements) -> AspectResult | None:
    """Returns a shared 'not applicable' result for all D aspects when Maya
    didn't produce usable data, or None if Maya data is available and normal
    per-aspect scoring should proceed."""
    if m.maya_status == "ok":
        return None
    if m.maya_status == "missing_model":
        return "missing_model"
    if m.maya_status == "max_unsupported":
        return "max_unsupported"
    if m.maya_status == "not_run":
        return "not_run"
    return "error"


def _score_maya_dependent(defn: AspectDef, m: RawMeasurements, ok_scorer) -> AspectResult:
    status = _maya_not_available(m)
    if status is None:
        return ok_scorer()
    if status == "missing_model":
        return _result(defn, "model file missing", False, notes="No model file submitted")
    if status == "max_unsupported":
        return _result(defn, "unsupported format (.max)", False,
                        notes="MANUAL MARKING REQUIRED — .max cannot be opened by Maya")
    if status == "not_run":
        return _result(defn, "NOT RUN", False,
                        notes="Maya was not available for this run — score is provisional zero, re-run with Maya to get a real result")
    return _result(defn, "MAYA ERROR", False, notes=f"Maya check failed: {m.maya_error or 'unknown error'}")


def _score_d1(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["D1"]

    def ok():
        problems = []
        if m.image_planes:
            problems.append(f"{m.image_planes} image plane(s)")
        if m.extra_cameras:
            problems.append(f"{len(m.extra_cameras)} extra camera(s): {', '.join(m.extra_cameras)}")
        if m.references:
            problems.append(f"{len(m.references)} reference(s): {', '.join(m.references)}")
        if m.hidden_objects:
            problems.append(f"{len(m.hidden_objects)} hidden object(s): {', '.join(m.hidden_objects)}")
        passed = not problems
        measured = "clean scene" if passed else "; ".join(problems)
        return _result(d, measured, passed)

    return _score_maya_dependent(d, m, ok)


def _score_d2(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["D2"]

    def ok():
        tris = m.triangles or 0
        budget = m.triangle_budget or 1
        pct = (tris / budget) * 100 if budget else 0
        passed = 90.0 <= pct <= 100.0
        measured = f"{tris:,} tris ({pct:.1f}% of {budget:,} budget)"
        return _result(d, measured, passed)

    return _score_maya_dependent(d, m, ok)


def _score_d3(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["D3"]

    def ok():
        n = m.ngon_count or 0
        return _result(d, f"{n} n-gon(s)", n == 0)

    return _score_maya_dependent(d, m, ok)


def _score_d4(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["D4"]

    def ok():
        if m.inverted_check_failed or m.inverted_normals is None:
            return _result(d, "CHECK FAILED", False,
                            notes="Inverted-normals check threw an exception — treated as a fail, not a pass. Verify manually.")
        n = m.inverted_normals
        return _result(d, f"{n} inverted face(s)", n == 0)

    return _score_maya_dependent(d, m, ok)


def _score_d5(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["D5"]

    def ok():
        shells = m.shell_candidates or []
        # D5 is always provisional/amber - never a confirmed pass or fail.
        if shells:
            measured = f"{len(shells)} candidate shell(s): {', '.join(shells)}"
            passed = False
        else:
            measured = "no enclosed-shell candidates found"
            passed = True
        return _result(d, measured, passed,
                        notes=f"{PROVISIONAL_NOTE} — automated bounding-box heuristic cannot tell legitimate interior detail from stray geometry. Chief Expert to confirm.",
                        provisional=True)

    result = _score_maya_dependent(d, m, ok)
    result.provisional = True
    if result.notes and PROVISIONAL_NOTE not in result.notes:
        result.notes = f"{PROVISIONAL_NOTE} — {result.notes}"
    elif not result.notes:
        result.notes = PROVISIONAL_NOTE
    return result


def _score_d6(m: RawMeasurements) -> AspectResult:
    d = _DEFS_BY_ID["D6"]

    def ok():
        if m.construction_history is None:
            return _result(d, "CHECK FAILED", False,
                            notes="History check threw an exception — treated as a fail. Verify manually.")
        measured = m.history_details or ("history present" if m.construction_history else "no construction history")
        return _result(d, measured, not m.construction_history)

    return _score_maya_dependent(d, m, ok)


def score_competitor(m: RawMeasurements) -> list[AspectResult]:
    """Returns all 24 aspects in official order for one competitor."""
    automated_scorers = {
        "A1": _score_a1, "A2": _score_a2, "A3": _score_a3,
        "C2": _score_c2, "C3": _score_c3,
        "D1": _score_d1, "D2": _score_d2, "D3": _score_d3,
        "D4": _score_d4, "D5": _score_d5, "D6": _score_d6,
    }
    results = []
    for defn in ASPECT_DEFS:
        if defn.kind == AUTOMATED:
            results.append(automated_scorers[defn.id](m))
        else:
            results.append(_manual_blank(defn))
    return results


def automated_total(results: list[AspectResult]) -> int:
    return sum(r.marks_awarded or 0 for r in results if r.kind == AUTOMATED)
