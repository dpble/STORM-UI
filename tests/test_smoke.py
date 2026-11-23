"""
Smoke tests for STORMpro. Written to run on both PyQt5 and PyQt6 so the
same checks can be run before and after the port.

Run with:  QT_QPA_PLATFORM=offscreen ./run_dev.sh -m pytest -q tests
Uses the test movie that ships with storm-analysis (test/data/test.dax).
"""
import os
import shutil

import pytest

import storm_analysis
import storm_analysis.sa_library.sa_h5py as saH5Py

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    KEY = QtCore.Qt.Key
except ImportError:
    from PyQt5 import QtCore, QtGui, QtWidgets
    KEY = QtCore.Qt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
TEST_DAX = storm_analysis.getData("test/data/test.dax")
TEST_XML = storm_analysis.getData("test/data/test_3d_2d_fixed.xml")


@pytest.fixture(scope="module")
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield a


@pytest.fixture(scope="module")
def fitted_hdf5():
    """Run a 3D-DAOSTORM fit on the test movie once for the whole module."""
    os.makedirs(OUT, exist_ok=True)
    h5 = os.path.join(OUT, "test_fit.hdf5")
    if os.path.exists(h5):
        os.remove(h5)
    from storm_analysis.daostorm_3d.mufit_analysis import analyze
    analyze(TEST_DAX, h5, TEST_XML)
    return h5


def make_window(app):
    import main
    w = main.Window(directory=OUT)
    w.show()
    app.processEvents()
    return w


def press(w, key):
    ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress if hasattr(QtCore.QEvent, "Type")
                         else QtCore.QEvent.KeyPress, key, QtCore.Qt.KeyboardModifier.NoModifier
                         if hasattr(QtCore.Qt, "KeyboardModifier") else QtCore.Qt.NoModifier)
    w.keyPressEvent(ev)


def test_window_launches(app):
    w = make_window(app)
    assert w.isVisible()
    os.makedirs(OUT, exist_ok=True)
    w.grab().save(os.path.join(OUT, "window.png"))
    w.close()


def test_load_movie_and_step_frames(app):
    w = make_window(app)
    w.handleDragDrop(TEST_DAX)
    w.incCurFrame(0)
    app.processEvents()
    assert w.movie_file is not None
    n = w.film_l
    assert n > 1

    press(w, KEY.Key_Period)   # forward 1
    assert w.cur_frame == 1
    press(w, KEY.Key_Comma)    # back 1
    assert w.cur_frame == 0
    press(w, KEY.Key_End)
    assert w.cur_frame == n - 1
    press(w, KEY.Key_Home)
    assert w.cur_frame == 0
    press(w, KEY.Key_L)        # forward 200 (clamped)
    assert w.cur_frame == min(200, n - 1)
    app.processEvents()
    w.grab().save(os.path.join(OUT, "movie_loaded.png"))
    w.close()


def test_daostorm_fit(fitted_hdf5):
    with saH5Py.SAH5Reader(fitted_hdf5) as h5:
        n = h5.getNLocalizations()
    print("3D-DAOSTORM localizations:", n)
    # storm-analysis's own test expects ~1998 for this movie and settings.
    assert abs(n - 1998) / 1998 < 0.05


def test_load_localizations_overlay(app, fitted_hdf5):
    w = make_window(app)
    w.handleDragDrop(TEST_DAX)
    w.handleDragDrop(fitted_hdf5)
    w.displayFrame(True)
    app.processEvents()
    assert w.locs1_list is not None
    w.grab().save(os.path.join(OUT, "locs_overlay.png"))
    w.close()
