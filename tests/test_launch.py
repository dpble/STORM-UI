import os
from pathlib import Path
import subprocess
import sys


def test_app_starts_without_custom_pythonpath(tmp_path):
    entry = Path(__file__).resolve().parents[1] / "main.py"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("PYTHONPATH", None)
    probe = '''
import runpy
import sys
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, '.')
app = QApplication([])
namespace = runpy.run_path(sys.argv[1])
window = namespace['Window']()
window.show()
app.processEvents()
assert window.isVisible()
'''
    # Script execution automatically puts the script directory on sys.path.
    # Mirror that in this bounded probe so it need not enter the GUI event loop.
    probe = "import os, sys; sys.path.insert(0, os.path.dirname(sys.argv[1]))\n" + probe
    result = subprocess.run([sys.executable, "-c", probe, str(entry)], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
