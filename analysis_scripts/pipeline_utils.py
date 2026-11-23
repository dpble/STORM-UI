"""
Shared helpers for the analysis pipeline.

- Locates storm-analysis scripts from the installed package (was hardcoded to
  C:/Program Files/Python36/...), and runs them with the current Python.
- run_jobs() replaces storm_analysis.sa_library.batch_run.batchRun, which ignores
  exit codes (a crashed fit still looked like success) and cannot be cancelled.
"""
import os
import json
from pathlib import Path
from lxml import etree
import subprocess
import sys
import threading
import time

import storm_analysis
from storm_analysis.sa_library import datareader, sa_h5py

SA_DIR = os.path.dirname(os.path.abspath(storm_analysis.__file__))
PYTHON = sys.executable

SCMOS_ANALYSIS = os.path.join(SA_DIR, "sCMOS", "scmos_analysis.py")
HDF5_TO_BIN = os.path.join(SA_DIR, "sa_utilities", "hdf5_to_bin.py")
HDF5_TO_IMAGE = os.path.join(SA_DIR, "sa_utilities", "hdf5_to_image.py")


class PipelineError(Exception):
    pass


class Cancelled(PipelineError):
    pass


def read_fit_xml(source):
    tree = etree.parse(str(source), etree.XMLParser(resolve_entities=False, no_network=True))
    names = set()
    for node in tree.getroot():
        if not isinstance(node.tag, str):
            continue
        if node.tag in names:
            raise ValueError(f"{source}: duplicate parameter {node.tag}")
        names.add(node.tag)
    return tree


def check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled("Cancelled by user")


def plan_fit(movie, output, xml, log, cancel_event):
    check_cancel(cancel_event)
    try:
        reader = datareader.inferReader(movie)
        try:
            _, _, length = reader.filmSize()
        finally:
            reader.close()
        root = read_fit_xml(xml).getroot()
        start = max(0, int(root.findtext("start_frame", "0")))
        limit = int(root.findtext("max_frame", "0"))
    except Exception as exc:
        raise PipelineError(f"Could not validate {movie}: {exc}") from exc
    stop = length if limit <= 0 else min(limit, length)
    if not 0 <= start < stop:
        raise PipelineError(f"Invalid frame range for {movie}: start {start}, end {limit}, movie length {length}")
    if limit > length:
        log(f"{Path(movie).name}: end frame {limit} clipped to movie length {length}")
    return dict(movie=str(movie), output=str(output), xml=str(xml), start=start, stop=stop)


def verify_fits(records, cancel_event):
    for record in records:
        check_cancel(cancel_event)
        path = record["output"]
        try:
            with sa_h5py.SAH5Reader(path) as reader:
                if not reader.isAnalysisFinished():
                    raise ValueError("analysis is marked unfinished")
                for frame in range(record["start"], record["stop"]):
                    if not reader.isAnalyzed(frame):
                        raise ValueError(f"frame {frame} was not analyzed")
                    if frame % 256 == 0:
                        check_cancel(cancel_event)
        except Cancelled:
            raise
        except Exception as exc:
            raise PipelineError(f"Incomplete fit {path}: {exc}") from exc


def verify_artifacts(paths):
    from storm_analysis.sa_library.readinsight3 import checkStatus
    from tifffile import TiffFile
    for path in map(Path, paths):
        try:
            if path.suffix == ".bin":
                if not checkStatus(str(path)):
                    raise ValueError("invalid Insight3 header")
            else:
                with TiffFile(path) as tiff:
                    if not tiff.pages or not all(tiff.pages[0].shape):
                        raise ValueError("empty TIFF")
        except Exception as exc:
            raise PipelineError(f"Unreadable result {path}: {exc}") from exc


def write_manifest(stage, records):
    stage = Path(stage)
    portable = [dict(record, output=Path(record["output"]).relative_to(stage).as_posix(),
                     xml=Path(record["xml"]).relative_to(stage).as_posix()) for record in records]
    (stage / "run.json").write_text(json.dumps(portable, indent=2), encoding="utf-8")


class FitSettingsSnapshot:
    """Capture the XML and its referenced input files before starting fit jobs."""

    def __init__(self, directory, cancel_event=None):
        self.cancel_event = cancel_event
        self.directory = Path(directory)
        self.directory.mkdir()
        self.xmls = {}
        self.inputs = {}

    def copy(self, filename):
        check_cancel(self.cancel_event)
        source = Path(os.path.abspath(filename))
        if source in self.xmls:
            return self.xmls[source]
        try:
            tree = read_fit_xml(source)
        except (OSError, ValueError, etree.XMLSyntaxError) as exc:
            raise PipelineError(f"Reading fit settings failed: {source}: {exc}") from exc
        for node in tree.getroot():
            if node.get("type") != "filename" or not (node.text or "").strip():
                continue
            check_cancel(self.cancel_event)
            original = (source.parent / node.text).resolve()
            if original not in self.inputs:
                dest = self.directory / f"input-{len(self.inputs)}-{original.name}"
                with original.open("rb") as src, dest.open("wb") as out:
                    while chunk := src.read(1024 * 1024):
                        check_cancel(self.cancel_event)
                        out.write(chunk)
                self.inputs[original] = dest
            node.text = self.inputs[original].name
        result = self.directory / f"settings-{len(self.xmls)}-{source.name}"
        tree.write(str(result), encoding="UTF-8", xml_declaration=True)
        self.xmls[source] = str(result)
        return str(result)


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
                check_cancel(cancel_event)
                cmd = pending.pop(0)
                log(f"[{label} {done + len(running) + 1}/{total}] " + " ".join(os.path.basename(c) if c.endswith(".py") else c for c in cmd[1:]))
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, bufsize=1, env=os.environ.copy())
                t = threading.Thread(target=reader, args=(proc,), daemon=True)
                running.append((proc, cmd, t))
                t.start()
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
            if thread.ident is not None:
                thread.join(timeout=5)
        raise

    if failed:
        raise PipelineError(f"{len(failed)} of {total} {label}s failed:\n" +
                            "\n".join(f"  exit {rc}: {' '.join(cmd)}" for cmd, rc in failed))
    return total
