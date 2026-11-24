# SPDX-License-Identifier: GPL-3.0-or-later
"""Vista Control Panel design schema.

Every size, spacing, font and color the Control Panel and its applets use comes from
here, so all screens look like one product. Based on the Windows Vista UX guidelines
(Segoe UI 9 pt body, 12 pt "main instruction" in blue, ~11 px dialog margins, ~7 px
between related and ~11 px between unrelated controls), rounded to a 4 px grid. Colors and
Control Panel geometry are measured from Vista screenshots (Microsoft's "Windows Vista UX
Walkthrough" and lossless captures): text #003399 / #0066CC / #3399FF are the guideline
values; the task pane is Vista's blue-to-green gradient, 208 px wide, white links on a
25 px pitch starting 36 px from its edge.

Fonts are *ratios* of the system UI font, so a larger system font scales everything
consistently. Use the roles below; don't set point sizes or colors directly."""
from dataclasses import dataclass

from PyQt6.QtGui import QFont

# ----------------------------------------------------------------------------- colors
COLOR = {
    "text": "#000000",          # normal text, values (Vista: black)
    "secondary": "#5b5b5b",     # descriptions, explanations, column captions
    "instruction": "#003399",   # main instruction / page headings (Vista MainInstruction)
    "section": "#003399",       # section headings (Vista group headers)
    "heading": "#1e7b1e",       # category and applet names (Vista Control Panel green)
    "link": "#0066cc",          # Vista HyperLinkText
    "link_hover": "#3399ff",    # Vista Hot
    "pane_link": "#ffffff",     # task pane links: white on the blue-green pane
    "pane_hover": "#ffffff",
    "pane_g0": "#416fa6",       # task pane gradient, top ... bottom (measured)
    "pane_g1": "#4f8793",
    "pane_g2": "#5d9f82",
    "pane_g3": "#6cb772",
    "error": "#b00020",
    "rule": "#d5dfe9",          # horizontal separator lines
    "command_area": "#f0f0f0",  # Vista: the grey strip with the buttons under a page
    "command_line": "#dfdfdf",
    "page": "#ffffff",          # content background
    "pane_top": "#dce8f6",      # task pane gradient
    "pane_bottom": "#eef4fb",
    "pane_border": "#b9cbe2",
    "field_border": "#8ea6c4",  # address bar
    "crumb_sep": "#6b7d93",
    "select": "#2a7ad8",        # selected swatch/tile border
    "select_hover": "#6fb0f0",
    "swatch_border": "#8a9bb0",
    "clock_rim": "#7d93ad",     # analog clock (Date and Time)
    "clock_face": "#ffffff",
    "clock_tick": "#3a4a5c",
    "clock_tick_minor": "#a9b6c6",
    "clock_hand": "#1f2f44",
    "clock_second": "#c0392b",
    "canvas": "#f3f6fa",        # monitor arrangement background (Display Settings)
    "monitor": "#5b7fae",
    "monitor_disabled": "#a9b6c6",
    "monitor_selected": "#2a7ad8",
    "monitor_text": "#ffffff",
    "identify_bg": "#1e3287",   # "Identify Monitors" number overlay
    "identify_text": "#ffffff",
    "bezel_top": "#4a4f57",     # monitor illustration (Screen Saver preview)
    "bezel_bottom": "#1d2025",
    "bezel_edge": "#15171a",
    "stand": "#2b2f35",
    "status_on": "#2e9b3a",     # "On" indicator (Sharing and Discovery)
    "on_error": "#ffffff",      # mark drawn on an error-colored badge (network map)
}

# ----------------------------------------------------------------------------- spacing
# Vista's spacing (UX guidelines, relative pixels): 11 margins, 7 related, 11 unrelated,
# 5 label-to-control, 16 to the first control of a group box. Use the semantic names in code.
XS, S, M, L, XL, XXL = 4, 7, 11, 16, 23, 32   # Vista: 7 related, 11 unrelated / margins, 23 page edge

SPACE = {
    "none": 0,            # lines that read as one item (a choice and its "using ..." line)
    "link_gap": XS,       # between stacked links (task lists, pane links)
    "related": S,         # between related controls (label/field, radio/description)
    "unrelated": M,       # between separate blocks or groups
    "section": L,         # space before a new section heading
    "icon_gap": M,        # icon to its text
    "grid_h": L,          # label/value columns
    "grid_v": S,          # rows in a label/value grid
    "home_col": XXL,      # Control Panel home: between the two category columns
    "home_row": XL,       # Control Panel home: between categories
    "tile": S,            # between swatches / tiles in a row
}

MARGIN = {                # (left, top, right, bottom)
    "dialog": (M, M, M, M),            # outer dialog edge (around tabs and buttons)
    "dialog_page": (M, M, M, M),       # inside a tab / the single page of a dialog
    "cp_page": (23, 20, 23, XL),       # Control Panel content (Vista: heading 23 px from the pane)
    "taskpane": (22, 16, 8, 22),       # Vista: bullets at 22 px, link text at 36 px
    "pane_row": (0, 0, 0, 0),
    "navbar": (S, S - 2, S, S - 2),
    "address": (XS, 1, XS, 1),
    "choice": (S, S - 2, M, S - 2),    # a clickable choice row (AutoPlay actions)
    "none": (0, 0, 0, 0),
}

ICON = {"small": 16, "toolbar": 24, "medium": 32, "large": 48, "hero": 128}

SIZE = {                  # default window sizes (w, h)
    "control_panel": (980, 700),
    "dialog": (460, 500),            # standard property sheet
    "dialog_wide": (620, 540),       # pages with two columns of controls
    "taskpane_width": 208,           # Vista Control Panel task pane
    "pane_pitch": 25,                # one task pane link per 25 px (Vista)
    "pane_bullet": 14,               # bullet column before the current page's link
    "dialog_pane_width": 208,        # task pane inside an applet window (as wide as Vista's)
    "search_width": 220,
    "label_column": 180,             # first column of label/value grids
    "swatch": (60, 52),              # color swatches (Window Color)
    "clock": 150,                    # analog clock (Date and Time)
    "classic_tile": (75, 98),        # Classic View grid cell (Vista: 48 px icon + two text lines)
    "classic_columns": (75, 100),    # Classic View header: Name, Category
    "button_min_width": 80,          # OK / Cancel / Apply (Windows: 50 DLU)
    "monitor_canvas_height": 170,    # Display Settings arrangement area
    "identify": (220, 220),          # Identify Monitors overlay
    "monitor_preview": (240, 200),   # Screen Saver preview monitor
    "thumbnail": (160, 100),         # Desktop Background pictures
}


# ----------------------------------------------------------------------------- type
@dataclass(frozen=True)
class Role:
    """A type role: size relative to the system font, weight, and a COLOR key."""
    scale: float = 1.0
    bold: bool = False
    color: str = "text"


TYPE = {
    "body": Role(),                                    # normal text
    "strong": Role(bold=True),                         # bold body text (e.g. option names)
    "value": Role(),                                   # a value next to a label
    "secondary": Role(color="secondary"),              # descriptions, help text
    "caption": Role(color="secondary"),                # column captions, small notes
    "section": Role(bold=True, color="section"),       # section / group heading
    "instruction": Role(12 / 9, color="instruction"),  # main instruction: page/dialog heading
    "subinstruction": Role(11 / 9, color="instruction"),   # a second heading on the same page
    "emphasis": Role(11 / 9),                          # a prominent value (edition, clock)
    "choice": Role(color="instruction"),               # an action you click (AutoPlay "View pictures")
    "link": Role(color="link"),
    "pane_link": Role(color="pane_link"),
    "pane_current": Role(bold=True, color="pane_link"),     # the page you're on
    "pane_heading": Role(bold=True, color="pane_link"),
    "link_title": Role(11 / 9, color="heading"),       # applet / category name links
    "error": Role(color="error"),
    "monitor_number": Role(18 / 9, bold=True, color="monitor_text"),   # number on a monitor tile
    "identify": Role(96 / 9, bold=True, color="identify_text"),        # Identify Monitors overlay
}


def font(role, base=None):
    """QFont for a type role, derived from the application's UI font."""
    from PyQt6.QtWidgets import QApplication
    r = TYPE[role]
    f = QFont(base if base is not None else QApplication.font())
    if r.scale != 1.0:
        f.setPointSizeF(f.pointSizeF() * r.scale)
    f.setBold(r.bold)
    return f


def color(role_or_key):
    """Hex color for a type role or a COLOR key."""
    if role_or_key in TYPE:
        return COLOR[TYPE[role_or_key].color]
    return COLOR[role_or_key]


def margins(layout, kind):
    """Set a layout's contents margins from MARGIN[kind]; returns the layout."""
    layout.setContentsMargins(*MARGIN[kind])
    return layout


def stylesheet():
    """Application-level stylesheet for the Control Panel window."""
    c = COLOR
    return f"""
#navbar {{
    /* the same light glass-like band as Dolphin's address row (Kvantum toolbar) */
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f4f7fc, stop:0.04 #d4dbed, stop:1 #e1e6f6);
    border-bottom: 1px solid #8b9db5;
}}
#content, #page, #classic {{ background: {c['page']}; }}
QToolButton#addressdrop {{ border: none; background: transparent; }}
QToolButton#addressdrop::menu-indicator {{ image: none; }}
#address {{ background: {c['page']}; border: 1px solid {c['field_border']}; border-radius: 2px; }}
QToolButton#crumb {{ padding: 1px 2px; color: {c['text']}; }}
QListWidget#classiclist {{ background: {c['page']}; padding: 2px 4px; }}
QListWidget#classiclist::item {{ color: {c['text']}; }}
"""
