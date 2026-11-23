#!/usr/bin/env python
"""
Utility for visualizing quality of peak finding.
Hazen 05/13
main
"""

import numpy
import os
import sys

from functools import partial
import shutil 
import glob 
import numpy as np 

from gui import dark_theme as styles  # replaces qtmodern (PyQt5 only)

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QT_VERSION_STR
from PyQt6.QtGui import QImage, QPixmap, QPainterPath
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QFileDialog


import storm_analysis.sa_library.datareader as datareader
import storm_analysis.sa_library.i3dtype as i3dtype
import storm_analysis.sa_library.readinsight3 as readinsight3
import storm_analysis.sa_library.sa_h5py as saH5Py

# Imports for the UI
import gui.GUI_ui as gui_UI

# Inports for Dialogs
from gui.input_parameters_dlg import InputParametersDialog
from gui.frame_range_dlg import FrameRangeDialog
from gui.advanced_settings_dlg import AdvancedSettingsDialog

from gui import qtRangeSlider
from gui.layout import apply_layout, show_help
from gui.pipeline_worker import start_worker 

# Pipeline Imports 
from analysis_scripts import fitting_parameters_evaluation as fitting_func 
from analysis_scripts import scmos_batch_fitting as scmos_func

# Makes sure the GUI looks normal 
if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)


class InfoTable(QtWidgets.QWidget):
    """
    Handle Info Table.
    """

    def __init__(self, table_widget = None, **kwds):
        super(InfoTable, self).__init__(**kwds)

        self.fields = None
        self.table_widget = table_widget

        # Setup info table.
        self.table_widget.setColumnCount(2)

    def hideFields(self):
        self.table_widget.setRowCount(0)

    def showFields(self, fields):
        self.fields = fields
        self.table_widget.setRowCount(len(fields))
        for i, field in enumerate(fields):
            widget = QtWidgets.QTableWidgetItem(field)
            widget.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table_widget.setItem(i,0,widget)
            widget = QtWidgets.QTableWidgetItem("na")
            widget.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table_widget.setItem(i,1,widget)
        self.table_widget.resizeColumnToContents(0)

    def update(self, properties):
        if bool(properties):
            for i, field in enumerate(self.fields):
                val = "na"
                if (field in properties):
                    if isinstance(properties[field], np.int32):
                        val = str(properties[field])
                    else:
                        val = "{0:.3f}".format(properties[field])
                self.table_widget.item(i,1).setText(val)


class MoleculeItem(QtWidgets.QGraphicsEllipseItem):
    """
    Molecule item for the graphics scene.
    """
    def __init__(self, x, y, w, h, mtype):

        if (mtype == "l2"):
            self.pen = QtGui.QPen(QtGui.QColor(255,0,255))
            self.pen.setWidthF(0.4)
            self.sel_pen = QtGui.QPen(QtGui.QColor(255,100,200))
            self.sel_pen.setWidthF(0.4)
        else:
            self.pen = QtGui.QPen(QtGui.QColor(0,255,0))
            self.pen.setWidthF(0.6)
            self.sel_pen = QtGui.QPen(QtGui.QColor(100,255,200))
            self.sel_pen.setWidthF(0.6)

        x = x - 0.5*w - 0.5
        y = y - 0.5*h - 0.5
        QtWidgets.QGraphicsEllipseItem.__init__(self, x, y, w, h)
        self.setPen(self.pen)

    def setMarked(self, marked):
        if marked:
            self.setPen(self.sel_pen)
        else:
            self.setPen(self.pen)


class MoleculeList(object):
    """
    Handle molecule list.
    """
    def __init__(self, mtype = None, **kwds):
        super(MoleculeList, self).__init__(**kwds)

        self.fields = []
        self.last_frame = -1
        self.last_index = 0
        self.locs = {}
        self.mol_items = []
        self.mtype = mtype
        self.reader = None

    def clearLocs(self):
        self.last_index = 0
        self.locs = {}
        self.mol_items = []

    def createMolItems(self, frame_number, nm_per_pixel):
        self.clearLocs()
        self.locs = self.loadLocalizations(frame_number, nm_per_pixel)
        if bool(self.locs):
            if "xsigma" in self.locs:
                xs = self.locs["xsigma"]
                ys = self.locs["ysigma"]
            else:
                xs = 1.5*np.ones(self.locs["x"].size)
                ys = 1.5*np.ones(self.locs["x"].size)
            for i in range(self.locs["x"].size):
                self.mol_items.append(MoleculeItem(self.locs["x"][i] + 1,
                                                   self.locs["y"][i] + 1,
                                                   xs[i]*6.0,
                                                   ys[i]*6.0,
                                                   self.mtype))
        return self.mol_items

    def getClosest(self, px, py):
        """
        Return a dictionary with information about the closest localization
        to px, py.
        """
        vals = {}
        if bool(self.locs) and (self.locs["x"].size > 0):

            # Find the one nearest to px, py.
            dx = self.locs["x"] - px - 0.5
            dy = self.locs["y"] - py - 0.5
            dist = dx*dx+dy*dy
            closest_index = np.argmin(dist)

            # Unmark old item, mark new item
            self.mol_items[self.last_index].setMarked(False)
            self.mol_items[closest_index].setMarked(True)
            self.last_index = closest_index

            # Create a dictionary containing the data for this molecule.
            vals = {}
            for field in self.locs:
                vals[field] = self.locs[field][closest_index]

        return vals

    def getFields(self):
        return self.fields


class MoleculeListHDF5(MoleculeList):
    """
    Handle HDF5 molecule list.
    """
    def __init__(self, filename = None, **kwds):
        super(MoleculeListHDF5, self).__init__(**kwds)

        self.fields = ["x",
                       "y",
                       "z",
                       "background",
                       "error",
                       "height",
                       "sum",
                       "xsigma",
                       "ysigma",
                       "category",
                       "iterations",
                       "significance"]

        self.filename = filename

    def cleanUp(self):
        # There is no persistent file handle to close.
        pass

    def loadLocalizations(self, frame_number, nm_per_pixel):
        # A persistent HDF5 handle prevents Windows from replacing a Test Fit
        # result on rerun. Read the frame, then release the handle immediately.
        with saH5Py.SAH5Reader(self.filename) as reader:
            locs = reader.getLocalizationsInFrame(frame_number)
        if bool(locs):
            if ("xsigma" in locs) and (not "ysigma" in locs):
                locs["ysigma"] = locs["xsigma"]
        return locs


class MoleculeListI3(MoleculeList):
    """
    Handle Insight3 molecule list.
    """
    def __init__(self, filename = None, **kwds):
        super(MoleculeListI3, self).__init__(**kwds)

        self.fields = ["x",
                       "y",
                       "z",
                       "background",
                       "error",
                       "height",
                       "sum",
                       "xsigma",
                       "ysigma"]

        self.filename = filename
        self.reader = readinsight3.I3Reader(filename)

        self.n_locs = self.reader.getNumberMolecules()

    def cleanUp(self):
        self.reader.close()

    def loadLocalizations(self, frame_number, nm_per_pixel):
        if (self.n_locs > 0):
            fnum = frame_number + 1
            i3data = self.reader.getMoleculesInFrame(fnum)
            return i3dtype.convertToSAHDF5(i3data, fnum, nm_per_pixel)
        else:
            return {}


class MovieView(QtWidgets.QGraphicsView):
    """
    Movie view window.
    """

    #key_press = QtCore.pyqtSignal(object)
    mouse_press = QtCore.pyqtSignal(float, float, name='mousePress')
    leftMouseButtonPressed = pyqtSignal(float, float)
    leftMouseButtonReleased = pyqtSignal(float, float)
    dragged = QtCore.pyqtSignal(str)
    dropped = QtCore.pyqtSignal(str)
    region_selected = QtCore.pyqtSignal(QtCore.QRectF)   # Shift+drag box, scene coords


    def __init__(self, xyi_label = None, **kwds):
        super(MovieView, self).__init__(**kwds)

        # Class variables.
        self.data = False
        self.image = False
        self.margin = 128.0
        self.xyi_label = xyi_label
        self.zoom_in = 1.2
        self.zoom_out = 1.0/self.zoom_in

        # UI initializiation.
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding,
                                           QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizePolicy)
        self.setMinimumSize(QtCore.QSize(200, 200))
        
        # Scroll Bar Behavior 
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Scene initialization.
        self.scene = QtWidgets.QGraphicsScene()
        self.setScene(self.scene)
        self.setMouseTracking(True)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.scale(2.0, 2.0)

        # Shift+drag draws a box: zoom to it and set contrast from it.
        self._rubber_rect = None
        self._box_mode = False
        self.rubberBandChanged.connect(self._onRubberBand)
        
        # Tooltip.
        self.setToolTip("Frames: . and ,  (L / K: 200)  Home / End\n"
                        "Wheel: zoom   Drag: pan   Shift+drag: zoom to box + contrast\n"
                        "A: auto contrast   R: reset zoom")
       
        # Drag and Drop Functionality 
        self.setAcceptDrops(True)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            

    def dragMoveEvent(self, event):
        pass 
        
    @staticmethod
    def droppedPath(mime):
        # Use Qt's URL -> local path conversion. The old text()[8:] cut off
        # 'file:///' and only gave a valid path on Windows (it dropped the
        # leading '/' on Mac and Linux).
        if mime.hasUrls() and mime.urls()[0].isLocalFile():
            return mime.urls()[0].toLocalFile()
        return None

    def dragEnterEvent(self, event):
        path = self.droppedPath(event.mimeData())
        if path and path.endswith(('.hdf5', '.bin', 'tif', 'dax', 'fits', 'spe')):
            event.setAccepted(True)
        else:
            event.ignore()
        
    def dropEvent(self, event):
        path = self.droppedPath(event.mimeData())
        if path:
            self.dropped.emit(path)
 # 
       
    def keyPressEvent(self, event):
        # This allows keyboard scrolling to work.
        QtWidgets.QGraphicsView.keyPressEvent(self, event)

        # This allows us to scroll through the movie.
        # self.key_press.emit(event)

    def mouseMoveEvent(self, event):
        pointf = self.mapToScene(event.pos())
        x = pointf.x()
        y = pointf.y()
        i = 0
        if (type(self.data) == type(np.array([]))):
            [sy, sx] = self.data.shape
            if ((x>=0) and (x<sx) and (y>=0) and (y<sy)):
                i = int(self.data[int(y), int(x)])
        self.xyi_label.setText("{0:.2f}, {1:.2f}, {2:d}".format(x - 0.5, y - 0.5, i))
        # Pass the event on. Without this, Qt never saw the drag, so panning with
        # the mouse (ScrollHandDrag) did nothing, and neither could a selection box.
        QGraphicsView.mouseMoveEvent(self, event)

    def mousePressEvent(self, event):
        if (event.button() == QtCore.Qt.MouseButton.LeftButton):
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self._box_mode = True
                self._rubber_rect = None
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            else:
                self._box_mode = False
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            scenePos = self.mapToScene(event.pos())
            self.mouse_press.emit(scenePos.x(), scenePos.y())
            self.leftMouseButtonPressed.emit(scenePos.x(), scenePos.y())
        QGraphicsView.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        """ Stop mouse pan, or finish a Shift+drag box (zoom to it).
        """
        QGraphicsView.mouseReleaseEvent(self, event)
        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            if self._box_mode and self._rubber_rect is not None \
                    and self._rubber_rect.width() > 2 and self._rubber_rect.height() > 2:
                rect = self._rubber_rect
                self.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                self.region_selected.emit(rect)
            self._box_mode = False
            self._rubber_rect = None
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.leftMouseButtonReleased.emit(scenePos.x(), scenePos.y())

    def _onRubberBand(self, view_rect, from_scene, to_scene):
        # Qt sends an empty rect when the drag ends, so remember the last real one.
        if not view_rect.isNull():
            self._rubber_rect = QtCore.QRectF(from_scene, to_scene).normalized()

    def resetZoom(self):
        if isinstance(self.data, np.ndarray):
            h, w = self.data.shape
            self.fitInView(QtCore.QRectF(0, 0, w, h), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def newFrame(self, frame, locs1, locs2, fmin, fmax):
        self.scene.clear()

        ## process image
        # save image
        self.data = frame.copy()

        # scale image.
        frame = 255.0*(frame-fmin)/(fmax-fmin)
        frame[(frame > 255.0)] = 255.0
        frame[(frame < 0.0)] = 0.0

        # convert to QImage.
        frame = np.ascontiguousarray(frame.astype(np.uint8))
        h, w = frame.shape
        frame_RGB = np.zeros((frame.shape[0], frame.shape[1], 4), dtype = np.uint8)
        frame_RGB[:,:,0] = frame
        frame_RGB[:,:,1] = frame
        frame_RGB[:,:,2] = frame
        frame_RGB[:,:,3] = 255

        self.image = QtGui.QImage(frame_RGB.data, w, h, QtGui.QImage.Format.Format_RGB32)
        self.image.ndarray1 = frame
        self.image.ndarray2 = frame_RGB

        # add to scene
        self.scene.addPixmap(QtGui.QPixmap.fromImage(self.image))

        # add localizations from file 1
        for loc in locs1:
            self.scene.addItem(loc)

        # add localizations from file 2
        for loc in locs2:
            self.scene.addItem(loc)

    def wheelEvent(self, event):
        if not event.angleDelta().isNull():
            if (event.angleDelta().y() > 0):
                self.zoomIn()
            else:
                self.zoomOut()

            # This blocks propogation to the main window where the
            # same event will cause the frame number to change.
            event.accept()

    def zoomIn(self):
        self.scale(self.zoom_in, self.zoom_in)

    def zoomOut(self):
        self.scale(self.zoom_out, self.zoom_out)

class Window(QtWidgets.QMainWindow):
    """
    Main window.
    """

    def __init__(self, directory = None, **kwds):
        super(Window, self).__init__(**kwds)

        # variables
        self.cur_frame = 0
        self.directory = ""
        self.film_l = 0
        self.film_x = 255
        self.film_y = 255
        self.locs1_list = None
        self.locs2_list = None
        self.movie_file = None
        self.settings = QtCore.QSettings(QtCore.QSettings.defaultFormat(), QtCore.QSettings.Scope.UserScope,
                                         "Speer Lab", "Image Analysis")  # default format so tests can redirect it

        self.locs_display_timer = QtCore.QTimer(self)
        self.locs_display_timer.setInterval(100)
        self.locs_display_timer.setSingleShot(True)
        self.locs_display_timer.timeout.connect(self.handleLocsDisplayTimer)

        # ui setup
        self.ui = gui_UI.Ui_MainWindow()
        self.ui.setupUi(self)

        # initialize info tables
        self.locs1_table = InfoTable(table_widget = self.ui.locs1TableWidget)
        self.locs2_table = InfoTable(table_widget = self.ui.locs2TableWidget)

        # initialize movie viewing tab.
        self.movie_view = MovieView(xyi_label = self.ui.xyiLabel, parent = self.ui.movieGroupBox)
        movie_layout = QtWidgets.QGridLayout(self.ui.movieGroupBox)
        movie_layout.addWidget(self.movie_view)
        self.movie_view.show()
        #self.movie_view.key_press.connect(self.keyPressEvent)
        self.movie_view.mouse_press.connect(self.updateInfo)
        self.movie_view.dropped.connect(self.handleDragDrop) 


        self.ui.maxSpinBox.setValue(int(self.settings.value("maximum", 2000)))
        self.ui.minSpinBox.setValue(int(self.settings.value("minimum", 100)))
        self.ui.nmPerPixelSpinBox.setValue(float(self.settings.value("pixel_size", 160)))

        # Fitting Parameters Slider
        self.ui.proc_slider.setMinimum(self.ui.proc_spin_box.minimum())
        self.ui.proc_slider.setMaximum(self.ui.proc_spin_box.maximum())
        self.ui.proc_slider.valueChanged.connect(partial(self.updateDisplay,
                                                        self.ui.proc_slider,
                                                        self.ui.proc_spin_box))
        self.ui.proc_spin_box.valueChanged.connect(self.handleProcSpinBox)

        # Frame Spin Box (Connect to actually move frame) 
        self.ui.frame_spin_box.valueChanged.connect(self.handleFrameSpinBox)


        # initialize range slider.
        self.rangeSlider = qtRangeSlider.QVRangeSlider([self.ui.minSpinBox.minimum(),
                                                        self.ui.maxSpinBox.maximum(),
                                                        1.0],
                                                       [self.ui.minSpinBox.value(),
                                                        self.ui.maxSpinBox.value()],
                                                       parent = self.ui.rangeSliderWidget)
        layout = QtWidgets.QGridLayout(self.ui.rangeSliderWidget)
        layout.addWidget(self.rangeSlider)
        self.rangeSlider.setEmitWhileMoving(True)
        self.rangeSlider.rangeChanged.connect(self.handleRangeChange)

        # signals
        self.ui.actionCapture.triggered.connect(self.capture)
        self.ui.actionLoad_Locs1.triggered.connect(self.handleLoadLocs1)
        self.ui.actionLoad_Locs2.triggered.connect(self.handleLoadLocs2)
        self.ui.actionLoad_Movie.triggered.connect(self.handleLoadMovie)
        self.ui.actionQuit.triggered.connect(self.quit)
        self.ui.maxSpinBox.valueChanged.connect(self.handleMaxMinSpinBox)
        self.ui.minSpinBox.valueChanged.connect(self.handleMaxMinSpinBox)
        self.ui.nmPerPixelSpinBox.valueChanged.connect(self.handleNmPerPixelSpinBox)
        
        # load settings.
        if directory is None:
            self.directory = str(self.settings.value("directory", ""))
        else:
            self.directory = directory

        self.move(self.settings.value("position", self.pos()))

        # Handle actions
        self.ui.actionLoad_Experiment_Folder.triggered.connect(self.handleLoadExpFolder)
        self.ui.actionLoad_Training_Parameters.triggered.connect(self.open_input_parameters_dlg)

        # Handle button actions
        self.ui.load_exp_btn.clicked.connect(self.handleLoadExpFolder)
        self.ui.load_mov_btn.clicked.connect(self.handleLoadMovie)
        self.ui.load_loc1_btn.clicked.connect(self.handleLoadLocs1)
        self.ui.load_loc2_btn.clicked.connect(self.handleLoadLocs2) 

        # Dialog
        self.ui.test_params_btn.clicked.connect(self.open_input_parameters_dlg)
        self.ui.frame_rg_btn.clicked.connect(self.open_frame_range_dlg)
        
        # Button functionality for STORM analysis 
        self.ui.fit_btn.clicked.connect(self.runFitting) 
        self.ui.multifit_btn.clicked.connect(self.runAnalysis) 

        # New layout, help, log panel, viewer extras (gui/layout.py)
        apply_layout(self)
        self._worker = None
        self._worker_thread = None
        self.auto_contrast_btn.clicked.connect(lambda: self.autoContrast())
        self.reset_zoom_btn.clicked.connect(lambda: self.movie_view.resetZoom())
        self.cancel_btn.clicked.connect(self.cancelJob)
        self.movie_view.region_selected.connect(self.autoContrast)
        self.ui.actionCapture.setText("Save View as PNG…")
               

    """ This method handles running the fitting parameters evaluation pipeline """
    def selectedChannels(self):
        return [cb.text() for cb in (self.ui.checkBox488, self.ui.checkBox561,
                                     self.ui.checkBox647, self.ui.checkBox750) if cb.isChecked()]

    def experimentFolder(self):
        return self.ui.exp_lbl.text().strip()

    def showError(self, title, message):
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        # macOS does not show message box titles, so the heading goes in the text.
        box.setText(f"<b>{title}</b>")
        box.setInformativeText(message)
        self._msg = box
        box.show()
        return box

    def runFitting(self):
        """Test fit: fit one movie per selected channel in the background, then
        open the movie and its localizations in the viewer."""
        if self.isBusy():
            return
        channels = self.selectedChannels()
        experiment_folder = self.experimentFolder()
        movie_idx = self.ui.fit_frame_select.value()
        if not experiment_folder or not channels:
            self.showError("Test Fit", "Choose an experiment folder first." if not experiment_folder
                           else "Tick at least one STORM channel.")
            return
        n = self.ui.proc_spin_box.value()

        def fit(log, cancel):
            return fitting_func.fitting_params(experiment_folder, n, channels, movie_idx,
                                               log=log, cancel_event=cancel, return_records=True)
        self.startJob("Test fit", [("Test fit", fit)], on_success=self._showTestFitResult)

    def _showTestFitResult(self, results):
        outputs = results.get("Test fit") or []
        if not outputs:
            return
        record = outputs[0]
        movie, h5, start = record["movie"], record["output"], record["start"]
        if self.loadMovieFile(movie, first_frame=start) and self.loadLocalizations(h5, 1):
            message = f"Showing {os.path.basename(movie)} at frame {start + 1}."
        else:
            message = f"Could not open the preview. Results saved to {os.path.dirname(h5)}."
        self.statusBar().showMessage(f"Test fit saved: {len(outputs)} movie(s). {message}", 15000)

    def runAnalysis(self):
        """Run batch fitting only. Legacy alignment is not ready for use."""
        if self.isBusy():
            return
        experiment = self.experimentFolder()
        channels = self.selectedChannels()
        if not experiment or not channels:
            self.showError("Batch Fit", "Choose an experiment folder first." if not experiment
                           else "Tick at least one STORM channel.")
            return
        workers = self.ui.proc_spin_box.value()

        def fit(log, cancel):
            return scmos_func.batch_fitting(experiment, workers, channels, log=log, cancel_event=cancel)

        self.startJob("Batch fitting", [("Batch fitting", fit)])

    def updateDisplay(self, horizontalSlider, spinBox):
        spinBox.setValue(horizontalSlider.value())

    def handleLoadExpFolder(self):
        if self.isBusy():
            return
        exp_folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose Experiment Folder",
                                                                self.directory)
        if exp_folder:
            self.setExperimentFolder(exp_folder)

    def setExperimentFolder(self, folder):
        editor = getattr(self, "input_parameters_dlg", None)
        if editor is not None:
            editor.close()
            editor.deleteLater()
            self.input_parameters_dlg = None
        self.ui.exp_lbl.setText(folder)
        self.ui.exp_lbl.setVisible(True)
        missing = [d for d in ("acquisition", "XMLs") if not os.path.isdir(os.path.join(folder, d))]
        if missing:
            self.exp_hint.setText("Missing: " + ", ".join(m + "/" for m in missing))
            self.exp_hint.setStyleSheet("color: #ff9f43;")
        else:
            n = len(glob.glob(os.path.join(folder, "acquisition", "*.dax")))
            self.exp_hint.setText(f"{n} movie(s) in acquisition/")
            self.exp_hint.setStyleSheet("color: #9a9a9a;")
        self.statusBar().showMessage("Experiment folder: " + folder, 10000)

    def open_input_parameters_dlg(self):
        if self.isBusy():
            return
        # Keep a reference on the window. As a local variable the dialog was
        # garbage collected as soon as this method returned, so it closed instantly.
        editor = getattr(self, "input_parameters_dlg", None)
        if editor is not None:
            if editor.isVisible():
                editor.raise_()
                editor.activateWindow()
                return
            editor.deleteLater()
        self.input_parameters_dlg = AdvancedSettingsDialog(self, xml_dir=self.experimentXmlDir())
        self.input_parameters_dlg.show()

    def experimentXmlDir(self):
        d = os.path.join(self.experimentFolder(), "XMLs") if self.experimentFolder() else ""
        return d if d and os.path.isdir(d) else None

    def open_frame_range_dlg(self):
        if self.isBusy():
            return
        # (The original called show() after exec(), so the dialog reopened after OK/Cancel.)
        self.frame_range_dlg = FrameRangeDialog(self, xml_dir=self.experimentXmlDir())
        self.frame_range_dlg.exec()
        
    # ---- background jobs
    def isBusy(self):
        return self._worker_thread is not None

    def startJob(self, title, steps, on_success=None):
        worker, thread = start_worker(self, steps)
        self._job_title = title
        self._job_on_success = on_success
        worker.log.connect(self.appendLog)
        worker.progress.connect(self._onProgress)
        worker.step_started.connect(lambda s: self.progress_bar.setFormat(s + "…"))
        worker.succeeded.connect(self._onJobSucceeded)
        worker.failed.connect(self._onJobFailed)
        worker.cancelled.connect(lambda: self.statusBar().showMessage(title + " cancelled.", 15000))
        thread.finished.connect(self._onJobDone)
        self.setRunning(True, title)
        self.appendLog(f"\n##### {title} started #####")
        thread.start()

    def setRunning(self, running, title=""):
        for w in (self.ui.fit_btn, self.ui.multifit_btn, self.ui.load_exp_btn,
                  self.ui.test_params_btn, self.ui.frame_rg_btn,
                  self.ui.actionLoad_Experiment_Folder, self.ui.actionLoad_Training_Parameters):
            w.setEnabled(not running)
        editor = getattr(self, "input_parameters_dlg", None)
        if editor is not None:
            editor.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        if running:
            self.progress_bar.setRange(0, 0)          # busy until the first [i/n] line
            self.progress_bar.setFormat(title + "…")
            self.statusBar().showMessage(title + " running. You can keep using the viewer.")
        else:
            self.progress_bar.setRange(0, 100)

    def appendLog(self, line):
        self.log_view.appendPlainText(line)

    def _onProgress(self, label, i, n):
        self.progress_bar.setRange(0, n)
        self.progress_bar.setValue(i - 1)
        self.progress_bar.setFormat(f"{label} {i}/{n}")

    def _onJobSucceeded(self, results):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.setFormat(self._job_title + " done")
        self.statusBar().showMessage(self._job_title + " finished.", 15000)
        if self._job_on_success:
            self._job_on_success(results)

    def _onJobFailed(self, step, message):
        self.progress_bar.setFormat(f"{step} failed")
        self.statusBar().showMessage(f"{step} failed. See the log.", 15000)
        self.showError(f"{step} failed", message[:2000])

    def _onJobDone(self):
        self.setRunning(False)
        if self.progress_bar.format().endswith("…"):
            self.progress_bar.setFormat("Cancelled")
        thread = self._worker_thread
        self._worker_thread = None
        self._worker = None
        if thread is not None:
            thread.deleteLater()

    def cancelJob(self):
        if self._worker is not None and self.isBusy():
            self.appendLog("Cancelling…")
            self.progress_bar.setFormat("Cancelling…")
            self._worker.cancel()

    def capture(self):
        name = QtWidgets.QFileDialog.getSaveFileName(self, "Save View as PNG",
                                                     os.path.join(self.directory or "", "capture.png"),
                                                     "PNG image (*.png)")[0]
        if name:
            self.movie_view.grab().save(name)
            self.statusBar().showMessage("Saved " + name, 10000)

    def cleanUp(self):
        if self.movie_file is not None:
            self.movie_file.close()
            self.movie_file = None
        for elt in [self.locs1_list, self.locs2_list]:
            if elt is not None:
                elt.cleanUp()

        self.settings.setValue("directory", self.directory)
        self.settings.setValue("maximum", self.ui.maxSpinBox.value())
        self.settings.setValue("minimum", self.ui.minSpinBox.value())
        self.settings.setValue("pixel_size", self.ui.nmPerPixelSpinBox.value())
        self.settings.setValue("position", self.pos())
        self.settings.setValue("size", self.size())

    def closeEvent(self, event):
        if self.isBusy():
            self.cancelJob()
            self.statusBar().showMessage("Stopping after the current stage. Close again when idle.")
            event.ignore()
            return
        self.cleanUp()

    def displayFrame(self, update_locs):
        if self.movie_file:
            
            # Make sure cur_frame is valid! 
            if (self.cur_frame < 0):
                self.cur_frame = 0
            if (self.cur_frame >= self.film_l):
                self.cur_frame = self.film_l - 1

            # Get the current frame.
            try:
                frame = self.movie_file.loadAFrame(self.cur_frame).astype(float)
            except Exception as exc:
                self.showError("Could not read movie frame", f"{self.ui.mov_path_lbl.text()}: {exc}")
                return

            # Scene.clear() deletes older Qt items. Never leave hit-testing pointed at them.
            nm_per_pixel = self.ui.nmPerPixelSpinBox.value()
            overlays = []
            for locs in (self.locs1_list, self.locs2_list):
                if locs is None:
                    overlays.append([])
                    continue
                locs.clearLocs()
                try:
                    overlays.append(locs.createMolItems(self.cur_frame, nm_per_pixel) if update_locs else [])
                except Exception as exc:
                    locs.clearLocs()
                    overlays.append([])
                    self.showError("Could not read localizations", f"{locs.filename}: {exc}")
            locs1, locs2 = overlays

            self.movie_view.newFrame(frame,
                                     locs1,
                                     locs2,
                                     self.ui.minSpinBox.value(),
                                     self.ui.maxSpinBox.value())
                                     
    def handleDragDrop(self, file):
        if file.lower().endswith(('.bin', '.hdf5')):
            self.loadLocalizations(file, 1)
        elif file.lower().endswith(('.dax', '.spe', '.tif', '.tiff', '.fits')):
            self.loadMovieFile(file)

    def loadLocalizations(self, list_filename, which):
        old = self.locs1_list if which == 1 else self.locs2_list
        new = None
        try:
            mtype = "l1" if which == 1 else "l2"
            if list_filename.lower().endswith(".hdf5"):
                if not saH5Py.isSAHDF5(list_filename):
                    raise ValueError("not a storm-analysis HDF5 file")
                new = MoleculeListHDF5(filename=list_filename, mtype=mtype)
                with saH5Py.SAH5Reader(list_filename) as reader:
                    reader.getMovieLength()
            else:
                if not readinsight3.checkStatus(list_filename):
                    raise ValueError("invalid Insight3 file")
                new = MoleculeListI3(filename=list_filename, mtype=mtype)
            new.createMolItems(max(0, self.cur_frame), self.ui.nmPerPixelSpinBox.value())
        except Exception as exc:
            if new is not None:
                new.cleanUp()
            self.showError("Could not open localizations", f"{list_filename}: {exc}")
            return False
        if old is not None:
            old.cleanUp()
        self.directory = os.path.dirname(list_filename)
        if which == 1:
            self.locs1_list = new
            self.locs1_table.showFields(new.getFields())
        else:
            self.locs2_list = new
            self.locs2_table.showFields(new.getFields())
        self.incCurFrame(0)
        return True

    def loadMovieFile(self, movie_filename, first_frame=0):
        """Shared by Load Movie, drag and drop, and the test fit result. (Drag and
        drop used to skip the label updates, so the frame count stayed wrong.)"""
        reader = None
        try:
            reader = datareader.inferReader(movie_filename)
            width, height, length = reader.filmSize()
            if width <= 0 or height <= 0 or not 0 <= first_frame < length:
                raise ValueError("invalid movie dimensions or frame range")
            for n in {0, first_frame, length - 1}:
                frame = reader.loadAFrame(n)
                if frame.shape != (height, width) or not np.isfinite(frame).any():
                    raise ValueError(f"frame {n + 1} has invalid image data")
        except Exception as exc:
            if reader is not None:
                reader.close()
            self.showError("Could not open movie", f"{movie_filename}: {exc}")
            return False
        previous = self.movie_file
        self.movie_file = reader
        if previous is not None:
            previous.close()
        self.directory = os.path.dirname(movie_filename)
        self.film_x, self.film_y, self.film_l = width, height, length
        self.cur_frame = first_frame

        # Clear molecule lists.
        for elt in [self.locs1_list, self.locs2_list]:
            if elt is not None:
                elt.cleanUp()
        self.locs1_list = None
        self.locs2_list = None

        # Hide info displays
        self.locs1_table.hideFields()
        self.locs2_table.hideFields()

        # Block signals: shrinking the maximum clamps the box value, and that change
        # used to jump the viewer to the last frame.
        self.ui.frame_spin_box.blockSignals(True)
        self.ui.frame_spin_box.setMaximum(max(1, self.film_l))
        self.ui.frame_spin_box.setValue(first_frame + 1)
        self.ui.frame_spin_box.blockSignals(False)
        self.incCurFrame(0)
        self.ui.mov_path_lbl.setText(movie_filename)
        self.ui.nmPerPixLabel_2.setText("of {}".format(self.film_l))
        self.fitContrastSliderToMovie()
        self.movie_view.resetZoom()
        self.statusBar().showMessage(f"{os.path.basename(movie_filename)}: {self.film_l} frames, "
                                     f"{self.film_x} x {self.film_y} pixels", 10000)
        return True

    def handleLoadLocs1(self):
        list_filename = QtWidgets.QFileDialog.getOpenFileName(self,
                                                              "Overlay Localizations 1",
                                                              self.directory,
                                                              "Localizations (*.bin *.hdf5)")[0]
        if list_filename:
            self.loadLocalizations(list_filename, 1)

    def handleLoadLocs2(self):
        list_filename = QtWidgets.QFileDialog.getOpenFileName(self,
                                                              "Overlay Localizations 2",
                                                              self.directory,
                                                              "Localizations (*.bin *.hdf5)")[0]
        if list_filename:
            self.loadLocalizations(list_filename, 2)

    def handleLoadMovie(self):
        movie_filename = QtWidgets.QFileDialog.getOpenFileName(self,
                                                               "Open Movie",
                                                               self.directory,
                                                               "Movies (*.dax *.fits *.spe *.tif)")[0]
        if movie_filename:
            self.loadMovieFile(movie_filename)

    def handleLocsDisplayTimer(self):
        self.displayFrame(True)

    def handleMaxMinSpinBox(self, value):
        self.rangeSlider.setValues([self.ui.minSpinBox.value(),
                                    self.ui.maxSpinBox.value()])

    def handleNmPerPixelSpinBox(self, value):
        self.displayFrame(True)

    def handleProcSpinBox(self):
        self.ui.proc_slider.setValue(self.ui.proc_spin_box.value())
        
    def handleFrameSpinBox(self):
        self.cur_frame = int(self.ui.frame_spin_box.value()) - 1  # box is 1-indexed, cur_frame is 0-indexed
        self.displayFrame(False)
        self.locs_display_timer.start()

    def handleRangeChange(self, range_min, range_max):
        # The range slider sends floats. PyQt5 rounded them silently; PyQt6 raises
        # TypeError, which crashed the app on any contrast slider drag.
        self.ui.minSpinBox.setValue(int(round(range_min)))
        self.ui.maxSpinBox.setValue(int(round(range_max)))
        self.displayFrame(False)
        self.locs_display_timer.start()

    def incCurFrame(self, amount):
        self.cur_frame += amount
        if (self.cur_frame < 0):
            self.cur_frame = 0
        if (self.cur_frame >= self.film_l):
            self.cur_frame = self.film_l - 1
        if self.movie_file:
            if (self.locs1_list is not None):
                self.locs1_list.clearLocs()
            if (self.locs2_list is not None):
                self.locs2_list.clearLocs()
            self.ui.frame_spin_box.setValue(self.cur_frame+1)
            self.displayFrame(False)
            self.locs_display_timer.start()

    def keyPressEvent(self, event):
        if (event.key() == QtCore.Qt.Key.Key_End):
            self.incCurFrame(self.film_l)
        if (event.key() == QtCore.Qt.Key.Key_Home):
            self.incCurFrame(-self.film_l)
        if (event.key() == QtCore.Qt.Key.Key_Comma):
            self.incCurFrame(-1)
        if (event.key() == QtCore.Qt.Key.Key_Period):
            self.incCurFrame(1)
        if (event.key() == QtCore.Qt.Key.Key_K):
            self.incCurFrame(-200)
        if (event.key() == QtCore.Qt.Key.Key_L):
            self.incCurFrame(200)
        if (event.key() == QtCore.Qt.Key.Key_A):
            self.autoContrast()
        if (event.key() == QtCore.Qt.Key.Key_R):
            self.movie_view.resetZoom()

    def fitContrastSliderToMovie(self):
        """The slider spanned 0..65535, about 150 counts per pixel, so typical STORM
        data (~100..2000) used the bottom few pixels. Fit it to this movie instead."""
        frame = self.movie_file.loadAFrame(0)
        top = max(1000, int(np.ceil(np.percentile(frame[np.isfinite(frame)], 99.99) * 2)),
                  self.ui.maxSpinBox.value())
        top = min(top, self.ui.maxSpinBox.maximum())
        self.rangeSlider.setRange([self.ui.minSpinBox.minimum(), top, 1.0])
        self.rangeSlider.updateDisplayValues()
        self.rangeSlider.update()

    def autoContrast(self, region=None, lo_pct=1.0, hi_pct=99.5):
        """Set the display range from percentiles of the current frame, or of the
        given box (scene/pixel coordinates) if one is passed."""
        data = self.movie_view.data
        if not isinstance(data, np.ndarray):
            return None
        if region is not None:
            h, w = data.shape
            x0 = int(max(0, np.floor(region.left())));  x1 = int(min(w, np.ceil(region.right())))
            y0 = int(max(0, np.floor(region.top())));   y1 = int(min(h, np.ceil(region.bottom())))
            if x1 - x0 < 2 or y1 - y0 < 2:
                return None
            data = data[y0:y1, x0:x1]
        lo, hi = np.percentile(data, [lo_pct, hi_pct])
        lo, hi = int(np.floor(lo)), int(np.ceil(hi))
        if hi <= lo:
            hi = lo + 1
        lo = max(lo, self.ui.minSpinBox.minimum())
        hi = min(hi, self.ui.maxSpinBox.maximum())
        # Order matters so the min never passes the max on the way.
        if lo > self.ui.maxSpinBox.value():
            self.ui.maxSpinBox.setValue(hi); self.ui.minSpinBox.setValue(lo)
        else:
            self.ui.minSpinBox.setValue(lo); self.ui.maxSpinBox.setValue(hi)
        where = "box" if region is not None else "frame"
        self.statusBar().showMessage(f"Contrast set from {where}: {lo} to {hi}", 8000)
        return lo, hi

    def quit(self):
        self.close()

    def updateInfo(self, x, y):
        if self.locs1_list is not None:
            properties = self.locs1_list.getClosest(x, y)
            self.locs1_table.update(properties)
        if self.locs2_list:
            properties = self.locs2_list.getClosest(x, y)
            self.locs2_table.update(properties)

    def wheelEvent(self, event):
        if not event.angleDelta().isNull():
            if (event.angleDelta().y() > 0):
                self.incCurFrame(1)
            else:
                self.incCurFrame(-1)


if (__name__ == "__main__"):
    app = QtWidgets.QApplication(sys.argv)
    styles.dark(app)

    directory = None
    if (len(sys.argv) == 2):
        directory = sys.argv[1]

    window = Window(directory = directory)

    window.show()
    app.exec()
    app.deleteLater()
    sys.exit()
