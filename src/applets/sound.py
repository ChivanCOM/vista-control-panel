# SPDX-License-Identifier: GPL-3.0-or-later
"""Sound (Windows Vista style) on top of PipeWire/PulseAudio (pactl) and KDE's sound theme.

Playback/Recording: devices, default device, volume and mute (volume changes are live).
Sounds: the system sound scheme (kdeglobals [Sounds] Theme), with a Test button."""
import json
import os
import shutil

from PyQt6.QtCore import QPoint, QProcess, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel,
                             QListWidget, QListWidgetItem, QPushButton, QSlider, QStyledItemDelegate, QWidget)

from applets.base import AppletDialog
from style import ICON, SPACE, color as style_color
from ui import gap, hbox, icon_label, kread, kwrite_cmd, run, text_label, vbox
import distro

SOUND_DIRS = [os.path.join(d, "sounds") for d in
              (os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
               *os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"))]


def devices(kind):
    """kind = 'sinks' | 'sources' -> list of dicts (monitors skipped)."""
    ok, out, _ = run(["pactl", "-f", "json", "list", kind])
    try:
        items = json.loads(out) if ok else []
    except ValueError:
        items = []
    res = []
    for d in items:
        props = d.get("properties", {})
        if kind == "sources" and props.get("device.class") == "monitor":
            continue
        vols = [int(str(c.get("value_percent", "0")).rstrip("%")) for c in d.get("volume", {}).values()]
        port = next((p.get("description") for p in d.get("ports", []) if p.get("name") == d.get("active_port")), "")
        res.append({
            "name": d["name"], "description": d.get("description", d["name"]),
            "icon": props.get("device.icon_name") or ("audio-speakers" if kind == "sinks" else "audio-input-microphone"),
            "volume": max(vols) if vols else 0, "mute": bool(d.get("mute")),
            "port": port or props.get("device.description", ""),
        })
    return res


def device_icon(dev):
    fallback = "audio-card" if "speaker" in dev["icon"] or "headphone" in dev["icon"] else "audio-input-microphone"
    return QIcon.fromTheme(dev["icon"], QIcon.fromTheme(fallback, QIcon.fromTheme("audio-card")))


def default_device(kind):
    """Name of the default sink/source ("" if pactl isn't available)."""
    ok, out, _ = run(["pactl", "get-default-sink" if kind == "sinks" else "get-default-source"])
    return out.strip() if ok else ""


def sound_themes():
    """id -> (title, folder) of every installed freedesktop sound theme (user's first)."""
    themes = {}
    for base in SOUND_DIRS:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            idx = os.path.join(base, name, "index.theme")
            if name in themes or not os.path.isfile(idx):
                continue
            title = name
            try:
                for line in open(idx, encoding="utf-8", errors="replace"):
                    if line.startswith("Name="):
                        title = line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass
            themes[name] = (title, os.path.join(base, name))
    return themes


def theme_sample(path):
    """A representative sound file of a theme for the Test button, or None."""
    for sub in ("stereo", ""):
        for event in ("desktop-login", "bell", "dialog-information", "message-new-instant", "complete"):
            for ext in (".oga", ".ogg", ".wav"):
                f = os.path.join(path, sub, event + ext)
                if os.path.isfile(f):
                    return f
    return None


class DeviceProperties(QDialog):
    """Volume and mute for one device; changes are live, Cancel restores them."""

    def __init__(self, kind, dev, parent=None):
        super().__init__(parent)
        self.kind, self.dev = kind, dev
        self.setWindowTitle(f"{dev['description']} Properties")
        v = vbox(self, "dialog", "related")
        h = hbox(spacing="icon_gap")
        icon = QLabel()
        icon.setPixmap(device_icon(dev).pixmap(QSize(ICON["large"], ICON["large"])))
        h.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(text_label(f"{dev['description']}\n{dev['port']}", "value"), 1)
        v.addLayout(h)
        gap(v)
        v.addWidget(text_label("Levels:", "section"))
        row = hbox(spacing="related")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 150)
        self.slider.setValue(dev["volume"])
        self.pct = QLabel(f"{dev['volume']}%")
        self.pct.setMinimumWidth(self.pct.fontMetrics().horizontalAdvance("150%") + SPACE["link_gap"])
        self.mute = QCheckBox("Mute")
        self.mute.setChecked(dev["mute"])
        row.addWidget(self.slider, 1)
        row.addWidget(self.pct)
        row.addWidget(self.mute)
        v.addLayout(row)
        v.addWidget(text_label("Levels above 100% amplify the sound and may distort it.", "secondary"))
        self.slider.valueChanged.connect(self._volume)
        self.mute.toggled.connect(self._mute)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _cmd(self):
        return "set-sink" if self.kind == "sinks" else "set-source"

    # run, not startDetached: detached pactl calls can finish out of order while the slider
    # is dragged (or after Cancel restored the old level), leaving a stale volume behind
    def _volume(self, val):
        self.pct.setText(f"{val}%")
        run(["pactl", f"{self._cmd()}-volume", self.dev["name"], f"{val}%"], timeout=2)

    def _mute(self, on):
        run(["pactl", f"{self._cmd()}-mute", self.dev["name"], "1" if on else "0"], timeout=2)

    def reject(self):
        run(["pactl", f"{self._cmd()}-volume", self.dev["name"], f"{self.dev['volume']}%"])
        run(["pactl", f"{self._cmd()}-mute", self.dev["name"], "1" if self.dev["mute"] else "0"])
        super().reject()


class DeviceDelegate(QStyledItemDelegate):
    """Vista's sound device rows: a 48 px icon (a green check badge on the default device),
    then the kind of device in black and the hardware and its status in grey."""
    GREY = "#6d6d6d"

    def sizeHint(self, option, index):
        fm = option.fontMetrics
        return QSize(option.rect.width(), max(ICON["large"], 3 * fm.height()) + 2 * SPACE["link_gap"] + 2)

    def paint(self, painter, option, index):
        from PyQt6.QtGui import QColor, QPen
        from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        icon = index.data(Qt.ItemDataRole.DecorationRole) or QIcon()
        opt.text, opt.icon = "", QIcon()
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        r = option.rect.adjusted(SPACE["link_gap"] + 2, SPACE["link_gap"], -SPACE["link_gap"], -SPACE["link_gap"])
        size = ICON["large"]
        icon_rect = r.adjusted(0, (r.height() - size) // 2, 0, 0)
        icon_rect.setSize(QSize(size, size))
        icon.paint(painter, icon_rect)
        if index.data(Qt.ItemDataRole.UserRole + 1):          # the default device
            painter.save()
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            d = size // 2.4
            b = icon_rect.adjusted(0, size - int(d), int(d) - size, 0)
            painter.setBrush(QColor("#3d9a3b"))
            painter.setPen(QPen(QColor("white"), 1.5))
            painter.drawEllipse(b)
            painter.setPen(QPen(QColor("white"), 2.0))
            c = b.center()
            painter.drawPolyline([c + QPoint(-int(d * .25), 0), c + QPoint(-int(d * .05), int(d * .2)),
                                  c + QPoint(int(d * .28), -int(d * .22))])
            painter.restore()
        lines = text.split("\n")
        fm = option.fontMetrics
        x = icon_rect.right() + SPACE["icon_gap"]
        y = r.top() + (r.height() - len(lines) * fm.height()) // 2
        for i, line in enumerate(lines):
            painter.setPen(QColor(style_color("text") if i == 0 else self.GREY))
            painter.drawText(x, y + i * fm.height() + fm.ascent(), fm.elidedText(line, Qt.TextElideMode.ElideRight, r.right() - x))


class DevicePage(QWidget):
    """The Playback or Recording tab: device list, Set Default (applied with Apply) and
    Properties (volume, live)."""

    def __init__(self, dialog, kind, intro):
        super().__init__()
        self.dialog, self.kind = dialog, kind
        _, v = dialog.new_page(self)
        v.addWidget(QLabel(intro))
        self.list = QListWidget()
        self.list.setIconSize(QSize(ICON["large"], ICON["large"]))
        self.list.setItemDelegate(DeviceDelegate(self.list))
        v.addWidget(self.list, 1)
        row = hbox(spacing="related")
        row.addStretch(1)
        self.btn_default = QPushButton("Set Default")
        self.btn_props = QPushButton("Properties")
        row.addWidget(self.btn_default)
        row.addWidget(self.btn_props)
        v.addLayout(row)
        self.btn_default.clicked.connect(self._set_default)
        self.btn_props.clicked.connect(self._props)
        self.list.itemDoubleClicked.connect(lambda _: self._props())
        self.list.currentItemChanged.connect(lambda *_: self._buttons())
        self.default = self.new_default = ""

    def load(self):
        self.default = self.new_default = default_device(self.kind)
        self._fill()

    def _fill(self):
        cur = self._current()            # None also for the "No devices" placeholder row
        sel = cur["name"] if cur else None
        self.list.clear()
        self.devs = devices(self.kind)
        for d in self.devs:
            default = d["name"] == self.new_default
            status = "Default Device" if default else "Ready"
            # Vista: what it is ("Speakers"), then the hardware, then its status
            kind = d["port"] or ("Speakers" if self.kind == "sinks" else "Microphone")
            it = QListWidgetItem(device_icon(d), f"{kind}\n{d['description']}\n{status}")
            it.setData(Qt.ItemDataRole.UserRole, d)
            it.setData(Qt.ItemDataRole.UserRole + 1, default)
            self.list.addItem(it)
            if d["name"] in (sel, self.new_default) and not self.list.currentItem():
                self.list.setCurrentItem(it)
        if not self.devs:
            self.list.addItem(QListWidgetItem("No devices are installed."))
        self._buttons()

    def _current(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _buttons(self):
        d = self._current()
        self.btn_props.setEnabled(bool(d))
        self.btn_default.setEnabled(bool(d) and d["name"] != self.new_default)

    def _set_default(self):
        d = self._current()
        if d:
            self.new_default = d["name"]
            self._fill()
            self.dialog.changed()

    def _props(self):
        d = self._current()
        if d:
            DeviceProperties(self.kind, d, self).exec()
            self._fill()

    def commands(self):
        if self.new_default and self.new_default != self.default:
            return [["pactl", "set-default-sink" if self.kind == "sinks" else "set-default-source",
                     self.new_default]]
        return []


class Sound(AppletDialog):
    ID = "sound"
    TITLE = "Sound"
    ICON = "preferences-desktop-sound"
    ADVANCED = "kcm:kcm_pulseaudio"
    REPLACES = ["kcm_pulseaudio", "kcm_soundtheme#sounds"]

    def build(self):
        self.playback = DevicePage(self, "sinks", "Select a playback device below to modify its settings:")
        self.recording = DevicePage(self, "sources", "Select a recording device below to modify its settings:")
        self.add_tab(self.playback, "Playback", "playback")
        self.add_tab(self.recording, "Recording", "recording")

        page, v = self.new_page()
        v.addWidget(text_label(f"A sound theme is a set of sounds applied to events in {distro.NAME} and "
                               "programs. You can select an existing scheme.", "secondary"))
        gap(v)
        v.addWidget(QLabel("Sound Scheme:"))
        row = hbox(spacing="related")
        self.scheme = QComboBox()
        self.scheme.currentIndexChanged.connect(self.changed)
        row.addWidget(self.scheme, 1)
        test = QPushButton("Test")
        test.clicked.connect(self._test)
        row.addWidget(test)
        v.addLayout(row)
        v.addStretch(1)
        self.add_tab(page, "Sounds", "sounds")

    def load(self):
        self.playback.load()
        self.recording.load()
        self.themes = sound_themes()
        self._theme = kread("kdeglobals", "Sounds", "Theme", "ocean")
        self.scheme.clear()
        for tid, (title, _) in sorted(self.themes.items(), key=lambda t: t[1][0].lower()):
            self.scheme.addItem(title, tid)
        i = self.scheme.findData(self._theme)
        if i < 0 and self.themes:
            # keep the configured theme selected even if it isn't installed, so Apply doesn't
            # silently switch to whichever theme happens to be listed first
            self.scheme.addItem(self._theme, self._theme)
            i = self.scheme.count() - 1
        if i >= 0:
            self.scheme.setCurrentIndex(i)

    def _test(self):
        tid = self.scheme.currentData()
        sample = theme_sample(self.themes[tid][1]) if tid in self.themes else None
        if sample:
            QProcess.startDetached("pw-play" if shutil.which("pw-play") else "paplay", [sample])

    def apply_changes(self):
        cmds = self.playback.commands() + self.recording.commands()
        tid = self.scheme.currentData()
        if tid and tid != self._theme:
            cmds.append(kwrite_cmd("kdeglobals", "Sounds", "Theme", tid))
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
