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
4. Which steps still use MATLAB (gen_bead_warp_hcam, test_bead_warp_hcam, wga_norm_and_thresh)? Is MATLAB still part of the workflow?
5. Paths are built with `"\\"` in several scripts (Windows-only). OK to switch to `os.path.join` so it runs on Mac/Linux too?

## Next: PyQt6 port (Phase 2)

- Regenerate gui/*_ui.py from gui/ui/*.ui with pyuic6.
- Scoped enums (`Qt.Key_End` -> `Qt.Key.Key_End`), `exec_()` -> `exec()`, QAction moved to QtGui, mouse event `.pos()` changes.
- Replace qtmodern (PyQt5 only).
- Replace bare imports with package imports so run_dev.sh is no longer needed.
- Move hardcoded paths into configs/.
