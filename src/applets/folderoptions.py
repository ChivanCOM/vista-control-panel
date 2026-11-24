# SPDX-License-Identifier: GPL-3.0-or-later
"""Folder Options (Windows style) for Dolphin and the desktop.

- Click items: kdeglobals [KDE] SingleClick (all KDE apps and the desktop; notified).
- Dolphin (dolphin 25.12 src/settings/dolphin_generalsettings.kcfg): dolphinrc [General]
  ShowFullPathInTitlebar, ShowFullPath, ShowToolTips, ShowStatusBar (0 Small, 1 FullWidth -
  Explorer's bar across the bottom, 2 Disabled),
  ShowSelectionToggle, BrowseThroughArchives.
- Folder views (global view properties, GlobalViewProps=true is Dolphin's default):
  ~/.local/share/dolphin/view_properties/global/.directory [Settings] HiddenFilesShown,
  [Dolphin] PreviewsShown, Version=4. A .directory file there is read in preference to
  the folder's view-properties attribute (src/views/viewproperties.cpp)."""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QButtonGroup, QPushButton, QRadioButton, QTreeWidget, QTreeWidgetItem

from applets.base import AppletDialog
from style import SPACE
from ui import Link, gap, hbox, kread, kwrite_cmd, text_label
import distro

GLOBAL_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
                          "dolphin", "view_properties", "global")
GLOBAL_FILE = os.path.join(GLOBAL_DIR, ".directory")
VIEW_PROPS_VERSION = 4
VIEW_PROPS_XATTR = "user.kde.fm.viewproperties#1"
CHECKED, UNCHECKED = Qt.CheckState.Checked, Qt.CheckState.Unchecked

# (key, label, kind, default) - kind: "rc" dolphinrc [General] bool, "status", "previews"
ADVANCED = [
    ("previews", "Always show icons, never thumbnails", "previews", False),
    ("ShowFullPathInTitlebar", "Display the full path in the title bar", "rc", False),
    ("ShowFullPath", "Display the full path in the address bar", "rc", False),
    ("ShowToolTips", "Show pop-up description for folder and desktop items", "rc", False),
    ("status", "Show status bar", "status", False),   # Vista: off; the Details Pane shows the same
    ("ShowSelectionToggle", "Use check boxes to select items", "rc", True),
    ("BrowseThroughArchives", "Open compressed files (ZIP, …) like folders", "rc", False),
]


def _global_xattr():
    """Dolphin's global view properties as stored in the folder's xattr ("" if none)."""
    try:
        return os.getxattr(GLOBAL_DIR, VIEW_PROPS_XATTR).decode(errors="replace")
    except OSError:
        return ""


def global_view(key, group, default):
    """A global view property: from the .directory file if there is one, else the xattr."""
    if os.path.exists(GLOBAL_FILE):
        return kread(GLOBAL_FILE, group, key, default)
    raw = _global_xattr()
    if not raw:
        return default
    section = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]")
        elif section == group and line.startswith(key + "="):
            return line.split("=", 1)[1]
    return default


class FolderOptions(AppletDialog):
    """General (single/double click), View (Dolphin options, hidden files) and Search tabs."""
    ID = "folderoptions"
    TITLE = "Folder Options"
    ICON = "folder"
    ADVANCED = "app:dolphin"

    def build(self):
        # --- General ----------------------------------------------------------------------
        page, v = self.new_page()
        g = self.group(v, "Click items as follows", "preferences-desktop-mouse", "medium")
        self.clicks = QButtonGroup(self)
        self.single = QRadioButton("Single-click to open an item (point to select)")
        self.double = QRadioButton("Double-click to open an item (single-click to select)")
        for rb in (self.single, self.double):
            self.clicks.addButton(rb)
            rb.toggled.connect(self.changed)
            g.addWidget(rb)
        g.addWidget(text_label("Applies to Dolphin, the desktop and other programs.", "secondary"))
        v.addStretch(1)
        self.add_tab(page, "General", "general")

        # --- View --------------------------------------------------------------------------
        page2, v2 = self.new_page()
        g2 = self.group(v2, "Folder views", "folder", "medium")
        g2.addWidget(text_label("These settings apply to all folders. Changes show in Dolphin windows "
                                "you open after clicking Apply.", "body"))
        v2.addWidget(text_label("Advanced settings:", "body"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(SPACE["section"] + SPACE["link_gap"])
        root = QTreeWidgetItem(["Files and Folders"])
        root.setIcon(0, QIcon.fromTheme("folder"))
        self.tree.addTopLevelItem(root)
        self.items = {}
        for key, label, _kind, _default in ADVANCED:
            it = QTreeWidgetItem([label])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            root.addChild(it)
            self.items[key] = it
        hidden = QTreeWidgetItem(["Hidden files and folders"])
        hidden.setIcon(0, QIcon.fromTheme("folder"))
        root.addChild(hidden)
        self.hide_hidden = QTreeWidgetItem(["Don’t show hidden files and folders"])
        self.show_hidden = QTreeWidgetItem(["Show hidden files and folders"])
        for it in (self.hide_hidden, self.show_hidden):
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            hidden.addChild(it)
        self.tree.expandAll()
        self.tree.itemChanged.connect(self._item_changed)
        v2.addWidget(self.tree, 1)
        row = hbox(spacing="related")
        row.addStretch(1)
        restore = QPushButton("Restore Defaults")
        restore.clicked.connect(self._defaults)
        row.addWidget(restore)
        v2.addLayout(row)
        self.add_tab(page2, "View", "view")

        # --- Search ------------------------------------------------------------------------
        page3, v3 = self.new_page()
        g3 = self.group(v3, "What to search", "system-search", "medium")
        g3.addWidget(text_label(f"{distro.NAME} indexes the files in your personal folders so you can find them "
                                "quickly from the Start menu and Dolphin.", "body"))
        link = Link("Change indexing options", "link")
        link.clicked.connect(self._indexing)
        g3.addWidget(link)
        v3.addStretch(1)
        self.add_tab(page3, "Search", "search")

    def _indexing(self):
        import applets
        from PyQt6.QtCore import QProcess
        QProcess.startDetached("kcmshell6", ["kcm_baloofile"])

    def _item_changed(self, item, _col):
        # the hidden-files pair behaves like radio buttons
        if item in (self.hide_hidden, self.show_hidden) and item.checkState(0) == CHECKED:
            other = self.show_hidden if item is self.hide_hidden else self.hide_hidden
            self.tree.blockSignals(True)
            other.setCheckState(0, UNCHECKED)
            self.tree.blockSignals(False)
        elif item in (self.hide_hidden, self.show_hidden):
            self.tree.blockSignals(True)
            item.setCheckState(0, CHECKED)          # one of the two is always chosen
            self.tree.blockSignals(False)
            return
        self.changed()

    def _set_state(self, values):
        self.tree.blockSignals(True)
        for key, it in self.items.items():
            it.setCheckState(0, CHECKED if values[key] else UNCHECKED)
        self.show_hidden.setCheckState(0, CHECKED if values["hidden"] else UNCHECKED)
        self.hide_hidden.setCheckState(0, UNCHECKED if values["hidden"] else CHECKED)
        self.tree.blockSignals(False)

    def _defaults(self):
        values = {key: default for key, _l, _k, default in ADVANCED}
        values["hidden"] = False
        self._set_state(values)
        self.double.setChecked(True)
        self.changed()

    # --- state --------------------------------------------------------------------------
    def load(self):
        v = {}
        for key, _label, kind, default in ADVANCED:
            if kind == "rc":
                v[key] = kread("dolphinrc", "General", key, str(default).lower()) == "true"
            elif kind == "status":
                # Dolphin itself writes the enum's name ("Disabled"), we write the number
                v[key] = kread("dolphinrc", "General", "ShowStatusBar", "0").lower() not in ("2", "disabled")
            elif kind == "previews":
                v[key] = global_view("PreviewsShown", "Dolphin", "true") != "true"
        v["hidden"] = global_view("HiddenFilesShown", "Settings", "false") == "true"
        v["single"] = kread("kdeglobals", "KDE", "SingleClick", "false") == "true"
        self._v = v
        self._set_state(v)
        (self.single if v["single"] else self.double).setChecked(True)

    def _current(self):
        cur = {key: self.items[key].checkState(0) == CHECKED for key in self.items}
        cur["hidden"] = self.show_hidden.checkState(0) == CHECKED
        cur["single"] = self.single.isChecked()
        return cur

    def apply_changes(self):
        cur, old, cmds = self._current(), self._v, []
        if cur["single"] != old["single"]:
            cmds.append(kwrite_cmd("kdeglobals", "KDE", "SingleClick", cur["single"], notify=True))
        for key, _label, kind, _default in ADVANCED:
            if cur[key] == old[key]:
                continue
            if kind == "rc":
                cmds.append(kwrite_cmd("dolphinrc", "General", key, cur[key], notify=True))
            elif kind == "status":
                cmds.append(kwrite_cmd("dolphinrc", "General", "ShowStatusBar", 1 if cur[key] else 2, notify=True))
        view_changed = cur["previews"] != old["previews"] or cur["hidden"] != old["hidden"]
        if view_changed:
            os.makedirs(GLOBAL_DIR, exist_ok=True)
            raw = "" if os.path.exists(GLOBAL_FILE) else _global_xattr()
            if raw:
                # a .directory file overrides the xattr completely: start it from the
                # xattr's contents, or the global view mode, sorting etc. would be lost
                tmp = GLOBAL_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(raw)
                os.replace(tmp, GLOBAL_FILE)
            cmds += [kwrite_cmd(GLOBAL_FILE, "Dolphin", "Version", VIEW_PROPS_VERSION),
                     kwrite_cmd(GLOBAL_FILE, "Dolphin", "PreviewsShown", not cur["previews"]),
                     kwrite_cmd(GLOBAL_FILE, "Settings", "HiddenFilesShown", cur["hidden"])]
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
