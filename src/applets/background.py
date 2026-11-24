# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop Background (Windows Vista / 7 style).

Opens already showing the current wallpaper's location with the current picture selected
and scrolled into view; thumbnails fill in progressively so the window appears at once.
Applies with plasma-apply-wallpaperimage (desktop) and kscreenlockerrc (lock screen).
The current wallpaper is read from the desktop containment's
[Containments][n][Wallpaper][org.kde.image][General] Image= / FillMode= in the shell's
appletsrc (FillMode is QML Image.FillMode; Plasma's default is PreserveAspectCrop)."""
import glob
import json
import os
import re

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QLabel, QListWidget,
                             QListWidgetItem)

from applets.base import AppletDialog
from style import COLOR, SIZE, SPACE
from ui import EvenGrid, form_grid, gap, kwrite_cmd, text_label
import distro

THUMB = QSize(*SIZE["thumbnail"])
# Windows label, QML Image.FillMode (stored in appletsrc), plasma-apply-wallpaperimage --fill-mode
POSITIONS = [("Fill", 2, "preserveAspectCrop"), ("Fit", 1, "preserveAspectFit"),
             ("Stretch", 0, "stretch"), ("Tile", 3, "tile"), ("Center", 6, "pad")]
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".svg")
BROWSE = "__browse__"


def config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def current_wallpaper():
    """(path, fill_mode) of the desktop containment's wallpaper, from the shell's appletsrc."""
    shell = os.environ.get("PLASMA_DEFAULT_SHELL", "org.kde.plasma.desktop")
    path = os.path.join(config_home(), f"plasma-{shell}-appletsrc")
    if not os.path.isfile(path):
        cands = glob.glob(os.path.join(config_home(), "plasma-*-appletsrc"))
        path = cands[0] if cands else None
    if not path:
        return None, 2
    groups, cur = {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("["):
            cur = line
            groups.setdefault(cur, {})
        elif cur and "=" in line:
            k, _, val = line.partition("=")
            groups[cur][k] = val
    for g, kv in groups.items():
        m = re.fullmatch(r"\[Containments\]\[(\d+)\]", g)
        if not m or kv.get("formfactor", "0") != "0" or not kv.get("activityId"):
            continue          # desktops have an activity; panels don't
        img = groups.get(f"[Containments][{m.group(1)}][Wallpaper][org.kde.image][General]", {})
        if img.get("Image"):
            p = img["Image"].removeprefix("file://").rstrip("/")
            return p, int(img.get("FillMode", 2) or 2)
    return None, 2


def wallpaper_dirs():
    """The wallpapers folders in XDG data dirs (user's first), without duplicates."""
    data = [os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))] + \
        os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    seen, out = set(), []
    for d in data:
        w = os.path.join(d, "wallpapers")
        if os.path.isdir(w) and os.path.realpath(w) not in seen:
            seen.add(os.path.realpath(w))
            out.append(w)
    return out


def package_image(pkg, target=(1920, 1080)):
    """Best image of a wallpaper package for `target` size (closest area)."""
    imgs = glob.glob(os.path.join(pkg, "contents", "images", "*"))
    best, best_d = None, None
    for f in imgs:
        m = re.match(r"(\d+)x(\d+)", os.path.basename(f))
        if not m:
            continue
        d = abs(int(m.group(1)) * int(m.group(2)) - target[0] * target[1])
        if best_d is None or d < best_d:
            best, best_d = f, d
    return best or (imgs[0] if imgs else None)


def package_name(pkg):
    try:
        with open(os.path.join(pkg, "metadata.json"), encoding="utf-8") as f:
            return json.load(f)["KPlugin"]["Name"]
    except (OSError, ValueError, KeyError):
        return os.path.basename(pkg)


def collect(location):
    """[(apply_path, thumbnail_source, title)] for a location id or folder."""
    items = []
    if location == "system":
        for d in wallpaper_dirs():
            for name in sorted(os.listdir(d)):
                p = os.path.join(d, name)
                if os.path.isdir(os.path.join(p, "contents")):
                    src = package_image(p)
                    if src:
                        items.append((p, src, package_name(p)))
                elif name.lower().endswith(IMAGE_EXT):
                    items.append((p, p, os.path.splitext(name)[0]))
    else:
        for root, dirs, files in os.walk(location):
            dirs[:] = [x for x in sorted(dirs) if not x.startswith(".")]
            for f in sorted(files):
                if f.lower().endswith(IMAGE_EXT):
                    p = os.path.join(root, f)
                    items.append((p, p, os.path.splitext(f)[0]))
            if root.count(os.sep) - location.count(os.sep) >= 2:   # Pictures/<album>/<album> deep
                dirs[:] = []
    items.sort(key=lambda t: t[2].lower())
    return items


def thumbnail(src):
    """A THUMB-sized icon: the picture scaled to cover the cell and cropped to its centre."""
    r = QImageReader(src)
    r.setAutoTransform(True)
    s = r.size()
    if s.isValid() and s.width() > 0:
        r.setScaledSize(s.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
    img = r.read()
    pm = QPixmap(THUMB)
    pm.fill(QColor(COLOR["canvas"]))
    if not img.isNull():
        p = QPainter(pm)
        x = (img.width() - THUMB.width()) // 2
        y = (img.height() - THUMB.height()) // 2
        p.drawImage(0, 0, img, x, y, THUMB.width(), THUMB.height())
        p.end()
    return QIcon(pm)


class DesktopBackground(AppletDialog):
    ID = "background"
    TITLE = "Desktop Background"
    ICON = "preferences-desktop-wallpaper"
    ADVANCED = "kcm:kcm_wallpaper"
    REPLACES = ["kcm_wallpaper"]
    TABBED = False
    SIZE = "dialog_wide"

    def build(self):
        self.resize(760, 600)
        _, v = self.new_page(self.page)
        self.heading(v, "Choose a desktop background",
                     "Click a picture to make it your desktop background.")
        g = form_grid()
        g.addWidget(QLabel("Picture location:"), 0, 0)
        self.location = QComboBox()
        g.addWidget(self.location, 0, 1)
        g.setColumnStretch(2, 1)
        v.addLayout(g)

        self.grid = EvenGrid(THUMB, (THUMB.width() + SPACE["unrelated"], THUMB.height() + 3 * SPACE["section"]))
        self.grid.setWordWrap(True)
        self.grid.currentItemChanged.connect(lambda *_: self.changed())
        v.addWidget(self.grid, 1)

        gap(v)
        g2 = form_grid()
        g2.addWidget(QLabel("How should the picture be positioned?"), 0, 0)
        self.position = QComboBox()
        for label, mode, _ in POSITIONS:
            self.position.addItem(label, mode)
        self.position.currentIndexChanged.connect(self.changed)
        g2.addWidget(self.position, 0, 1)
        g2.setColumnStretch(2, 1)
        v.addLayout(g2)
        self.lock = QCheckBox("Use this picture on the lock screen too")
        self.lock.toggled.connect(self.changed)
        v.addWidget(self.lock)

        self._pending, self._timer = [], QTimer(self, interval=0)
        self._timer.timeout.connect(self._thumb_batch)

    # --- locations ----------------------------------------------------------------------
    def _fill_locations(self, current):
        self.location.blockSignals(True)
        self.location.clear()
        self.location.addItem(QIcon.fromTheme("preferences-desktop-wallpaper"), f"{distro.NAME} Wallpapers", "system")
        pics = os.path.expanduser("~/Pictures")
        try:
            import subprocess
            pics = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True).stdout.strip() or pics
        except OSError:
            pass
        if os.path.isdir(pics):
            self.location.addItem(QIcon.fromTheme("folder-pictures"), "Pictures", pics)
        # the folder of the current picture, if it is somewhere else
        if current and not any(current.startswith(d) for d in wallpaper_dirs()) and not current.startswith(pics):
            folder = current if os.path.isdir(current) else os.path.dirname(current)
            self.location.addItem(QIcon.fromTheme("folder"), os.path.basename(folder) or folder, folder)
        self.location.addItem(QIcon.fromTheme("document-open-folder"), "Browse…", BROWSE)
        self.location.blockSignals(False)
        try:
            self.location.currentIndexChanged.disconnect()
        except TypeError:
            pass
        self.location.currentIndexChanged.connect(self._location_changed)

    def _location_for(self, path):
        """The location (combo data) holding a picture; the system wallpapers otherwise."""
        if not path:
            return "system"
        for i in range(self.location.count()):
            d = self.location.itemData(i)
            if d not in ("system", BROWSE) and path.startswith(d):
                return d
        return "system"

    def _location_changed(self, i):
        loc = self.location.itemData(i)
        if loc == BROWSE:
            folder = QFileDialog.getExistingDirectory(self, "Browse for a folder of pictures",
                                                      os.path.expanduser("~"))
            if not folder:
                self.location.setCurrentIndex(0)
                return
            self.location.blockSignals(True)
            self.location.insertItem(self.location.count() - 1, QIcon.fromTheme("folder"),
                                     os.path.basename(folder) or folder, folder)
            self.location.setCurrentIndex(self.location.count() - 2)
            self.location.blockSignals(False)
            loc = folder
        self._show(loc, select=self._selected_path())

    # --- grid --------------------------------------------------------------------------
    def _show(self, location, select=None):
        self._timer.stop()
        self.grid.clear()
        placeholder = QPixmap(THUMB)
        placeholder.fill(QColor(COLOR["canvas"]))
        ph = QIcon(placeholder)
        self._pending = []
        sel_item = None
        for path, src, title in collect(location):
            it = QListWidgetItem(ph, title)
            it.setData(Qt.ItemDataRole.UserRole, path)
            it.setToolTip(path)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.grid.addItem(it)
            self._pending.append((it, src))
            if select and os.path.realpath(path) == os.path.realpath(select):
                sel_item = it
        if sel_item is not None:
            # thumbnail the selected picture first, then the rest in reading order
            self._pending.sort(key=lambda t: t[0] is not sel_item)
            self.grid.setCurrentItem(sel_item)
            QTimer.singleShot(0, lambda: self.grid.scrollToItem(sel_item, QListWidget.ScrollHint.PositionAtCenter))
        if not self._pending:
            it = QListWidgetItem("There are no pictures in this location.")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.grid.addItem(it)
        self._timer.start()

    def _thumb_batch(self):
        for _ in range(4):
            if not self._pending:
                self._timer.stop()
                return
            it, src = self._pending.pop(0)
            it.setIcon(thumbnail(src))

    def _selected_path(self):
        it = self.grid.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    # --- state ---------------------------------------------------------------------------
    def load(self):
        self._path, mode = current_wallpaper()
        self._mode = mode
        self._fill_locations(self._path)
        loc = self._location_for(self._path)
        self.location.blockSignals(True)
        self.location.setCurrentIndex(max(self.location.findData(loc), 0))
        self.location.blockSignals(False)
        self._show(loc, select=self._path)
        self.position.setCurrentIndex(max(self.position.findData(mode), 0))
        self.lock.setChecked(False)

    def apply_changes(self):
        path = self._selected_path() or self._path
        mode = self.position.currentData()
        if not path:
            return []
        fill = next(name for _, m, name in POSITIONS if m == mode)
        cmds = []
        if path != self._path or mode != self._mode:
            cmds.append(["plasma-apply-wallpaperimage", path, "--fill-mode", fill])
        if self.lock.isChecked():
            img = package_image(path) if os.path.isdir(path) else path
            if img:
                grp = ["Greeter", "Wallpaper", "org.kde.image", "General"]
                cmds.append(kwrite_cmd("kscreenlockerrc", grp, "Image", "file://" + img))
                cmds.append(kwrite_cmd("kscreenlockerrc", grp, "PreviewImage", "file://" + img))
        return cmds

    def after_apply(self):
        self._path = self._selected_path() or self._path
        self._mode = self.position.currentData()
