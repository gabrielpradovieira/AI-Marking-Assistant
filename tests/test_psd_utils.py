import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from psd_utils import PSDParseError, read_psd
from tests.make_test_psd import write_test_psd


def test_reads_width_height_ppi(tmp_path):
    p = tmp_path / "test.psd"
    write_test_psd(p, width=3840, height=2160, ppi=300.0, layer_count=4)
    info = read_psd(p)
    assert info.width == 3840
    assert info.height == 2160
    assert info.ppi_horizontal == pytest.approx(300.0, abs=0.01)
    assert info.ppi_vertical == pytest.approx(300.0, abs=0.01)
    assert info.layer_count == 4


def test_reads_72_ppi(tmp_path):
    p = tmp_path / "wrong.psd"
    write_test_psd(p, width=3840, height=2160, ppi=72.0)
    info = read_psd(p)
    assert info.ppi_horizontal == pytest.approx(72.0, abs=0.01)


def test_wrong_canvas_size(tmp_path):
    p = tmp_path / "wrongsize.psd"
    write_test_psd(p, width=1920, height=1080, ppi=300.0)
    info = read_psd(p)
    assert (info.width, info.height) == (1920, 1080)


def test_rejects_non_psd(tmp_path):
    p = tmp_path / "not_a_psd.psd"
    p.write_bytes(b"NOT A PSD FILE AT ALL" * 10)
    with pytest.raises(PSDParseError):
        read_psd(p)


def test_rejects_truncated_file(tmp_path):
    p = tmp_path / "truncated.psd"
    p.write_bytes(b"8BPS\x00\x01")
    with pytest.raises(Exception):
        read_psd(p)
