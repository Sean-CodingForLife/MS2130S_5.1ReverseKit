#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""force alt3: neutralize the two 2-channel alternate settings so the host must
select AS alt=3 (the factory 6ch/16bit/48k setting), and fix the channel mask.

Rationale: the MS2130S ignores the descriptor *contents* and maps SET_INTERFACE
wValue (the alt number) onto a hard-coded audio format table.  alt1 -> 2ch/24bit/96k,
alt2 -> 2ch/16bit/48k, alt3 -> 6ch/16bit/48k.  As long as Windows picks alt1 or
alt2 we can never get 6 channels, no matter how the descriptors are edited.

Run:  python patch_alt3.py ms2130s_backup.bin out.bin
"""
import sys

# AS interface descriptors (bLength=09 bDescriptorType=04 bInterfaceNumber=03)
# bNumEndpoints is byte +4 of each interface descriptor.
EP_COUNT_OFFS = [
    0x9DC,   # config A (USB2) alt1  (interface desc @0x9D8)
    0xA07,   # config A alt2         (interface desc @0xA03)
    0x1058,  # config B (USB3) alt1  (interface desc @0x1054)
    0x1089,  # config B alt2         (interface desc @0x1085)
]
# AC input terminal wChannelConfig high byte (0x0003 -> 0x003F = 5.1)
MASK_OFFS = [0x9B5, 0x1031]
# UTF-16LE serial "20210629" -> "20210631"
SERIAL_OFFS = [0x1A77, 0x1A8C]


def checksum(body):
    return sum(body) & 0xFFFF


def main(src, dst):
    b = bytearray(open(src, 'rb').read())
    n = len(b)

    # sanity: descriptor layout must match what we expect
    assert b[0x9D8:0x9E1] == bytes.fromhex('090403010101020004'), b[0x9D8:0x9E1].hex()
    assert b[0xA03:0xA0C] == bytes.fromhex('090403020101020004'), b[0xA03:0xA0C].hex()
    assert b[0x1054:0x105D] == bytes.fromhex('090403010101020004'), b[0x1054:0x105D].hex()
    assert b[0x1085:0x108E] == bytes.fromhex('090403020101020004'), b[0x1085:0x108E].hex()
    assert b[0xA3E:0xA49] == bytes.fromhex('0B2402010602100180BB00'), b[0xA3E:0xA49].hex()
    assert b[0x10C6:0x10D1] == bytes.fromhex('0B2402010602100180BB00'), b[0x10C6:0x10D1].hex()

    for o in EP_COUNT_OFFS:
        assert b[o] == 1, (hex(o), b[o])
        b[o] = 0

    for o in MASK_OFFS:
        assert b[o] == 0x00, (hex(o), b[o])
        b[o] = 0x3F

    for o in SERIAL_OFFS:
        assert b[o] == 0x39, (hex(o), b[o])
        b[o] = 0x31

    b[n - 2:] = checksum(b[0x30:n - 4]).to_bytes(2, 'big')

    open(dst, 'wb').write(bytes(b))
    print('wrote %s (%d bytes) csum=%s' % (dst, n, b[n - 2:].hex()))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
