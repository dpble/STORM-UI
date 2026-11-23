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
    assert w.locs1_list is not None and w.locs1_list.mol_items
    w.updateInfo(1, 1)
    w.ui.frame_spin_box.setValue(2)
    assert not w.locs1_list.mol_items
    w.updateInfo(1, 1)  # immediate click before the deferred redraw
    w.displayFrame(True)
    w.updateInfo(1, 1)
    w.grab().save(os.path.join(OUT, "locs_overlay.png"))
    w.close()


def test_click_at_drawn_peak_center_selects_that_peak(app):
    import numpy as np
    from main import MoleculeList

    class TwoPeaks(MoleculeList):
        def loadLocalizations(self, frame_number, nm_per_pixel):
            return {"x": np.array([10.0, 11.0]), "y": np.array([10.0, 11.0])}

    peaks = TwoPeaks()
    items = peaks.createMolItems(0, 155)
    for index in (0, 1, 0):
        center = items[index].rect().center()
        assert peaks.getClosest(center.x(), center.y())["x"] == 10 + index


def test_unreadable_frame_clears_image_overlays_and_inspector(app, fitted_hdf5, monkeypatch):
    w = make_window(app)
    try:
        assert w.loadMovieFile(TEST_DAX)
        assert w.loadLocalizations(fitted_hdf5, 1)
        w.displayFrame(True)
        assert w.locs1_list.mol_items
        w.updateInfo(10, 10)
        read = w.movie_file.loadAFrame

        def read_frame(frame):
            if frame == 1:
                raise OSError("broken frame")
            return read(frame)

        monkeypatch.setattr(w.movie_file, "loadAFrame", read_frame)
        w.ui.frame_spin_box.setValue(2)
        assert w.cur_frame == 1
        assert w.movie_view.data is None
        assert not w.locs1_list.mol_items
        assert not w.locs_display_timer.isActive()
        items = w.movie_view.scene.items()
        assert len(items) == 1 and items[0].text() == "Frame 2 could not be read"
        table = w.locs1_table.table_widget
        assert all(table.item(row, 1).text() == "na" for row in range(table.rowCount()))
        w.ui.frame_spin_box.setValue(3)
        w.displayFrame(True)
        assert w.cur_frame == 2 and w.movie_view.data is not None
        assert w.locs1_list.mol_items
    finally:
        w.close()
