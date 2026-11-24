# SPDX-License-Identifier: GPL-3.0-or-later
"""Default Programs (Windows style): one row per kind of program.

Writes the same thing KDE's default applications module does
(plasma-workspace kcms/componentchooser, Plasma/6.6): for each of the role's MIME types
the program supports, mimeapps.list [Default Applications] (and first in [Added
Associations]); the terminal goes to kdeglobals [General] TerminalApplication/
TerminalService. mimeapps.list is updated at its real path, so a symlinked file (a
desktop with its own config home may share it with another session) stays a symlink."""
import configparser
import glob
import os
import stat
import tempfile

from PyQt6.QtCore import QProcess, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QComboBox, QLabel, QMessageBox

from applets.base import AppletDialog
from style import ICON
from ui import Link, form_grid, gap, icon_label, kread, kwrite_cmd, run, text_label
import distro

# Generated from plasma-workspace kcms/componentchooser (Plasma/6.6) component lists;
# browser adds text/html and XHTML (Windows' default browser opens .html files);
# maps and phone calls are left to 'Associate a file type or protocol'.
ROLES = [
    ('browser', 'Web browser', 'gnome-globe', [
        'x-scheme-handler/http', 'x-scheme-handler/https', 'text/html',
        'application/xhtml+xml',
    ]),
    ('email', 'E-mail', 'internet-mail', [
        'x-scheme-handler/mailto',
    ]),
    ('musicplayer', 'Music player', 'audio-x-generic', [
        'audio/mpeg', 'audio/aac', 'audio/mp4',
        'audio/mpegurl', 'audio/ogg', 'audio/vnd.rn-realaudio',
        'audio/vorbis', 'audio/x-flac', 'audio/x-mp3',
        'audio/x-mpegurl', 'audio/x-ms-wma', 'audio/x-musepack',
        'audio/x-oggflac', 'audio/x-pn-realaudio', 'audio/x-scpls',
        'audio/x-speex', 'audio/x-vorbis', 'audio/x-vorbis+ogg',
        'audio/x-wav',
    ]),
    ('videoplayer', 'Video player', 'video-x-generic', [
        'video/mp4', 'video/3gp', 'video/3gpp',
        'video/3gpp2', 'video/avi', 'video/divx',
        'video/dv', 'video/fli', 'video/flv',
        'video/mp2t', 'video/mp4v-es', 'video/mpeg',
        'video/msvideo', 'video/ogg', 'video/quicktime',
        'video/vnd.divx', 'video/vnd.mpegurl', 'video/vnd.rn-realvideo',
        'video/webm', 'video/x-avi', 'video/x-flv',
        'video/x-m4v', 'video/x-matroska', 'video/x-mpeg2',
        'video/x-ms-asf', 'video/x-msvideo', 'video/x-ms-wmv',
        'video/x-ms-wmx', 'video/x-ogm', 'video/x-ogm+ogg',
        'video/x-theora', 'video/x-theora+ogg', 'application/x-matroska',
    ]),
    ('imageviewer', 'Photo viewer', 'image-x-generic', [
        'image/png', 'image/jpeg', 'image/webp',
        'image/avif', 'image/heif', 'image/bmp',
        'image/x-icns',
    ]),
    ('pdfviewer', 'PDF viewer', 'application-pdf', [
        'application/pdf',
    ]),
    ('texteditor', 'Text editor', 'accessories-text-editor', [
        'text/plain', 'text/x-cmake', 'text/markdown',
        'application/x-docbook+xml', 'application/json', 'application/x-yaml',
    ]),
    ('filemanager', 'File manager', 'system-file-manager', [
        'inode/directory',
    ]),
    ('archivemanager', 'Archive manager', 'package-x-generic', [
        'application/zip', 'application/x-tar', 'application/x-compressed-tar',
        'application/x-bzip-compressed-tar', 'application/x-tarz', 'application/x-xz-compressed-tar',
        'application/x-lzma-compressed-tar', 'application/x-lzip-compressed-tar', 'application/x-tzo',
        'application/x-lrzip-compressed-tar', 'application/x-lz4-compressed-tar', 'application/x-zstd-compressed-tar',
        'application/x-cd-image', 'application/x-bcpio', 'application/x-cpio',
        'application/x-cpio-compressed', 'application/x-sv4cpio', 'application/x-sv4crc',
        'application/x-source-rpm', 'application/vnd.ms-cab-compressed', 'application/x-xar',
        'application/x-iso9660-appimage', 'application/x-archive', 'application/vnd.rar',
        'application/x-rar', 'application/x-7z-compressed', 'application/x-compress',
        'application/gzip', 'application/x-bzip', 'application/x-lzma',
        'application/x-xz', 'application/zstd', 'application/x-lha',
    ]),
]


def config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def application_dirs():
    """The applications folders in XDG data dirs, user's first (XDG lookup order)."""
    data = [os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))] + \
        os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    return [os.path.join(d, "applications") for d in data if os.path.isdir(os.path.join(d, "applications"))]


def desktop_apps():
    """storage id -> {name, icon, mimes, categories, exec}; first directory wins (XDG order)."""
    apps = {}
    for base in application_dirs():
        for path in glob.glob(os.path.join(base, "**", "*.desktop"), recursive=True):
            sid = os.path.relpath(path, base).replace("/", "-")
            if sid in apps:
                continue
            d, main = {}, False
            try:
                for line in open(path, encoding="utf-8", errors="replace"):
                    line = line.strip()
                    if line.startswith("["):
                        main = line == "[Desktop Entry]"
                    elif main and "=" in line:
                        k, _, v = line.partition("=")
                        d.setdefault(k, v)
            except OSError:
                continue
            if d.get("Type") != "Application" or d.get("Hidden") == "true":
                apps[sid] = None          # still shadows the same id in later directories
                continue
            # NoDisplay handlers count: e.g. Okular registers PDF via a hidden okularApplication_pdf
            apps[sid] = {"name": d.get("Name", sid), "icon": d.get("Icon", ""), "exec": d.get("Exec", ""),
                         "mimes": [m for m in d.get("MimeType", "").split(";") if m],
                         "categories": [c for c in d.get("Categories", "").split(";") if c],
                         "hidden": d.get("NoDisplay") == "true"}
    return {k: v for k, v in apps.items() if v}


def read_mimeapps(strict=False):
    """-> (parser, real path of mimeapps.list). A damaged file is read as far as it parses;
    strict=True raises instead (before rewriting it, so nothing the parser skipped is lost)."""
    cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    cp.optionxform = str        # MIME types and desktop ids are case-sensitive
    path = os.path.realpath(os.path.join(config_home(), "mimeapps.list"))
    if os.path.exists(path):
        try:
            cp.read(path, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError):
            if strict:
                raise
    return cp, path


def current_default(mime, cp):
    """The user's default for a MIME type: mimeapps.list, else what xdg-mime resolves."""
    if cp.has_option("Default Applications", mime):
        return cp.get("Default Applications", mime).split(";")[0]
    ok, out, _ = run(["xdg-mime", "query", "default", mime])
    return out.strip() if ok else ""


def write_defaults(assignments):
    """assignments: {mime: storage_id}. Atomic write to mimeapps.list's real path."""
    cp, path = read_mimeapps(strict=True)
    for sec in ("Default Applications", "Added Associations"):
        if not cp.has_section(sec):
            cp.add_section(sec)
    for mime, sid in assignments.items():
        cp.set("Default Applications", mime, sid + ";")
        added = [x for x in cp.get("Added Associations", mime, fallback="").split(";") if x and x != sid]
        cp.set("Added Associations", mime, ";".join([sid] + added) + ";")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".mimeapps-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            cp.write(f, space_around_delimiters=False)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp makes the file 0600; keep the existing file's permissions
        os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


class DefaultPrograms(AppletDialog):
    """One combo per role (browser, e-mail, ...), listing the programs that open its MIME types."""
    ID = "defaults"
    TITLE = "Default Programs"
    ICON = "preferences-desktop-default-applications"
    ADVANCED = "kcm:kcm_filetypes"
    REPLACES = ["kcm_componentchooser"]
    TABBED = False
    SIZE = "dialog_wide"

    def build(self):
        self.resize(620, 620)
        _, v = self.new_page(self.page)
        self.heading(v, f"Choose the programs that {distro.NAME} uses by default",
                     "These programs open web links, e-mail links, music, videos, pictures and documents.")
        self.grid = form_grid()
        v.addLayout(self.grid)
        gap(v, "section")
        assoc = Link("Associate a file type or protocol with a specific program", "link")
        assoc.clicked.connect(lambda: QProcess.startDetached("kcmshell6", ["kcm_filetypes"]))
        v.addWidget(assoc)
        v.addStretch(1)
        self.combos = {}

    def load(self):
        from ui import clear_layout
        clear_layout(self.grid)
        self.combos = {}            # reloaded after Apply: drop the deleted combos
        self.apps = desktop_apps()
        cp, _ = read_mimeapps()
        rows = [(key, label, icon, mimes) for key, label, icon, mimes in ROLES]
        # the terminal comes last (after the archive manager); it lives in kdeglobals, no MIME types
        rows.insert(9, ("terminal", "Terminal", "utilities-terminal", []))
        self._orig = {}
        for r, (key, label, icon, mimes) in enumerate(rows):
            if key == "terminal":
                cands = {sid: a for sid, a in self.apps.items() if "TerminalEmulator" in a["categories"]}
                cur = kread("kdeglobals", "General", "TerminalService", "") or "org.kde.konsole.desktop"
            else:
                primary = mimes[0]
                cands = {sid: a for sid, a in self.apps.items() if primary in a["mimes"]}
                cur = current_default(primary, cp)
            cands = self._unique_by_name(cands, cur)
            if not cands:
                continue
            self.grid.addWidget(icon_label(icon, "medium"), r, 0)
            self.grid.addWidget(QLabel(label), r, 1)
            cb = QComboBox()
            cb.setIconSize(QSize(ICON["small"], ICON["small"]))
            for sid, a in sorted(cands.items(), key=lambda kv: kv[1]["name"].lower()):
                ic = QIcon(a["icon"]) if os.path.isabs(a["icon"]) else QIcon.fromTheme(a["icon"])
                cb.addItem(ic, a["name"], sid)
            i = cb.findData(cur)
            if i < 0 and cur:
                cb.addItem(cur.removesuffix(".desktop"), cur)
                i = cb.count() - 1
            cb.setCurrentIndex(max(i, 0))
            cb.currentIndexChanged.connect(self.changed)
            self.grid.addWidget(cb, r, 2)
            self.combos[key] = (cb, mimes)
            self._orig[key] = cb.currentData()
        self.grid.setColumnStretch(2, 1)
        first = next(iter(self.combos.values()), None)
        if first:
            first[0].setFocus()

    @staticmethod
    def _unique_by_name(cands, current):
        """One entry per program name: prefer the current default, then a visible entry."""
        best = {}
        for sid, a in cands.items():
            prev = best.get(a["name"])
            rank = (sid != current, a.get("hidden", False))
            if prev is None or rank < prev[0]:
                best[a["name"]] = (rank, sid, a)
        return {sid: a for _, sid, a in best.values()}

    def apply_changes(self):
        assignments, cmds = {}, []
        for key, (cb, mimes) in self.combos.items():
            sid = cb.currentData()
            if sid == self._orig.get(key):
                continue
            if key == "terminal":
                exe = self.apps.get(sid, {}).get("exec", "").split(" %")[0]
                cmds += [kwrite_cmd("kdeglobals", "General", "TerminalApplication", exe, notify=True),
                         kwrite_cmd("kdeglobals", "General", "TerminalService", sid, notify=True)]
                continue
            supported = set(self.apps.get(sid, {}).get("mimes", []))
            for m in mimes:
                if m in supported:          # like KDE: only types the program can open
                    assignments[m] = sid
        if assignments:
            try:
                write_defaults(assignments)
            except (configparser.Error, UnicodeDecodeError):
                QMessageBox.warning(self, self.TITLE, "The default programs could not be changed: "
                                    f"{read_mimeapps()[1]} is damaged. Correct or remove it and try again.")
                return None
            cmds.append(["kbuildsycoca6"])        # refresh KDE's cache of applications/associations
        return cmds

    def after_apply(self):
        self._loading = True
        self.load()
        self._loading = False
