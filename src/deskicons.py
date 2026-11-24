# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows Vista's desktop icons (Computer, the user's files, Network, Recycle Bin, Control Panel)
as link files in the desktop folder.

Each icon is a .desktop file marked with X-VistaCP-DesktopIcon=<id> (X-BOONE-DesktopIcon on
icons made by earlier BOONE versions is recognised too); only marked files are ever changed
or removed, never the user's own files. No Qt here: the session start script and the
Control Panel's Desktop Icon Settings both use it (python3 deskicons.py --seed)."""
import os
import pwd
import subprocess
import sys
import shlex

import distro

MARK = "X-VistaCP-DesktopIcon"
LEGACY_MARKS = ("X-BOONE-DesktopIcon",)
SEED_MARK = "vista-desktop-icons-seeded"
LEGACY_SEED_MARKS = ("boone-desktop-icons-seeded",)


def user_name():
    """The name Vista shows on the user's folder: the full name, else the login."""
    pw = pwd.getpwuid(os.getuid())
    full = pw.pw_gecos.split(",")[0].strip()
    return full or pw.pw_name


# id, label in the settings, default icon (and the empty Recycle Bin's), entry (Comment: Vista's
# infotip, shown when pointing at the icon)
ICONS = [
    ("computer", "Computer", "computer", None,
     {"Type": "Link", "URL": "file:///",
      "Comment": "Shows the disk drives and hardware connected to this computer."}),
    ("user", "User's Files", "user-home", None,
     {"Type": "Link", "URL": "file://" + os.path.expanduser("~"),
      "Comment": "Contains your documents, pictures, music and other personal files."}),
    ("network", "Network", "folder-network", None,
     {"Type": "Link", "URL": "remote:/",
      "Comment": "Accesses computers and devices that are on your network."}),
    ("recyclebin", "Recycle Bin", "user-trash-full", "user-trash",
     {"Type": "Link", "URL": "trash:/",
      "Comment": "Contains files and folders that you have deleted."}),
    ("controlpanel", "Control Panel", "preferences-system", None,
     {"Type": "Application", "Exec": shlex.join(distro.command()),
      "Comment": "Change settings and customize the functionality of this computer."}),
]
BY_ID = {i[0]: i for i in ICONS}
DEFAULT_ON = {"recyclebin"}     # Vista's desktop after setup: just the Recycle Bin


def desktop_dir():
    """The user's desktop folder (xdg-user-dir; ~/Desktop if unset or set to home)."""
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out and out != os.path.expanduser("~"):
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.expanduser("~/Desktop")


def display_name(icon_id):
    return user_name() if icon_id == "user" else BY_ID[icon_id][1]


def _read(path):
    """Keys of a .desktop file (all groups, flat); {} if unreadable."""
    entry = {}
    try:
        # errors="replace": a user's own non-UTF-8 .desktop file must not break the scan
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "=" in line and not line.startswith("["):
                    k, v = line.rstrip("\n").split("=", 1)
                    entry[k] = v
    except OSError:
        pass
    return entry


def managed():
    """{id: (path, entry)} for the marked icons on the desktop."""
    d, found = desktop_dir(), {}
    try:
        names = os.listdir(d)
    except OSError:
        return found
    for n in names:
        if n.endswith(".desktop"):
            p = os.path.join(d, n)
            e = _read(p)
            icon_id = next((e[k] for k in (MARK,) + LEGACY_MARKS if e.get(k) in BY_ID), None)
            if icon_id:
                found[icon_id] = (p, e)
    return found


def state():
    """{id: (shown, icon, empty_icon)} - the current settings."""
    m = managed()
    out = {}
    for icon_id, _, icon, empty, _ in ICONS:
        if icon_id in m:
            e = m[icon_id][1]
            out[icon_id] = (True, e.get("Icon", icon), e.get("EmptyIcon", empty))
        else:
            out[icon_id] = (False, icon, empty)
    return out


def write(icon_id, icon=None, empty_icon=None):
    """Create or update the icon's link file (atomically), reusing an existing marked file."""
    _, _, default_icon, default_empty, entry = BY_ID[icon_id]
    d = desktop_dir()
    os.makedirs(d, exist_ok=True)
    path = managed().get(icon_id, (os.path.join(d, f"vcp-{icon_id}.desktop"),))[0]
    lines = ["[Desktop Entry]", f"Name={display_name(icon_id)}", f"Icon={icon or default_icon}"]
    if default_empty:
        lines.append(f"EmptyIcon={empty_icon or default_empty}")
    lines += [f"{k}={v}" for k, v in entry.items()]
    lines.append(f"{MARK}={icon_id}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o755)       # Plasma only opens executable (trusted) desktop links
    os.replace(tmp, path)


def remove(icon_id):
    m = managed()
    if icon_id in m:
        os.remove(m[icon_id][0])


def seed(marker_dir):
    """First login of the session: Vista's default desktop (the Recycle Bin), once."""
    marker = os.path.join(marker_dir, SEED_MARK)
    if any(os.path.exists(os.path.join(marker_dir, m)) for m in LEGACY_SEED_MARKS):
        return
    if os.path.exists(marker):
        return
    if not managed():
        for icon_id in DEFAULT_ON:
            write(icon_id)
    os.makedirs(marker_dir, exist_ok=True)
    open(marker, "w").close()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--seed":
        seed(sys.argv[2])
    else:
        sys.exit("usage: deskicons.py --seed <config dir>")
