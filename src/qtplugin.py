# SPDX-License-Identifier: GPL-3.0-or-later
"""Read a Qt 6 plugin's embedded metadata (e.g. a Plasma applet's KPlugin name and icon)
without loading the plugin - PyQt6 does not wrap QPluginLoader::metaData().

Qt 6 stores it in the ELF note .note.qt.metadata (older builds: after "QTMETADATA !"):
marker, 4 header bytes (version, Qt major, Qt minor, requirements), then a CBOR map whose
key 4 is the plugin's JSON metadata (qtbase src/corelib/plugin/qplugin.h)."""
import struct

MARKERS = (b"qt-project!\x00", b"QTMETADATA !")
METADATA_KEY = 4


def _cbor(b, i):
    """Decode the CBOR item at b[i] -> (value, index after it). Covers what Qt writes:
    ints, strings, arrays, maps, tags, simple values and floats."""
    ib = b[i]
    mt, ai = ib >> 5, ib & 31
    i += 1
    if ai < 24:
        val = ai
    elif ai in (24, 25, 26, 27):
        n = 1 << (ai - 24)
        val = int.from_bytes(b[i:i + n], "big")
        i += n
    elif ai == 31:
        val = None                                   # indefinite length
    else:
        raise ValueError("unsupported CBOR")
    if mt == 0:
        return val, i
    if mt == 1:
        return -1 - val, i
    if mt in (2, 3):
        if val is None:
            raise ValueError("indefinite string")
        s = bytes(b[i:i + val])
        return (s.decode("utf-8", "replace") if mt == 3 else s), i + val
    if mt in (4, 5):
        out = [] if mt == 4 else {}
        n = 0
        while (b[i] != 0xFF) if val is None else (n < val):
            if mt == 4:
                x, i = _cbor(b, i)
                out.append(x)
            else:
                k, i = _cbor(b, i)
                v, i = _cbor(b, i)
                out[k] = v
            n += 1
        return out, i + (1 if val is None else 0)
    if mt == 6:
        return _cbor(b, i)                           # tag: take the value
    if mt == 7:
        if ai == 25:
            return struct.unpack(">e", b[i - 2:i])[0], i
        if ai == 26:
            return struct.unpack(">f", b[i - 4:i])[0], i
        if ai == 27:
            return struct.unpack(">d", b[i - 8:i])[0], i
        return {20: False, 21: True}.get(ai), i
    raise ValueError("bad CBOR")


def metadata(path, limit=1 << 16):
    """The plugin's metadata dict (e.g. {"KPlugin": {"Name": ...}}), or {}."""
    try:
        with open(path, "rb") as f:
            head = f.read(limit)                     # the note sits near the start of the file
            for marker in MARKERS:
                p = head.find(marker)
                # last resort (old builds put the data anywhere): search the whole file
                if p < 0 and marker == MARKERS[-1]:
                    head = head + f.read()
                    p = head.find(marker)
                if p >= 0:
                    m, _ = _cbor(head, p + len(marker) + 4)
                    return m.get(METADATA_KEY, {}) if isinstance(m, dict) else {}
    except (OSError, ValueError, IndexError, TypeError, struct.error):      # malformed data
        pass
    return {}
