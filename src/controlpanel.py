#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Vista Control Panel — a Windows Vista style Control Panel for KDE Plasma.

Category View, Classic View, instant search, breadcrumbs with Back/Forward, a task pane
with Recent Tasks, and a native "System" page. Every link opens a KDE settings module
on its own (kcmshell6) or the right program; see catalog.py for the mapping.

Usage: vista-control-panel [page]
       vista-control-panel --applet <id>[#tab]
       vista-control-panel --kcm <kde module> [--args ...]   (used by the systemsettings router)
       page   = home | classic | sysinfo | admintools | backup | sharing | <category id>
       applet = an ID from applets/, e.g. windowcolor | power | mouse | display
"""
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys

from PyQt6.QtCore import QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                             QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog as C  # noqa: E402

APP_NAME = "Control Panel"
import style  # noqa: E402
from style import ICON, SIZE, SPACE  # noqa: E402
import distro
RECENT_MAX = 6


# ----------------------------------------------------------------------------- environment
class Env:
    """Resolves catalog actions to commands, hiding what isn't installed."""

    def __init__(self):
        self.x11 = os.environ.get("XDG_SESSION_TYPE") == "x11"
        try:
            out = subprocess.run(["kcmshell6", "--list"], capture_output=True, text=True,
                                 timeout=15).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""                # no kcmshell6 (not KDE): every kcm: action is hidden
        # "--list" prints a header line, then "<module>  - <description>" per line
        self.kcms = set()
        for line in out.splitlines():
            line = line.strip()
            if line and not line.startswith("The following"):
                self.kcms.add(line.split()[0])
        self._cache = {}

    def resolve(self, action):
        """-> ("run", argv) | ("page", id) | ("native", (id, tab)) | None.
        "a|b" tries a, then b."""
        if action in self._cache:
            return self._cache[action]
        if "|" in action:
            res = None
            for alt in action.split("|"):
                res = self.resolve(alt)
                if res:
                    break
            self._cache[action] = res
            return res
        kind, _, arg = action.partition(":")
        res = None
        if kind == "native":
            aid, _, tab = arg.partition("#")
            if applets.available(aid):
                res = ("native", (aid, tab or None))
        elif kind == "kcm":
            name = arg
            if self.x11 and name + "_x11" in self.kcms:
                name += "_x11"
            if name in self.kcms:
                res = ("run", ["kcmshell6", name])
        elif kind == "settings":
            if arg in self.kcms:
                res = ("run", ["systemsettings", arg])
        elif kind == "app":
            try:
                argv = shlex.split(arg)
            except ValueError:      # unbalanced quotes (e.g. in an extension's entry)
                argv = []
            if argv and shutil.which(argv[0]):
                res = ("run", argv)
        elif kind == "page":
            res = ("page", arg)
        self._cache[action] = res
        return res

    def available(self, action):
        return self.resolve(action) is not None


# Shared Vista widgets
from ui import (Link, TaskPane, clear_layout, form_grid, gap, hbox, hrule, icon_label, section,  # noqa: E402
                text_label, vbox)
import applets  # noqa: E402

C.merge_extensions(applets.EXTENSIONS)


# ----------------------------------------------------------------------------- main window
class Page(QWidget):
    """A content page for the scroll area. Its minimum height is measured at the width it
    actually has: Qt would otherwise measure the wrapped text at the narrowest width and
    show a scroll bar on pages that fit."""

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(hint.width(), 0)


class ControlPanel(QMainWindow):
    """The Control Panel window. Pages are ids ("home", "classic", "sysinfo", a category
    or PAGES id, "search:<text>"), rebuilt on every visit and kept in a Back/Forward history."""

    def __init__(self, start_page="home"):
        super().__init__()
        self.env = Env()
        self.settings = QSettings(distro.APP_ID, "ControlPanel")
        self.cats = {c.id: c for c in C.CATEGORIES}
        self.applets = [a for a in C.APPLETS if self.env.available(a.action)]
        self.history, self.pos = [], -1

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon.fromTheme("preferences-system"))
        self.resize(*SIZE["control_panel"])

        root = QWidget()
        root.setObjectName("root")
        v = vbox(root, "none")
        v.setSpacing(0)
        v.addWidget(self._build_navbar())
        body = hbox(margin="none")
        body.setSpacing(0)
        self.taskpane = TaskPane()
        body.addWidget(self.taskpane)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("content")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.addWidget(self.scroll, 1)
        v.addLayout(body, 1)
        self.setCentralWidget(root)
        self.setStyleSheet(style.stylesheet())
        self.ensurePolished()
        self._size_navbar()

        self._search_timer = QTimer(self, singleShot=True, interval=200)
        self._search_timer.timeout.connect(self._run_search)
        for seq, fn in ((QKeySequence.StandardKey.Back, self.back),
                        (QKeySequence.StandardKey.Forward, self.forward),
                        (QKeySequence.StandardKey.Find, self.search.setFocus),
                        ("F3", self.search.setFocus),
                        ("Alt+Up", lambda: self.navigate("home")),
                        ("F5", self.refresh)):
            QShortcut(QKeySequence(seq), self, activated=fn)
        QShortcut(QKeySequence("Esc"), self.search, activated=lambda: self.search.clear())

        self.navigate(start_page if self._page_exists(start_page) else "home")

    # ------------------------------------------------------------------ chrome
    def _build_navbar(self):
        bar = QFrame()
        bar.setObjectName("navbar")
        h = hbox(bar, "navbar", "link_gap")
        self.btn_back = QToolButton(icon=QIcon.fromTheme("go-previous"), autoRaise=True,
                                    toolTip="Back (Alt+Left)")
        self.btn_fwd = QToolButton(icon=QIcon.fromTheme("go-next"), autoRaise=True,
                                   toolTip="Forward (Alt+Right)")
        for b in (self.btn_back, self.btn_fwd):
            b.setIconSize(QSize(ICON["toolbar"], ICON["toolbar"]))
        self.btn_back.clicked.connect(self.back)
        self.btn_fwd.clicked.connect(self.forward)
        h.addWidget(self.btn_back)
        h.addWidget(self.btn_fwd)

        self.address = QFrame()
        self.address.setObjectName("address")
        outer = hbox(self.address, "address")
        outer.setSpacing(0)
        self.address_layout = hbox(margin="none")
        self.address_layout.setSpacing(0)
        outer.addLayout(self.address_layout, 1)
        # Vista: a drop-down arrow at the right end of the address bar lists recent places
        self.btn_recent = QToolButton(autoRaise=True, toolTip="Recent pages")
        self.btn_recent.setObjectName("addressdrop")
        self.btn_recent.setArrowType(Qt.ArrowType.DownArrow)
        self.btn_recent.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_recent.setMenu(QMenu(self.btn_recent))
        self.btn_recent.menu().aboutToShow.connect(self._fill_recent_menu)
        outer.addWidget(self.btn_recent)
        h.addWidget(self.address, 1)
        self.btn_refresh = QToolButton(icon=QIcon.fromTheme("view-refresh"), autoRaise=True, toolTip="Refresh (F5)")
        self.btn_refresh.clicked.connect(self.refresh)
        h.addWidget(self.btn_refresh)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search")
        self.search.setClearButtonEnabled(True)
        # Vista: the magnifier sits at the right end of the search box
        self.search.addAction(QIcon.fromTheme("system-search"), QLineEdit.ActionPosition.TrailingPosition)
        self.search.setFixedWidth(SIZE["search_width"])
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        # Vista's grey italic "Search"; what you type is upright
        def italic_when_empty(text):
            f = self.search.font()
            f.setItalic(not text)
            self.search.setFont(f)
        self.search.textChanged.connect(italic_when_empty)
        italic_when_empty("")
        h.addWidget(self.search)
        return bar

    def _fill_recent_menu(self):
        menu = self.btn_recent.menu()
        menu.clear()
        seen = []
        for page in reversed(self.history):
            if page in seen or page.startswith("search:"):
                continue
            seen.append(page)
            title = {"home": APP_NAME, "classic": "Classic View", "sysinfo": "System"}.get(page)
            if not title:
                title = self.cats[page].name if page in self.cats else C.PAGES.get(page, (page,))[0]
            menu.addAction(title, lambda p=page: self.navigate(p))
            if len(seen) == 8:
                break

    def _size_navbar(self):
        """Address bar and search box share one height, measured after styling: the
        field's own size hint, never less than the text line plus breathing room."""
        fm = self.search.fontMetrics()
        self._bar_height = max(self.search.sizeHint().height(), fm.height() + 2 * SPACE["link_gap"] + 4)
        self.search.setFixedHeight(self._bar_height)
        self.address.setFixedHeight(self._bar_height)
        self.btn_recent.setFixedSize(self._bar_height - 4, self._bar_height - 4)

    def _set_breadcrumbs(self, crumbs):
        """Vista's breadcrumb: icon, then "▸ Name" for every level and a final ▸ (where
        Vista offers the pages below), all tight against each other."""
        clear_layout(self.address_layout)
        icon = icon_label("preferences-system", "small")
        icon.setContentsMargins(SPACE["link_gap"], 0, 0, 0)
        self.address_layout.addWidget(icon)

        def sep():
            lab = QLabel("\u25B8")
            lab.setContentsMargins(SPACE["link_gap"] + 1, 0, 1, 0)
            lab.setStyleSheet(f"color: {style.color('crumb_sep')}; background: transparent;")
            self.address_layout.addWidget(lab)
        for i, (title, page) in enumerate(crumbs):
            sep()
            b = QToolButton(text=title, autoRaise=True)
            b.setObjectName("crumb")
            b.setMaximumHeight(self._bar_height - 2)
            if page and i < len(crumbs) - 1:
                b.clicked.connect(lambda _=False, p=page: self.navigate(p))
            self.address_layout.addWidget(b)
        sep()
        self.address_layout.addStretch(1)

    def _clear_taskpane(self):
        self.taskpane.clear()

    def _pane_link(self, text, page=None, action=None, current=False, label=None):
        link = Link(text, "pane_current" if current else "pane_link")
        if page:
            link.clicked.connect(lambda: self.navigate(page))
        elif action:
            link.clicked.connect(lambda: self.run(action, label or text))
        return self.taskpane.add_link(link, current)

    def _pane_heading(self, text):
        self.taskpane.add_heading(text)

    def _fill_taskpane(self, page):
        self._clear_taskpane()
        self._pane_link("Control Panel Home", page="home", current=(page == "home"))
        if page != "home" and not page.startswith("search:") and page != "classic":
            for c in C.CATEGORIES:
                if c.hidden or not self._category_applets(c.id):
                    continue
                self._pane_link(c.name, page=c.id, current=(c.id == page))
        self._pane_link("Classic View", page="classic", current=(page == "classic"))
        if page == "sysinfo":
            self._pane_heading("Tasks")
            for t in (C.Task("Device Manager", "app:kinfocenter"),
                      C.Task("System protection", "native:sysprops#protection|app:timeshift-launcher"),
                      C.Task("Advanced system settings", "native:sysprops#advanced|app:systemsettings")):
                if self.env.available(t.action):
                    self._pane_link(t.label, action=t.action)
        if page == "personalize":
            # Vista's Personalization tasks
            self._pane_heading("Tasks")
            for t in (C.Task("Change desktop icons", "native:desktopicons"),
                      C.Task("Adjust font size (DPI)", "kcm:kcm_fonts")):
                if self.env.available(t.action):
                    self._pane_link(t.label, action=t.action)
        recent = self._recent()
        if recent and page in ("home", "classic"):
            self._pane_heading("Recent Tasks")
            for label, action in recent:
                if self.env.available(action):
                    self._pane_link(label, action=action)
        self.taskpane.add_stretch()
        if page in ("home", "classic"):
            self._pane_heading("See also")
            for t in (C.Task(f"{distro.NAME} Update", "app:plasma-discover --mode Update"),
                      C.Task("All Settings", "app:systemsettings")):
                if self.env.available(t.action):
                    self._pane_link(t.label, action=t.action)

    # ------------------------------------------------------------------ navigation
    def _page_exists(self, page):
        return (page in ("home", "classic", "sysinfo") or page in self.cats or page in C.PAGES
                or page.startswith("search:"))

    def navigate(self, page, push=True):
        """Show a page; push=False moves within the history (Back/Forward)."""
        if not self._page_exists(page):
            return
        if push:
            if page.startswith("search:") and self.pos >= 0 and self.history[self.pos].startswith("search:"):
                self.history[self.pos] = page          # typing refines the same search
            else:
                del self.history[self.pos + 1:]
                self.history.append(page)
                self.pos = len(self.history) - 1
        if not page.startswith("search:") and self.search.text():
            self.search.clear()
            self._search_timer.stop()          # clearing the box must not start a new search
        self._render(page)
        self.btn_back.setEnabled(self.pos > 0)
        self.btn_fwd.setEnabled(self.pos < len(self.history) - 1)

    def back(self):
        if self.pos > 0:
            self.pos -= 1
            self.navigate(self.history[self.pos], push=False)

    def forward(self):
        if self.pos < len(self.history) - 1:
            self.pos += 1
            self.navigate(self.history[self.pos], push=False)

    def refresh(self):
        self.env = Env()
        self.applets = [a for a in C.APPLETS if self.env.available(a.action)]
        if self.history:
            self._render(self.history[self.pos])

    def _run_search(self):
        """Debounced search: results replace each other; an emptied box leaves the results."""
        q = self.search.text().strip()
        if q:
            self.navigate("search:" + q)
        elif self.pos >= 0 and self.history[self.pos].startswith("search:"):
            self.back() if self.pos > 0 else self.navigate("home")

    # ------------------------------------------------------------------ actions
    def run(self, action, label):
        """Open a catalog action; `label` is what Recent Tasks shows for it."""
        res = self.env.resolve(action)
        if not res:
            return
        kind, arg = res
        if kind == "page":
            self.navigate(arg)
            return
        if kind == "native":
            dlg = applets.open_applet(*arg)
            # keep open dialogs referenced (they are top-level windows without a parent)
            self._dialogs = [d for d in getattr(self, "_dialogs", []) if d.isVisible()] + [dlg]
            self._add_recent(label, action)
            return
        from PyQt6.QtCore import QProcess
        QProcess.startDetached(arg[0], arg[1:])
        self._add_recent(label, action)

    def _recent(self):
        """Recent Tasks as [(label, action)], stored as "label<TAB>action" strings."""
        raw = self.settings.value("recent", [], type=list) or []
        out = []
        for entry in raw:
            if isinstance(entry, str) and "\t" in entry:
                out.append(tuple(entry.split("\t", 1)))
        return out

    def _add_recent(self, label, action):
        if action.startswith("page:"):
            return
        items = [r for r in self._recent() if r[1] != action]
        items.insert(0, (label, action))
        self.settings.setValue("recent", [f"{l}\t{a}" for l, a in items[:RECENT_MAX]])

    # ------------------------------------------------------------------ pages
    def _category_applets(self, cat_id):
        return [a for a in self.applets if a.category == cat_id]

    def _render(self, page):
        if page == "home":
            title, crumbs, w = APP_NAME, [(APP_NAME, None)], self._page_home()
        elif page == "classic":
            title, crumbs, w = APP_NAME, [(APP_NAME, "home"), ("Classic View", None)], self._page_classic()
        elif page == "sysinfo":
            title = "System"
            crumbs = [(APP_NAME, "home"), (self.cats["system"].name, "system"), ("System", None)]
            w = self._page_system()
        elif page.startswith("search:"):
            q = page.split(":", 1)[1]
            title, crumbs, w = f"Search results for “{q}”", [(APP_NAME, "home"), ("Search Results", None)], self._page_search(q)
        elif page in C.PAGES:
            name = C.PAGES[page][0]
            parent = next((a.category for a in C.APPLETS if a.action == f"page:{page}"), None)
            crumbs = [(APP_NAME, "home")]
            if parent and parent in self.cats:
                crumbs.append((self.cats[parent].name, parent))
            crumbs.append((name, None))
            title, w = name, self._page_tasks(page)
        else:
            c = self.cats[page]
            crumbs = [(APP_NAME, "home")]
            if c.hidden:   # Administrative Tools / Personalization live under a category
                parent = "appearance" if page == "personalize" else "system"
                crumbs.append((self.cats[parent].name, parent))
            crumbs.append((c.name, None))
            title, w = c.name, self._page_category(page)
        self.setWindowTitle(title)
        self._set_breadcrumbs(crumbs)
        self._fill_taskpane(page)
        self.scroll.setWidget(w)

    def _page_frame(self):
        w = Page()
        w.setObjectName("page")
        return w, vbox(w, "cp_page", "unrelated")

    def _page_header(self, v, icon, title, subtitle=None):
        """Big icon + main instruction (+ optional explanation), then a rule."""
        h = hbox(spacing="icon_gap")
        h.addWidget(icon_label(icon, "large"), 0, Qt.AlignmentFlag.AlignTop)
        tv = vbox(spacing="related")
        tv.addWidget(text_label(title, "instruction"))
        if subtitle:
            tv.addWidget(text_label(subtitle, "secondary"))
        tv.addStretch(1)
        h.addLayout(tv, 1)
        v.addLayout(h)
        v.addWidget(hrule())

    def _task_links(self, tasks, layout):
        shown = 0
        for t in tasks:
            if not self.env.available(t.action):
                continue
            link = Link(t.label, "link")
            link.clicked.connect(lambda t=t: self.run(t.action, t.label))
            layout.addWidget(link)
            shown += 1
        return shown

    def _icon_block(self, icon, title_link, body_widgets=(), tasks=()):
        """The Control Panel's repeating unit: large icon, green title link, then
        an optional description and blue task links, all top-aligned."""
        box = hbox(spacing="icon_gap")
        box.addWidget(icon_label(icon, "large"), 0, Qt.AlignmentFlag.AlignTop)
        col = vbox(spacing="link_gap")
        col.addWidget(title_link)
        for w in body_widgets:
            col.addWidget(w)
        self._task_links(tasks, col)
        col.addStretch(1)
        box.addLayout(col, 1)
        return box

    def _applet_block(self, a, show_desc=False):
        title = Link(a.name, "link_title")
        title.clicked.connect(lambda a=a: self.run(a.action, a.name))
        title.setToolTip(a.description)
        body = []
        if (show_desc or not a.tasks) and a.description:
            body.append(text_label(a.description, "body"))     # Vista: descriptions in black
        return self._icon_block(a.icon, title, body, a.tasks)

    def _page_home(self):
        w, v = self._page_frame()
        # Vista's Control Panel Home has no heading: the categories start right away
        grid = form_grid()
        grid.setHorizontalSpacing(SPACE["home_col"])
        grid.setVerticalSpacing(SPACE["home_row"])
        cats = [c for c in C.CATEGORIES if not c.hidden and self._category_applets(c.id)]
        half = (len(cats) + 1) // 2
        for i, c in enumerate(cats):
            title = Link(c.name, "link_title")
            title.clicked.connect(lambda c=c: self.navigate(c.id))
            cell = QWidget()
            cell.setLayout(self._icon_block(c.icon, title, (), c.tasks))
            grid.addWidget(cell, i % half, i // half, Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        v.addStretch(1)
        return w

    def _page_category(self, cat_id):
        # Vista: a category page is just its items; the pane's bullet and the address bar
        # say where you are
        c = self.cats[cat_id]
        w, v = self._page_frame()
        if c.subtitle:      # a hub such as Personalization has Vista's main instruction
            v.addWidget(text_label(c.subtitle, "instruction"))
        for a in self._category_applets(cat_id):
            v.addLayout(self._applet_block(a, show_desc=c.describe))
        v.addStretch(1)
        return w

    def _page_tasks(self, page):
        name, icon, text, tasks = C.PAGES[page]
        w, v = self._page_frame()
        self._page_header(v, icon, name, text)
        col = vbox(spacing="link_gap")
        if not self._task_links(tasks, col):
            col.addWidget(text_label("The tools for this aren\u2019t installed.", "secondary"))
        v.addLayout(col)
        v.addStretch(1)
        return w

    def _page_classic(self):
        """Vista's Classic View: every item as a 48 px icon on Explorer's grid, under the
        Name / Category column header (click to sort, again to reverse)."""
        from PyQt6.QtGui import QStandardItemModel
        from PyQt6.QtWidgets import QHeaderView
        w = QWidget()
        w.setObjectName("classic")
        v = vbox(w, "none")
        v.setSpacing(0)
        header = QHeaderView(Qt.Orientation.Horizontal)
        # a third, empty section runs the header to the window's edge, like Explorer's
        model = QStandardItemModel(0, 3, header)
        model.setHorizontalHeaderLabels(["Name", "Category", ""])
        header.setModel(model)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col, width in enumerate(SIZE["classic_columns"]):
            header.resizeSection(col, width)
        header.setStretchLastSection(True)
        header.setFixedHeight(header.sizeHint().height())
        v.addWidget(header)

        lst = QListWidget()
        lst.setObjectName("classiclist")
        lst.setViewMode(QListWidget.ViewMode.IconMode)
        lst.setResizeMode(QListWidget.ResizeMode.Adjust)
        lst.setMovement(QListWidget.Movement.Static)
        lst.setIconSize(QSize(ICON["large"], ICON["large"]))
        lst.setGridSize(QSize(*SIZE["classic_tile"]))
        lst.setWordWrap(True)
        lst.setTextElideMode(Qt.TextElideMode.ElideRight)
        lst.setUniformItemSizes(True)
        lst.setFrameShape(QFrame.Shape.NoFrame)
        cat_name = {c.id: c.name for c in C.CATEGORIES}
        seen = set()
        for a in self.applets:
            if a.id in C.CLASSIC_EXCLUDE or a.name in seen:
                continue
            seen.add(a.name)
            it = QListWidgetItem(QIcon.fromTheme(a.icon, QIcon.fromTheme("preferences-other")), a.name)
            it.setToolTip(f"{a.name}\n{a.description}" if a.description else a.name)
            it.setData(Qt.ItemDataRole.UserRole, (a.action, a.name))
            it.setData(Qt.ItemDataRole.UserRole + 1, (cat_name.get(a.category, ""), a.name.lower()))
            lst.addItem(it)

        def sort(col, order):
            items = [lst.takeItem(0) for _ in range(lst.count())]
            key = (lambda it: it.text().lower()) if col == 0 else (lambda it: it.data(Qt.ItemDataRole.UserRole + 1))
            for it in sorted(items, key=key, reverse=(order == Qt.SortOrder.DescendingOrder)):
                lst.addItem(it)
        def clicked(col, order):
            if col == 2:   # the filler section sorts nothing: keep the last real column
                header.blockSignals(True)
                header.setSortIndicator(clicked.col, clicked.order)
                header.blockSignals(False)
                return
            clicked.col, clicked.order = col, order
            sort(col, order)
        clicked.col, clicked.order = 0, Qt.SortOrder.AscendingOrder
        header.sortIndicatorChanged.connect(clicked)
        sort(0, Qt.SortOrder.AscendingOrder)
        lst.itemActivated.connect(lambda it: self.run(*it.data(Qt.ItemDataRole.UserRole)))
        v.addWidget(lst, 1)
        return w

    def _page_search(self, q):
        words = q.lower().split()
        w, v = self._page_frame()
        hits = []
        for a in self.applets:
            hay = " ".join([a.name, a.description, a.keywords] + [t.label for t in a.tasks]).lower()
            if all(word in hay for word in words):
                score = (0 if q.lower() in a.name.lower() else 1, a.name.lower())
                hits.append((score, a))
        names = set()
        found = 0
        for _, a in sorted(hits, key=lambda h: h[0]):
            if a.name in names:
                continue
            names.add(a.name)
            v.addLayout(self._applet_block(a, show_desc=True))
            found += 1
        if not found:
            v.addWidget(text_label(f"No results for \u201c{q}\u201d.", "subinstruction"))
            more = Link("Search all settings", "link")
            more.clicked.connect(lambda: self.run("app:systemsettings", "All Settings"))
            v.addWidget(more)
        v.addStretch(1)
        return w

    def _page_system(self):
        w, v = self._page_frame()
        v.setSpacing(SPACE["related"])
        v.addWidget(text_label("View basic information about your computer", "instruction"))
        gap(v)
        info = system_info()

        def rows(pairs):
            g = form_grid(label_column=True)
            for r, (k, val) in enumerate(pairs):
                g.addWidget(text_label(k + ":", "secondary"), r, 0, Qt.AlignmentFlag.AlignTop)
                g.addWidget(text_label(val, "value"), r, 1)
            g.setColumnStretch(1, 1)
            v.addLayout(g)

        top = hbox(spacing="section")
        ed = vbox(spacing="related")
        section(ed, "Edition")
        ed.addWidget(text_label(info["edition"], "emphasis"))
        for line in info["edition_lines"]:
            ed.addWidget(text_label(line, "secondary"))
        ed.addStretch(1)
        top.addLayout(ed, 1)
        top.addWidget(icon_label(info["logo"], "hero"), 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)
        section(v, "System")
        rows([("Processor", info["cpu"]), ("Installed memory (RAM)", info["ram"]),
              ("System type", info["type"]), ("Graphics", info["gpu"])])
        section(v, "Computer name")
        rows([("Computer name", info["host"]), ("Kernel", info["kernel"])])
        if self.env.available("native:sysprops"):
            change = Link("Change settings", "link")
            change.clicked.connect(lambda: self.run("native:sysprops", "System Properties"))
            v.addWidget(change, 0, Qt.AlignmentFlag.AlignRight)
        section(v, "See also")
        links = vbox(spacing="link_gap")
        self._task_links([C.Task("Device Manager", "app:kinfocenter"),
                          C.Task("Performance Information and Tools", "app:plasma-systemmonitor"),
                          C.Task(f"{distro.NAME} Update", "app:plasma-discover --mode Update")], links)
        v.addLayout(links)
        v.addStretch(1)
        return w


# ----------------------------------------------------------------------------- system info
def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _os_release():
    """/etc/os-release as a dict (the System page shows the installed OS, not VCP_OS_NAME)."""
    d = {}
    for line in _read("/etc/os-release").splitlines():
        k, _, val = line.partition("=")
        if k:
            d[k] = val.strip().strip('"')
    return d


def system_logo():
    """The system's logo for the System page: VCP_LOGO (icon name or picture file), the
    os-release LOGO icon, else a computer. Note: the Vista icon theme draws the generic
    "distributor-logo" as a Windows flag; distros that want their own logo set LOGO."""
    want = os.environ.get("VCP_LOGO")
    if want and (os.path.isabs(want) and os.path.exists(want) or not QIcon.fromTheme(want).isNull()):
        return want
    for name in (distro.logo_icon(), "distributor-logo"):
        if not QIcon.fromTheme(name).isNull():
            return name
    return "computer"


def system_info():
    """Everything the System page shows, as display strings."""
    osr = _os_release()
    edition = osr.get("PRETTY_NAME") or osr.get("NAME", "Linux")
    lines = []
    if os.environ.get("VCP_OS_NAME") and os.environ["VCP_OS_NAME"] != osr.get("NAME"):
        # a desktop that brands itself differently from the installed OS (e.g. a themed
        # session on stock Ubuntu): show its name, and what it runs on
        lines.append(f"Based on {edition}")
        edition = os.environ["VCP_OS_NAME"]
    if osr.get("ID") != "ubuntu" and "ubuntu" in osr.get("ID_LIKE", ""):
        base = _read("/etc/upstream-release/lsb-release")
        desc = next((l.split("=", 1)[1].strip('"') for l in base.splitlines()
                     if l.startswith("DISTRIB_DESCRIPTION=")), "")
        if desc:
            lines.append(f"Based on {desc}")
    try:
        plasma = subprocess.run(["plasmashell", "--version"], capture_output=True, text=True,
                                timeout=5).stdout.split()[-1]
        lines.append(f"KDE Plasma {plasma}")
    except (OSError, subprocess.SubprocessError, IndexError):
        pass

    cpuinfo = _read("/proc/cpuinfo")
    model = next((l.split(":", 1)[1].strip() for l in cpuinfo.splitlines()
                  if l.startswith("model name")), platform.processor() or "Unknown")
    cores = sum(1 for l in cpuinfo.splitlines() if l.startswith("processor"))
    cpu = f"{model}  ({cores} threads)" if cores else model

    mem_kb = next((int(l.split()[1]) for l in _read("/proc/meminfo").splitlines()
                   if l.startswith("MemTotal:")), 0)
    ram = f"{mem_kb / 1024 / 1024:.1f} GB usable" if mem_kb else "Unknown"

    bits = "64-bit" if sys.maxsize > 2 ** 32 else "32-bit"
    gpu = "Unknown"
    try:
        out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5).stdout
        gpus = [l.split(": ", 1)[1] for l in out.splitlines()
                if any(k in l for k in ("VGA compatible", "3D controller", "Display controller"))]
        if gpus:
            gpu = "\n".join(gpus)
    except (OSError, subprocess.SubprocessError):
        pass

    logo = system_logo()
    return {
        "edition": edition, "edition_lines": lines, "logo": logo,
        "cpu": cpu, "ram": ram, "type": f"{bits} Operating System ({platform.machine()})",
        "gpu": gpu, "host": socket.gethostname(), "kernel": f"Linux {platform.release()}",
    }


def ensure_icon_theme():
    """Without a platform theme (e.g. a bare X/Wayland session) Qt has no icon theme;
    use the user's KDE icon theme so icons still show."""
    if not QIcon.themeName():
        from ui import kread
        QIcon.setThemeName(kread("kdeglobals", "Icons", "Theme", "breeze") or "breeze")
        QIcon.setFallbackThemeName("breeze")


def main():
    app = QApplication(sys.argv)
    ensure_icon_theme()
    app.setApplicationName(distro.APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(distro.APP_ID)
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(args) >= 2 and args[0] == "--kcm":
        # from the systemsettings router: "Open settings" in tray popups, widgets, ...
        kcm, rest = args[1], args[2:]
        target = applets.applet_for_kcm(kcm)
        if target is None:
            try:
                os.execvp("kcmshell6", ["kcmshell6", kcm] + rest)      # KDE module, own window
            except OSError as e:
                print(f"Cannot open {kcm}: {e}", file=sys.stderr)
                return 1
        dlg = applets.open_applet(*target)
        dlg.finished.connect(app.quit)
        return app.exec()
    if len(args) >= 2 and args[0] == "--applet":
        aid, _, tab = args[1].partition("#")
        if aid in applets.REGISTRY and applets.available(aid):
            dlg = applets.open_applet(aid, tab or None)
            dlg.finished.connect(app.quit)
            return app.exec()
        args = []          # not available here: fall back to the Control Panel itself
    start = args[0] if args and not args[0].startswith("-") else "home"
    win = ControlPanel(start)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
