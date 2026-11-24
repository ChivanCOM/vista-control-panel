# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop Icon Settings (Windows Vista: Personalization > Change desktop icons).

Shows or hides Vista's desktop icons - Computer, the user's files, Network, Recycle Bin and
Control Panel - and changes their pictures. The icons are marked link files in the desktop
folder (see deskicons.py); the desktop picks changes up by itself."""
import shutil

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QListView, QListWidget, QListWidgetItem, QPushButton

import deskicons
from applets.base import AppletDialog
from style import ICON, SPACE
from ui import hbox, run


class DesktopIcons(AppletDialog):
    """Check boxes for the icons, and their pictures (Change Icon via kdialog, Restore Default)."""
    ID = "desktopicons"
    TITLE = "Desktop Icon Settings"
    ICON = "preferences-desktop"

    def build(self):
        page, v = self.new_page()
        g = self.group(v, "Desktop icons")
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE["section"])
        grid.setVerticalSpacing(SPACE["related"])
        self.checks = {}
        # Vista's order: Computer, User's Files, Network down the left; Recycle Bin, Control Panel right
        for (icon_id, row, col) in (("computer", 0, 0), ("user", 1, 0), ("network", 2, 0),
                                    ("recyclebin", 0, 1), ("controlpanel", 1, 1)):
            cb = QCheckBox(deskicons.BY_ID[icon_id][1])
            cb.toggled.connect(self.changed)
            grid.addWidget(cb, row, col)
            self.checks[icon_id] = cb
        grid.setColumnStretch(2, 1)
        g.addLayout(grid)

        # the pictures, as in Vista: each icon, the Recycle Bin full and empty
        self.pictures = QListWidget()
        self.pictures.setViewMode(QListView.ViewMode.IconMode)
        self.pictures.setIconSize(QSize(ICON["large"], ICON["large"]))
        self.pictures.setMovement(QListView.Movement.Static)
        self.pictures.setResizeMode(QListView.ResizeMode.Adjust)
        self.pictures.setWordWrap(True)
        self.pictures.setSpacing(SPACE["related"])
        self.pictures.setFixedHeight(ICON["large"] * 2 + SPACE["section"] * 2)
        self.pictures.currentItemChanged.connect(self._selection)
        v.addWidget(self.pictures)

        row = hbox(spacing="related")
        row.addStretch(1)
        self.change = QPushButton("Change Icon...")
        self.change.clicked.connect(self._change_icon)
        self.change.setVisible(bool(shutil.which("kdialog")))
        self.restore = QPushButton("Restore Default")
        self.restore.clicked.connect(self._restore)
        row.addWidget(self.change)
        row.addWidget(self.restore)
        v.addLayout(row)
        v.addStretch(1)
        self.add_tab(page, "Desktop Icons", "icons")

    # pictures: (icon id, "icon" or "empty") -> chosen icon name
    def _fill_pictures(self):
        self.pictures.clear()
        for icon_id, label, icon, empty, _ in deskicons.ICONS:
            name = deskicons.display_name(icon_id)
            for which, default in (("icon", icon), ("empty", empty)):
                if default is None:
                    continue
                text = name
                if icon_id == "recyclebin":
                    text = f"{name} ({'full' if which == 'icon' else 'empty'})"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, (icon_id, which))
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                self.pictures.addItem(item)
        self._show_icons()
        self.pictures.setCurrentRow(0)

    def _show_icons(self):
        for i in range(self.pictures.count()):
            item = self.pictures.item(i)
            key = item.data(Qt.ItemDataRole.UserRole)
            item.setIcon(QIcon.fromTheme(self.icons[key]))

    def _selection(self, *_):
        item = self.pictures.currentItem()
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        icon_id, which = key
        default = deskicons.BY_ID[icon_id][2 if which == "icon" else 3]
        self.restore.setEnabled(self.icons[key] != default)

    def _change_icon(self):
        item = self.pictures.currentItem()
        if item is None:
            return
        ok, out, _ = run(["kdialog", "--title", "Change Icon", "--geticon", "Desktop", "Applications"])
        name = out.strip()
        if ok and name:
            self.icons[item.data(Qt.ItemDataRole.UserRole)] = name
            self._show_icons()
            self._selection()
            self.changed()

    def _restore(self):
        item = self.pictures.currentItem()
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        icon_id, which = key
        self.icons[key] = deskicons.BY_ID[icon_id][2 if which == "icon" else 3]
        self._show_icons()
        self._selection()
        self.changed()

    def load(self):
        self._state = deskicons.state()
        self.icons = {}
        for icon_id, (shown, icon, empty) in self._state.items():
            self.checks[icon_id].setChecked(shown)
            self.icons[(icon_id, "icon")] = icon
            if empty:
                self.icons[(icon_id, "empty")] = empty
        self._fill_pictures()

    def apply_changes(self):
        # the link files are written right here (no commands): plain file writes in the
        # user's desktop folder, which the desktop notices by itself
        for icon_id, (shown, icon, empty) in self._state.items():
            want = self.checks[icon_id].isChecked()
            new_icon = self.icons[(icon_id, "icon")]
            new_empty = self.icons.get((icon_id, "empty"))
            if want and (not shown or new_icon != icon or new_empty != empty):
                deskicons.write(icon_id, new_icon, new_empty)
            elif not want and shown:
                deskicons.remove(icon_id)
        return []

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
