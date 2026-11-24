# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal asynchronous PackageKit client (the backend Discover uses), over QtDBus.

One Transaction object = one PackageKit transaction. Methods return immediately; results
arrive through Qt signals, so the window keeps painting while PackageKit works or waits
for the UAC (polkit) prompt.

PackageKit bitfields are 1 << enum value (packagekit-glib2 pk-enum.h):
  filter INSTALLED = 1 << 2, NOT_INSTALLED = 1 << 3; transaction flag SIMULATE = 1 << 2,
  ONLY_TRUSTED = 1 << 1;
  exit SUCCESS = 1."""
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import (QDBusConnection, QDBusInterface, QDBusMessage, QDBusPendingCallWatcher,
                          QDBusPendingReply)

SERVICE, ROOT, ROOT_IF = "org.freedesktop.PackageKit", "/org/freedesktop/PackageKit", "org.freedesktop.PackageKit"
TX_IF = "org.freedesktop.PackageKit.Transaction"
FILTER_INSTALLED, FILTER_NOT_INSTALLED = 1 << 2, 1 << 3
FLAG_NONE, FLAG_ONLY_TRUSTED, FLAG_SIMULATE = 0, 1 << 1, 1 << 2
EXIT_SUCCESS = 1


def available():
    """True if the PackageKit daemon is on the system bus (or can be activated)."""
    iface = QDBusInterface(SERVICE, ROOT, ROOT_IF, QDBusConnection.systemBus())
    return iface.isValid()


def package_name(package_id):
    """'name;version;arch;repo' -> name"""
    return package_id.split(";", 1)[0]


class Transaction(QObject):
    """One PackageKit transaction: call one operation, then wait for finished()."""
    package = pyqtSignal(int, str, str)       # info, package_id, summary
    finished = pyqtSignal(bool, str)          # success, error text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bus = QDBusConnection.systemBus()
        self.path = None
        self._error = ""
        self._watchers = []

    def _start(self, method, *args, interactive=False):
        root = QDBusInterface(SERVICE, ROOT, ROOT_IF, self.bus)
        reply = root.call("CreateTransaction")
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            self.finished.emit(False, reply.errorMessage())
            return
        arg = reply.arguments()[0]
        self.path = arg.path() if hasattr(arg, "path") else str(arg)     # PyQt may hand back a str
        for sig, slot in (("Package", self._on_package), ("Finished", self._on_finished),
                          ("ErrorCode", self._on_error)):
            self.bus.connect(SERVICE, self.path, TX_IF, sig, slot)
        if interactive:
            hints = QDBusMessage.createMethodCall(SERVICE, self.path, TX_IF, "SetHints")
            hints.setArguments([["interactive=true"]])
            self.bus.call(hints)
        msg = QDBusMessage.createMethodCall(SERVICE, self.path, TX_IF, method)
        msg.setArguments(list(args))
        msg.setInteractiveAuthorizationAllowed(interactive)
        w = QDBusPendingCallWatcher(self.bus.asyncCall(msg, 10 * 60 * 1000), self)
        w.finished.connect(self._on_call_done)
        self._watchers.append(w)

    def _on_call_done(self, w):
        # the method call itself failed (e.g. a bad package id); otherwise the outcome
        # arrives later through the transaction's Finished signal
        reply = QDBusPendingReply(w)
        if reply.isError():
            self.finished.emit(False, reply.error().message())

    @pyqtSlot(QDBusMessage)
    def _on_package(self, msg):
        info, pid, summary = msg.arguments()
        self.package.emit(int(info), pid, summary)

    @pyqtSlot(QDBusMessage)
    def _on_error(self, msg):
        _code, details = msg.arguments()
        self._error = details

    @pyqtSlot(QDBusMessage)
    def _on_finished(self, msg):
        exit_code = int(msg.arguments()[0])
        self.finished.emit(exit_code == EXIT_SUCCESS, self._error or ("" if exit_code == EXIT_SUCCESS
                                                                       else "The operation was cancelled."))

    # --- operations ---------------------------------------------------------------------
    def resolve_installed(self, names):
        self._start("Resolve", _u64(FILTER_INSTALLED), _strlist(names))

    def resolve_available(self, names):
        """Packages that can be installed (not installed yet)."""
        self._start("Resolve", _u64(FILTER_NOT_INSTALLED), _strlist(names))

    def install(self, package_ids):
        self._start("InstallPackages", _u64(FLAG_ONLY_TRUSTED), _strlist(package_ids), interactive=True)

    def remove(self, package_ids, simulate=False):
        flags = FLAG_SIMULATE if simulate else FLAG_NONE
        self._start("RemovePackages", _u64(flags), _strlist(package_ids), True, False,
                    interactive=not simulate)


# PackageKit's methods need exact D-Bus types (uint64 "t", string array "as"); plain
# Python values would be marshalled as other types and rejected.
def _u64(v):
    """v as a D-Bus uint64 ("t")."""
    from PyQt6.QtCore import QMetaType, QVariant
    var = QVariant(v)
    var.convert(QMetaType(QMetaType.Type.ULongLong.value))
    return var


def _strlist(items):
    """items as a D-Bus string array ("as")."""
    from PyQt6.QtCore import QMetaType, QVariant
    var = QVariant(list(items))
    var.convert(QMetaType(QMetaType.Type.QStringList.value))
    return var
