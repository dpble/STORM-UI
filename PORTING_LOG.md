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
4. MATLAB: the MATLAB calls in batch fitting are commented out, and `gen_bead_warp_hcam.py` / `wga_norm_and_thresh.py` look like Python ports of the .m files. Is any MATLAB still run today? Is the bead warp (gen_bead_warp_and_chrom_align) the step that replaced it? (`image_chrom_align_hcam.py` is MATLAB code saved as .py and is not imported anywhere.)
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

Correction (Phase B): the Phase 2 slider test pressed in the middle of the slider, so it never moved a handle and could not catch the slider crash found later. It now drags the min handle and checks the value changed.

7. "Delete existing files?" in Run Analysis never deleted anything (the code was commented out). It is now "Existing results found: Continue or Cancel" and nothing is deleted. Should it ever delete old results, or is resume-and-keep right?
8. XY and Z alignment need conventional images (`Conv_*.dax`), flat-field images (`FFC_*.dax`), bead movies and Fiji. Could the test data set include one small experiment with all of these, so alignment can be ported and tested?

## Phase A: make the pipeline work (2026-11-23)

### Simulated experiment with known answers
`tools/make_test_experiment.py` writes movies in the lab layout (`acquisition/647storm_00.dax`, `Regbead_000_00.dax`, `XMLs/`) using the lab's XMLs and sCMOS calibration, with known emitter positions. `tools/accuracy.py` matches fits to the truth.

| Run | Recall | False positives | Median error |
|-----|--------|-----------------|--------------|
| 647, full 896x896 lab calibration, frames 0-50 | 98.5% | 1 of 3256 | 5.0 nm |
| 647, 256x256 crop (CI size) | 98.4% | 3 of 3155 | 4.8 nm |
| 750, 256x256 crop, all 105 frames | 98.6% | 0 of 6314 | 5.2 nm |

3000 photons, 155 nm pixels, sigma 1.12 px, 20 photons/px background. The theoretical best precision for these settings is roughly 3 to 5 nm, so ~5 nm is in range, not suspiciously good.

### Bugs fixed in Test Fit and batch fitting

| File | Problem | Fix |
|------|---------|-----|
| fitting_parameters_evaluation.py | Windows `"\\"` paths, `C:/Program Files/Python36/...` script paths, bare `python` | `os.path.join`, scripts from the installed storm_analysis, `sys.executable` |
| fitting_parameters_evaluation.py | Movie index -1 ("all movies") matched nothing: glob had a literal `{}` | Fixed |
| fitting_parameters_evaluation.py | Index 1 also matched movies 11, 21, ... | Match the exact trailing number |
| fitting_parameters_evaluation.py | **Re-running Test Fit kept the old result.** storm-analysis resumes an existing output file. Measured: threshold raised to 100000, re-run still reported 7035 localizations (fixed: 0) | Stage a fresh result under `acquisition/test_fits/`; leave batch outputs and previous test results intact on failed fits |
| fitting_parameters_evaluation.py | "Already fitted" check looked for `.bin` files that are never written to `bins/` | Removed |
| scmos_batch_fitting.py | Command list built outside the channel loop, run inside it: earlier channels relaunched for every later channel | One batch, each movie once (tested) |
| both | storm-analysis `batchRun` ignores exit codes: a crashed fit looked like success | `pipeline_utils.run_jobs` checks exit codes, supports cancel |
| XY_alignment.py (not fixed) | On Mac the `"\\"` paths create folders literally named `exp\acquisition\distcorr\` | Waiting for real data, see question 8 |

## Phase B: UI (2026-11-23)

- Jobs run in a background thread: progress bar, live log, Cancel. The window used to freeze for the whole run.
- Test Fit opens the fitted movie with its localizations.
- Layout: viewer out of the floating MDI subwindow; left panel in numbered steps; tooltips on every control; Help menu; status bar.
- Shift+drag box: zoom to it and set contrast from it. Auto Contrast (A), Reset Zoom (R).
- Dialogs edit the experiment's `XMLs/` (what Test Fit reads), not the placeholder paths in `configs/XMLs.yml`.

### More bugs found while building the UI

| Where | Problem | Fix |
|------|---------|-----|
| main.py handleRangeChange | **Dragging the contrast slider crashed the app under PyQt6** (float into QSpinBox.setValue; PyQt5 rounded silently) | `int(round())` |
| gui/qtRangeSlider.py | Dragging min past max moved the handle but not the value: min > max (original) | Keep them ordered |
| main.py | Contrast slider spanned 0-65535, ~150 counts per pixel; typical data used the bottom few pixels | Range fitted to the loaded movie |
| main.py MovieView.mouseMoveEvent | **Drag-to-pan never worked**: base class never called. Confirmed on the original PyQt5 code | Call the base class |
| main.py | Opening a movie jumped to the last frame (spin box max clamp fired valueChanged) | Block signals while resetting |
| gui/advanced_settings_dlg.py | Loading an XML passed floats to integer frame boxes: crash under PyQt6 | `int(float())` |
| gui/advanced_settings_dlg.py, frame_range_dlg.py | Edited `configs/XMLs.yml` placeholder paths, not the experiment's XMLs | Use the experiment's `XMLs/` |
| gui/frame_range_dlg.py | Stopped at the first missing channel after writing earlier ones; showed defaults, not file values | Write all present, report missing; prefill |
| main.py open_frame_range_dlg | `show()` after `exec()`: dialog reopened after OK/Cancel | Removed |
| main.py | "Delete existing files?" deleted nothing | Honest Continue/Cancel prompt |
| main.py | Error dialogs had their heading only in the title, which macOS hides | Heading in the text |
| main.py | Parallel jobs defaulted to 0; frame box showed "1.00"; capture.png saved to the launch folder; closing during a job | Fixed |
| tests | Tests wrote into the real user's settings (contrast, folder, window position) | Settings redirected to a temp folder in tests |

## Phase C: testing

- **41 tests** (`pytest tests`, about a minute): smoke, interaction, pipeline accuracy, UI jobs/cancel/errors, dialogs.
- Every bug fix that could be tested has a test; the Test Fit re-run test was checked to fail with the fix turned off.
- Real macOS window (Cocoa, Retina) checked by screenshot.
- A Linux/macOS/Windows workflow is prepared locally; upload is blocked by missing `workflow` scope.
- `MANUAL_TEST.md`: 10 minute hands-on checklist.

## Still to do

- XY and Z alignment (question 8), Fiji path and memory into configs/.
- Replace bare imports with package imports (tests no longer need run_dev.sh; the app still does).
- Sync the `.ui` files (question 6). "MS Shell Dlg 2" font warning from the dialog .ui stylesheets.

## Alignment input check

XY alignment checks `acquisition/` for conventional `Conv_*.dax` and flat-field
`FFC_*.dax` movies before calling legacy processing. If either is absent, the
error lists the exact directory and missing patterns without creating output
folders. This checks presence only; it does not validate frames, calibration,
Fiji macros, or XY/Z output. Two regression cases failed before the fix and
passed afterward; the full macOS suite passed 43 tests.

For the next alignment run, request one small complete lab experiment with
conventional, flat-field, STORM and registration bead movies, their `.inf`
sidecars, the matching `XMLs/` and calibration, and a reference aligned result
if available. Use a disposable working copy for validation.
