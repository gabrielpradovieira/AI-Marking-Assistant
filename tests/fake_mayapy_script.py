"""Stand-in for `mayapy.exe maya_worker.py` used by test_maya_launcher.py.

Real Maya isn't available in this environment, so this script simulates the
process-level behaviours maya_launcher.py has to handle: a normal run, a
hard crash partway through a batch (exits non-zero without finishing), and
a hang (runs past the caller's subprocess timeout). It mimics maya_worker.py's
contract: reads --input jobs.json, writes --output results.json
incrementally, one entry per job, in the same job order.

A job's model_path controls what happens:
  contains "crash"  -> process exits with code 1 before writing this job's
                        result (simulating Maya itself dying mid-file)
  contains "hang"   -> sleeps well past any reasonable timeout
  anything else     -> writes a canned "ok" result and continues
"""
import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    jobs = json.loads(Path(args.input).read_text(encoding="utf-8"))["jobs"]
    output_path = Path(args.output)

    results = {}
    if output_path.exists():
        try:
            results = json.loads(output_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            results = {}

    for job in jobs:
        model_path = job["model_path"]
        competitor = job["competitor"]
        if "hang" in model_path:
            time.sleep(300)
        if "crash" in model_path:
            return 1  # die without writing this job's result
        results[competitor] = {"status": "ok", "triangles": 100, "ngon_count": 0}
        output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
