#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mk_alt3_usb3only.py

从原厂固件生成一版"只保留 alt3"的镜像，但**只改 USB 3.x 那一份配置描述符**，
USB 2.0 那份一个字节都不动。这样万一 Windows 不接受，插到 USB 2.0 口就会走
未改动的配置，设备照常枚举，可以刷回来 —— 不需要 Linux。

做法：在 config B 里删掉接口 3 的 alt1、alt2 两个完整块（每块 49 字节，含
SS companion），把后面的描述符整体前移，并把 wTotalLength 减小 98。
描述符块变短，但后面 flash 里的内容不移动（SIE 按 wTotalLength 返回）。

用法: python mk_alt3_usb3only.py ms2130s_backup.bin out.bin [--serial 20210624]
"""
import argparse
import re

CONFIG_USB2 = 0x0640     # 不动
CONFIG_USB3 = 0x0A94     # 只改这一份
AS_INTF = 3              # 音频流接口号
DROP_ALTS = (1, 2)       # 要删掉的 alt


def walk(blob, start, total):
    """产出 (offset, length, type) 直到配置末尾。"""
    p = start
    end = start + total
    while p + 2 <= end:
        ln = blob[p]
        if ln < 2:
            break
        yield p, ln, blob[p + 1]
        p += ln


def find_alt_blocks(blob, cfg):
    """返回 {alt: (start, end)}，end 为块尾（不含）。"""
    total = blob[cfg + 2] | (blob[cfg + 3] << 8)
    items = list(walk(blob, cfg, total))
    out = {}
    for i, (off, ln, dt) in enumerate(items):
        if dt != 0x04 or off + 9 > len(blob):
            continue
        if blob[off + 2] != AS_INTF:
            continue
        alt = blob[off + 3]
        # 块结束 = 下一个 interface 描述符，或配置结尾
        nxt = cfg + total
        for off2, _, dt2 in items[i + 1:]:
            if dt2 == 0x04:
                nxt = off2
                break
        out[alt] = (off, nxt)
    return out, total


def find_serial(blob):
    """找固件里唯一的 8 位 UTF-16LE 序列号。"""
    found = set()
    for m in re.finditer(rb"(?:[0-9]\x00){8}", blob):
        found.add(m.group().decode("utf-16le"))
    if len(found) != 1:
        raise ValueError("无法唯一识别序列号：%s" % sorted(found))
    return found.pop()


def patch_serial(blob, serial):
    """把源固件里的 8 位序列号改成目标值；长度不变，改完重算校验和。"""
    old = find_serial(blob)
    if not re.fullmatch(r"[0-9]{8}", serial):
        raise ValueError("序列号必须是 8 位数字")
    old_bytes = old.encode("utf-16le")
    new_bytes = serial.encode("utf-16le")
    count = blob.count(old_bytes)
    if count == 0:
        raise ValueError("没有找到序列号 %s" % old)
    blob[:] = blob.replace(old_bytes, new_bytes)
    print("serial %s -> %s  (%d 处)" % (old, serial, count))
    return blob


def main(src, dst, serial=None):
    blob = bytearray(open(src, 'rb').read())

    blocks, total = find_alt_blocks(blob, CONFIG_USB3)
    if set(DROP_ALTS) - set(blocks):
        sys.exit('alt %s not found in config B (found %s)'
                 % (sorted(set(DROP_ALTS) - set(blocks)), sorted(blocks)))

    lo = min(blocks[a][0] for a in DROP_ALTS)
    hi = max(blocks[a][1] for a in DROP_ALTS)
    removed = hi - lo
    print('config B @0x%04X  wTotalLength=%d' % (CONFIG_USB3, total))
    for a in sorted(blocks):
        print('  alt%d  block 0x%04X-0x%04X (%d bytes)' %
              (a, blocks[a][0], blocks[a][1], blocks[a][1] - blocks[a][0]))
    print('removing 0x%04X-0x%04X  (%d bytes)' % (lo, hi, removed))
    if removed <= 0:
        sys.exit('nothing to remove')

    # 前移：把 hi 之后到配置末尾的内容搬到 lo
    cfg_end = CONFIG_USB3 + total
    tail = bytes(blob[hi:cfg_end])
    blob[lo:lo + len(tail)] = tail
    new_total = total - removed
    blob[CONFIG_USB3 + 2] = new_total & 0xFF
    blob[CONFIG_USB3 + 3] = (new_total >> 8) & 0xFF
    print('new wTotalLength=%d' % new_total)

    if serial:
        patch_serial(blob, serial)

    # 校验和（固件最后 2 字节 = code 区字节和，大端）
    body = blob[0x30:len(blob) - 4]
    blob[-2:] = (sum(body) & 0xFFFF).to_bytes(2, 'big')
    open(dst, 'wb').write(bytes(blob))
    print('wrote %s  checksum=%s' % (dst, blob[-2:].hex()))


def cli():
    ap = argparse.ArgumentParser(description="只删 USB3 配置的 alt1/alt2，可选改序列号")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--serial", help="目标 8 位序列号；不传则保留源固件序列号")
    args = ap.parse_args()
    try:
        main(args.src, args.dst, args.serial)
    except (OSError, ValueError) as e:
        raise SystemExit(str(e))


if __name__ == '__main__':
    cli()
