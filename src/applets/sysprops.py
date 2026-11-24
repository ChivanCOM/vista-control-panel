# SPDX-License-Identifier: GPL-3.0-or-later
"""System Properties (Windows Vista style): computer name and description (systemd-hostnamed),
plus shortcuts to hardware, performance and system protection tools.

The description (pretty hostname) is set with hostnamectl, which asks polkit itself; the
computer name goes through helpers/set-computer-name under pkexec, which also updates
/etc/hosts."""
import os
import re
import shutil

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QGroupBox, QLabel, QLineEdit, QPushButton

from applets.base import AppletDialog, kcm_argv
from style import SIZE
from ui import form_grid, gap, hbox, icon_label, run, set_role, text_label, vbox
import distro

HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "helpers", "set-computer-name")
# same rule as the helper (an RFC 1123 host label); the helper checks again as root
NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def launch(argv):
    """Start a program detached -> False if it isn't installed."""
    if argv and shutil.which(argv[0]):
        QProcess.startDetached(argv[0], argv[1:])
        return True
    return False


class RenameDialog(QDialog):
    """Windows' "Computer Name Changes" box: OK stays disabled until the name is valid."""

    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Computer Name Changes")
        v = vbox(self, "dialog", "related")
        v.addWidget(text_label("You can change the name of this computer. Changes might affect "
                               "access to network resources.", "secondary"))
        v.addWidget(QLabel("Computer name:"))
        self.edit = QLineEdit(current)
        self.edit.setMaxLength(63)
        v.addWidget(self.edit)
        self.hint = text_label("Use letters (A-Z), numbers (0-9) and hyphens (-). No spaces.", "secondary")
        v.addWidget(self.hint)
        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        v.addWidget(self.bb)
        self.edit.textChanged.connect(self._validate)
        self._validate(current)

    def _validate(self, text):
        ok = bool(NAME_RE.match(text))
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        set_role(self.hint, "secondary" if ok else "error")

    def name(self):
        return self.edit.text().strip()


class SystemProperties(AppletDialog):
    ID = "sysprops"
    TITLE = "System Properties"
    ICON = "computer"
    ADVANCED = "app:kinfocenter"

    def build(self):
        # --- Computer Name --------------------------------------------------------------
        page, v = self.new_page()
        top = hbox(spacing="icon_gap")
        top.addWidget(icon_label("computer", "large"), 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(text_label(f"{distro.NAME} uses the following information to identify your computer "
                                 "on the network.", "body"), 1)
        v.addLayout(top)
        gap(v)
        g = form_grid()
        g.addWidget(QLabel("Computer description:"), 0, 0)
        self.desc = QLineEdit()
        self.desc.textChanged.connect(self.changed)
        g.addWidget(self.desc, 0, 1)
        g.addWidget(text_label("For example: \u201cKitchen Computer\u201d or \u201cMary\u2019s Computer\u201d.",
                               "secondary"), 1, 1)
        g.addWidget(QLabel("Full computer name:"), 2, 0)
        self.name_lbl = text_label("", "value")
        g.addWidget(self.name_lbl, 2, 1)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        gap(v)
        row = hbox(spacing="related")
        row.addWidget(text_label("To rename this computer, click Change.", "body"), 1)
        b = QPushButton("Change\u2026")
        b.clicked.connect(self._rename)
        row.addWidget(b)
        v.addLayout(row)
        v.addStretch(1)
        self.add_tab(page, "Computer Name", "name")

        # --- Hardware ----------------------------------------------------------------------
        hw, hv = self.new_page()
        self._group(hv, "Device Manager", "preferences-desktop-peripherals",
                    "The Device Manager lists all the hardware devices installed on your computer.",
                    [("Device Manager", ["kinfocenter"])])
        self._group(hv, "Drivers", "system-software-update",
                    "Find and install additional drivers, for example for graphics cards and Wi-Fi.",
                    [("Additional Drivers", ["software-properties-qt", "--open-tab=4"])])
        hv.addStretch(1)
        self.add_tab(hw, "Hardware", "hardware")

        # --- Advanced ------------------------------------------------------------------------
        adv, av = self.new_page()
        av.addWidget(text_label("You must be logged on as an Administrator to make most of these changes.",
                                "secondary"))
        self._group(av, "Performance", "preferences-system-performance",
                    "Visual effects, processor scheduling and memory usage.",
                    [("Settings\u2026", kcm_argv("kcm_kwin_effects")), ("Task Manager", ["plasma-systemmonitor"])])
        self._group(av, "User Profiles", "system-users", "Settings related to your logon.",
                    [("Settings\u2026", kcm_argv("kcm_users"))])
        self._group(av, "Startup and Recovery", "preferences-system-splash",
                    "System startup screen and startup programs.",
                    [("Startup Screen\u2026", kcm_argv("kcm_plymouth")), ("Startup Programs\u2026", kcm_argv("kcm_autostart"))])
        av.addStretch(1)
        self.add_tab(adv, "Advanced", "advanced")

        # --- System Protection ------------------------------------------------------------
        sp, sv = self.new_page()
        if shutil.which("timeshift-launcher"):
            self._group(sv, "System Restore", "preferences-system-backup",
                        "Use restore points (snapshots) to undo unwanted system changes. Your personal "
                        "files are not affected.",
                        [("System Restore\u2026", ["timeshift-launcher"])])
        else:
            self._group(sv, "System Restore", "preferences-system-backup",
                        "System Restore (Timeshift) isn\u2019t installed. Install it to create restore points.",
                        [("Get Timeshift\u2026", ["plasma-discover", "--search", "timeshift"])])
        self._group(sv, "Back up files", "document-save",
                    "Back up your documents and pictures on a schedule.",
                    [("Backup Settings\u2026", kcm_argv("kcm_kup"))])
        sv.addStretch(1)
        self.add_tab(sp, "System Protection", "protection")

    def _group(self, layout, title, icon, text, buttons):
        """A titled group: medium icon, description, buttons aligned right."""
        box = QGroupBox(title)
        h = hbox(box, "dialog_page", "icon_gap")
        h.addWidget(icon_label(icon, "medium"), 0, Qt.AlignmentFlag.AlignTop)
        col = vbox(spacing="related")
        col.addWidget(text_label(text, "body"))
        row = hbox(spacing="related")
        row.addStretch(1)
        shown = 0
        for label, argv in buttons:
            if not argv or not shutil.which(argv[0]):
                continue
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, a=argv: launch(a))
            row.addWidget(b)
            shown += 1
        if shown:
            col.addLayout(row)
        h.addLayout(col, 1)
        layout.addWidget(box)

    def load(self):
        self._desc = run(["hostnamectl", "--pretty"])[1].strip()
        self._name = self._new_name = run(["hostnamectl", "--static"])[1].strip() or run(["hostname"])[1].strip()
        self.desc.setText(self._desc)
        self.name_lbl.setText(self._name)

    def _rename(self):
        d = RenameDialog(self._new_name, self)
        if d.exec() and d.name() != self._new_name:
            self._new_name = d.name()
            self.name_lbl.setText(f"{self._new_name}  (after you click Apply)")
            self.changed()

    def apply_changes(self):
        cmds = []
        if self.desc.text().strip() != self._desc:
            # "--": a description starting with "-" must not be read as an option
            cmds.append(["hostnamectl", "set-hostname", "--pretty", "--", self.desc.text().strip()])
        if self._new_name != self._name:
            cmds.append(["pkexec", HELPER, self._new_name])
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
