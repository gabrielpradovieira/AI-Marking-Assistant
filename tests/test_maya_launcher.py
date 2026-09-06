import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maya_launcher import get_maya_version_label, run_maya_batch

FAKE_WORKER = Path(__file__).resolve().parent / "fake_mayapy_script.py"
PYTHON = Path(sys.executable)


def test_version_label_parses_version_number():
    assert get_maya_version_label(Path("C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe")) == "Maya 2026"
    assert get_maya_version_label(Path("/weird/path/mayapy.exe")) == "Maya (version unknown)"


def test_all_jobs_succeed_normally():
    jobs = [
        {"competitor": "07", "model_path": "good_07.mb", "triangle_budget": 10000},
        {"competitor": "08", "model_path": "good_08.mb", "triangle_budget": 10000},
    ]
    events = []
    results = run_maya_batch(PYTHON, jobs, timeout_per_file=5, on_progress=lambda e, c: events.append((e, c)),
                              worker_path=FAKE_WORKER)
    assert results["07"]["status"] == "ok"
    assert results["08"]["status"] == "ok"
    assert ("maya_starting", None) in events
    assert ("competitor_done", "07") in events
    assert ("competitor_done", "08") in events


def test_process_crash_skips_only_the_offending_file_and_continues():
    jobs = [
        {"competitor": "07", "model_path": "good_07.mb", "triangle_budget": 10000},
        {"competitor": "08", "model_path": "crash_08.mb", "triangle_budget": 10000},
        {"competitor": "09", "model_path": "good_09.mb", "triangle_budget": 10000},
    ]
    results = run_maya_batch(PYTHON, jobs, timeout_per_file=5, worker_path=FAKE_WORKER)

    assert results["07"]["status"] == "ok"
    assert results["08"]["status"] == "error"
    assert "crash" in results["08"]["error"].lower()
    assert results["09"]["status"] == "ok"  # batch continued after restart


def test_restart_limit_is_respected(monkeypatch):
    # Every remaining job crashes -> restarts should stop at max_restarts
    # rather than looping forever.
    jobs = [
        {"competitor": "01", "model_path": "crash_01.mb", "triangle_budget": 10000},
        {"competitor": "02", "model_path": "crash_02.mb", "triangle_budget": 10000},
        {"competitor": "03", "model_path": "crash_03.mb", "triangle_budget": 10000},
    ]
    results = run_maya_batch(PYTHON, jobs, timeout_per_file=5, worker_path=FAKE_WORKER, max_restarts=1)
    assert results["01"]["status"] == "error"
    # With max_restarts=1: first crash consumes job 01 (restart #1), second
    # crash on job 02 exceeds the limit, so 02 and 03 are both marked failed
    # without further restarts.
    assert results["02"]["status"] == "error"
    assert results["03"]["status"] == "error"
    assert "restart limit" in results["03"]["error"].lower()


def test_subprocess_hang_is_treated_as_crash():
    jobs = [
        {"competitor": "07", "model_path": "hang_07.mb", "triangle_budget": 10000},
        {"competitor": "08", "model_path": "good_08.mb", "triangle_budget": 10000},
    ]
    # total_timeout inside run_maya_batch = 60 (startup buffer) + timeout_per_file*n + 30
    # We can't wait 90+ seconds in a unit test, so we monkeypatch the buffer.
    import maya_launcher
    original_buffer = maya_launcher.MAYA_STARTUP_BUFFER_SECONDS
    maya_launcher.MAYA_STARTUP_BUFFER_SECONDS = 0
    try:
        results = run_maya_batch(PYTHON, jobs, timeout_per_file=1, worker_path=FAKE_WORKER)
    finally:
        maya_launcher.MAYA_STARTUP_BUFFER_SECONDS = original_buffer

    assert results["07"]["status"] == "error"
    assert results["08"]["status"] == "ok"
