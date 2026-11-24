# SPDX-License-Identifier: GPL-3.0-or-later
"""User Accounts (Windows Vista style) on AccountsService, the backend KDE's users module
uses (plasma-workspace kcms/users): SetRealName, SetIconFile (picture scaled to 256 px PNG),
SetAccountType (0 standard, 1 administrator), SetPassword (SHA-512 crypt hash + hint),
CreateUser, DeleteUser. Calls go through busctl with interactive authorization, so the
UAC prompt appears when an administrator is needed. Passwords are hashed with
`openssl passwd -6` reading the password on stdin (never on a command line)."""
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QFileDialog, QFrame, QLabel, QLineEdit, QListWidgetItem,
                             QMessageBox, QPushButton, QRadioButton, QSizePolicy, QWidget)

import style
from applets.base import TaskWindow
from style import SIZE, SPACE
from ui import EvenGrid, Jobs, Link, clear_layout, form_grid, gap, hbox, run, text_label, vbox
import distro

ACC, ACC_PATH, USER_IF = "org.freedesktop.Accounts", "/org/freedesktop/Accounts", "org.freedesktop.Accounts.User"
TILE = 64
AVATAR_DIRS = ["/usr/share/plasma/avatars", "/usr/local/share/plasma/avatars"]
STANDARD_TEXT = ("Standard account users can use most software and change system settings that do not "
                 "affect other users or the security of the computer.")
ADMIN_TEXT = ("Administrators have complete access to the computer and can make any desired changes. "
              f"{distro.NAME} asks for an administrator’s password before making changes that affect "
              "everyone.")
LOGON_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
FALLBACK_PICTURE = "/usr/share/vistathemeplasma/fallback-picture.png"   # Vista's default user picture


# ----------------------------------------------------------------------------- backend
@dataclass
class User:
    path: str
    uid: int
    name: str
    real: str
    admin: bool
    icon: str
    has_password: bool

    @property
    def display(self):
        return self.real or self.name


def _busctl(*args):
    """A quick, non-interactive AccountsService query -> the reply's data, or None."""
    ok, out, _ = run(["busctl", "--system", "--json=short", *args])
    try:
        return json.loads(out)["data"] if ok and out.strip() else None
    except (ValueError, KeyError):
        return None


def load_user(path):
    """User at an AccountsService object path, or None for system accounts."""
    def prop(name):
        return _busctl("get-property", ACC, path, USER_IF, name)
    if prop("SystemAccount"):
        return None
    return User(path=path, uid=int(prop("Uid") or 0), name=prop("UserName") or "", real=prop("RealName") or "",
                admin=prop("AccountType") == 1, icon=prop("IconFile") or "",
                has_password=prop("PasswordMode") == 0 and not prop("Locked"))


def list_users():
    """-> ([User], my object path): the human accounts, the current user first."""
    paths = (_busctl("call", ACC, ACC_PATH, ACC, "ListCachedUsers") or [[]])[0]
    me = (_busctl("call", ACC, ACC_PATH, ACC, "FindUserByName", "s", os.environ.get("USER", "")) or [None])[0]
    if me and me not in paths:
        paths.append(me)
    users = [u for u in (load_user(p) for p in paths) if u]
    users.sort(key=lambda u: (u.path != me, u.display.lower()))
    return users, me


def call(path, method, sig, *args):
    """argv calling a User method with interactive authorization (shows the UAC prompt)."""
    # "--": busctl would take an argument such as a real name or hint starting with "-"
    # for one of its own options
    return ["busctl", "--system", "--allow-interactive-authorization=yes", "call", "--", ACC, path,
            USER_IF, method, sig, *[str(a) for a in args]]


def hash_password(plain):
    """SHA-512 crypt hash for SetPassword, or None (e.g. openssl not installed). The password
    goes to openssl on stdin, never on a command line."""
    try:
        p = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=plain + "\n",
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def avatar_files():
    """The stock account pictures (Plasma's avatars and VistaThemePlasma's)."""
    files = []
    for d in AVATAR_DIRS + ["/usr/share/vistathemeplasma"]:
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith((".png", ".jpg", ".jpeg")) and "reflection" not in f:
                    files.append(os.path.join(d, f))
    return files


def picture(path, size=TILE):
    """A rounded square account picture (falls back to the generic user icon)."""
    img = QImage(path) if path and os.path.isfile(path) else QImage()
    if img.isNull():
        img = QImage(FALLBACK_PICTURE) if os.path.isfile(FALLBACK_PICTURE) else QImage()
    if img.isNull():
        return QIcon.fromTheme("user-identity", QIcon.fromTheme("system-users")).pixmap(QSize(size, size))
    img = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                     Qt.TransformationMode.SmoothTransformation)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, size / 10, size / 10)
    p.setClipPath(clip)
    p.drawImage(0, 0, img, (img.width() - size) // 2, (img.height() - size) // 2)
    p.end()
    return pm


# ----------------------------------------------------------------------------- widgets
class AccountTile(QFrame):
    """Picture, name, account type and password state - Vista's account tile."""

    def __init__(self, user, size=TILE, on_click=None):
        super().__init__()
        self.setObjectName("tile")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)   # compact everywhere
        h = hbox(self, "dialog_page", "icon_gap")
        pic = QLabel()
        pic.setPixmap(picture(user.icon, size))
        h.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        col = vbox(spacing="link_gap")
        col.addWidget(text_label(user.display, "emphasis"))
        col.addWidget(text_label("Administrator" if user.admin else "Standard user", "secondary"))
        col.addWidget(text_label("Password protected" if user.has_password else "No password", "secondary"))
        col.addStretch(1)
        h.addLayout(col, 1)
        self._on_click = on_click
        if on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if self._on_click and e.button() == Qt.MouseButton.LeftButton:
            self._on_click()


# ----------------------------------------------------------------------------- dialog
class UserAccounts(TaskWindow):
    ID = "useraccounts"
    TITLE = "User Accounts"
    ICON = "system-users"
    ADVANCED = "kcm:kcm_users"
    REPLACES = ["kcm_users"]
    def build(self):
        self.resize(780, 560)
        self.task_frame()
        self._jobs = None

    def load(self):
        self.users, self.me = list_users()
        self.target = next((u for u in self.users if u.path == self.me), self.users[0] if self.users else None)
        # every page but home needs an account (none without AccountsService)
        start = (self.initial or "home") if self.target else "home"
        self.show_page(start if hasattr(self, f"_page_{start}") else "home")

    # --- frame --------------------------------------------------------------------------
    @property
    def is_me(self):
        return self.target and self.target.path == self.me

    def _admins(self):
        return [u for u in self.users if u.admin]

    def show_page(self, name):
        clear_layout(self.content_layout)
        clear_layout(self.pane_layout)
        getattr(self, f"_page_{name}")()
        self._fill_pane(name)

    def _fill_pane(self, page):
        self.pane_heading("Tasks")
        if page != "home":
            self.pane_link("User Accounts home", self._go_me)
        if page != "manage":
            self.pane_link("Manage another account", lambda: self.show_page("manage"))
        from shutil import which
        if which("kwalletmanager5"):
            self.pane_link("Manage your saved passwords", lambda: self.launch(["kwalletmanager5"]))
        self.pane_layout.addStretch(1)
        self.pane_heading("See also")
        self.pane_link("Logon screen", lambda: self.launch(["kcmshell6", "kcm_sddm"]))

    def _go_me(self):
        self.target = next((u for u in self.users if u.path == self.me), self.target)
        self.show_page("home")

    def _actions(self, primary, on_primary, extra=(), stretch=True):
        """Bottom-right action buttons of a task page: [primary] [extra...] [Cancel].
        stretch=False when the page itself has a part that should take the free space."""
        gap(self.content_layout, "section")
        row = hbox(spacing="related")
        row.addStretch(1)
        b = QPushButton(primary)
        b.setDefault(True)
        b.clicked.connect(on_primary)
        row.addWidget(b)
        for label, fn in extra:
            x = QPushButton(label)
            x.clicked.connect(fn)
            row.addWidget(x)
        c = QPushButton("Cancel")
        c.clicked.connect(lambda: self.show_page("home"))
        row.addWidget(c)
        self.content_layout.addLayout(row)
        if stretch:
            self.content_layout.addStretch(1)
        return b

    def _run(self, cmds, then="home", ok_msg=None):
        """Run AccountsService calls in the background; on success reload the accounts and
        go to page `then` (or call it)."""
        self.setCursor(Qt.CursorShape.BusyCursor)
        self._jobs = Jobs(cmds, self)

        def done(ok, err):
            self.unsetCursor()
            if not ok:
                if "Interactive authentication required" in err or "not authorized" in err.lower():
                    err = "The change was cancelled or not authorized."
                QMessageBox.warning(self, self.TITLE, f"The change could not be made.\n\n{err}")
                return
            path = self.target.path if self.target else None
            self.users, self.me = list_users()
            self.target = next((u for u in self.users if u.path == path), None) or \
                next((u for u in self.users if u.path == self.me), None)
            if callable(then):
                then()
            else:
                self.show_page(then)
        self._jobs.finished.connect(done)
        self._jobs.start()

    # --- pages ----------------------------------------------------------------------------
    def _page_home(self):
        v, u = self.content_layout, self.target
        if not u:
            v.addWidget(text_label("No user accounts were found.", "secondary"))
            return
        self.heading(v, "Make changes to your user account" if self.is_me
                     else f"Make changes to {u.display}’s account")
        row = hbox(spacing="section")
        links = vbox(spacing="related")
        you = "your" if self.is_me else "the"
        for text, page in ((f"Change {you} password" if u.has_password else "Create a password", "password"),
                           (f"Change {you} picture", "picture"),
                           (f"Change {you} account name", "name"),
                           (f"Change {you} account type", "type")):
            l = Link(text, "link")
            l.clicked.connect(lambda p=page: self.show_page(p))
            links.addWidget(l)
        if not self.is_me:
            l = Link("Delete the account", "link")
            l.clicked.connect(lambda: self.show_page("delete"))
            links.addWidget(l)
        links.addStretch(1)
        row.addLayout(links, 1)
        row.addWidget(AccountTile(u), 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(row)
        v.addStretch(1)

    def _page_name(self):
        v, u = self.content_layout, self.target
        self.heading(v, "Type a new account name" if self.is_me else f"Type a new account name for {u.display}",
                     "This name will appear on the logon screen and on the Start menu.")
        v.addWidget(AccountTile(u))
        gap(v)
        self._name_edit = QLineEdit(u.real or u.name)
        self._name_edit.setPlaceholderText("New account name")
        self._name_edit.selectAll()
        v.addWidget(self._name_edit)
        btn = self._actions("Change Name", self._do_name)
        self._name_edit.textChanged.connect(lambda t: btn.setEnabled(bool(t.strip()) and t.strip() != u.display))
        btn.setEnabled(False)
        self._name_edit.setFocus()

    def _do_name(self):
        self._run([call(self.target.path, "SetRealName", "s", self._name_edit.text().strip())])

    def _page_password(self):
        v, u = self.content_layout, self.target
        verb = "Change" if u.has_password else "Create"
        self.heading(v, f"{verb} {'your' if self.is_me else u.display + chr(0x2019) + 's'} password",
                     "If your password contains capital letters, they must be typed the same way every "
                     "time you log on.")
        v.addWidget(AccountTile(u))
        gap(v)
        g = form_grid()
        self._pw1, self._pw2, self._hint = QLineEdit(), QLineEdit(), QLineEdit()
        for e in (self._pw1, self._pw2):
            e.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw1.setPlaceholderText("New password")
        self._pw2.setPlaceholderText("Confirm new password")
        self._hint.setPlaceholderText("Type a password hint")
        g.addWidget(self._pw1, 0, 0)
        g.addWidget(self._pw2, 1, 0)
        g.addWidget(self._hint, 2, 0)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        self._pw_msg = text_label("The password hint will be visible to everyone who uses this computer.",
                                  "secondary")
        v.addWidget(self._pw_msg)
        btn = self._actions(f"{verb} password", self._do_password)
        btn.setEnabled(False)

        def check():
            a, b = self._pw1.text(), self._pw2.text()
            ok = bool(a) and a == b
            btn.setEnabled(ok)
            if b and a != b:
                self._pw_msg.setText("The passwords you typed do not match.")
                self._pw_msg.setStyleSheet(f"color: {style.color('error')}; background: transparent;")
            else:
                self._pw_msg.setText("The password hint will be visible to everyone who uses this computer.")
                self._pw_msg.setStyleSheet(f"color: {style.color('secondary')}; background: transparent;")
        self._pw1.textChanged.connect(check)
        self._pw2.textChanged.connect(check)
        self._pw1.setFocus()

    def _do_password(self):
        hashed = hash_password(self._pw1.text())
        self._pw1.clear()
        self._pw2.clear()
        if not hashed:
            QMessageBox.warning(self, self.TITLE, "The password could not be prepared.")
            return
        self._run([call(self.target.path, "SetPassword", "ss", hashed, self._hint.text())])

    def _page_picture(self):
        v, u = self.content_layout, self.target
        self.heading(v, "Choose a new picture for your account" if self.is_me
                     else f"Choose a new picture for {u.display}’s account",
                     "Your picture appears on the logon screen and on the Start menu.")
        self._pic_grid = EvenGrid(QSize(TILE, TILE), (TILE + SPACE["section"], TILE + SPACE["section"]))
        for f in avatar_files():
            it = QListWidgetItem(QIcon(picture(f, TILE)), "")
            it.setData(Qt.ItemDataRole.UserRole, f)
            it.setToolTip(os.path.splitext(os.path.basename(f))[0])
            self._pic_grid.addItem(it)
        row = hbox(spacing="section")
        row.addWidget(AccountTile(u), 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self._pic_grid, 1)
        v.addLayout(row, 1)
        browse = Link("Browse for more pictures…", "link")
        browse.clicked.connect(self._browse_picture)
        v.addWidget(browse)
        self._pic_btn = self._actions("Change Picture", self._do_picture, stretch=False)
        self._pic_btn.setEnabled(False)
        self._pic_grid.currentItemChanged.connect(lambda *_: self._pic_btn.setEnabled(True))
        self._pic_file = None

    def _browse_picture(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose a picture", os.path.expanduser("~/Pictures"),
                                           "Pictures (*.png *.jpg *.jpeg *.bmp *.webp)")
        if f:
            it = QListWidgetItem(QIcon(picture(f, TILE)), "")
            it.setData(Qt.ItemDataRole.UserRole, f)
            self._pic_grid.addItem(it)
            self._pic_grid.setCurrentItem(it)

    def _do_picture(self):
        it = self._pic_grid.currentItem()
        if not it:
            return
        img = QImage(it.data(Qt.ItemDataRole.UserRole))
        if img.isNull():
            QMessageBox.warning(self, self.TITLE, "This picture could not be opened.")
            return
        img = img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        # in /tmp, not the home folder: accounts-daemon must be able to read it
        fd, tmp = tempfile.mkstemp(prefix="vcp-picture-", suffix=".png", dir="/tmp")
        os.close(fd)
        img.save(tmp, "PNG")
        os.chmod(tmp, 0o644)          # accounts-daemon reads it as root and copies it
        self._run([call(self.target.path, "SetIconFile", "s", tmp)])
        # remove the copy whether or not the change went through (e.g. a cancelled prompt)
        self._jobs.finished.connect(lambda *_: os.path.exists(tmp) and os.remove(tmp))

    def _page_type(self):
        v, u = self.content_layout, self.target
        self.heading(v, "Choose a new account type" if self.is_me
                     else f"Choose a new account type for {u.display}")
        v.addWidget(AccountTile(u))
        gap(v)
        grp = QButtonGroup(self)
        self._std, self._adm = QRadioButton("Standard user"), QRadioButton("Administrator")
        indent = self.option_indent()
        for rb, text in ((self._std, STANDARD_TEXT), (self._adm, ADMIN_TEXT)):
            rb.setFont(text_label("", "strong").font())
            grp.addButton(rb)
            v.addWidget(rb)
            d = text_label(text, "secondary")
            d.setContentsMargins(indent, 0, 0, SPACE["link_gap"])
            v.addWidget(d)
        (self._adm if u.admin else self._std).setChecked(True)
        last_admin = u.admin and len(self._admins()) <= 1
        if last_admin:
            self._std.setEnabled(False)
            v.addWidget(text_label("This is the only administrator account. Create another administrator "
                                   "before changing this one to a standard user.", "secondary"))
        btn = self._actions("Change Account Type", self._do_type)
        btn.setEnabled(False)
        for rb in (self._std, self._adm):
            rb.toggled.connect(lambda *_: btn.setEnabled(self._adm.isChecked() != u.admin))

    def _do_type(self):
        self._run([call(self.target.path, "SetAccountType", "i", 1 if self._adm.isChecked() else 0)])

    def _page_manage(self):
        v = self.content_layout
        self.heading(v, "Choose the account you would like to change")
        grid = form_grid()
        grid.setHorizontalSpacing(SPACE["section"])
        grid.setVerticalSpacing(SPACE["section"])
        for i, u in enumerate(self.users):
            tile = AccountTile(u, on_click=lambda u=u: self._open_user(u))
            grid.addWidget(tile, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        gap(v)
        create = Link("Create a new account", "link")
        create.clicked.connect(lambda: self.show_page("create"))
        v.addWidget(create)
        v.addStretch(1)

    def _open_user(self, u):
        self.target = u
        self.show_page("home")

    def _page_create(self):
        v = self.content_layout
        self.heading(v, "Name the account and choose an account type",
                     "This name will appear on the logon screen and on the Start menu.")
        g = form_grid(label_column=False)
        self._new_real, self._new_logon = QLineEdit(), QLineEdit()
        self._new_pw1, self._new_pw2 = QLineEdit(), QLineEdit()
        self._new_real.setPlaceholderText("New account name")
        self._new_logon.setPlaceholderText("logon name")
        for e, ph in ((self._new_pw1, "Password"), (self._new_pw2, "Confirm password")):
            e.setEchoMode(QLineEdit.EchoMode.Password)
            e.setPlaceholderText(ph)
        g.addWidget(QLabel("Name:"), 0, 0)
        g.addWidget(self._new_real, 0, 1)
        g.addWidget(QLabel("Logon name:"), 1, 0)
        g.addWidget(self._new_logon, 1, 1)
        g.addWidget(QLabel("Password:"), 2, 0)
        g.addWidget(self._new_pw1, 2, 1)
        g.addWidget(QLabel("Confirm:"), 3, 0)
        g.addWidget(self._new_pw2, 3, 1)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        self._create_msg = text_label("", "error")
        self._create_msg.setVisible(False)
        v.addWidget(self._create_msg)
        gap(v)
        grp = QButtonGroup(self)
        self._new_std, self._new_adm = QRadioButton("Standard user"), QRadioButton("Administrator")
        indent = self.option_indent()
        for rb, text in ((self._new_std, STANDARD_TEXT), (self._new_adm, ADMIN_TEXT)):
            rb.setFont(text_label("", "strong").font())
            grp.addButton(rb)
            v.addWidget(rb)
            d = text_label(text, "secondary")
            d.setContentsMargins(indent, 0, 0, SPACE["link_gap"])
            v.addWidget(d)
        self._new_std.setChecked(True)
        btn = self._actions("Create Account", self._do_create)
        btn.setEnabled(False)
        self._logon_edited = False
        existing = {u.name for u in self.users}

        def derive(text):
            if not self._logon_edited:
                logon = re.sub(r"[^a-z0-9_-]", "", text.lower().replace(" ", ""))[:32]
                if logon and not logon[0].isalpha():
                    logon = "u" + logon
                self._new_logon.blockSignals(True)
                self._new_logon.setText(logon)
                self._new_logon.blockSignals(False)
            check()

        def check():
            logon, a, b = self._new_logon.text(), self._new_pw1.text(), self._new_pw2.text()
            problem = ""
            if logon and not LOGON_RE.match(logon):
                problem = "The logon name may use lowercase letters, numbers, - and _."
            elif logon in existing:
                problem = "An account with this logon name already exists."
            elif b and a != b:
                problem = "The passwords you typed do not match."
            self._create_msg.setText(problem)
            self._create_msg.setVisible(bool(problem))
            self._create_msg.setStyleSheet(f"color: {style.color('error')}; background: transparent;")
            btn.setEnabled(bool(self._new_real.text().strip() and logon and a and a == b and not problem))
        self._new_real.textChanged.connect(derive)
        self._new_logon.textEdited.connect(lambda _: (setattr(self, "_logon_edited", True), check()))
        self._new_pw1.textChanged.connect(lambda _: check())
        self._new_pw2.textChanged.connect(lambda _: check())
        self._new_real.setFocus()

    def _do_create(self):
        logon, real = self._new_logon.text(), self._new_real.text().strip()
        hashed = hash_password(self._new_pw1.text())
        self._new_pw1.clear()
        self._new_pw2.clear()
        if not hashed:
            QMessageBox.warning(self, self.TITLE, "The password could not be prepared.")
            return
        create = ["busctl", "--system", "--allow-interactive-authorization=yes", "call", "--", ACC, ACC_PATH, ACC,
                  "CreateUser", "ssi", logon, real, "1" if self._new_adm.isChecked() else "0"]

        # CreateUser can't set a password: look the new account up, then SetPassword on it
        def set_password():
            path = (_busctl("call", ACC, ACC_PATH, ACC, "FindUserByName", "s", logon) or [None])[0]
            if not path:
                self.show_page("manage")
                return
            self.target = load_user(path)
            self._run([call(path, "SetPassword", "ss", hashed, "")], then="manage")
        self._run([create], then=set_password)

    def _page_delete(self):
        v, u = self.content_layout, self.target
        self.heading(v, f"Do you want to keep {u.display}’s files?",
                     f"{distro.NAME} can keep {u.display}’s home folder (documents, pictures, music and "
                     "settings) in /home. The account itself is removed either way.")
        v.addWidget(AccountTile(u))
        self._actions("Delete Files", lambda: self._do_delete(True),
                      extra=[("Keep Files", lambda: self._do_delete(False))])

    def _do_delete(self, remove_files):
        u = self.target
        if remove_files and QMessageBox.question(
                self, self.TITLE, f"Are you sure you want to delete {u.display}’s account and all of "
                                  "its files?") != QMessageBox.StandardButton.Yes:
            return
        self.target = next((x for x in self.users if x.path == self.me), None)
        self._run([["busctl", "--system", "--allow-interactive-authorization=yes", "call", "--", ACC, ACC_PATH, ACC,
                    "DeleteUser", "xb", str(u.uid), "true" if remove_files else "false"]], then="manage")
