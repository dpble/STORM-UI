"""
Compare fitted localizations against simulated ground truth.

Used by the pipeline tests and runnable by hand:
    python tools/accuracy.py fitted.hdf5 truth.hdf5 [--xml 647.xml]
"""
import argparse
import re

import numpy
from scipy.spatial import cKDTree

import storm_analysis.sa_library.sa_h5py as saH5Py


def read_xml_roi(xml):
    t = open(xml, encoding="latin-1").read()
    g = lambda k: int(re.search(rf"<{k} type=\"int\">(-?\d+)<", t).group(1))
    return dict(x=(g("x_start"), g("x_stop")), y=(g("y_start"), g("y_stop")),
                frames=(g("start_frame"), g("max_frame")),
                nm=float(re.search(r"<pixel_size type=\"float\">([\d.]+)<", t).group(1)))


def compare(fitted_h5, truth_h5, roi=None, match_px=1.0, nm_per_px=155.0):
    """
    Per-frame nearest-neighbour matching of fits to true emitters inside the ROI.
    Returns dict with recall, false positives, and position error in nm.
    """
    with saH5Py.SAH5Reader(truth_h5) as h5:
        t = h5.getLocalizationsInFrame(0, fields=["x", "y"])
    tx, ty = t["x"], t["y"]
    if roi:
        keep = (tx >= roi["x"][0] + 2) & (tx < roi["x"][1] - 2) & (ty >= roi["y"][0] + 2) & (ty < roi["y"][1] - 2)
        tx, ty = tx[keep], ty[keep]
    tree = cKDTree(numpy.column_stack([tx, ty]))

    errs, found, fitted_total, false_pos, frames = [], 0, 0, 0, 0
    with saH5Py.SAH5Reader(fitted_h5) as h5:
        for fnum, locs in h5.localizationsIterator(fields=["x", "y"]):
            if "x" not in locs or locs["x"].size == 0:
                continue
            fx, fy = locs["x"], locs["y"]
            if roi:
                k = (fx >= roi["x"][0] + 2) & (fx < roi["x"][1] - 2) & (fy >= roi["y"][0] + 2) & (fy < roi["y"][1] - 2)
                fx, fy = fx[k], fy[k]
            frames += 1
            d, idx = tree.query(numpy.column_stack([fx, fy]), distance_upper_bound=match_px)
            ok = numpy.isfinite(d)
            fitted_total += fx.size
            false_pos += int((~ok).sum())
            # one match per true emitter per frame
            uniq = numpy.unique(idx[ok])
            found += uniq.size
            errs.extend(d[ok].tolist())

    errs = numpy.array(errs) * nm_per_px
    possible = frames * len(tx)
    return {
        "frames": frames,
        "true_emitters": int(len(tx)),
        "fitted": int(fitted_total),
        "recall": found / possible if possible else 0.0,
        "false_positives": int(false_pos),
        "median_error_nm": float(numpy.median(errs)) if errs.size else float("nan"),
        "p90_error_nm": float(numpy.percentile(errs, 90)) if errs.size else float("nan"),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("fitted"); p.add_argument("truth"); p.add_argument("--xml")
    a = p.parse_args()
    roi = read_xml_roi(a.xml) if a.xml else None
    r = compare(a.fitted, a.truth, roi, nm_per_px=roi["nm"] if roi else 155.0)
    for k, v in r.items():
        print(f"{k:>16}: {v:.4g}" if isinstance(v, float) else f"{k:>16}: {v}")
