# SPDX-License-Identifier: GPL-3.0-or-later
"""AutoPlay: shared settings, content detection and actions (used by the Control Panel's
AutoPlay page and by autoplay_agent.py).

Settings: vista-control-panel/autoplayrc in the config home (denairu/autoplayrc on BOONE
installs that have it) - [General] Enabled, [Handlers] <kind>=
"ask" | "open" | "none" | <desktop file id>. Mounting itself is done by KDE's device
automounter (kded_device_automounterrc [General], plasma-desktop solid-device-automounter;
it re-reads its settings for every device that is plugged in).

Only drives that mount take part (USB sticks, memory cards, external disks, DVDs); audio
CDs never mount and are left to the device notifier."""
import os
import shlex

import distro
from ui import kread, kwrite_cmd, run


def _settings_file():
    """Settings file, relative to the config home. Installs that already have the older
    BOONE file keep using it, so nobody's choices are lost."""
    new, old = f"{distro.APP_ID}/autoplayrc", f"{distro.LEGACY_ID}/autoplayrc"
    home = distro.config_home()
    if not os.path.exists(os.path.join(home, new)) and os.path.exists(os.path.join(home, old)):
        return old
    return new


RC = _settings_file()
# kind, Windows label, MIME type the programs must open, freedesktop categories, icon
TYPES = [
    ("pictures", "Pictures", "image/jpeg", {"Graphics", "Photography"}, "image-x-generic"),
    ("videos", "Videos", "video/mp4", {"Video", "AudioVideo"}, "video-x-generic"),
    ("music", "Music", "audio/mpeg", {"Audio", "AudioVideo"}, "audio-x-generic"),
    ("mixed", "Mixed content", None, set(), "folder"),
    ("files", "Removable drive", None, set(), "drive-removable-media"),
    ("dvd", "DVD movie", "video/mpeg", {"Video", "AudioVideo"}, "media-optical-dvd-video"),
]
LABEL = {k: label for k, label, *_ in TYPES}
ICON = {k: icon for k, *_, icon in TYPES}
VERBS = {"pictures": "View pictures", "videos": "Play videos", "music": "Play music",
         "dvd": "Play DVD movie"}

PICTURES = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".tif", ".tiff",
            ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"}
VIDEOS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg", ".3gp", ".mts",
          ".m2ts", ".vob"}
MUSIC = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav", ".wma", ".aiff", ".aif"}
EXT = {"pictures": PICTURES, "videos": VIDEOS, "music": MUSIC}
SKIP_DIRS = {"System Volume Information", "$RECYCLE.BIN", "lost+found"}

AUTOMOUNT = ("kded_device_automounterrc", "General")
AUTOMOUNT_KEYS = ("AutomountEnabled", "AutomountOnPlugin", "AutomountUnknownDevices")


# --- settings ------------------------------------------------------------------------------
def enabled():
    return kread(RC, "General", "Enabled", "true") == "true"


def chosen():
    """True when the user has decided either way (the Control Panel wrote [General] Enabled)."""
    return kread(RC, "General", "Enabled", "") in ("true", "false")


def handler(kind):
    """The saved choice for a kind of content: "ask", "open", "none" or a desktop file id."""
    return kread(RC, "Handlers", kind, "ask") or "ask"


def set_handler_cmd(kind, value):
    return kwrite_cmd(RC, "Handlers", kind, value)


def automount_on():
    """Is KDE's automounter set to mount drives by itself (all three keys on)?"""
    return all(kread(*AUTOMOUNT, k, "false") == "true" for k in AUTOMOUNT_KEYS)


def automount_cmds(on):
    return [kwrite_cmd(*AUTOMOUNT, k, on) for k in AUTOMOUNT_KEYS]


# --- what is on the drive -----------------------------------------------------------------
def classify(mountpoint, max_files=3000, max_depth=4):
    """-> (kind, {kind: [media files]}). kind: dvd, pictures, videos, music, mixed or files."""
    if any(os.path.isdir(os.path.join(mountpoint, d)) for d in ("VIDEO_TS", "video_ts")):
        return "dvd", {}
    found = {k: [] for k in EXT}
    seen = 0
    for root, dirs, files in os.walk(mountpoint):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        if root[len(mountpoint):].count(os.sep) >= max_depth:
            dirs[:] = []
        for f in sorted(files):
            if f.startswith("."):
                continue
            seen += 1
            ext = os.path.splitext(f)[1].lower()
            for k, exts in EXT.items():
                if ext in exts:
                    found[k].append(os.path.join(root, f))
            if seen >= max_files:
                break
        if seen >= max_files:
            break
    counts = {k: len(v) for k, v in found.items() if v}
    if not counts:
        return "files", found
    top = max(counts, key=counts.get)
    # mostly one kind of media, and media is a real part of the drive
    if counts[top] >= 0.8 * sum(counts.values()) and counts[top] >= 0.25 * seen:
        return top, found
    return "mixed", found


# --- programs -------------------------------------------------------------------------------
def apps_for(kind, limit=5):
    """[(desktop id, name, icon)] for a kind: the default program first, then other
    programs of the right sort (e.g. Graphics for pictures) that open that type."""
    from applets.defaults import desktop_apps
    entry = next((t for t in TYPES if t[0] == kind), None)
    if not entry or not entry[2]:
        return []
    _k, _l, mime, cats, _i = entry
    apps = desktop_apps()
    ok, out, _ = run(["xdg-mime", "query", "default", mime])
    default = out.strip() if ok else ""
    res, names = [], set()

    def add(sid, a):
        if a["name"] not in names:
            names.add(a["name"])
            res.append((sid, a["name"], a["icon"]))

    if default in apps:
        add(default, apps[default])
    for sid, a in sorted(apps.items(), key=lambda kv: kv[1]["name"].lower()):
        if mime in a["mimes"] and cats & set(a["categories"]) and not a.get("hidden"):
            add(sid, a)
    return res[:limit]


def desktop_path(sid):
    """Desktop file id -> its file (also "kde4-foo.desktop" -> kde4/foo.desktop), or None."""
    from applets.defaults import application_dirs
    for d in application_dirs():
        p = os.path.join(d, sid)
        if os.path.exists(p):
            return p
        p = os.path.join(d, *sid.split("-", 1)) if "-" in sid else None
        if p and os.path.exists(p):
            return p
    return None


def takes_many(path):
    """Does the program's Exec line accept several files (%F / %U)?"""
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            if line.startswith("Exec="):
                return any(t in ("%F", "%U") for t in shlex.split(line[5:].strip()))
    except (OSError, ValueError):
        pass
    return False


def run_action(action, mountpoint, kind=None, files=None):
    """Carry out an AutoPlay choice for a mounted drive."""
    from PyQt6.QtCore import QProcess
    if action in ("none", "ask", "", None):
        return True
    if action == "open":
        return QProcess.startDetached("dolphin", ["--new-window", mountpoint])
    path = desktop_path(action)
    if not path:
        return QProcess.startDetached("dolphin", ["--new-window", mountpoint])
    targets = [mountpoint]
    # players get the media files themselves (a folder means nothing to most of them);
    # picture viewers browse the folder
    if kind in ("music", "videos") and files and takes_many(path):
        targets = files[kind][:1000]
    return QProcess.startDetached("gio", ["launch", path] + targets)
