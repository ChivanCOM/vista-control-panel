# Vista Control Panel — design and developer guide

A Windows Vista style Control Panel: Windows interface, KDE / system backends.

```
controlpanel.py   window: Category View, category pages, Classic View, search, System page
catalog.py        what's in it: categories, applets, task links, actions (+ merge_extensions)
style.py          design schema: colors, spacing, margins, type roles, icon and window sizes
ui.py             shared Vista widgets (Link, labels, layouts) and helpers (run, Jobs, kread/kwrite)
applets/          native settings dialogs, discovered automatically
  base.py         AppletDialog: tabs or single page, OK/Cancel/Apply, "Advanced settings" link
helpers/          small root helpers run through pkexec (e.g. set-computer-name)
extensions/       optional add-ons shipped with the Control Panel or a distro (see below)
```

Run: `vista-control-panel [page]` or `vista-control-panel --applet <id>[#tab]`
(from a checkout: `python3 src/controlpanel.py ...`).

## Design schema (`style.py`)

Every screen takes its look from `style.py`; **no colors, point sizes, margins or
spacings in code**. Based on the Windows Vista UX guidelines, on a 4 px grid.

| | tokens |
|---|---|
| Type roles (ratios of the system font, so a larger font scales everything) | `body` · `strong` · `value` · `secondary` · `caption` · `section` · `instruction` (12 pt, Vista blue: page/dialog heading) · `subinstruction` · `emphasis` · `link` · `link_title` (11 pt green: applet/category names) · `pane_link` · `pane_current` · `pane_heading` · `error` |
| Spacing | `link_gap` 4 · `related` 8 · `unrelated` 12 · `section` 16 · `icon_gap` 12 · `grid_h` 16 · `grid_v` 8 |
| Margins | `dialog` 12 · `dialog_page` 12 (tab content) · `cp_page` 24 · `taskpane` |
| Icons | `small` 16 · `toolbar` 24 · `medium` 32 · `large` 48 · `hero` 128 |
| Windows | `dialog` 460×500 (property sheet) · `dialog_wide` 620×540 |

Use the helpers instead of building layouts by hand:

```python
page, v = self.new_page()                      # tab/page with schema margins + spacing
self.heading(v, "Select a power plan", "Explanation…")   # main instruction (+ secondary text)
section(v, "Change settings for the plan")     # section heading + rule, schema space before it
g = form_grid(label_column=True)               # label/value grid
v.addWidget(text_label("…", "secondary"))      # text in a role
Link("Change settings", "link")                # links: "link", "link_title", "pane_link"
gap(v)                                         # space between unrelated blocks ("related", "section")
```

**Never greet the user with an empty window.** Every screen opens showing the current
state: the current wallpaper selected and scrolled into view, the current pointer scheme
previewed, the current values in every control. Slow content (thumbnails, previews)
fills in progressively; it never blocks the window from appearing.

Task-style windows (task pane + white page + Close) derive from `TaskWindow` and call
`self.task_frame()`; `pane_heading()` / `pane_link()` / `launch()` fill the pane.

Conventions: icons top-aligned with their title; groups use `self.group(layout, title,
icon)` (illustration left, content right); option descriptions indented to the
option's label (`self.option_indent()`); dialog buttons in Windows order OK · Cancel ·
Apply; single-page dialogs align content with the dialog edge.

## Actions

Catalog entries point at actions; anything not available on the machine is hidden.

| action | opens |
|---|---|
| `native:<id>[#tab]` | a native applet dialog (`applets/`), optionally on a tab |
| `kcm:<name>` | one KDE settings module in its own window (`kcmshell6`; `_x11` variant on X11) |
| `settings:<name>` | full System Settings at that module |
| `app:<command>` | a program |
| `page:<id>` | a Control Panel page (category id, `sysinfo`, `admintools`, `classic`, …) |
| `a\|b\|c` | the first available of a, b, c — e.g. `native:power\|kcm:kcm_powerdevilprofilesconfig` |

Always give native applets a KDE fallback, so the link still works where the native
dialog isn't available (e.g. Window Color needs the Aero glass effect).

## Adding a native settings screen

1. Create `applets/<name>.py` with a subclass of `applets.base.AppletDialog`:

   ```python
   from applets.base import AppletDialog
   from ui import kread, kwrite_cmd

   class Keyboard(AppletDialog):
       ID = "keyboard"                 # used as native:keyboard
       TITLE = "Keyboard Properties"
       ICON = "preferences-desktop-keyboard"
       ADVANCED = "kcm:kcm_keyboard"   # "Advanced settings…" link

       def build(self):                # create widgets; self.add_tab(widget, "Speed", "speed")
           ...                         # connect edits to self.changed (enables Apply)
       def load(self):                 # read current values (kread / run)
           ...
       def apply_changes(self):        # -> list of commands; run in order, UI stays responsive
           return [kwrite_cmd("kcminputrc", "Keyboard", "RepeatRate", 25)]
   ```

   It is registered automatically (no list to edit). Optional: `available()` (classmethod)
   to hide it when its backend is missing, `after_apply()`, `revert()` for live previews.
2. Point catalog entries at it: `"native:keyboard|kcm:kcm_keyboard"`.

Rules of thumb:
- Write the **same keys KDE writes** (check the KDE source, e.g. plasma-workspace and plasma-desktop's `kcms/`), and
  notify the service that owns them (D-Bus `reparseConfiguration`, `reconfigureEffect`, …).
- Anything needing root goes through a command that asks polkit (`timedatectl`,
  `hostnamectl`, `pkexec helpers/…`), so the UAC prompt appears. Never run as root.
- Cancel must leave the system as it was.

## Extensions

Modules in `extensions/`, `/etc/vista-control-panel/extensions/` or
`~/.local/share/vista-control-panel/extensions/` can add applets *and* catalog entries
without touching the core:

```python
# extensions/wine.py
from catalog import Applet, Category, Task
from applets.base import AppletDialog

class WinePrograms(AppletDialog):
    ID = "wineprograms"
    ...

CATEGORIES = [Category("windowsapps", "Windows Programs", "wine", [Task("Run a Windows program", "native:wineprograms")])]
APPLETS = [Applet("wineprograms", "Windows Programs", "wine", "native:wineprograms|app:winecfg", "windowsapps", "…")]
```

New categories appear before "Additional Options"; an applet with an existing id replaces
the built-in one. A broken extension is skipped (see `applets.ERRORS`), never fatal.

## Native applets so far

| id | Windows applet | backend |
|---|---|---|
| `windowcolor` | Window Color and Appearance | kwinrc `[Effect-aeroglassblur]`, KWin reconfigureEffect (live preview) |
| `power` | Power Options | power-profiles-daemon + powerdevilrc, PowerDevil reparseConfiguration |
| `datetime` | Date and Time | timedatectl (systemd-timedated, polkit) |
| `sound` | Sound | pactl (PipeWire), kdeglobals `[Sounds] Theme` |
| `sysprops` | System Properties | hostnamectl + `helpers/set-computer-name` (pkexec, keeps /etc/hosts in sync) |
| `mouse` | Mouse Properties | kcminputrc `[Mouse] XLbInpt*` + `kcminit kcm_mouse` (X11), kdeglobals double-click/wheel (notify), plasma-apply-cursortheme; pointer previews via `xcursor.py` |
| `background` | Desktop Background | plasma-apply-wallpaperimage (fill modes), kscreenlockerrc greeter image; current picture read from the shell's appletsrc |
| `screensaver` | Screen Saver Settings | kscreenlockerrc `[Daemon]` Autolock/Timeout/LockOnResume/LockGrace, `org.kde.screensaver.configure` |
| `useraccounts` | User Accounts | AccountsService via busctl (interactive auth): SetRealName, SetIconFile (256 px PNG), SetAccountType, SetPassword (`openssl passwd -6` on stdin + hint), CreateUser, DeleteUser; keeps the last administrator |
| `programs` | Programs and Features | programs = packages with menu entries (`dpkg -S` mapping, dpkg-query details, Flatpak apps); uninstall via PackageKit (`packagekit.py`, D-Bus): SIMULATE first, refuse metapackages/core, then remove with UAC prompt |
| `network` | Network and Sharing Center | nmcli (terse output parsed with escapes): map, active networks, Sharing and Discovery (avahi, smbd, cups), Network Connections, Status window with live counters (/sys/class/net), Details, diagnostics |
| `keyboard` | Keyboard Properties | kcminputrc `[Keyboard]` repeat/NumLock (+ `xset r rate` on X11), kxkbrc `[Layout]` layouts with notification (keyboard daemon re-applies); names from xkb base.lst |
| `region` | Regional and Language Options | plasma-localerc: formats as all `LC_*` format keys (system locale may override unset ones), display language as `LANG` + `LANGUAGE`; live examples via QLocale; language packs via check-language-support + PackageKit; system locale via localed SetLocale |
| `defaults` | Default Programs | role -> MIME lists from KDE's componentchooser; mimeapps.list `[Default Applications]`/`[Added Associations]` written at its real path (keeps the session symlink); terminal in kdeglobals |
| `folderoptions` | Folder Options | kdeglobals SingleClick; dolphinrc `[General]` (full path, tooltips, status bar, check boxes, archives as folders); global view properties `.directory` (hidden files, thumbnails) |
| `autoplay` | AutoPlay | per kind of content (pictures, videos, music, mixed, drive, DVD): a program, open folder, no action or ask; `vista-control-panel/autoplayrc`; "Use AutoPlay" also switches KDE's device automounter. The AutoPlay window itself is `autoplay_agent.py` (session autostart `vista-autoplay`, opt-in outside BOONE: see the README): watches mountinfo, removable/hot-plug devices only, asks once per insert |
| `notifyicons` | Notification Area Icons | the Vista tray's own settings (shownItems/hiddenItems = Show/Hide, neither = Hide when inactive; showAllItems; sound/network/batteryEnabled = System icons). Live through `org.kde.PlasmaShell.evaluateScript` (writeConfig on the tray's config scheme, which it reloads at once), else the appletsrc file. Program icons from the StatusNotifierWatcher (name: launcher, tooltip title, Id), built-in icons from their plugin metadata (`qtplugin.py` reads it from the .so) |
| `display` | Display Settings | kscreen-doctor (one config per Apply, 15 s keep/revert); X11 text size: kdeglobals `[KScreen]`, kcmfonts, Xft.dpi + log off |

## "Open settings" from KDE

KDE opens settings with `systemsettings <module>` (tray popups, widgets). The optional
router (`router/systemsettings`, installed in `<prefix>/lib/vista-control-panel/router/`) can be
put first on PATH in a session; it routes module requests to
`vista-control-panel --kcm <module>`: an applet whose `REPLACES` lists the module opens;
other modules open in their own window (kcmshell6). Plain `systemsettings` still opens
System Settings.
