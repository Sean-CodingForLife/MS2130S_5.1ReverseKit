#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MS2130S / MS2131S firmware inspector.

Scans a flash dump (.bin) for
  * EDID blocks and the audio formats they advertise to the HDMI source
  * USB Audio Class 1.0 streaming descriptors (what the PC is allowed to see)

Usage:
    python ms213x_uac_tool.py scan  dump.bin
    python ms213x_uac_tool.py patch dump.bin --channels 6 --out patched.bin

`patch` only rewrites bNrChannels in FORMAT_TYPE_I descriptors and the
wMaxPacketSize of the matching isochronous endpoint. It does NOT fix any
firmware checksum -- let the flashing tool do that.
"""

import argparse
import struct
import sys

SAD_FORMAT = {
    1: "LPCM", 2: "AC-3", 3: "MPEG1", 4: "MP3", 5: "MPEG2", 6: "AAC",
    7: "DTS", 8: "ATRAC", 9: "DSD", 10: "E-AC-3", 11: "DTS-HD", 12: "MLP",
    13: "DST", 14: "WMA-Pro",
}


def find_edid(blob):
    sig = bytes.fromhex("00FFFFFFFFFFFF00")
    out, i = [], blob.find(sig)
    while i != -1:
        out.append(i)
        i = blob.find(sig, i + 1)
    return out


def parse_edid(blob, base):
    """Return (list of audio format strings, note)."""
    notes, fmts = [], []
    if base + 128 > len(blob):
        return fmts, "truncated"
    n_ext = blob[base + 126]
    for e in range(n_ext):
        off = base + 128 * (e + 1)
        if off + 128 > len(blob):
            notes.append("ext%d beyond file" % (e + 1))
            break
        ext = blob[off:off + 128]
        if ext[0] != 0x02:            # not CEA-861
            notes.append("ext%d tag=0x%02X (not CEA)" % (e + 1, ext[0]))
            continue
        dtd = ext[2]
        i = 4
        while i < min(dtd, 127) and i < len(ext):
            tag, ln = ext[i] >> 5, ext[i] & 0x1F
            if ln == 0:
                break
            if tag == 1:              # Audio Data Block
                for j in range(i + 1, i + 1 + ln - 2, 3):
                    b0, b1, b2 = ext[j], ext[j + 1], ext[j + 2]
                    code = (b0 >> 3) & 0x0F
                    ch = (b0 & 0x07) + 1
                    name = SAD_FORMAT.get(code, "fmt%d" % code)
                    fmts.append("%s %dch" % (name, ch))
            i += 1 + ln
    return fmts, "; ".join(notes)


def uac_format_descriptors(blob):
    """Yield dicts for every CS_INTERFACE / FORMAT_TYPE / FORMAT_TYPE_I."""
    out = []
    for i in range(1, len(blob) - 8):
        if blob[i] != 0x24 or blob[i + 1] != 0x02 or blob[i + 2] != 0x01:
            continue
        length = blob[i - 1]
        ch, sub, bits = blob[i + 3], blob[i + 4], blob[i + 5]
        nf = blob[i + 6]
        if not (11 <= length <= 64 and 1 <= ch <= 8 and 1 <= sub <= 4 and nf <= 6):
            continue
        freqs = []
        for k in range(nf):
            p = i + 7 + 3 * k
            if p + 3 > len(blob):
                break
            freqs.append(blob[p] | (blob[p + 1] << 8) | (blob[p + 2] << 16))
        if length < 7 + 3 * nf:
            continue
        out.append(dict(off=i - 1, ch=ch, sub=sub, bits=bits,
                        freqs=freqs, length=length))
    return out


def iso_endpoints(blob):
    out = []
    for i in range(0, len(blob) - 7):
        if blob[i] == 0x07 and blob[i + 1] == 0x05 and (blob[i + 3] & 0x03) == 0x01:
            out.append(dict(off=i, addr=blob[i + 2], attr=blob[i + 3],
                            mps=blob[i + 4] | (blob[i + 5] << 8),
                            interval=blob[i + 6]))
    return out


def cmd_scan(path):
    blob = open(path, "rb").read()
    print("file      : %s (%d bytes)" % (path, len(blob)))

    print("\n== EDID ==")
    bases = find_edid(blob)
    if not bases:
        print("  no EDID signature found")
    for b in bases:
        fmts, note = parse_edid(blob, b)
        print("  @0x%06X  %s" % (b, note or ""))
        print("    audio: %s" % (", ".join(fmts) if fmts else "(none / no CEA block)"))

    print("\n== UAC1 FORMAT_TYPE_I ==")
    fmts = uac_format_descriptors(blob)
    if not fmts:
        print("  no audio format descriptor found (firmware may store it compressed)")
    for f in fmts:
        print("  @0x%06X  ch=%d sub=%dB bits=%d  freqs=%s  len=%d"
              % (f["off"], f["ch"], f["sub"], f["bits"],
                 ",".join(str(x) for x in f["freqs"]), f["length"]))

    print("\n== isochronous endpoints ==")
    eps = iso_endpoints(blob)
    if not eps:
        print("  none")
    for e in eps:
        print("  @0x%06X  addr=0x%02X  mps=%d B/frame  interval=%d"
              % (e["off"], e["addr"], e["mps"], e["interval"]))

    print("\n== needed wMaxPacketSize (bytes per 1 ms frame) ==")
    for f in fmts:
        for r in f["freqs"] or [48000]:
            print("  %dch %dbit @%d Hz -> %d" % (f["ch"], f["bits"], r,
                                                 (f["ch"] * f["sub"] * r) // 1000))


def cmd_patch(path, channels, out):
    blob = bytearray(open(path, "rb").read())
    fmts = uac_format_descriptors(bytes(blob))
    if not fmts:
        print("no format descriptor found; aborting")
        return 1
    eps = iso_endpoints(bytes(blob))
    changed = 0
    for f in fmts:
        if f["ch"] == channels:
            continue
        old = f["ch"]
        blob[f["off"] + 3] = channels
        rate = f["freqs"][0] if f["freqs"] else 48000
        need = (channels * f["sub"] * rate) // 1000
        near = [e for e in eps if 0 < e["off"] - f["off"] < 64]
        if near:
            e = min(near, key=lambda x: x["off"] - f["off"])
            blob[e["off"] + 4] = need & 0xFF
            blob[e["off"] + 5] = (need >> 8) & 0xFF
            print("  @0x%06X ch %d->%d, ep@0x%06X mps->%d"
                  % (f["off"], old, channels, e["off"], need))
        else:
            print("  @0x%06X ch %d->%d (no adjacent endpoint found)"
                  % (f["off"], old, channels))
        changed += 1
    if not changed:
        print("nothing to do")
        return 0
    open(out, "wb").write(bytes(blob))
    print("wrote %s" % out)
    print("NOTE: firmware checksum not fixed here -- let the flashing tool rebuild it.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("bin")
    p = sub.add_parser("patch")
    p.add_argument("bin")
    p.add_argument("--channels", type=int, default=6, choices=[6, 8])
    p.add_argument("--out", default="patched.bin")
    a = ap.parse_args()
    if a.cmd == "scan":
        cmd_scan(a.bin)
        return 0
    return cmd_patch(a.bin, a.channels, a.out)


if __name__ == "__main__":
    sys.exit(main())
