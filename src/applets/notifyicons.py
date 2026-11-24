# SPDX-License-Identifier: GPL-3.0-or-later
"""Notification Area Icons (Windows style) for the Vista taskbar's notification area
(VistaThemePlasma's io.gitgud.catpswin56.systemtray).

The tray's own settings (plasmoids/src/systemtray_src, package/contents/config/main.xml),
in the tray applet's [General] group of plasma-io.gitgud.catpswin56.desktop-appletsrc:
- shownItems / hiddenItems: per icon "Show" / "Hide"; in neither = "Hide when inactive"
  (KDE: shown when relevant). Program icons are matched on their StatusNotifierItem Id,
  built-in icons on their plasmoid id.
- showAllItems: the inverse of Windows' "Hide inactive icons".
- soundEnabled / networkEnabled / batteryEnabled: Windows' "System icons".

While the Vista taskbar runs, plasmashell owns that file, so changes go through its
scripting interface (org.kde.PlasmaShell.evaluateScript): writeConfig on a key of the
applet's config scheme emits configChanged, which the tray reloads from at once
(plasma-workspace shell/scripting/applet.cpp, systemtraysettings.cpp). Otherwise the file
is written directly."""
import glob
import json
import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import QCheckBox, QComboBox, QHeaderView, QPushButton, QTreeWidget, QTreeWidgetItem

from applets.base import AppletDialog
from style import ICON, SPACE
from ui import hbox, kread, kwrite_cmd, run, text_label
import distro

TRAY = "io.gitgud.catpswin56.systemtray"
SHELL_FILE = "plasma-io.gitgud.catpswin56.desktop-appletsrc"
# an AeroThemePlasma build installed outside the XDG dirs (BOONE puts it here): searched last
ATP_SHARE = "/opt/aerothemeplasma/builds/current/share"
SYSTEM = [("soundEnabled", "Volume", "io.gitgud.catpswin56.volume"),
          ("networkEnabled", "Network", "io.gitgud.catpswin56.networkmanagement"),
          ("batteryEnabled", "Power", "io.gitgud.catpswin56.battery")]
NOT_LISTED = {p for _k, _l, p in SYSTEM} | {"io.gitgud.catpswin56.notifications"}
AUTO, HIDE, SHOW = "auto", "hide", "show"
BEHAVIORS = [(AUTO, "Hide when inactive"), (HIDE, "Hide"), (SHOW, "Show")]
KEYS = ["shownItems", "hiddenItems", "showAllItems", "extraItems"] + [k for k, _l, _p in SYSTEM]


# --- where the tray keeps its settings ----------------------------------------------------
def shell_file():
    """The Plasma shell's applet config. Normally in the config home; when the Control Panel
    runs outside a BOONE session on a machine that has one, BOONE's session keeps its own
    config home (~/.local/share/denairu/vista-config), so edit that one."""
    home = distro.config_home()
    if not os.environ.get("DENAIRU_SESSION"):
        boone = os.path.expanduser(f"~/.local/share/{distro.LEGACY_ID}/vista-config")
        if os.path.isdir(boone):
            home = boone
    return os.path.join(home, SHELL_FILE)


def tray_groups(path):
    """-> ["Containments", "2", "Applets", "7", "General"] for the tray applet, or None."""
    section = None
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line.startswith("["):
                section = line
            elif line == f"plugin={TRAY}" and section:
                return [g for g in section.strip("[]").split("][")] + ["General"]
    except OSError:
        pass
    return None


def _script_for(body):
    """Plasma shell script running `body` on the first Vista tray found; `body` sets r,
    which is printed as JSON (busctl returns it as the reply string)."""
    return ("var r=null; panels().forEach(function(p){ p.widgets('%s').forEach(function(w){"
            " if (r) return; w.currentConfigGroup=['General']; %s }); }); print(JSON.stringify(r));"
            % (TRAY, body))


def shell_call(script):
    """argv evaluating a script in the running plasmashell."""
    return ["busctl", "--user", "--json=short", "call", "org.kde.plasmashell", "/PlasmaShell",
            "org.kde.PlasmaShell", "evaluateScript", "s", script]


def live_read():
    """The running tray's settings, or None when the Vista taskbar isn't running."""
    body = "r={}; %s" % " ".join(f"r['{k}']=w.readConfig('{k}');" for k in KEYS)
    ok, out, _ = run(shell_call(_script_for(body)), timeout=5)
    if not ok:
        return None
    try:
        res = json.loads(json.loads(out)["data"][0])
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return res if isinstance(res, dict) else None


def as_list(v):
    """A list setting as read live (JS array) or from the file ("a,b") -> [str]."""
    if isinstance(v, list):
        return [str(x) for x in v if str(x)]
    return [x for x in str(v or "").split(",") if x]


def as_bool(v, default):
    if v in (None, ""):
        return default
    return v is True or str(v).lower() == "true"


# --- what is in the tray ------------------------------------------------------------------
def desktop_entry(app_id):
    """The menu entry of a tray icon's program, matched on its StatusNotifierItem Id
    (desktop file id, its last dotted part, or the executable name), or None."""
    from applets.defaults import desktop_apps
    apps = desktop_apps()
    key = app_id.lower()
    for sid, a in apps.items():
        base = sid.removesuffix(".desktop").lower()
        if key in (base, base.rsplit(".", 1)[-1]) or os.path.basename(a["exec"].split(" ")[0]).lower() == key:
            return a
    return None


def pixmap_icon(data):
    """IconPixmap a(iiay): ARGB32, network byte order -> QIcon (all sizes)."""
    icon = QIcon()
    for w, h, raw in data or []:
        if w <= 0 or h <= 0 or len(raw) < w * h * 4:
            continue
        buf = bytes(raw[:w * h * 4])
        # network order ARGB -> QImage.Format_ARGB32 is host-order 0xAARRGGBB: swap per pixel
        swapped = bytearray(len(buf))
        swapped[0::4], swapped[1::4], swapped[2::4], swapped[3::4] = buf[3::4], buf[2::4], buf[1::4], buf[0::4]
        img = QImage(bytes(swapped), w, h, QImage.Format.Format_ARGB32).copy()
        icon.addPixmap(QPixmap.fromImage(img))
    return icon


def status_notifiers():
    """[(id, name, description, QIcon)] for the programs with a tray icon right now."""
    ok, out, _ = run(["busctl", "--user", "--json=short", "get-property", "org.kde.StatusNotifierWatcher",
                      "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems"])
    try:
        entries = json.loads(out)["data"] if ok else []
    except ValueError:
        entries = []
    items, seen = [], set()
    for entry in entries:
        service, _, path = entry.partition("/")
        path = "/" + path if path else "/StatusNotifierItem"
        props = ["Id", "Title", "IconName", "IconThemePath", "ToolTip", "IconPixmap"]
        ok, out, _ = run(["busctl", "--user", "--json=short", "get-property", service, path,
                          "org.kde.StatusNotifierItem"] + props, timeout=5)
        if not ok:
            continue
        vals = {}
        for name, line in zip(props, out.splitlines()):
            try:
                vals[name] = json.loads(line)["data"]
            except (ValueError, KeyError):
                vals[name] = None
        item_id = vals.get("Id") or ""
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        tip = vals.get("ToolTip") or ["", [], "", ""]
        entry_app = desktop_entry(item_id)
        name = (entry_app and entry_app["name"]) or (tip[2] if len(tip) > 2 and tip[2] != item_id else "") \
            or vals.get("Title") or item_id
        desc = tip[3] if len(tip) > 3 and tip[3] != name else ""
        icon = QIcon()
        icon_name, theme_path = vals.get("IconName") or "", vals.get("IconThemePath") or ""
        if icon_name and theme_path:
            found = glob.glob(os.path.join(theme_path, "**", icon_name + ".*"), recursive=True)
            if found:
                icon = QIcon(found[0])
        if icon.isNull() and icon_name:
            icon = QIcon.fromTheme(icon_name)
        if icon.isNull() and vals.get("IconPixmap"):
            icon = pixmap_icon(vals["IconPixmap"])
        if icon.isNull() and entry_app:
            icon = QIcon.fromTheme(entry_app["icon"])
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-executable")
        items.append((item_id, name, desc.splitlines()[0] if desc else "", icon))
    return sorted(items, key=lambda i: i[1].lower())


def plugin_dirs():
    """Folders with compiled Plasma applets (plasma/applets/*.so), AeroThemePlasma's included."""
    from PyQt6.QtCore import QLibraryInfo
    dirs = [d for d in os.environ.get("QT_PLUGIN_PATH", "").split(":") if d]
    dirs.append(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    dirs += glob.glob(os.path.join(os.path.dirname(ATP_SHARE), "lib*", "**", "qt6", "plugins"), recursive=True)
    return [os.path.join(d, "plasma", "applets") for d in dict.fromkeys(dirs)]


def plasmoid_info(plugin):
    """(name, description, icon) of a Plasma applet: a QML package (metadata.json) or a
    compiled plugin (metadata inside the .so, Plasma 6)."""
    import qtplugin
    data_dirs = [os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))] + \
        os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") + [ATP_SHARE]
    kp = None
    for d in data_dirs:
        p = os.path.join(d, "plasma", "plasmoids", plugin, "metadata.json")
        if os.path.exists(p):
            try:
                kp = json.load(open(p, encoding="utf-8")).get("KPlugin", {})
            except (OSError, ValueError):
                pass
            break
    if kp is None:
        for d in plugin_dirs():
            p = os.path.join(d, plugin + ".so")
            if os.path.exists(p):
                kp = qtplugin.metadata(p).get("KPlugin", {})
                break
    if not kp:
        return None
    return kp.get("Name", plugin), kp.get("Description", ""), kp.get("Icon", "")


class NotificationAreaIcons(AppletDialog):
    ID = "notifyicons"
    TITLE = "Notification Area Icons"
    ICON = "preferences-desktop-notification"
    ADVANCED = None
    TABBED = False
    SIZE = "dialog_wide"

    @classmethod
    def available(cls):
        return tray_groups(shell_file()) is not None

    def build(self):
        self.resize(620, 600)
        _, v = self.new_page(self.page)
        self.heading(v, "Select which icons appear in the notification area",
                     "Hidden icons stay one click away, behind the arrow next to the clock.")
        self.hide_inactive = QCheckBox("Hide inactive icons")
        self.hide_inactive.toggled.connect(self.changed)
        self.hide_inactive.toggled.connect(lambda on: self.tree.setEnabled(on))
        v.addWidget(self.hide_inactive)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Icons", "Behaviors"])
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(0)
        self.tree.setIconSize(QSize(ICON["small"], ICON["small"]))
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hd = self.tree.header()
        hd.setStretchLastSection(False)
        hd.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hd.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hd.resizeSection(1, 190)
        v.addWidget(self.tree, 1)

        box = self.group(v, "System icons")
        row = hbox(spacing="section")
        self.system = {}
        for key, label, _plugin in SYSTEM:
            cb = QCheckBox(label)
            cb.toggled.connect(self.changed)
            row.addWidget(cb)
            self.system[key] = cb
        row.addStretch(1)
        box.addLayout(row)

        bottom = hbox(spacing="related")
        restore = QPushButton("Restore Defaults")
        restore.clicked.connect(self._defaults)
        bottom.addWidget(restore)
        bottom.addStretch(1)
        v.addLayout(bottom)
        self.combos = {}

    def _header(self, text):
        it = QTreeWidgetItem([text])
        it.setFirstColumnSpanned(True)
        f = it.font(0)
        f.setBold(True)
        it.setFont(0, f)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.tree.addTopLevelItem(it)
        it.setFirstColumnSpanned(True)

    def _row(self, item_id, name, desc, icon, behavior):
        it = QTreeWidgetItem([name])
        it.setIcon(0, icon)
        if desc:
            it.setToolTip(0, desc)
        it.setSizeHint(0, QSize(0, ICON["small"] + 2 * SPACE["link_gap"] + SPACE["related"]))
        self.tree.addTopLevelItem(it)
        cb = QComboBox()
        for val, label in BEHAVIORS:
            cb.addItem(label, val)
        cb.setCurrentIndex(cb.findData(behavior))
        cb.currentIndexChanged.connect(self.changed)
        self.tree.setItemWidget(it, 1, cb)
        self.combos[item_id] = cb

    def _behavior(self, item_id):
        if item_id in self._v["shownItems"]:
            return SHOW
        if item_id in self._v["hiddenItems"]:
            return HIDE
        return AUTO

    def _defaults(self):
        for cb in self.combos.values():
            cb.setCurrentIndex(cb.findData(AUTO))
        for cb in self.system.values():
            cb.setChecked(True)
        self.hide_inactive.setChecked(True)

    # --- state ------------------------------------------------------------------------------
    def load(self):
        self.groups = tray_groups(shell_file())
        live = live_read()
        self.live = live is not None
        if live is None:
            live = {k: kread(shell_file(), self.groups, k, "") for k in KEYS}
        self._v = {"shownItems": as_list(live.get("shownItems")), "hiddenItems": as_list(live.get("hiddenItems")),
                   "showAllItems": as_bool(live.get("showAllItems"), False),
                   "extraItems": as_list(live.get("extraItems"))}
        for key, _l, _p in SYSTEM:
            self._v[key] = as_bool(live.get(key), True)

        self.tree.clear()
        self.combos = {}
        programs = status_notifiers()
        if programs:
            self._header("Programs")
            for item_id, name, desc, icon in programs:
                self._row(item_id, name, desc, icon, self._behavior(item_id))
        builtin = []
        for plugin in self._v["extraItems"]:
            if plugin in NOT_LISTED:
                continue
            info = plasmoid_info(plugin)
            if info:
                name, desc, icon = info
                builtin.append((plugin, name, desc, QIcon.fromTheme(icon or "plasma")))
        if builtin:
            self._header(distro.NAME)
            for item_id, name, desc, icon in sorted(builtin, key=lambda b: b[1].lower()):
                self._row(item_id, name, desc, icon, self._behavior(item_id))
        self.hide_inactive.setChecked(not self._v["showAllItems"])
        self.tree.setEnabled(not self._v["showAllItems"])
        for key, _l, _p in SYSTEM:
            self.system[key].setChecked(self._v[key])

    def _wanted(self):
        shown = [i for i in self._v["shownItems"] if i not in self.combos]   # keep past items
        hidden = [i for i in self._v["hiddenItems"] if i not in self.combos]
        for item_id, cb in self.combos.items():
            if cb.currentData() == SHOW:
                shown.append(item_id)
            elif cb.currentData() == HIDE:
                hidden.append(item_id)
        w = {"shownItems": shown, "hiddenItems": hidden, "showAllItems": not self.hide_inactive.isChecked()}
        for key, cb in self.system.items():
            w[key] = cb.isChecked()
        return w

    def apply_changes(self):
        want = self._wanted()
        changed = {k: v for k, v in want.items() if v != self._v.get(k)}
        if not changed:
            return []
        if live_read() is not None:
            # values are JSON literals (item ids come from other programs: never paste them raw)
            body = " ".join(f"w.writeConfig('{k}', {json.dumps(v)});" for k, v in changed.items())
            return [shell_call(_script_for(body + " w.reloadConfig(); r='ok';"))]
        return [kwrite_cmd(shell_file(), self.groups, k, ",".join(v) if isinstance(v, list) else v)
                for k, v in changed.items()]

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
