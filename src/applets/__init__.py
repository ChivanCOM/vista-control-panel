# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Control Panel applets (Windows-style dialogs on top of KDE/system backends).

Applets are discovered, not listed: every module in this package and in the extension
directories is imported, and every AppletDialog subclass with an ID is registered.
Catalog entries open them with "native:<ID>[#tab]" (see catalog.py and docs/DESIGN.md).

Extension directories (later ones override earlier ones with the same ID; see distro.py):
  <control-panel>/extensions/                     shipped with the Control Panel / a distro
  /etc/vista-control-panel/extensions/            machine-wide additions
  ~/.local/share/vista-control-panel/extensions/  per-user additions
  (BOONE's older /etc/denairu/... and ~/.local/share/denairu/... folders are read too)
An extension module may also define APPLETS / CATEGORIES lists (catalog entries) and
PAGES (dict), which the Control Panel merges into its catalog."""
import importlib
import importlib.util
import os
import pkgutil
import sys
import traceback

import distro
from applets.base import AppletDialog

HERE = os.path.dirname(os.path.abspath(__file__))
EXTENSION_DIRS = distro.extension_dirs(os.path.dirname(HERE))

REGISTRY = {}       # applet id -> AppletDialog subclass
EXTENSIONS = []     # loaded extension modules (for catalog merging)
ERRORS = []         # (module, traceback) - a broken module never breaks the Control Panel


def _register_from(module):
    for obj in vars(module).values():
        if isinstance(obj, type) and issubclass(obj, AppletDialog) and obj is not AppletDialog and obj.ID:
            REGISTRY[obj.ID] = obj


def _discover():
    for info in pkgutil.iter_modules([HERE]):
        if info.name == "base":
            continue
        try:
            _register_from(importlib.import_module(f"applets.{info.name}"))
        except Exception:
            ERRORS.append((info.name, traceback.format_exc()))
    for d in EXTENSION_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            name = f"vcp_ext_{os.path.splitext(fn)[0]}"
            try:
                spec = importlib.util.spec_from_file_location(name, os.path.join(d, fn))
                mod = importlib.util.module_from_spec(spec)
                sys.modules[name] = mod
                spec.loader.exec_module(mod)
                _register_from(mod)
                EXTENSIONS.append(mod)
            except Exception:
                ERRORS.append((fn, traceback.format_exc()))


_discover()
_available = {}


def available(applet_id):
    """Can this applet open here (its available() check, cached; False if it raises)?"""
    if applet_id not in _available:
        cls = REGISTRY.get(applet_id)
        try:
            _available[applet_id] = bool(cls and cls.available())
        except Exception:
            _available[applet_id] = False
    return _available[applet_id]


def open_applet(applet_id, tab=None):
    """Create and show the applet dialog -> the dialog (caller keeps a reference)."""
    dlg = REGISTRY[applet_id](tab=tab)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg


def applet_for_kcm(kcm):
    """Native applet replacing a KDE module -> (id, tab) or None (see AppletDialog.REPLACES).
    "_x11" variants map like the base module."""
    base = kcm[:-4] if kcm.endswith("_x11") else kcm
    for aid, cls in REGISTRY.items():
        for entry in cls.REPLACES:
            name, _, tab = entry.partition("#")
            if name == base and available(aid):
                return aid, (tab or None)
    return None
