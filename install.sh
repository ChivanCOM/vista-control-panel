#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Install (or remove) Vista Control Panel.
#
#   sudo ./install.sh                  install to /usr/local
#   sudo PREFIX=/usr ./install.sh      install to /usr (e.g. for a distro package)
#   DESTDIR=/tmp/pkg ./install.sh      stage into a directory (packaging)
#   sudo ./install.sh --uninstall      remove what install.sh installed
#
# Installs: <PREFIX>/lib/vista-control-panel (the program, its applets, the optional
# settings router), <PREFIX>/bin/vista-control-panel and vista-autoplay, the menu entry, and
# the AutoPlay autostart entry (AutoPlay stays off until switched on in the Control Panel).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
PREFIX=${PREFIX:-/usr/local}
DESTDIR=${DESTDIR:-}
LIBDIR=$PREFIX/lib/vista-control-panel
APPS=$PREFIX/share/applications
AUTOSTART=/etc/xdg/autostart

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$DESTDIR$LIBDIR"
    rm -f "$DESTDIR$PREFIX/bin/vista-control-panel" "$DESTDIR$PREFIX/bin/vista-autoplay" \
          "$DESTDIR$APPS/vista-control-panel.desktop" "$DESTDIR$AUTOSTART/vista-autoplay.desktop"
    echo "Vista Control Panel removed from $PREFIX"
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -c 'import PyQt6.QtWidgets' 2>/dev/null \
    || echo "note: PyQt6 not found - install it (Debian/Ubuntu: python3-pyqt6, Fedora: python3-pyqt6, Arch: python-pyqt6)" >&2

# the program: copied without bytecode caches; the root helper must not be group/world writable
install -d "$DESTDIR$LIBDIR"
(cd "$HERE/src" && find . -type d -name __pycache__ -prune -o -type f -print) | while read -r f; do
    install -D -m 0644 "$HERE/src/$f" "$DESTDIR$LIBDIR/$f"
done
chmod 0755 "$DESTDIR$LIBDIR/helpers/set-computer-name"
install -D -m 0755 "$HERE/router/systemsettings" "$DESTDIR$LIBDIR/router/systemsettings"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
for b in vista-control-panel vista-autoplay; do
    sed "s|@LIBDIR@|$LIBDIR|" "$HERE/bin/$b" > "$tmp"
    install -D -m 0755 "$tmp" "$DESTDIR$PREFIX/bin/$b"
done
install -D -m 0644 "$HERE/data/vista-control-panel.desktop" "$DESTDIR$APPS/vista-control-panel.desktop"
install -D -m 0644 "$HERE/data/vista-autoplay.desktop" "$DESTDIR$AUTOSTART/vista-autoplay.desktop"

echo "Vista Control Panel installed to $PREFIX - start it with: vista-control-panel"
