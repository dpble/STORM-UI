#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtWidgets import *

import os
import sys
from functools import partial

import xml.etree.ElementTree as ET
from lxml import etree
from .xml_settings import read_settings, save_edits
import yaml 

# configs/XMLs.yml, found relative to this repo (was hardcoded to one lab PC)
XMLS_YML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'configs', 'XMLs.yml')

from .advanced_settings_dlg_ui import * 

from PyQt6 import QtCore, QtGui, QtWidgets

if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

class AdvancedSettingsDialog(QDialog):

    def __init__(self, *args, xml_dir=None, **kwargs):
        """xml_dir: the experiment's XMLs/ folder, the files Test Fit reads.
        Without it, falls back to the paths in configs/XMLs.yml (original behavior)."""
        super(AdvancedSettingsDialog, self).__init__(*args, **kwargs)
        self.xml_dir = xml_dir
        self.loaded = {}

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        # Handle findXML buttons
        self.ui.find488.clicked.connect(partial(self.findXML,
                self.ui.pathLbl488, self.ui.thresh488, 0, None))
        self.ui.find561.clicked.connect(partial(self.findXML,
                self.ui.pathLbl561, self.ui.thresh561, 1, None))
        self.ui.find647.clicked.connect(partial(self.findXML,
                self.ui.pathLbl647, self.ui.thresh647, 2, None))
        self.ui.find750.clicked.connect(partial(self.findXML,
                self.ui.pathLbl750, self.ui.thresh750, 3, None))

        self.ui.updateBtn.clicked.connect(self.updateXML)

        self.labels = [self.ui.pathLbl488, self.ui.pathLbl561,
                       self.ui.pathLbl647, self.ui.pathLbl750]
        self.threshs = [self.ui.thresh488, self.ui.thresh561,
                        self.ui.thresh647, self.ui.thresh750]
        self.sfs = [self.ui.sf488, self.ui.sf561, self.ui.sf647, self.ui.sf750]
        self.efs = [self.ui.ef488, self.ui.ef561, self.ui.ef647, self.ui.ef750]
        self.bss = [self.ui.bs488, self.ui.bs561, self.ui.bs647, self.ui.bs750]
        self.fss = [self.ui.fs488, self.ui.fs561, self.ui.fs647, self.ui.fs750]
        self.psfs = [self.ui.psf488, self.ui.psf561, self.ui.psf647, self.ui.psf750]
        self.checkBoxes = [self.ui.checkBox488, self.ui.checkBox561, self.ui.checkBox647, self.ui.checkBox750]
        
        # Auto-load each channel's XML. The original always used configs/XMLs.yml
        # (placeholder paths), not the experiment's XMLs/ that Test Fit reads, and
        # showed an error popup for every file it could not find.
        with open(XMLS_YML) as f:
            self.config = yaml.safe_load(f)
        for i, ch in enumerate((488, 561, 647, 750)):
            path = os.path.join(xml_dir, f"{ch}.xml") if xml_dir else self.config[ch]
            if os.path.exists(path):
                self.findXML(self.labels[i], self.threshs[i], i, path)
            else:
                self.labels[i].setText("")
                self.labels[i].setToolTip(f"Not found: {path}")
        if xml_dir:
            self.setWindowTitle("Test Parameters: " + xml_dir)

    def findXML(self, label, thresh, channel, fileName=None):
        
        print('pressed') 
        if fileName is None:
            print('NONE') 
            options = QFileDialog.Option(0)  # PyQt6: Options() flag constructor removed
            options |= QFileDialog.Option.DontUseNativeDialog
            (fileName, _) = QFileDialog.getOpenFileName(self,
                    'QFileDialog.getOpenFileName()', '', 'XML Files (*.xml)'
                    , options=options)

        if fileName:
            print(fileName)
            try:
                root = read_settings(fileName).getroot()
                fields = self.fields(channel)
                values = {}
                for name, widget in fields.items():
                    text = root.findtext(name)
                    if text is None:
                        continue
                    values[name] = (bool(int(text)) if name == "drift_correction"
                                    else int(text) if name in ("start_frame", "max_frame")
                                    else float(text))
            except (OSError, ValueError, etree.XMLSyntaxError) as exc:
                QMessageBox.warning(self, "Could not read settings", str(exc))
                return
            label.setText(fileName)
            for name, widget in fields.items():
                widget.setEnabled(name in values)
                if name not in values:
                    continue
                if name == "drift_correction":
                    widget.setChecked(values[name])
                else:
                    widget.setValue(values[name])
            self.loaded[channel] = (fileName, self.field_values(channel))

    def fields(self, i):
        return dict(start_frame=self.sfs[i], max_frame=self.efs[i],
                    background_sigma=self.bss[i], foreground_sigma=self.fss[i],
                    threshold=self.threshs[i], sigma=self.psfs[i], drift_correction=self.checkBoxes[i])

    def field_values(self, i):
        return {name: (str(int(widget.isChecked())) if name == "drift_correction" else str(widget.value()))
                for name, widget in self.fields(i).items() if widget.isEnabled()}

    def updateXML(self):
        if not self.isEnabled():
            return
        edits = []
        for channel, (path, initial) in self.loaded.items():
            changes = {key: value for key, value in self.field_values(channel).items()
                       if value != initial.get(key)}
            if changes:
                edits.append((path, changes))
        try:
            save_edits(edits)
        except (OSError, ValueError, etree.XMLSyntaxError) as exc:
            QMessageBox.warning(self, "Could not save settings", str(exc))
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Settings")
        msg.setText(f"{len(edits)} XML file(s) updated.")
        msg.exec()
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AdvancedSettingsDialog()
    ex.show()
    app.exec()
    sys.exit()
