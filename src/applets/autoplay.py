# SPDX-License-Identifier: GPL-3.0-or-later
"""AutoPlay (Windows style): what happens when you insert a USB drive, memory card or DVD.

Settings are shared with the AutoPlay helper (autoplay_agent.py) through autoplay.py:
the AutoPlay settings file (see autoplay.py) [General] Enabled, [Handlers] <kind>.
"Use AutoPlay" also turns on KDE's device automounter (kded_device_automounterrc), because AutoPlay acts on drives
once they are mounted; turning it off returns mounting to KDE's default (on click)."""
import os
import sys

from PyQt6.QtCore import QProcess, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton

import autoplay as AP
from applets.base import AppletDialog
from style import ICON
from ui import form_grid, gap, hbox, icon_label, section, text_label

ASK, OPEN, NONE = "ask", "open", "none"
AGENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "autoplay_agent.py")


class AutoPlay(AppletDialog):
    """One row per kind of content: a program, open folder, no action or ask."""
    ID = "autoplay"
    TITLE = "AutoPlay"
    ICON = "preferences-desktop-multimedia"
    ADVANCED = "kcm:kcm_device_automounter"
    REPLACES = ["kcm_device_automounter"]
    TABBED = False
    SIZE = "dialog_wide"

    def build(self):
        _, v = self.new_page(self.page)
        self.heading(v, "Choose what happens when you insert each type of media or device")
        self.use = QCheckBox("Use AutoPlay for all media and devices")
        self.use.toggled.connect(self.changed)
        self.use.toggled.connect(self._enable_rows)
        v.addWidget(self.use)
        gap(v, "section")
        section(v, "Media")
        self.grid = form_grid()
        v.addLayout(self.grid)
        self.combos = {}
        for r, (kind, label, *_rest, icon) in enumerate(AP.TYPES):
            self.grid.addWidget(icon_label(icon, "medium"), r, 0)
            self.grid.addWidget(QLabel(label), r, 1)
            cb = QComboBox()
            cb.setIconSize(QSize(ICON["small"], ICON["small"]))
            for sid, name, ic in AP.apps_for(kind):
                cb.addItem(QIcon(ic) if os.path.isabs(ic) else QIcon.fromTheme(ic),
                           f"{AP.VERBS[kind]} using {name}", sid)
            cb.addItem(QIcon.fromTheme("system-file-manager"), "Open folder to view files using Dolphin", OPEN)
            cb.addItem(QIcon.fromTheme("dialog-cancel"), "Take no action", NONE)
            cb.addItem(QIcon.fromTheme("dialog-question"), "Ask me every time", ASK)
            cb.currentIndexChanged.connect(self.changed)
            self.grid.addWidget(cb, r, 2)
            self.combos[kind] = cb
        self.grid.setColumnStretch(2, 1)
        gap(v, "section")
        v.addWidget(text_label("AutoPlay works with USB drives, memory cards, external disks and DVDs.", "secondary"))
        v.addStretch(1)
        row = hbox(spacing="related")
        reset = QPushButton("Reset all defaults")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        v.addLayout(row)

    def _enable_rows(self, on):
        for i in range(self.grid.count()):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setEnabled(on)

    def _reset(self):
        for cb in self.combos.values():
            cb.setCurrentIndex(cb.findData(ASK))
        self.use.setChecked(True)

    # --- state ------------------------------------------------------------------------------
    def load(self):
        self._v = {"use": AP.enabled() and AP.automount_on()}
        self.use.setChecked(self._v["use"])
        self._enable_rows(self._v["use"])
        for kind, cb in self.combos.items():
            h = AP.handler(kind)
            i = cb.findData(h)
            if i < 0:                       # a program that is no longer installed
                i = cb.findData(ASK)
            cb.setCurrentIndex(i)
            self._v[kind] = cb.currentData()

    def apply_changes(self):
        cmds = []
        use = self.use.isChecked()
        if use != self._v["use"]:
            cmds.append(AP.kwrite_cmd(AP.RC, "General", "Enabled", use))
            cmds += AP.automount_cmds(use)
        for kind, cb in self.combos.items():
            if cb.currentData() != self._v[kind]:
                cmds.append(AP.set_handler_cmd(kind, cb.currentData()))
        return cmds

    def after_apply(self):
        if self.use.isChecked():
            # make sure the helper runs now, not only from the next log-in (it keeps one copy)
            QProcess.startDetached(sys.executable, [AGENT])
        self._loading = True
        self.load()
        self._loading = False
