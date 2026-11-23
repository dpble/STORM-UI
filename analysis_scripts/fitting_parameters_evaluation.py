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
#  - stage fresh results separately so re-runs use new parameters, without
#    touching batch results or losing previous test fits on failure
#  - failed fits raise an error (batchRun ignored exit codes)
#  - no matching movies raises an error instead of reporting success
#  - only the movies fitted now are converted to .bin (was every .hdf5 in bins/)

from pathlib import Path
import os
import re
import tempfile
import uuid


from .pipeline_utils import (FitSettingsSnapshot, HDF5_TO_BIN, PYTHON, PipelineError,
                             check_cancel, fit_cmd, plan_fit, run_jobs, verify_artifacts, verify_fits, write_manifest)

CHANNELS = {"488", "561", "647", "750"}


def find_test_movies(input_directory, channel, movie_idx):
    """Accept CHANNEL_INDEX and CHANNELstorm_INDEX, with optional numbered section fields."""
    if str(channel) not in CHANNELS:
        raise PipelineError(f"Unknown STORM channel: {channel}")
    pattern = re.compile(rf"{channel}(?:storm_|_)([0-9]+(?:_[0-9]+)*)\.dax")
    movies = []
    for path in sorted(Path(input_directory).iterdir()):
        match = pattern.fullmatch(path.name)
        if match and path.is_file():
            if movie_idx is None or movie_idx < 0 or int(match[1].rsplit("_", 1)[-1]) == movie_idx:
                movies.append(str(path))
    if movie_idx is not None and movie_idx >= 0 and len(movies) > 1:
        raise PipelineError(f"Ambiguous index {movie_idx} for channel {channel}: " +
                            ", ".join(Path(movie).name for movie in movies))
    return movies


def fitting_params(expfolder, max_processes, selected_channels, movie_idx,
                   debug=False, log=print, cancel_event=None, return_records=False):
    """Run and publish a complete Test Fit. Optionally return exact viewer records."""
    experiment = Path(os.path.abspath(expfolder))
    acquisition = experiment / "acquisition"
    if not acquisition.is_dir():
        raise PipelineError(f"No acquisition folder in {experiment}")
    root = acquisition / "test_fits"
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=root) as staging:
        stage = Path(staging) / "results"
        stage.mkdir()
        snapshots = FitSettingsSnapshot(stage / "settings", cancel_event)
        records = []
        for channel in dict.fromkeys(str(c) for c in selected_channels):
            check_cancel(cancel_event)
            movies = find_test_movies(acquisition, channel, movie_idx)
            if not movies:
                raise PipelineError(f"No movies to fit for channel {channel} at index {movie_idx}")
            xml = experiment / "XMLs" / f"{channel}.xml"
            settings = snapshots.copy(xml)
            for movie in movies:
                output = stage / f"{Path(movie).stem}_mlist.hdf5"
                log(f"Analyzing {Path(movie).name} with {xml.name}")
                records.append(plan_fit(movie, output, settings, log, cancel_event))
        if not records:
            raise PipelineError("No movies to fit")
        commands = [fit_cmd(r["movie"], r["output"], r["xml"]) for r in records]
        run_jobs(commands, max_processes, log, cancel_event, label="fit")
        verify_fits(records, cancel_event)
        outputs = [r["output"] for r in records]
        conv = [[PYTHON, HDF5_TO_BIN, "--hdf5", h5, "--bin", h5[:-5] + ".bin"] for h5 in outputs]
        run_jobs(conv, max_processes, log, cancel_event, label="conversion")
        verify_artifacts([cmd[-1] for cmd in conv])
        write_manifest(stage, records)
        check_cancel(cancel_event)
        final = root / f"run-{uuid.uuid4().hex}"
        stage.rename(final)
        for record in records:
            for key in ("output", "xml"):
                record[key] = str(final / Path(record[key]).relative_to(stage))
    log(f"Done: {len(records)} movie(s) fitted. Results published to {final}.")
    return records if return_records else [r["output"] for r in records]


if __name__ == "__main__":
    import sys
    fitting_params(sys.argv[1], 2, sys.argv[2:] or ["647"], 0)
