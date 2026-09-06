import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_checks import (
    discover_competitors,
    filename_matches,
    submitted_on_time,
)


def _touch(path: Path, content: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_discovers_competitors_with_deliverables_folder(tmp_path):
    root = tmp_path / "submissions"
    _touch(root / "07" / "Deliverables" / "ESC2026_TP50_07_Digital-Art.psd")
    _touch(root / "07" / "Deliverables" / "ESC2026_TP50_07_Diving_Helmet.mb")
    _touch(root / "08" / "Deliverables" / "ESC2026_TP50_08_Digital-Art.psd")
    _touch(root / "08" / "Deliverables" / "ESC2026_TP50_08_Diving_Helmet.mb")

    competitors = discover_competitors(root)
    assert [c.competitor_number for c in competitors] == ["07", "08"]
    c07 = competitors[0]
    assert c07.deliverables_dir_found is True
    assert c07.concept_path.name == "ESC2026_TP50_07_Digital-Art.psd"
    assert c07.model_path.name == "ESC2026_TP50_07_Diving_Helmet.mb"


def test_missing_deliverables_folder_falls_back_to_root(tmp_path):
    root = tmp_path / "submissions"
    _touch(root / "09" / "ESC2026_TP50_09_Digital-Art.psd")
    _touch(root / "09" / "ESC2026_TP50_09_Diving_Helmet.mb")

    competitors = discover_competitors(root)
    c09 = competitors[0]
    assert c09.deliverables_dir_found is False
    assert c09.concept_path is not None
    assert c09.model_path is not None


def test_missing_model_file(tmp_path):
    root = tmp_path / "submissions"
    _touch(root / "10" / "Deliverables" / "ESC2026_TP50_10_Digital-Art.psd")

    competitors = discover_competitors(root)
    c10 = competitors[0]
    assert c10.concept_path is not None
    assert c10.model_path is None


def test_max_file_detected(tmp_path):
    root = tmp_path / "submissions"
    _touch(root / "11" / "Deliverables" / "ESC2026_TP50_11_Digital-Art.psd")
    _touch(root / "11" / "Deliverables" / "ESC2026_TP50_11_Diving_Helmet.max")

    competitors = discover_competitors(root)
    c11 = competitors[0]
    assert c11.is_max_file is True


def test_filename_matches_case_sensitive():
    pattern = "ESC2026_TP50_{n}_Digital-Art.psd"
    good = Path("ESC2026_TP50_07_Digital-Art.psd")
    bad_case = Path("esc2026_tp50_07_digital-art.psd")
    wrong_number = Path("ESC2026_TP50_08_Digital-Art.psd")

    assert filename_matches(good, pattern, "07") is True
    assert filename_matches(bad_case, pattern, "07") is False
    assert filename_matches(wrong_number, pattern, "07") is False
    assert filename_matches(None, pattern, "07") is False


def test_submitted_on_time(tmp_path):
    on_time_file = tmp_path / "on_time.psd"
    _touch(on_time_file)
    deadline_future = datetime.now() + timedelta(days=1)
    deadline_past = datetime.now() - timedelta(days=1)

    assert submitted_on_time(on_time_file, deadline_future) is True
    assert submitted_on_time(on_time_file, deadline_past) is False
    assert submitted_on_time(None, deadline_future) is False


def test_only_immediate_subfolders_count_as_competitors(tmp_path):
    root = tmp_path / "submissions"
    _touch(root / "07" / "Deliverables" / "file.psd")
    (root / "loose_file.txt").parent.mkdir(parents=True, exist_ok=True)
    (root / "loose_file.txt").write_text("not a competitor")

    competitors = discover_competitors(root)
    assert len(competitors) == 1
    assert competitors[0].competitor_number == "07"
