"""Stand-in for `mayapy.exe maya_worker.py` used by the end-to-end runner
test. Real Maya is unavailable in this environment, so results are canned
per competitor number to match the planted scenarios in
tests/make_mock_submissions.py: competitor 09 has n-gons, construction
history and an image plane; everyone else with a Maya job is clean.
"""
import argparse
import json
from pathlib import Path

CANNED_RESULTS = {
    "07": {
        "status": "ok", "triangles": 9500, "ngon_count": 0,
        "inverted_normals": 0, "inverted_normals_check_failed": False,
        "construction_history": False, "history_details": None,
        "image_planes": 0, "extra_cameras": [], "references": [],
        "hidden_objects": [], "shell_candidates": [],
    },
    "08": {
        "status": "ok", "triangles": 9500, "ngon_count": 0,
        "inverted_normals": 0, "inverted_normals_check_failed": False,
        "construction_history": False, "history_details": None,
        "image_planes": 0, "extra_cameras": [], "references": [],
        "hidden_objects": [], "shell_candidates": [],
    },
    "09": {
        "status": "ok", "triangles": 9500, "ngon_count": 14,
        "inverted_normals": 0, "inverted_normals_check_failed": False,
        "construction_history": True, "history_details": "Helmet: polySmoothFace1",
        "image_planes": 1, "extra_cameras": [], "references": [],
        "hidden_objects": [], "shell_candidates": [],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    jobs = json.loads(Path(args.input).read_text(encoding="utf-8"))["jobs"]
    output_path = Path(args.output)
    results = {}
    for job in jobs:
        competitor = job["competitor"]
        results[competitor] = CANNED_RESULTS.get(competitor, {
            "status": "ok", "triangles": 9500, "ngon_count": 0,
            "inverted_normals": 0, "inverted_normals_check_failed": False,
            "construction_history": False, "history_details": None,
            "image_planes": 0, "extra_cameras": [], "references": [],
            "hidden_objects": [], "shell_candidates": [],
        })
        output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
