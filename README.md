# SC2026 — Skill 50 Marking Tool

Automates the 11 objective marking aspects (42 of 100 marks) for the
WorldSkills-format Skill 50 (3D Digital Game Art) competition. Built for the
Chief Expert to run once or twice a year - see `BUILD_BRIEF.md` for the full
specification this tool implements.

## What it does

- Walks a submissions folder (one subfolder per competitor)
- Checks submission timing, folder structure and filenames
- Parses concept-art PSDs for canvas size and PPI (pure Python, no Photoshop needed)
- Opens each 3D model once in a single Maya session to check triangle count,
  n-gons, inverted normals, construction history and scene cleanliness
- Scores all of the above (binary: full marks or zero, per WorldSkills convention)
- Exports a two-sheet Excel workbook: an automated summary, and the full
  24-aspect marking sheet with the 13 human-marked aspects left blank

## Running from source

```
pip install -r requirements.txt
python main.py
```

## Building the executable

On Windows, with Maya installed (only needed to test the Maya-dependent
checks, not to build):

```
build.bat
```

This produces `dist\SC2026_Marking_Tool.exe` - a single file, no console
window. `maya_worker.py` is bundled into the exe and extracted to a temp
folder at runtime, because mayapy needs a real `.py` file on disk to run.

**Antivirus note:** PyInstaller executables are sometimes flagged as
suspicious by antivirus software (a known false-positive pattern, not
specific to this tool). If Windows Defender or another AV quarantines the
exe, allowlist it once - the source is right here if you want to check it
yourself.

## Architecture

`main.py` (this app) never runs inside mayapy - Maya's bundled Python can't
host a PySide6 GUI reliably. Instead:

```
SC2026_Marking_Tool.exe   (normal Python, does file + PSD checks itself)
    └── subprocess → mayapy.exe maya_worker.py --input jobs.json --output results.json
```

`maya_worker.py` runs the whole batch of model files in one Maya session
(startup is ~25s; per-file checks are ~2s). If Maya crashes or hangs on a
specific file, the orchestrator (`maya_launcher.py`) restarts mayapy only for
the files that never produced a result - the batch is never lost over one
bad file.

| Module | Responsibility |
|---|---|
| `psd_utils.py` | Pure-Python PSD header reader (no external dependency) |
| `file_checks.py` | Folder walking, filename/deadline checks |
| `config.py` | Persists Test Project fields between sessions |
| `maya_worker.py` | Runs under mayapy; the actual Maya audit |
| `maya_launcher.py` | Finds Maya, drives maya_worker.py as a subprocess |
| `scoring.py` | The marking rules (binary pass/fail per aspect) |
| `excel_export.py` | Two-sheet Excel output |
| `runner.py` | Ties the above together for one full marking run |
| `main.py` | The GUI |

## Known limitations

- **D5 (no stray geometry) is always provisional.** The bounding-box shell
  heuristic can't tell a legitimate interior detail (a bolt, an inner rim)
  from geometry a competitor forgot to delete. It's always shown amber and
  labelled "REVIEW" - never presented as a confirmed score.
- **Inverted-normals detection is inherently fragile** (see build brief
  section 6) - it duplicates each mesh, conforms normals on the copy, and
  compares face normals by dot product. `polyInfo` output formatting can
  vary across Maya versions. If the check throws, it's reported as "CHECK
  FAILED" and scored as a fail - never a silent pass.
- **`.max` files cannot be opened by Maya.** Competitors who submit a 3ds Max
  file get D1-D6 marked "MANUAL MARKING REQUIRED" rather than a crash.
- **Per-file Maya timeouts are best-effort.** Maya's C++ layer can't be
  safely pre-empted from Python, so a true infinite hang in Maya itself can
  only be caught by the whole-process timeout in `maya_launcher.py` (which
  restarts mayapy and skips the offending file), not a graceful per-call
  cutoff.
- The Maya-side audit code (`maya_worker.py`) is written from the documented
  Maya Python API and has been validated with fake-Maya unit tests (see
  `tests/fake_maya_cmds.py`), but has not been run against a real Maya
  install in this environment. Test it against your Maya version before
  relying on it for a live competition.

## Testing

```
pip install pytest
pytest tests/
```

The test suite covers the PSD reader, file/timestamp checks, the scoring
rules (including the four planted scenarios from the build brief: a clean
pass, wrong PPI/canvas, n-gons + history + image plane, and a missing model
file), Excel export, the Maya worker's algorithms (against a fake `cmds`),
the crash/restart orchestration in `maya_launcher.py`, and the GUI wiring
(offscreen Qt platform).

To regenerate the mock submissions folder used by the end-to-end test:

```
python tests/make_mock_submissions.py path\to\mock_submissions
```
