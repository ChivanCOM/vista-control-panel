# Control Panel extensions

Drop a Python module here (or in `/etc/vista-control-panel/extensions/` or
`~/.local/share/vista-control-panel/extensions/`) to add to the Control Panel
without touching its core. See [`docs/DESIGN.md`](../../docs/DESIGN.md) for the full guide.

Each `*.py` file here (names starting with `_` are skipped) is imported at startup and
may define:

- `AppletDialog` subclasses with an `ID`: native applets, opened as `native:<ID>`;
- `APPLETS` / `CATEGORIES` lists and a `PAGES` dict, merged into the catalog.

Later folders win (per-user over machine-wide over this one), and an applet with an
existing `ID` replaces the built-in one. A module that fails to import is skipped and
listed in `applets.ERRORS`; it never stops the Control Panel.
