"""
Run pipeline steps off the GUI thread.

The original called the fitting/alignment functions directly from the button
handlers, so the window froze ("Not Responding") for the whole run, which can
be hours for a full data set, and there was no way to stop it.
"""
import re
import threading
import traceback

from PyQt6 import QtCore

try:
    from analysis_scripts.pipeline_utils import Cancelled
except ImportError:                      # bare-import layout (run_dev.sh)
    from pipeline_utils import Cancelled

PROGRESS_RE = re.compile(r"^\[(?P<label>[^\]]+?) (?P<i>\d+)/(?P<n>\d+)\]")


class PipelineWorker(QtCore.QObject):
    """
    Runs `steps`, a list of (name, fn) where fn(log, cancel_event) does the work,
    one after another in a QThread.
    """
    log = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(str, int, int)      # step label, i, n
    step_started = QtCore.pyqtSignal(str)
    succeeded = QtCore.pyqtSignal(object)            # dict of step name -> return value
    failed = QtCore.pyqtSignal(str, str)             # step name, message
    cancelled = QtCore.pyqtSignal()
    done = QtCore.pyqtSignal()                       # always emitted last

    def __init__(self, steps):
        super().__init__()
        self.steps = steps
        self.cancel_event = threading.Event()

    def _log(self, line):
        m = PROGRESS_RE.match(line)
        if m:
            self.progress.emit(m.group("label"), int(m.group("i")), int(m.group("n")))
        self.log.emit(line)

    @QtCore.pyqtSlot()
    def run(self):
        results = {}
        name = ""
        try:
            for name, fn in self.steps:
                if self.cancel_event.is_set():
                    raise Cancelled()
                self.step_started.emit(name)
                self._log(f"=== {name} ===")
                results[name] = fn(self._log, self.cancel_event)
            self.succeeded.emit(results)
        except Cancelled:
            self.log.emit("Cancelled.")
            self.cancelled.emit()
        except Exception as e:                     # report everything, never crash the GUI
            self.log.emit(traceback.format_exc())
            self.failed.emit(name, str(e))
        finally:
            self.done.emit()

    def cancel(self):
        self.cancel_event.set()


def start_worker(owner, steps):
    """Create a worker + thread owned by `owner` (kept alive as attributes)."""
    thread = QtCore.QThread(owner)
    worker = PipelineWorker(steps)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.done.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    owner._worker, owner._worker_thread = worker, thread
    return worker, thread
