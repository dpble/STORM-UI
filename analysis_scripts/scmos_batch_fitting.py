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
#  - "already done" checks looked for .bin files that are never written to
#    bins/; removed. storm-analysis resumes existing .hdf5 files, so a re-run
#    picks up where it stopped instead of starting over (kept on purpose here)
#  - bead/conversion/rendering steps unchanged in what they produce

import glob
import os

import storm_analysis.sa_library.datareader as datareader

try:
    from analysis_scripts.pipeline_utils import (HDF5_TO_BIN, HDF5_TO_IMAGE, PYTHON,
                                                 PipelineError, fit_cmd, run_jobs)
except ImportError:
    from pipeline_utils import (HDF5_TO_BIN, HDF5_TO_IMAGE, PYTHON,
                                PipelineError, fit_cmd, run_jobs)

try:
    from .gen_bead_warp_hcam import *  # noqa: F401,F403  (kept: original import)
except ImportError:
    pass

# Bead movie -> (output suffix, XML). Unchanged from the original.
BEAD_FITS = [("_Vis647mlist.hdf5", "Visbead_647.xml"),
             ("_561mlist.hdf5", "Visbead_561.xml"),
             ("_488mlist.hdf5", "Visbead_488.xml"),
             ("_750mlist.hdf5", "IRbead_750.xml"),
             ("_IR647mlist.hdf5", "IRbead_647.xml")]

OUTPUT_CHANNELS = ["750storm", "647storm", "561storm", "488storm"]
RENDER_SIGMA = {"750storm": 1, "647storm": 0.5, "561storm": 0.5, "488storm": 1}
STORM_IMAGE_SCALE = 10


def batch_fitting(expfolder, max_processes, selected_channels, debug=False,
                  log=print, cancel_event=None, render=True):
    """Returns a dict with lists of the files produced."""
    expfolder = os.path.normpath(expfolder)
    xml_folder = os.path.join(expfolder, "XMLs")
    input_directory = os.path.join(expfolder, "acquisition")
    bin_folder = os.path.join(input_directory, "bins")
    real_bins = os.path.join(input_directory, "real_bins")
    storm_tiffs = os.path.join(expfolder, "stormtiffs")

    if not os.path.isdir(input_directory):
        raise PipelineError(f"No acquisition folder in {expfolder}")
    for d in (os.path.join(input_directory, "bead_registration"), bin_folder, real_bins):
        os.makedirs(d, exist_ok=True)

    # 1. STORM movies, all selected channels in one batch.
    storm_cmds = []
    for channel in selected_channels:
        base = str(channel)
        xml = os.path.join(xml_folder, base + ".xml")
        movies = sorted(glob.glob(os.path.join(input_directory, base + "*.dax")))
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
            storm_cmds.append(fit_cmd(movie_file, mlist, xml))
    if not storm_cmds:
        raise PipelineError("No STORM movies found for the selected channels in " + input_directory)
    run_jobs(storm_cmds, max_processes, log, cancel_event, label="STORM fit")

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
            bead_cmds.append(fit_cmd(movie_file, stem + suffix, xml))
    if bead_cmds:
        run_jobs(bead_cmds, max_processes, log, cancel_event, label="bead fit")
    else:
        log("No Regbead*.dax bead movies found; skipping bead fitting.")

    # 3. Convert STORM results to .bin.
    h5_by_channel = {c: sorted(glob.glob(os.path.join(bin_folder, c + "*.hdf5"))) for c in OUTPUT_CHANNELS}
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
    return {"storm_fits": len(storm_cmds), "bead_fits": len(bead_cmds), "bins": bins, "tiffs": tiffs}


if __name__ == "__main__":
    import sys
    batch_fitting(sys.argv[1], 2, sys.argv[2:] or ["647"])
