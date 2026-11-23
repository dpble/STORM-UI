"""
Shared helpers for the analysis pipeline.

- Locates storm-analysis scripts from the installed package (was hardcoded to
  C:/Program Files/Python36/...), and runs them with the current Python.
- run_jobs() replaces storm_analysis.sa_library.batch_run.batchRun, which ignores
  exit codes (a crashed fit still looked like success) and cannot be cancelled.
"""
import os
import subprocess
import sys
import threading
import time

import storm_analysis

SA_DIR = os.path.dirname(os.path.abspath(storm_analysis.__file__))
PYTHON = sys.executable

SCMOS_ANALYSIS = os.path.join(SA_DIR, "sCMOS", "scmos_analysis.py")
HDF5_TO_BIN = os.path.join(SA_DIR, "sa_utilities", "hdf5_to_bin.py")
HDF5_TO_IMAGE = os.path.join(SA_DIR, "sa_utilities", "hdf5_to_image.py")


class PipelineError(Exception):
    pass


class Cancelled(PipelineError):
    pass


def fit_cmd(movie, mlist, xml):
    return [PYTHON, SCMOS_ANALYSIS, "--movie", movie, "--bin", mlist, "--xml", xml]


def run_jobs(cmd_lines, max_processes=2, log=print, cancel_event=None, label="job"):
    """
    Run command lines in parallel, at most max_processes at a time.

    log:          called with each line of output (and status lines).
    cancel_event: threading.Event; when set, running jobs are killed and Cancelled is raised.
    Raises PipelineError listing every job that exited non-zero.
    """
    max_processes = max(1, int(max_processes))
    pending = list(cmd_lines)
    running = []          # (proc, cmd, reader_thread)
    failed = []
    done = 0
    total = len(pending)
    if total == 0:
        log(f"No {label}s to run.")
        return 0

    def reader(proc):
        for line in proc.stdout:
            log(line.rstrip())

    try:
        while pending or running:
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled("Cancelled by user")
            while pending and len(running) < max_processes:
                cmd = pending.pop(0)
                log(f"[{label} {done + len(running) + 1}/{total}] " + " ".join(os.path.basename(c) if c.endswith(".py") else c for c in cmd[1:]))
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, bufsize=1, env=os.environ.copy())
                t = threading.Thread(target=reader, args=(proc,), daemon=True)
                t.start()
                running.append((proc, cmd, t))
            still = []
            for proc, cmd, t in running:
                rc = proc.poll()
                if rc is None:
                    still.append((proc, cmd, t))
                    continue
                t.join(timeout=5)
                done += 1
                if rc != 0:
                    failed.append((cmd, rc))
                    log(f"FAILED (exit {rc}): {' '.join(cmd)}")
            running = still
            time.sleep(0.05)
    except BaseException:
        for proc, _, _ in running:
            if proc.poll() is None:
                proc.kill()
        for proc, _, thread in running:
            proc.wait()
            thread.join(timeout=5)
        raise

    if failed:
        raise PipelineError(f"{len(failed)} of {total} {label}s failed:\n" +
                            "\n".join(f"  exit {rc}: {' '.join(cmd)}" for cmd, rc in failed))
    return total
