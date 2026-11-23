"""
Main window layout, help text and tooltips.

The generated GUI_ui.py put the viewer in a floating MDI "Subwindow" (with a
gray dead area under it) and listed every control in one column. This moves
the same widgets (same object names, so every signal connection still works)
into:

    left:   numbered steps in group boxes, then viewer controls
    right:  the viewer, filling the space, with a log/progress panel under it
"""
import os

from PyQt6 import QtCore, QtGui, QtWidgets

QUICK_START = """
<h3>STORMpro quick start</h3>
<ol>
<li><b>Experiment folder</b>: choose the folder that contains <code>acquisition/</code>
(the .dax movies, named like <code>647storm_00.dax</code>) and <code>XMLs/</code>
(one fitting parameter file per channel, like <code>647.xml</code>).</li>
<li><b>Channels</b>: tick the STORM channels to fit.
<i>Parallel jobs</i> is how many movies are fitted at the same time.</li>
<li><b>Test fit</b>: <i>Edit Test Parameters</i> to change the XML settings, pick a
movie number, then <i>Run Test Fit</i>. Only that movie is fitted, using the frame
range in the XML. The movie and its localizations open in the viewer when it is done,
so you can check the parameters before the full run.</li>
<li><b>Batch fitting</b>: <i>Set Frame Ranges</i>, then <i>Run Batch Fit</i>.
Results go into a new folder under <code>batch_fits/</code>. XY and Z alignment are not available in this build.</li>
</ol>
<p>Jobs run in the background. Progress and messages appear in the log under the
viewer, and <i>Cancel</i> stops them. Run fitting only with trusted settings and calibration files.</p>
"""

SHORTCUTS = """
<h3>Viewer controls</h3>
<table cellpadding="3">
<tr><td><b>.</b> / <b>,</b></td><td>next / previous frame</td></tr>
<tr><td><b>L</b> / <b>K</b></td><td>forward / back 200 frames</td></tr>
<tr><td><b>Home</b> / <b>End</b></td><td>first / last frame</td></tr>
<tr><td>Mouse wheel over the movie</td><td>zoom in / out</td></tr>
<tr><td>Drag</td><td>pan</td></tr>
<tr><td><b>Shift</b> + drag a box</td><td>zoom to the box and set contrast from it</td></tr>
<tr><td><b>A</b></td><td>auto contrast (whole frame)</td></tr>
<tr><td><b>R</b></td><td>reset zoom</td></tr>
<tr><td>Drop a file on the movie</td><td>open a .dax/.tif movie or .hdf5/.bin localizations</td></tr>
</table>
<p>The numbers under the movie are x, y (pixels) and the intensity under the cursor.</p>
"""

TOOLTIPS = {
    "load_exp_btn": "Choose the experiment folder (it must contain acquisition/ and XMLs/).",
    "exp_lbl": "Current experiment folder.",
    "checkBox750": "Fit the 750 nm STORM channel (uses XMLs/750.xml).",
    "checkBox647": "Fit the 647 nm STORM channel (uses XMLs/647.xml).",
    "checkBox561": "Fit the 561 nm STORM channel (uses XMLs/561.xml).",
    "checkBox488": "Fit the 488 nm STORM channel (uses XMLs/488.xml).",
    "a_checkBox561": "Use 561 as the alignment channel for XY and Z alignment.",
    "a_checkBox488": "Use 488 (WGA) as the alignment channel for XY and Z alignment.",
    "proc_spin_box": "How many movies are fitted at the same time. More is faster but uses more memory.",
    "test_params_btn": "Edit the fitting parameters (XML files) for the test fit.",
    "fit_frame_select": "Movie number to test, e.g. 3 for 647storm_03.dax. -1 tests every movie.",
    "fit_btn": "Fit one movie per selected channel with the current XML parameters and show the result.",
    "frame_rg_btn": "Set the frame ranges used for the full analysis.",
    "multifit_btn": "Fit selected STORM channels and bead movies into a new results folder.",
    "load_mov_btn": "Open a movie (.dax, .tif, .spe, .fits). You can also drop it on the viewer.",
    "load_loc1_btn": "Overlay localizations (.hdf5 or .bin), drawn in the first color.",
    "load_loc2_btn": "Overlay a second localization file, drawn in the second color.",
    "nmPerPixelSpinBox": "Camera pixel size in nm, used to size the localization markers.",
    "frame_spin_box": "Current frame. Use . and , to step.",
    "maxSpinBox": "Display maximum (contrast).",
    "minSpinBox": "Display minimum (contrast).",
}

CHANNEL_COLORS = {"750": "#ff6b6b", "647": "#ff9f43", "561": "#feca57", "488": "#48dbfb"}


def _group(title, *rows):
    box = QtWidgets.QGroupBox(title)
    lay = QtWidgets.QVBoxLayout(box)
    lay.setSpacing(6)
    for r in rows:
        if isinstance(r, QtWidgets.QLayout):
            lay.addLayout(r)
        else:
            lay.addWidget(r)
    return box


def _row(*items, stretch=True):
    h = QtWidgets.QHBoxLayout()
    h.setSpacing(8)
    for it in items:
        if isinstance(it, str):
            h.addWidget(QtWidgets.QLabel(it))
        else:
            h.addWidget(it)
    if stretch:
        h.addStretch(1)
    return h


def apply_layout(win):
    ui = win.ui

    # Clearer button names. Channel checkbox text stays "750"/"647"/... because
    # the pipeline reads it with cb.text().
    ui.load_exp_btn.setText("Choose Experiment Folder…")
    ui.test_params_btn.setText("Edit Test Parameters…")
    ui.fit_btn.setText("Run Test Fit")
    ui.frame_rg_btn.setText("Set Frame Ranges…")
    ui.multifit_btn.setText("Run Batch Fit")
    ui.load_mov_btn.setText("Open Movie…")
    ui.load_loc1_btn.setText("Overlay Localizations 1…")
    ui.load_loc2_btn.setText("Overlay Localizations 2…")
    ui.fit_frame_lbl.setText("Movie number")
    ui.proc_lbl.setText("Parallel jobs")
    for b in (ui.fit_btn, ui.multifit_btn):
        b.setMinimumHeight(30)
        f = b.font(); f.setBold(True); b.setFont(f)

    # Experiment folder label: never "NA"
    if ui.exp_lbl.text() in ("", "NA"):
        ui.exp_lbl.setText("")
    ui.exp_lbl.setWordWrap(True)
    ui.exp_lbl.setMinimumHeight(0)
    ui.exp_lbl.setVisible(bool(ui.exp_lbl.text()))
    ui.exp_lbl.setMinimumWidth(0)
    ui.exp_lbl.setMaximumWidth(16777215)
    win.exp_hint = QtWidgets.QLabel("No folder selected")
    win.exp_hint.setStyleSheet("color: #9a9a9a;")

    # Parallel jobs: never 0 (the old default); start at half the CPU cores.
    if ui.proc_spin_box.value() < 1:        # check before raising the minimum clamps it to 1
        ui.proc_spin_box.setValue(max(1, (os.cpu_count() or 2) // 2))
    ui.proc_spin_box.setMinimum(1)
    ui.proc_slider.setMinimum(1)
    ui.proc_slider.hide()
    ui.fit_frame_select.setMinimum(-1)
    ui.fit_frame_select.setMaximumWidth(80)
    ui.proc_spin_box.setMaximumWidth(80)

    # Viewer extras
    win.auto_contrast_btn = QtWidgets.QPushButton("Auto Contrast")
    win.reset_zoom_btn = QtWidgets.QPushButton("Reset Zoom")
    win.help_btn = QtWidgets.QPushButton("Help")

    # ---- left panel
    left = QtWidgets.QWidget()
    lv = QtWidgets.QVBoxLayout(left)
    lv.setContentsMargins(8, 8, 8, 8)
    lv.setSpacing(10)
    trust_hint = QtWidgets.QLabel("Only fit experiments with trusted XML and calibration files.")
    trust_hint.setWordWrap(True)
    lv.addWidget(_group("1. Experiment", ui.load_exp_btn, ui.exp_lbl, win.exp_hint, trust_hint))
    lv.addWidget(_group("2. Channels",
                        _row("STORM", ui.checkBox750, ui.checkBox647, ui.checkBox561, ui.checkBox488),
                        _row(ui.proc_lbl, ui.proc_spin_box)))
    lv.addWidget(_group("3. Test fit (one movie)",
                        ui.test_params_btn,
                        _row(ui.fit_frame_lbl, ui.fit_frame_select),
                        ui.fit_btn))
    lv.addWidget(_group("4. Batch fitting", ui.frame_rg_btn, ui.multifit_btn))
    lv.addWidget(_group("Viewer", ui.load_mov_btn, ui.load_loc1_btn, ui.load_loc2_btn,
                        _row(win.auto_contrast_btn, win.reset_zoom_btn, stretch=False),
                        win.help_btn))
    lv.addStretch(1)
    for lbl in (ui.chl_lbl, ui.align_chl_lbl, ui.fit_title_lbl, ui.scmos_title_lbl):
        lbl.hide()
    scroll = QtWidgets.QScrollArea()
    scroll.setWidget(left)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setMinimumWidth(320)
    scroll.setMaximumWidth(420)

    # ---- log panel
    win.log_view = QtWidgets.QPlainTextEdit()
    win.log_view.setReadOnly(True)
    win.log_view.setMaximumBlockCount(20000)
    win.log_view.setPlaceholderText("Messages from Test Fit and Batch Fit appear here.")
    win.log_view.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
    win.progress_bar = QtWidgets.QProgressBar()
    win.progress_bar.setTextVisible(True)
    win.progress_bar.setFormat("Idle")
    win.progress_bar.setValue(0)
    win.cancel_btn = QtWidgets.QPushButton("Cancel")
    win.cancel_btn.setEnabled(False)
    log_panel = QtWidgets.QWidget()
    lp = QtWidgets.QVBoxLayout(log_panel)
    lp.setContentsMargins(0, 0, 0, 0)
    lp.addLayout(_row(win.progress_bar, win.cancel_btn, stretch=False))
    lp.addWidget(win.log_view)

    # ---- right: viewer (taken out of the MDI area) above the log
    viewer = ui.subwindow
    ui.mdiArea.removeSubWindow(viewer)
    viewer.setParent(None)
    viewer.setWindowTitle("")
    right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
    right.addWidget(viewer)
    right.addWidget(log_panel)
    right.setStretchFactor(0, 4)
    right.setStretchFactor(1, 1)
    right.setSizes([620, 160])
    ui.mdiArea.hide()

    split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
    split.addWidget(scroll)
    split.addWidget(right)
    split.setStretchFactor(1, 1)
    old = win.centralWidget()
    win.setCentralWidget(split)
    old.deleteLater()
    win.main_splitter, win.right_splitter = split, right

    # Frame box shows whole frames, not "1.00"
    ui.frame_spin_box.setDecimals(0)
    ui.frame_spin_box.setMinimum(1)

    # Consistent fonts: the generated code hardcoded 10 pt on most widgets.
    base = win.font()          # the window sets 12 pt; match it everywhere
    moved = [ui.load_exp_btn, ui.exp_lbl, ui.proc_lbl, ui.proc_spin_box, ui.test_params_btn,
             ui.fit_frame_lbl, ui.fit_frame_select, ui.fit_btn, ui.frame_rg_btn, ui.multifit_btn,
             ui.load_mov_btn, ui.load_loc1_btn, ui.load_loc2_btn,
             ui.checkBox750, ui.checkBox647, ui.checkBox561, ui.checkBox488,
             ui.a_checkBox561, ui.a_checkBox488]
    for w in moved:
        f = QtGui.QFont(base)
        f.setBold(w.font().bold() or w in (ui.fit_btn, ui.multifit_btn))
        f.setUnderline(False)
        w.setFont(f)
        # The generated code gave most buttons a fixed max width, which clipped the text.
        w.setMinimumWidth(0)
        w.setMaximumWidth(16777215 if isinstance(w, (QtWidgets.QPushButton, QtWidgets.QLabel)) else w.maximumWidth())
        if isinstance(w, QtWidgets.QPushButton):
            w.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
    ui.fit_frame_select.setMaximumWidth(80)
    ui.proc_spin_box.setMaximumWidth(80)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # Visible checkbox indicators on the dark theme, filled with the channel color when on.
    for cb in (ui.checkBox750, ui.checkBox647, ui.checkBox561, ui.checkBox488,
               ui.a_checkBox561, ui.a_checkBox488):
        c = CHANNEL_COLORS[cb.text()]
        cb.setStyleSheet(
            f"QCheckBox {{ color: {c}; font-weight: bold; spacing: 5px; }}"
            f"QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid #9a9a9a;"
            f" border-radius: 2px; background: #2a2a2a; }}"
            f"QCheckBox::indicator:checked {{ background: {c}; border-color: {c}; }}")

    # No "NA" placeholders under the movie.
    ui.xyiLabel.setText("")
    ui.xyiLabel.setToolTip("x, y (pixels) and intensity under the cursor")
    ui.fileLabel.setText("")
    ui.fileLabel.hide()
    ui.nmPerPixLabel_2.setText("of 0")

    for name, tip in TOOLTIPS.items():
        w = getattr(ui, name, None)
        if w is not None:
            w.setToolTip(tip)
    win.auto_contrast_btn.setToolTip("Set contrast from the current frame (A).")
    win.reset_zoom_btn.setToolTip("Fit the whole frame in the viewer (R).")
    win.cancel_btn.setToolTip("Stop the running job.")

    # Help menu
    help_menu = win.menuBar().addMenu("Help")
    a1 = help_menu.addAction("Quick Start")
    a2 = help_menu.addAction("Viewer Controls")
    a1.triggered.connect(lambda: show_help(win, QUICK_START, "Quick Start"))
    a2.triggered.connect(lambda: show_help(win, SHORTCUTS, "Viewer Controls"))
    win.help_btn.clicked.connect(lambda: show_help(win, QUICK_START + SHORTCUTS, "Help"))

    win.statusBar().showMessage("Choose an experiment folder, or open a movie to view it.")
    win.setWindowTitle("STORMpro")
    win.resize(1400, 860)


def show_help(win, html, title):
    dlg = QtWidgets.QMessageBox(win)
    dlg.setWindowTitle(title)
    dlg.setTextFormat(QtCore.Qt.TextFormat.RichText)
    dlg.setText(html)
    dlg.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Close)
    win._help_dlg = dlg
    dlg.show()
    return dlg
