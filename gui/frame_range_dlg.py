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

from .frame_range_dlg_ui import * 
# import frame_range_dlg_ui 

class FrameRangeDialog(QDialog):

    def __init__(self, *args, xml_dir=None, **kwargs):
        super(FrameRangeDialog, self).__init__(*args, **kwargs)
        self.xml_dir = xml_dir
        self.initial = {}

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        # Handle findXML buttons
        self.sfs = [self.ui.sf_spinBox_488, self.ui.sf_spinBox_561,
                       self.ui.sf_spinBox_647, self.ui.sf_spinBox_750]
        self.efs = [self.ui.ef_spinBox_488, self.ui.ef_spinBox_561,
                        self.ui.ef_spinBox_647, self.ui.ef_spinBox_750]

        self.ui.okBtn.clicked.connect(self.send_params)
        self.ui.cancelBtn.clicked.connect(self.cancel)
        
        with open(XMLS_YML) as f:
            self.config = yaml.safe_load(f)
        # Show the values that are in the files now (the original showed defaults).
        for sf, ef, channel in zip(self.sfs, self.efs, [488, 561, 647, 750]):
            path = self.xmlPath(channel)
            if os.path.exists(path):
                root = read_settings(path).getroot()
                for child in root:
                    if child.tag == "start_frame":
                        sf.setValue(int(float(child.text)))
                    if child.tag == "max_frame":
                        ef.setValue(int(float(child.text)))
                self.initial[channel] = (sf.value(), ef.value())
            else:
                sf.setEnabled(False); ef.setEnabled(False)
                sf.setToolTip(f"Not found: {path}"); ef.setToolTip(f"Not found: {path}")
        if xml_dir:
            self.setWindowTitle("Frame Ranges: " + xml_dir)

    def xmlPath(self, channel):
        # The experiment's XMLs/ (what fitting reads), else configs/XMLs.yml.
        if self.xml_dir:
            return os.path.join(self.xml_dir, f"{channel}.xml")
        return self.config[channel]

  
    def send_params(self):
        edits, written, missing = [], [], []
        for sf, ef, channel in zip(self.sfs, self.efs, [488, 561, 647, 750]):
            if channel not in self.initial:
                missing.append(str(channel))
                continue
            changes = {key: str(value) for key, value, initial in
                       zip(("start_frame", "max_frame"), (sf.value(), ef.value()), self.initial[channel])
                       if value != initial}
            if changes:
                edits.append((self.xmlPath(channel), changes))
                written.append(str(channel))
        try:
            save_edits(edits)
        except (OSError, ValueError, etree.XMLSyntaxError) as exc:
            QMessageBox.warning(self, "Could not save frame ranges", str(exc))
            return [], missing
        msg = QMessageBox(self)
        msg.setWindowTitle("Frame ranges")
        text = "Frame ranges saved for " + (", ".join(written) or "no channels") + "."
        if missing:
            text += "\nNo XML file for " + ", ".join(missing) + "."
        msg.setText(text)
        msg.exec()
        self.accept()
        return written, missing

    def cancel(self):
        self.reject()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = FrameRangeDialog()
    ex.show()
    app.exec()
    sys.exit()
