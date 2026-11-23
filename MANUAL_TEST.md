# Hands-on checklist (about 10 minutes)

The automated tests cover the code paths, but not how the app feels to use. Run
this once on your own machine (and again on the lab PC when you can).

Setup: make a simulated experiment and open the app. Use a new or empty demo folder, never an existing experiment.

```
cd STORM-UI
python tools/make_test_experiment.py ~/stormpro-demo --channels 647 750 --sections 2 --beads 1
python main.py
```

On Windows, use `python tools\make_test_experiment.py ...` and `python main.py`
from the activated venv.

Tick each box. If something is off, write down what you did and what you saw.

## Viewer
- [ ] **Help** button opens the quick start and the viewer controls.
- [ ] **Open Movie…** → `~/stormpro-demo/acquisition/647storm_00.dax`. It opens on frame 1 "of 105", with the size in the status bar.
- [ ] Press **A**. Spots become clearly visible.
- [ ] Press **.** five times: frame goes 1 → 6, one at a time. **,** goes back. **End** / **Home** jump to 105 / 1.
- [ ] Scroll the wheel over the movie: it zooms. **Drag** pans. **R** fits the frame again.
- [ ] **Shift + drag** a small box around a few spots: it zooms to the box and the contrast changes (status bar says "from box").
- [ ] Drag the contrast slider handles: the image updates, the min can never go above the max, no crash.
- [ ] Hover over a spot: x, y and the intensity under the cursor show under the movie.
- [ ] Drag a .dax file from Finder onto the movie: it opens, and the frame count is right.
- [ ] **File → Save View as PNG…** asks where to save and writes the image.

## Test fit
- [ ] **Choose Experiment Folder…** → `~/stormpro-demo`. It says "5 movie(s) in acquisition/".
- [ ] Tick **647**. **Edit Test Parameters…** shows the 647 path inside `~/stormpro-demo/XMLs`, start 0, end 50, threshold 14. No error popups.
- [ ] Close it. **Movie number** 0 → **Run Test Fit**. The window stays responsive (try zooming while it runs), the progress bar moves, and the log fills in.
- [ ] When it finishes, the movie opens with green circles on the spots.
- [ ] **Edit Test Parameters…** → set the 647 end frame to 10 → **Update**. Run Test Fit again. Circles only appear on frames 1 to 10 now.
- [ ] Movie number **-1** → Run Test Fit, then press **Cancel** straight away. It stops and the buttons come back.

## Batch fitting
- [ ] Tick **647** and **750**. **Set Frame Ranges…** shows the current values; OK closes it and it does not reopen.
- [ ] **Run Batch Fit**. The log reports 4 STORM fits and 5 bead fits, followed by the new output folder under `batch_fits/`. XY and Z alignment do not run.
- [ ] Run it again. A new output folder is created; the earlier output folder is still present.
- [ ] Close the window while a job runs: cancellation is requested and the window stays open until the job exits. Close it again when idle.

## Notes
Anything confusing, slow, or ugly:

-
-
