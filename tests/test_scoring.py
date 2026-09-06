import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring import (
    AUTOMATED_MAX_TOTAL,
    GRAND_MAX_TOTAL,
    RawMeasurements,
    automated_total,
    score_competitor,
)


def _base_measurements(**overrides) -> RawMeasurements:
    now = datetime(2026, 4, 15, 10, 0)
    defaults = dict(
        competitor_number="07",
        concept_path_name="ESC2026_TP50_07_Digital-Art.psd",
        model_path_name="ESC2026_TP50_07_Diving_Helmet.mb",
        concept_exists=True,
        model_exists=True,
        concept_mtime=now,
        model_mtime=now,
        concept_deadline=now + timedelta(hours=2),
        model_deadline=now + timedelta(hours=6),
        deliverables_dir_found=True,
        concept_filename_ok=True,
        model_filename_ok=True,
        psd_error=None,
        psd_width=3840,
        psd_height=2160,
        psd_ppi=300.0,
        canvas_width=3840,
        canvas_height=2160,
        required_ppi=300,
        triangle_budget=10000,
        maya_status="ok",
        maya_error=None,
        triangles=9500,
        ngon_count=0,
        inverted_normals=0,
        inverted_check_failed=False,
        construction_history=False,
        history_details=None,
        image_planes=0,
        extra_cameras=[],
        references=[],
        hidden_objects=[],
        shell_candidates=[],
    )
    defaults.update(overrides)
    return RawMeasurements(**defaults)


def _by_id(results, aid):
    return next(r for r in results if r.id == aid)


def test_totals_are_internally_consistent():
    assert AUTOMATED_MAX_TOTAL == 42
    assert GRAND_MAX_TOTAL == 100


def test_scenario_1_clean_pass_gets_full_automated_marks():
    m = _base_measurements()
    results = score_competitor(m)
    assert automated_total(results) == AUTOMATED_MAX_TOTAL
    for r in results:
        if r.kind == "automated":
            assert r.passed is True, f"{r.id} unexpectedly failed: {r.measured_value}"
    # D5 must always be provisional even on a clean pass
    d5 = _by_id(results, "D5")
    assert d5.provisional is True


def test_scenario_2_wrong_ppi_and_canvas_size():
    m = _base_measurements(psd_width=1920, psd_height=1080, psd_ppi=72.0)
    results = score_competitor(m)
    c2 = _by_id(results, "C2")
    c3 = _by_id(results, "C3")
    assert c2.passed is False
    assert c2.marks_awarded == 0
    assert "1920x1080" in c2.measured_value
    assert c3.passed is False
    assert c3.marks_awarded == 0
    assert "72" in c3.measured_value
    # Other aspects unaffected
    assert _by_id(results, "A1").passed is True


def test_scenario_3_ngons_history_and_image_plane():
    m = _base_measurements(
        ngon_count=14,
        construction_history=True,
        history_details="polySmoothFace1 on pCube1",
        image_planes=1,
    )
    results = score_competitor(m)
    d3 = _by_id(results, "D3")
    d6 = _by_id(results, "D6")
    d1 = _by_id(results, "D1")
    assert d3.passed is False and d3.marks_awarded == 0
    assert "14" in d3.measured_value
    assert d6.passed is False and d6.marks_awarded == 0
    assert d1.passed is False and d1.marks_awarded == 0
    assert "image plane" in d1.measured_value


def test_scenario_4_missing_model_file():
    m = _base_measurements(
        model_exists=False,
        model_path_name=None,
        model_filename_ok=False,
        maya_status="missing_model",
        triangles=None,
        ngon_count=None,
        inverted_normals=None,
        construction_history=None,
        image_planes=None,
    )
    results = score_competitor(m)
    a1 = _by_id(results, "A1")
    a3 = _by_id(results, "A3")
    assert a1.passed is False
    assert "model missing" in a1.measured_value
    assert a3.passed is False
    for aid in ("D1", "D2", "D3", "D4", "D5", "D6"):
        r = _by_id(results, aid)
        assert r.passed is False
        assert r.marks_awarded == 0


def test_max_file_marks_manual_marking_required():
    m = _base_measurements(maya_status="max_unsupported")
    results = score_competitor(m)
    for aid in ("D1", "D2", "D3", "D4", "D5", "D6"):
        r = _by_id(results, aid)
        assert r.passed is False
        assert "MANUAL MARKING REQUIRED" in r.notes


def test_maya_not_run_does_not_silently_pass():
    m = _base_measurements(maya_status="not_run")
    results = score_competitor(m)
    for aid in ("D1", "D2", "D3", "D4", "D5", "D6"):
        r = _by_id(results, aid)
        assert r.passed is False
        assert r.measured_value == "NOT RUN"


def test_inverted_normals_check_failure_is_not_a_silent_pass():
    m = _base_measurements(inverted_normals=None, inverted_check_failed=True)
    results = score_competitor(m)
    d4 = _by_id(results, "D4")
    assert d4.passed is False
    assert d4.marks_awarded == 0
    assert d4.measured_value == "CHECK FAILED"


def test_triangle_budget_under_90_percent_fails():
    m = _base_measurements(triangles=8000, triangle_budget=10000)  # 80%
    results = score_competitor(m)
    d2 = _by_id(results, "D2")
    assert d2.passed is False


def test_triangle_budget_exactly_90_percent_passes():
    m = _base_measurements(triangles=9000, triangle_budget=10000)
    results = score_competitor(m)
    d2 = _by_id(results, "D2")
    assert d2.passed is True


def test_triangle_budget_over_100_percent_fails():
    m = _base_measurements(triangles=10001, triangle_budget=10000)
    results = score_competitor(m)
    d2 = _by_id(results, "D2")
    assert d2.passed is False


def test_ppi_tolerance_half_a_unit():
    m = _base_measurements(psd_ppi=300.5, required_ppi=300)
    results = score_competitor(m)
    assert _by_id(results, "C3").passed is True

    m2 = _base_measurements(psd_ppi=300.51, required_ppi=300)
    results2 = score_competitor(m2)
    assert _by_id(results2, "C3").passed is False


def test_d5_always_provisional_even_when_clean():
    m = _base_measurements(shell_candidates=[])
    results = score_competitor(m)
    d5 = _by_id(results, "D5")
    assert d5.provisional is True
    assert "REVIEW" in d5.notes


def test_manual_aspects_are_blank():
    m = _base_measurements()
    results = score_competitor(m)
    for aid in ("B1", "B2", "C1", "C4", "C7", "D7", "D10"):
        r = _by_id(results, aid)
        assert r.marks_awarded is None
        assert r.passed is None
        assert r.measured_value == ""
        assert "CE" in r.notes


def test_all_24_aspects_present_in_official_order():
    m = _base_measurements()
    results = score_competitor(m)
    ids = [r.id for r in results]
    assert ids == [
        "A1", "A2", "A3", "B1", "B2",
        "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9",
        "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10",
    ]
