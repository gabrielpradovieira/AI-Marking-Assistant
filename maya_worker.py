#!/usr/bin/env mayapy
"""Runs under mayapy.exe (NOT under normal Python - see main.py for why).

Starts one Maya session, opens every model file in the batch in that same
session, audits each one for the D1-D6 aspects, and writes the results to a
JSON file. Results are flushed to disk after every file, so if Maya crashes
partway through the batch, everything already processed is still recovered
by the orchestrator (see maya_launcher.py), which restarts mayapy only for
the files that never got a result.

Usage:
    mayapy maya_worker.py --input jobs.json --output results.json [--timeout 60]

jobs.json:
    {"jobs": [{"competitor": "07", "model_path": "C:\\...\\....mb",
               "triangle_budget": 10000}, ...]}

results.json (written incrementally):
    {"07": {"status": "ok", "triangles": 9412, "ngon_count": 0, ...},
     "08": {"status": "error", "error": "Timed out after 60s"}}
"""
from __future__ import annotations

import argparse
import json
import threading
import traceback
from pathlib import Path

DEFAULT_TIMEOUT = 60
DEFAULT_CAMERAS = {"persp", "top", "front", "side"}


# ---------------------------------------------------------------------------
# Timeout / retry plumbing (no Maya dependency - testable on its own)
# ---------------------------------------------------------------------------

def _run_with_timeout(func, timeout):
    """Runs func() in a worker thread and enforces a soft timeout.

    Maya's C++ layer cannot be safely pre-empted from Python - there is no
    way to forcibly kill only "the current cmds call" without killing the
    whole process. So this is best-effort: if func() doesn't return within
    timeout, we stop waiting and report a timeout for this job, but the
    thread itself is left running in the background (daemon=True) since it
    cannot be cancelled. Ordinary exceptions (corrupt scene, bad geometry,
    missing plugin) are caught here and returned rather than raised, which
    covers the common failure case even without a true hang.
    """
    box: dict = {}

    def target():
        try:
            box["value"] = func()
        except Exception as exc:
            box["error"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None, f"Timed out after {timeout}s"
    if "error" in box:
        return None, box["error"]
    return box.get("value"), None


def process_jobs(jobs, cmds, timeout, on_result):
    """Runs audit_model_file for every job, retrying once on failure/timeout
    before giving up on that file. Calls on_result(competitor, result_dict)
    after each job completes so the caller can persist progress to disk
    without waiting for the whole batch."""
    results = {}
    for job in jobs:
        competitor = job["competitor"]
        filepath = job["model_path"]
        triangle_budget = job.get("triangle_budget", 0)

        value, error = None, None
        for _attempt in range(2):  # try once, retry once
            value, error = _run_with_timeout(
                lambda fp=filepath, tb=triangle_budget: audit_model_file(cmds, fp, tb),
                timeout,
            )
            if value is not None:
                break

        if value is not None:
            value["status"] = "ok"
            value["error"] = None
            results[competitor] = value
        else:
            results[competitor] = {"status": "error", "error": error}
        on_result(competitor, results[competitor])
    return results


# ---------------------------------------------------------------------------
# The actual Maya audit
# ---------------------------------------------------------------------------

def audit_model_file(cmds, filepath: str, triangle_budget: int) -> dict:
    """Opens filepath fresh and measures everything scoring.py needs for
    D1-D6. Caller must not pass a .max file - Maya cannot open those."""
    cmds.file(new=True, force=True)
    cmds.file(filepath, open=True, force=True, ignoreVersion=True, prompt=False)

    meshes = cmds.ls(type="mesh", noIntermediate=True) or []
    mesh_transforms = sorted({
        cmds.listRelatives(m, parent=True, fullPath=True)[0] for m in meshes
    }) if meshes else []

    result: dict = {}

    tri_total = cmds.polyEvaluate(triangle=True) if meshes else 0
    result["triangles"] = tri_total if isinstance(tri_total, int) else 0

    result["ngon_count"] = _count_ngons(cmds, mesh_transforms)

    inverted, check_failed = _count_inverted_normals(cmds, mesh_transforms)
    result["inverted_normals"] = inverted
    result["inverted_normals_check_failed"] = check_failed

    history_nodes = _find_construction_history(cmds, mesh_transforms)
    result["construction_history"] = bool(history_nodes)
    result["history_details"] = "; ".join(history_nodes) if history_nodes else None

    result["image_planes"] = len(cmds.ls(type="imagePlane") or [])
    result["extra_cameras"] = _find_extra_cameras(cmds)
    result["references"] = cmds.file(query=True, reference=True) or []
    result["hidden_objects"] = _find_hidden_objects(cmds, mesh_transforms)

    result["shell_candidates"] = _find_enclosed_shells(cmds, mesh_transforms)

    return result


def _count_ngons(cmds, mesh_transforms: list[str]) -> int:
    """Faces with more than 4 sides, via the standard polySelectConstraint
    trick (mode=3 "more than", type=0x0008 faces, size=3 sides)."""
    if not mesh_transforms:
        return 0
    cmds.select(mesh_transforms, replace=True)
    cmds.changeSelectMode(component=True)
    cmds.selectType(polymeshFace=True)
    cmds.polySelectConstraint(mode=3, type=0x0008, size=3)
    ngon_faces = cmds.ls(selection=True, flatten=True) or []
    cmds.polySelectConstraint(mode=0)
    cmds.selectType(polymeshFace=False)
    cmds.changeSelectMode(object=True)
    cmds.select(clear=True)
    return len(ngon_faces)


def _parse_face_normal(line: str):
    # polyInfo -faceNormals output: "FACE_NORMAL      0: 0.000000 1.000000 0.000000"
    try:
        after_colon = line.split(":", 1)[1]
        return tuple(float(x) for x in after_colon.split()[:3])
    except (IndexError, ValueError):
        return None


def _count_inverted_normals(cmds, mesh_transforms: list[str]):
    """Known-fragile (see build brief): duplicates each mesh, conforms
    normals on the copy (polyNormal -normalMode 2), and flags faces whose
    original normal points opposite to the conformed one. Wrapped so any
    exception surfaces as "check failed" (None, True) rather than a silent
    zero - scoring.py treats a failed check as a fail, never a free pass."""
    if not mesh_transforms:
        return 0, False
    total_inverted = 0
    try:
        for mesh_transform in mesh_transforms:
            short_name = mesh_transform.split("|")[-1]
            dup = cmds.duplicate(mesh_transform, name=f"{short_name}_normCheck", renameChildren=True)[0]
            try:
                cmds.polyNormal(dup, normalMode=2, userNormalMode=0, ch=False)
                face_count = cmds.polyEvaluate(mesh_transform, face=True) or 0
                for i in range(face_count):
                    orig_info = cmds.polyInfo(f"{mesh_transform}.f[{i}]", faceNormals=True)
                    dup_info = cmds.polyInfo(f"{dup}.f[{i}]", faceNormals=True)
                    if not orig_info or not dup_info:
                        continue
                    ov = _parse_face_normal(orig_info[0])
                    dv = _parse_face_normal(dup_info[0])
                    if ov is None or dv is None:
                        continue
                    dot = ov[0] * dv[0] + ov[1] * dv[1] + ov[2] * dv[2]
                    if dot < 0:
                        total_inverted += 1
            finally:
                cmds.delete(dup)
        return total_inverted, False
    except Exception:
        return None, True


def _find_construction_history(cmds, mesh_transforms: list[str]) -> list[str]:
    flagged = []
    for mesh_transform in mesh_transforms:
        shapes = cmds.listRelatives(mesh_transform, shapes=True, fullPath=True) or []
        for shape in shapes:
            history = cmds.listHistory(shape, pruneDagObjects=True) or []
            construction_nodes = sorted({
                h for h in history if cmds.nodeType(h) != "mesh"
            })
            if construction_nodes:
                short_name = mesh_transform.split("|")[-1]
                flagged.append(f"{short_name}: {', '.join(construction_nodes)}")
    return flagged


def _find_extra_cameras(cmds) -> list[str]:
    all_cameras = cmds.ls(type="camera") or []
    extra = []
    for cam_shape in all_cameras:
        parents = cmds.listRelatives(cam_shape, parent=True) or []
        if not parents:
            continue
        transform = parents[0]
        if transform not in DEFAULT_CAMERAS:
            extra.append(transform)
    return extra


def _find_hidden_objects(cmds, mesh_transforms: list[str]) -> list[str]:
    hidden = []
    for t in mesh_transforms:
        try:
            visible = cmds.getAttr(f"{t}.visibility")
        except Exception:
            visible = True
        if not visible:
            hidden.append(t.split("|")[-1])
    return hidden


def _find_enclosed_shells(cmds, mesh_transforms: list[str]) -> list[str]:
    """Flags shells whose bounding box sits entirely inside another shell's
    bounding box. This is a heuristic, not proof of stray geometry -
    scoring.py always marks D5 as provisional/amber regardless of this
    result (see build brief section 5)."""
    boxes = {}
    for t in mesh_transforms:
        try:
            boxes[t] = cmds.exactWorldBoundingBox(t)
        except Exception:
            continue

    def contained(inner, outer):
        return (
            inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] >= outer[2]
            and inner[3] <= outer[3] and inner[4] <= outer[4] and inner[5] <= outer[5]
        )

    candidates = set()
    names = list(boxes.keys())
    for a in names:
        for b in names:
            if a == b:
                continue
            if contained(boxes[a], boxes[b]):
                candidates.add(a.split("|")[-1])
                break
    return sorted(candidates)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    jobs = json.loads(Path(args.input).read_text(encoding="utf-8")).get("jobs", [])
    output_path = Path(args.output)

    import maya.standalone  # noqa: only importable under mayapy
    maya.standalone.initialize(name="python")
    from maya import cmds as maya_cmds

    results: dict = {}

    def on_result(competitor, result):
        results[competitor] = result
        output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    try:
        process_jobs(jobs, maya_cmds, args.timeout, on_result)
    finally:
        try:
            maya.standalone.uninitialize()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
