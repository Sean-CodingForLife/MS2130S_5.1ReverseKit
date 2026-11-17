#!/usr/bin/env python3
"""读一段 WAV，输出通道 RMS、通道相关、重复检测和格式 verdict。只用标准库。"""
import json
import struct
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("ops_config.json")
# sample_format 到 (WAVE format tag, bits) 的映射；0xFFFE 是 EXTENSIBLE，实际看子格式。
FORMAT_SPECS = {
    "float32": (3, 32),
    "pcm16": (1, 16),
    "pcm24": (1, 24),
}


def load_config():
    if not CONFIG_PATH.exists():
        raise RuntimeError("缺少工具配置：%s" % CONFIG_PATH)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_wav(path):
    """整段读入后按 chunk 拼出 fmt/data；验收录音只有几十秒，不做流式分块。"""
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("不是 RIFF/WAVE")
    pos = 12
    fmt = None
    pcm = None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        sz = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + sz]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            pcm = body
        pos += 8 + sz + (sz & 1)
    if fmt is None or pcm is None:
        raise ValueError("缺少 fmt 或 data")
    tag, ch, rate, _brate, _balign, bits = struct.unpack("<HHIIHH", fmt[:16])
    sub = None
    if tag == 0xFFFE and len(fmt) >= 26:
        sub = struct.unpack("<H", fmt[24:26])[0]
    return tag, sub, ch, rate, bits, pcm


def decode(tag, sub, ch, bits, pcm):
    eff = sub if tag == 0xFFFE else tag
    if eff == 3 and bits == 32:
        step = "<f"
        scale = 1.0
        raw = pcm[:len(pcm) // 4 * 4]
    elif eff == 1 and bits == 16:
        step = "<h"
        scale = 32768.0
        raw = pcm[:len(pcm) // 2 * 2]
    # 24 bit 没有 struct 原生格式，手工做符号扩展，再按 2^23 归一化。
    elif eff == 1 and bits == 24:
        raw = pcm[:len(pcm) // 3 * 3]
        vals = []
        for i in range(0, len(raw), 3):
            v = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if v >= 1 << 23:
                v -= 1 << 24
            vals.append(v / float(1 << 23))
        return [vals[c::ch] for c in range(ch)]
    else:
        raise ValueError("不支持的格式 %s/%s" % (tag, bits))

    size = struct.calcsize(step)
    vals = []
    for i in range(0, len(raw), size * ch):
        for c in range(ch):
            vals.append(struct.unpack_from(step, raw, i + c * size)[0] / scale)
    return [vals[c::ch] for c in range(ch)]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    if not path:
        raise SystemExit("用法：verify_wav.py <file.wav>")
    cfg = load_config()
    dev = cfg["device"]
    ana = cfg["analysis"]
    expect_ch = int(dev["channels"])
    expect_rate = int(dev["sample_rate"])
    active_rms = float(ana["active_rms"])
    silence_rms = float(ana["silence_rms"])
    min_active = int(ana["min_active_channels"])
    dup_tol = float(ana["duplicate_tolerance"])

    tag, sub, ch, rate, bits, pcm = read_wav(path)
    chans = decode(tag, sub, ch, bits, pcm)
    eff_tag = sub if tag == 0xFFFE else tag
    expect_fmt = dev.get("sample_format", "")
    expect_tag, expect_bits = FORMAT_SPECS.get(expect_fmt, (None, None))
    n = min(len(c) for c in chans) if chans else 0
    rms = []
    for c in chans:
        if not c:
            rms.append(0.0)
            continue
        s = sum(v * v for v in c) / len(c)
        rms.append(round(s ** 0.5, 6))

    step = max(1, n // 20000)
    pairs = []
    for i in range(ch):
        for j in range(i + 1, ch):
            a = chans[i][:n:step]
            b = chans[j][:n:step]
            if not a or not b:
                pairs.append(0.0)
                continue
            sa = sum(x * x for x in a) ** 0.5
            sb = sum(y * y for y in b) ** 0.5
            if sa == 0 or sb == 0:
                pairs.append(0.0)
                continue
            pairs.append(round(sum(x * y for x, y in zip(a, b)) / (sa * sb), 4))

    duplicates = []
    for i in range(ch):
        for j in range(i + 1, ch):
            a = chans[i][:n:step]
            b = chans[j][:n:step]
            if a and b and max(abs(x - y) for x, y in zip(a, b)) < dup_tol:
                duplicates.append([i, j])

    active = [i for i, v in enumerate(rms) if v > active_rms]
    format_ok = ch == expect_ch and rate == expect_rate
    if expect_tag is not None:
        format_ok = format_ok and eff_tag == expect_tag and bits == expect_bits
    # 判定顺序固定：格式错优先报 format-fail，再判静音、重复和有效通道数。
    if not format_ok:
        verdict = "format-fail"
    elif max(rms) < silence_rms:
        verdict = "silent"
    elif duplicates:
        verdict = "duplicate"
    elif len(active) >= min_active:
        verdict = "pass"
    else:
        verdict = "low-signal"

    print(json.dumps({
        "ok": True,
        "channels": ch,
        "rate": rate,
        "bits": bits,
        "tag": tag,
        "effective_tag": eff_tag,
        "frames": n,
        "expected_channels": expect_ch,
        "expected_rate": expect_rate,
        "expected_format": expect_fmt,
        "expected_bits": expect_bits,
        "rms": rms,
        "active": active,
        "corr_pairs": pairs,
        "duplicates": duplicates,
        "verdict": verdict,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
