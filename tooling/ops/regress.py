#!/usr/bin/env python3
"""不碰硬件的回归自检：固件 SHA 基线、描述符 lint、文档链接、文件数、HTML 结构。"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "tooling" / "ops" / "ops_config.json"
BASELINE = ROOT / "firmware" / "SHA256SUMS"


def load_config():
    if not CONFIG_PATH.exists():
        raise RuntimeError("缺少工具配置：%s" % CONFIG_PATH)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


CFG = load_config()
REG = CFG["regress"]


def sha256(path):
    h = __import__("hashlib").sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_baseline():
    if not BASELINE.exists():
        return {}
    rows = {}
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, rel = parts
        rows[rel.strip().lstrip("*")] = digest.upper()
    return rows


def check_sha():
    # 基线是唯一真源：镜像存在但 SUM 里没有，也算失败。
    baseline = read_baseline()
    rows = []
    seen = set()
    for p in sorted((ROOT / "firmware").rglob("*.bin")):
        rel = p.relative_to(ROOT).as_posix()
        got = sha256(p)
        want = baseline.get(rel)
        rows.append({"name": rel, "ok": bool(want) and got == want,
                     "want": want or "UNLISTED（运行 regress.py --update-baseline）",
                     "got": got})
        seen.add(rel)
    for rel, want in sorted(baseline.items()):
        if rel not in seen:
            rows.append({"name": rel, "ok": False, "want": want, "got": "MISSING"})
    return rows


def check_lint():
    rows = []
    for p in sorted((ROOT / "firmware").rglob("*.bin")):
        rel = p.relative_to(ROOT).as_posix()
        # danger/ 的变砖镜像本来就该失败；这里把“失败”当成通过条件。
        danger = "danger" in p.relative_to(ROOT).parts
        r = subprocess.run(
            [sys.executable, str(ROOT / "tooling" / "reverse" / "uac_desc_lint.py"), str(p)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        out = (r.stdout or "") + (r.stderr or "")
        errs = out.count("!!")
        if danger:
            ok = errs > 0 and r.returncode != 0
            expect = "danger>0"
        else:
            ok = errs == 0 and r.returncode == 0
            expect = "0"
        rows.append({"name": rel, "ok": ok,
                     "detail": "exit=%s errors=%s expect=%s" % (r.returncode, errs, expect)})
    return rows


def check_docs():
    """检查根 README 与 docs/*.md 的相对链接；archive 与工具目录不在范围内。"""
    rows = []
    pat = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    files = [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md"))
    for md in files:
        text = md.read_text(encoding="utf-8", errors="replace")
        for target in pat.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#")[0].strip()
            if not clean:
                continue
            p = (md.parent / clean).resolve()
            if not p.exists():
                rows.append({"name": "%s -> %s" % (md.relative_to(ROOT).as_posix(), target),
                             "ok": False, "detail": "目标不存在"})
    return rows


def count_files():
    # skip_dirs 是运行时输出与生成的 dist/，不计入 README/核对记录里的项目文件数。
    skip = set(REG["skip_dirs"])
    n = 0
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if not any(part in skip for part in rel.parts):
            n += 1
    return n


def check_html():
    rows = []
    files = sorted(ROOT.glob("*.html")) + sorted((ROOT / "docs").glob("*.html"))
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        rows.append({
            "name": rel,
            "ok": text.lstrip().lower().startswith("<!doctype html") and "</html>" in text.lower(),
            "detail": "%d 字节" % len(text.encode("utf-8")),
        })
    return rows


def check_paths():
    rows = []
    for rel in REG["critical_paths"]:
        p = ROOT / rel
        rows.append({"name": rel, "ok": p.exists(), "detail": "存在" if p.exists() else "缺失"})
    return rows


def check_ps1_encoding():
    """Windows PowerShell 5.1 只有 UTF-8 BOM 才能可靠解析中文注释。"""
    rows = []
    skip = set(REG["skip_dirs"])
    for p in sorted(ROOT.rglob("*.ps1")):
        rel = p.relative_to(ROOT)
        if "archive" in rel.parts or any(part in skip for part in rel.parts):
            continue
        data = p.read_bytes()
        non_ascii = any(b > 0x7F for b in data)
        bom = data.startswith(b"\xef\xbb\xbf")
        rows.append({
            "name": p.relative_to(ROOT).as_posix(),
            "ok": (not non_ascii) or bom,
            "detail": ("UTF-8 BOM" if bom else "无 BOM") + ("；含非 ASCII" if non_ascii else ""),
        })
    return rows


def update_baseline():
    # 会重写 firmware/SHA256SUMS；只在确认镜像未变时手动执行。
    lines = []
    for p in sorted((ROOT / "firmware").rglob("*.bin")):
        lines.append("%s  %s" % (sha256(p), p.relative_to(ROOT).as_posix()))
    BASELINE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(BASELINE)


def main():
    if "--update-baseline" in sys.argv:
        update_baseline()
        return
    checks = {
        "sha": check_sha(),
        "lint": check_lint(),
        "docs": check_docs(),
        "html": check_html(),
        "paths": check_paths(),
        "scripts": check_ps1_encoding(),
    }
    files = count_files()
    ok = all(r["ok"] for group in checks.values() for r in group)
    print(json.dumps({
        "ok": ok,
        "files": files,
        "checks": checks,
        "summary": {
            "sha": "%d/%d" % (sum(1 for r in checks["sha"] if r["ok"]), len(checks["sha"])),
            "lint": "%d/%d" % (sum(1 for r in checks["lint"] if r["ok"]), len(checks["lint"])),
            "docs_bad": sum(1 for r in checks["docs"] if not r["ok"]),
            "html": "%d/%d" % (sum(1 for r in checks["html"] if r["ok"]), len(checks["html"])),
            "paths": "%d/%d" % (sum(1 for r in checks["paths"] if r["ok"]), len(checks["paths"])),
            "scripts": "%d/%d" % (sum(1 for r in checks["scripts"] if r["ok"]), len(checks["scripts"])),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
