import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maya_worker import (
    _count_ngons,
    _find_construction_history,
    _find_enclosed_shells,
    _find_extra_cameras,
    _find_hidden_objects,
    _run_with_timeout,
    audit_model_file,
    process_jobs,
)
from tests.fake_maya_cmds import FakeCmds


def test_count_ngons():
    cmds = FakeCmds()
    cmds.add_mesh("clean", ngon_faces=0)
    cmds.add_mesh("dirty", ngon_faces=14)
    assert _count_ngons(cmds, ["clean"]) == 0
    assert _count_ngons(cmds, ["dirty"]) == 14
    assert _count_ngons(cmds, []) == 0


def test_find_construction_history():
    cmds = FakeCmds()
    cmds.add_mesh("clean", history=[])
    cmds.add_mesh("dirty", history=["polySmoothFace1"])
    flagged = _find_construction_history(cmds, ["clean", "dirty"])
    assert len(flagged) == 1
    assert "dirty" in flagged[0]
    assert "polySmoothFace1" in flagged[0]


def test_find_extra_cameras():
    cmds = FakeCmds()
    cmds.add_camera("persp")
    cmds.add_camera("top")
    cmds.add_camera("front")
    cmds.add_camera("side")
    cmds.add_camera("renderCam")
    extra = _find_extra_cameras(cmds)
    assert extra == ["renderCam"]


def test_find_hidden_objects():
    cmds = FakeCmds()
    cmds.add_mesh("visibleThing", visibility=True)
    cmds.add_mesh("hiddenThing", visibility=False)
    hidden = _find_hidden_objects(cmds, ["visibleThing", "hiddenThing"])
    assert hidden == ["hiddenThing"]


def test_find_enclosed_shells():
    cmds = FakeCmds()
    cmds.add_mesh("outer", bbox=(0, 0, 0, 10, 10, 10))
    cmds.add_mesh("innerBolt", bbox=(4, 4, 4, 6, 6, 6))
    cmds.add_mesh("separateProp", bbox=(20, 20, 20, 21, 21, 21))
    candidates = _find_enclosed_shells(cmds, ["outer", "innerBolt", "separateProp"])
    assert candidates == ["innerBolt"]


def test_audit_model_file_clean_scene():
    cmds = FakeCmds()
    cmds.add_mesh("Helmet", ngon_faces=0, face_count=9500, history=[])
    result = audit_model_file(cmds, "helmet.mb", triangle_budget=10000)
    assert result["triangles"] == 9500
    assert result["ngon_count"] == 0
    assert result["construction_history"] is False
    assert result["image_planes"] == 0
    assert result["extra_cameras"] == []
    assert result["hidden_objects"] == []
    assert result["shell_candidates"] == []


def test_audit_model_file_dirty_scene():
    cmds = FakeCmds()
    cmds.add_mesh("Helmet", ngon_faces=14, face_count=9500, history=["polySmoothFace1"])
    cmds.add_image_plane("imagePlane1")
    result = audit_model_file(cmds, "helmet.mb", triangle_budget=10000)
    assert result["ngon_count"] == 14
    assert result["construction_history"] is True
    assert result["image_planes"] == 1


def test_run_with_timeout_returns_value_on_success():
    value, error = _run_with_timeout(lambda: 42, timeout=1)
    assert value == 42
    assert error is None


def test_run_with_timeout_captures_exception():
    def boom():
        raise RuntimeError("scene is corrupt")

    value, error = _run_with_timeout(boom, timeout=1)
    assert value is None
    assert "scene is corrupt" in error


def test_run_with_timeout_reports_timeout():
    def hang():
        time.sleep(2)
        return "too late"

    value, error = _run_with_timeout(hang, timeout=0.2)
    assert value is None
    assert "Timed out" in error


def test_process_jobs_retries_once_then_skips():
    calls = {"count": 0}

    def flaky_audit(cmds, filepath, triangle_budget):
        calls["count"] += 1
        raise RuntimeError("always fails")

    import maya_worker
    original = maya_worker.audit_model_file
    maya_worker.audit_model_file = flaky_audit
    try:
        jobs = [{"competitor": "09", "model_path": "bad.mb", "triangle_budget": 10000}]
        recorded = {}
        results = process_jobs(jobs, cmds=FakeCmds(), timeout=1,
                                on_result=lambda c, r: recorded.__setitem__(c, r))
    finally:
        maya_worker.audit_model_file = original

    assert calls["count"] == 2  # one try + one retry
    assert results["09"]["status"] == "error"
    assert "always fails" in results["09"]["error"]
    assert recorded["09"] == results["09"]


def test_process_jobs_succeeds_after_one_retry():
    calls = {"count": 0}

    def flaky_audit(cmds, filepath, triangle_budget):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient")
        return {"triangles": 100, "ngon_count": 0}

    import maya_worker
    original = maya_worker.audit_model_file
    maya_worker.audit_model_file = flaky_audit
    try:
        jobs = [{"competitor": "10", "model_path": "flaky.mb", "triangle_budget": 10000}]
        results = process_jobs(jobs, cmds=FakeCmds(), timeout=1, on_result=lambda c, r: None)
    finally:
        maya_worker.audit_model_file = original

    assert results["10"]["status"] == "ok"
    assert results["10"]["triangles"] == 100


def test_process_jobs_continues_after_one_file_fails():
    import maya_worker
    original = maya_worker.audit_model_file

    def selective_audit(cmds, filepath, triangle_budget):
        if "bad" in filepath:
            raise RuntimeError("corrupt")
        return {"triangles": 500, "ngon_count": 0}

    maya_worker.audit_model_file = selective_audit
    try:
        jobs = [
            {"competitor": "01", "model_path": "bad.mb", "triangle_budget": 10000},
            {"competitor": "02", "model_path": "good.mb", "triangle_budget": 10000},
        ]
        results = process_jobs(jobs, cmds=FakeCmds(), timeout=1, on_result=lambda c, r: None)
    finally:
        maya_worker.audit_model_file = original

    assert results["01"]["status"] == "error"
    assert results["02"]["status"] == "ok"
    assert results["02"]["triangles"] == 500
