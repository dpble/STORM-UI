#!/usr/bin/python
#
# Test fitting: fit a small part of one STORM movie per channel with the
# current XML parameters, so the parameters can be checked before the full run.
#
# Colenso 05_30_18. Rewritten 2026-11 for Python 3.12 / any OS:
#  - paths built with os.path.join (were Windows "\\" strings)
#  - storm-analysis scripts found from the installed package, run with the
#    current Python (were hardcoded to C:/Program Files/Python36/...)
#  - movie_idx = -1 ("all movies") matched no files: the glob had a literal "{}"
#  - the "already fitted" check looked for 647storm_*_mlist.bin in bins/, which is
#    never written there (fits are .hdf5), so it never skipped; removed
#  - a previous result for the same movie is removed first; storm-analysis
#    resumes existing files, so new parameters were silently ignored on re-runs
#  - failed fits raise an error (batchRun ignored exit codes)
#  - no matching movies raises an error instead of reporting success
#  - only the movies fitted now are converted to .bin (was every .hdf5 in bins/)

import glob
import os
import re

import storm_analysis.sa_library.datareader as datareader

try:
    from analysis_scripts.pipeline_utils import (HDF5_TO_BIN, PYTHON, PipelineError,
                                                 fit_cmd, remove_previous_output, run_jobs)
except ImportError:
    from pipeline_utils import (HDF5_TO_BIN, PYTHON, PipelineError,
                                fit_cmd, remove_previous_output, run_jobs)

MINIMUM_LENGTH = 100   # frames; shorter movies are skipped (unchanged from original)


def find_test_movies(input_directory, channel, movie_idx):
    """Movies for one channel. movie_idx >= 0 selects the movie whose trailing
    number equals movie_idx (647storm_03.dax for 3); -1 selects all of them.
    (The original glob "*3.dax" also matched 647storm_13.dax, 647storm_23.dax, ...)"""
    movies = sorted(glob.glob(os.path.join(input_directory, f"{channel}*.dax")))
    if movie_idx is None or movie_idx < 0:
        return movies
    pat = re.compile(r"(\d+)\.dax$")
    return [m for m in movies if pat.search(m) and int(pat.search(m).group(1)) == int(movie_idx)]


def fitting_params(expfolder, max_processes, selected_channels, movie_idx,
                   debug=False, log=print, cancel_event=None):
    """Returns the list of fitted .hdf5 files."""
    expfolder = os.path.normpath(expfolder)
    xml_folder = os.path.join(expfolder, "XMLs")
    input_directory = os.path.join(expfolder, "acquisition")
    bin_folder = os.path.join(input_directory, "bins")
    real_bins = os.path.join(input_directory, "real_bins")

    if not os.path.isdir(input_directory):
        raise PipelineError(f"No acquisition folder in {expfolder}")
    for d in (os.path.join(input_directory, "bead_registration"), bin_folder, real_bins):
        os.makedirs(d, exist_ok=True)

    cmd_lines, outputs = [], []
    for channel in selected_channels:
        base = str(channel)
        xml = os.path.join(xml_folder, base + ".xml")
        if not os.path.isfile(xml):
            raise PipelineError(f"Missing parameters file {xml}")
        movies = find_test_movies(input_directory, base, movie_idx)
        if not movies:
            log(f"{base}: no movie matches index {movie_idx}")
        for movie_file in movies:
            n_frames = datareader.inferReader(movie_file).filmSize()[2]
            if n_frames <= MINIMUM_LENGTH:
                log(f"Skipping {os.path.basename(movie_file)}: {n_frames} frames (needs > {MINIMUM_LENGTH})")
                continue
            mlist = os.path.join(bin_folder, os.path.basename(movie_file)[:-4] + "_mlist.hdf5")
            remove_previous_output(mlist, log)
            log(f"Analyzing {os.path.basename(movie_file)} with {os.path.basename(xml)}")
            cmd_lines.append(fit_cmd(movie_file, mlist, xml))
            outputs.append(mlist)

    if not cmd_lines:
        raise PipelineError("No movies to fit. Check the channels, the movie index, and that "
                            f"movies are named like 647storm_00.dax in {input_directory}")

    run_jobs(cmd_lines, max_processes, log, cancel_event, label="fit")

    # Convert the new results to Insight3 .bin files (as before, into real_bins/).
    conv = []
    for h5 in outputs:
        out_bin = os.path.join(real_bins, os.path.basename(h5)[:-5] + ".bin")
        remove_previous_output(out_bin, log)
        conv.append([PYTHON, HDF5_TO_BIN, "--hdf5", h5, "--bin", out_bin])
    run_jobs(conv, max_processes, log, cancel_event, label="conversion")
    log(f"Done: {len(outputs)} movie(s) fitted.")
    return outputs


if __name__ == "__main__":
    import sys
    fitting_params(sys.argv[1], 2, sys.argv[2:] or ["647"], 0)
