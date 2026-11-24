# SPDX-License-Identifier: GPL-3.0-or-later
"""Display Settings (Windows Vista style) on top of KScreen (kscreen-doctor).

Monitor arrangement (drag to arrange, snaps edge to edge), Identify Monitors, main monitor,
extend the desktop, resolution slider, refresh rate, orientation, and text size.
After Apply, Windows' "Do you want to keep these display settings?" countdown reverts the
change unless it is confirmed.

Backend facts (libkscreen Plasma/6.6, src/doctor/doctor.cpp, src/config.h, src/output.h):
- one kscreen-doctor call applies all ops as one configuration; ops are split on '.', so
  modes are set by id, never by name; scale "1.25" arrives as two parts and is handled
- rotation: 1 none, 2 left, 4 inverted, 8 right
- features bit 4 = PerOutputScaling (Wayland). Without it (X11) scaling is global and
  needs a log off: kdeglobals [KScreen] ScaleFactor/ScreenScaleFactors, kcmfonts
  forceFontDPI and Xft.dpi, as KDE's own display module does (kscreen kcm/kcm.cpp)."""
import copy
import json
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QRadioButton, QSlider, QWidget)

import style
from applets.base import AppletDialog
from style import COLOR, SIZE, SPACE
from ui import form_grid, gap, hbox, kread, kwrite_cmd, run, section, text_label, vbox

ROTATIONS = [(1, "Landscape", "normal"), (2, "Portrait", "left"),
             (4, "Landscape (flipped)", "inverted"), (8, "Portrait (flipped)", "right")]
ROT_NAME = {r: n for r, _, n in ROTATIONS}
FEATURE_PER_OUTPUT_SCALING = 1 << 2
SCALES = [(1.0, "Smaller – 100% (default)"), (1.25, "Medium – 125%"),
          (1.5, "Larger – 150%"), (1.75, "Larger – 175%"), (2.0, "Largest – 200%")]
REVERT_SECONDS = 15


# ----------------------------------------------------------------------------- model
@dataclass
class Output:
    """One connected monitor as kscreen-doctor -j describes it (positions in device pixels)."""
    name: str
    connected: bool
    enabled: bool
    primary: bool
    modes: list                      # [{"id", "w", "h", "rate"}]
    mode_id: str
    preferred: list
    x: int = 0
    y: int = 0
    rotation: int = 1
    scale: float = 1.0
    kind: int = 0
    mm: tuple = (0, 0)
    extra: dict = field(default_factory=dict)

    def mode(self, mode_id=None):
        mid = mode_id or self.mode_id
        return next((m for m in self.modes if m["id"] == mid), self.modes[0] if self.modes else None)

    def size(self, logical=False):
        m = self.mode()
        if not m:
            return 0, 0
        w, h = m["w"], m["h"]
        if self.rotation in (2, 8):
            w, h = h, w
        if logical and self.scale:
            w, h = round(w / self.scale), round(h / self.scale)
        return w, h

    def label(self):
        built_in = self.kind == 7 or self.name.lower().startswith(("edp", "lvds", "dsi"))
        return f"{self.name} (Built-in display)" if built_in else self.name


def load_config():
    """-> ([Output] for connected monitors, main one first; kscreen features bit mask)."""
    ok, out, _ = run(["kscreen-doctor", "-j"])
    data = json.loads(out) if ok and out.strip() else {"outputs": [], "features": 0}
    outs = []
    for o in data.get("outputs", []):
        if not o.get("connected"):
            continue
        modes = [{"id": str(m["id"]), "w": m["size"]["width"], "h": m["size"]["height"],
                  "rate": float(m.get("refreshRate", 0))} for m in o.get("modes", [])]
        outs.append(Output(
            name=o["name"], connected=True, enabled=bool(o.get("enabled")),
            primary=o.get("priority") == 1, modes=modes, mode_id=str(o.get("currentModeId") or ""),
            preferred=[str(p) for p in o.get("preferredModes", [])],
            x=o.get("pos", {}).get("x", 0), y=o.get("pos", {}).get("y", 0),
            rotation=int(o.get("rotation", 1)), scale=float(o.get("scale", 1) or 1),
            kind=int(o.get("type", 0)), mm=(o.get("sizeMM", {}).get("width", 0), o.get("sizeMM", {}).get("height", 0)),
        ))
    outs.sort(key=lambda o: (not o.primary, not o.enabled, o.x, o.y))
    return outs, int(data.get("features", 0))


def pack(outputs, logical=False):
    """Remove gaps/overlaps after size changes while keeping the arrangement: walk the
    enabled outputs in reading order and put each one right of, or below, the previous."""
    active = [o for o in outputs if o.enabled]
    if not active:
        return
    active.sort(key=lambda o: (o.y, o.x))
    placed = []
    for o in active:
        if not placed:
            o.x, o.y = 0, 0
        else:
            prev = placed[-1]
            pw, ph = prev.size(logical)
            if o.x >= prev.x + pw * 0.5 or o.y < prev.y + ph * 0.5:      # beside
                o.x, o.y = prev.x + pw, prev.y
            else:                                                      # below
                o.x, o.y = prev.x, prev.y + ph
        placed.append(o)
    normalize(outputs)


def normalize(outputs):
    """Shift the enabled outputs so the arrangement starts at (0, 0)."""
    active = [o for o in outputs if o.enabled]
    if not active:
        return
    mx, my = min(o.x for o in active), min(o.y for o in active)
    for o in active:
        o.x -= mx
        o.y -= my


def snap(moving, others, x, y, logical=False):
    """Place `moving` at the edge of the nearest other output, close to (x, y)."""
    w, h = moving.size(logical)
    best = None
    for o in others:
        ow, oh = o.size(logical)
        clamp_y = min(max(y, o.y - h + 1), o.y + oh - 1)
        clamp_x = min(max(x, o.x - w + 1), o.x + ow - 1)
        for cx, cy in ((o.x + ow, clamp_y), (o.x - w, clamp_y), (clamp_x, o.y + oh), (clamp_x, o.y - h)):
            d = (cx - x) ** 2 + (cy - y) ** 2
            if best is None or d < best[0]:
                best = (d, cx, cy)
    if best:
        moving.x, moving.y = best[1], best[2]


def doctor_ops(old, new, per_output_scaling):
    """kscreen-doctor ops that turn configuration `old` into `new` (lists of Output)."""
    ops = []
    olds = {o.name: o for o in old}
    for n in new:
        o = olds.get(n.name)
        if o is None:
            continue
        p = f"output.{n.name}"
        if n.enabled != o.enabled:
            ops.append(f"{p}.{'enable' if n.enabled else 'disable'}")
        if not n.enabled:
            continue
        if n.mode_id and n.mode_id != o.mode_id:
            ops.append(f"{p}.mode.{n.mode_id}")
        if n.rotation != o.rotation:
            ops.append(f"{p}.rotation.{ROT_NAME.get(n.rotation, 'normal')}")
        if per_output_scaling and abs(n.scale - o.scale) > 1e-3:
            ops.append(f"{p}.scale.{n.scale:g}")
        if (n.x, n.y) != (o.x, o.y) or n.enabled != o.enabled:
            ops.append(f"{p}.position.{n.x},{n.y}")
        if n.primary and not o.primary:
            ops.append(f"{p}.primary")
    return ops


# ----------------------------------------------------------------------------- widgets
class Arrangement(QWidget):
    """The monitor diagram: numbered tiles, click to select, drag to arrange."""
    selected = pyqtSignal(str)
    moved = pyqtSignal()

    def __init__(self, logical):
        super().__init__()
        self.logical = logical
        self.outputs, self.current = [], None
        self._drag = None
        self.setMinimumHeight(SIZE["monitor_canvas_height"])
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_outputs(self, outputs, current):
        self.outputs, self.current = outputs, current
        self.update()

    def _layout(self):
        """Scene rects in widget coordinates (disabled outputs shown to the right, greyed)."""
        rects = {}
        right = 0
        for o in self.outputs:
            if o.enabled:
                w, h = o.size(self.logical)
                rects[o.name] = QRectF(o.x, o.y, w, h)
                right = max(right, o.x + w)
        for o in self.outputs:
            if not o.enabled:
                w, h = o.size(self.logical) if o.mode() else (1920, 1080)
                rects[o.name] = QRectF(right + 200, 0, w, h)
                right += 200 + w
        if not rects:
            return {}, 1, QPointF()
        x0 = min(r.left() for r in rects.values())
        y0 = min(r.top() for r in rects.values())
        x1 = max(r.right() for r in rects.values())
        y1 = max(r.bottom() for r in rects.values())
        pad = SPACE["section"]
        k = min((self.width() - 2 * pad) / max(x1 - x0, 1), (self.height() - 2 * pad) / max(y1 - y0, 1))
        off = QPointF((self.width() - (x1 - x0) * k) / 2 - x0 * k, (self.height() - (y1 - y0) * k) / 2 - y0 * k)
        return {n: QRectF(r.left() * k + off.x(), r.top() * k + off.y(), r.width() * k, r.height() * k)
                for n, r in rects.items()}, k, off

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(COLOR["canvas"]))
        rects, _, _ = self._layout()
        for i, o in enumerate(self.outputs, start=1):
            r = rects.get(o.name)
            if r is None:
                continue
            if self._drag and self._drag[0] == o.name:
                r = r.translated(self._drag[2])
            fill = QColor(COLOR["monitor"] if o.enabled else COLOR["monitor_disabled"])
            p.setBrush(fill)
            sel = o.name == self.current
            p.setPen(QPen(QColor(COLOR["monitor_selected"] if sel else COLOR["swatch_border"]), 3 if sel else 1))
            p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 4, 4)
            p.setPen(QColor(COLOR["monitor_text"]))
            p.setFont(style.font("monitor_number"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(i))

    def _hit(self, pos):
        rects, _, _ = self._layout()
        for o in reversed(self.outputs):
            if o.name in rects and rects[o.name].contains(QPointF(pos)):
                return o
        return None

    def mousePressEvent(self, e):
        o = self._hit(e.position())
        if o:
            self.current = o.name
            self.selected.emit(o.name)
            movable = o.enabled and sum(1 for x in self.outputs if x.enabled) > 1
            self._drag = (o.name, e.position(), QPointF()) if movable else None
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._drag = (self._drag[0], self._drag[1], e.position() - self._drag[1])
            self.update()

    def mouseReleaseEvent(self, e):
        if not self._drag:
            return
        name, start, delta = self._drag
        self._drag = None
        if delta.manhattanLength() < 4:
            self.update()
            return
        _, k, _ = self._layout()
        o = next(x for x in self.outputs if x.name == name)
        others = [x for x in self.outputs if x.enabled and x.name != name]
        snap(o, others, o.x + delta.x() / k, o.y + delta.y() / k, self.logical)
        o.x, o.y = round(o.x), round(o.y)
        normalize(self.outputs)
        self.moved.emit()
        self.update()


class KeepDialog(QDialog):
    """Windows' "Do you want to keep these display settings?" with a countdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Display Settings")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        v = vbox(self, "dialog", "related")
        v.addWidget(text_label("Do you want to keep these display settings?", "instruction"))
        self.msg = text_label("", "secondary")
        v.addWidget(self.msg)
        gap(v)
        row = hbox(spacing="related")
        row.addStretch(1)
        yes, no = QPushButton("Yes"), QPushButton("No")
        no.setDefault(True)
        yes.clicked.connect(self.accept)
        no.clicked.connect(self.reject)
        row.addWidget(yes)
        row.addWidget(no)
        v.addLayout(row)
        self.left = REVERT_SECONDS
        self._t = QTimer(self, interval=1000)
        self._t.timeout.connect(self._tick)
        self._tick(first=True)
        self._t.start()

    def _tick(self, first=False):
        if not first:
            self.left -= 1
        if self.left <= 0:
            self.reject()
            return
        self.msg.setText(f"Reverting in {self.left} seconds.")


class Identify(QLabel):
    """Big monitor number shown on each screen for a few seconds."""

    def __init__(self, number, screen):
        super().__init__(str(number))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(style.font("identify"))
        self.setStyleSheet(f"background: {COLOR['identify_bg']}; color: {COLOR['identify_text']};"
                           " border-radius: 12px;")
        w, h = SIZE["identify"]
        self.resize(w, h)
        g = screen.geometry()
        self.move(g.x() + SPACE["section"] * 2, g.y() + SPACE["section"] * 2)
        QTimer.singleShot(3000, self.close)


# ----------------------------------------------------------------------------- dialog
class DisplaySettings(AppletDialog):
    ID = "display"
    TITLE = "Display Settings"
    ICON = "preferences-desktop-display"
    ADVANCED = "kcm:kcm_kscreen"
    REPLACES = ["kcm_kscreen"]
    SIZE = "dialog_wide"

    def build(self):
        self.outputs, self.features = [], 0
        self._identify = []
        # --- Monitor --------------------------------------------------------------------
        page, v = self.new_page()
        self.heading(v, "Drag the icons to match your monitors.")
        self.canvas = Arrangement(logical=False)
        self.canvas.selected.connect(self._select)
        self.canvas.moved.connect(self._edited)
        v.addWidget(self.canvas)
        row = hbox(spacing="related")
        self.monitor = QComboBox()
        self.monitor.currentIndexChanged.connect(lambda i: self._select(self.monitor.itemData(i)))
        row.addWidget(self.monitor, 1)
        ident = QPushButton("Identify Monitors")
        ident.clicked.connect(self._identify_monitors)
        row.addWidget(ident)
        v.addLayout(row)
        self.main_cb = QCheckBox("This is my main monitor")
        self.main_cb.toggled.connect(self._main_toggled)
        self.extend_cb = QCheckBox("Extend the desktop onto this monitor")
        self.extend_cb.toggled.connect(self._extend_toggled)
        v.addWidget(self.main_cb)
        v.addWidget(self.extend_cb)

        section(v, "Resolution")
        res = hbox(spacing="related")
        res.addWidget(text_label("Low", "caption"))
        self.res_slider = QSlider(Qt.Orientation.Horizontal)
        self.res_slider.setPageStep(1)
        self.res_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.res_slider.valueChanged.connect(self._res_changed)
        res.addWidget(self.res_slider, 1)
        res.addWidget(text_label("High", "caption"))
        v.addLayout(res)
        self.res_label = text_label("", "value")
        self.res_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(self.res_label)
        g = form_grid()
        g.addWidget(QLabel("Refresh rate:"), 0, 0)
        self.rate = QComboBox()
        self.rate.currentIndexChanged.connect(self._rate_changed)
        g.addWidget(self.rate, 0, 1)
        g.addWidget(QLabel("Orientation:"), 1, 0)
        self.orient = QComboBox()
        for r, label, _ in ROTATIONS:
            self.orient.addItem(label, r)
        self.orient.currentIndexChanged.connect(self._orient_changed)
        g.addWidget(self.orient, 1, 1)
        g.setColumnStretch(2, 1)
        v.addLayout(g)
        v.addStretch(1)
        self.add_tab(page, "Monitor", "monitor")

        # --- Text size ------------------------------------------------------------------
        page2, v2 = self.new_page()
        self.heading(v2, "Make text and other items larger or smaller",
                     "You can make text and other items on the screen easier to read by choosing one "
                     "of these options.")
        self.scale_group = QButtonGroup(self)
        self.scale_buttons = {}
        for val, label in SCALES:
            rb = QRadioButton(label)
            self.scale_group.addButton(rb)
            self.scale_buttons[val] = rb
            rb.toggled.connect(self._scale_toggled)
            v2.addWidget(rb)
        self.scale_note = text_label("", "secondary")
        gap(v2)
        v2.addWidget(self.scale_note)
        v2.addStretch(1)
        self.add_tab(page2, "Text Size", "textsize")

    # --- data ---------------------------------------------------------------------------
    @property
    def per_output_scaling(self):
        return bool(self.features & FEATURE_PER_OUTPUT_SCALING)

    def load(self):
        self.outputs, self.features = load_config()
        self.orig = copy.deepcopy(self.outputs)
        self.canvas.logical = self.per_output_scaling
        self.monitor.blockSignals(True)
        self.monitor.clear()
        for i, o in enumerate(self.outputs, start=1):
            self.monitor.addItem(f"{i}. {o.label()}", o.name)
        self.monitor.blockSignals(False)
        first = next((o.name for o in self.outputs if o.primary), self.outputs[0].name if self.outputs else None)
        self.current = first
        self.canvas.set_outputs(self.outputs, first)
        self._fill_controls()
        # text size: global on X11 (needs log off), per monitor on Wayland
        if self.per_output_scaling:
            self._scale = self._cur().scale if self._cur() else 1.0
            self.scale_note.setText("Applies to the selected monitor.")
        else:
            self._scale = float(kread("kdeglobals", "KScreen", "ScaleFactor", 1.0) or 1.0)
            self.scale_note.setText("Applies to all monitors. You need to log off for the change to take effect.")
        self._orig_scale = self._scale
        self._check_scale(self._scale)

    def _cur(self):
        return next((o for o in self.outputs if o.name == self.current), None)

    def _sizes(self, o):
        seen, sizes = set(), []
        for m in sorted(o.modes, key=lambda m: (m["w"] * m["h"], m["w"])):
            if (m["w"], m["h"]) not in seen:
                seen.add((m["w"], m["h"]))
                sizes.append((m["w"], m["h"]))
        return sizes

    def _fill_controls(self):
        o = self._cur()
        widgets = (self.main_cb, self.extend_cb, self.res_slider, self.rate, self.orient)
        for w in widgets:
            w.blockSignals(True)
        if o is None:
            for w in widgets:
                w.setEnabled(False)
            self.res_label.setText("No monitor detected.")
        else:
            self.monitor.setCurrentIndex(self.monitor.findData(o.name))
            enabled_count = sum(1 for x in self.outputs if x.enabled)
            self.main_cb.setChecked(o.primary)
            self.main_cb.setEnabled(o.enabled and not o.primary)
            self.extend_cb.setChecked(o.enabled)
            self.extend_cb.setEnabled(not (o.enabled and enabled_count == 1))
            sizes = self._sizes(o)
            self.res_slider.setRange(0, max(len(sizes) - 1, 0))
            m = o.mode()
            if m:
                self.res_slider.setValue(sizes.index((m["w"], m["h"])))
            for w in (self.res_slider, self.rate, self.orient):
                w.setEnabled(o.enabled)
            self._fill_rates(o)
            self.orient.setCurrentIndex(max(self.orient.findData(o.rotation), 0))
            self._update_res_label(o)
        for w in widgets:
            w.blockSignals(False)

    def _fill_rates(self, o):
        m = o.mode()
        self.rate.blockSignals(True)
        self.rate.clear()
        if m:
            for mm in sorted((x for x in o.modes if (x["w"], x["h"]) == (m["w"], m["h"])),
                             key=lambda x: -x["rate"]):
                self.rate.addItem(f"{mm['rate']:.0f} Hertz" if abs(mm["rate"] - round(mm["rate"])) < 0.1
                                  else f"{mm['rate']:.2f} Hertz", mm["id"])
            self.rate.setCurrentIndex(max(self.rate.findData(m["id"]), 0))
        self.rate.blockSignals(False)

    def _update_res_label(self, o):
        m = o.mode()
        if not m:
            self.res_label.setText("")
            return
        pref = o.mode(o.preferred[0]) if o.preferred else None
        rec = pref and (pref["w"], pref["h"]) == (m["w"], m["h"])
        self.res_label.setText(f"{m['w']} by {m['h']} pixels" + ("  (Recommended)" if rec else ""))

    # --- edits ---------------------------------------------------------------------------
    def _select(self, name):
        if name and name != self.current:
            self.current = name
            self.canvas.current = name
            self.canvas.update()
            self._fill_controls()
            if self.per_output_scaling and self._cur():
                self._check_scale(self._cur().scale)

    def _edited(self):
        self.canvas.update()
        self._fill_controls()
        self.changed()

    def _main_toggled(self, on):
        o = self._cur()
        if o and on:
            for x in self.outputs:
                x.primary = x is o
            self._edited()

    def _extend_toggled(self, on):
        o = self._cur()
        if not o:
            return
        o.enabled = on
        if on:
            if not o.mode_id or not o.mode():
                o.mode_id = (o.preferred[0] if o.preferred else (o.modes[0]["id"] if o.modes else ""))
            others = [x for x in self.outputs if x.enabled and x is not o]
            o.x = max((x.x + x.size(self.canvas.logical)[0] for x in others), default=0)
            o.y = 0
        elif o.primary:
            nxt = next((x for x in self.outputs if x.enabled), None)
            if nxt:
                o.primary, nxt.primary = False, True
        pack(self.outputs, self.canvas.logical)
        self._edited()

    def _res_changed(self, idx):
        o = self._cur()
        if not o:
            return
        w, h = self._sizes(o)[idx]
        cur_rate = o.mode()["rate"] if o.mode() else 60
        same = [m for m in o.modes if (m["w"], m["h"]) == (w, h)]
        best = min(same, key=lambda m: abs(m["rate"] - cur_rate))
        o.mode_id = best["id"]
        pack(self.outputs, self.canvas.logical)
        self._edited()

    def _rate_changed(self, i):
        o = self._cur()
        if o and self.rate.itemData(i):
            o.mode_id = self.rate.itemData(i)
            self.changed()

    def _orient_changed(self, i):
        o = self._cur()
        if o:
            o.rotation = self.orient.itemData(i)
            pack(self.outputs, self.canvas.logical)
            self._edited()

    def _check_scale(self, val):
        """Show `val` (nearest choice) without it counting as an edit."""
        btn = self.scale_buttons.get(min(self.scale_buttons, key=lambda k: abs(k - val)))
        if btn:
            # block the buttons themselves: their toggled signals (connected to
            # _scale_toggled) are not covered by blocking the QButtonGroup
            for b in self.scale_buttons.values():
                b.blockSignals(True)
            btn.setChecked(True)
            for b in self.scale_buttons.values():
                b.blockSignals(False)

    def _scale_toggled(self, on):
        if not on or self._loading:
            return
        val = next(k for k, b in self.scale_buttons.items() if b.isChecked())
        if self.per_output_scaling and self._cur():
            self._cur().scale = val
            pack(self.outputs, True)
            self.canvas.update()
        self._scale = val
        self.changed()

    def _identify_monitors(self):
        screens = {s.name(): s for s in QGuiApplication.screens()}
        self._identify = []
        for i, o in enumerate(self.outputs, start=1):
            s = screens.get(o.name) or (QGuiApplication.screens()[i - 1] if i <= len(QGuiApplication.screens()) else None)
            if s and o.enabled:
                w = Identify(i, s)
                w.show()
                self._identify.append(w)

    # --- apply ------------------------------------------------------------------------------
    def apply_changes(self):
        self._ops = doctor_ops(self.orig, self.outputs, self.per_output_scaling)
        self._revert_ops = doctor_ops(self.outputs, self.orig, self.per_output_scaling)
        cmds = []
        if self._ops:
            cmds.append(["kscreen-doctor"] + self._ops)
        self._global_scale_changed = (not self.per_output_scaling and abs(self._scale - self._orig_scale) > 1e-3)
        if self._global_scale_changed:
            cmds += self._global_scale_cmds(self._scale)
        return cmds

    def _global_scale_cmds(self, scale):
        """X11: same settings KDE's display module writes (kscreen kcm/kcm.cpp)."""
        factors = "".join(f"{o.name}={scale:g};" for o in self.outputs)
        cmds = [kwrite_cmd("kdeglobals", "KScreen", "ScaleFactor", f"{scale:g}"),
                kwrite_cmd("kdeglobals", "KScreen", "ScreenScaleFactors", factors)]
        if abs(scale - 1.0) < 1e-3:
            cmds.append(kwrite_cmd("kcmfonts", "General", "forceFontDPI", 0))
            cmds.append(["sh", "-c", "xrdb -query | grep -v '^Xft.dpi:' | xrdb -quiet -load -nocpp"])
        else:
            dpi = round(scale * 96)
            cmds.append(kwrite_cmd("kcmfonts", "General", "forceFontDPI", dpi))
            cmds.append(["sh", "-c", f"printf 'Xft.dpi: {dpi}\\n' | xrdb -quiet -merge -nocpp"])
        return cmds

    def after_apply(self):
        """Ask to keep the new layout (reverting it otherwise) and offer to log off after an
        X11 text size change; -> False keeps the dialog open after a revert."""
        keep = True
        if self._ops:
            dlg = KeepDialog(self)
            if not dlg.exec():
                run(["kscreen-doctor"] + self._revert_ops)
                keep = False
        if self._global_scale_changed:
            self._orig_scale = self._scale
            box = QMessageBox(QMessageBox.Icon.Information, self.TITLE,
                              "You must log off your computer to apply these changes.",
                              parent=self)
            box.setInformativeText("Save any open files and close all programs before you log off.")
            now = box.addButton("Log Off Now", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Log Off Later", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is now:
                run(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.Shutdown",
                     "/Shutdown", "org.kde.Shutdown.logout"])
        self._loading = True
        self.load()
        self._loading = False
        return keep
