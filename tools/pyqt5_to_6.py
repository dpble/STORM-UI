"""
One-off PyQt5 -> PyQt6 converter for STORM-UI.

The big PyQt6 change is scoped enums: Qt.AlignLeft becomes Qt.AlignmentFlag.AlignLeft.
Rather than a hand-written lookup table, this asks PyQt6 itself: for every
`<Class>.<Name>` where <Name> is no longer an attribute of <Class>, it searches
<Class>'s nested enums for <Name> and rewrites to `<Class>.<Enum>.<Name>`.

Prints every rewrite and every name it could not resolve, so nothing changes silently.
Usage: python tools/pyqt5_to_6.py file1.py file2.py ...
"""
import enum
import re
import sys
from collections import Counter

from PyQt6 import QtCore, QtGui, QtWidgets

MODULES = {"QtCore": QtCore, "QtGui": QtGui, "QtWidgets": QtWidgets}

# Classes that moved module between Qt5 and Qt6.
MOVED = {"QtWidgets.QAction": "QtGui.QAction",
         "QtWidgets.QShortcut": "QtGui.QShortcut",
         "QtWidgets.QActionGroup": "QtGui.QActionGroup"}

# `[QtCore.|QtGui.|QtWidgets.]<Class>.<Name>` (Class is Qt or Q-something)
PAT = re.compile(r"\b((?:QtCore|QtGui|QtWidgets)\.)?(Qt|Q[A-Z]\w*)\.([A-Za-z]\w*)\b")


def find_class(mod_prefix, cls_name):
    mods = [MODULES[mod_prefix.rstrip(".")]] if mod_prefix else MODULES.values()
    for m in mods:
        if hasattr(m, cls_name):
            return getattr(m, cls_name)
    return None


def find_enum(cls, name):
    for attr in dir(cls):
        obj = getattr(cls, attr, None)
        if isinstance(obj, type) and issubclass(obj, enum.Enum) and name in obj.__members__:
            return attr
    return None


def convert(src, stats, unresolved):
    for old, new in MOVED.items():
        if old in src:
            stats[f"{old} -> {new}"] += src.count(old)
            src = src.replace(old, new)

    def repl(m):
        prefix, cls_name, name = m.group(1) or "", m.group(2), m.group(3)
        cls = find_class(prefix, cls_name)
        if cls is None:
            return m.group(0)
        if hasattr(cls, name):          # still valid in PyQt6 (method, nested class, enum type)
            return m.group(0)
        e = find_enum(cls, name)
        if e is None:
            unresolved[f"{prefix}{cls_name}.{name}"] += 1
            return m.group(0)
        stats[f"{cls_name}.{name} -> {cls_name}.{e}.{name}"] += 1
        return f"{prefix}{cls_name}.{e}.{name}"

    src = PAT.sub(repl, src)

    n = len(re.findall(r"\.exec_\(", src))
    if n:
        stats["exec_() -> exec()"] += n
        src = re.sub(r"\.exec_\(", ".exec(", src)
    n = src.count("PyQt5")
    if n:
        stats["PyQt5 -> PyQt6"] += n
        src = src.replace("PyQt5", "PyQt6")
    return src


if __name__ == "__main__":
    total = Counter()
    for path in sys.argv[1:]:
        raw = open(path, "rb").read()
        crlf = b"\r\n" in raw
        src = raw.decode("utf-8").replace("\r\n", "\n")
        stats, unresolved = Counter(), Counter()
        out = convert(src, stats, unresolved)
        if crlf:
            out = out.replace("\n", "\r\n")   # keep the file's original line endings
        open(path, "wb").write(out.encode("utf-8"))
        print(f"\n== {path}: {sum(stats.values())} rewrites")
        for k, v in sorted(stats.items()):
            print(f"   {v:3d}  {k}")
        for k, v in unresolved.items():
            print(f"   UNRESOLVED {v}x {k}")
        total += stats
    print(f"\nTOTAL rewrites: {sum(total.values())}")
