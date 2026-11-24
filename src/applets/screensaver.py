# SPDX-License-Identifier: GPL-3.0-or-later
"""Screen Saver Settings (Windows Vista style) on KDE's screen locker.

Windows' screen saver + "On resume, display logon screen" map onto kscreenlockerrc [Daemon]:
Autolock (lock when idle), Timeout (minutes), LockOnResume (lock after sleep), LockGrace
(seconds before the password is required). Reloaded with org.kde.screensaver.configure.
The preview monitor shows the current lock screen picture."""
import os

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QSpinBox, QWidget

from applets.background import current_wallpaper, package_image
from applets.base import AppletDialog
from style import COLOR, SIZE, SPACE
from ui import Link, gap, hbox, kread, kwrite_cmd, text_label

RC = ("kscreenlockerrc", "Daemon")
GREETER = ["Greeter", "Wallpaper", "org.kde.image", "General"]
GRACE = [(0, "Immediately"), (5, "After 5 seconds"), (30, "After 30 seconds"), (60, "After 1 minute"),
         (300, "After 5 minutes")]


def lock_picture():
    """The lock screen's picture file: its own greeter image, else the desktop wallpaper
    (a wallpaper package resolves to its image), or None."""
    img = kread("kscreenlockerrc", GREETER, "Image", "").removeprefix("file://").rstrip("/")
    if not img:
        img, _ = current_wallpaper()
    if img and os.path.isdir(img):
        img = package_image(img)
    return img if img and os.path.exists(img) else None


class MonitorPreview(QWidget):
    """A small monitor with the lock screen picture on it (Vista's preview area)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(QSize(*SIZE["monitor_preview"]))
        self._img = None
        self.active = True

    def set_picture(self, path):
        self._img = None
        if path:
            r = QImageReader(path)
            r.setAutoTransform(True)
            s = r.size()
            if s.isValid():
                r.setScaledSize(s.scaled(QSize(208, 130), Qt.AspectRatioMode.KeepAspectRatioByExpanding))
            img = r.read()
            self._img = None if img.isNull() else img
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        bezel = QRectF(8, 4, w - 16, 150)
        g = QLinearGradient(bezel.topLeft(), bezel.bottomLeft())
        g.setColorAt(0, QColor(COLOR["bezel_top"]))
        g.setColorAt(1, QColor(COLOR["bezel_bottom"]))
        p.setPen(QPen(QColor(COLOR["bezel_edge"]), 1))
        p.setBrush(g)
        p.drawRoundedRect(bezel, 8, 8)
        screen = bezel.adjusted(8, 8, -8, -12)
        path = QPainterPath()
        path.addRoundedRect(screen, 2, 2)
        p.setClipPath(path)
        if self._img is not None and self.active:
            x = (self._img.width() - screen.width()) / 2
            y = (self._img.height() - screen.height()) / 2
            p.drawImage(screen, self._img, QRectF(x, y, screen.width(), screen.height()))
            # a hint of the logon prompt
            box = QRectF(screen.center().x() - 30, screen.center().y() - 10, 60, 20)
            p.setBrush(QColor(255, 255, 255, 170))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(box, 4, 4)
        else:
            p.fillRect(screen, QColor("#000000"))
        p.setClipping(False)
        # stand
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(COLOR["stand"]))
        neck = QRectF(w / 2 - 14, bezel.bottom(), 28, 20)
        p.drawRect(neck)
        base = QRectF(w / 2 - 60, neck.bottom(), 120, 10)
        p.drawRoundedRect(base, 5, 5)


class ScreenSaver(AppletDialog):
    ID = "screensaver"
    TITLE = "Screen Saver Settings"
    ICON = "preferences-desktop-screensaver"
    ADVANCED = "kcm:kcm_screenlocker"
    REPLACES = ["kcm_screenlocker"]

    def build(self):
        page, v = self.new_page()
        self.preview = MonitorPreview()
        v.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)
        gap(v)

        g = self.group(v, "Screen saver")
        row = hbox(spacing="related")
        self.saver = QComboBox()
        self.saver.addItem("(None)", False)
        self.saver.addItem("Lock screen", True)
        self.saver.currentIndexChanged.connect(self._saver_changed)
        row.addWidget(self.saver, 1)
        g.addLayout(row)
        row2 = hbox(spacing="related")
        row2.addWidget(QLabel("Wait:"))
        self.wait = QSpinBox()
        self.wait.setRange(1, 999)
        self.wait.valueChanged.connect(self.changed)
        row2.addWidget(self.wait)
        row2.addWidget(QLabel("minutes"))
        row2.addSpacing(SPACE["section"])
        self.resume = QCheckBox("On resume, display logon screen")
        self.resume.toggled.connect(self.changed)
        row2.addWidget(self.resume)
        row2.addStretch(1)
        g.addLayout(row2)
        row3 = hbox(spacing="related")
        row3.addWidget(QLabel("Require the password:"))
        self.grace = QComboBox()
        for sec, label in GRACE:
            self.grace.addItem(label, sec)
        self.grace.currentIndexChanged.connect(self.changed)
        row3.addWidget(self.grace)
        row3.addStretch(1)
        g.addLayout(row3)

        g2 = self.group(v, "Power management", "preferences-system-power-management", "medium")
        g2.addWidget(text_label("Conserve energy or maximize performance by adjusting display brightness "
                                "and other power settings.", "body"))
        link = Link("Change power settings", "link")
        link.clicked.connect(self._power)
        g2.addWidget(link)
        v.addStretch(1)
        self.add_tab(page, "Screen Saver", "screensaver")

    def _power(self):
        import applets
        if applets.available("power"):
            self._power_dlg = applets.open_applet("power")

    def _saver_changed(self, *_):
        # "(None)" = no automatic lock: its timing options don't apply, the preview goes dark
        on = bool(self.saver.currentData())
        for w in (self.wait, self.grace):
            w.setEnabled(on)
        self.preview.active = on
        self.preview.update()
        self.changed()

    def load(self):
        self._v = {
            "auto": kread(*RC, "Autolock", "true") == "true",
            "timeout": int(kread(*RC, "Timeout", 5) or 5),
            "resume": kread(*RC, "LockOnResume", "true") == "true",
            "grace": int(kread(*RC, "LockGrace", 5) or 0),
        }
        self.preview.set_picture(lock_picture())
        self.saver.setCurrentIndex(1 if self._v["auto"] else 0)
        self.wait.setValue(self._v["timeout"])
        self.resume.setChecked(self._v["resume"])
        i = self.grace.findData(self._v["grace"])
        if i < 0:
            self.grace.addItem(f"After {self._v['grace']} seconds", self._v["grace"])
            i = self.grace.count() - 1
        self.grace.setCurrentIndex(i)
        self._saver_changed()

    def apply_changes(self):
        v, cmds = self._v, []
        for key, new, old in (("Autolock", bool(self.saver.currentData()), v["auto"]),
                              ("Timeout", self.wait.value(), v["timeout"]),
                              ("LockOnResume", self.resume.isChecked(), v["resume"]),
                              ("LockGrace", self.grace.currentData(), v["grace"])):
            if new != old:
                cmds.append(kwrite_cmd(*RC, key, new))
        if cmds:
            cmds.append(["dbus-send", "--session", "--type=method_call", "--dest=org.freedesktop.ScreenSaver",
                         "/ScreenSaver", "org.kde.screensaver.configure"])
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
