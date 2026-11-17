#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uac_desc_lint.py -- validate the USB configuration descriptors inside an
MS2130S firmware image *before* flashing it.

This mirrors what a host USB stack does: walk the descriptors by bLength,
and complain about anything a host would refuse.  The check that matters most
here is `bNumEndpoints` vs the number of endpoint descriptors that actually
follow an interface -- Windows rejects the whole configuration descriptor (and
therefore every interface, including the HID flash channel) when they disagree.

    python uac_desc_lint.py fw.bin
exit code 0 = all configs look parseable, 1 = at least one error
"""

import sys

DT_CONFIG, DT_INTERFACE, DT_ENDPOINT, DT_CS_INTERFACE = 0x02, 0x04, 0x05, 0x24
DT_SS_COMPANION = 0x30


def find_configs(blob):
    out = []
    for i in range(len(blob) - 9):
        if blob[i] == 0x09 and blob[i + 1] == DT_CONFIG:
            total, nintf = blob[i + 2] | (blob[i + 3] << 8), blob[i + 4]
            if 32 <= total <= 4096 and 1 <= nintf <= 16:
                out.append(i)
    return out


def lint(blob, off):
    total = blob[off + 2] | (blob[off + 3] << 8)
    nintf = blob[off + 4]
    errs, notes = [], []
    end = off + total
    if end > len(blob):
        errs.append('wTotalLength %d runs past end of image' % total)
        return errs, notes

    p = off
    seen = set()
    sum_len = 0
    while p < end:
        ln = blob[p]
        if ln < 2 or p + ln > end:
            errs.append('descriptor at +0x%X has bogus bLength %d' % (p - off, ln))
            break
        dt = blob[p + 1]
        sum_len += ln
        if dt == DT_INTERFACE:
            num, alt, nep = blob[p + 2], blob[p + 3], blob[p + 4]
            seen.add(num)
            # count endpoint descriptors that really follow this interface
            q = p + ln
            real_ep = 0
            while q < end:
                l2 = blob[q]
                if l2 < 2:
                    break
                if blob[q + 1] == DT_INTERFACE:
                    break
                if blob[q + 1] == DT_ENDPOINT:
                    real_ep += 1
                q += l2
            if real_ep != nep:
                errs.append(
                    'interface %d alt %d (desc +0x%X): bNumEndpoints=%d '
                    'but %d endpoint descriptor(s) follow'
                    % (num, alt, p - off, nep, real_ep))
            notes.append('  intf %d alt %d  eps %d  (+0x%X)'
                         % (num, alt, nep, p - off))
        p += ln

    if sum_len != total:
        errs.append('descriptor lengths sum to %d, wTotalLength says %d'
                    % (sum_len, total))
    if len(seen) != nintf:
        errs.append('bNumInterfaces=%d but found %d distinct interface numbers'
                    % (nintf, len(seen)))
    return errs, notes


def main(path):
    blob = open(path, 'rb').read()
    cfgs = find_configs(blob)
    if not cfgs:
        print('no configuration descriptor found')
        return 1
    bad = 0
    for off in cfgs:
        errs, notes = lint(blob, off)
        tag = 'config @0x%05X (%d B, %d interfaces)' % (
            off, blob[off + 2] | (blob[off + 3] << 8), blob[off + 4])
        print(('FAIL  ' if errs else 'ok    ') + tag)
        for n in notes:
            print(n)
        for e in errs:
            print('   !! ' + e)
        bad += bool(errs)
    print('\n%d configuration descriptor(s), %d with errors' % (len(cfgs), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
