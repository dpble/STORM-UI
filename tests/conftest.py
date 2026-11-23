"""
Test setup shared by every test file.

The app saves its settings (contrast, folder, window position) when a window
closes. Without this, the tests wrote into the real user's settings, and values
left by one test run changed the next one.
"""
import os
import sys
import tempfile

# Same import path run_dev.sh sets up (the lab PC had these on PYTHONPATH), done
# here so the tests also run on Windows and in CI without the bash script.
import storm_analysis

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SA = os.path.dirname(os.path.abspath(storm_analysis.__file__))
for p in (_REPO, os.path.join(_REPO, "analysis_scripts"), os.path.join(_SA, "sa_library"), _SA):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="stormpro-test-settings-")
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,
                         QtCore.QSettings.Scope.UserScope, _SETTINGS_DIR)

os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"), exist_ok=True)
