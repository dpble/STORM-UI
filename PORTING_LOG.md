# Porting log: STORM-UI (STORMpro) to Python 3.12 and PyQt6

Fork: https://github.com/dpble/STORM-UI (upstream: SpeerLab/STORM-UI, last commit Oct 2021)
Branch: `pyqt6-port`
Machine: MacBook (Apple Silicon), macOS, Python 3.12.6

## Setup

1. `brew install fftw lapack` (C libraries storm-analysis needs).
2. storm-analysis is not on PyPI or conda-forge anymore, so it is built from source:
   `git clone https://github.com/ZhuangLab/storm-analysis ../storm-analysis`, then
   `pip install -e ../storm-analysis` inside `.venv`. Version 2.4.1.
3. Its own test suite: **294 passed, 1 skipped** (the skip is its PyQt6 visualizer test, PyQt6 not installed yet).
4. `./run_dev.sh` recreates the lab PC's Python path (storm_analysis, sa_library and
   analysis_scripts on PYTHONPATH) so the original bare imports work. Temporary.

## Smoke tests (`tests/test_smoke.py`)

Run: `QT_QPA_PLATFORM=offscreen ./run_dev.sh -m pytest -q tests`

Uses storm-analysis's bundled test movie (`test/data/test.dax`, 10 frames) until the lab data set is available.

1. Main window launches.
2. Loads a .dax movie and steps frames with `.` `,` `Home` `End` `l`.
3. 3D-DAOSTORM fit on the test movie finds about 1998 localizations (storm-analysis's reference number, 5% tolerance).
4. Fitted HDF5 loads as a localization overlay on the movie.

Written to work on both PyQt5 and PyQt6, so the same tests run before and after the port.

## Baseline on PyQt5 (before the port)

Status: **4 of 4 smoke tests pass** after the fixes below.

### What broke and how it was fixed

| # | File | Problem | Fix |
|---|------|---------|-----|
| 1 | requirements.txt | 2021 pins (numpy 1.19, scipy 1.5, pandas 0.24, pywinpty) do not install on Python 3.12 / Apple Silicon | Installed current versions; new pinned list to come with the port |
| 2 | scmos_batch_fitting.py | `import storm_analysis.Name_Correction`: lab-local file, not in any repo | Import commented out. Its only use (line 44) was already commented out |
| 3 | z_alignment.py, z_alignment_561storm_488wga.py | `from cproc import *`, `from reorder import *`: lab-local files, not in the repo | Wrapped in try/except so the GUI loads. Z-alignment may need them |
| 4 | image_chrom_align_hcam.py, combined_matlab_conversion.py | `tifffile.imsave` removed from tifffile | `from tifffile import imwrite as imsave` |
| 5 | corr_mols_v8.py, main.py | `np.int`, `np.float` removed in numpy 1.24 | Plain `int`, `float` |
| 6 | main.py `handleFrameSpinBox` | **Off-by-one bug**: frame box is 1-indexed but its value was used as the 0-indexed frame. Every step moved 2 frames, so the viewer skipped every other frame and opened on frame 2 | `value() - 1`. Verified: steps now go 0, 1, 2, 3 |

Also needed `image_registration` (Adam Ginsburg's package, used by py_dftregistration.py) and `tqdm`, which were missing from requirements.txt.

### Smaller issues seen, not fixed yet

- Drag and drop a movie: the "of N" frame count label is not updated (shows "of 10000"). Load Movie button does update it.
- "Load Experiment Folder" button text is clipped.
- Font "MS Shell Dlg 2" (Windows-only) is requested in the .ui files; Qt substitutes it.

## Questions for Dr. Speer

1. Are `cproc.py`, `reorder.py`, and `Name_Correction.py` on the lab computer? Z-alignment imports the first two.
2. z_alignment.py calls `fiji_z_align1_488wga.py`, `fiji_z_align2_488wga.py`, `fiji_z_align3_488wga.py`, but `macros/` only has the `_FullChannel` versions of the 488 scripts and no `fiji_z_align3_488wga.py`. Are the others somewhere?
3. Fiji path is hardcoded to `C:/Users/Colenso/Fiji.app/ImageJ-win64` with `-Xms50g -Xmx50g`. Is the lab analysis PC still Windows with 64+ GB RAM? (Plan: move path and memory into configs/.)
4. MATLAB: Samarth's understanding is it is still part of the workflow, now called from the code. Which .m steps run today (gen_bead_warp_hcam, test_bead_warp_hcam, wga_norm_and_thresh)? Note `image_chrom_align_hcam.py` is MATLAB code saved as .py and is not imported anywhere.
5. Paths are built with `"\\"` in several scripts (Windows-only). OK to switch to `os.path.join` so it runs on Mac/Linux too?

6. The `gui/ui/*.ui` Designer files are older than the `gui/*_ui.py` files the app runs (frame box maximums, colors, a removed label). OK to update the .ui files to match, so future Designer edits do not undo those changes?

## Phase 2: PyQt6 port (done 2026-11-23)

Status: **app runs on PyQt6 6.12.1 with PyQt5 uninstalled. 11 of 11 tests pass**, also in a fresh venv built only from the new requirements.txt.

### How it was ported

- `tools/pyqt5_to_6.py` rewrites scoped enums by asking PyQt6 which nested enum holds each name (no hand-written table), moves QAction to QtGui, `exec_()` -> `exec()`. It prints every rewrite. 172 rewrites across 10 files.
- The `gui/*_ui.py` files were ported directly, not regenerated, because the `.ui` sources are stale (see question 6). Regenerating would have reset the frame boxes to Qt's default maximum of 99.
- `qtmodern` (PyQt5 only) replaced by `gui/dark_theme.py`: Fusion style with a dark palette, same look, no dependency.
- requirements.txt rewritten: 14 packages the code actually imports, pinned to tested versions (was 110 pins for Python 3.6, most unused, pandas never imported).

### PyQt6 breakages fixed by hand

| File | Problem | Fix |
|------|---------|-----|
| main.py | `RenderHint.A + RenderHint.B`: PyQt6 enums cannot be added | `\|` |
| gui/qtRangeSlider.py | `Qt.gray` etc.: lowercase color enums | `Qt.GlobalColor.gray` (converter widened) |
| gui/qtRangeSlider.py | `event.x()`/`event.y()` removed. **Any click on the contrast slider would crash the app** | `event.position().x()` |
| gui/*_dlg.py | `QFileDialog.Options()` removed | `QFileDialog.Option(0)` |

### Bugs in the original code (also present on PyQt5)

| File | Problem | Fix |
|------|---------|-----|
| main.py dropEvent | Path taken as `text()[8:]`, only valid on Windows. On Mac it dropped the leading `/` | `QUrl.toLocalFile()` |
| main.py open_input_parameters_dlg | "Set Test Parameters" dialog was a local variable, garbage collected on return, so it closed instantly. **Confirmed on the original PyQt5 code: 0 dialogs open after the click** | Keep a reference on the window |
| gui/advanced_settings_dlg.py, gui/frame_range_dlg.py | Config path hardcoded to `C:\Users\Vatsal\QT_Projects\...`. Both dialogs crashed on any other PC | Path relative to the repo |
| 6 files | `yaml.load(f)` needs a Loader in PyYAML 6 | `yaml.safe_load(f)` |

### Tests added (`tests/test_interaction.py`)

Mouse move/press/release on the movie, wheel zoom, contrast slider drag, drop path on this OS, Set Test Parameters stays open, Frame Range dialog opens, all 3 dialogs build.

## Still to do

- Replace bare imports with package imports so run_dev.sh is no longer needed.
- Move the remaining hardcoded paths into configs/ (about 25 in analysis_scripts: Fiji, `C:/Program Files/Python36/.../storm_analysis/...`, test folders). These block the fitting and alignment buttons on any PC but the original one. Phase 3.
- Smaller GUI issues: drag-and-drop does not update the "of N" frame count; frame box shows decimals ("1.00"); "MS Shell Dlg 2" font is Windows-only.
- Remove the 2021 `__pycache__/*.pyc` files committed to the repo.
