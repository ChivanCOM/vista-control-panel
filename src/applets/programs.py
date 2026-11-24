# SPDX-License-Identifier: GPL-3.0-or-later
"""Programs and Features (Windows Vista style): "Uninstall or change a program".

Lists programs (packages that put an application in the menu), not libraries: desktop
entries are mapped to their package with one `dpkg -S` call; details come from
dpkg-query (version, Installed-Size, Maintainer, Section) and the package's dpkg file
list date ("Installed On"). Flatpak apps are listed too.

Uninstall goes through PackageKit (packagekit.py), like Discover: first a SIMULATE run
shows exactly what else would be removed; removals that would take a metapackage or a
core desktop component are refused with an explanation. The real removal asks for an
administrator through the UAC prompt."""
import glob
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date

from PyQt6.QtCore import QLocale, QSize, Qt, QTimer
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QMessageBox, QPushButton, QStyle,
                             QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem,
                             QWidget)

import packagekit as pk
import style
from applets.base import TaskWindow
from style import ICON, SIZE, SPACE
from ui import Jobs, Link, form_grid, gap, hbox, icon_label, run, text_label, vbox
import distro

# Removing any of these (or a metapackage) would break the desktop - refuse.
PROTECTED = {
    "plasma-desktop", "plasma-workspace", "kwin-x11", "kwin-wayland", "kwin-common", "sddm",
    "systemsettings", "plasma-discover", "network-manager", "plasma-nm", "sudo", "polkitd",
    "linux-generic", "grub-efi-amd64-signed", "grub-pc", "shim-signed", "pipewire", "wireplumber",
    "dolphin", "konsole", "kio", "plasma-pa", "packagekit", "python3-pyqt6", "kscreen",
    "xserver-xorg-core", "dbus", "systemd", "ubuntu-minimal", "ubuntu-standard",
}
MAX_EXTRA_REMOVALS = 12


@dataclass
class Program:
    key: str                 # package name or flatpak app id
    name: str
    icon: str
    kind: str                # "deb" | "flatpak"
    publisher: str = ""
    version: str = ""
    size_kb: int = 0
    installed: date = None
    section: str = ""
    desktop_files: list = field(default_factory=list)


# ----------------------------------------------------------------------------- data
def _desktop_dirs():
    """System application folders only: per-user entries don't belong to a package."""
    data = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    return [os.path.join(d, "applications") for d in data if d.startswith(("/usr", "/var/lib/flatpak"))]


def _read_desktop(path):
    """[Desktop Entry] keys of a shown application entry, or None (hidden/not an app)."""
    d, in_main = {}, False
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line.startswith("["):
                in_main = line == "[Desktop Entry]"
                continue
            if in_main and "=" in line:
                k, _, v = line.partition("=")
                d.setdefault(k, v)
    except OSError:
        return None
    if d.get("Type") != "Application" or d.get("NoDisplay") == "true" or d.get("Hidden") == "true":
        return None
    return d


def collect_programs():
    """All programs: packages owning a menu entry, plus Flatpak apps -> [Program] by name."""
    entries = {}
    for d in _desktop_dirs():
        for f in glob.glob(os.path.join(d, "**", "*.desktop"), recursive=True):
            real = os.path.realpath(f)
            if real in entries:
                continue
            de = _read_desktop(real)
            if de and de.get("Name"):
                entries[real] = de
    owners = {}
    paths = [p for p in entries if p.startswith("/usr/")]
    for i in range(0, len(paths), 200):        # batches keep the command line short
        # exit status 1 only means some paths aren't packaged; the rest are still listed
        ok, out, _ = run(["dpkg", "-S", *paths[i:i + 200]], timeout=60)
        for line in out.splitlines():
            pkgs, _, path = line.partition(": ")
            if path in entries and "diversion" not in pkgs:
                owners[path] = pkgs.split(",")[0].strip().split(":")[0]
    progs = {}
    for path, pkg in owners.items():
        de = entries[path]
        p = progs.setdefault(pkg, Program(key=pkg, name=de["Name"], icon=de.get("Icon", ""), kind="deb"))
        p.desktop_files.append(path)
        # prefer the entry named like the package as the program's name/icon
        if os.path.basename(path).removesuffix(".desktop").split(".")[-1].lower() == pkg.split("-")[0]:
            p.name, p.icon = de["Name"], de.get("Icon", p.icon)
    if progs:
        ok, out, _ = run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Installed-Size}\t${Maintainer}\t${Section}\n",
                          *progs.keys()], timeout=60)
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 5 or parts[0] not in progs:
                continue
            p = progs[parts[0]]
            p.version = parts[1].split(":", 1)[-1]
            p.size_kb = int(parts[2] or 0)
            p.publisher = parts[3].split("<")[0].strip()
            p.section = parts[4]
            # "Installed On": the file list dpkg (re)wrote; Multi-Arch: same packages use pkg:<arch>.list
            for lst in [f"/var/lib/dpkg/info/{p.key}.list"] + glob.glob(f"/var/lib/dpkg/info/{p.key}:*.list"):
                if os.path.exists(lst):
                    p.installed = date.fromtimestamp(os.path.getmtime(lst))
                    break
    ok, out, _ = run(["flatpak", "list", "--app", "--columns=application,name,version,size,origin"], timeout=30)
    for line in out.splitlines() if ok else []:
        parts = line.split("\t")
        if len(parts) >= 2:
            progs[parts[0]] = Program(key=parts[0], name=parts[1], icon=parts[0], kind="flatpak",
                                      version=parts[2] if len(parts) > 2 else "",
                                      publisher=parts[4] if len(parts) > 4 else "Flatpak")
    return sorted(progs.values(), key=lambda p: p.name.lower())


def upstream_version(v):
    """'4:25.12.3-0ubuntu1' -> '25.12.3', '2.61.3+dfsg-3ubuntu0.1' -> '2.61.3' (as Windows shows it)."""
    v = v.split(":", 1)[-1]
    if "-" in v:
        v = v.rsplit("-", 1)[0]
    for sep in ("+dfsg", "+ds", "~", "+really"):
        v = v.split(sep, 1)[0]
    return v


def human_size(kb):
    if not kb:
        return ""
    mb = kb / 1024
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else (f"{mb:.1f} MB" if mb >= 1 else f"{kb} KB")


class RightPadDelegate(QStyledItemDelegate):
    """Right-aligned text inset from the cell's right edge (Size column), while the row
    background and selection still cover the whole cell."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        widget = opt.widget
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        painter.save()
        painter.setPen(opt.palette.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text))
        painter.drawText(opt.rect.adjusted(0, 0, -SPACE["unrelated"], 0),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), text)
        painter.restore()


class SortItem(QTreeWidgetItem):
    """Sort Size/Installed On by value, not by their text."""

    def __lt__(self, other):
        col = self.treeWidget().sortColumn()
        a, b = self.data(col, Qt.ItemDataRole.UserRole + 1), other.data(col, Qt.ItemDataRole.UserRole + 1)
        if a is not None and b is not None:
            return a < b
        return self.text(col).lower() < other.text(col).lower()


# ----------------------------------------------------------------------------- dialog
class ProgramsAndFeatures(TaskWindow):
    ID = "programs"
    TITLE = "Programs and Features"
    ICON = "system-software-install"
    ADVANCED = "app:plasma-discover --mode Installed"

    @classmethod
    def available(cls):
        return pk.available()

    def build(self):
        self.resize(900, 620)
        self.task_frame()
        self.pane_heading("Tasks")
        for text, argv in (("View installed updates", ["plasma-discover", "--mode", "Update"]),
                           ("Get new programs online", ["plasma-discover"]),
                           ("Software sources", ["software-properties-qt"])):
            if shutil.which(argv[0]):
                self.pane_link(text, lambda a=argv: self.launch(a))
        self.pane_layout.addStretch(1)
        v = self.content_layout
        self.heading(v, "Uninstall or change a program",
                     "To uninstall a program, select it from the list and then click Uninstall or Change.")
        # Vista: the list sits under Explorer's blue command bar and above its details pane
        from ui import CommandBar, DetailsPane
        list_box = vbox(spacing="none")
        bar = CommandBar()
        self.btn_uninstall = bar.add_button("Uninstall")      # Vista: text only
        self.btn_change = bar.add_button("Change")
        self.btn_uninstall.clicked.connect(self._uninstall)
        self.btn_change.clicked.connect(self._change)
        list_box.addWidget(bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Publisher", "Installed On", "Size", "Version"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(ICON["small"] + SPACE["link_gap"], ICON["small"] + SPACE["link_gap"]))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSortingEnabled(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)   # sized in _fit_columns
        self.tree.setItemDelegateForColumn(3, RightPadDelegate(self.tree))
        self.tree.currentItemChanged.connect(lambda *_: self._details())
        self.tree.itemDoubleClicked.connect(lambda *_: self._uninstall())
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        list_box.addWidget(self.tree, 1)
        self.details = DetailsPane()
        list_box.addWidget(self.details)
        frame = QFrame()
        frame.setObjectName("listframe")
        frame.setStyleSheet("QFrame#listframe { border: 1px solid #8e9fb6; }")
        frame.setLayout(list_box)
        v.addWidget(frame, 1)
        self._total = 0
        self.programs = []
        self._busy = False

    # --- list ---------------------------------------------------------------------------
    def load(self):
        self.tree.clear()
        wait = QTreeWidgetItem(["Please wait while the list is populated…"])
        wait.setFlags(Qt.ItemFlag.NoItemFlags)
        self.tree.addTopLevelItem(wait)
        self._buttons()
        QTimer.singleShot(0, self._fill)         # show the window first, then fill it

    def _fill(self):
        self.programs = collect_programs()
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        loc = QLocale()
        total = 0
        for p in self.programs:
            it = SortItem([p.name, p.publisher,
                           loc.toString(p.installed, QLocale.FormatType.ShortFormat) if p.installed else "",
                           human_size(p.size_kb), upstream_version(p.version)])
            it.setIcon(0, QIcon.fromTheme(p.icon, QIcon.fromTheme("application-x-executable"))
                       if not os.path.isabs(p.icon) else QIcon(p.icon))
            it.setData(0, Qt.ItemDataRole.UserRole, p)
            it.setData(2, Qt.ItemDataRole.UserRole + 1, p.installed.toordinal() if p.installed else 0)
            it.setData(3, Qt.ItemDataRole.UserRole + 1, p.size_kb)
            it.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tree.addTopLevelItem(it)
            total += p.size_kb
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._fit_columns()
        self._total = total
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree.setFocus()
        self._details()

    def _fit_columns(self):
        """Content width + a gap per column (the style ignores item padding on right-aligned
        text, so Size would touch Version); columns stay resizable by dragging."""
        hdr = self.tree.header()
        for c in range(1, 5):
            w = max(self.tree.sizeHintForColumn(c), hdr.sectionSizeHint(c))
            hdr.resizeSection(c, w + SPACE["section"])

    def _current(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _buttons(self):
        p = self._current()
        self.btn_uninstall.setEnabled(bool(p) and not self._busy)
        self.btn_change.setEnabled(bool(p) and not self._busy)

    def _details(self):
        """Vista's details pane: the selected program, or with none selected, the totals."""
        p = self._current()
        self._buttons()
        if not p:
            self.details.show_item(QIcon.fromTheme(self.ICON), "Currently installed programs",
                                   [("Total size:", human_size(self._total))],
                                   subtitle=f"{len(self.programs)} programs installed")
            return
        icon = (QIcon.fromTheme(p.icon, QIcon.fromTheme("application-x-executable")) if not os.path.isabs(p.icon)
                else QIcon(p.icon))
        self.details.show_item(icon, p.name, [("Product version:", upstream_version(p.version)),
                                              ("Size:", human_size(p.size_kb)),
                                              ("Package:", p.key)],
                               subtitle=p.publisher)

    # --- actions ------------------------------------------------------------------------------
    def _change(self):
        p = self._current()
        if p:
            # Discover shows the program's page with its options (add-ons, reinstall, ...)
            self.launch(["plasma-discover", "--search", p.name])

    def _uninstall(self):
        """Flatpak: confirm and remove. Packages: resolve -> simulate the removal -> confirm
        (or refuse) in _confirm -> remove; each PackageKit step is asynchronous."""
        p = self._current()
        if not p or self._busy:
            return
        if p.kind == "flatpak":
            if QMessageBox.question(self, self.TITLE, f"Are you sure you want to uninstall {p.name}?") \
                    == QMessageBox.StandardButton.Yes:
                self._set_busy(True, f"Uninstalling {p.name}…")
                self._jobs = Jobs([["flatpak", "uninstall", "-y", "--noninteractive", p.key]], self)
                self._jobs.finished.connect(lambda ok, err: self._done(ok, err, p))
                self._jobs.start()
            return
        if p.key in PROTECTED:
            self._refuse(p, [p.key])
            return
        self._set_busy(True, f"Checking what else {p.name} needs…")
        ids, removed = [], []
        r = pk.Transaction(self)
        r.package.connect(lambda _i, pid, _s: ids.append(pid))

        def resolved(ok, err):
            if not ok or not ids:
                self._set_busy(False)
                QMessageBox.warning(self, self.TITLE, f"{p.name} could not be found.\n\n{err}")
                return
            sim = pk.Transaction(self)
            sim.package.connect(lambda _i, pid, _s: removed.append(pk.package_name(pid)))
            sim.finished.connect(lambda ok2, err2: self._confirm(p, ids, sorted(set(removed)), ok2, err2))
            sim.remove(ids, simulate=True)
            self._sim = sim
        r.finished.connect(resolved)
        r.resolve_installed([p.key])
        self._resolve = r

    def _confirm(self, p, ids, removed, ok, err):
        self._set_busy(False)
        if not ok:
            QMessageBox.warning(self, self.TITLE, f"{p.name} can’t be uninstalled right now.\n\n{err}")
            return
        blocked = [x for x in removed if x in PROTECTED or self._is_meta(x)]
        if blocked or len(removed) > MAX_EXTRA_REMOVALS + 1:
            self._refuse(p, blocked or removed)
            return
        others = [x for x in removed if x != p.key]
        box = QMessageBox(QMessageBox.Icon.Question, self.TITLE, f"Are you sure you want to uninstall {p.name}?",
                          parent=self)
        if others:
            box.setInformativeText("These related components will be removed too:\n" + ", ".join(others))
        yes = box.addButton("Uninstall", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not yes:
            return
        self._set_busy(True, f"Uninstalling {p.name}…")
        t = pk.Transaction(self)
        t.finished.connect(lambda ok2, err2: self._done(ok2, err2, p))
        t.remove(ids, simulate=False)
        self._remove = t

    def _refuse(self, p, packages):
        others = [x for x in packages if x != p.key]
        text = f"{p.name} can\u2019t be uninstalled because {distro.NAME} needs it."
        if others:
            shown = ", ".join(others[:8]) + (" \u2026" if len(others) > 8 else "")
            text += f"\n\nRemoving it would also remove: {shown}"
        QMessageBox.information(self, self.TITLE, text)

    @staticmethod
    def _is_meta(pkg):
        ok, out, _ = run(["dpkg-query", "-W", "-f=${Section}", pkg])
        return ok and out.strip().endswith("metapackages")

    def _set_busy(self, busy, text=""):
        self._busy = busy
        if busy and text:                  # Vista shows progress in the details pane
            self.details.show_item(QIcon.fromTheme(self.ICON), text)
        if busy:
            self.setCursor(Qt.CursorShape.BusyCursor)
        else:
            self.unsetCursor()
        self._buttons()
        if not busy:
            self._details()

    def _done(self, ok, err, p):
        self._set_busy(False)
        if not ok:
            if "authoriz" in err.lower() or "not allowed" in err.lower():
                err = "The change was cancelled or not authorized."
            QMessageBox.warning(self, self.TITLE, f"{p.name} could not be uninstalled.\n\n{err}")
        self.load()
