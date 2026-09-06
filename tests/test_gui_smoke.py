"""Smoke tests the PySide6 GUI actually wires up correctly: folder/Maya
detection, enabling RUN CHECK, running the pipeline on a background thread,
and populating the results table - using the offscreen Qt platform so it
can run headless in CI / this sandbox.
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

import maya_launcher
from main import MainWindow
from tests.make_mock_submissions import build_mock_submissions

FAKE_MAYAPY = Path(__file__).resolve().parent / "fake_mayapy_for_runner.py"

_app = None


def _get_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication(sys.argv)
    return _app


def _pump(condition, timeout=15.0):
    app = _get_app()
    start = time.time()
    while not condition() and time.time() - start < timeout:
        app.processEvents()
        time.sleep(0.02)
    return condition()


def test_window_starts_on_input_page_with_run_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _get_app()
    win = MainWindow()
    assert win.stack.currentWidget() is win.input_page
    # No folder configured yet -> RUN CHECK must stay disabled
    assert win.run_button.isEnabled() is False


def test_folder_and_maya_detection_enables_run_button(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    submissions = tmp_path / "submissions"
    build_mock_submissions(submissions)
    _get_app()
    win = MainWindow()

    win.folder_edit.setText(str(submissions))
    assert "4 competitor" in win.folder_status.text()

    win.mayapy_path = Path(sys.executable)
    win._show_maya_status(found=True)
    win._update_run_enabled()

    assert win.run_button.isEnabled() is True


def test_full_run_through_the_gui_populates_results_table(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(maya_launcher, "worker_script_path", lambda: FAKE_MAYAPY)

    submissions = tmp_path / "submissions"
    build_mock_submissions(submissions)
    _get_app()
    win = MainWindow()

    win.folder_edit.setText(str(submissions))
    win.mayapy_path = Path(sys.executable)
    win._show_maya_status(found=True)
    win.concept_date.setText("31/12/2099")
    win.model_date.setText("31/12/2099")
    win._update_run_enabled()
    assert win.run_button.isEnabled() is True

    win._start_run()

    assert _pump(lambda: win.stack.currentWidget() is win.results_page, timeout=20.0), \
        "Run did not complete and switch to the results page in time"

    assert win.results_table.rowCount() == 4
    competitor_numbers = {
        win.results_table.item(r, 0).text() for r in range(win.results_table.rowCount())
    }
    assert competitor_numbers == {"07", "08", "09", "10"}

    # Row selection should populate the detail panel
    win.results_table.selectRow(0)
    win._on_row_selected()
    assert win.detail_view.toPlainText() != ""

    win.worker.wait(2000)
