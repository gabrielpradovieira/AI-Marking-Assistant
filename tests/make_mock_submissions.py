"""Builds a mock submissions folder with the 4 planted scenarios from build
brief section 9, for end-to-end testing of runner.py without real Maya or
real competitor files:

  07 - a fully clean pass
  08 - wrong PPI and wrong canvas size
  09 - n-gons, construction history left on, and an image plane
  10 - missing model file entirely
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.make_test_psd import write_test_psd

CONCEPT_PATTERN = "ESC2026_TP50_{n}_Digital-Art.psd"
MODEL_PATTERN = "ESC2026_TP50_{n}_Diving_Helmet.mb"


def build_mock_submissions(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    # 07 - clean pass
    d = root / "07" / "Deliverables"
    d.mkdir(parents=True, exist_ok=True)
    write_test_psd(d / CONCEPT_PATTERN.format(n="07"), width=3840, height=2160, ppi=300.0)
    (d / MODEL_PATTERN.format(n="07")).write_bytes(b"fake maya binary - clean scene")

    # 08 - wrong PPI and wrong canvas size
    d = root / "08" / "Deliverables"
    d.mkdir(parents=True, exist_ok=True)
    write_test_psd(d / CONCEPT_PATTERN.format(n="08"), width=1920, height=1080, ppi=72.0)
    (d / MODEL_PATTERN.format(n="08")).write_bytes(b"fake maya binary - clean scene")

    # 09 - n-gons, construction history, image plane
    d = root / "09" / "Deliverables"
    d.mkdir(parents=True, exist_ok=True)
    write_test_psd(d / CONCEPT_PATTERN.format(n="09"), width=3840, height=2160, ppi=300.0)
    (d / MODEL_PATTERN.format(n="09")).write_bytes(b"fake maya binary - dirty scene")

    # 10 - missing model file entirely
    d = root / "10" / "Deliverables"
    d.mkdir(parents=True, exist_ok=True)
    write_test_psd(d / CONCEPT_PATTERN.format(n="10"), width=3840, height=2160, ppi=300.0)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("mock_submissions")
    build_mock_submissions(target)
    print(f"Mock submissions folder built at {target.resolve()}")
