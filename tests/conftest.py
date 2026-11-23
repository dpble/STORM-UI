"""
Test setup shared by every test file.

The app saves its settings (contrast, folder, window position) when a window
closes. Without this, the tests wrote into the real user's settings, and values
left by one test run changed the next one.
"""
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore  # noqa: E402

_SETTINGS_DIR = tempfile.mkdtemp(prefix="stormpro-test-settings-")
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,
                         QtCore.QSettings.Scope.UserScope, _SETTINGS_DIR)

os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"), exist_ok=True)
