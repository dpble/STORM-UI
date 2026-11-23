"""
Dark theme for STORMpro.

Replaces qtmodern.styles.dark(), which only supports PyQt5. qtmodern applied
Qt's Fusion style with a dark palette; this does the same with no extra dependency.
"""
from PyQt6 import QtGui, QtWidgets

R = QtGui.QPalette.ColorRole
G = QtGui.QPalette.ColorGroup


def dark(app):
    app.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    p = QtGui.QPalette()
    c = QtGui.QColor
    p.setColor(R.Window, c(53, 53, 53))
    p.setColor(R.WindowText, c(255, 255, 255))
    p.setColor(R.Base, c(42, 42, 42))
    p.setColor(R.AlternateBase, c(66, 66, 66))
    p.setColor(R.ToolTipBase, c(53, 53, 53))
    p.setColor(R.ToolTipText, c(255, 255, 255))
    p.setColor(R.Text, c(255, 255, 255))
    p.setColor(R.Button, c(53, 53, 53))
    p.setColor(R.ButtonText, c(255, 255, 255))
    p.setColor(R.BrightText, c(255, 0, 0))
    p.setColor(R.Link, c(42, 130, 218))
    p.setColor(R.Highlight, c(42, 130, 218))
    p.setColor(R.HighlightedText, c(255, 255, 255))
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(G.Disabled, role, c(127, 127, 127))
    app.setPalette(p)
