# SPDX-License-Identifier: GPL-3.0-or-later
"""Mouse Properties (Windows Vista style) for the X11 session.

Same settings KDE's mouse module writes (plasma-desktop kcms/mouse, Plasma/6.6):
- kcminputrc [Mouse] XLbInptLeftHanded, XLbInptPointerAcceleration (-1..1),
  XLbInptAccelProfileFlat (flat = "Enhance pointer precision" off), XLbInptNaturalScroll;
  applied to all pointer devices by `kcminit kcm_mouse` (backends/x11).
- kdeglobals [KDE] DoubleClickInterval (ms), WheelScrollLines - with change notification.
- Pointer scheme/size via plasma-apply-cursortheme.
On Wayland input settings are per device in KWin; there the KDE module is used instead."""
import os

from PyQt6.QtCore import QElapsedTimer, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QHeaderView, QLabel, QSlider, QSpinBox,
                             QToolButton, QTreeWidget, QTreeWidgetItem)

import xcursor
from applets.base import AppletDialog
from style import ICON, SPACE
from ui import form_grid, gap, hbox, kread, kwrite_cmd, text_label

INPUT = ("kcminputrc", "Mouse")
CURSOR_SIZES = [(24, "Normal"), (32, "Large"), (48, "Extra large")]
DOUBLE_CLICK = (200, 900)   # ms: Windows' range; the slider runs Slow -> Fast


def cursor_themes():
    """name -> display name of every installed pointer scheme."""
    themes = {}
    for d in xcursor.search_dirs():
        for name in sorted(os.listdir(d)):
            if name in themes or not os.path.isdir(os.path.join(d, name, "cursors")):
                continue
            title = None
            try:
                for line in open(os.path.join(d, name, "index.theme"), encoding="utf-8", errors="replace"):
                    if line.startswith("Name="):
                        title = line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass
            themes[name] = xcursor.pretty_name(name, title)
    return themes


class TestFolder(QToolButton):
    """Windows' double-click test: the folder opens/closes on a double-click at the
    speed currently set on the slider (not the system's)."""

    def __init__(self, interval_ms):
        super().__init__()
        self.interval = interval_ms
        self.open = False
        self._last = QElapsedTimer()
        self.setAutoRaise(True)
        self.setIconSize(QSize(ICON["large"], ICON["large"]))
        self.setToolTip("Double-click the folder to test your setting.")
        self._paint()

    def _paint(self):
        self.setIcon(QIcon.fromTheme("folder-open" if self.open else "folder"))

    def mousePressEvent(self, e):
        if self._last.isValid() and self._last.elapsed() <= self.interval:
            self.open = not self.open
            self._paint()
            self._last.invalidate()
        else:
            self._last.start()


class MouseProperties(AppletDialog):
    ID = "mouse"
    TITLE = "Mouse Properties"
    ICON = "preferences-desktop-mouse"
    ADVANCED = "kcm:kcm_mouse"
    REPLACES = ["kcm_mouse", "kcm_cursortheme#pointers"]

    @classmethod
    def available(cls):
        return os.environ.get("XDG_SESSION_TYPE") == "x11"

    def build(self):
        # --- Buttons ---------------------------------------------------------------------
        page, v = self.new_page()
        g = self.group(v, "Button configuration", "preferences-desktop-mouse")
        self.left_handed = QCheckBox("Switch primary and secondary buttons")
        self.left_handed.toggled.connect(self.changed)
        g.addWidget(self.left_handed)
        g.addWidget(text_label("Select this check box to make the button on the right the one you use "
                               "for primary functions such as selecting and dragging.", "secondary"))
        g = self.group(v, "Double-click speed")
        g.addWidget(text_label("Double-click the folder to test your setting. If the folder does not "
                               "open or close, try using a slower setting.", "secondary"))
        row = hbox(spacing="related")
        row.addWidget(text_label("Speed:", "body"))
        row.addWidget(text_label("Slow", "caption"))
        self.dbl = QSlider(Qt.Orientation.Horizontal)
        self.dbl.setRange(0, 14)          # 14 steps of 50 ms between 900 and 200 ms
        self.dbl.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.dbl.setTickInterval(2)
        self.dbl.valueChanged.connect(self._dbl_changed)
        row.addWidget(self.dbl, 1)
        row.addWidget(text_label("Fast", "caption"))
        row.addSpacing(SPACE["unrelated"])
        self.folder = TestFolder(400)
        row.addWidget(self.folder)
        g.addLayout(row)
        v.addStretch(1)
        self.add_tab(page, "Buttons", "buttons")

        # --- Pointers --------------------------------------------------------------------
        page2, v2 = self.new_page()
        g = self.group(v2, "Pointer scheme", "preferences-desktop-cursors")
        grid = form_grid()
        grid.addWidget(QLabel("Scheme:"), 0, 0)
        self.scheme = QComboBox()
        self.scheme.currentIndexChanged.connect(self._scheme_changed)
        grid.addWidget(self.scheme, 0, 1)
        grid.addWidget(QLabel("Size:"), 1, 0)
        self.size = QComboBox()
        for px, label in CURSOR_SIZES:
            self.size.addItem(label, px)
        self.size.currentIndexChanged.connect(self.changed)
        grid.addWidget(self.size, 1, 1)
        grid.setColumnStretch(1, 1)
        g.addLayout(grid)
        gap(v2)
        v2.addWidget(QLabel("Customize:"))
        self.preview = QTreeWidget()
        self.preview.setColumnCount(2)
        self.preview.setHeaderHidden(True)
        self.preview.setRootIsDecorated(False)
        self.preview.setAlternatingRowColors(True)
        self.preview.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview.setIconSize(QSize(ICON["medium"], ICON["medium"]))
        hdr = self.preview.header()
        hdr.setStretchLastSection(False)           # role names stretch, pointers sit at the right
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(1, ICON["medium"] + 2 * SPACE["unrelated"])
        for role, _names in xcursor.ROLES:
            it = QTreeWidgetItem([role, ""])
            it.setSizeHint(0, QSize(0, ICON["medium"] + SPACE["related"]))
            self.preview.addTopLevelItem(it)
        v2.addWidget(self.preview, 1)
        self.add_tab(page2, "Pointers", "pointers")

        # --- Pointer Options --------------------------------------------------------------
        page3, v3 = self.new_page()
        g = self.group(v3, "Motion", "preferences-desktop-mouse")
        g.addWidget(QLabel("Select a pointer speed:"))
        row3 = hbox(spacing="related")
        row3.addWidget(text_label("Slow", "caption"))
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(0, 20)        # libinput acceleration -1..1 in steps of 0.1
        self.speed.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.speed.setTickInterval(2)
        self.speed.valueChanged.connect(self.changed)
        row3.addWidget(self.speed, 1)
        row3.addWidget(text_label("Fast", "caption"))
        g.addLayout(row3)
        self.precision = QCheckBox("Enhance pointer precision")
        self.precision.toggled.connect(self.changed)
        g.addWidget(self.precision)
        g.addWidget(text_label("Moves the pointer further when you move the mouse quickly.", "secondary"))
        v3.addStretch(1)
        self.add_tab(page3, "Pointer Options", "options")

        # --- Wheel -------------------------------------------------------------------------
        page4, v4 = self.new_page()
        g = self.group(v4, "Vertical Scrolling", "preferences-desktop-mouse")
        g.addWidget(QLabel("Roll the wheel one notch to scroll:"))
        row4 = hbox(spacing="related")
        self.lines = QSpinBox()
        self.lines.setRange(1, 30)
        self.lines.valueChanged.connect(self.changed)
        row4.addWidget(self.lines)
        row4.addWidget(QLabel("lines at a time"))
        row4.addStretch(1)
        g.addLayout(row4)
        self.natural = QCheckBox("Reverse scrolling direction")
        self.natural.toggled.connect(self.changed)
        g.addWidget(self.natural)
        g.addWidget(text_label("Content moves the same way as your fingers, like on a phone.", "secondary"))
        v4.addStretch(1)
        self.add_tab(page4, "Wheel", "wheel")

    def _scheme_changed(self, *_):
        theme = self.scheme.currentData()
        for i, (_role, names) in enumerate(xcursor.ROLES):
            pm = xcursor.preview(theme, names, ICON["medium"]) if theme else None
            it = self.preview.topLevelItem(i)
            it.setIcon(1, QIcon(pm) if pm else QIcon())
        self.changed()

    def _dbl_changed(self, val):
        self.folder.interval = DOUBLE_CLICK[1] - val * 50
        self.changed()

    def load(self):
        self._v = {
            "left": kread(*INPUT, "XLbInptLeftHanded", "false") == "true",
            "accel": float(kread(*INPUT, "XLbInptPointerAcceleration", 0) or 0),
            "flat": kread(*INPUT, "XLbInptAccelProfileFlat",
                          kread(*INPUT, "X11LibInputXAccelProfileFlat", "false")) == "true",
            "natural": kread(*INPUT, "XLbInptNaturalScroll", "false") == "true",
            "dbl": int(kread("kdeglobals", "KDE", "DoubleClickInterval", 400) or 400),
            "lines": int(kread("kdeglobals", "KDE", "WheelScrollLines", 3) or 3),
            "cursor": kread(*INPUT, "cursorTheme", "breeze_cursors"),
            "csize": int(kread(*INPUT, "cursorSize", 24) or 24),
        }
        v = self._v
        self.left_handed.setChecked(v["left"])
        self.dbl.setValue(round((DOUBLE_CLICK[1] - min(max(v["dbl"], DOUBLE_CLICK[0]), DOUBLE_CLICK[1])) / 50))
        self.folder.interval = v["dbl"]
        self.speed.setValue(round((v["accel"] + 1) * 10))
        # the sliders snap to steps: remember where they started, so an untouched slider
        # doesn't rewrite a value set elsewhere (e.g. 425 ms) when something else is applied
        self._slider_pos = {"dbl": self.dbl.value(), "speed": self.speed.value()}
        self.precision.setChecked(not v["flat"])
        self.natural.setChecked(v["natural"])
        self.lines.setValue(v["lines"])
        self.scheme.clear()
        for name, title in sorted(cursor_themes().items(), key=lambda t: t[1].lower()):
            self.scheme.addItem(title, name)
        i = self.scheme.findData(v["cursor"])
        if i < 0:
            self.scheme.addItem(v["cursor"], v["cursor"])
            i = self.scheme.count() - 1
        self.scheme.setCurrentIndex(i)
        self._scheme_changed()               # the preview is filled before the window shows
        j = self.size.findData(v["csize"])
        if j < 0:
            self.size.addItem(f"{v['csize']} pixels", v["csize"])
            j = self.size.count() - 1
        self.size.setCurrentIndex(j)

    def apply_changes(self):
        v, cmds, input_changed = self._v, [], False
        accel = round(self.speed.value() / 10 - 1, 1)
        for key, new, old in (("XLbInptLeftHanded", self.left_handed.isChecked(), v["left"]),
                              ("XLbInptAccelProfileFlat", not self.precision.isChecked(), v["flat"]),
                              ("XLbInptNaturalScroll", self.natural.isChecked(), v["natural"])):
            if new != old:
                cmds.append(kwrite_cmd(*INPUT, key, new))
                input_changed = True
        if self.speed.value() != self._slider_pos["speed"]:
            cmd = kwrite_cmd(*INPUT, "XLbInptPointerAcceleration", accel)
            if "--" not in cmd:          # "-0.5" would be taken for options by kwriteconfig6
                cmd.insert(-1, "--")
            cmds.append(cmd)
            input_changed = True
        if input_changed:
            cmds.append(["kcminit", "kcm_mouse"])           # applies kcminputrc to the devices
        dbl = DOUBLE_CLICK[1] - self.dbl.value() * 50
        if self.dbl.value() != self._slider_pos["dbl"]:
            cmds.append(kwrite_cmd("kdeglobals", "KDE", "DoubleClickInterval", dbl, notify=True))
        if self.lines.value() != v["lines"]:
            cmds.append(kwrite_cmd("kdeglobals", "KDE", "WheelScrollLines", self.lines.value(), notify=True))
        theme, size = self.scheme.currentData(), self.size.currentData()
        if theme != v["cursor"] or size != v["csize"]:
            cmds.append(["plasma-apply-cursortheme", theme, "--size", str(size)])
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
