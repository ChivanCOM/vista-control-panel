# Contributing

Thanks for helping! Bug reports, fixes and new settings screens are all welcome.

## Reporting a problem

Open an issue with:
- your distribution and KDE Plasma version (`plasmashell --version`),
- what you clicked and what happened (a screenshot helps),
- the terminal output of `vista-control-panel` if it printed an error.

## Making changes

1. Read [`docs/DESIGN.md`](docs/DESIGN.md) first. The Control Panel follows a small design
   schema (`src/style.py`): no colours, point sizes, margins or spacings in code — use the
   tokens and the helpers in `src/ui.py`, so every screen looks like Vista.
2. Run it from your checkout, no install needed:
   ```sh
   python3 src/controlpanel.py                  # Control Panel home
   python3 src/controlpanel.py --applet mouse   # one settings dialog
   ```
3. Settings screens must write **the same keys KDE writes** (check the KDE module's source),
   so KDE's own settings, the Control Panel and the desktop always agree.
4. Never block the window: slow work goes through `ui.Jobs` / `QProcess`; administrator actions
   go through `pkexec` (see `src/helpers/`), never with passwords on a command line.
5. Before opening a pull request, check that everything still loads:
   ```sh
   cd src && python3 -m py_compile *.py applets/*.py
   QT_QPA_PLATFORM=offscreen python3 -c "import sys; sys.path.insert(0,'.'); \
     from PyQt6.QtWidgets import QApplication; a=QApplication([]); \
     import applets, catalog, controlpanel; print(len(applets.REGISTRY), applets.ERRORS)"
   ```
   It should print the number of applets and `[]` (no errors).

New settings screens can also start life as an extension (`src/extensions/README.md`) — no
change to the core needed.

## License

By contributing you agree that your contributions are licensed under the
GNU General Public License v3.0 or later, like the rest of the project.
