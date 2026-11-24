# SPDX-License-Identifier: GPL-3.0-or-later
"""Base class for native Control Panel applets: a Windows-style properties dialog with
tabs (or a single page), OK / Cancel / Apply, and an "Advanced settings" link to the
KDE module for everything the dialog doesn't cover.

Subclasses set ID/TITLE/ICON/ADVANCED and implement build(), load() and apply_changes().
apply_changes() returns a list of commands (argv lists) that are run in order without
blocking the window; commands needing an administrator show the UAC prompt."""
import os
import shlex

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QFrame, QMessageBox, QPushButton, QStyle, QTabWidget, QWidget

from style import SIZE, SPACE, margins

BUTTON_MIN_WIDTH = SIZE["button_min_width"]
from ui import Jobs, Link, gap, hbox, run, text_label, vbox


def kcm_argv(name):
    """kcmshell6 argv for a module, preferring the _x11 variant on X11."""
    ok, out, _ = run(["kcmshell6", "--list"])
    names = {l.split()[0] for l in out.splitlines() if l.strip() and not l.startswith("The following")}
    if os.environ.get("XDG_SESSION_TYPE") == "x11" and name + "_x11" in names:
        name += "_x11"
    return ["kcmshell6", name] if name in names else None


class AppletDialog(QDialog):
    """A native applet window; subclasses fill it in build() (see the module docstring)."""
    ID = ""
    TITLE = ""
    ICON = "preferences-other"
    ADVANCED = None          # "kcm:<name>" or "app:<cmd>" for the Advanced settings link
    REPLACES = []            # KDE modules this applet stands in for ("kcm_x" or "kcm_x#tab"):
                             # "Open settings" buttons in tray popups etc. open this applet
    TABBED = True
    BUTTONS = "ok_cancel_apply"   # or "close": task-style windows whose pages have their own buttons
    SIZE = "dialog"          # style.SIZE key: "dialog" (property sheet) or "dialog_wide"

    def __init__(self, tab=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.TITLE)
        self.setWindowIcon(QIcon.fromTheme(self.ICON, QIcon.fromTheme("preferences-system")))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._loading = True
        self._dirty = False
        self._jobs = None
        self.initial = tab           # requested tab / page (task-style applets use it too)

        self.resize(*SIZE[self.SIZE])
        if self.TABBED:
            # a Vista property sheet: tabs and buttons on the dialog face, 11 px margins
            v = vbox(self, "dialog", "unrelated")
            self.tabs = QTabWidget()
            v.addWidget(self.tabs, 1)
        else:
            # a Vista Control Panel page: white from edge to edge, the buttons in the grey
            # command area along the bottom
            import style
            v = vbox(self, "none", "none")
            self.page = QWidget()
            self.page.setObjectName("spokepage")
            self.page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            v.addWidget(self.page, 1)
            self.setStyleSheet(self.styleSheet() + f"""
                QWidget#spokepage {{ background: {style.color('page')}; }}
                QFrame#commandarea {{ background: {style.color('command_area')};
                                      border-top: 1px solid {style.color('command_line')}; }}""")
        self.build()

        bottom = hbox(spacing="unrelated")
        adv = self._advanced_argv()
        if adv:
            link = Link("Advanced settings…")
            link.clicked.connect(lambda: QProcess.startDetached(adv[0], adv[1:]))
            bottom.addWidget(link)
        bottom.addStretch(1)
        # Windows order (OK, Cancel, Apply) regardless of the widget style's own button layout
        self.buttons = QWidget()
        row = hbox(self.buttons, "none", "related")
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_apply = QPushButton("Apply")
        self.btn_ok.setDefault(True)
        self.btn_apply.setEnabled(False)
        shown = (self.btn_ok, self.btn_cancel, self.btn_apply)
        if self.BUTTONS == "close":
            self.btn_cancel.setText("Close")
            self.btn_cancel.setDefault(True)
            shown = (self.btn_cancel,)
        for b in shown:
            b.setMinimumWidth(max(b.sizeHint().width(), BUTTON_MIN_WIDTH))
            row.addWidget(b)
        self.btn_ok.clicked.connect(self._ok)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(lambda: self._apply(close=False))
        bottom.addWidget(self.buttons)
        if self.TABBED:
            v.addLayout(bottom)
        else:
            area = QFrame()
            area.setObjectName("commandarea")
            margins(bottom, "dialog")
            area.setLayout(bottom)
            v.addWidget(area)

        self.load()
        self._loading = False
        if tab is not None and self.TABBED:
            for i in range(self.tabs.count()):
                if self.tabs.widget(i).objectName() == tab:
                    self.tabs.setCurrentIndex(i)

    # --- to implement -------------------------------------------------------------
    def build(self):
        raise NotImplementedError

    def load(self):
        pass

    def apply_changes(self):
        """-> list of argv lists to run (may be empty), or None to abort."""
        return []

    def after_apply(self):
        """Called after all commands succeeded (e.g. reload values). Return False to keep
        the dialog open even after OK (e.g. the user reverted the change)."""

    def revert(self):
        """Called on Cancel (for applets that preview changes live)."""

    @classmethod
    def available(cls):
        return True

    # --- helpers --------------------------------------------------------------------
    def changed(self, *_):
        if self._loading:
            return
        self._dirty = True
        self.btn_apply.setEnabled(True)

    def add_tab(self, widget, title, name):
        widget.setObjectName(name)
        self.tabs.addTab(widget, title)

    # --- layout helpers: every applet page is built the same way --------------------
    def new_page(self, widget=None):
        """A page (tab content, or the single page) -> (widget, layout) with the
        schema's dialog page margins and related-control spacing."""
        w = widget if widget is not None else QWidget()
        # tab pages sit inside the tab frame with the dialog margin; a single page is a
        # Control Panel page: its content keeps Vista's page inset from the window edge
        return w, vbox(w, "dialog_page" if self.TABBED else "cp_page", "related")

    @staticmethod
    def heading(layout, instruction, explanation=None):
        """Main instruction (+ explanation), followed by the space before the content."""
        layout.addWidget(text_label(instruction, "instruction"))
        if explanation:
            layout.addWidget(text_label(explanation, "secondary"))
        gap(layout)

    @staticmethod
    def group(layout, title, icon=None, icon_size="large"):
        """A titled group (Vista property-sheet style): optional illustration on the left,
        content on the right. Returns the content layout."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QGroupBox
        from ui import icon_label
        box = QGroupBox(title)
        h = hbox(box, "dialog_page", "icon_gap")
        if icon:
            h.addWidget(icon_label(icon, icon_size), 0, Qt.AlignmentFlag.AlignTop)
        content = vbox(spacing="related")
        h.addLayout(content, 1)
        layout.addWidget(box)
        return content

    def option_indent(self):
        """Indent that lines text up with a radio button's / checkbox's label."""
        st = self.style()
        return (st.pixelMetric(QStyle.PixelMetric.PM_ExclusiveIndicatorWidth)
                + st.pixelMetric(QStyle.PixelMetric.PM_RadioButtonLabelSpacing))

    def _advanced_argv(self):
        if not self.ADVANCED:
            return None
        kind, _, arg = self.ADVANCED.partition(":")
        if kind == "kcm":
            return kcm_argv(arg)
        argv = shlex.split(arg)
        from shutil import which
        return argv if argv and which(argv[0]) else None

    def _ok(self):
        if self._dirty:
            self._apply(close=True)
        else:
            self.accept()

    def _apply(self, close):
        try:
            cmds = self.apply_changes()
        except OSError as e:
            # some applets write files directly (mimeapps.list, desktop links); an exception
            # escaping a Qt slot would abort the whole Control Panel
            QMessageBox.warning(self, self.TITLE, f"Some settings could not be changed.\n\n{e}")
            return
        if cmds is None:
            return
        self.buttons.setEnabled(False)
        self.setCursor(Qt.CursorShape.BusyCursor)
        self._jobs = Jobs(cmds, self)

        def done(ok, err):
            self.unsetCursor()
            self.buttons.setEnabled(True)
            if not ok:
                # polkit's "dismissed" / "not authorized", or pkexec's exit code 126
                if "dismissed" in err.lower() or "not authorized" in err.lower() or "126" in err:
                    err = "The change was cancelled or not authorized."
                QMessageBox.warning(self, self.TITLE, f"Some settings could not be changed.\n\n{err}")
                return
            self._dirty = False
            self.btn_apply.setEnabled(False)
            keep = self.after_apply()
            if close and keep is not False:      # after_apply() may return False (e.g. reverted)
                self.accept()

        self._jobs.finished.connect(done)
        self._jobs.start()

    def reject(self):
        self.revert()
        super().reject()


class TaskWindow(AppletDialog):
    """A Control Panel-style applet window (User Accounts, Programs and Features, Network
    and Sharing Center): blue task pane on the left, white page on the right, Close only.
    Subclasses call self.task_frame() in build() and fill self.pane_layout /
    self.content_layout (or rebuild them per page with show_page())."""
    TABBED = False
    BUTTONS = "close"
    SIZE = "dialog_wide"
    EXTRA_STYLE = ""

    def task_frame(self):
        """Build the task pane + white content page inside self.page."""
        import style
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QFrame
        self.setStyleSheet(style.stylesheet() + f"""
            QFrame#tile {{ background: {style.color('page')}; border: 1px solid {style.color('rule')};
                           border-radius: 6px; }}
            QFrame#tile:hover {{ border-color: {style.color('select_hover')}; }}
            QFrame#details {{ background: {style.color('canvas')}; border: 1px solid {style.color('rule')};
                              border-radius: 4px; }}""" + self.EXTRA_STYLE)
        from ui import TaskPane
        root = hbox(self.page, "none", "none")        # Vista: the pane meets the page directly
        self.pane = TaskPane(width=SIZE["dialog_pane_width"])
        self.pane_layout = self.pane.layout_
        root.addWidget(self.pane)
        self.content = QWidget()
        self.content.setObjectName("page")
        self.content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.content_layout = vbox(self.content, "cp_page", "related")
        root.addWidget(self.content, 1)

    def pane_heading(self, text):
        self.pane.add_heading(text)

    def pane_link(self, text, fn, current=False):
        link = Link(text, "pane_current" if current else "pane_link")
        link.clicked.connect(fn)
        return self.pane.add_link(link, current)

    @staticmethod
    def launch(argv):
        """Start a program detached if it is installed -> True if started."""
        from shutil import which
        from PyQt6.QtCore import QProcess
        if argv and which(argv[0]):
            QProcess.startDetached(argv[0], argv[1:])
            return True
        return False
