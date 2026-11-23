"""
Interaction tests: the code paths the smoke tests do not touch.
On PyQt6 an exception inside a Qt event handler aborts the whole app,
so each handler here is driven at least once.

Run with:  QT_QPA_PLATFORM=offscreen ./run_dev.sh -m pytest -q tests
"""
import gc
import os

import pytest

import storm_analysis
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtTest import QTest

Qt = QtCore.Qt
TEST_DAX = storm_analysis.getData("test/data/test.dax")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def win(app):
    import main
    w = main.Window(directory=OUT)
    w.show()
    w.handleDragDrop(TEST_DAX)
    w.incCurFrame(0)
    app.processEvents()
    yield w
    w.close()


def mouse(widget, etype, pos, button=Qt.MouseButton.LeftButton):
    p = QtCore.QPointF(*pos)
    ev = QtGui.QMouseEvent(etype, p, widget.mapToGlobal(p), button,
                           button if etype != QtCore.QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(widget, ev)


def test_movie_view_mouse(win, app):
    vp = win.movie_view.viewport()
    T = QtCore.QEvent.Type
    mouse(vp, T.MouseMove, (40, 40), Qt.MouseButton.NoButton)
    mouse(vp, T.MouseButtonPress, (40, 40))
    mouse(vp, T.MouseMove, (60, 50))
    mouse(vp, T.MouseButtonRelease, (60, 50))
    app.processEvents()
    # x, y, intensity readout under the cursor gets filled in
    assert "," in win.movie_view.xyi_label.text()


def test_wheel_zoom_and_frame_scroll(win, app):
    vp = win.movie_view.viewport()
    before = win.movie_view.transform().m11()
    ev = QtGui.QWheelEvent(QtCore.QPointF(40, 40), QtCore.QPointF(40, 40), QtCore.QPoint(0, 0),
                           QtCore.QPoint(0, 120), Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QtWidgets.QApplication.sendEvent(vp, ev)
    app.processEvents()
    assert win.movie_view.transform().m11() > before   # zoomed in


def test_contrast_range_slider_drag(win, app):
    """Drag the slider's min handle. The slider emits floats; PyQt6 rejects floats
    in QSpinBox.setValue, which crashed the app before the fix."""
    s = win.rangeSlider
    T = QtCore.QEvent.Type
    s.updateDisplayValues()
    # vertical slider: getPos() = height - y, min handle sits just below display_min
    handle_y = s.height() - (s.display_min - 0.5 * s.bar_width)
    x = s.width() // 2
    before = win.ui.minSpinBox.value()
    mouse(s, T.MouseButtonPress, (x, handle_y))
    assert s.moving == "min"
    mouse(s, T.MouseMove, (x, handle_y - 15))
    mouse(s, T.MouseButtonRelease, (x, handle_y - 15))
    app.processEvents()
    after = win.ui.minSpinBox.value()
    assert after > before, (before, after)          # the drag really changed the range
    assert after <= win.ui.maxSpinBox.value()


def test_contrast_slider_min_never_passes_max(win, app):
    """Original bug: dragging min past max moved the max handle but not its value."""
    s = win.rangeSlider
    T = QtCore.QEvent.Type
    s.updateDisplayValues()
    handle_y = s.height() - (s.display_min - 0.5 * s.bar_width)
    x = s.width() // 2
    mouse(s, T.MouseButtonPress, (x, handle_y))
    mouse(s, T.MouseMove, (x, 25))                  # far past the max handle
    mouse(s, T.MouseButtonRelease, (x, 25))
    app.processEvents()
    assert win.ui.minSpinBox.value() <= win.ui.maxSpinBox.value()


def test_contrast_slider_fits_movie_range(win):
    # test.dax values are well under 65535; the slider top should be near the data
    assert win.rangeSlider.start + win.rangeSlider.scale < 65535


def test_drop_path_is_valid_on_this_os(win):
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(TEST_DAX)])
    path = win.movie_view.droppedPath(mime)
    assert os.path.samefile(path, TEST_DAX)


def test_set_test_parameters_dialog_stays_open(win, app):
    from gui.advanced_settings_dlg import AdvancedSettingsDialog
    win.open_input_parameters_dlg()
    gc.collect()
    app.processEvents()
    open_dlgs = [d for d in QtWidgets.QApplication.topLevelWidgets()
                 if isinstance(d, AdvancedSettingsDialog) and d.isVisible()]
    assert open_dlgs, "Set Test Parameters dialog was garbage collected right after opening"
    for d in open_dlgs:
        d.close()


def test_frame_range_dialog_opens(win, app):
    # The dialog is modal (exec), so close it from a timer once it is up.
    seen = []

    def close_it():
        for d in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(d, QtWidgets.QDialog) and d.isVisible():
                seen.append(type(d).__name__)
                d.reject()
    QtCore.QTimer.singleShot(300, close_it)
    QtCore.QTimer.singleShot(600, close_it)   # it calls show() again after exec()
    win.open_frame_range_dlg()
    app.processEvents()
    assert "FrameRangeDialog" in seen


def test_all_dialogs_construct(app):
    from gui.advanced_settings_dlg import AdvancedSettingsDialog
    from gui.frame_range_dlg import FrameRangeDialog
    from gui.input_parameters_dlg import InputParametersDialog
    for cls in (AdvancedSettingsDialog, FrameRangeDialog, InputParametersDialog):
        d = cls()
        d.show()
        app.processEvents()
        d.grab().save(os.path.join(OUT, f"{cls.__name__}.png"))
        d.close()
