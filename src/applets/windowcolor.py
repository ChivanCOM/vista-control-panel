# SPDX-License-Identifier: GPL-3.0-or-later
"""Window Color and Appearance (Windows Vista style) for the AeroShell glass effect.

Writes the same kwinrc [Effect-aeroglassblur] keys as the effect's own color dialog
(aeroshell-kwin-components, kcm/mainwindow.cpp): AccentColorGroup/AccentColorName pick
the preset, AeroHue (degrees, hslHue), AeroSaturation/AeroBrightness (percent, HSV),
AeroIntensity (alpha 0-255), EnableTransparency. Changes preview live, like Vista;
Cancel restores the previous colors."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QCheckBox, QGroupBox, QLabel, QSlider, QToolButton

import style
from applets.base import AppletDialog
from style import SIZE
from ui import Link, form_grid, hbox, kread, kwrite, run, text_label

GROUP = "Effect-aeroglassblur"
VISTA_GROUP = 1
# (index in the effect's preset list, name, ARGB) - the Windows Vista colors
VISTA_COLORS = [
    (17, "Default", "45409efe"), (18, "Graphite", "a3000000"), (19, "Blue", "a8004ade"),
    (20, "Teal", "82008ca5"), (21, "Red", "9cce0c0f"), (22, "Orange", "a6ff7700"),
    (23, "Pink", "49f93ee7"), (24, "Frost", "cceff7f7"),
]


def effect_loaded():
    """True when KWin runs the aeroglassblur effect (the dialog has nothing to set otherwise)."""
    ok, out, _ = run(["dbus-send", "--session", "--print-reply", "--dest=org.kde.KWin", "/Effects",
                      "org.kde.kwin.Effects.isEffectLoaded", "string:aeroglassblur"])
    return ok and "true" in out


def argb(hexstr):
    """'AARRGGBB' -> QColor with alpha."""
    a = int(hexstr[0:2], 16)
    c = QColor("#" + hexstr[2:])
    c.setAlpha(a)
    return c


class Swatch(QToolButton):
    """One of Vista's color presets: a glossy, checkable color button."""

    def __init__(self, name, color):
        super().__init__()
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setToolTip(name)
        self.setFixedSize(*SIZE["swatch"])
        top = QColor(color)
        top.setAlpha(255)
        light = top.lighter(160)
        c = style.COLOR
        self.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {c['swatch_border']}; border-radius: 4px;
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {light.name()},
                            stop:0.5 {top.name()}, stop:1 {top.darker(130).name()}); }}
            QToolButton:hover {{ border: 2px solid {c['select_hover']}; }}
            QToolButton:checked {{ border: 3px solid {c['select']}; }}""")


class WindowColor(AppletDialog):
    ID = "windowcolor"
    TITLE = "Window Color and Appearance"
    ICON = "preferences-desktop-color"
    ADVANCED = "kcm:kcm_colors"
    TABBED = False
    SIZE = "dialog_wide"

    @classmethod
    def available(cls):
        return effect_loaded()

    def build(self):
        _, v = self.new_page(self.page)
        self.heading(v, "Change the color of your windows",
                     "You can change the color of windows, the Start menu, and the taskbar. Pick one of "
                     "the available colors or create your own color using the color mixer.")
        row = hbox(spacing="tile")
        self.swatches = {}
        for idx, name, hexstr in VISTA_COLORS:
            sw = Swatch(name, argb(hexstr))
            sw.clicked.connect(lambda _=False, i=idx: self._pick(i))
            self.swatches[idx] = sw
            row.addWidget(sw)
        row.addStretch(1)
        v.addLayout(row)
        self.color_name = text_label("", "body")
        v.addWidget(self.color_name)

        self.transparency = QCheckBox("Enable transparency")
        self.transparency.toggled.connect(self._edited)
        v.addWidget(self.transparency)

        g = form_grid()
        self.intensity = self._slider(0, 255)
        g.addWidget(QLabel("Color intensity:"), 0, 0)
        g.addWidget(self.intensity, 0, 1)
        g.setColumnStretch(1, 1)
        v.addLayout(g)

        toggle = Link("Show color mixer", "link")
        v.addWidget(toggle)
        self.mixer = QGroupBox()
        mg = form_grid()
        self.mixer.setLayout(mg)
        self.hue = self._slider(0, 359, hue=True)
        self.sat = self._slider(0, 100)
        self.bri = self._slider(0, 100)
        for r, (label, s) in enumerate((("Hue:", self.hue), ("Saturation:", self.sat), ("Brightness:", self.bri))):
            mg.addWidget(QLabel(label), r, 0)
            mg.addWidget(s, r, 1)
        mg.setColumnStretch(1, 1)
        self.mixer.setVisible(False)
        toggle.clicked.connect(lambda: (self.mixer.setVisible(not self.mixer.isVisible()),
                                        toggle.setText("Hide color mixer" if self.mixer.isVisible()
                                                       else "Show color mixer")))
        v.addWidget(self.mixer)
        v.addStretch(1)

        self._preview_timer = QTimer(self, singleShot=True, interval=120)
        self._preview_timer.timeout.connect(self._preview)

    def _slider(self, lo, hi, hue=False):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        if hue:
            s.setStyleSheet("QSlider::groove:horizontal { height: 8px; border-radius: 3px; background: "
                            "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f00, stop:0.17 #ff0, stop:0.33 #0f0,"
                            " stop:0.5 #0ff, stop:0.67 #00f, stop:0.83 #f0f, stop:1 #f00); }")
        s.valueChanged.connect(self._edited)
        return s

    # --- state ----------------------------------------------------------------------
    def _values(self):
        """The kwinrc keys for the current controls; a custom mix keeps the stored preset ids."""
        sel = next((i for i, sw in self.swatches.items() if sw.isChecked()), None)
        return {
            "AccentColorGroup": VISTA_GROUP if sel is not None else
            int(kread("kwinrc", GROUP, "AccentColorGroup", 0)),
            "AccentColorName": sel if sel is not None else int(kread("kwinrc", GROUP, "AccentColorName", 1)),
            "AeroHue": self.hue.value(),
            "AeroSaturation": self.sat.value(),
            "AeroBrightness": self.bri.value(),
            "AeroIntensity": self.intensity.value(),
            "EnableTransparency": self.transparency.isChecked(),
        }

    def load(self):
        self._orig = {
            "AccentColorGroup": int(kread("kwinrc", GROUP, "AccentColorGroup", 0)),
            "AccentColorName": int(kread("kwinrc", GROUP, "AccentColorName", 1)),
            "AeroHue": int(kread("kwinrc", GROUP, "AeroHue", 0)),
            "AeroSaturation": int(kread("kwinrc", GROUP, "AeroSaturation", 50)),
            "AeroBrightness": int(kread("kwinrc", GROUP, "AeroBrightness", 50)),
            "AeroIntensity": int(kread("kwinrc", GROUP, "AeroIntensity", 50)),
            "EnableTransparency": kread("kwinrc", GROUP, "EnableTransparency", "true") == "true",
        }
        self._set_controls(self._orig)
        if self._orig["AccentColorGroup"] == VISTA_GROUP and self._orig["AccentColorName"] in self.swatches:
            self.swatches[self._orig["AccentColorName"]].setChecked(True)
        self._update_name()

    def _set_controls(self, vals):
        for w in (self.hue, self.sat, self.bri, self.intensity, self.transparency):
            w.blockSignals(True)
        self.hue.setValue(vals["AeroHue"])
        self.sat.setValue(vals["AeroSaturation"])
        self.bri.setValue(vals["AeroBrightness"])
        self.intensity.setValue(vals["AeroIntensity"])
        self.transparency.setChecked(vals["EnableTransparency"])
        for w in (self.hue, self.sat, self.bri, self.intensity, self.transparency):
            w.blockSignals(False)

    def _update_name(self):
        sel = next((name for i, name, _ in VISTA_COLORS if self.swatches[i].isChecked()), None)
        self.color_name.setText(f"Current color: {sel}" if sel else "Current color: Custom")

    def _pick(self, idx):
        hexstr = next(h for i, _, h in VISTA_COLORS if i == idx)
        c = argb(hexstr)
        self._set_controls({
            "AeroHue": max(c.hslHue(), 0), "AeroSaturation": round(c.hsvSaturationF() * 100),
            "AeroBrightness": round(c.valueF() * 100), "AeroIntensity": c.alpha(),
            "EnableTransparency": self.transparency.isChecked(),
        })
        self._update_name()
        self._edited()

    def _edited(self, *_):
        if self._loading:
            return
        if self.sender() in (self.hue, self.sat, self.bri):
            for sw in self.swatches.values():      # mixing makes it a custom color
                sw.setAutoExclusive(False)
                sw.setChecked(False)
                sw.setAutoExclusive(True)
            self._update_name()
        self.changed()
        self._preview_timer.start()

    # --- live preview / apply / cancel ----------------------------------------------------
    def _write(self, vals):
        """Save the keys and have KWin reload the effect (used for the live preview too)."""
        for k, val in vals.items():
            kwrite("kwinrc", GROUP, k, val)
        run(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.KWin", "/Effects",
             "org.kde.kwin.Effects.reconfigureEffect", "string:aeroglassblur"])

    def _preview(self):
        self._write(self._values())

    def apply_changes(self):
        self._preview_timer.stop()
        self._write(self._values())      # already previewed; make sure the final values are saved
        return []

    def after_apply(self):
        self._orig = self._values()

    def revert(self):
        self._preview_timer.stop()
        if self._dirty:
            self._write(self._orig)
