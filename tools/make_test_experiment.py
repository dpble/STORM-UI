"""
Build a simulated STORM experiment folder in the lab's layout, with known
molecule positions, so the pipeline can be tested end to end without lab data.

    <out>/XMLs/            lab fitting XMLs + sCMOS calibration (from ex_pipeline/XMLs)
    <out>/acquisition/     <channel>storm_<section>.dax movies (+ Regbead_NNN_00.dax with --beads)
    <out>/ground_truth/    <channel>storm_<section>_truth.hdf5 (true positions)

Usage:
    python tools/make_test_experiment.py OUT_DIR                  # 896x896, lab calibration
    python tools/make_test_experiment.py OUT_DIR --small          # 256x256 crop (fast, for CI)
    python tools/make_test_experiment.py OUT_DIR --channels 647 750 --sections 2

Emitters are always on (no blinking) so every frame has the same true positions.
That makes the accuracy check exact: fitted vs true position in nm.
"""
import argparse
import glob
import os
import re
import shutil

import numpy

import storm_analysis.sa_library.sa_h5py as saH5Py
import storm_analysis.simulator.background as background
import storm_analysis.simulator.camera as camera
import storm_analysis.simulator.photophysics as photophysics
import storm_analysis.simulator.psf as psf
import storm_analysis.simulator.simulate as simulate

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB_XMLS = os.path.join(REPO, "ex_pipeline", "XMLs")

NM_PER_PIXEL = 155.0   # pixel_size in the lab XMLs
SIGMA_PX = 1.12        # sigma in the lab XMLs (2dfixed model)
PHOTONS = 3000.0       # per emitter per frame
BG_PHOTONS = 20.0      # per pixel per frame
N_FRAMES = 105         # Test Fit skips movies with <= 100 frames
ROI = (50, 200)        # x_start..x_stop / y_start..y_stop in the lab XMLs


def write_emitters(h5_name, size, n_roi, seed):
    """Random emitters inside the fitting ROI (with a margin) plus a sparse field elsewhere."""
    rng = numpy.random.default_rng(seed)
    lo, hi = ROI[0] + 5, ROI[1] - 5
    x = [rng.uniform(lo, hi, n_roi)]
    y = [rng.uniform(lo, hi, n_roi)]
    n_out = max(0, int(n_roi * ((size - 20) ** 2) / ((hi - lo) ** 2) * 0.05))
    x.append(rng.uniform(10, size - 10, n_out))
    y.append(rng.uniform(10, size - 10, n_out))
    x, y = numpy.concatenate(x), numpy.concatenate(y)
    n = x.size
    peaks = {"x": x, "y": y, "z": numpy.zeros(n),
             "xsigma": numpy.full(n, SIGMA_PX), "ysigma": numpy.full(n, SIGMA_PX)}
    with saH5Py.SAH5Py(h5_name, is_existing=False, overwrite=True) as h5:
        h5.setMovieInformation(size, size, 1, "")
        h5.addLocalizations(peaks, 0)
    return n


def copy_xmls(dst, small, size):
    os.makedirs(dst, exist_ok=True)
    for f in glob.glob(os.path.join(LAB_XMLS, "*.xml")):
        if "-Copy" in os.path.basename(f):
            continue
        text = open(f, encoding="latin-1").read()  # lab XMLs are not all UTF-8
        if small:
            text = re.sub(r"(<camera_calibration type=\"filename\">)[^<]+", r"\1calib_small.npy", text)
        open(os.path.join(dst, os.path.basename(f)), "w", encoding="latin-1").write(text)
    for f in glob.glob(os.path.join(LAB_XMLS, "*.npy")):
        shutil.copy(f, dst)
    if small:
        # Crop the lab's 896x896 calibration to the movie size (top-left corner,
        # which contains the fitting ROI).
        cal = numpy.load(os.path.join(LAB_XMLS, "calib_896x896.npy"), allow_pickle=True)
        cropped = [a[:size, :size] if hasattr(a, "shape") and a.ndim == 2 else a for a in cal]
        numpy.save(os.path.join(dst, "calib_small.npy"), numpy.array(cropped, dtype=object), allow_pickle=True)


def calib_for(xml_dir, channel):
    text = open(os.path.join(xml_dir, f"{channel}.xml"), encoding="latin-1").read()
    name = re.search(r"<camera_calibration type=\"filename\">([^<]+)", text).group(1)
    return os.path.join(xml_dir, name)


def make(out, channels=("647",), sections=1, small=False, n_roi=60, n_frames=N_FRAMES, seed=1, beads=0):
    os.makedirs(out, exist_ok=True)
    if os.listdir(out):
        raise FileExistsError(f"Choose a new or empty demo directory: {out}")
    size = 256 if small else 896
    xml_dir = os.path.join(out, "XMLs")
    acq = os.path.join(out, "acquisition")
    truth_dir = os.path.join(out, "ground_truth")
    for d in (acq, truth_dir):
        os.makedirs(d)
    copy_xmls(xml_dir, small, size)

    made = []
    for ch in channels:
        cal = calib_for(xml_dir, ch)
        cal_size = numpy.load(cal, allow_pickle=True)[0].shape
        assert cal_size == (size, size), f"{ch}.xml calibration is {cal_size}, movie is {size}x{size}"
        for s in range(sections):
            name = f"{ch}storm_{s:02d}"
            truth = os.path.join(truth_dir, name + "_truth.hdf5")
            n = write_emitters(truth, size, n_roi, seed + 100 * s + int(ch))
            sim = simulate.Simulate(
                background_factory=lambda st, xs, ys, h5: background.UniformBackground(st, xs, ys, h5, photons=BG_PHOTONS),
                camera_factory=lambda st, xs, ys, h5, cal=cal: camera.SCMOS(st, xs, ys, h5, cal),
                photophysics_factory=lambda st, xs, ys, h5: photophysics.AlwaysOn(st, xs, ys, h5, PHOTONS),
                psf_factory=lambda st, xs, ys, h5: psf.GaussianPSF(st, xs, ys, h5, NM_PER_PIXEL),
                x_size=size, y_size=size)
            dax = os.path.join(acq, name + ".dax")
            sim.simulate(dax, truth, n_frames, verbosity=1000)
            # The simulator also writes a per-frame truth file (_ref.hdf5) and a settings
            # log next to the movie. Move them out so acquisition/ looks like real data.
            shutil.move(os.path.join(acq, name + "_ref.hdf5"), os.path.join(truth_dir, name + "_ref.hdf5"))
            for extra in set(glob.glob(os.path.join(acq, name + "_sim*.txt"))):
                shutil.move(extra, os.path.join(truth_dir, os.path.basename(extra)))
            made.append((dax, n, n_frames))
    for b in range(beads):
        # One registration bead movie: bright beads always on, 25 frames, which
        # covers every bead XML frame range (frames 1 to 23).
        name = f"Regbead_{b:03d}_00"
        cal = calib_for(xml_dir, "647")
        truth = os.path.join(truth_dir, name + "_truth.hdf5")
        n = write_emitters(truth, size, 30, seed + 7 + b)
        sim = simulate.Simulate(
            background_factory=lambda st, xs, ys, h5: background.UniformBackground(st, xs, ys, h5, photons=BG_PHOTONS),
            camera_factory=lambda st, xs, ys, h5, cal=cal: camera.SCMOS(st, xs, ys, h5, cal),
            photophysics_factory=lambda st, xs, ys, h5: photophysics.AlwaysOn(st, xs, ys, h5, 20000.0),
            psf_factory=lambda st, xs, ys, h5: psf.GaussianPSF(st, xs, ys, h5, NM_PER_PIXEL),
            x_size=size, y_size=size)
        dax = os.path.join(acq, name + ".dax")
        sim.simulate(dax, truth, 25, verbosity=1000)
        shutil.move(os.path.join(acq, name + "_ref.hdf5"), os.path.join(truth_dir, name + "_ref.hdf5"))
        for extra in set(glob.glob(os.path.join(acq, name + "_sim*.txt"))):
            shutil.move(extra, os.path.join(truth_dir, os.path.basename(extra)))
        made.append((dax, n, 25))
    return made


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out")
    p.add_argument("--small", action="store_true", help="256x256 movies with a cropped calibration (fast)")
    p.add_argument("--channels", nargs="+", default=["647"])
    p.add_argument("--sections", type=int, default=1)
    p.add_argument("--frames", type=int, default=N_FRAMES)
    p.add_argument("--beads", type=int, default=0, help="number of Regbead bead movies")
    a = p.parse_args()
    for dax, n, nf in make(a.out, a.channels, a.sections, a.small, n_frames=a.frames, beads=a.beads):
        print(f"wrote {dax}  ({n} emitters, {nf} frames)")
