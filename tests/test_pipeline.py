"""
Pipeline tests on a simulated experiment with known molecule positions.
Run with:  ./run_dev.sh -m pytest -q tests
"""
import os
import re
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import accuracy                                  # noqa: E402
import make_test_experiment as mte               # noqa: E402
from analysis_scripts import pipeline_utils as pu                  # noqa: E402
from analysis_scripts.fitting_parameters_evaluation import fitting_params, find_test_movies  # noqa: E402
from analysis_scripts.scmos_batch_fitting import batch_fitting     # noqa: E402

import storm_analysis.sa_library.sa_h5py as saH5Py  # noqa: E402


@pytest.fixture(scope="module")
def exp(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("exp"))
    mte.make(d, channels=("647", "750"), sections=2, small=True, beads=1)
    return d


def n_locs(h5):
    with saH5Py.SAH5Reader(h5) as f:
        return f.getNLocalizations()


def quiet(lines):
    return lambda s: lines.append(s)


def test_test_fit_accuracy_vs_ground_truth(exp):
    out = fitting_params(exp, 2, ["647"], 0, log=quiet([]))
    assert [os.path.basename(o) for o in out] == ["647storm_00_mlist.hdf5"]
    roi = accuracy.read_xml_roi(os.path.join(exp, "XMLs", "647.xml"))
    r = accuracy.compare(out[0], os.path.join(exp, "ground_truth", "647storm_00_truth.hdf5"), roi, nm_per_px=roi["nm"])
    print(r)
    assert r["frames"] == 50                      # lab XML fits frames 0..50
    assert r["recall"] > 0.95
    assert r["false_positives"] < 0.01 * r["fitted"]
    assert r["median_error_nm"] < 10.0
    # converted .bin written too
    assert os.path.exists(os.path.join(exp, "acquisition", "test_fits", "647storm_00_mlist.bin"))


def test_test_fit_rerun_uses_new_parameters(exp, tmp_path):
    """storm-analysis resumes an existing file; Test Fit must refit with the new XML."""
    first = fitting_params(exp, 2, ["750"], 1, log=quiet([]))[0]
    before = n_locs(first)
    xml = os.path.join(exp, "XMLs", "750.xml")
    original = open(xml, encoding="latin-1").read()
    try:
        # A huge threshold should find (almost) nothing.
        open(xml, "w", encoding="latin-1").write(
            re.sub(r"(<threshold type=\"float\">)[\d.]+", r"\g<1>100000.0", original))
        logs = []
        after = n_locs(fitting_params(exp, 2, ["750"], 1, log=quiet(logs))[0])
    finally:
        open(xml, "w", encoding="latin-1").write(original)
    assert before > 1000 and after < before * 0.05, (before, after)


def test_all_movies_index_minus_one(exp):
    """Original glob '*{}.dax' (literal braces) matched no files for 'all movies'."""
    out = fitting_params(exp, 4, ["647"], -1, log=quiet([]))
    assert sorted(os.path.basename(o) for o in out) == ["647storm_00_mlist.hdf5", "647storm_01_mlist.hdf5"]


def test_movie_index_matches_exact_number(tmp_path):
    acq = tmp_path
    for name in ["647storm_01.dax", "647storm_11.dax", "647storm_21.dax", "750storm_01.dax"]:
        (acq / name).write_bytes(b"")
    got = [os.path.basename(m) for m in find_test_movies(str(acq), "647", 1)]
    assert got == ["647storm_01.dax"]     # the old '*1.dax' glob also took 11 and 21
    assert len(find_test_movies(str(acq), "647", -1)) == 3


def test_no_matching_movie_is_an_error(exp):
    with pytest.raises(pu.PipelineError, match="No movies to fit"):
        fitting_params(exp, 2, ["647"], 7, log=quiet([]))


def test_failed_fit_is_reported(exp, tmp_path):
    """batchRun ignored exit codes, so a crashed fit looked like success."""
    import shutil
    bad = tmp_path / "bad"
    shutil.copytree(exp, bad, ignore=shutil.ignore_patterns("bins", "real_bins", "stormtiffs"))
    (bad / "XMLs" / "647.xml").write_text("<settings><this is not valid xml")
    with pytest.raises(pu.PipelineError, match="failed"):
        fitting_params(str(bad), 2, ["647"], 0, log=quiet([]))


def test_run_jobs_cancel_kills_running_jobs():
    ev = threading.Event()
    cmds = [[sys.executable, "-c", "import time; time.sleep(30)"] for _ in range(3)]
    threading.Timer(0.5, ev.set).start()
    t0 = time.time()
    with pytest.raises(pu.Cancelled):
        pu.run_jobs(cmds, 3, log=quiet([]), cancel_event=ev)
    assert time.time() - t0 < 5


def test_storm_analysis_scripts_found():
    for p in (pu.SCMOS_ANALYSIS, pu.HDF5_TO_BIN, pu.HDF5_TO_IMAGE):
        assert os.path.isfile(p), p


def test_batch_fitting_each_movie_fitted_once(exp):
    """Original ran the accumulated command list inside the channel loop, so
    earlier channels were launched again for each later channel."""
    logs = []
    r = batch_fitting(exp, 4, ["647", "750"], log=quiet(logs))
    starts = [l for l in logs if l.startswith("[STORM fit")]
    assert len(starts) == 4 and r["storm_fits"] == 4       # 2 channels x 2 sections, once each
    assert r["bead_fits"] == 5                              # 1 bead movie x 5 bead XMLs
    assert len(r["bins"]) == 4 and all(os.path.exists(b) for b in r["bins"])
    assert len(r["tiffs"]) == 4 and all(os.path.exists(t) for t in r["tiffs"])
    beads = os.path.join(r["output_dir"], "bins", "Regbead_000_00_Vis647mlist.hdf5")
    assert n_locs(beads) > 20


def test_demo_generator_refuses_existing_experiment(tmp_path):
    movie = tmp_path / "acquisition" / "647storm_00.dax"
    xml = tmp_path / "XMLs" / "647.xml"
    for path, data in [(movie, b"raw movie"), (xml, b"lab settings")]:
        path.parent.mkdir()
        path.write_bytes(data)
    with pytest.raises(FileExistsError, match="new or empty"):
        mte.make(tmp_path, small=True)
    assert movie.read_bytes() == b"raw movie"
    assert xml.read_bytes() == b"lab settings"
    assert not (tmp_path / "ground_truth").exists()


def test_batch_rerun_and_cancel_preserve_preexisting_results(tmp_path, monkeypatch):
    from pathlib import Path
    from analysis_scripts import scmos_batch_fitting as batch
    mte.make(str(tmp_path), channels=("647", "750"), small=True)
    first = batch_fitting(str(tmp_path), 2, ["647"], render=False, log=quiet([]))
    previous = {Path(path): Path(path).read_bytes() for path in first["localizations"] + first["bins"]}
    xml = tmp_path / "XMLs" / "647.xml"
    t = xml.read_text()
    xml.write_text(t.replace('>50</max_frame>', '>20</max_frame>'))
    second = batch_fitting(str(tmp_path), 2, ["647"], render=False, log=quiet([]))
    assert second["output_dir"] != first["output_dir"]
    assert all("750storm" not in file for file in second["bins"] + second["localizations"])
    with saH5Py.SAH5Reader(second["localizations"][0]) as reader:
        frames = [frame for frame, _ in reader.localizationsIterator()]
    assert max(frames) == 19
    assert all(path.read_bytes() == contents for path, contents in previous.items())

    run_jobs = batch.run_jobs
    def cancel_conversion(cmds, workers, log, cancel_event, label):
        if label == "conversion":
            Path(cmds[0][-1]).write_bytes(b"incomplete conversion")
            raise pu.Cancelled("conversion interrupted")
        return run_jobs(cmds, workers, log, cancel_event, label=label)

    monkeypatch.setattr(batch, "run_jobs", cancel_conversion)
    with pytest.raises(pu.Cancelled):
        batch_fitting(str(tmp_path), 2, ["647"], render=False, log=quiet([]))
    assert sorted(x.name for x in (tmp_path / "batch_fits").iterdir()) == sorted(
        [Path(first["output_dir"]).name, Path(second["output_dir"]).name])
    assert all(path.read_bytes() == contents for path, contents in previous.items())
