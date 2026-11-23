"""Stage XML edits beside their originals; leave unedited files untouched."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from analysis_scripts.pipeline_utils import read_fit_xml


def read_settings(path):
    return read_fit_xml(path)


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_edits(edits, expected_versions=None):
    expected_versions = expected_versions or {}
    staged = []
    targets = set()
    applied = []
    try:
        for filename, changes in edits:
            path = Path(filename).resolve(strict=True)
            if path in targets:
                raise ValueError(f"More than one edit targets {path}. Select each XML only once.")
            targets.add(path)
            if filename in expected_versions and fingerprint(path) != expected_versions[filename]:
                raise ValueError(f"{filename} changed since it was opened. Close and reload the editor.")
            tree = read_settings(path)
            for key, text in changes.items():
                node = tree.find(key)
                if node is None:
                    raise ValueError(f"{path.name} has no {key} setting")
                node.text = text
            if changes.keys() & {"start_frame", "max_frame"}:
                start = int(tree.findtext("start_frame", "0"))
                end = int(tree.findtext("max_frame", "0"))
                if start < 0 or (end > 0 and end <= start):
                    raise ValueError(f"{path.name}: end frame must be after start frame, or 0 for the full movie.")
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".settings-", delete=False) as temp:
                staged.append((temp.name, path))
                tree.write(temp, encoding=tree.docinfo.encoding or "UTF-8", xml_declaration=True)
            shutil.copymode(path, temp.name)
        for temp, path in staged:
            try:
                os.replace(temp, path)
            except OSError as exc:
                saved = ", ".join(str(item) for item in applied) or "none"
                raise OSError(f"Could not replace {path}. Already saved: {saved}. {exc}") from exc
            applied.append(path)
    finally:
        for temp, _ in staged:
            Path(temp).unlink(missing_ok=True)
