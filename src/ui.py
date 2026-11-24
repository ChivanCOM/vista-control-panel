# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared Vista-style widgets and small helpers for the Vista Control Panel: links,
labels, layouts, the task pane, command running (run, Jobs) and KDE config access
(kread, kwrite_cmd). All sizes, fonts and colors come from style.py (the design schema)."""
import os
import subprocess

from PyQt6.QtCore import QObject, QProcess, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QSizePolicy, QWidget,
                             QVBoxLayout)

import style
from style import ICON, MARGIN, SPACE


# ----------------------------------------------------------------------------- widgets
class Link(QLabel):
    """A Vista-style hyperlink: colored text, underline on hover/focus, keyboard activatable.
    role: "link" (task links), "link_title" (green applet/category names), "pane_link"."""
    clicked = pyqtSignal()

    def __init__(self, text, role="link", parent=None):
        super().__init__(text, parent)
        self._role = role
        self._color = style.color(role)
        self.setFont(style.font(role))
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._paint(False)

    def _paint(self, hover):
        f = self.font()
        f.setUnderline(hover or self.hasFocus())
        self.setFont(f)
        # Vista: content links light up (#3399FF); the task pane's white links only underline
        if hover:
            c = style.color("pane_hover") if self._role.startswith("pane") else style.color("link_hover")
        else:
            c = self._color
        self.setStyleSheet(f"color: {c}; background: transparent;")

    def enterEvent(self, e):
        self._paint(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._paint(False)
        super().leaveEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._paint(False)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._paint(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(e)


def icon_label(name, size="large"):
    """An icon from the theme. size: a style.ICON key ("small", "medium", "large", "hero")."""
    px = ICON[size] if isinstance(size, str) else size
    lbl = QLabel()
    if os.path.isabs(name):                       # a picture file (e.g. a distro logo)
        icon = QIcon(name)
    else:
        icon = QIcon.fromTheme(name, QIcon.fromTheme("preferences-other"))
    lbl.setPixmap(icon.pixmap(QSize(px, px)))
    lbl.setFixedSize(px, px)
    lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    lbl.setStyleSheet("background: transparent;")
    return lbl


def text_label(text, role="secondary", wrap=True, selectable=True):
    """A label in a type role from style.TYPE ("instruction", "section", "secondary", ...)."""
    lbl = QLabel(text)
    lbl.setFont(style.font(role))
    lbl.setWordWrap(wrap)
    lbl.setStyleSheet(f"color: {style.color(role)}; background: transparent;")
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


def set_role(label, role):
    """Change the type role of an existing label."""
    label.setFont(style.font(role))
    label.setStyleSheet(f"color: {style.color(role)}; background: transparent;")


class EvenGrid(QListWidget):
    """Icon grid whose columns always share the full width evenly (no ragged right edge).
    cell: (min width, height) of a cell."""

    def __init__(self, icon_size, cell):
        super().__init__()
        self._cell = cell
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setIconSize(icon_size)
        self.setUniformItemSizes(True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        avail = self.viewport().width() - 2 * SPACE["related"]   # the view keeps a small inner margin
        cols = max(1, avail // self._cell[0])
        self.setGridSize(QSize(avail // cols, self._cell[1]))


def hrule():
    """A one-pixel horizontal separator in the schema's rule color."""
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {style.color('rule')};")
    return line


# ----------------------------------------------------------------------------- layouts
def vbox(parent=None, margin="none", spacing="related"):
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setContentsMargins(*MARGIN[margin])
    lay.setSpacing(SPACE[spacing])
    return lay


def hbox(parent=None, margin="none", spacing="related"):
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setContentsMargins(*MARGIN[margin])
    lay.setSpacing(SPACE[spacing])
    return lay


def form_grid(label_column=False):
    """Label/value grid with schema spacing; optional fixed label column width."""
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(SPACE["grid_h"])
    g.setVerticalSpacing(SPACE["grid_v"])
    if label_column:
        g.setColumnMinimumWidth(0, style.SIZE["label_column"])
    return g


def gap(layout, kind="unrelated"):
    """Add the schema's space of `kind` before the next item, on top of the layout's own
    spacing (so the visible distance is exactly SPACE[kind])."""
    layout.addSpacing(max(0, SPACE[kind] - max(layout.spacing(), 0)))


def section(layout, title):
    """Section heading + rule, with the schema's space before it (not before the first)."""
    if layout.count():
        gap(layout, "section")
    layout.addWidget(text_label(title, "section"))
    layout.addWidget(hrule())


def clear_layout(layout):
    """Remove everything from a layout right away (deleteLater alone leaves the old
    widgets painted until the event loop runs, so they overlap the new ones)."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


# ----------------------------------------------------------------------------- commands
def run(argv, timeout=20):
    """Run a quick command synchronously -> (ok, stdout, stderr)."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout)
        return p.returncode == 0, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return False, "", str(e)


class Jobs(QObject):
    """Run commands one after another without freezing the UI (commands that need an
    administrator show the UAC/polkit prompt while the window keeps painting).
    finished(ok, error_text) is emitted once; stops at the first failure."""
    finished = pyqtSignal(bool, str)

    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self._queue = [c for c in commands if c]
        self._proc = None

    def start(self):
        self._next()

    def _next(self):
        if not self._queue:
            self.finished.emit(True, "")
            return
        argv = self._queue.pop(0)
        self._proc = QProcess(self)
        self._proc.finished.connect(self._done)
        # only a failed start is handled here: a crash also emits finished(), handled in _done
        self._proc.errorOccurred.connect(
            lambda e: self._fail(f"Could not run {argv[0]}") if e == QProcess.ProcessError.FailedToStart else None)
        self._proc.start(argv[0], argv[1:])

    def _done(self, code, status):
        if code != 0 or status == QProcess.ExitStatus.CrashExit:
            err = bytes(self._proc.readAllStandardError()).decode(errors="replace").strip()
            self._fail(err or f"failed with exit code {code}")
            return
        self._next()

    def _fail(self, msg):
        self._queue.clear()
        self.finished.emit(False, msg)


# ----------------------------------------------------------------------------- KDE config
def kread(file, groups, key, default=""):
    """A KConfig value via kreadconfig6 (groups: a name or a list for nested groups);
    `default` (as a string) if it is unset or kreadconfig6 is missing."""
    argv = ["kreadconfig6", "--file", file]
    for g in groups if isinstance(groups, (list, tuple)) else [groups]:
        argv += ["--group", g]
    argv += ["--key", key, "--default", str(default)]
    ok, out, _ = run(argv)
    return out.strip() if ok else str(default)


def kwrite_cmd(file, groups, key, value, notify=False):
    """argv for kwriteconfig6 setting one key (for Jobs / AppletDialog.apply_changes).
    notify=True sends KConfig's change notification, so running KDE apps pick the new
    value up immediately (used for kdeglobals settings like double-click speed)."""
    argv = ["kwriteconfig6", "--file", file] + (["--notify"] if notify else [])
    for g in groups if isinstance(groups, (list, tuple)) else [groups]:
        argv += ["--group", g]
    if isinstance(value, bool):
        argv += ["--type", "bool", "--key", key, "true" if value else "false"]
    else:
        argv += ["--key", key, str(value)]
    return argv


def kwrite(file, groups, key, value):
    """Write one KConfig key right away -> True on success."""
    return run(kwrite_cmd(file, groups, key, value))[0]


class TaskPane(QFrame):
    """Windows Vista's Control Panel task pane: a blue-to-green gradient with soft light
    swooshes low down, white links one per SIZE["pane_pitch"] pixels, bold white headings,
    and a bullet hanging in the margin beside the page you are on."""

    def __init__(self, parent=None, width=None):
        super().__init__(parent)
        self.setObjectName("taskpane")
        self.setFixedWidth(width or style.SIZE["taskpane_width"])
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(*MARGIN["taskpane"])
        self.layout_.setSpacing(0)

    def _row(self, widget, bullet=False):
        """One line of the pane: a fixed bullet column, then the text, padded to the pitch."""
        row = QWidget()
        h = QHBoxLayout(row)
        fm = widget.fontMetrics()
        pad = max(0, style.SIZE["pane_pitch"] - fm.height())
        h.setContentsMargins(0, pad // 2, 0, pad - pad // 2)
        h.setSpacing(0)
        dot = QLabel("•" if bullet else "")
        dot.setFixedWidth(style.SIZE["pane_bullet"])
        dot.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        dot.setStyleSheet(f"color: {style.color('pane_link')}; background: transparent;")
        dot.setFont(widget.font())
        h.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(widget, 1)
        self.layout_.addWidget(row)
        return widget

    def add_link(self, link, current=False):
        return self._row(link, bullet=current)

    def add_heading(self, text, first=None):
        if first is None:
            first = self.layout_.count() == 0
        if not first:
            self.layout_.addSpacing(style.SPACE["section"] - 4)
        return self._row(text_label(text, "pane_heading", selectable=False))

    def add_stretch(self):
        self.layout_.addStretch(1)

    def clear(self):
        clear_layout(self.layout_)

    def paintEvent(self, e):
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
        p = QPainter(self)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        for at, key in ((0.0, "pane_g0"), (0.45, "pane_g1"), (0.72, "pane_g2"), (1.0, "pane_g3")):
            g.setColorAt(at, QColor(style.color(key)))
        p.fillRect(self.rect(), g)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Vista's swooshes: soft translucent bands rising from the lower left, a few
        # brighter threads along their edges
        p.setPen(Qt.PenStyle.NoPen)
        for top, depth, alpha in ((0.58, 0.20, 26), (0.66, 0.16, 22), (0.75, 0.12, 20)):
            path = QPainterPath(QPointF(-4, h * (top + depth)))
            path.cubicTo(QPointF(w * 0.25, h * (top + depth * 0.4)), QPointF(w * 0.55, h * top),
                         QPointF(w + 4, h * (top - 0.08)))
            path.lineTo(w + 4, h * (top - 0.08 + depth * 0.35))
            path.cubicTo(QPointF(w * 0.6, h * (top + depth * 0.45)), QPointF(w * 0.3, h * (top + depth * 0.9)),
                         QPointF(-4, h * (top + depth * 1.35)))
            path.closeSubpath()
            p.setBrush(QColor(255, 255, 255, alpha))
            p.drawPath(path)
        for top, alpha in ((0.62, 70), (0.70, 55), (0.79, 45), (0.84, 35)):
            path = QPainterPath(QPointF(-4, h * (top + 0.16)))
            path.cubicTo(QPointF(w * 0.3, h * (top + 0.07)), QPointF(w * 0.6, h * top),
                         QPointF(w + 4, h * (top - 0.07)))
            p.setPen(QPen(QColor(255, 255, 255, alpha), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.end()


class CommandBar(QFrame):
    """Vista Explorer's command bar (measured): 30 px between dark lines, a lit upper half,
    a sharp step to the darker lower half that brightens to a light bottom edge; white
    buttons that light up like glass on hover."""
    STYLE = """
        QFrame#commandbar {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #bacac9, stop:0.034 #91b2bb, stop:0.48 #448b9f, stop:0.5 #186076,
                stop:0.9 #4e8d9e, stop:0.94 #5f97a4, stop:1 #99c7d4);
            border-top: 1px solid #45575f; border-bottom: 1px solid #12343e; }
        QFrame#commandbar QToolButton { color: white; background: transparent; border: 1px solid transparent;
            border-radius: 3px; padding: 3px 7px; }
        QFrame#commandbar QToolButton:hover { border-color: rgba(255,255,255,150);
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,95),
                stop:0.48 rgba(255,255,255,45), stop:0.5 rgba(255,255,255,18), stop:1 rgba(255,255,255,50)); }
        QFrame#commandbar QToolButton:pressed { border-color: rgba(10,30,45,170);
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0,20,40,90), stop:1 rgba(255,255,255,30)); }
        QFrame#commandbar QToolButton:disabled { color: rgba(255,255,255,110); }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("commandbar")
        self.setStyleSheet(self.STYLE)
        self.setFixedHeight(32)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(6, 1, 6, 1)
        self.row.setSpacing(2)
        self.row.addStretch(1)

    def add_button(self, text, icon=None):
        from PyQt6.QtWidgets import QToolButton
        b = QToolButton(self)
        b.setText(text)
        if icon:
            b.setIcon(QIcon.fromTheme(icon))
            b.setIconSize(QSize(16, 16))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setAutoRaise(True)
        self.row.insertWidget(self.row.count() - 1, b)
        return b


class DetailsPane(QFrame):
    """Vista Explorer's details pane (measured): 70 px, a grey-blue top line with light
    shading under it, a left-to-right wash from near white to light blue; a 48 px icon at
    18 px, the text from 89 px, top-aligned: the name, then grey keys with black values."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(max(70, 4 * self.fontMetrics().height() + 10))
        h = QHBoxLayout(self)
        h.setContentsMargins(18, 9, 18, 6)
        h.setSpacing(23)
        self.icon = QLabel()
        self.icon.setFixedSize(48, 48)
        self.icon.setStyleSheet("background: transparent;")
        h.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(7)
        self.grid.setVerticalSpacing(1)
        h.addLayout(self.grid, 1)

    def show_item(self, icon, title, pairs=(), subtitle=None):
        """icon: QIcon; pairs: [(key, value)], filled three to a column like Vista."""
        clear_layout(self.grid)
        self.icon.setPixmap(icon.pixmap(QSize(48, 48)))
        name = text_label(title, "body", wrap=False, selectable=False)
        self.grid.addWidget(name, 0, 0, 1, 2)
        row = 1
        if subtitle:
            self.grid.addWidget(text_label(subtitle, "secondary", wrap=False, selectable=False), 1, 0, 1, 2)
            row = 2
        col, r = 2, 0
        for key, value in pairs:
            k = text_label(key, "secondary", wrap=False, selectable=False)
            k.setStyleSheet(k.styleSheet() + "color: #5a6779;")
            k.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(k, r, col)
            self.grid.addWidget(text_label(value, "body", wrap=False, selectable=True), r, col + 1)
            r += 1
            if r == 3:
                r, col = 0, col + 2
        self.grid.setColumnMinimumWidth(1, 16)
        self.grid.setColumnStretch(col + 2, 1)

    def paintEvent(self, e):
        from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
        p = QPainter(self)
        r = self.rect()
        g = QLinearGradient(0, 0, r.width(), 0)
        for at, c in ((0.0, "#f6faf9"), (0.37, "#edfaff"), (0.55, "#e8f7fc"), (0.72, "#d5ebf8"),
                      (0.9, "#c7ddf2"), (1.0, "#c0dbf0")):
            g.setColorAt(at, QColor(c))
        p.fillRect(r, g)
        shade = QLinearGradient(0, 0, 0, 8)
        shade.setColorAt(0, QColor(0x9f, 0xbc, 0xd2, 120))
        shade.setColorAt(1, QColor(0x9f, 0xbc, 0xd2, 0))
        p.fillRect(0, 0, r.width(), 8, shade)
        p.setPen(QColor("#a7b1ba"))
        p.drawLine(0, 0, r.width(), 0)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, hgt = r.width(), r.height()
        for i in range(4):
            path = QPainterPath()
            x0 = w - 0.22 * w + i * 9
            path.moveTo(x0, hgt + 2)
            path.cubicTo(x0 + 0.06 * w, hgt * 0.55, w - 0.07 * w, hgt * 0.25, w + 4, 2 + i * 4)
            p.setPen(QPen(QColor(255, 255, 255, 190 - i * 35), 1.2))
            p.drawPath(path)
        p.end()
