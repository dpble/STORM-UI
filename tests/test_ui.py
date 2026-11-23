"""
Tests for the Phase B UI: background jobs, cancel, error messages, box zoom,
auto contrast, help, drag and drop labels.

Run with:  QT_QPA_PLATFORM=offscreen ./run_dev.sh -m pytest -q tests
"""
import os
import sys
import time

import pytest
from PyQt6 import QtCore, QtGui, QtWidgets

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import make_test_experiment as mte   # noqa: E402

Qt = QtCore.Qt
T = QtCore.QEvent.Type


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def exp(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("uiexp"))
    mte.make(d, channels=("647",), sections=1, small=True)
    return d


@pytest.fixture
def win(app):
    import main
    w = main.Window(directory=REPO)
    w.show()
    app.processEvents()
    yield w
    if w.isBusy():
        w.cancelJob()
        wait_until(app, lambda: not w.isBusy(), 30)
    w.close()


def wait_until(app, cond, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def message_boxes():
    return [w for w in QtWidgets.QApplication.topLevelWidgets()
            if isinstance(w, QtWidgets.QMessageBox) and w.isVisible()]


def box_text(m):
    return m.text() + "\n" + m.informativeText()


def close_message_boxes():
    for m in message_boxes():
        m.close()


def mouse(widget, etype, pos, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    p = QtCore.QPointF(*pos)
    buttons = Qt.MouseButton.NoButton if etype == T.MouseButtonRelease else button
    ev = QtGui.QMouseEvent(etype, p, widget.mapToGlobal(p), button, buttons, mods)
    QtWidgets.QApplication.sendEvent(widget, ev)


# ---------------------------------------------------------------- test fit via the button

def test_test_fit_button_runs_in_background_and_shows_result(win, app, exp):
    win.setExperimentFolder(exp)
    assert "1 movie(s)" in win.exp_hint.text()
    win.ui.checkBox647.setChecked(True)
    win.ui.fit_frame_select.setValue(0)

    t0 = time.time()
    win.ui.fit_btn.click()
    returned_after = time.time() - t0
    # The click returns right away and the job runs in the background
    # (the original ran the fit on the GUI thread and froze the window).
    assert returned_after < 0.5
    assert win.isBusy()
    assert not win.ui.fit_btn.isEnabled() and win.cancel_btn.isEnabled()

    # The GUI keeps handling events while the fit runs.
    ticks = []
    timer = QtCore.QTimer(); timer.timeout.connect(lambda: ticks.append(1)); timer.start(50)
    assert wait_until(app, lambda: not win.isBusy(), 120)
    timer.stop()
    assert len(ticks) >= 3

    assert win.ui.fit_btn.isEnabled() and not win.cancel_btn.isEnabled()
    assert win.progress_bar.format() == "Test fit done"
    log = win.log_view.toPlainText()
    assert "Analyzing 647storm_00.dax with 647.xml" in log
    # Result is opened in the viewer: movie + localization overlay.
    assert win.ui.mov_path_lbl.text().endswith("647storm_00.dax")
    assert win.locs1_list is not None
    assert win.cur_frame == 0
    win.grab().save(os.path.join(REPO, "tests", "output", "ui_test_fit_result.png"))


def test_cancel_stops_job(win, app, exp):
    win.setExperimentFolder(exp)
    win.ui.checkBox647.setChecked(True)
    win.ui.fit_frame_select.setValue(-1)
    win.ui.fit_btn.click()
    assert win.isBusy()
    win.cancelJob()
    assert wait_until(app, lambda: not win.isBusy(), 30)
    assert win.progress_bar.format() in ("Cancelled", "Test fit done")
    assert win.ui.fit_btn.isEnabled()
    close_message_boxes()


def test_test_fit_without_folder_shows_message(win, app):
    win.ui.exp_lbl.setText("")
    win.ui.fit_btn.click()
    app.processEvents()
    assert not win.isBusy()
    assert any("experiment folder" in box_text(m) for m in message_boxes())
    close_message_boxes()


def test_full_analysis_needs_alignment_channel(win, app, exp):
    win.setExperimentFolder(exp)
    win.ui.checkBox647.setChecked(True)
    win.ui.a_checkBox488.setChecked(False)
    win.ui.a_checkBox561.setChecked(False)
    win.ui.multifit_btn.click()
    app.processEvents()
    assert not win.isBusy()
    assert any("alignment channel" in box_text(m) for m in message_boxes())
    close_message_boxes()


def test_existing_results_prompt_never_deletes(win, app, exp, tmp_path):
    """Old dialog said 'delete?' but deleted nothing. Now: Continue or Cancel."""
    import shutil
    d = tmp_path / "e"
    shutil.copytree(exp, d)
    bins = d / "acquisition" / "bins"
    bins.mkdir(exist_ok=True)
    keep = bins / "647storm_00_mlist.hdf5"
    keep.write_bytes(b"previous result")
    win.setExperimentFolder(str(d))
    win.ui.checkBox647.setChecked(True)
    win.ui.a_checkBox561.setChecked(True)

    seen = {}

    def press_cancel():
        for m in message_boxes():
            seen["text"] = box_text(m)
            m.button(QtWidgets.QMessageBox.StandardButton.Cancel).click()
    QtCore.QTimer.singleShot(200, press_cancel)
    win.ui.multifit_btn.click()
    app.processEvents()
    assert "Nothing will be deleted" in seen.get("text", "")
    assert not win.isBusy()
    assert keep.read_bytes() == b"previous result"


def test_full_analysis_reports_the_failing_step(win, app, exp, tmp_path):
    """Batch fitting works on simulated data; XY alignment needs real conventional
    images and Fiji, so it must fail with a clear message, not a frozen or crashed app."""
    import shutil
    d = tmp_path / "f"
    shutil.copytree(exp, d, ignore=shutil.ignore_patterns("bins", "real_bins", "stormtiffs"))
    win.setExperimentFolder(str(d))
    win.ui.checkBox647.setChecked(True)
    win.ui.a_checkBox561.setChecked(True)
    win.ui.multifit_btn.click()
    assert wait_until(app, lambda: not win.isBusy(), 180)
    log = win.log_view.toPlainText()
    assert "=== Batch fitting ===" in log and "Batch fitting done" in log
    assert "=== XY alignment ===" in log
    assert win.progress_bar.format() == "XY alignment failed"
    assert any("XY alignment failed" in m.text() and "missing" in m.informativeText().lower()
               for m in message_boxes())
    close_message_boxes()


# ---------------------------------------------------------------- viewer

def test_drop_movie_updates_labels_and_starts_at_frame_1(win, app, exp):
    movie = os.path.join(exp, "acquisition", "647storm_00.dax")
    win.ui.frame_spin_box.setValue(160)        # leftover value, like the .ui default
    win.handleDragDrop(movie)
    app.processEvents()
    assert win.ui.nmPerPixLabel_2.text() == "of 105"
    assert win.ui.mov_path_lbl.text() == movie
    assert win.cur_frame == 0 and win.ui.frame_spin_box.value() == 1
    assert win.ui.frame_spin_box.decimals() == 0


def test_auto_contrast_key_and_box_zoom(win, app, exp):
    win.loadMovieFile(os.path.join(exp, "acquisition", "647storm_00.dax"))
    app.processEvents()
    ev = QtGui.QKeyEvent(T.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
    win.keyPressEvent(ev)
    lo, hi = win.ui.minSpinBox.value(), win.ui.maxSpinBox.value()
    assert lo < hi and hi < 65535

    # Shift+drag a box over the viewport: zooms in and sets contrast from the box.
    vp = win.movie_view.viewport()
    scale_before = win.movie_view.transform().m11()
    shift = Qt.KeyboardModifier.ShiftModifier
    c = vp.rect().center()
    mouse(vp, T.MouseButtonPress, (c.x() - 40, c.y() - 40), mods=shift)
    mouse(vp, T.MouseMove, (c.x(), c.y()), mods=shift)
    mouse(vp, T.MouseMove, (c.x() + 40, c.y() + 40), mods=shift)
    mouse(vp, T.MouseButtonRelease, (c.x() + 40, c.y() + 40), mods=shift)
    app.processEvents()
    assert win.movie_view.transform().m11() > scale_before
    assert "box" in win.statusBar().currentMessage()

    # R resets the zoom to fit the frame.
    win.keyPressEvent(QtGui.QKeyEvent(T.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier))
    app.processEvents()
    assert win.movie_view.transform().m11() < scale_before * 1.5


def test_auto_contrast_from_region_uses_only_that_region(win, app, exp):
    import numpy as np
    win.loadMovieFile(os.path.join(exp, "acquisition", "647storm_00.dax"))
    data = win.movie_view.data
    lo, hi = win.autoContrast(QtCore.QRectF(0, 0, 20, 20))
    exp_lo, exp_hi = np.percentile(data[0:20, 0:20], [1.0, 99.5])
    assert lo == int(np.floor(exp_lo)) and hi == int(np.ceil(exp_hi))


def test_help_opens(win, app):
    win.help_btn.click()
    app.processEvents()
    texts = [m.text() for m in message_boxes()]
    assert any("Quick start" in t or "quick start" in t.lower() for t in texts)
    assert any("Shift" in t for t in texts)
    close_message_boxes()


def test_every_control_has_a_tooltip(win):
    from gui.layout import TOOLTIPS
    for name in TOOLTIPS:
        assert getattr(win.ui, name).toolTip(), name
    for w in (win.auto_contrast_btn, win.reset_zoom_btn, win.cancel_btn):
        assert w.toolTip()


def test_save_view_png(win, app, exp, tmp_path, monkeypatch):
    win.loadMovieFile(os.path.join(exp, "acquisition", "647storm_00.dax"))
    out = str(tmp_path / "view.png")
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))
    win.capture()
    assert os.path.getsize(out) > 0


def test_parallel_jobs_never_zero(win):
    assert win.ui.proc_spin_box.value() >= 1
    assert win.ui.proc_spin_box.minimum() == 1


def test_drag_pans_when_zoomed(win, app, exp):
    """Original mouseMoveEvent never called the base class, so drag-to-pan did nothing."""
    win.loadMovieFile(os.path.join(exp, "acquisition", "647storm_00.dax"))
    for _ in range(8):
        win.movie_view.zoomIn()
    app.processEvents()
    hbar = win.movie_view.horizontalScrollBar()
    assert hbar.maximum() > 0
    hbar.setValue(hbar.maximum() // 2)
    before = hbar.value()
    vp = win.movie_view.viewport()
    c = vp.rect().center()
    mouse(vp, T.MouseButtonPress, (c.x(), c.y()))
    mouse(vp, T.MouseMove, (c.x() - 60, c.y()))
    mouse(vp, T.MouseMove, (c.x() - 120, c.y()))
    mouse(vp, T.MouseButtonRelease, (c.x() - 120, c.y()))
    app.processEvents()
    assert hbar.value() != before
