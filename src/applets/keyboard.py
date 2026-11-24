# SPDX-License-Identifier: GPL-3.0-or-later
"""Keyboard Properties (Windows style): character repeat, NumLock and input languages.

Same settings as KDE's keyboard module (plasma-desktop kcms/keyboard, Plasma/6.6):
- kcminputrc [Keyboard] RepeatDelay (ms), RepeatRate (per second), KeyRepeat
  ("repeat"/"nothing"/"accent"), NumLock (0 on, 1 off, 2 leave) - on X11 applied right
  away like the keyboard daemon does (xset r rate).
- kxkbrc [Layout] Use, LayoutList, VariantList, DisplayNames - written with change
  notification; the keyboard daemon (KConfigWatcher on [Layout]) re-applies the layouts.
Layout names come from X11's catalog (/usr/share/X11/xkb/rules/base.lst)."""
import os
import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QComboBox, QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QPushButton, QSlider)

from applets.base import AppletDialog
from style import SIZE
from ui import gap, hbox, kread, kwrite_cmd, text_label, vbox
import distro

BASE_LST = "/usr/share/X11/xkb/rules/base.lst"
DELAYS = [1000, 750, 500, 250]        # Windows' four repeat-delay steps (Long -> Short), ms
NUMLOCK = [(0, "On"), (1, "Off"), (2, "Leave unchanged")]


def xkb_catalog():
    """-> ({layout: name}, {(layout, variant): name})"""
    layouts, variants, section = {}, {}, None
    try:
        for line in open(BASE_LST, encoding="utf-8", errors="replace"):
            if line.startswith("!"):
                section = line[1:].strip()
                continue
            parts = line.strip().split(None, 1)
            if len(parts) < 2:
                continue
            if section == "layout":
                layouts[parts[0]] = parts[1]
            elif section == "variant" and ":" in parts[1]:
                lay, name = parts[1].split(":", 1)
                variants[(lay.strip(), parts[0])] = name.strip()
    except OSError:
        pass
    return layouts, variants


def split_list(value):
    """KConfig list "a,b,c" -> ["a", "b", "c"] ("" -> [])."""
    return [x.strip() for x in value.split(",")] if value else []


class AddLanguageDialog(QDialog):
    """Pick one layout or layout variant from the xkb catalog (with a search filter)."""

    def __init__(self, layouts, variants, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Input Language")
        self.resize(*SIZE["dialog"])
        v = vbox(self, "dialog", "related")
        v.addWidget(text_label("Select the keyboard layout to add.", "body"))
        self.filter = QLineEdit(placeholderText="Search")
        v.addWidget(self.filter)
        self.list = QListWidget()
        entries = [(name, (lay, "")) for lay, name in layouts.items()]
        entries += [(name, key) for key, name in variants.items()]
        for name, key in sorted(entries, key=lambda e: e[0].lower()):
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(it)
        v.addWidget(self.list, 1)
        row = hbox(spacing="related")
        row.addStretch(1)
        ok, cancel = QPushButton("OK"), QPushButton("Cancel")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        v.addLayout(row)
        self.filter.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.filter.setFocus()

    def _filter(self, text):
        t = text.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def choice(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


class KeyboardProperties(AppletDialog):
    ID = "keyboard"
    TITLE = "Keyboard Properties"
    ICON = "preferences-desktop-keyboard"
    ADVANCED = "kcm:kcm_keyboard"
    REPLACES = ["kcm_keyboard"]

    @classmethod
    def available(cls):
        # on Wayland KWin applies these per device; the KDE module is used there
        return os.environ.get("XDG_SESSION_TYPE") == "x11"

    def build(self):
        self.layouts, self.variants = xkb_catalog()
        # --- Speed ------------------------------------------------------------------------
        page, v = self.new_page()
        g = self.group(v, "Character repeat", "preferences-desktop-keyboard")
        for label, attr, left, right, lo, hi in (("Repeat delay:", "delay", "Long", "Short", 0, 3),
                                                 ("Repeat rate:", "rate", "Slow", "Fast", 2, 50)):
            g.addWidget(QLabel(label))
            row = hbox(spacing="related")
            row.addWidget(text_label(left, "caption"))
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setTickPosition(QSlider.TickPosition.TicksBelow)
            s.setTickInterval(1 if attr == "delay" else 4)
            s.valueChanged.connect(self.changed)
            setattr(self, attr, s)
            row.addWidget(s, 1)
            row.addWidget(text_label(right, "caption"))
            g.addLayout(row)
        g.addWidget(QLabel("Click here and hold down a key to test repeat rate (after Apply):"))
        g.addWidget(QLineEdit())
        g2 = self.group(v, "NumLock")
        row = hbox(spacing="related")
        row.addWidget(QLabel(f"Turn on NumLock when {distro.NAME} starts:"))
        self.numlock = QComboBox()
        for val, label in NUMLOCK:
            self.numlock.addItem(label, val)
        self.numlock.currentIndexChanged.connect(self.changed)
        row.addWidget(self.numlock)
        row.addStretch(1)
        g2.addLayout(row)
        v.addStretch(1)
        self.add_tab(page, "Speed", "speed")

        # --- Input languages --------------------------------------------------------------
        page2, v2 = self.new_page()
        self.heading(v2, "Input languages",
                     "Choose the keyboard layouts you type with. The first one is the default.")
        row = hbox(spacing="related")
        self.lang = QListWidget()
        row.addWidget(self.lang, 1)
        col = vbox(spacing="related")
        self.b_add, self.b_remove = QPushButton("Add…"), QPushButton("Remove")
        self.b_up, self.b_down = QPushButton("Move Up"), QPushButton("Move Down")
        for b in (self.b_add, self.b_remove, self.b_up, self.b_down):
            col.addWidget(b)
        col.addStretch(1)
        row.addLayout(col)
        v2.addLayout(row, 1)
        gap(v2)
        v2.addWidget(text_label("Switch between layouts with the language indicator on the taskbar, or with "
                                "Meta+Alt+K.", "secondary"))
        self.b_add.clicked.connect(self._add)
        self.b_remove.clicked.connect(self._remove)
        self.b_up.clicked.connect(lambda: self._move(-1))
        self.b_down.clicked.connect(lambda: self._move(1))
        self.lang.currentRowChanged.connect(lambda *_: self._lang_buttons())
        self.add_tab(page2, "Input Languages", "languages")

    # --- languages ------------------------------------------------------------------------
    def _name(self, lay, var):
        if var:
            return self.variants.get((lay, var), f"{self.layouts.get(lay, lay)} ({var})")
        return self.layouts.get(lay, lay)

    def _add_item(self, lay, var, label=""):
        it = QListWidgetItem(QIcon.fromTheme("input-keyboard"), self._name(lay, var))
        it.setData(Qt.ItemDataRole.UserRole, (lay, var, label))
        self.lang.addItem(it)

    def _entries(self):
        return [self.lang.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lang.count())]

    def _lang_buttons(self):
        r, n = self.lang.currentRow(), self.lang.count()
        self.b_remove.setEnabled(r >= 0 and n > 1)          # always keep one layout
        self.b_up.setEnabled(r > 0)
        self.b_down.setEnabled(0 <= r < n - 1)
        for i in range(n):
            it = self.lang.item(i)
            f = it.font()
            f.setBold(i == 0)                               # the default layout
            it.setFont(f)

    def _add(self):
        d = AddLanguageDialog(self.layouts, self.variants, self)
        if d.exec() and d.choice():
            lay, var = d.choice()
            if (lay, var) not in [(e[0], e[1]) for e in self._entries()]:
                self._add_item(lay, var)
                self.lang.setCurrentRow(self.lang.count() - 1)
                self.changed()

    def _remove(self):
        r = self.lang.currentRow()
        if r >= 0 and self.lang.count() > 1:
            self.lang.takeItem(r)
            self.changed()
            self._lang_buttons()

    def _move(self, delta):
        r = self.lang.currentRow()
        if r < 0 or not 0 <= r + delta < self.lang.count():
            return
        it = self.lang.takeItem(r)
        self.lang.insertItem(r + delta, it)
        self.lang.setCurrentRow(r + delta)
        self.changed()

    # --- state ------------------------------------------------------------------------------
    def load(self):
        self._v = {
            "delay": int(kread("kcminputrc", "Keyboard", "RepeatDelay", 600) or 600),
            "rate": float(kread("kcminputrc", "Keyboard", "RepeatRate", 25) or 25),
            "numlock": int(kread("kcminputrc", "Keyboard", "NumLock", 2) or 2),
            "use": kread("kxkbrc", "Layout", "Use", "false") == "true",
            "layouts": split_list(kread("kxkbrc", "Layout", "LayoutList", "")),
            "variants": split_list(kread("kxkbrc", "Layout", "VariantList", "")),
            "names": split_list(kread("kxkbrc", "Layout", "DisplayNames", "")),
        }
        v = self._v
        self.delay.setValue(min(range(len(DELAYS)), key=lambda i: abs(DELAYS[i] - v["delay"])))
        self.rate.setValue(round(v["rate"]))
        # the sliders snap to steps: remember where they started, so an untouched slider
        # doesn't rewrite e.g. KDE's default 600 ms as 500 ms when something else is applied
        self._slider_pos = (self.delay.value(), self.rate.value())
        self.numlock.setCurrentIndex(max(self.numlock.findData(v["numlock"]), 0))
        self.lang.clear()
        layouts = v["layouts"] if v["use"] and v["layouts"] else self._current_xkb()
        for i, lay in enumerate(layouts):
            var = v["variants"][i] if i < len(v["variants"]) else ""
            label = v["names"][i] if i < len(v["names"]) else ""
            self._add_item(lay, var, label)
        self.lang.setCurrentRow(0)
        self._lang_buttons()
        self._orig_layouts = self._entries()

    @staticmethod
    def _current_xkb():
        """Layouts the X server uses now (when kxkbrc has none of its own)."""
        from ui import run
        ok, out, _ = run(["setxkbmap", "-query"])
        for line in out.splitlines():
            if line.startswith("layout:"):
                return split_list(line.split(":", 1)[1].strip())
        return ["us"]

    def apply_changes(self):
        v, cmds = self._v, []
        delay, rate = DELAYS[self.delay.value()], self.rate.value()
        kb = ("kcminputrc", "Keyboard")
        if (self.delay.value(), self.rate.value()) != self._slider_pos:
            cmds.append(kwrite_cmd(*kb, "RepeatDelay", delay, notify=True))
            cmds.append(kwrite_cmd(*kb, "RepeatRate", rate, notify=True))
            if shutil.which("xset"):     # optional: a missing xset must not abort the other changes
                cmds.append(["xset", "r", "rate", str(delay), str(rate)])     # like the keyboard daemon
        if self.numlock.currentData() != v["numlock"]:
            cmds.append(kwrite_cmd(*kb, "NumLock", self.numlock.currentData(), notify=True))
        entries = self._entries()
        # also write when kxkbrc wasn't in use yet but several layouts are listed (from setxkbmap)
        if entries != self._orig_layouts or not v["use"] and len(entries) > 1:
            lay = ",".join(e[0] for e in entries)
            var = ",".join(e[1] for e in entries)
            names = ",".join(e[2] for e in entries)
            lo = ("kxkbrc", "Layout")
            cmds += [kwrite_cmd(*lo, "Use", True), kwrite_cmd(*lo, "LayoutList", lay),
                     kwrite_cmd(*lo, "VariantList", var), kwrite_cmd(*lo, "DisplayNames", names, notify=True)]
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
