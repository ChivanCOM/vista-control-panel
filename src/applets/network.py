# SPDX-License-Identifier: GPL-3.0-or-later
"""Network and Sharing Center (Windows Vista style) on NetworkManager (nmcli).

Network map (this computer - network - Internet), the active connections with access
level and signal, Sharing and Discovery status, Manage network connections, Diagnose and
repair, and Windows' connection Status window (live activity counters, Details).
nmcli's terse output escapes ':' inside values as '\\:' (IPv6, MAC); see split_terse()."""
import html
import os
import re
import socket
import time

from PyQt6.QtCore import QPointF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen
from PyQt6.QtWidgets import (QDialog, QFrame, QLabel, QMessageBox, QPushButton, QTreeWidget,
                             QTreeWidgetItem, QWidget)

import style
from applets.base import TaskWindow
from style import COLOR, ICON, SIZE, SPACE
from ui import Jobs, Link, clear_layout, form_grid, gap, hbox, hrule, icon_label, run, section, text_label, vbox
import distro

SIGNAL_WORDS = [(80, "Excellent"), (60, "Very good"), (40, "Good"), (20, "Low"), (0, "Very low")]
ACCESS = {"full": "Local and Internet", "limited": "Local only", "portal": "Local only (sign-in page)",
          "none": "No network access", "unknown": "Unknown"}


# ----------------------------------------------------------------------------- nmcli
def split_terse(line):
    """Split an `nmcli -t` line on unescaped ':' and unescape '\\:' and '\\\\'."""
    out, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def nm(*args):
    """`nmcli -t <args>` -> rows of fields ([] if nmcli fails)."""
    ok, out, _ = run(["nmcli", "-t", *args])
    return [split_terse(l) for l in out.splitlines()] if ok else []


def connectivity():
    rows = nm("networking", "connectivity")
    return rows[0][0] if rows else "unknown"


def devices():
    """[{device, type, state, connection}] for real network adapters."""
    res = []
    for row in nm("-f", "DEVICE,TYPE,STATE,CONNECTION", "device"):
        if len(row) >= 4 and row[1] in ("wifi", "ethernet", "gsm", "bt", "wireguard", "vpn", "tun"):
            res.append({"device": row[0], "type": row[1], "state": row[2], "connection": row[3]})
    return res


def device_details(dev):
    """`nmcli device show` -> {"IP4.ADDRESS": [...], ...}; indexed keys ("IP4.DNS[2]") are
    collected into one list. These multi-line rows don't escape ':' in values, hence the join."""
    d = {}
    for row in nm("-f", "GENERAL,CAPABILITIES,IP4,IP6", "device", "show", dev):   # explicit: SPEED isn't in the default set
        if len(row) >= 2:
            k = re.sub(r"\[\d+\]$", "", row[0])
            d.setdefault(k, []).append(":".join(row[1:]))
    return d


def wifi_signal(ssid):
    for row in nm("-f", "SSID,SIGNAL", "device", "wifi", "list", "--rescan", "no"):
        if len(row) >= 2 and row[0] == ssid and row[1].isdigit():
            return int(row[1])
    return None


def connection_ssid(name):
    # -e no: -g would escape ':' and backslashes in the SSID; "id": a profile named like an
    # nmcli keyword ("uuid", "path"...) is still taken as a name
    ok, out, _ = run(["nmcli", "-e", "no", "-g", "802-11-wireless.ssid", "connection", "show", "id", name])
    return out.strip() if ok else name


def activated_since(name):
    for row in nm("-f", "NAME,TIMESTAMP", "connection", "show", "--active"):
        if len(row) >= 2 and row[0] == name and row[1].isdigit():
            return int(row[1])
    return None


def signal_word(pct):
    return next(w for limit, w in SIGNAL_WORDS if (pct or 0) >= limit)


def kind_label(t):
    return {"wifi": "Wireless Network Connection", "ethernet": "Local Area Connection",
            "gsm": "Mobile Broadband Connection", "bt": "Bluetooth Network Connection"}.get(t, "Network Connection")


def kind_icon(t):
    return "network-wireless" if t == "wifi" else ("network-wired" if t == "ethernet" else "network-workgroup")


def human_bytes(n):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024


def counters(dev):
    """-> (bytes sent, bytes received) of an interface since it came up."""
    def read(name):
        try:
            return int(open(f"/sys/class/net/{dev}/statistics/{name}").read())
        except (OSError, ValueError):
            return 0
    return read("tx_bytes"), read("rx_bytes")


def service_active(name):
    return run(["systemctl", "is-active", "--quiet", name])[0]


# ----------------------------------------------------------------------------- map
class NetworkMap(QWidget):
    """This computer --- network --- Internet, with a red cross where the path is broken."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(ICON["large"] + 3 * SPACE["section"] + 2 * self.fontMetrics().height())
        self.nodes = []          # (icon, label)
        self.links_ok = []       # bool per link

    def set_state(self, nodes, links_ok):
        self.nodes, self.links_ok = nodes, links_ok
        self.update()

    def paintEvent(self, _):
        if not self.nodes:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n, size = len(self.nodes), ICON["large"]
        step = self.width() / n
        centers = [QPointF(step * (i + 0.5), SPACE["section"] + size / 2) for i in range(n)]
        for i in range(n - 1):
            a, b = centers[i], centers[i + 1]
            ok = self.links_ok[i] if i < len(self.links_ok) else False
            # Vista: a working link is a green double line, a broken one a grey dashed line
            x0, x1 = a.x() + size / 2 + SPACE["related"], b.x() - size / 2 - SPACE["related"]
            if ok:
                for dy, col in ((-1.5, "#86c15e"), (1.5, "#5c9f37")):
                    p.setPen(QPen(QColor(col), 1.2))
                    p.drawLine(QPointF(x0, a.y() + dy), QPointF(x1, b.y() + dy))
            else:
                p.setPen(QPen(QColor(COLOR["monitor_disabled"]), 2, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(x0, a.y()), QPointF(x1, b.y()))
            if not ok:
                mid, r = QPointF((a.x() + b.x()) / 2, a.y()), 7
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(COLOR["error"]))
                p.drawEllipse(mid, r + 2, r + 2)
                p.setPen(QPen(QColor(COLOR["on_error"]), 2))
                p.drawLine(QPointF(mid.x() - r / 2, mid.y() - r / 2), QPointF(mid.x() + r / 2, mid.y() + r / 2))
                p.drawLine(QPointF(mid.x() + r / 2, mid.y() - r / 2), QPointF(mid.x() - r / 2, mid.y() + r / 2))
        p.setPen(QColor(COLOR["text"]))
        for c, (icon, label) in zip(centers, self.nodes):
            pm = QIcon.fromTheme(icon, QIcon.fromTheme("network-workgroup")).pixmap(QSize(size, size))
            p.drawPixmap(int(c.x() - size / 2), int(c.y() - size / 2), pm)
            rect = self.rect().adjusted(int(c.x() - step / 2), int(c.y() + size / 2 + SPACE["related"]),
                                        0, 0)
            rect.setWidth(int(step))
            p.drawText(rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), label)


# ----------------------------------------------------------------------------- status window
# --- Vista's ruled information box and Sharing and Discovery rows -----------------------
VISTA_BOX = "#d0d0d0"        # box and row rules (measured, Network and Sharing Center)
VISTA_ROW = "#f3f4f8"        # Sharing and Discovery row background (measured)
LABEL_COLUMN = 175           # first column of those boxes (measured: 236 -> 411 px)


def ruled_box(rows):
    """[(label, value, trailing widget or None)] in a light grey box, one rule per row."""
    box = QFrame()
    box.setObjectName("ruledbox")
    box.setStyleSheet(f"QFrame#ruledbox {{ border: 1px solid {VISTA_BOX}; border-left: none; border-right: none; }}"
                      f" QFrame#ruledrow {{ border-top: 1px solid {VISTA_BOX}; }}")
    v = vbox(box, "none", "none")
    for i, (label, value, extra) in enumerate(rows):
        row = QFrame()
        if i:
            row.setObjectName("ruledrow")
        h = hbox(row, "none", "related")
        h.setContentsMargins(5, 5, 0, 5)
        lab = text_label(label, "body", selectable=False)
        lab.setFixedWidth(LABEL_COLUMN)
        h.addWidget(lab)
        h.addWidget(text_label(value, "value"), 1)
        if extra is not None:
            h.addWidget(extra)
        v.addWidget(row)
    return box


class Expander(QPushButton):
    """Vista's round expand button: a small glassy circle with a chevron (down: closed)."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, _):
        from PyQt6.QtGui import QLinearGradient, QPolygonF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        hover = self.underMouse()
        g = QLinearGradient(QPointF(r.topLeft()), QPointF(r.bottomLeft()))
        g.setColorAt(0, QColor("#ffffff"))
        g.setColorAt(0.5, QColor("#eef2f7" if not hover else "#e3f1fb"))
        g.setColorAt(1, QColor("#d9e1ea" if not hover else "#c4e2f7"))
        p.setBrush(g)
        p.setPen(QPen(QColor("#7d8fa5" if not hover else "#3c7fb1"), 1))
        p.drawEllipse(r)
        c = QPointF(r.center()) + QPointF(0.5, 0.5)
        d = 1 if not self.isChecked() else -1
        p.setPen(QPen(QColor("#2b3c52"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF([c + QPointF(-3.5, -1.8 * d), c + QPointF(0, 1.8 * d), c + QPointF(3.5, -1.8 * d)]))
        p.end()


class SharingRows(QFrame):
    """Vista's Sharing and Discovery list: setting, a green or grey dot with On/Off, and a
    round button that opens an explanation with a way to change it."""

    def __init__(self, rows, launch):
        super().__init__()
        self.setObjectName("sharing")
        self.setStyleSheet(f"QFrame#sharing {{ border: 1px solid {VISTA_BOX}; }}"
                           f" QFrame#sharingrow {{ background: {VISTA_ROW}; }}"
                           f" QFrame#sharingmore {{ background: {style.color('page')}; border-top: 1px solid {VISTA_BOX};"
                           f" border-bottom: 1px solid {VISTA_BOX}; }}")
        v = vbox(self, "none", "none")
        for name, on, text, action, argv in rows:
            row = QFrame()
            row.setObjectName("sharingrow")
            h = hbox(row, "none", "related")
            h.setContentsMargins(5, 4, 5, 4)
            lab = text_label(name, "body", selectable=False)
            lab.setFixedWidth(LABEL_COLUMN)
            h.addWidget(lab)
            dot = QLabel("\u25CF")
            dot.setStyleSheet(f"color: {style.color('status_on' if on else 'monitor_disabled')}; background: transparent;")
            h.addWidget(dot)
            h.addWidget(text_label("On" if on else "Off", "value", selectable=False), 1)
            more = Expander()
            more.setToolTip(f"About {name.lower()}")
            h.addWidget(more)
            v.addWidget(row)
            detail = QFrame()
            detail.setObjectName("sharingmore")
            dv = vbox(detail, "none", "related")
            dv.setContentsMargins(26, 9, 9, 11)
            dv.addWidget(text_label(text, "body"))
            go = Link(action, "link")
            go.clicked.connect(lambda a=argv: launch(a))
            dv.addWidget(go)
            detail.setVisible(False)
            v.addWidget(detail)

            more.toggled.connect(detail.setVisible)


class StatusDialog(QDialog):
    """Windows' "<connection> Status" window: connection facts and live activity."""

    def __init__(self, dev, parent=None):
        super().__init__(parent)
        self.dev = dev
        self.setWindowTitle(f"{kind_label(dev['type'])} Status")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        v = vbox(self, "dialog", "related")
        section(v, "Connection")
        self.grid = form_grid()
        v.addLayout(self.grid)
        section(v, "Activity")
        act = form_grid()
        act.addWidget(text_label("", "secondary"), 0, 0)
        act.addWidget(text_label("Sent", "caption"), 0, 1, Qt.AlignmentFlag.AlignRight)
        act.addWidget(text_label("Received", "caption"), 0, 2, Qt.AlignmentFlag.AlignRight)
        act.addWidget(text_label("Bytes:", "secondary"), 1, 0)
        self.sent, self.recv = text_label("", "value"), text_label("", "value")
        act.addWidget(self.sent, 1, 1, Qt.AlignmentFlag.AlignRight)
        act.addWidget(self.recv, 1, 2, Qt.AlignmentFlag.AlignRight)
        act.setColumnStretch(0, 1)
        act.setColumnMinimumWidth(1, 120)
        act.setColumnMinimumWidth(2, 120)
        v.addLayout(act)
        gap(v, "section")
        row = hbox(spacing="related")
        details = QPushButton("Details…")
        details.clicked.connect(self._details)
        disable = QPushButton("Disable")
        disable.clicked.connect(self._disable)
        diag = QPushButton("Diagnose")
        diag.clicked.connect(lambda: diagnose(self))
        row.addWidget(details)
        row.addWidget(disable)
        row.addWidget(diag)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)
        self.resize(SIZE["dialog"][0], 0)
        self._refresh()
        t = QTimer(self, interval=1000)
        t.timeout.connect(self._tick)
        t.start()
        self._tick()

    def _refresh(self):
        clear_layout(self.grid)
        d, dev = device_details(self.dev["device"]), self.dev
        state = connectivity()
        ipv6 = "Internet" if d.get("IP6.GATEWAY", [""])[0] else ("Local" if d.get("IP6.ADDRESS") else "No network access")
        self._since = activated_since(dev["connection"])
        rows = [("IPv4 Connectivity:", "Internet" if state == "full" else ACCESS.get(state, state)),
                ("IPv6 Connectivity:", ipv6),
                ("Media State:", "Enabled" if dev["state"].startswith("connected") else "Disabled")]
        if dev["type"] == "wifi":
            rows.append(("SSID:", connection_ssid(dev["connection"])))
        self._duration = text_label("", "value")
        rows.append(("Duration:", self._duration))
        rows.append(("Speed:", (d.get("CAPABILITIES.SPEED") or ["Unknown"])[0].replace("Mb/s", "Mbps")))
        if dev["type"] == "wifi":
            sig = wifi_signal(connection_ssid(dev["connection"]))
            rows.append(("Signal Quality:", f"{signal_word(sig)} ({sig}%)" if sig is not None else "Unknown"))
        for r, (k, val) in enumerate(rows):
            self.grid.addWidget(text_label(k, "secondary"), r, 0)
            self.grid.addWidget(val if isinstance(val, QLabel) else text_label(val, "value"), r, 1)
        self.grid.setColumnStretch(1, 1)

    def _tick(self):
        tx, rx = counters(self.dev["device"])
        self.sent.setText(human_bytes(tx))
        self.recv.setText(human_bytes(rx))
        if self._since:
            secs = int(time.time() - self._since)
            d, rem = divmod(secs, 86400)
            h, rem = divmod(rem, 3600)
            m, s = divmod(rem, 60)
            self._duration.setText((f"{d} days, " if d else "") + f"{h:02d}:{m:02d}:{s:02d}")

    def _details(self):
        d = device_details(self.dev["device"])
        dlg = QDialog(self)
        dlg.setWindowTitle("Network Connection Details")
        v = vbox(dlg, "dialog", "related")
        v.addWidget(QLabel("Network Connection Details:"))
        tree = QTreeWidget()
        tree.setHeaderLabels(["Property", "Value"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        addr = d.get("IP4.ADDRESS", [])

        def mask(cidr):
            try:
                bits = int(cidr.split("/")[1])
                m = (0xffffffff << (32 - bits)) & 0xffffffff
                return socket.inet_ntoa(m.to_bytes(4, "big"))
            except (IndexError, ValueError, OSError):
                return ""
        rows = [("Description", kind_label(self.dev["type"])),
                ("Physical Address", (d.get("GENERAL.HWADDR") or [""])[0].replace(":", "-")),
                ("IPv4 Address", ", ".join(a.split("/")[0] for a in addr)),
                ("IPv4 Subnet Mask", mask(addr[0]) if addr else ""),
                ("IPv4 Default Gateway", (d.get("IP4.GATEWAY") or [""])[0]),
                ("IPv4 DNS Server", ", ".join(d.get("IP4.DNS", []))),
                ("IPv6 Address", "\n".join(a.split("/")[0] for a in d.get("IP6.ADDRESS", []) if not a.startswith("fe80"))),
                ("Link-local IPv6 Address", "\n".join(a.split("/")[0] for a in d.get("IP6.ADDRESS", []) if a.startswith("fe80"))),
                ("IPv6 Default Gateway", (d.get("IP6.GATEWAY") or [""])[0]),
                ("IPv6 DNS Server", ", ".join(d.get("IP6.DNS", [])))]
        for k, val in rows:
            if val:
                tree.addTopLevelItem(QTreeWidgetItem([k, val]))
        tree.resizeColumnToContents(0)
        v.addWidget(tree, 1)
        row = hbox(spacing="related")
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        v.addLayout(row)
        dlg.resize(*SIZE["dialog"])
        dlg.exec()

    def _disable(self):
        if QMessageBox.question(self, self.windowTitle(),
                                f"Disconnect from {self.dev['connection']}?") == QMessageBox.StandardButton.Yes:
            run(["nmcli", "device", "disconnect", self.dev["device"]])
            self.accept()


def diagnose(parent):
    """Windows Network Diagnostics, simplified: check connectivity, say what we found."""
    ok, out, _ = run(["nmcli", "networking", "connectivity", "check"], timeout=30)
    state = out.strip() if ok else "unknown"
    if state == "full":
        msg, icon = "Your computer is connected to the Internet. No problems were found.", QMessageBox.Icon.Information
    elif state == "portal":
        msg, icon = ("This network requires you to sign in. Open your web browser to see the sign-in page.",
                     QMessageBox.Icon.Warning)
    elif state == "limited":
        msg, icon = ("You are connected to the network, but it doesn’t have Internet access. Restart your "
                     "router, or check with whoever manages this network.", QMessageBox.Icon.Warning)
    else:
        msg, icon = ("Your computer is not connected to a network. Connect to a wireless network from the "
                     "notification area, or plug in a network cable.", QMessageBox.Icon.Warning)
    QMessageBox(icon, f"{distro.NAME} Network Diagnostics", msg, parent=parent).exec()


# ----------------------------------------------------------------------------- center
class NetworkCenter(TaskWindow):
    ID = "network"
    TITLE = "Network and Sharing Center"
    ICON = "preferences-system-network-connection"
    ADVANCED = "kcm:kcm_networkmanagement"
    REPLACES = ["kcm_networkmanagement"]
    EXTRA_STYLE = ""

    @classmethod
    def available(cls):
        return run(["nmcli", "-v"])[0]

    def build(self):
        self.resize(860, 600)
        self.task_frame()
        self._status = None

    def load(self):
        start = self.initial or "home"
        self.show_page(start if hasattr(self, f"_page_{start}") else "home")

    def show_page(self, name):
        clear_layout(self.content_layout)
        clear_layout(self.pane_layout)
        getattr(self, f"_page_{name}")()
        self.pane_heading("Tasks")
        if name != "home":
            self.pane_link("Network and Sharing Center", lambda: self.show_page("home"))
        self.pane_link("View computers and devices", lambda: self.launch(["dolphin", "network:/"]))
        self.pane_link("Connect to a network", lambda: self.launch(["kcmshell6", "kcm_networkmanagement"]))
        if name != "connections":
            self.pane_link("Manage network connections", lambda: self.show_page("connections"))
        self.pane_link("Diagnose and repair", lambda: diagnose(self))
        self.pane_layout.addStretch(1)
        self.pane_heading("See also")
        self.pane_link("Internet Options", lambda: self.launch(["kcmshell6", "kcm_proxy"]))
        self.pane_link(f"{distro.NAME} Firewall", lambda: self.launch(["kcmshell6", "kcm_firewall"]))

    # --- home ----------------------------------------------------------------------------
    def _page_home(self):
        """Vista's Network and Sharing Center: the map, the network you are on in a ruled
        box, and Sharing and Discovery as rows you can open for an explanation."""
        v = self.content_layout
        top = hbox()
        top.addWidget(text_label("Network and Sharing Center", "instruction"), 1)
        v.addLayout(top)
        state = connectivity()
        devs = devices()
        active = [d for d in devs if d["state"].startswith("connected")]
        net_label = active[0]["connection"] if active else "Not connected"
        host = socket.gethostname().upper()
        full_map = Link("View full map", "link")
        full_map.clicked.connect(lambda: self.launch(["dolphin", "network:/"]))
        v.addWidget(full_map, 0, Qt.AlignmentFlag.AlignRight)
        m = NetworkMap()
        m.set_state([("computer", f"{host}\n(This computer)"),
                     (kind_icon(active[0]["type"]) if active else "network-offline", net_label),
                     ("gnome-globe", "Internet")],             # the Vista globe (applications-internet is IE's logo)
                    [bool(active), state == "full"])
        v.addWidget(m)
        gap(v, "section")

        if not active:
            v.addWidget(text_label("You are currently not connected to any networks.", "body"))
            l = Link("Connect to a network", "link")
            l.clicked.connect(lambda: self.launch(["kcmshell6", "kcm_networkmanagement"]))
            v.addWidget(l)
        for d in active:
            head = hbox(spacing="related")
            head.addWidget(icon_label(kind_icon(d["type"]), "small"))
            # the profile name is often the SSID, which anyone nearby can choose: escape it
            name = text_label(f"<b>{html.escape(d['connection'])}</b> (Private network)", "body")
            name.setTextFormat(Qt.TextFormat.RichText)
            head.addWidget(name, 1)
            custom = Link("Customize", "link")
            custom.clicked.connect(lambda: self.launch(["kcmshell6", "kcm_networkmanagement"]))
            head.addWidget(custom)
            v.addLayout(head)
            conn = kind_label(d["type"])
            if d["type"] == "wifi":
                sig = wifi_signal(connection_ssid(d["connection"]))
                if sig is not None:
                    conn += f" (Signal strength: {signal_word(sig)})"
            status = Link("View status", "link")
            status.clicked.connect(lambda d=d: self._show_status(d))
            v.addWidget(ruled_box([("Access", ACCESS.get(state, state), None),
                                   ("Connection", conn, status)]))
            gap(v, "section")

        head = hbox(spacing="related")
        head.addWidget(icon_label("folder-remote", "small"))
        head.addWidget(text_label("Sharing and Discovery", "strong"), 1)
        v.addLayout(head)
        cups = run(["cupsctl"])[1]
        v.addWidget(SharingRows([
            ("Network discovery", service_active("avahi-daemon"),
             "When network discovery is on, this computer can see other network computers and devices "
             "and is visible to other network computers.",
             "Change discovery settings", ["kcmshell6", "kcm_networkmanagement"]),
            ("File sharing", service_active("smbd"),
             "When file sharing is on, files and folders you have shared can be accessed by people on "
             "the network. Share a folder from its Properties in Dolphin.",
             "Share a folder", ["dolphin"]),
            ("Printer sharing", "_share_printers=1" in cups,
             "When printer sharing is on, people on the network can use the printers attached to this "
             "computer.",
             "Open printer settings", ["kcmshell6", "kcm_printer_manager"]),
        ], self.launch))
        gap(v, "section")
        share = Link("Show me all the files and folders I am sharing", "link")
        share.clicked.connect(lambda: self.launch(["dolphin", "--new-window", os.path.expanduser("~/Public")]))
        v.addWidget(share)
        nearby = Link("Show me all the shared network folders on this computer", "link")
        nearby.clicked.connect(lambda: self.launch(["dolphin", "network:/"]))
        v.addWidget(nearby)
        v.addStretch(1)

    def _show_status(self, d):
        self._status = StatusDialog(d, self)
        self._status.show()

    def _disconnect(self, d):
        if QMessageBox.question(self, self.TITLE, f"Disconnect from {d['connection']}?") == \
                QMessageBox.StandardButton.Yes:
            self._job = Jobs([["nmcli", "device", "disconnect", d["device"]]], self)
            self._job.finished.connect(lambda ok, err: (ok or QMessageBox.warning(self, self.TITLE, err),
                                                        self.show_page("home")))
            self._job.start()

    # --- network connections -----------------------------------------------------------
    def _page_connections(self):
        v = self.content_layout
        self.heading(v, "Network Connections",
                     "Select a connection to see its status, or to connect or disconnect it.")
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Status", "Device Name", "Connectivity"])
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setIconSize(QSize(ICON["medium"], ICON["medium"]))
        state = connectivity()
        for d in devices():
            connected = d["state"].startswith("connected")
            it = QTreeWidgetItem([kind_label(d["type"]),
                                  d["connection"] if connected else d["state"].capitalize(),
                                  d["device"], ACCESS.get(state, "") if connected else "Not connected"])
            it.setIcon(0, QIcon.fromTheme(kind_icon(d["type"])))
            it.setData(0, Qt.ItemDataRole.UserRole, d)
            self._tree.addTopLevelItem(it)
        for c in range(4):
            self._tree.resizeColumnToContents(c)
        v.addWidget(self._tree, 1)
        row = hbox(spacing="related")
        self._b_status = QPushButton("Status")
        self._b_toggle = QPushButton("Disconnect")
        self._b_props = QPushButton("Properties")
        for b in (self._b_status, self._b_toggle, self._b_props):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self._b_status.clicked.connect(lambda: self._cur() and self._show_status(self._cur()))
        self._b_toggle.clicked.connect(self._toggle)
        self._b_props.clicked.connect(lambda: self.launch(["kcmshell6", "kcm_networkmanagement"]))
        self._tree.currentItemChanged.connect(lambda *_: self._conn_buttons())
        self._tree.itemDoubleClicked.connect(lambda *_: self._cur() and self._show_status(self._cur()))
        if self._tree.topLevelItemCount():
            self._tree.setCurrentItem(self._tree.topLevelItem(0))
        self._conn_buttons()

    def _cur(self):
        it = self._tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _conn_buttons(self):
        d = self._cur()
        connected = bool(d) and d["state"].startswith("connected")
        self._b_status.setEnabled(connected)
        self._b_toggle.setEnabled(bool(d))
        self._b_toggle.setText("Disconnect" if connected else "Connect")

    def _toggle(self):
        d = self._cur()
        if not d:
            return
        cmd = ["nmcli", "device", "disconnect" if d["state"].startswith("connected") else "connect", d["device"]]
        self._job = Jobs([cmd], self)
        self._job.finished.connect(lambda ok, err: (ok or QMessageBox.warning(self, self.TITLE, err),
                                                    self.show_page("connections")))
        self._job.start()
