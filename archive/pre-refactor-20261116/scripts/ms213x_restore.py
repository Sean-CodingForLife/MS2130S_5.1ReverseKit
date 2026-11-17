#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ms213x_restore.py -- dependency-free MS2130S/MS2131S flash tool for Linux.

Talks to the card through /dev/bus/usb + USBDEVFS_CONTROL, so it needs neither
pyusb, nor hidapi, nor a kernel driver bound to the device.  This is the
recovery path for a card whose USB configuration descriptor no longer parses
(Windows: "Unknown USB Device (Invalid Configuration Descriptor)", hardware ID
USB\\CONFIGURATION_DESCRIPTOR_VALIDATION_FAILURE).

Protocol re-implemented from steve-m/ms213x_flash (MIT).

    sudo python3 ms213x_restore.py probe
    sudo python3 ms213x_restore.py backup  out.bin
    sudo python3 ms213x_restore.py restore ms2130s_backup.bin

    # if the device is not found automatically:
    sudo python3 ms213x_restore.py probe 1 12      (bus 1, address 12)
"""

import ctypes
import glob
import os
import struct
import sys

try:
    import fcntl
except ImportError:          # not on Linux; kept so the file can be inspected
    fcntl = None             # and its checksum helpers tested anywhere

USBDEVFS_CONTROL = 0xC0185500            # _IOWR('U',  0, struct ctrltransfer)
USBDEVFS_CLAIMINTERFACE = 0x8004550F     # _IOR('U', 15, unsigned int)
USBDEVFS_DISCONNECT = 0x00005516         # _IO('U', 22)

HEADER_LEN = 0x30
CODE_LEN = 0x18000
FLASH_SIZE = HEADER_LEN + CODE_LEN + 4   # 98356
PAGE = 256

HID_IF = 4                               # MI_04
REPORT = 1
TIMEOUT_MS = 3000

KNOWN_IDS = {0x2132: 'MS2130S', 0x2133: 'MS2131S', 0x0001: 'MS213xS-ROM'}


class Ctrl(ctypes.Structure):
    _fields_ = [('bRequestType', ctypes.c_uint8),
                ('bRequest', ctypes.c_uint8),
                ('wValue', ctypes.c_uint16),
                ('wIndex', ctypes.c_uint16),
                ('wLength', ctypes.c_uint16),
                ('timeout', ctypes.c_uint32),
                ('data', ctypes.c_void_p)]


def control(fd, rtype, rreq, value, index, length, data=b'', timeout=TIMEOUT_MS):
    buf = ctypes.create_string_buffer(max(length, 1))
    if data:
        ctypes.memmove(buf, data, min(len(data), length))
    c = Ctrl(rtype, rreq, value, index, length, timeout,
             ctypes.cast(buf, ctypes.c_void_p))
    fcntl.ioctl(fd, USBDEVFS_CONTROL,
                ctypes.string_at(ctypes.byref(c), ctypes.sizeof(c)))
    if rtype & 0x80:
        return buf.raw[:length]
    return b''


class Dev(object):
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR)
        self.path = path

    # -- reports (the MS2130S shifts the payload by one byte) ----------------
    def send(self, payload):
        buf = bytes([REPORT]) + payload
        control(self.fd, 0x21, 0x09, (3 << 8) | REPORT, HID_IF, len(buf), buf)

    def recv(self):
        r = control(self.fd, 0xA1, 0x01, (3 << 8) | REPORT, HID_IF, 64)
        return r[1:9]

    # -- registers -----------------------------------------------------------
    def write_reg(self, addr, val):
        self.send(bytes([0xb6, addr >> 8, addr & 0xff, val, 0, 0, 0, 0]))

    def read_sfr(self, addr):
        self.send(bytes([0xc5, addr, 0, 0, 0, 0, 0, 0]))
        return self.recv()[2]

    def write_sfr(self, addr, val):
        self.send(bytes([0xc6, addr, val, 0, 0, 0, 0, 0]))

    def setup_spi(self):
        self.write_reg(0xf01f, 0x00)
        p3 = self.read_sfr(0xb0) | 0x20
        p3 &= ~0x1c
        self.write_sfr(0xb0, p3)
        p2 = self.read_sfr(0xa0) | 0x1c
        self.write_sfr(0xa0, p2)
        self.write_reg(0xf01f, 0x10)

    # -- flash ---------------------------------------------------------------
    def read_page(self, addr):
        self.send(bytes([0xf7, 0x01, (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                         addr & 0xff, 0x01, 0x00, 0x00]))
        out = bytearray()
        for offs in range(0, PAGE, 8):
            self.send(bytes([0xf7, 0x00, 0, 0, 0, offs >> 8, offs & 0xff, 0]))
            out += self.recv()
        return bytes(out)

    def write_page(self, addr, data):
        self.send(bytes([0xf8, 0x01, (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                         addr & 0xff, 0x01, 0x00, 0x00]))
        for offs in range(0, PAGE, 6):
            chunk = data[offs:offs + 6]
            if len(chunk) < 6:
                chunk = chunk + b'\xff' * (6 - len(chunk))
            self.send(bytes([0xf8, 0x00]) + chunk)

    def erase(self):
        self.send(bytes([0xfe, 0, 0, 0, 0, 0, 0, 0]))

    def read_flash(self, total):
        buf = bytearray()
        for a in range(0, total, PAGE):
            buf += self.read_page(a)
            if a % (PAGE * 32) == 0:
                sys.stderr.write('\r  read  %6d / %d' % (a, total))
                sys.stderr.flush()
        sys.stderr.write('\r  read  %6d / %d\n' % (total, total))
        # the last page is padded to PAGE bytes by the chip, trim to the real size
        return bytes(buf[:total])

    def write_flash(self, data):
        total = len(data)
        for a in range(0, total, PAGE):
            self.write_page(a, data[a:a + PAGE])
            if a % (PAGE * 32) == 0:
                sys.stderr.write('\r  write %6d / %d' % (a, total))
                sys.stderr.flush()
        sys.stderr.write('\r  write %6d / %d\n' % (total, total))


def sysfs_devices():
    out = []
    for d in sorted(glob.glob('/sys/bus/usb/devices/*')):
        try:
            vid = int(open(os.path.join(d, 'idVendor')).read(), 16)
            pid = int(open(os.path.join(d, 'idProduct')).read(), 16)
            bus = int(open(os.path.join(d, 'busnum')).read())
            dev = int(open(os.path.join(d, 'devnum')).read())
        except (IOError, ValueError):
            continue
        try:
            prod = open(os.path.join(d, 'product')).read().strip()
        except IOError:
            prod = ''
        out.append((bus, dev, vid, pid, prod))
    return out


def known_devices():
    return [x for x in sysfs_devices() if x[2] == 0x345f and x[3] in KNOWN_IDS]


def checksum_report(data):
    hdr = 0
    for i in range(2, HEADER_LEN):
        if i < 0x0c or i > 0x0f:
            hdr += data[i]
    hdr &= 0xffff
    code = sum(data[HEADER_LEN:HEADER_LEN + CODE_LEN]) & 0xffff
    st_hdr = (data[HEADER_LEN + CODE_LEN] << 8) | data[HEADER_LEN + CODE_LEN + 1]
    st_code = (data[HEADER_LEN + CODE_LEN + 2] << 8) | data[HEADER_LEN + CODE_LEN + 3]
    return hdr, st_hdr, code, st_code


def main():
    if not os.path.isdir('/sys/bus/usb/devices'):
        sys.exit('this tool only runs on Linux (no /sys/bus/usb)')
    if os.geteuid() != 0:
        sys.exit('run with sudo')

    mode = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    if mode not in ('probe', 'backup', 'restore'):
        sys.exit('unknown mode %r (probe | backup | restore)' % mode)

    args = sys.argv[2:]
    bus = addr = None
    if len(args) >= 2 and args[0].isdigit() and args[1].isdigit():
        bus, addr = int(args[0]), int(args[1])
        args = args[2:]

    devs = known_devices()
    for b, dv, vid, pid, prod in devs:
        print('found %04x:%04x (%s)  bus %d addr %d  %r'
              % (vid, pid, KNOWN_IDS.get(pid, '?'), b, dv, prod))

    if bus is None:
        if not devs:
            print('!! no MS213x on the USB bus')
            print('   what Linux does see:')
            for b, dv, vid, pid, prod in sysfs_devices():
                print('     bus %d addr %d  %04x:%04x  %s' % (b, dv, vid, pid, prod))
            print('   also try:  lsusb ; dmesg | tail -40')
            print('   if it is listed above, rerun with bus and address, e.g.')
            print('     sudo python3 %s %s <bus> <addr>' % (sys.argv[0], mode))
            return 3
        bus, addr = devs[0][0], devs[0][1]

    path = '/dev/bus/usb/%03d/%03d' % (bus, addr)
    print('opening %s' % path)
    d = Dev(path)

    for name, req, arg in (('disconnect driver', USBDEVFS_DISCONNECT, None),
                           ('claim interface %d' % HID_IF, USBDEVFS_CLAIMINTERFACE,
                            struct.pack('I', HID_IF))):
        try:
            if arg is None:
                fcntl.ioctl(d.fd, req)
            else:
                fcntl.ioctl(d.fd, req, arg)
            print('  %s: ok' % name)
        except OSError as e:
            print('  %s: %s (continuing)' % (name, e.strerror))

    print('SPI setup ...')
    try:
        d.setup_spi()
    except OSError as e:
        sys.exit('SPI setup failed (%s) -- the card did not answer.\n'
                 'Nothing was written.' % e.strerror)

    if mode == 'probe':
        head = d.read_page(0)
        print('first 64 bytes of flash:')
        print('  ' + ' '.join('%02x' % b for b in head[:64]))
        ok = head[0] == 0x3c and head[1] == 0xc3
        print('header magic %02X %02X -> %s' % (head[0], head[1],
                                                'OK' if ok else 'UNEXPECTED'))
        if ok:
            print('\nchannel is alive.  Now run:')
            print('  sudo python3 %s restore ms2130s_backup.bin' % sys.argv[0])
        return 0 if ok else 2

    if mode == 'backup':
        out = args[0] if args else 'backup.bin'
        data = d.read_flash(FLASH_SIZE)
        open(out, 'wb').write(data)
        print('saved %s (%d bytes)' % (out, len(data)))
        return 0

    # restore
    if not args:
        sys.exit('restore needs a firmware file: restore ms2130s_backup.bin')
    data = open(args[0], 'rb').read()
    if len(data) != FLASH_SIZE:
        sys.exit('wrong file size %d, expected %d' % (len(data), FLASH_SIZE))
    if data[0] != 0x3c or data[1] != 0xc3:
        sys.exit('not a firmware image (bad magic %02x %02x)' % (data[0], data[1]))
    hdr, st_hdr, code, st_code = checksum_report(data)
    print('image: header %04x/%04x  code %04x/%04x'
          % (hdr, st_hdr, code, st_code))
    if hdr != st_hdr or code != st_code:
        sys.exit('image checksum mismatch -- refusing to erase anything')

    print('erase ...')
    d.erase()
    print('writing ...')
    d.write_flash(data)
    print('verifying ...')
    back = d.read_flash(FLASH_SIZE)
    if back != data:
        sys.exit('VERIFY FAILED -- do not unplug, run restore again')
    print('OK: flash verified byte-for-byte')
    print('now unplug the card and plug it back in (full power cycle)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
