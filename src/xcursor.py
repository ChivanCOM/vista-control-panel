# SPDX-License-Identifier: GPL-3.0-or-later
"""Read pointer images from X cursor themes, for previews (Mouse > Pointers).

Xcursor file format: "Xcur" header, a table of contents, then image chunks of
type 0xfffd0002 with (width, height, xhot, yhot, delay) and premultiplied ARGB32 pixels.
Themes are directories with a cursors/ subfolder; missing cursors come from the themes
listed in index.theme Inherits=."""
import os
import struct

from PyQt6.QtGui import QImage, QPixmap

IMAGE_TYPE = 0xFFFD0002

# Windows pointer roles -> X cursor names (first existing one wins)
ROLES = [
    ("Normal Select", ["default", "left_ptr", "arrow"]),
    ("Help Select", ["help", "question_arrow", "whats_this", "left_ptr_help"]),
    ("Working in Background", ["progress", "left_ptr_watch", "half-busy"]),
    ("Busy", ["wait", "watch"]),
    ("Precision Select", ["crosshair", "cross", "tcross"]),
    ("Text Select", ["text", "xterm", "ibeam"]),
    ("Unavailable", ["not-allowed", "crossed_circle", "forbidden", "no-drop"]),
    ("Vertical Resize", ["ns-resize", "size_ver", "sb_v_double_arrow", "v_double_arrow"]),
    ("Horizontal Resize", ["ew-resize", "size_hor", "sb_h_double_arrow", "h_double_arrow"]),
    ("Diagonal Resize 1", ["nwse-resize", "size_fdiag", "bd_double_arrow"]),
    ("Diagonal Resize 2", ["nesw-resize", "size_bdiag", "fd_double_arrow"]),
    ("Move", ["move", "fleur", "size_all", "all-scroll"]),
    ("Link Select", ["pointer", "hand2", "pointing_hand", "hand1"]),
]


def search_dirs():
    """Existing cursor theme folders, in libXcursor's lookup order ($XCURSOR_PATH first)."""
    dirs = os.environ.get("XCURSOR_PATH", "").split(":") + [
        os.path.expanduser("~/.local/share/icons"), os.path.expanduser("~/.icons"), "/usr/share/icons"]
    seen, out = set(), []
    for d in dirs:
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def theme_dir(name):
    """Folder of the cursor theme `name` (first match in search_dirs()), or None."""
    for d in search_dirs():
        p = os.path.join(d, name)
        if os.path.isdir(p):
            return p
    return None


def _inherits(path):
    """Theme names from index.theme's Inherits= line."""
    try:
        with open(os.path.join(path, "index.theme"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Inherits="):
                    return [t.strip() for t in line.split("=", 1)[1].split(",") if t.strip()]
    except OSError:
        pass
    return []


def find_cursor_file(theme, names, _depth=0):
    """Path of the first cursor in `names` in `theme` or the themes it inherits."""
    path = theme_dir(theme)
    if not path or _depth > 4:          # depth limit: themes that inherit in a cycle
        return None
    for n in names:
        f = os.path.join(path, "cursors", n)
        if os.path.isfile(f):
            return f
    for parent in _inherits(path):
        f = find_cursor_file(parent, names, _depth + 1)
        if f:
            return f
    return None


def load_image(path, size=32):
    """First frame of the cursor image whose nominal size is closest to `size`."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if data[:4] != b"Xcur" or len(data) < 16:
        return None
    try:
        _hsize, _ver, ntoc = struct.unpack_from("<III", data, 4)
        best = None
        for i in range(ntoc):
            typ, sub, pos = struct.unpack_from("<III", data, 16 + i * 12)
            if typ == IMAGE_TYPE and (best is None or abs(sub - size) < abs(best[0] - size)):
                best = (sub, pos)
        if best is None:
            return None
        pos = best[1]
        _chunk, _typ, _sub, _v, w, h, _xh, _yh, _delay = struct.unpack_from("<9I", data, pos)
    except struct.error:                # truncated or corrupt file
        return None
    pixels = data[pos + 36: pos + 36 + w * h * 4]
    if len(pixels) < w * h * 4:
        return None
    img = QImage(pixels, w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied)
    return img.copy()     # detach from the Python buffer


def preview(theme, names, size=32):
    """QPixmap of the first of `names` found in `theme` (or its parents), or None."""
    f = find_cursor_file(theme, names)
    img = load_image(f, size) if f else None
    return QPixmap.fromImage(img) if img is not None else None


def pretty_name(name, title=None):
    """'vista-aero-drop' -> 'Vista Aero Drop' when the theme has no proper Name=."""
    if title and title != name:
        return title
    return " ".join(w[:1].upper() + w[1:] for w in name.replace("_", " ").replace("-", " ").split())
