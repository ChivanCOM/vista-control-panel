# SPDX-License-Identifier: GPL-3.0-or-later
"""Date and Time (Windows Vista style) on top of systemd-timedated (timedatectl).

Setting the clock, time zone or Internet time needs an administrator; timedatectl asks
through polkit, so the UAC prompt appears."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from PyQt6.QtCore import QDateTime, QLocale, QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QCalendarWidget, QCheckBox, QDialog, QDialogButtonBox, QGroupBox,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QTimeEdit, QWidget)

from style import COLOR, SIZE, SPACE
from ui import Jobs, gap, hbox, run, text_label, vbox
from applets.base import AppletDialog


def timedate_status():
    """`timedatectl show` as a dict (Timezone, NTP, CanNTP, NTPSynchronized, ...)."""
    ok, out, _ = run(["timedatectl", "show"])
    d = {}
    for line in out.splitlines():
        k, _, v = line.partition("=")
        d[k] = v
    return d


def zone_label(zone):
    """Zone -> ("(UTC+01:00) Europe/Paris", offset in minutes) for listing and sorting."""
    try:
        off = datetime.now(ZoneInfo(zone)).utcoffset()
    except Exception:  # unknown/odd zone names
        return zone, 0
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    hh, mm = divmod(abs(minutes), 60)
    return f"(UTC{sign}{hh:02d}:{mm:02d}) {zone.replace('_', ' ')}", minutes


class Clock(QWidget):
    """A small Vista-style analog clock."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(SIZE["clock"], SIZE["clock"])
        t = QTimer(self, interval=1000)
        t.timeout.connect(self.update)
        t.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = min(self.width(), self.height()) / 2 - 4
        c = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(QPen(QColor(COLOR["clock_rim"]), 2))
        p.setBrush(QColor(COLOR["clock_face"]))
        p.drawEllipse(c, r, r)
        for i in range(60):
            a = math.radians(i * 6)
            outer = QPointF(c.x() + math.sin(a) * (r - 4), c.y() - math.cos(a) * (r - 4))
            inner_r = r - (12 if i % 5 == 0 else 7)
            inner = QPointF(c.x() + math.sin(a) * inner_r, c.y() - math.cos(a) * inner_r)
            p.setPen(QPen(QColor(COLOR["clock_tick"] if i % 5 == 0 else COLOR["clock_tick_minor"]), 2 if i % 5 == 0 else 1))
            p.drawLine(inner, outer)
        now = datetime.now()

        def hand(angle_deg, length, width, color):
            a = math.radians(angle_deg)
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(c, QPointF(c.x() + math.sin(a) * length, c.y() - math.cos(a) * length))

        hand((now.hour % 12 + now.minute / 60) * 30, r * 0.5, 4, COLOR["clock_hand"])
        hand((now.minute + now.second / 60) * 6, r * 0.72, 3, COLOR["clock_hand"])
        hand(now.second * 6, r * 0.8, 1, COLOR["clock_second"])
        p.setBrush(QColor(COLOR["clock_hand"]))
        p.drawEllipse(c, 3, 3)


class TimeZoneDialog(QDialog):
    """Pick a time zone from timedatectl's list, sorted by UTC offset, with a filter box."""

    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Time Zone Settings")
        self.resize(*SIZE["dialog"])
        v = vbox(self, "dialog", "related")
        v.addWidget(QLabel("Set the time zone:"))
        self.filter = QLineEdit(placeholderText="Search for a city or region")
        v.addWidget(self.filter)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        ok, out, _ = run(["timedatectl", "list-timezones"])
        zones = [z for z in out.split() if z]
        items = sorted((zone_label(z) + (z,) for z in zones), key=lambda t: (t[1], t[0]))
        for label, _, zone in items:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, zone)
            self.list.addItem(it)
            if zone == current:
                self.list.setCurrentItem(it)
        self.list.scrollToItem(self.list.currentItem()) if self.list.currentItem() else None
        self.filter.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _filter(self, text):
        t = text.lower().replace(" ", "_")
        for i in range(self.list.count()):
            it = self.list.item(i)
            zone = it.data(Qt.ItemDataRole.UserRole).lower()
            it.setHidden(bool(t) and t not in zone and text.lower() not in it.text().lower())

    def zone(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


class SetTimeDialog(QDialog):
    """Calendar + time field; value() is the "YYYY-MM-DD HH:MM:SS" timedatectl set-time takes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Date and Time Settings")
        v = vbox(self, "dialog", "related")
        v.addWidget(QLabel("Set the date and time:"))
        h = hbox(spacing="section")
        self.cal = QCalendarWidget()
        self.cal.setGridVisible(False)
        h.addWidget(self.cal)
        right = vbox(spacing="related")
        self.clock = Clock()
        right.addWidget(self.clock, 0, Qt.AlignmentFlag.AlignHCenter)
        self.time = QTimeEdit(QDateTime.currentDateTime().time())
        self.time.setDisplayFormat("HH:mm:ss")
        right.addWidget(self.time)
        right.addStretch(1)
        h.addLayout(right)
        v.addLayout(h)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def value(self):
        d, t = self.cal.selectedDate(), self.time.time()
        return f"{d.year():04d}-{d.month():02d}-{d.day():02d} {t.hour():02d}:{t.minute():02d}:{t.second():02d}"


class DateTime(AppletDialog):
    ID = "datetime"
    TITLE = "Date and Time"
    ICON = "preferences-system-time"
    ADVANCED = "kcm:kcm_clock"
    REPLACES = ["kcm_clock"]

    def build(self):
        # --- Date and Time -----------------------------------------------------------
        page, v = self.new_page()
        top = hbox(spacing="section")
        top.addWidget(Clock(), 0, Qt.AlignmentFlag.AlignTop)
        info = vbox(spacing="link_gap")
        info.addWidget(text_label("Date:", "caption"))
        self.date_lbl = text_label("", "emphasis")
        info.addWidget(self.date_lbl)
        gap(info, "related")
        info.addWidget(text_label("Time:", "caption"))
        self.time_lbl = text_label("", "emphasis")
        info.addWidget(self.time_lbl)
        info.addStretch(1)
        self.btn_time = QPushButton("Change date and time\u2026")
        self.btn_time.clicked.connect(self._change_time)
        info.addWidget(self.btn_time)
        self.ntp_note = text_label("", "secondary")
        info.addWidget(self.ntp_note)
        top.addLayout(info, 1)
        v.addLayout(top)
        tz = QGroupBox("Time zone")
        tzl = vbox(tz, "dialog_page", "related")
        self.tz_lbl = text_label("", "value")
        tzl.addWidget(self.tz_lbl)
        b = QPushButton("Change time zone\u2026")
        b.clicked.connect(self._change_zone)
        tzl.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)
        v.addWidget(tz)
        v.addStretch(1)
        self.add_tab(page, "Date and Time", "datetime")

        # --- Internet Time ------------------------------------------------------------
        page2, v2 = self.new_page()
        self.heading(v2, "Internet Time")
        self.ntp_status = text_label("", "secondary")
        v2.addWidget(self.ntp_status)
        self.ntp = QCheckBox("Synchronize with an Internet time server")
        self.ntp.toggled.connect(self.changed)
        v2.addWidget(self.ntp)
        self.ntp_sync = text_label("", "secondary")
        v2.addWidget(self.ntp_sync)
        v2.addStretch(1)
        self.add_tab(page2, "Internet Time", "internettime")

        t = QTimer(self, interval=1000)
        t.timeout.connect(self._tick)
        t.start()

    def _tick(self):
        loc, now = QLocale(), QDateTime.currentDateTime()
        self.date_lbl.setText(loc.toString(now.date(), QLocale.FormatType.LongFormat))
        fmt = " ".join(t for t in loc.timeFormat(QLocale.FormatType.LongFormat).split() if "t" not in t)
        self.time_lbl.setText(loc.toString(now.time(), fmt))   # long format without the time zone

    def load(self):
        st = timedate_status()
        self._zone = self._new_zone = st.get("Timezone", "UTC")
        self._ntp = st.get("NTP") == "yes"
        can_ntp = st.get("CanNTP") == "yes"
        self.tz_lbl.setText(zone_label(self._zone)[0])
        self.ntp.setChecked(self._ntp)
        self.ntp.setEnabled(can_ntp)
        self.ntp_status.setText(
            "This computer is set to automatically synchronize with an Internet time server."
            if self._ntp else "This computer is not set to synchronize automatically.")
        self.ntp_sync.setText("The clock is synchronized." if st.get("NTPSynchronized") == "yes"
                              else ("The clock hasn’t synchronized yet." if self._ntp else ""))
        self.btn_time.setEnabled(not self._ntp)
        self.ntp_note.setText("Turn off Internet time (Internet Time tab) to set the clock by hand."
                              if self._ntp else "")
        self._tick()

    def _change_zone(self):
        d = TimeZoneDialog(self._new_zone, self)
        if d.exec() and d.zone() and d.zone() != self._new_zone:
            self._new_zone = d.zone()
            self.tz_lbl.setText(zone_label(self._new_zone)[0])
            self.changed()

    def _change_time(self):
        d = SetTimeDialog(self)
        if d.exec():
            # Windows sets the clock as soon as this dialog is confirmed
            self._time_job = Jobs([["timedatectl", "set-time", d.value()]], self)
            self._time_job.finished.connect(
                lambda ok, err: ok or QMessageBox.warning(self, self.TITLE, f"The time could not be changed.\n\n{err}"))
            self._time_job.start()

    def apply_changes(self):
        cmds = []
        if self._new_zone != self._zone:
            cmds.append(["timedatectl", "set-timezone", self._new_zone])
        if self.ntp.isChecked() != self._ntp:
            cmds.append(["timedatectl", "set-ntp", "true" if self.ntp.isChecked() else "false"])
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
