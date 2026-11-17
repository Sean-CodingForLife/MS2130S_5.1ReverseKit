import numpy as np, os, sys
D = r'D:\Backups\workspace\_resume'
import wav_scan as W

def load(fn):
    tag, sub, ch, rate, bits, pcm = W.read_wav(os.path.join(D, fn))
    return W.decode(tag, sub, ch, bits, pcm), rate

for fn, t0 in [('ns2_selftest.wav', 11.0), ('game_51.wav', 2.0), ('ns2_51_test.wav', 2.0)]:
    x, rate = load(fn)
    print('=' * 78); print(fn, x.shape)
    i0 = int(t0 * rate)
    seg = x[i0:i0 + 8]
    print('  raw int16 of 8 frames:')
    for r in seg:
        print('   ', ' '.join('%7d' % round(v * 32768) for v in r))
    # bit equality
    print('  bitwise-equal fraction per pair (offset 3):')
    for a, b in [(0, 3), (1, 4), (2, 5), (0, 1), (0, 2), (1, 2)]:
        eq = (x[:, a] == x[:, b]).mean()
        print('    c%d==c%d : %.4f' % (a, b, eq))
    # correlation over whole file and over active part
    y = x[i0:i0 + rate * 2]
    print('  corr over 2s window at %.1fs:' % t0)
    for a, b in [(0, 3), (1, 4), (2, 5)]:
        c = np.corrcoef(y[:, a], y[:, b])[0, 1]
        print('    c%d vs c%d : %.6f' % (a, b, c))
    # lag scan: does c3 = shifted/filtered c0?
    a = x[:, 0].astype(np.float64); b = x[:, 3].astype(np.float64)
    print('  lag scan c0 vs c3 (normalized dot), lags -4..4:')
    for lag in range(-4, 5):
        if lag >= 0:
            u, v = a[:len(a)-lag], b[lag:]
        else:
            u, v = a[-lag:], b[:len(b)+lag]
        print('    lag %+d : %.6f' % (lag, float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12))))
    # low byte structure
    iv = np.round(x[:, :6] * 32768).astype(np.int32)
    print('  int16 parity (fraction even) per channel:', ['%.3f' % (iv[:, k] % 2 == 0).mean() for k in range(6)])
    print()

# stereo pairing test: is the buffer a 2ch stream read as 6ch?
x, rate = load('ns2_selftest.wav')
i0 = int(11.0 * rate)
w = x[i0:i0 + rate].astype(np.float64)
print('=' * 78)
print('Decimation hypothesis: frame -> [L0,R0,L1,R1,L2,R2]')
print('  corr(c0,c2)=%.4f corr(c0,c4)=%.4f corr(c1,c3)=%.4f corr(c1,c5)=%.4f' % (
    np.corrcoef(w[:,0], w[:,2])[0,1], np.corrcoef(w[:,0], w[:,4])[0,1],
    np.corrcoef(w[:,1], w[:,3])[0,1], np.corrcoef(w[:,1], w[:,5])[0,1]))
print('  corr(c0,c3)=%.4f corr(c1,c4)=%.4f corr(c2,c5)=%.4f' % (
    np.corrcoef(w[:,0], w[:,3])[0,1], np.corrcoef(w[:,1], w[:,4])[0,1], np.corrcoef(w[:,2], w[:,5])[0,1]))
# spectral check of the two groups
for k in range(6):
    s = np.abs(np.fft.rfft(w[:, k] * np.hanning(len(w))))
    f = np.fft.rfftfreq(len(w), 1/rate)
    cen = (s * f).sum() / (s.sum() + 1e-12)
    print('  ch%d centroid %.0f Hz  rms %.4f' % (k, cen, np.sqrt((w[:,k]**2).mean())))
