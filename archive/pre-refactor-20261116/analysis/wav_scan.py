import sys, os, struct, wave
import numpy as np

D = r'D:\Backups\workspace\_resume'
FMT = {1: 'PCM', 3: 'FLOAT', 0xFFFE: 'EXT'}

def read_wav(path):
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:4] == b'RIFF' and data[8:12] == b'WAVE'
    pos = 12
    fmt = None
    pcm = None
    while pos + 8 <= len(data):
        cid = data[pos:pos+4]
        sz = struct.unpack('<I', data[pos+4:pos+8])[0]
        body = data[pos+8:pos+8+sz]
        if cid == b'fmt ':
            fmt = body
        elif cid == b'data':
            pcm = body
        pos += 8 + sz + (sz & 1)
    tag, ch, rate, brate, balign, bits = struct.unpack('<HHIIHH', fmt[:16])
    sub = None
    if tag == 0xFFFE:
        sub = struct.unpack('<H', fmt[24:26])[0]
    return tag, sub, ch, rate, bits, pcm

def decode(tag, sub, ch, bits, pcm):
    eff = sub if tag == 0xFFFE else tag
    if eff == 3:
        a = np.frombuffer(pcm[:len(pcm)//4*4], dtype='<f4')
    elif eff == 1 and bits == 16:
        a = np.frombuffer(pcm[:len(pcm)//2*2], dtype='<i2').astype(np.float32) / 32768.0
    elif eff == 1 and bits == 24:
        b = np.frombuffer(pcm[:len(pcm)//3*3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float32) / float(1 << 23)
        a = v
    elif eff == 1 and bits == 32:
        a = np.frombuffer(pcm[:len(pcm)//4*4], dtype='<i4').astype(np.float32) / 2147483648.0
    else:
        raise SystemExit('unsupported fmt %s/%s/%s' % (tag, sub, bits))
    n = len(a) // ch
    return a[:n*ch].reshape(n, ch)

def pairmatrix(x, nmax=6):
    m = x[:, :nmax]
    D = np.zeros((nmax, nmax))
    for i in range(nmax):
        for j in range(nmax):
            d = np.abs(m[:, i] - m[:, j])
            D[i, j] = d.mean()
    return D

def main():
    files = sys.argv[1:] or [f for f in sorted(os.listdir(D)) if f.lower().endswith('.wav')]
    for fn in files:
        p = os.path.join(D, fn)
        if not os.path.exists(p):
            continue
        tag, sub, ch, rate, bits, pcm = read_wav(p)
        x = decode(tag, sub, ch, bits, pcm)
        dur = len(x) / rate
        print('=' * 78)
        print('%s  tag=%s/%s ch=%d rate=%d bits=%d  frames=%d  %.2fs' %
              (fn, FMT.get(tag, tag), FMT.get(sub, sub), ch, rate, bits, len(x), dur))
        rms = np.sqrt((x.astype(np.float64) ** 2).mean(axis=0))
        print('  RMS/ch : ' + ' '.join('c%d=%.4f' % (i, r) for i, r in enumerate(rms)))
        print('  std/ch : ' + ' '.join('c%d=%.4f' % (i, s) for i, s in enumerate(x.astype(np.float64).std(axis=0))))
        if ch >= 2:
            Dm = pairmatrix(x, min(ch, 6))
            print('  mean|ci-cj| matrix:')
            for i in range(Dm.shape[0]):
                print('    c%d ' % i + ' '.join('%8.4f' % v for v in Dm[i]))
            # exact duplicate offset search
            for off in (1, 2, 3, 4, 5):
                if off < ch:
                    d = np.abs(x[:, :ch-off] - x[:, off:]).mean(axis=0)
                    print('    offset %d dup: ' % off + ' '.join('%d:%.4f' % (k, v) for k, v in enumerate(d)))
        # blockwise channel activity (0.5 s blocks)
        blk = int(rate * 0.5)
        nb = len(x) // blk
        if nb >= 4 and nb <= 400:
            act = []
            for b in range(nb):
                seg = x[b*blk:(b+1)*blk].astype(np.float64)
                r = np.sqrt((seg ** 2).mean(axis=0))
                act.append(r)
            act = np.array(act)
            mx = act.max() or 1
            print('  0.5s block RMS (rows=t, cols=c), normalized to file max %.3f:' % mx)
            step = max(1, nb // 40)
            for b in range(0, nb, step):
                print('    %6.1fs ' % (b*0.5) + ' '.join('%.2f' % v for v in act[b] / mx))
        print()

main()
