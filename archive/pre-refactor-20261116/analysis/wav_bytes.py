import numpy as np, os, struct
D = r'D:\Backups\workspace\_resume'
import wav_scan as W

def load(fn):
    tag, sub, ch, rate, bits, pcm = W.read_wav(os.path.join(D, fn))
    return W.decode(tag, sub, ch, bits, pcm), rate

def dump(fn, t0, nframes=12):
    x, rate = load(fn)
    i0 = int(t0 * rate)
    print('=' * 90)
    print(fn, '@%.3fs' % t0)
    raw = np.round(x[i0:i0 + nframes] * 32768).astype(np.int64)
    print('  int16 words (hex):')
    for r in raw:
        print('   ', ' '.join('%04X' % (int(v) & 0xFFFF) for v in r))
    print('  int16 words (dec):')
    for r in raw:
        print('   ', ' '.join('%7d' % v for v in r))
    b = bytearray()
    for r in raw:
        for v in r:
            b += struct.pack('<h', int(v))
    print('  bytes LE, 4-byte groups as float32:')
    for k in range(0, min(len(b), 96), 4):
        f = struct.unpack('<f', bytes(b[k:k+4]))[0]
        print('    off %3d : %s  f32=%g' % (k, ' '.join('%02X' % c for c in b[k:k+4]), f))
    # check periodic byte zero
    arr = np.frombuffer(bytes(b), dtype=np.uint8).reshape(-1, 12)
    print('  per-byte-of-frame: fraction zero')
    for c in range(12):
        print('    byte%2d : zero=%.2f' % (c, (arr[:, c] == 0).mean()))
    print('  int32 words of the frame (6 words?):')
    a32 = np.frombuffer(bytes(b), dtype='<i4')
    print('   ', ' '.join('%d' % v for v in a32[:12]))

dump('ns2_51_test.wav', 2.0)
dump('ns2_selftest.wav', 11.0)
dump('ns2_selftest.wav', 15.5)
