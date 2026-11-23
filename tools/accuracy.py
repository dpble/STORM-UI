"""
Compare fitted localizations against simulated ground truth.

Used by the pipeline tests and runnable by hand:
    python tools/accuracy.py fitted.hdf5 truth.hdf5 [--xml 647.xml]
"""
import argparse
from xml.etree import ElementTree as ET

import numpy
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

import storm_analysis.sa_library.sa_h5py as saH5Py


def read_xml_roi(xml):
    root = ET.parse(xml).getroot()
    def bounds(axis):
        return tuple(int(value) if (value := root.findtext(f"{axis}_{end}")) is not None else None
                     for end in ("start", "stop"))
    return dict(x=bounds("x"), y=bounds("y"),
                frames=(int(root.findtext("start_frame", "0")), int(root.findtext("max_frame", "0"))),
                nm=float(root.findtext("pixel_size", "155.0")))


def _points(locs, roi):
    points = numpy.column_stack([locs.get(axis, []) for axis in ("x", "y")])
    if roi:
        for col, axis in enumerate(("x", "y")):
            low, high = roi[axis]
            if low is not None:
                points = points[points[:, col] >= low]
            if high is not None:
                points = points[points[:, col] < high]
    return points


def compare(fitted_h5, truth_h5, roi=None, match_px=1.0, nm_per_px=155.0):
    """Score all expected frames with one-to-one matches within match_px.

    Single-frame truth is a static emitter list, repeated for every frame.
    Longer truth movies are scored using their per-frame localizations.
    """
    errs, fitted, possible, frames = [], 0, 0, 0
    with saH5Py.SAH5Reader(truth_h5) as truth, saH5Py.SAH5Reader(fitted_h5) as fit:
        start, stop = roi["frames"] if roi else (0, 0)
        length = fit.getMovieLength()
        end = min(length, stop) if stop > 0 else length
        for frame in range(max(0, start), end):
            frames += 1
            expected = _points(truth.getLocalizationsInFrame(0 if truth.getMovieLength() == 1 else frame,
                                                              fields=["x", "y"]), roi)
            observed = _points(fit.getLocalizationsInFrame(frame, fields=["x", "y"]), roi)
            possible += len(expected)
            fitted += len(observed)
            if not len(expected) or not len(observed):
                continue
            distance = cdist(observed, expected)
            penalty = (max(distance.shape) + 1) * (match_px + 1)
            row, col = linear_sum_assignment(numpy.where(distance <= match_px, distance, penalty))
            matched = distance[row, col]
            errs.extend(matched[matched <= match_px])
    count = len(errs)
    errs = numpy.asarray(errs) * nm_per_px
    return dict(frames=frames, expected=possible, matched=count, fitted=fitted,
                recall=count / possible if possible else 0.0, false_positives=fitted - count,
                median_error_nm=float(numpy.median(errs)) if count else float("nan"),
                p90_error_nm=float(numpy.percentile(errs, 90)) if count else float("nan"))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("fitted"); p.add_argument("truth"); p.add_argument("--xml")
    a = p.parse_args()
    roi = read_xml_roi(a.xml) if a.xml else None
    r = compare(a.fitted, a.truth, roi, nm_per_px=roi["nm"] if roi else 155.0)
    for k, v in r.items():
        print(f"{k:>16}: {v:.4g}" if isinstance(v, float) else f"{k:>16}: {v}")
