"""
Dialog tests: Set Test Parameters and Set Frame Ranges must edit the XML files
that fitting actually reads (the experiment's XMLs/ folder).

Run with:  QT_QPA_PLATFORM=offscreen ./run_dev.sh -m pytest -q tests
"""
import os
import re
import shutil
import sys
import time

import pytest
from PyQt6 import QtCore, QtWidgets

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import make_test_experiment as mte   # noqa: E402

import storm_analysis.sa_library.sa_h5py as saH5Py  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def base_exp(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("dlgexp"))
    mte.make(d, channels=("647",), sections=1, small=True)
    return d


@pytest.fixture
def exp(base_exp, tmp_path):
    d = tmp_path / "e"
    shutil.copytree(base_exp, d)
    return str(d)


@pytest.fixture(autouse=True)
def no_modal_popups(monkeypatch):
    # Success popups use exec(); don't block the test.
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)


@pytest.fixture
def win(app, exp):
    import main
    w = main.Window(directory=REPO)
    w.show()
    w.setExperimentFolder(exp)
    app.processEvents()
    yield w
    w.close()


def xml_value(path, tag):
    return re.search(rf"<{tag} type=\"\w+\">([^<]+)<", open(path, encoding="latin-1").read()).group(1)


def visible(cls):
    return [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, cls) and w.isVisible()]


def test_test_parameters_loads_experiment_xmls(win, app, exp):
    from gui.advanced_settings_dlg import AdvancedSettingsDialog
    win.open_input_parameters_dlg()
    app.processEvents()
    d = win.input_parameters_dlg
    assert d.ui.pathLbl647.text() == os.path.join(exp, "XMLs", "647.xml")
    assert d.ui.sf647.value() == 0 and d.ui.ef647.value() == 50      # from the lab 647.xml
    assert d.ui.thresh647.value() == pytest.approx(14.0)
    # no "Please enter valid file path!" popups on open
    assert not visible(QtWidgets.QErrorMessage)
    d.close()


def test_changed_threshold_is_used_by_test_fit(win, app, exp):
    """The whole point of the dialog: edit a parameter, test fit with it."""
    from pathlib import Path
    def run_fit():
        root = Path(exp) / "acquisition" / "test_fits"
        previous = set(root.glob("run-*"))
        win.ui.checkBox647.setChecked(True)
        win.ui.fit_frame_select.setValue(0)
        win.ui.fit_btn.click()
        t0 = time.time()
        while win.isBusy() and time.time() - t0 < 120:
            app.processEvents(); time.sleep(0.02)
        assert not win.isBusy(), "Test Fit did not finish"
        assert win.progress_bar.format() == "Test fit done", win.log_view.toPlainText()
        h5 = str(next(iter(set(root.glob("run-*")) - previous)) / "647storm_00_mlist.hdf5")
        with saH5Py.SAH5Reader(h5) as f:
            return f.getNLocalizations(), h5

    before, first_h5 = run_fit()
    win.open_input_parameters_dlg()
    d = win.input_parameters_dlg
    d.ui.ef647.setValue(20)                     # fit frames 0..20 instead of 0..50
    d.ui.thresh647.setValue(30.0)
    d.updateXML()
    xml = os.path.join(exp, "XMLs", "647.xml")
    assert xml_value(xml, "max_frame") == "20"
    assert float(xml_value(xml, "threshold")) == 30.0
    after, h5 = run_fit()
    assert h5 != first_h5 and os.path.exists(first_h5)
    with saH5Py.SAH5Reader(h5) as f:
        frames = sorted({fn for fn, locs in f.localizationsIterator(fields=["x"]) if locs["x"].size})
    assert frames[-1] < 20, frames[-1]              # the new frame range was used
    assert before > 2500 and after < before * 0.5, (before, after)


def test_frame_range_prefilled_and_saved(win, app, exp):
    from gui.frame_range_dlg import FrameRangeDialog
    QtCore.QTimer.singleShot(200, lambda: _set_and_ok(app))
    win.open_frame_range_dlg()
    app.processEvents()
    xml = os.path.join(exp, "XMLs", "647.xml")
    assert xml_value(xml, "start_frame") == "5" and xml_value(xml, "max_frame") == "30"
    # Original called show() after exec(), so the dialog came back after OK.
    assert not visible(FrameRangeDialog)


def _set_and_ok(app):
    from gui.frame_range_dlg import FrameRangeDialog
    for d in visible(FrameRangeDialog):
        assert d.ui.ef_spinBox_647.value() == 50          # prefilled from the file
        d.ui.sf_spinBox_647.setValue(5)
        d.ui.ef_spinBox_647.setValue(30)
        d.ui.okBtn.click()


def test_frame_range_missing_channel_does_not_stop_halfway(app, exp):
    from gui.frame_range_dlg import FrameRangeDialog
    os.remove(os.path.join(exp, "XMLs", "561.xml"))
    d = FrameRangeDialog(xml_dir=os.path.join(exp, "XMLs"))
    assert not d.ui.sf_spinBox_561.isEnabled()
    d.ui.sf_spinBox_750.setValue(3)
    written, missing = d.send_params()
    assert missing == ["561"]
    assert written == ["750"]  # only changed XML is saved
    assert xml_value(os.path.join(exp, "XMLs", "750.xml"), "start_frame") == "3"


def test_dialogs_without_experiment_fall_back_quietly(app):
    from gui.advanced_settings_dlg import AdvancedSettingsDialog
    from gui.frame_range_dlg import FrameRangeDialog
    a = AdvancedSettingsDialog()          # configs/XMLs.yml placeholder paths
    f = FrameRangeDialog()
    app.processEvents()
    assert not visible(QtWidgets.QErrorMessage)
    a.close(); f.close()


def test_edit_preserves_unedited_xml_and_precision(win, app, exp):
    from pathlib import Path
    xmls = Path(exp) / "XMLs"
    other = xmls / "750.xml"
    old = other.read_bytes()
    xml = xmls / "647.xml"
    xml.write_bytes(xml.read_bytes().replace(b'>14.0</threshold>', b'>14.1234567</threshold>'))
    assert xml_value(str(xml), "threshold") == "14.1234567"
    win.open_input_parameters_dlg()
    d = win.input_parameters_dlg
    d.ui.ef647.setValue(20)
    d.updateXML()
    assert xml_value(str(xml), "threshold") == "14.1234567"
    assert xml_value(str(xml), "max_frame") == "20"
    assert other.read_bytes() == old


def test_invalid_later_xml_leaves_all_originals_untouched(tmp_path):
    from gui.xml_settings import save_edits
    a, b = tmp_path / "a.xml", tmp_path / "b.xml"
    a.write_bytes(b"<settings><start_frame>0</start_frame><max_frame>50</max_frame></settings>")
    b.write_bytes(a.read_bytes())
    old = a.read_bytes()
    with pytest.raises(ValueError):
        save_edits([(a, {"start_frame": "5"}), (b, {"start_frame": "60"})])
    assert a.read_bytes() == b.read_bytes() == old
    assert len(list(tmp_path.iterdir())) == 2


def test_duplicate_xml_targets_are_rejected(tmp_path):
    from gui.xml_settings import save_edits
    xml = tmp_path / "settings.xml"
    data = b"<settings><start_frame>0</start_frame><max_frame>50</max_frame></settings>"
    xml.write_bytes(data)
    with pytest.raises(ValueError, match="only once"):
        save_edits([(xml, {"start_frame": "5"}), (xml, {"max_frame": "20"})])
    assert xml.read_bytes() == data


def test_xml_replace_error_reports_applied_files(tmp_path, monkeypatch):
    from gui import xml_settings
    a, b = tmp_path / "a.xml", tmp_path / "b.xml"
    for path in (a, b):
        path.write_bytes(b"<settings><start_frame>0</start_frame></settings>")
    replace = os.replace
    def fail_second(src, dst):
        if dst == b:
            raise PermissionError("file locked")
        replace(src, dst)
    monkeypatch.setattr(xml_settings.os, "replace", fail_second)
    with pytest.raises(OSError, match="Already saved: .*a.xml"):
        xml_settings.save_edits([(a, {"start_frame": "1"}), (b, {"start_frame": "2"})])
    assert b">1<" in a.read_bytes()
    assert b">0<" in b.read_bytes()


def test_invalid_or_duplicate_parameters_disable_only_that_channel(app, exp):
    from pathlib import Path
    from gui.frame_range_dlg import FrameRangeDialog
    root = Path(exp) / "XMLs"
    (root / "647.xml").write_text("<settings><start_frame>not-a-number</start_frame></settings>")
    (root / "750.xml").write_text("<settings><start_frame>0</start_frame><start_frame>2</start_frame></settings>")
    editor = FrameRangeDialog(xml_dir=str(root))
    assert not editor.ui.sf_spinBox_647.isEnabled()
    assert not editor.ui.sf_spinBox_750.isEnabled()
    assert editor.ui.sf_spinBox_488.isEnabled()


def test_stale_xml_version_is_refused(tmp_path):
    from gui.xml_settings import fingerprint, save_edits
    xml = tmp_path / "647.xml"
    old = b"<settings><start_frame>0</start_frame></settings>"
    xml.write_bytes(old)
    version = fingerprint(xml)
    changed = old.replace(b">0<", b">3<")
    xml.write_bytes(changed)
    with pytest.raises(ValueError, match="changed since it was opened"):
        save_edits([(xml, {"start_frame": "2"})], {xml: version})
    assert xml.read_bytes() == changed
