#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Vista AutoPlay: when a removable drive is inserted (and mounted by KDE's device
automounter), look at what is on it and either do the chosen default or ask - the
Windows AutoPlay window.

Watches /proc/self/mountinfo (the kernel signals changes with POLLPRI) with a slow poll as
a safety net. A drive counts when its block device is removable or hot-pluggable
(lsblk RM/HOTPLUG): USB sticks, memory cards, external disks, DVDs - not internal
partitions opened in Dolphin. Each insert asks once: re-mounting a drive that stayed
plugged in does not ask again.

Usage: autoplay_agent.py            run in the background (session autostart)
       autoplay_agent.py --show DIR  show the AutoPlay window for a folder (testing)"""
import os
import sys

from PyQt6.QtCore import QLockFile, QObject, QProcess, QSocketNotifier, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QFrame, QGroupBox, QLabel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autoplay as AP  # noqa: E402
import style  # noqa: E402
from style import ICON, SIZE  # noqa: E402
from ui import Link, gap, hbox, icon_label, kread, run, text_label, vbox  # noqa: E402
import distro

MEDIA_ROOTS = ("/media/", "/run/media/")
OPTICAL_FS = {"iso9660", "udf"}


def unescape(s):
    """Undo mountinfo's octal escapes (space, tab, newline, backslash) in a path."""
    return s.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def removable_mounts():
    """{mountpoint: (source device, fstype)} for mounts under /media and /run/media."""
    res = {}
    try:
        with open("/proc/self/mountinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                pre, _, post = line.partition(" - ")
                fields, tail = pre.split(), post.split()
                if len(fields) < 5 or len(tail) < 2:
                    continue
                mp = unescape(fields[4])
                if mp.startswith(MEDIA_ROOTS):
                    res[mp] = (tail[1], tail[0])
    except OSError:
        pass
    return res


def is_removable(dev):
    """Is the block device removable, hot-pluggable or on USB (lsblk RM, HOTPLUG, TRAN)?"""
    ok, out, _ = run(["lsblk", "-ndro", "RM,HOTPLUG,TRAN", dev], timeout=5)
    if not ok:
        return False
    parts = out.split()
    return "1" in parts[:2] or "usb" in parts[2:]


def drive_title(mp, fstype):
    label = os.path.basename(mp.rstrip("/"))
    kind = "DVD Drive" if fstype in OPTICAL_FS else "Removable Disk"
    return f"{kind} ({label})" if label else kind


class Classifier(QThread):
    """Looks at a drive's files off the GUI thread (a big drive takes a while to walk)."""
    done = pyqtSignal(str, str, object)        # mountpoint, kind, files

    def __init__(self, mp, parent=None):
        super().__init__(parent)
        self.mp = mp

    def run(self):
        try:
            kind, files = AP.classify(self.mp)
        except OSError:
            kind, files = "files", {}
        self.done.emit(self.mp, kind, files)


class ActionRow(QFrame):
    """One choice in the AutoPlay window: icon, verb, 'using <program>' underneath."""
    clicked = pyqtSignal()

    def __init__(self, icon, verb, using):
        super().__init__()
        self.setObjectName("action")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        h = hbox(self, "choice", "icon_gap")
        ic = icon if isinstance(icon, QIcon) else QIcon.fromTheme(icon)
        lab = QLabel()
        lab.setPixmap(ic.pixmap(ICON["medium"], ICON["medium"]))
        h.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)
        col = vbox(spacing="none")
        col.addWidget(text_label(verb, "choice", wrap=False, selectable=False))
        if using:
            col.addWidget(text_label(using, "secondary", wrap=False, selectable=False))
        h.addLayout(col, 1)
        for w in self.findChildren(QLabel):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(e)


def app_icon(name):
    return QIcon(name) if os.path.isabs(name) else QIcon.fromTheme(name)


class AutoPlayDialog(QDialog):
    """The AutoPlay window for one inserted drive: programs for its content + open folder."""

    def __init__(self, mp, fstype, kind, files):
        super().__init__()
        self.mp, self.kind, self.files = mp, kind, files
        self.setWindowTitle("AutoPlay")
        self.setWindowIcon(QIcon.fromTheme("media-removable" if fstype not in OPTICAL_FS else "media-optical"))
        self.setStyleSheet(style.stylesheet() + f"""
            QFrame#action {{ border: 1px solid transparent; border-radius: 3px; }}
            QFrame#action:hover, QFrame#action:focus {{ background: {style.color('pane_bottom')};
                border-color: {style.color('select_hover')}; }}""")
        self.setMinimumWidth(SIZE["dialog"][0] - ICON["large"])
        v = vbox(self, "dialog", "related")

        head = hbox(spacing="icon_gap")
        head.addWidget(icon_label("media-optical" if fstype in OPTICAL_FS else "drive-removable-media-usb",
                                  "large"), 0, Qt.AlignmentFlag.AlignTop)
        title = vbox(spacing="none")
        title.addWidget(text_label(drive_title(mp, fstype), "instruction", selectable=False))
        n = sum(len(f) for f in files.values()) if files else 0
        what = {"pictures": "pictures", "videos": "videos", "music": "music", "dvd": "a DVD movie",
                "mixed": "pictures, music or videos", "files": "files and folders"}[kind]
        title.addWidget(text_label(f"This drive contains {what}.", "secondary", selectable=False))
        head.addLayout(title, 1)
        v.addLayout(head)
        gap(v)

        self.always = None
        if kind in AP.VERBS:
            self.always = QCheckBox(f"Always do this for {AP.LABEL[kind].lower()}:")
            v.addWidget(self.always)
            box = QGroupBox(f"{AP.LABEL[kind]} options")
            bl = vbox(box, "dialog_page", "link_gap")
            apps = AP.apps_for(kind)
            for sid, name, icon in apps:
                row = ActionRow(app_icon(icon), AP.VERBS[kind], f"using {name}")
                row.clicked.connect(lambda s=sid: self.choose(s))
                bl.addWidget(row)
            if not apps:
                bl.addWidget(text_label("No program for this kind of media is installed.", "secondary"))
            v.addWidget(box)
        else:
            self.always = QCheckBox("Always do this for this kind of drive:")
            v.addWidget(self.always)

        box = QGroupBox("General options")
        bl = vbox(box, "dialog_page", "link_gap")
        row = ActionRow("system-file-manager", "Open folder to view files", "using Dolphin")
        row.clicked.connect(lambda: self.choose("open"))
        bl.addWidget(row)
        v.addWidget(box)
        gap(v)
        link = Link("Set AutoPlay defaults in Control Panel", "link")
        link.clicked.connect(self.open_settings)
        v.addWidget(link)

    def choose(self, action):
        if self.always is not None and self.always.isChecked():
            run(AP.set_handler_cmd(self.kind if self.kind in AP.VERBS else "files", action))
        AP.run_action(action, self.mp, self.kind, self.files)
        self.accept()

    def open_settings(self):
        cmd = distro.command()
        QProcess.startDetached(cmd[0], cmd[1:] + ["--applet", "autoplay"])
        self.accept()


class Agent(QObject):
    """Background watcher: notices new removable mounts and runs or asks for an action."""

    def __init__(self):
        super().__init__()
        self.known = removable_mounts()                 # already there at login: leave alone
        self.asked = {dev for dev, _ in self.known.values()}
        self.workers, self.dialogs = [], []
        try:
            self._fd = open("/proc/self/mountinfo", "rb")
            self.notifier = QSocketNotifier(self._fd.fileno(), QSocketNotifier.Type.Exception, self)
            self.notifier.activated.connect(self.check)
        except OSError:
            self._fd = None
        self.timer = QTimer(self, interval=5000, timeout=self.check)     # safety net
        self.timer.start()

    def check(self, *_):
        if self._fd:
            try:
                self._fd.seek(0)
                self._fd.read()                          # re-arm the change notification
            except OSError:
                pass
        now = removable_mounts()
        # a drive that is gone (device node removed) may ask again when it comes back
        self.asked = {d for d in self.asked if os.path.exists(d)}
        new = {mp: v for mp, v in now.items() if mp not in self.known}
        self.known = now
        if not new or not AP.enabled():
            self.asked |= {dev for dev, _ in new.values()}
            return
        for mp, (dev, fstype) in new.items():
            if dev in self.asked or not is_removable(dev):
                continue
            self.asked.add(dev)
            w = Classifier(mp, self)
            w.done.connect(lambda m, k, f, fs=fstype: self.handle(m, fs, k, f))
            w.finished.connect(lambda w=w: self.workers.remove(w))
            self.workers.append(w)
            w.start()

    def handle(self, mp, fstype, kind, files):
        if mp not in self.known:
            return                                       # pulled out while we looked
        action = AP.handler(kind if kind in AP.VERBS else "files")
        if action == "ask":
            show_dialog(mp, fstype, kind, files, self.dialogs)
        else:
            AP.run_action(action, mp, kind, files)


def show_dialog(mp, fstype, kind, files, keep):
    d = AutoPlayDialog(mp, fstype, kind, files)
    keep.append(d)
    d.finished.connect(lambda *_: keep.remove(d) if d in keep else None)
    d.show()
    d.raise_()
    d.activateWindow()
    return d


def wanted():
    """Should the agent run in this session? It is opt-in, so installing the Control Panel
    never takes over drive handling in an existing desktop:
    VCP_AUTOPLAY=1/0 forces it; BOONE (its session or the OS) always runs it; anywhere else it
    runs once AutoPlay has been switched on in the Control Panel."""
    force = os.environ.get("VCP_AUTOPLAY")
    if force in ("0", "1"):
        return force == "1"
    if os.environ.get("DENAIRU_SESSION") or distro.os_release().get("ID") == distro.LEGACY_ID:
        return True
    return AP.chosen() and AP.enabled()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("vista-autoplay")
    app.setApplicationDisplayName("AutoPlay")
    app.setDesktopFileName("vista-autoplay")
    app.setQuitOnLastWindowClosed(False)
    if not QIcon.themeName():
        QIcon.setThemeName(kread("kdeglobals", "Icons", "Theme", "breeze") or "breeze")

    if "--show" in sys.argv:                             # testing / manual use
        mp = os.path.abspath(sys.argv[sys.argv.index("--show") + 1])
        kind, files = AP.classify(mp)
        keep = []
        d = show_dialog(mp, "vfat", kind, files, keep)
        d.finished.connect(app.quit)
        return app.exec()

    if not wanted():
        return 0
    lock = QLockFile(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "vista-autoplay.lock"))
    if not lock.tryLock(0):
        return 0                                         # already running
    _agent = Agent()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
