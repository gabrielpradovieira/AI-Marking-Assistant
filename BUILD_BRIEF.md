# BUILD BRIEF — SC2026 Skill 50 Marking Tool
Hand this file to Claude Code with: "Read BUILD_BRIEF.md and build this."
---
## 1. WHAT THIS IS
A small Windows desktop application that automates the objective portion of
marking a 3D art competition (WorldSkills-format, Skill 50 — 3D Digital Game
Art). It is used once or twice a year by ONE person — the Chief Expert — who is
a 3D artist, not a developer.

The competition has 24 marking aspects totalling 100 marks. This tool scores 11
of them, worth 42 marks, fully automatically. The rest are done by a human.

**Design priority: simplicity of use over features.** The user should be able to
open it a year from now and understand it in ten seconds without documentation.

---
## 2. TECH STACK (use these unless there is a real reason not to)
- Python 3.11+
- **PySide6** for the GUI (better packaging behaviour than tkinter, looks native)
- **openpyxl** for Excel export
- **PyInstaller** to build a single-file `.exe`
- PSD parsing: pure-Python struct reading, NO external library (working
  implementation supplied in section 6 — reuse it)
- Maya interaction: `subprocess` call to `mayapy.exe`, hidden window

**Critical constraint:** the GUI must NOT run inside mayapy. Maya's bundled
Python cannot host a PySide6 app reliably. Architecture is:

```
marking_tool.exe  (your app, normal Python)
    ├── does file checks itself
    ├── does PSD parsing itself
    └── subprocess → mayapy.exe maya_worker.py --input jobs.json --output maya_results.json
```

`maya_worker.py` is a separate script that ships alongside the exe (or is
extracted to a temp dir at runtime). It imports `maya.standalone`, processes all
model files in one Maya session, writes JSON, exits.

Do NOT launch mayapy once per file — one Maya startup for the whole batch.
Startup is ~25 seconds; per-file processing is ~2 seconds.

---
## 3. THE INTERFACE
One window, roughly 560 x 620, not resizable smaller than that. No menu bar, no
tabs, no wizard, no splash screen.

```
┌──────────────────────────────────────────────┐
│  SC2026 — Skill 50 Marking Tool              │
├──────────────────────────────────────────────┤
│                                              │
│  Submissions folder                          │
│  ┌────────────────────────────┐ ┌─────────┐  │
│  │ C:\SC2026\Submissions      │ │ Browse… │  │
│  └────────────────────────────┘ └─────────┘  │
│  ✓ 15 competitor folders found               │
│                                              │
│  Maya                                        │
│  ✓ Maya 2026 detected            [Change…]   │
│                                              │
│  ─────────────  Test Project  ─────────────  │
│  Concept deadline   [15/04/2026] [12:00]     │
│  Model deadline     [15/04/2026] [16:30]     │
│  Triangle budget    [10000]                  │
│  Canvas size        [3840] x [2160]          │
│  Required PPI       [300]                    │
│  Concept filename   [ESC2026_TP50_{n}_Digital-Art.psd] │
│  Model filename     [ESC2026_TP50_{n}_Diving_Helmet.mb]│
│                                              │
│           ┌──────────────────┐               │
│           │    RUN CHECK     │               │
│           └──────────────────┘               │
│                                              │
│  ████████████░░░░░░░  Competitor 09 (9/15)   │
│                                              │
└──────────────────────────────────────────────┘
```

Behaviour:
- **Browse** opens a folder picker. On selection, immediately count subfolders
  and show "✓ N competitor folders found" in green, or a red warning if zero.
- **Maya detection** on startup: scan `C:\Program Files\Autodesk\Maya*\bin\mayapy.exe`,
  pick the highest version number. Show the version found. If none, show
  "✗ Maya not found" in red and let the user browse to mayapy.exe manually.
- **RUN CHECK** disabled until a valid folder AND a valid mayapy path exist.
- All Test Project fields **persist between sessions** — save to a JSON config
  in `%APPDATA%\SC2026MarkingTool\config.json`. This matters: the user should
  not retype them.
- `{n}` in the filename fields is substituted with the competitor number
  (the subfolder name). Make this visible with a small grey hint under the
  fields: "{n} = competitor number, taken from the folder name".
- Progress bar updates per competitor. The Maya phase takes ~25s to start —
  show "Starting Maya…" during that so it doesn't look frozen.
- Run the work on a **background thread**. The window must not freeze.

### Results view
When the run finishes, switch to a results view in the same window (or grow the
window — do not open a second one). A table:

| Competitor | A1 | A2 | A3 | C2 | C3 | D1 | D2 | D3 | D4 | D5 | D6 | Total |

- Cells show marks awarded, e.g. `6` or `0`
- **Failed cells (0 marks) coloured red**, passes plain
- **D5 column always amber**, never green — it is provisional (see section 5)
- Click any row → detail panel below showing the raw measured values for that
  competitor (triangle count, n-gon count, PSD dimensions, what failed and why)
- Buttons: **[ Export Excel ]** and **[ ← Back ]**

---
## 4. FOLDER STRUCTURE EXPECTED

```
<submissions folder>/
    07/
        Deliverables/
            ESC2026_TP50_07_Digital-Art.psd
            ESC2026_TP50_07_Diving_Helmet.mb
    08/
        Deliverables/
            ...
```

- Each immediate subfolder = one competitor. Subfolder name = competitor number.
- Look for deliverables inside a `Deliverables` subfolder. If absent, fall back
  to the competitor folder root, and record that the Deliverables folder was
  missing (this costs a mark — see A2).
- First `.psd` found is the concept art. First `.mb`/`.ma`/`.max` is the model.
- `.max` cannot be opened by Maya — record it as "manual marking required" and
  zero the D aspects with a clear note. Do not crash.

---
## 5. THE MARKING LOGIC
**All aspects are BINARY: full marks or zero. No partial marks.** One n-gon
fails exactly as fifty do. This is WorldSkills convention — do not "improve" it.

| ID | Aspect | Marks | Pass condition |
|----|--------|-------|----------------|
| A1 | Submit on time | 3 | BOTH files exist AND each modified-time ≤ its module deadline |
| A2 | Folder names | 1 | A `Deliverables` folder exists |
| A3 | Filenames | 1 | BOTH filenames match their pattern exactly (case-sensitive) |
| C2 | Image size / aspect | 4 | PSD width × height == configured canvas size exactly |
| C3 | PPI | 4 | PSD resolution == configured PPI (±0.5 tolerance) |
| D1 | Scene organisation | 5 | NO image planes AND no extra cameras AND no references AND no hidden objects |
| D2 | Triangle budget | 6 | 90% ≤ total triangles ≤ 100% of budget. **Under 90% also fails.** |
| D3 | No n-gons | 6 | n-gon count == 0 |
| D4 | No inverted normals | 4 | inverted face count == 0 |
| D5 | No stray geometry | 4 | No fully-enclosed shells — **PROVISIONAL, see below** |
| D6 | No modifiers / history | 4 | No object has polygon construction history |

**Total automated: 42 marks.**

### D5 is deliberately unreliable
The script detects mesh shells whose bounding box sits entirely inside another
shell's bounding box. That finds candidates, but cannot distinguish a legitimate
interior detail (a bolt, an inner rim) from geometry a competitor forgot to
delete. **Always display D5 in amber and label it "REVIEW" in the Excel Notes
column.** Never present it as a confirmed score.

### Object naming is NOT a criterion
Do not check node names, do not penalise `pCube1`. It is not in the marking
scheme.

### Aspects this tool must NOT attempt
Leave these entirely alone — they are human-marked. They appear in the Excel as
blank rows only:
- B1 Polite behaviour (2), B2 Problem-solving (3) — live observation
- C1 Scale indication (4), C4 3/4 view (5), C5 Highlights (4), C6 Shadows (4) —
  visual judgement
- C7 Style match (5), C8 Creativity (5), C9 Functionality (5) — judgement 0–3
- D7 Resembles reference (6), D8 Quad distribution (5), D9 Edgeflow (5),
  D10 Materials (5) — judgement 0–3

---
## 6. WORKING CODE TO REUSE
A tested batch script already exists and should be the starting point rather
than a rewrite. It contains:
- A **pure-Python PSD reader** (`read_psd`) returning width, height, ppi and
  layer count with no external dependency — lift this directly
- A **Maya audit function** (`check_model`) covering triangles, n-gons, inverted
  normals, construction history, shell/bounding-box analysis and scene contents
- A **scoring function** implementing the table above

Split it into:
- `psd_utils.py` — the PSD reader
- `file_checks.py` — folder walking, filename matching, timestamps
- `maya_worker.py` — runs under mayapy, JSON in / JSON out
- `scoring.py` — the marking rules
- `main.py` — the PySide6 GUI

### Known-fragile: inverted normals
The current method duplicates each mesh, runs `polyNormal -normalMode 2`
(conform) on the copy, and compares face normal vectors via dot product.
`cmds.polyInfo` output formatting varies across Maya versions. It is wrapped in
try/except so it cannot crash the run — **but that means it can silently report
zero.** Make the failure visible: if the normals check throws, record
`"inverted_normals": null` and surface it in the UI as "CHECK FAILED", not as a
pass. Do not let a silent exception award 4 marks.

---
## 7. EXCEL OUTPUT
One file per run: `SC2026_Marking_Results_<date>.xlsx`, saved to the submissions
folder. Two sheets.

**Sheet 1 — "Summary"**: one row per competitor, columns for each of the 11
automated aspects plus the automated total out of 42.

**Sheet 2 — "Full Marking Sheet"**: one block per competitor containing **all 24
aspects** in official order (A 3 rows, B 2 rows, C 9 rows, D 10 rows).
Columns: `Criterion | ID | Aspect | Type | Max Mark | Measured Value | Pass/Fail | Marks Awarded | Notes`

- The 13 human-marked aspects: Measured Value, Pass/Fail and Marks Awarded left
  **blank** for the Chief Expert to fill. Notes column reads
  "JUDGEMENT — CE" or "OBSERVATION — CE".
- **Measured Value must hold the actual finding**, not a repeat of the verdict:
  `9,412 tris`, `14 n-gons`, `3840x2160`, `72 ppi`, `2026-04-15 16:47`,
  `image plane present`. This column is the evidence trail — if a competitor
  challenges a mark, this is what defends it.
- Footer rows per competitor: automated subtotal (of 42), judgement subtotal
  (blank, of 36), behaviour subtotal (blank, of 5), and the line:
  *"Draft produced by automated tool. Judgement and behaviour marks pending
  Chief Expert review. Not a final score."*

Plain formatting. Bold headers, red fill on failed cells, amber on D5. Nothing
else — no logos, no theming.

---
## 8. ERROR HANDLING
The tool runs once a year under time pressure. It must never lose a whole batch
because one file is bad.

- A corrupt or unopenable file → record the error for that competitor, score
  those aspects 0 with the error text in Notes, **continue to the next**
- Maya crash or timeout → retry that file once, then skip with an error note
- Set a per-file timeout (60s is generous) so one bad scene cannot hang the run
- Missing PSD or missing model → not an error, a legitimate 0 with a clear note
- If mayapy cannot start at all → still run the file and PSD checks, show the
  Maya results as "NOT RUN", and tell the user plainly why. Half a result beats
  none.
- Write a `run_log.txt` beside the Excel with everything that happened

---
## 9. BUILD AND DELIVERY
- Build with PyInstaller to a single-file `.exe`, no console window
- `maya_worker.py` must be bundled and extracted at runtime (`--add-data`),
  since mayapy needs a real `.py` file on disk to execute
- Provide a `build.bat` that runs the PyInstaller command
- Note in the README that PyInstaller executables sometimes trigger antivirus
  false positives, and the user may need to allowlist it once

**Test before declaring done.** Create a mock submissions folder with at least
four competitors:
1. A fully clean pass
2. Wrong PPI and wrong canvas size
3. A model with n-gons, construction history left on, and an image plane
4. A missing model file entirely

Confirm the tool scores each correctly and that the failures are the ones you
planted. A clean pass proves much less than a correct failure.

---
## 10. WHAT SUCCESS LOOKS LIKE
The user opens the exe, clicks Browse, picks a folder, clicks Run Check, waits
about a minute for 15 competitors, sees a table with the failures in red, clicks
Export Excel. That is the entire interaction.

If any step needs explaining, the design is wrong.
