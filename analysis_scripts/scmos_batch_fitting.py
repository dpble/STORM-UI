#!/usr/bin/python
#
# Batch multifit analysis: fit every STORM movie and bead movie, then convert
# the results to .bin files and rendered .tiff images.
#
# Colenso 05_30_18. Rewritten 2026-11 for Python 3.12 / any OS:
#  - paths built with os.path.join (were Windows "\\" strings)
#  - storm-analysis scripts found from the installed package, run with the
#    current Python (were hardcoded to C:/Program Files/Python36/...)
#  - fix: the command list was created once, outside the channel loop, but the
#    batch was run inside it, so every earlier channel's fits were launched
#    again for each later channel
#  - failed fits raise an error (batchRun ignored exit codes)
#  - each run writes new results without resuming or changing old output


import glob
import os
from pathlib import Path
import tempfile
import uuid

import storm_analysis.sa_library.datareader as datareader

from .pipeline_utils import (Cancelled, FitSettingsSnapshot, HDF5_TO_BIN, HDF5_TO_IMAGE,
                             PYTHON, PipelineError, fit_cmd, run_jobs)

# Bead movie -> (output suffix, XML). Unchanged from the original.
BEAD_FITS = [("_Vis647mlist.hdf5", "Visbead_647.xml"),
             ("_561mlist.hdf5", "Visbead_561.xml"),
             ("_488mlist.hdf5", "Visbead_488.xml"),
             ("_750mlist.hdf5", "IRbead_750.xml"),
             ("_IR647mlist.hdf5", "IRbead_647.xml")]

RENDER_SIGMA = {"750storm": 1, "647storm": 0.5, "561storm": 0.5, "488storm": 1}
STORM_IMAGE_SCALE = 10


def batch_fitting(expfolder, max_processes, selected_channels, debug=False,
                  log=print, cancel_event=None, render=True):
    """Fit fresh into an isolated directory and publish only a complete run."""
    experiment = Path(expfolder).resolve()
    acquisition = experiment / "acquisition"
    if not acquisition.is_dir():
        raise PipelineError(f"No acquisition folder in {experiment}")
    root = experiment / "batch_fits"
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=root) as staging:
        stage = Path(staging) / "results"
        result = _fit_batch(acquisition, experiment / "XMLs", stage, max_processes,
                            selected_channels, log, cancel_event, render)
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled("Cancelled before publishing batch results")
        final = root / f"run-{uuid.uuid4().hex}"
        stage.rename(final)
        for key in ("bins", "tiffs", "localizations"):
            result[key] = [str(final / Path(path).relative_to(stage)) for path in result[key]]
        result["output_dir"] = str(final)
        log(f"Batch results: {final}")
        return result


def _fit_batch(acquisition, xml_folder, stage, max_processes, selected_channels, log, cancel_event, render):
    input_directory = str(acquisition)
    bin_folder, real_bins, storm_tiffs = (stage / name for name in ("bins", "real_bins", "stormtiffs"))
    bin_folder.mkdir(parents=True)
    real_bins.mkdir()
    snapshots = FitSettingsSnapshot(stage / "settings")
    selected_channels = list(dict.fromkeys(str(ch) for ch in selected_channels))
    if any(ch + "storm" not in RENDER_SIGMA for ch in selected_channels):
        raise PipelineError("Invalid STORM channel")

    # 1. STORM movies, all selected channels in one batch.
    storm_cmds = []
    h5_by_channel = {}
    for channel in selected_channels:
        base = str(channel)
        xml = os.path.join(xml_folder, base + ".xml")
        movies = sorted(glob.glob(os.path.join(input_directory, base + "storm_*.dax")))
        if not movies:
            log(f"{base}: no movies found")
            continue
        if not os.path.isfile(xml):
            raise PipelineError(f"Missing parameters file {xml}")
        for movie_file in movies:
            if datareader.inferReader(movie_file).filmSize()[2] <= 0:
                continue
            mlist = os.path.join(bin_folder, os.path.basename(movie_file)[:-4] + "_mlist.hdf5")
            log(f"Analyzing {os.path.basename(movie_file)} with {os.path.basename(xml)}")
            storm_cmds.append(fit_cmd(movie_file, mlist, snapshots.copy(xml)))
            h5_by_channel.setdefault(base + "storm", []).append(mlist)
    if not storm_cmds:
        raise PipelineError("No STORM movies found for the selected channels in " + input_directory)

    # 2. Bead registration movies (Regbead*.dax), each fitted with 5 bead XMLs.
    bead_cmds = []
    for movie_file in sorted(glob.glob(os.path.join(input_directory, "Regbead*.dax"))):
        if datareader.inferReader(movie_file).filmSize()[2] <= 1:
            continue
        stem = os.path.join(bin_folder, os.path.basename(movie_file)[:-4])
        for suffix, xml_name in BEAD_FITS:
            xml = os.path.join(xml_folder, xml_name)
            if not os.path.isfile(xml):
                raise PipelineError(f"Missing bead parameters file {xml}")
            log(f"Analyzing {os.path.basename(movie_file)} with {xml_name}")
            bead_cmds.append(fit_cmd(movie_file, stem + suffix, snapshots.copy(xml)))
    run_jobs(storm_cmds, max_processes, log, cancel_event, label="STORM fit")
    if bead_cmds:
        run_jobs(bead_cmds, max_processes, log, cancel_event, label="bead fit")
    else:
        log("No Regbead*.dax bead movies found; skipping bead fitting.")

    # 3. Convert STORM results to .bin.
    conv = []
    bins = []
    for c, files in h5_by_channel.items():
        for h5 in files:
            out = os.path.join(real_bins, os.path.basename(h5)[:-5] + ".bin")
            conv.append([PYTHON, HDF5_TO_BIN, "--hdf5", h5, "--bin", out])
            bins.append(out)
    run_jobs(conv, max_processes, log, cancel_event, label="conversion")

    # 4. Render STORM images.
    tiffs = []
    if render:
        os.makedirs(storm_tiffs, exist_ok=True)
        cmds = []
        for c, files in h5_by_channel.items():
            for h5 in files:
                out = os.path.join(storm_tiffs, os.path.basename(h5)[:-5] + ".tiff")
                cmds.append([PYTHON, HDF5_TO_IMAGE, "--image", out, "--bin", h5,
                             "--scale", str(STORM_IMAGE_SCALE), "--sigma", str(RENDER_SIGMA[c])])
                tiffs.append(out)
        run_jobs(cmds, max_processes, log, cancel_event, label="render")

    # Bead registration (gen_bead_warp_hcam) was commented out in the original
    # and is still not run here.
    log(f"Batch fitting done: {len(storm_cmds)} STORM fits, {len(bead_cmds)} bead fits, "
        f"{len(bins)} .bin files, {len(tiffs)} images.")
    return {"storm_fits": len(storm_cmds), "bead_fits": len(bead_cmds), "bins": bins, "tiffs": tiffs,
            "localizations": [cmd[cmd.index("--bin") + 1] for cmd in storm_cmds + bead_cmds]}


if __name__ == "__main__":
    import sys
    batch_fitting(sys.argv[1], 2, sys.argv[2:] or ["647"])
