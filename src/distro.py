# SPDX-License-Identifier: GPL-3.0-or-later
"""Who the Control Panel runs on: the system's name and logo, its own command, and where
settings and extensions live.

Everything distro-specific goes through this module, so the same code says "Kubuntu
Update" on Kubuntu and "BOONE Update" on BOONE. The name and logo come from
/etc/os-release (NAME, LOGO); VCP_OS_NAME overrides the name.

Paths: the generic vista-control-panel locations come first; the "denairu" ones are kept
as fallbacks for BOONE (the distro this project started in)."""
import os
import shutil

APP_ID = "vista-control-panel"          # command, desktop file, config folder name
LEGACY_ID = "denairu"                   # BOONE's earlier names (read as fallbacks)


def os_release():
    """/etc/os-release as a dict (empty if missing)."""
    out = {}
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    k, sep, v = line.strip().partition("=")
                    if sep:
                        out[k] = v.strip().strip('"')
            break
        except OSError:
            continue
    return out


_OSR = os_release()

# The name shown in texts like "<NAME> Update" or "<NAME> needs it".
NAME = os.environ.get("VCP_OS_NAME") or _OSR.get("NAME") or "Linux"


def logo_icon():
    """Icon name of the system's logo (os-release LOGO, else the common fallbacks)."""
    return _OSR.get("LOGO") or "distributor-logo"


def command():
    """argv that starts the Control Panel (used for links back into it, e.g. from AutoPlay
    or a desktop icon): the installed command if there is one, else this checkout."""
    for cmd in (APP_ID, f"{LEGACY_ID}-control-panel"):
        if shutil.which(cmd):
            return [cmd]
    return ["python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "controlpanel.py")]


def config_home():
    """$XDG_CONFIG_HOME, else ~/.config."""
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def data_home():
    """$XDG_DATA_HOME, else ~/.local/share."""
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


def extension_dirs(here):
    """Extension folders, lowest priority first (later ones override applets with the same ID)."""
    dirs = [os.path.join(here, "extensions")]
    for base in (f"/etc/{LEGACY_ID}/control-panel", f"/etc/{APP_ID}"):
        dirs.append(os.path.join(base, "extensions"))
    dirs.append(os.path.join(data_home(), LEGACY_ID, "control-panel", "extensions"))
    dirs.append(os.path.join(data_home(), APP_ID, "extensions"))
    return dirs
