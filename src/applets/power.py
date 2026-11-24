# SPDX-License-Identifier: GPL-3.0-or-later
"""Power Options (Windows Vista style) on top of power-profiles-daemon and PowerDevil.

Power plans map to power-profiles-daemon profiles; the choice is also stored as the
PowerDevil PowerProfile of both power sources, so plugging in/out doesn't switch it back.
Timeouts and button/lid actions are PowerDevil's per-source settings (powerdevilrc).
Keys and defaults follow powerdevil (PowerDevilProfileSettings.kcfg,
daemon/powerdevilsettingsdefaults.cpp, Plasma/6.6)."""
import glob

from PyQt6.QtWidgets import QButtonGroup, QComboBox, QLabel, QRadioButton

from applets.base import AppletDialog
from style import SPACE
from ui import form_grid, kread, kwrite_cmd, run, section, text_label

RC = "powerdevilrc"

PLANS = [
    ("balanced", "Balanced (recommended)",
     "Automatically balances performance with energy consumption on capable hardware."),
    ("power-saver", "Power saver",
     "Saves energy by reducing your computer’s performance where possible."),
    ("performance", "High performance",
     "Favors performance, but may use more energy."),
]

TIMES = [(60, "1 minute"), (120, "2 minutes"), (180, "3 minutes"), (300, "5 minutes"),
         (600, "10 minutes"), (900, "15 minutes"), (1200, "20 minutes"), (1500, "25 minutes"),
         (1800, "30 minutes"), (2700, "45 minutes"), (3600, "1 hour"), (7200, "2 hours"),
         (10800, "3 hours"), (14400, "4 hours"), (18000, "5 hours"), (0, "Never")]

# PowerDevil PowerButtonAction values
ACTIONS = [(0, "Do nothing"), (1, "Sleep"), (2, "Hibernate"), (8, "Shut down"),
           (16, "Ask me what to do"), (32, "Lock the computer"), (64, "Turn off the display")]

# (profile group, column title); defaults from powerdevilsettingsdefaults.cpp
SOURCES = [("Battery", "On battery"), ("AC", "Plugged in")]
DEFAULT_DISPLAY_OFF = {"AC": 600, "Battery": 300}
DEFAULT_SLEEP = {"AC": 900, "Battery": 600}


def has_battery():
    for t in glob.glob("/sys/class/power_supply/*/type"):
        try:
            if open(t).read().strip() == "Battery":
                return True
        except OSError:
            pass
    return False


def available_profiles():
    """Profile names from `powerprofilesctl list` ([] without power-profiles-daemon): the
    unindented "name:" lines (a "* " marks the active one); detail lines are indented."""
    ok, out, _ = run(["powerprofilesctl", "list"])
    if not ok:
        return []
    return [l.strip().lstrip("* ").rstrip(":") for l in out.splitlines()
            if l.strip().endswith(":") and not l.startswith(" " * 4)]


def active_profile():
    ok, out, _ = run(["powerprofilesctl", "get"])
    return out.strip() if ok else ""


class PowerOptions(AppletDialog):
    ID = "power"
    TITLE = "Power Options"
    ICON = "preferences-system-power-management"
    ADVANCED = "kcm:kcm_powerdevilprofilesconfig"
    REPLACES = ["kcm_powerdevilprofilesconfig"]
    SIZE = "dialog_wide"

    def build(self):
        self.sources = SOURCES if has_battery() else [("AC", "")]
        self.profiles = available_profiles()

        # --- Plans + idle timers -------------------------------------------------------
        page, v = self.new_page()
        self.heading(v, "Select a power plan",
                     "Power plans can help you maximize your computer\u2019s performance or conserve energy.")
        self.plan_group = QButtonGroup(self)
        self.plan_buttons = {}
        indent = self.option_indent()
        for pid, name, desc in PLANS:
            # without power-profiles-daemon no plan can be set (powerprofilesctl would fail
            # and abort the rest of Apply): show "not supported" instead
            if pid not in self.profiles:
                continue
            rb = QRadioButton(name)
            rb.setFont(text_label("", "strong").font())
            self.plan_group.addButton(rb)
            self.plan_buttons[pid] = rb
            rb.toggled.connect(self.changed)
            v.addWidget(rb)
            d = text_label(desc, "secondary")
            d.setContentsMargins(indent, 0, 0, SPACE["link_gap"])
            v.addWidget(d)
        if not self.plan_buttons:
            v.addWidget(text_label("Power plans aren\u2019t supported on this computer.", "secondary"))

        section(v, "Change settings for the plan")
        grid = self._source_grid()
        self.display_combo, self.sleep_combo = {}, {}
        for row, label, store, items in ((1, "Turn off the display:", self.display_combo, TIMES),
                                         (2, "Put the computer to sleep:", self.sleep_combo, TIMES)):
            self._combo_row(grid, row, label, store, items)
        v.addLayout(grid)
        v.addStretch(1)
        self.add_tab(page, "Power Plans", "plans")

        # --- Buttons and lid -----------------------------------------------------------
        page2, v2 = self.new_page()
        self.heading(v2, "Define power buttons and lid",
                     "Choose what happens when you press the power button or close the lid.")
        g2 = self._source_grid()
        self.button_combo, self.lid_combo = {}, {}
        self._combo_row(g2, 1, "When I press the power button:", self.button_combo, ACTIONS)
        if has_battery():
            self._combo_row(g2, 2, "When I close the lid:", self.lid_combo, ACTIONS)
        v2.addLayout(g2)
        v2.addStretch(1)
        self.add_tab(page2, "Power Buttons and Lid", "buttons")

    def _source_grid(self):
        """Grid with a caption per power source column ("On battery", "Plugged in")."""
        g = form_grid()
        for col, (_, title) in enumerate(self.sources, start=1):
            if title:
                g.addWidget(text_label(title, "caption"), 0, col)
        g.setColumnStretch(len(self.sources) + 1, 1)
        return g

    def _combo_row(self, grid, row, label, store, items):
        """A labelled row with one combo per power source, kept in store[source]."""
        grid.addWidget(QLabel(label), row, 0)
        for col, (src, _) in enumerate(self.sources, start=1):
            cb = QComboBox()
            for val, name in items:
                cb.addItem(name, val)
            cb.currentIndexChanged.connect(self.changed)
            store[src] = cb
            grid.addWidget(cb, row, col)

    @staticmethod
    def _select(combo, value):
        i = combo.findData(value)
        if i < 0:   # a custom value from System Settings: show it as an extra entry
            mins = value // 60
            combo.addItem(f"{mins} minutes" if value else "Never", value)
            i = combo.count() - 1
        combo.setCurrentIndex(i)

    def load(self):
        cur = active_profile()
        if cur in self.plan_buttons:
            self.plan_buttons[cur].setChecked(True)
        for src, _ in self.sources:
            off_enabled = kread(RC, [src, "Display"], "TurnOffDisplayWhenIdle", "true") == "true"
            off = int(kread(RC, [src, "Display"], "TurnOffDisplayIdleTimeoutSec", DEFAULT_DISPLAY_OFF[src]))
            self._select(self.display_combo[src], off if off_enabled else 0)
            action = int(kread(RC, [src, "SuspendAndShutdown"], "AutoSuspendAction", 1))
            sleep = int(kread(RC, [src, "SuspendAndShutdown"], "AutoSuspendIdleTimeoutSec", DEFAULT_SLEEP[src]))
            self._select(self.sleep_combo[src], sleep if action else 0)
            self._select(self.button_combo[src],
                         int(kread(RC, [src, "SuspendAndShutdown"], "PowerButtonAction", 16)))
            if src in self.lid_combo:
                self._select(self.lid_combo[src], int(kread(RC, [src, "SuspendAndShutdown"], "LidAction", 1)))
        self._loaded = self._snapshot()

    def _snapshot(self):
        """Current choices, compared with the loaded ones so Apply writes only what changed."""
        snap = {"plan": next((p for p, b in self.plan_buttons.items() if b.isChecked()), None)}
        for src, _ in self.sources:
            snap[(src, "off")] = self.display_combo[src].currentData()
            snap[(src, "sleep")] = self.sleep_combo[src].currentData()
            snap[(src, "button")] = self.button_combo[src].currentData()
            if src in self.lid_combo:
                snap[(src, "lid")] = self.lid_combo[src].currentData()
        return snap

    def apply_changes(self):
        now, old = self._snapshot(), self._loaded
        cmds = []
        if now["plan"] and now["plan"] != old["plan"]:
            cmds.append(["powerprofilesctl", "set", now["plan"]])
            # keep the plan when switching between battery and AC
            for src in ("AC", "Battery", "LowBattery"):
                cmds.append(kwrite_cmd(RC, [src, "Performance"], "PowerProfile", now["plan"]))
        for src, _ in self.sources:
            off = now[(src, "off")]
            if off != old[(src, "off")]:
                cmds.append(kwrite_cmd(RC, [src, "Display"], "TurnOffDisplayWhenIdle", bool(off)))
                if off:
                    cmds.append(kwrite_cmd(RC, [src, "Display"], "TurnOffDisplayIdleTimeoutSec", off))
            sleep = now[(src, "sleep")]
            if sleep != old[(src, "sleep")]:
                cmds.append(kwrite_cmd(RC, [src, "SuspendAndShutdown"], "AutoSuspendAction", 1 if sleep else 0))
                if sleep:
                    cmds.append(kwrite_cmd(RC, [src, "SuspendAndShutdown"], "AutoSuspendIdleTimeoutSec", sleep))
            if now[(src, "button")] != old[(src, "button")]:
                cmds.append(kwrite_cmd(RC, [src, "SuspendAndShutdown"], "PowerButtonAction", now[(src, "button")]))
            if (src, "lid") in now and now[(src, "lid")] != old[(src, "lid")]:
                cmds.append(kwrite_cmd(RC, [src, "SuspendAndShutdown"], "LidAction", now[(src, "lid")]))
        if cmds:
            cmds.append(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.Solid.PowerManagement",
                         "/org/kde/Solid/PowerManagement", "org.kde.Solid.PowerManagement.reparseConfiguration"])
            cmds.append(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.Solid.PowerManagement",
                         "/org/kde/Solid/PowerManagement", "org.kde.Solid.PowerManagement.refreshStatus"])
        return cmds

    def after_apply(self):
        self._loaded = self._snapshot()
