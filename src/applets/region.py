# SPDX-License-Identifier: GPL-3.0-or-later
"""Regional and Language Options (Windows Vista style).

Formats and display language are separate, like Windows:
- Formats: plasma-localerc [Formats] LC_NUMERIC/LC_TIME/LC_MONETARY/LC_MEASUREMENT/
  LC_PAPER/LC_ADDRESS/LC_NAME/LC_TELEPHONE (all set, because the system locale
  /etc/default/locale may override what isn't); live Examples rendered with QLocale.
- Display language: [Formats] LANG + [Translations] LANGUAGE.
- Administrative: copy to the welcome screen / new accounts with systemd-localed
  SetLocale (UAC prompt).
Missing languages: Ubuntu's check-language-support lists the language packs; they are
installed through PackageKit (as KDE's region module does on Ubuntu). Changes apply at
the next logon."""
import glob
import os

from PyQt6.QtCore import QDate, QLocale, QTime, Qt
from PyQt6.QtWidgets import QComboBox, QLabel, QMessageBox, QPushButton

import packagekit as pk
from applets.base import AppletDialog
from ui import form_grid, gap, hbox, kread, kwrite_cmd, run, section, text_label
import distro

RC = "plasma-localerc"
FORMAT_KEYS = ["LC_NUMERIC", "LC_TIME", "LC_MONETARY", "LC_MEASUREMENT", "LC_PAPER", "LC_ADDRESS",
               "LC_NAME", "LC_TELEPHONE"]
SUPPORTED = "/usr/share/i18n/SUPPORTED"


def utf8_locales():
    """UTF-8 locales glibc can generate (Debian/Ubuntu's SUPPORTED list)."""
    out = []
    try:
        for line in open(SUPPORTED, encoding="utf-8"):
            name = line.split()[0] if line.strip() else ""
            if name.endswith(".UTF-8") and "@" not in name:
                out.append(name)
    except OSError:
        out = ["en_US.UTF-8"]
    return out


def locale_title(name):
    """'nl_NL.UTF-8' -> 'Dutch (Netherlands)'"""
    loc = QLocale(name.split(".")[0])
    lang = QLocale.languageToString(loc.language())
    terr = QLocale.territoryToString(loc.territory())
    return f"{lang} ({terr})" if terr and terr != "AnyTerritory" else lang


def generated_locales():
    """Locales generated on this system, normalised like 'nl_nl.utf-8'."""
    ok, out, _ = run(["locale", "-a"])
    return {l.lower().replace(".utf8", ".utf-8") for l in out.split()} if ok else set()


def translations():
    """Installed UI translations (Plasma's own catalog decides what's really usable)."""
    codes = {"en_US"}
    for mo in glob.glob("/usr/share/locale/*/LC_MESSAGES/plasmashell.mo"):
        codes.add(mo.split("/")[4])
    return sorted(codes)


def full_locale(lang_code, supported):
    """'nl' -> 'nl_NL.UTF-8', 'pt_BR' -> 'pt_BR.UTF-8'."""
    if "_" in lang_code:
        cand = f"{lang_code.split('@')[0]}.UTF-8"
        return cand if cand in supported else "en_US.UTF-8"
    preferred = f"{lang_code}_{lang_code.upper()}.UTF-8"
    if preferred in supported:
        return preferred
    return next((l for l in supported if l.startswith(lang_code + "_")), "en_US.UTF-8")


class RegionAndLanguage(AppletDialog):
    ID = "region"
    TITLE = "Regional and Language Options"
    ICON = "preferences-desktop-locale"
    ADVANCED = "kcm:kcm_regionandlang"
    REPLACES = ["kcm_regionandlang"]

    def build(self):
        self.supported = utf8_locales()
        # --- Formats ----------------------------------------------------------------------
        page, v = self.new_page()
        self.heading(v, "Formats", "Choose how numbers, currencies, dates and times are shown.")
        row = hbox(spacing="related")
        row.addWidget(QLabel("Current format:"))
        self.format = QComboBox()
        self.format.setMaxVisibleItems(20)
        for name in sorted(self.supported, key=locale_title):
            self.format.addItem(locale_title(name), name)
        self.format.currentIndexChanged.connect(self._format_changed)
        row.addWidget(self.format, 1)
        v.addLayout(row)
        g = self.group(v, "Examples of how data is displayed using this format")
        self.examples = form_grid(label_column=False)
        g.addLayout(self.examples)
        v.addStretch(1)
        self.add_tab(page, "Formats", "formats")

        # --- Keyboards and Languages ---------------------------------------------------------
        page2, v2 = self.new_page()
        g2 = self.group(v2, "Keyboards and other input languages", "preferences-desktop-keyboard", "medium")
        g2.addWidget(text_label("To change your keyboard or input language click Change keyboards.", "body"))
        row2 = hbox(spacing="related")
        row2.addStretch(1)
        kb = QPushButton("Change keyboards…")
        kb.clicked.connect(self._keyboards)
        row2.addWidget(kb)
        g2.addLayout(row2)
        g3 = self.group(v2, "Display language", "preferences-desktop-locale", "medium")
        g3.addWidget(text_label("Choose the language used in menus, windows and dialogs.", "body"))
        self.display = QComboBox()
        for code in translations():
            self.display.addItem(locale_title(code), code)
        self.display.currentIndexChanged.connect(self.changed)
        g3.addWidget(self.display)
        v2.addStretch(1)
        self.add_tab(page2, "Keyboards and Languages", "languages")

        # --- Administrative ---------------------------------------------------------------------
        page3, v3 = self.new_page()
        g4 = self.group(v3, "Welcome screen and new user accounts", "preferences-system-login", "medium")
        g4.addWidget(text_label("View and copy your international settings to the welcome screen, system "
                                "accounts and new user accounts.", "body"))
        self.system_info = text_label("", "secondary")
        g4.addWidget(self.system_info)
        row4 = hbox(spacing="related")
        row4.addStretch(1)
        copy = QPushButton("Copy settings…")
        copy.clicked.connect(self._copy_to_system)
        row4.addWidget(copy)
        g4.addLayout(row4)
        v3.addStretch(1)
        self.add_tab(page3, "Administrative", "admin")

    # --- examples ---------------------------------------------------------------------------
    def _format_changed(self, *_):
        from ui import clear_layout
        clear_layout(self.examples)
        name = self.format.currentData() or "en_US.UTF-8"
        loc = QLocale(name.split(".")[0])
        now = QDate.currentDate()
        t = QTime.currentTime()
        # the long time format without its time zone part ("t"), as Windows' example shows it
        tfmt = " ".join(x for x in loc.timeFormat(QLocale.FormatType.LongFormat).split() if "t" not in x)
        rows = [("Number:", loc.toString(123456789.00, "f", 2)),
                ("Currency:", loc.toCurrencyString(123456789.00)),
                ("Time:", loc.toString(t, tfmt)),
                ("Short date:", loc.toString(now, QLocale.FormatType.ShortFormat)),
                ("Long date:", loc.toString(now, QLocale.FormatType.LongFormat)),
                ("Measurement:", "Metric" if loc.measurementSystem() == QLocale.MeasurementSystem.MetricSystem
                 else "U.S.")]
        for r, (k, val) in enumerate(rows):
            self.examples.addWidget(text_label(k, "secondary"), r, 0)
            self.examples.addWidget(text_label(val, "value"), r, 1)
        self.examples.setColumnStretch(1, 1)
        self.changed()

    # --- state ------------------------------------------------------------------------------
    def load(self):
        fmt = (kread(RC, "Formats", "LC_TIME", "") or os.environ.get("LC_TIME")
               or kread(RC, "Formats", "LANG", "") or os.environ.get("LANG", "en_US.UTF-8"))
        fmt = fmt.replace(".utf8", ".UTF-8")
        self._fmt = fmt
        i = self.format.findData(fmt)
        if i < 0:
            self.format.addItem(locale_title(fmt), fmt)
            i = self.format.count() - 1
        self.format.setCurrentIndex(i)
        self._format_changed()
        lang = (kread(RC, "Translations", "LANGUAGE", "") or os.environ.get("LANGUAGE", "")).split(":")[0]
        if not lang:
            lang = (kread(RC, "Formats", "LANG", "") or os.environ.get("LANG", "en_US")).split(".")[0]
        self._lang = lang
        j = self.display.findData(lang)
        if j < 0:
            j = self.display.findData(lang.split("_")[0])
        self.display.setCurrentIndex(max(j, 0))
        self._load_system_locale()

    def _load_system_locale(self):
        """The system locale (welcome screen, new accounts) from systemd-localed."""
        ok, out, _ = run(["localectl", "status"])
        sys_line = next((l.strip() for l in out.splitlines() if "System Locale" in l), "")
        self.system_info.setText("Welcome screen: " + (sys_line.split(":", 1)[1].strip() if sys_line else "unknown"))

    def apply_changes(self):
        cmds = []
        self._needs_logoff = False
        self._missing = []
        fmt = self.format.currentData()
        if fmt and fmt != self._fmt:
            cmds += [kwrite_cmd(RC, "Formats", k, fmt) for k in FORMAT_KEYS]
            self._needs_logoff = True
            if fmt.lower() not in generated_locales():
                self._missing.append(fmt.split(".")[0])
        lang = self.display.currentData()
        if lang and lang != self._lang:
            cmds.append(kwrite_cmd(RC, "Formats", "LANG", full_locale(lang, self.supported)))
            cmds.append(kwrite_cmd(RC, "Translations", "LANGUAGE", lang if lang == "en_US" else f"{lang}:en_US"))
            self._needs_logoff = True
            self._missing.append(lang)
        return cmds

    def after_apply(self):
        self._fmt = self.format.currentData()
        self._lang = self.display.currentData()
        if self._missing:
            self._install_language_support(self._missing)
        elif self._needs_logoff:
            self._ask_logoff()

    # --- language packs ---------------------------------------------------------------------------
    def _install_language_support(self, langs):
        """Offer the missing language packs (Ubuntu's check-language-support) via PackageKit,
        then ask to log off."""
        args = ["check-language-support"] + [f"--language={l.split('.')[0]}" for l in langs if l != "en_US"]
        if len(args) == 1:      # only en_US: without --language it would list the packs of the
            self._ask_logoff()  # current system language instead
            return
        ok, out, _ = run(args, timeout=60)
        pkgs = out.split() if ok else []
        if not pkgs:
            self._ask_logoff()
            return
        if QMessageBox.question(self, self.TITLE, f"{distro.NAME} needs to install language support for your new "
                                "settings.\n\nInstall it now?") != QMessageBox.StandardButton.Yes:
            self._ask_logoff()
            return
        self.setCursor(Qt.CursorShape.BusyCursor)
        ids = []
        r = pk.Transaction(self)
        r.package.connect(lambda _i, pid, _s: ids.append(pid))

        def resolved(ok, err):
            if not ok or not ids:
                self.unsetCursor()
                self._ask_logoff()
                return
            t = pk.Transaction(self)
            t.finished.connect(lambda ok2, err2: self._installed(ok2, err2))
            t.install(ids)
            self._tx = t
        r.finished.connect(resolved)
        r.resolve_available(pkgs)
        self._rx = r

    def _installed(self, ok, err):
        self.unsetCursor()
        if not ok:
            QMessageBox.warning(self, self.TITLE, f"Language support could not be installed.\n\n{err}")
        self._ask_logoff()

    def _ask_logoff(self):
        box = QMessageBox(QMessageBox.Icon.Information, self.TITLE,
                          "You must log off for these changes to take effect.", parent=self)
        now = box.addButton("Log Off Now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Log Off Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            run(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.Shutdown",
                 "/Shutdown", "org.kde.Shutdown.logout"])

    # --- other actions --------------------------------------------------------------------------------
    def _keyboards(self):
        import applets
        if applets.available("keyboard"):
            self._kb = applets.open_applet("keyboard", "languages")
        else:
            from PyQt6.QtCore import QProcess
            QProcess.startDetached("kcmshell6", ["kcm_keyboard"])

    def _copy_to_system(self):
        fmt = self.format.currentData() or "en_US.UTF-8"
        lang = full_locale(self.display.currentData() or "en_US", self.supported)
        assigns = [f"LANG={lang}"] + [f"{k}={fmt}" for k in ("LC_NUMERIC", "LC_TIME", "LC_MONETARY",
                                                             "LC_MEASUREMENT", "LC_PAPER")]
        if QMessageBox.question(self, self.TITLE, "Copy your format and display language to the welcome "
                                "screen and new user accounts?\n\n" + "\n".join(assigns)) != \
                QMessageBox.StandardButton.Yes:
            return
        from ui import Jobs
        # SetLocale(as locale, b interactive): the UAC prompt appears if polkit wants one
        cmd = ["busctl", "--system", "--allow-interactive-authorization=yes", "call", "org.freedesktop.locale1",
               "/org/freedesktop/locale1", "org.freedesktop.locale1", "SetLocale", "asb",
               str(len(assigns)), *assigns, "true"]
        self._sysjob = Jobs([cmd], self)
        # refresh only the system locale line: a full load() would drop unapplied choices
        self._sysjob.finished.connect(lambda ok, err: (QMessageBox.warning(self, self.TITLE, err) if not ok
                                                       else None, self._load_system_locale()))
        self._sysjob.start()
