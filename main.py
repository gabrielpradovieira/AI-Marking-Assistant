"""SC2026 Skill 50 Marking Tool - PySide6 GUI.

One window: pick a submissions folder, confirm Maya is detected, fill in
the Test Project fields (persisted between sessions), click RUN CHECK, then
review results and export to Excel. See BUILD_BRIEF.md for the full spec.

Deliberately NOT run under mayapy - PySide6 cannot be hosted reliably
inside Maya's bundled Python. This process does the file/PSD checks itself
and launches mayapy.exe as a subprocess for the Maya-side checks (see
maya_launcher.py / maya_worker.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QTimeEdit, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QDate, QTime

import maya_launcher
from config import ToolConfig, load_config, save_config
from excel_export import CompetitorResult
from runner import RunOutcome, run_marking
from scoring import AUTOMATED_MAX_TOTAL, SUMMARY_COLUMNS

GREEN = "#1a7f37"
RED = "#c0392b"
AMBER_BG = QColor("#ffe699")
RED_BG = QColor("#ffc7ce")


def count_competitor_folders(folder: Path) -> int:
    if not folder.exists() or not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.is_dir())


class RunWorker(QThread):
    phase_changed = Signal(str)
    competitor_progress = Signal(int, int, str)
    competitor_progress_maya = Signal(str)
    finished_ok = Signal(object)  # RunOutcome
    failed = Signal(str)

    def __init__(self, cfg: ToolConfig, mayapy_path: Path | None):
        super().__init__()
        self.cfg = cfg
        self.mayapy_path = mayapy_path

    def run(self) -> None:
        def on_progress(event, data):
            if event == "phase":
                self.phase_changed.emit(data)
            elif event == "competitor_progress":
                idx, total, number = data
                self.competitor_progress.emit(idx, total, number)
            elif event == "competitor_progress_maya":
                self.competitor_progress_maya.emit(data)

        try:
            outcome = run_marking(self.cfg, self.mayapy_path, on_progress=on_progress)
            self.finished_ok.emit(outcome)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SC2026 — Skill 50 Marking Tool")
        self.setMinimumSize(560, 620)
        self.resize(560, 660)

        self.cfg = load_config()
        self.mayapy_path: Path | None = None
        self.worker: RunWorker | None = None
        self.last_outcome: RunOutcome | None = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.input_page = self._build_input_page()
        self.results_page = self._build_results_page()
        self.stack.addWidget(self.input_page)
        self.stack.addWidget(self.results_page)
        self.stack.setCurrentWidget(self.input_page)

        self._load_config_into_fields()
        self._detect_maya(prefer_configured=True)
        self._refresh_folder_status()
        self._update_run_enabled()

    # ------------------------------------------------------------------
    # Input page
    # ------------------------------------------------------------------
    def _build_input_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # --- Submissions folder ---
        layout.addWidget(self._section_label("Submissions folder"))
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.textChanged.connect(self._on_folder_text_changed)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)
        self.folder_status = QLabel()
        layout.addWidget(self.folder_status)

        # --- Maya ---
        layout.addWidget(self._section_label("Maya"))
        maya_row = QHBoxLayout()
        self.maya_status = QLabel()
        change_btn = QPushButton("Change…")
        change_btn.clicked.connect(self._browse_mayapy)
        maya_row.addWidget(self.maya_status, stretch=1)
        maya_row.addWidget(change_btn)
        layout.addLayout(maya_row)

        layout.addWidget(self._divider("Test Project"))

        form = QGridLayout()
        form.setColumnStretch(1, 1)
        row = 0

        form.addWidget(QLabel("Concept deadline"), row, 0)
        self.concept_date = QLineEdit()
        self.concept_date.setPlaceholderText("DD/MM/YYYY")
        self.concept_time = QTimeEdit()
        self.concept_time.setDisplayFormat("HH:mm")
        dt_row = QHBoxLayout()
        dt_row.addWidget(self.concept_date)
        dt_row.addWidget(self.concept_time)
        form.addLayout(dt_row, row, 1)
        row += 1

        form.addWidget(QLabel("Model deadline"), row, 0)
        self.model_date = QLineEdit()
        self.model_date.setPlaceholderText("DD/MM/YYYY")
        self.model_time = QTimeEdit()
        self.model_time.setDisplayFormat("HH:mm")
        dt_row2 = QHBoxLayout()
        dt_row2.addWidget(self.model_date)
        dt_row2.addWidget(self.model_time)
        form.addLayout(dt_row2, row, 1)
        row += 1

        form.addWidget(QLabel("Triangle budget"), row, 0)
        self.triangle_budget = QSpinBox()
        self.triangle_budget.setRange(1, 100_000_000)
        self.triangle_budget.setSingleStep(1000)
        form.addWidget(self.triangle_budget, row, 1)
        row += 1

        form.addWidget(QLabel("Canvas size"), row, 0)
        canvas_row = QHBoxLayout()
        self.canvas_width = QSpinBox()
        self.canvas_width.setRange(1, 100_000)
        self.canvas_height = QSpinBox()
        self.canvas_height.setRange(1, 100_000)
        canvas_row.addWidget(self.canvas_width)
        canvas_row.addWidget(QLabel("x"))
        canvas_row.addWidget(self.canvas_height)
        form.addLayout(canvas_row, row, 1)
        row += 1

        form.addWidget(QLabel("Required PPI"), row, 0)
        self.required_ppi = QSpinBox()
        self.required_ppi.setRange(1, 10_000)
        form.addWidget(self.required_ppi, row, 1)
        row += 1

        form.addWidget(QLabel("Concept filename"), row, 0)
        self.concept_pattern = QLineEdit()
        form.addWidget(self.concept_pattern, row, 1)
        row += 1
        form.addWidget(QLabel(""), row, 0)
        form.addWidget(self._hint_label(), row, 1)
        row += 1

        form.addWidget(QLabel("Model filename"), row, 0)
        self.model_pattern = QLineEdit()
        form.addWidget(self.model_pattern, row, 1)
        row += 1
        form.addWidget(QLabel(""), row, 0)
        form.addWidget(self._hint_label(), row, 1)
        row += 1

        layout.addLayout(form)

        layout.addStretch(1)

        run_row = QHBoxLayout()
        run_row.addStretch(1)
        self.run_button = QPushButton("RUN CHECK")
        self.run_button.setMinimumHeight(36)
        self.run_button.setMinimumWidth(160)
        self.run_button.clicked.connect(self._start_run)
        run_row.addWidget(self.run_button)
        run_row.addStretch(1)
        layout.addLayout(run_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)

        for w in (
            self.concept_date, self.concept_time, self.model_date, self.model_time,
            self.triangle_budget, self.canvas_width, self.canvas_height,
            self.required_ppi, self.concept_pattern, self.model_pattern,
        ):
            pass  # persistence is saved on run / close, not on every keystroke

        return page

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        font = lbl.font()
        font.setBold(True)
        lbl.setFont(font)
        return lbl

    def _hint_label(self) -> QLabel:
        lbl = QLabel("{n} = competitor number, taken from the folder name")
        lbl.setStyleSheet("color: grey; font-size: 11px;")
        return lbl

    def _divider(self, text: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 8, 0, 4)
        row.addWidget(self._hline())
        lbl = QLabel(text)
        lbl.setStyleSheet("color: grey;")
        row.addWidget(lbl)
        row.addWidget(self._hline())
        return container

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    # ------------------------------------------------------------------
    # Results page
    # ------------------------------------------------------------------
    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        self.results_table = QTableWidget()
        headers = ["Competitor"] + SUMMARY_COLUMNS + [f"Total (/{AUTOMATED_MAX_TOTAL})"]
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.itemSelectionChanged.connect(self._on_row_selected)
        layout.addWidget(self.results_table, stretch=3)

        layout.addWidget(self._section_label("Details"))
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        layout.addWidget(self.detail_view, stretch=2)

        button_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(self._go_back)
        export_btn = QPushButton("Export Excel")
        export_btn.clicked.connect(self._export_excel)
        button_row.addWidget(back_btn)
        button_row.addStretch(1)
        button_row.addWidget(export_btn)
        layout.addLayout(button_row)

        return page

    # ------------------------------------------------------------------
    # Config <-> fields
    # ------------------------------------------------------------------
    def _load_config_into_fields(self) -> None:
        c = self.cfg
        self.folder_edit.setText(c.submissions_folder)
        self.concept_date.setText(c.concept_deadline_date)
        self._set_time_edit(self.concept_time, c.concept_deadline_time)
        self.model_date.setText(c.model_deadline_date)
        self._set_time_edit(self.model_time, c.model_deadline_time)
        self.triangle_budget.setValue(c.triangle_budget)
        self.canvas_width.setValue(c.canvas_width)
        self.canvas_height.setValue(c.canvas_height)
        self.required_ppi.setValue(c.required_ppi)
        self.concept_pattern.setText(c.concept_filename_pattern)
        self.model_pattern.setText(c.model_filename_pattern)

    def _set_time_edit(self, widget: QTimeEdit, value: str) -> None:
        t = QTime.fromString(value, "HH:mm")
        widget.setTime(t if t.isValid() else QTime(12, 0))

    def _collect_config(self) -> ToolConfig:
        return ToolConfig(
            submissions_folder=self.folder_edit.text().strip(),
            mayapy_path=str(self.mayapy_path) if self.mayapy_path else "",
            concept_deadline_date=self.concept_date.text().strip(),
            concept_deadline_time=self.concept_time.time().toString("HH:mm"),
            model_deadline_date=self.model_date.text().strip(),
            model_deadline_time=self.model_time.time().toString("HH:mm"),
            triangle_budget=self.triangle_budget.value(),
            canvas_width=self.canvas_width.value(),
            canvas_height=self.canvas_height.value(),
            required_ppi=self.required_ppi.value(),
            concept_filename_pattern=self.concept_pattern.text().strip(),
            model_filename_pattern=self.model_pattern.text().strip(),
        )

    def _save_config(self) -> None:
        self.cfg = self._collect_config()
        save_config(self.cfg)

    # ------------------------------------------------------------------
    # Folder / Maya detection
    # ------------------------------------------------------------------
    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select submissions folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _on_folder_text_changed(self, _text: str) -> None:
        self._refresh_folder_status()
        self._update_run_enabled()

    def _refresh_folder_status(self) -> None:
        folder = Path(self.folder_edit.text().strip()) if self.folder_edit.text().strip() else None
        if not folder or not folder.exists():
            self.folder_status.setText("✗ Folder not found" if folder else "")
            self.folder_status.setStyleSheet(f"color: {RED};")
            self._folder_valid = False
            return
        count = count_competitor_folders(folder)
        if count > 0:
            self.folder_status.setText(f"✓ {count} competitor folder(s) found")
            self.folder_status.setStyleSheet(f"color: {GREEN};")
            self._folder_valid = True
        else:
            self.folder_status.setText("✗ No competitor folders found")
            self.folder_status.setStyleSheet(f"color: {RED};")
            self._folder_valid = False

    def _detect_maya(self, prefer_configured: bool = False) -> None:
        if prefer_configured and self.cfg.mayapy_path:
            configured = Path(self.cfg.mayapy_path)
            if configured.exists():
                self.mayapy_path = configured
                self._show_maya_status(found=True)
                return
        detected = maya_launcher.find_mayapy()
        if detected:
            self.mayapy_path = detected
            self._show_maya_status(found=True)
        else:
            self.mayapy_path = None
            self._show_maya_status(found=False)

    def _show_maya_status(self, found: bool) -> None:
        if found and self.mayapy_path:
            label = maya_launcher.get_maya_version_label(self.mayapy_path)
            self.maya_status.setText(f"✓ {label} detected")
            self.maya_status.setStyleSheet(f"color: {GREEN};")
        else:
            self.maya_status.setText("✗ Maya not found")
            self.maya_status.setStyleSheet(f"color: {RED};")

    def _browse_mayapy(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate mayapy.exe", "", "mayapy.exe (mayapy.exe);;All files (*)")
        if path:
            self.mayapy_path = Path(path)
            self._show_maya_status(found=True)
            self._update_run_enabled()

    def _update_run_enabled(self) -> None:
        valid_folder = getattr(self, "_folder_valid", False)
        valid_maya = self.mayapy_path is not None and self.mayapy_path.exists()
        self.run_button.setEnabled(valid_folder and valid_maya)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _start_run(self) -> None:
        if not self.concept_date.text().strip() or not self.model_date.text().strip():
            QMessageBox.warning(self, "Missing deadline", "Please fill in both deadline dates (DD/MM/YYYY).")
            return
        self._save_config()

        try:
            from runner import parse_deadline
            parse_deadline(self.cfg.concept_deadline_date, self.cfg.concept_deadline_time)
            parse_deadline(self.cfg.model_deadline_date, self.cfg.model_deadline_time)
        except ValueError:
            QMessageBox.warning(self, "Invalid deadline", "Deadlines must be in DD/MM/YYYY format.")
            return

        self.run_button.setEnabled(False)
        self.progress_bar.setRange(0, 0)  # indeterminate until we know competitor count
        self.progress_label.setText("Starting…")

        self.worker = RunWorker(self.cfg, self.mayapy_path)
        self.worker.phase_changed.connect(self._on_phase_changed)
        self.worker.competitor_progress.connect(self._on_competitor_progress)
        self.worker.competitor_progress_maya.connect(self._on_competitor_progress_maya)
        self.worker.finished_ok.connect(self._on_run_finished)
        self.worker.failed.connect(self._on_run_failed)
        self.worker.start()

    def _on_phase_changed(self, phase: str) -> None:
        if phase == "maya_starting":
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText("Starting Maya…")
        elif phase == "scoring":
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.progress_label.setText("Scoring…")

    def _on_competitor_progress(self, idx: int, total: int, number: str) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(idx)
        self.progress_label.setText(f"Competitor {number} ({idx}/{total})")

    def _on_competitor_progress_maya(self, number: str) -> None:
        self.progress_label.setText(f"Maya: competitor {number} done")

    def _on_run_finished(self, outcome: RunOutcome) -> None:
        self.last_outcome = outcome
        self.run_button.setEnabled(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.progress_label.setText("Done.")
        self._populate_results(outcome)
        self.stack.setCurrentWidget(self.results_page)
        if not outcome.maya_available:
            QMessageBox.information(
                self, "Maya not available",
                "Maya could not be found, so D1-D6 are shown as NOT RUN for every "
                "competitor. File and image checks still ran normally.")

    def _on_run_failed(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self.progress_label.setText("Failed.")
        QMessageBox.critical(self, "Run failed", message)

    # ------------------------------------------------------------------
    # Results view
    # ------------------------------------------------------------------
    def _populate_results(self, outcome: RunOutcome) -> None:
        table = self.results_table
        table.setRowCount(len(outcome.competitor_results))
        self._row_aspects: list[list] = []

        for row, cr in enumerate(outcome.competitor_results):
            by_id = {r.id: r for r in cr.aspects}
            table.setItem(row, 0, QTableWidgetItem(cr.competitor_number))
            for col, aid in enumerate(SUMMARY_COLUMNS, start=1):
                r = by_id[aid]
                value = r.marks_awarded if r.marks_awarded is not None else ""
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                if r.provisional:
                    item.setBackground(AMBER_BG)
                elif r.passed is False:
                    item.setBackground(RED_BG)
                table.setItem(row, col, item)
            from scoring import automated_total
            total_item = QTableWidgetItem(str(automated_total(cr.aspects)))
            total_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, len(SUMMARY_COLUMNS) + 1, total_item)
            self._row_aspects.append(cr.aspects)

        table.resizeColumnsToContents()
        if table.rowCount() > 0:
            table.selectRow(0)

    def _on_row_selected(self) -> None:
        rows = self.results_table.selectionModel().selectedRows()
        if not rows:
            self.detail_view.clear()
            return
        row = rows[0].row()
        aspects = self._row_aspects[row]
        lines = []
        for r in aspects:
            if r.kind != "automated":
                continue
            status = "REVIEW" if r.provisional else ("PASS" if r.passed else "FAIL")
            lines.append(f"{r.id} {r.name}: {status} — {r.measured_value}")
            if r.notes:
                lines.append(f"    {r.notes}")
        self.detail_view.setPlainText("\n".join(lines))

    def _go_back(self) -> None:
        self.stack.setCurrentWidget(self.input_page)

    def _export_excel(self) -> None:
        if not self.last_outcome or not self.last_outcome.excel_path:
            QMessageBox.warning(self, "Nothing to export", "No results available yet.")
            return
        QMessageBox.information(
            self, "Excel exported",
            f"Results were saved to:\n{self.last_outcome.excel_path}")

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
