#!/usr/bin/env python3
"""MS2130S_5.1ReverseKit 操作台的本地服务。只绑定 127.0.0.1，不对外网开放。"""

import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
SERVER_STARTED = time.strftime("%Y-%m-%dT%H:%M:%S")
CONFIG_PATH = Path(__file__).with_name("ops_config.json")


def load_config():
    if not CONFIG_PATH.exists():
        raise RuntimeError("缺少工具配置：%s" % CONFIG_PATH)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    server = data.get("server") or {}
    for key in ("port", "port_span"):
        if key not in server:
            raise RuntimeError("ops_config.json 缺少 server.%s" % key)
    workspace = data.get("workspace") or {}
    for key in ("runtime", "recordings", "fixed"):
        if not workspace.get(key):
            raise RuntimeError("ops_config.json 缺少 workspace.%s" % key)
    dev = data.get("device") or {}
    for key in ("vid", "pid", "product", "channels", "sample_rate", "sample_format", "capture_api", "channel_labels", "channel_labels_fixed", "channel_colors",
                "level_display_gain", "flash_estimate_sec", "flash_blocks", "signal_window_sec",
                "poll_ms", "device_cache_sec", "max_record_sec", "min_record_sec",
                "record_default_sec", "record_presets_sec", "verify_record_sec"):
        if key not in dev:
            raise RuntimeError("ops_config.json 缺少 device.%s" % key)
    if (len(dev["channel_labels"]) != dev["channels"]
            or len(dev["channel_labels_fixed"]) != dev["channels"]
            or len(dev["channel_colors"]) != dev["channels"]):
        raise RuntimeError("ops_config.json 的通道标签/颜色数量与 channels 不一致")
    ana = data.get("analysis") or {}
    for key in ("active_rms", "silence_rms", "min_active_channels", "duplicate_tolerance"):
        if key not in ana:
            raise RuntimeError("ops_config.json 缺少 analysis.%s" % key)
    if not (data.get("snapshot") or {}).get("baseline"):
        raise RuntimeError("ops_config.json 缺少 snapshot.baseline")
    reg = data.get("regress") or {}
    for key in ("skip_dirs", "critical_paths"):
        if key not in reg:
            raise RuntimeError("ops_config.json 缺少 regress.%s" % key)
    docs = data.get("docs") or []
    if not docs:
        raise RuntimeError("ops_config.json 缺少 docs")
    for d in docs:
        for key in ("path", "label", "sub"):
            if key not in d:
                raise RuntimeError("ops_config.json 的 docs 条目缺少 %s" % key)
    return data


CFG = load_config()
DEV = CFG["device"]
VID_TOKEN = "VID_" + str(DEV["vid"]).upper()
ANALYSIS = CFG["analysis"]
ALLOWED_DOCS = {str(d["path"]) for d in CFG["docs"]}
HTML_PATH = ROOT / "操作台.html"
CSS_PATH = ROOT / "design-tokens.css"
COMPONENTS_PATH = ROOT / "components.css"
RUNTIME = ROOT / str(CFG["workspace"]["runtime"])
RECORDINGS = ROOT / str(CFG["workspace"]["recordings"])
FIXED = ROOT / str(CFG["workspace"]["fixed"])
TMP = RUNTIME / "tmp"
FIRMWARE_ROOT = ROOT / "firmware"
for _dir in (RUNTIME, TMP, RUNTIME / "logs", RUNTIME / "pip-cache", RUNTIME / "pycache", RECORDINGS, FIXED):
    _dir.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(TMP)
os.environ["TEMP"] = str(TMP)
os.environ.setdefault("PIP_CACHE_DIR", str(RUNTIME / "pip-cache"))
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(RUNTIME / "pycache"))
PORT = int(CFG["server"]["port"])
PORT_SPAN = int(CFG["server"]["port_span"])
JOBS = {}
try:
    IDLE_TIMEOUT_MIN = float(CFG["server"].get("idle_timeout_minutes", 30))
except (TypeError, ValueError):
    IDLE_TIMEOUT_MIN = 30.0
IDLE_TIMEOUT_SEC = max(0.0, IDLE_TIMEOUT_MIN * 60)
LAST_ACTIVITY = time.monotonic()


def touch_activity():
    global LAST_ACTIVITY
    LAST_ACTIVITY = time.monotonic()

DEVICE_CMD = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
    "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
    "Where-Object { $_.InstanceId -like '*" + VID_TOKEN + "*' } | "
    "Select-Object Status,Class,FriendlyName,InstanceId | ConvertTo-Json -Compress"
)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def workspace_path(value, must_exist=False):
    """把用户路径收进项目根；越界路径一律返回 None。"""
    raw = str(value or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    try:
        p = p.resolve()
    except Exception:
        return None
    try:
        p.relative_to(ROOT.resolve())
    except ValueError:
        return None
    if must_exist and (not p.exists() or not p.is_file()):
        return None
    return p


def firmware_path(value):
    """固件只允许从 firmware/ 目录进入刷写链路。"""
    p = workspace_path(value, must_exist=True)
    if not p or p.suffix.lower() != ".bin":
        return None
    try:
        p.relative_to(FIRMWARE_ROOT.resolve())
    except ValueError:
        return None
    return p


def flashable_path(value):
    """刷写只接受 release/ 与 experiments/；danger/ 和快照目录不能进入刷写。"""
    p = firmware_path(value)
    if not p:
        return None
    parts = p.relative_to(FIRMWARE_ROOT.resolve()).parts
    if len(parts) < 2 or parts[0] not in ("release", "experiments"):
        return None
    return p


def latest_valid_snapshot(state=None):
    """当前服务启动后成功读回、通过基线、晚于最近刷写、且属于当前设备实例的快照 Run。"""
    # 两遍扫描：先找最近一次刷写，再挑它之后且属于当前设备实例的有效快照。
    state = state or device_state()
    if not state.get("online"):
        return None
    if not single_device(state):
        return None
    current_ids = {
        str(x.get("InstanceId") or "")
        for x in (state.get("items") or [])
        if x.get("InstanceId")
    }
    scripts = sorted(RUNS.glob("*/manifest.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    last_flash = ""
    for p in scripts:
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("kind") == "flash":
            started = str(m.get("started") or "")
            if started > last_flash:
                last_flash = started
    for p in scripts:
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("kind") != "snapshot":
            continue
        started = str(m.get("started") or "")
        if started < SERVER_STARTED or (last_flash and started <= last_flash):
            continue
        snap = m.get("snapshot") or {}
        dev = m.get("device") or {}
        snap_ids = {
            str(x.get("InstanceId") or "")
            for x in (dev.get("items") or [])
            if x.get("InstanceId")
        }
        if not dev.get("online") or not snap.get("valid") or (m.get("result") or {}).get("exit") != 0:
            continue
        if current_ids and snap_ids and not (current_ids & snap_ids):
            continue
        return m.get("id")
    return None


def latest_run(kind):
    """取最近一条已完成的同类 Run，作为新 Run 的父记录。"""
    for p in sorted(RUNS.glob("*/manifest.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("kind") == kind and (m.get("result") or {}).get("exit") is not None:
            return m.get("id")
    return None


def snapshot_baseline():
    rel = CFG["snapshot"]["baseline"]
    p = ROOT / rel
    if not p.exists():
        return None
    with p.open("rb") as f:
        magic = f.read(2)
    return {"path": rel, "size": p.stat().st_size, "magic": magic}


RUNS = ROOT / "tooling" / "ops" / "runs"
RUNS.mkdir(parents=True, exist_ok=True)
RUN_LOCK = threading.Lock()


def new_run(kind, title, meta=None):
    meta = meta or {}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    rid = "%s_%s" % (stamp, kind)
    with RUN_LOCK:
        n = 1
        while (RUNS / rid).exists():
            n += 1
            rid = "%s_%s_%d" % (stamp, kind, n)
        d = RUNS / rid
        d.mkdir(parents=True)
    manifest = {
        "id": rid,
        "kind": kind,
        "title": title,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "operator": os.environ.get("USERNAME", ""),
        "device": meta.get("device") or device_state(),
        "firmware": meta.get("firmware"),
        "command": meta.get("command"),
        "parent": meta.get("parent"),
        "outputs": [],
        "result": None,
        "notes": meta.get("notes", ""),
    }
    (d / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return rid


def run_path(rid):
    if not re.fullmatch(r"[0-9A-Za-z_]+", rid or ""):
        return None
    d = RUNS / rid
    if not (d / "manifest.json").exists():
        return None
    return d


def update_run(rid, **fields):
    d = run_path(rid)
    if not d:
        return
    p = d / "manifest.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    m.update(fields)
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def finalize_run(j):
    with RUN_LOCK:
        if j.get("finalized"):
            return
        j["finalized"] = True
    rid = j.get("run_id")
    if not rid:
        return
    d = run_path(rid)
    if not d:
        return
    try:
        text = j["log"].read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""
    # 退出码是主判据；这几个关键词只补捉录制/刷写日志里的常见失败。
    low = text.lower()
    failed = any(k in low for k in ("没有找到 6 声道", "could not open device", "no such file"))
    outputs = []
    out = j.get("out_path")
    if out:
        p = Path(out)
        if p.exists():
            try:
                outputs.append({"path": str(p), "sha": sha256(p), "size": p.stat().st_size})
            except Exception:
                pass
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    m["result"] = {"exit": j["p"].returncode, "failed": failed,
                   "elapsed": round(time.time() - j["started"], 1)}
    m["outputs"] = outputs
    m["log_tail"] = text[-3000:]
    log_name = (j.get("kind") or "job") + ".log"
    (d / log_name).write_text(text, encoding="utf-8")
    m["log"] = log_name
    if j.get("kind") == "snapshot" and out:
        snap = Path(out)
        if snap.exists():
            head = snap.read_bytes()[:2]
            base = snapshot_baseline()
            size = snap.stat().st_size
            m["snapshot"] = {
                "size": size,
                "magic": head.hex().upper(),
                "valid": bool(base and head == base["magic"] and size == base["size"]),
                "baseline": ({"path": base["path"], "size": base["size"],
                              "magic": base["magic"].hex().upper()} if base else None),
            }
    (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def finish_sync_run(rid, exit_code, failed, elapsed, outputs=None, extra=None, log_text=None):
    d = run_path(rid)
    if not d:
        return
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    m["result"] = {"exit": exit_code, "failed": failed, "elapsed": elapsed}
    m["outputs"] = outputs or []
    if log_text is not None:
        log_name = (m.get("kind") or "job") + ".log"
        (d / log_name).write_text(log_text, encoding="utf-8")
        m["log"] = log_name
    if extra:
        m.update(extra)
    (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def wav_levels(path, seconds):
    """只读 WAV 尾部 N 秒算每通道 RMS；支持 float32 与 16 bit PCM。

    头只读 256 B：现有录音的 fmt/data 都落在这一段内，避免整段读入内存。
    """
    p = Path(path)
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            head = f.read(min(size, 256))
            if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return None
            pos = 12
            fmt = None
            data_off = None
            data_size = None
            while pos + 8 <= len(head):
                cid = head[pos:pos + 4]
                sz = struct.unpack("<I", head[pos + 4:pos + 8])[0]
                if cid == b"fmt ":
                    fmt = head[pos + 8:pos + 8 + sz]
                elif cid == b"data":
                    data_off = pos + 8
                    data_size = sz
                    break
                pos += 8 + sz + (sz & 1)
            if fmt is None or data_off is None or data_off >= size:
                return None
            tag, ch, rate, _brate, _balign, bits = struct.unpack("<HHIIHH", fmt[:16])
            eff = struct.unpack("<H", fmt[24:26])[0] if tag == 0xFFFE and len(fmt) >= 26 else tag
            if ch < 1 or rate < 1:
                return None
            if eff == 3 and bits == 32:
                step, scale, width = "<f", 1.0, 4
            elif eff == 1 and bits == 16:
                step, scale, width = "<h", 32768.0, 2
            else:
                return None
            bpf = ch * width
            avail = size - data_off
            if data_size and 0 < data_size < avail:
                avail = data_size
            n = int(rate * seconds)
            start = max(data_off, data_off + avail - n * bpf)
            start = data_off + ((start - data_off) // bpf) * bpf
            f.seek(start)
            raw = f.read(data_off + avail - start)
    except Exception:
        return None
    raw = raw[:len(raw) // bpf * bpf]
    sums = [0.0] * ch
    count = 0
    for i in range(0, len(raw), bpf):
        for c in range(ch):
            v = struct.unpack_from(step, raw, i + c * width)[0] / scale
            sums[c] += v * v
        count += 1
    if not count:
        return None
    return [round((v / count) ** 0.5, 5) for v in sums]


def job_progress(j):
    p = j.get("progress_path")
    if not p:
        return None
    p = Path(p)
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    hits = re.findall(r"out_time_us=(\d+)", text)
    if not hits:
        return None
    total = j.get("total_ms")
    if not total:
        return None
    return round(min(99.0, int(hits[-1]) / 1000.0 / total * 100), 1)


def media_duration(path):
    ff = find_ffmpeg()
    if not ff:
        return None
    probe = Path(ff).with_name("ffprobe.exe")
    if not probe.exists():
        found = shutil.which("ffprobe")
        if not found:
            return None
        probe = Path(found)
    try:
        r = subprocess.run(
            [str(probe), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=20,
        )
        return max(1, int(float(r.stdout.strip()) * 1000))
    except Exception:
        return None


def find_ffmpeg():
    """按 FFMPEG_PATH → runtime/bin → venv 内置 → PATH 的顺序找 ffmpeg。"""
    fixed = os.environ.get("FFMPEG_PATH", "").strip()
    if fixed and Path(fixed).exists():
        return fixed
    local = RUNTIME / "bin" / "ffmpeg.exe"
    if local.exists():
        return str(local)
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    return None


def firmware_list():
    items = []
    for p in sorted((ROOT / "firmware").rglob("*.bin")):
        rel = p.relative_to(ROOT).as_posix()
        items.append({
            "name": p.name,
            "path": rel,
            "sha": sha256(p),
            "size": p.stat().st_size,
            "danger": "danger" in p.parts,
        })
    return items


def wav_list():
    items = []
    for p in sorted((ROOT / "captures").rglob("*.wav")):
        rel = p.relative_to(ROOT).as_posix()
        items.append({
            "name": p.name,
            "path": rel,
            "dir": p.parent.name,
            "mb": round(p.stat().st_size / 1048576, 1),
        })
    return items


DEVICE_CACHE = {"at": 0.0, "state": {"online": False, "items": []}}


def live_device_count(state):
    """同型号多台时按 InstanceId 去重；没有实例 ID 的条目单独计数。"""
    live = [
        x for x in (state.get("items") or [])
        if str(x.get("Status", "")).lower() in ("ok", "error", "degraded")
    ]
    ids = {str(x.get("InstanceId") or "") for x in live if x.get("InstanceId")}
    no_id = sum(1 for x in live if not x.get("InstanceId"))
    return len(ids) + no_id


def single_device(state):
    return live_device_count(state) == 1


def device_state(force=False):
    """唯一设备读取入口：状态、运行清单、读回与验收都消费这一份结果。

    Get-PnpDevice 较慢，结果按 device_cache_sec 缓存；动作前用 force=True 复核。
    """
    if force or time.time() - DEVICE_CACHE["at"] > float(DEV["device_cache_sec"]):
        try:
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", DEVICE_CMD],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            )
            raw = (r.stdout or "").strip()
            if raw:
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
            else:
                items = []
        except Exception as e:
            items = [{"Status": "查询失败", "FriendlyName": str(e), "InstanceId": ""}]
        clean = []
        for d in items[:3]:
            clean.append({
                "InstanceId": d.get("InstanceId", ""),
                "Status": d.get("Status", ""),
                "FriendlyName": d.get("FriendlyName", ""),
            })
        online = any(str(x.get("Status", "")).lower() in ("ok", "error", "degraded") for x in clean)
        DEVICE_CACHE["at"] = time.time()
        DEVICE_CACHE["state"] = {"online": online, "items": clean}
    return DEVICE_CACHE["state"]


def check_env():
    items = []

    items.append({
        "name": "Python",
        "ok": True,
        "detail": "%s · %s" % (sys.version.split()[0], sys.executable),
    })

    try:
        import numpy
        items.append({"name": "numpy", "ok": True, "detail": numpy.__version__})
    except Exception as e:
        items.append({"name": "numpy", "ok": False, "detail": "未安装：%s" % e})

    ff = find_ffmpeg()
    items.append({
        "name": "ffmpeg",
        "ok": bool(ff),
        "detail": ff if ff else "未找到（PATH、runtime/bin、imageio-ffmpeg 都没有）",
    })

    release = ROOT / "firmware" / "release"
    for name in ("ms2130s_51unlock_20210624.bin", "ms2130s_backup.bin"):
        p = release / name
        if p.exists():
            items.append({"name": name, "ok": True, "detail": sha256(p)[:16] + "… · %d B" % p.stat().st_size})
        else:
            items.append({"name": name, "ok": False, "detail": "缺失"})

    return items


def spawn(name, cmd, note="", run_id=None, out_path=None, progress_path=None, kind=None, total_ms=None):
    jid = uuid.uuid4().hex[:8]
    log = TMP / ("%s.log" % jid)
    handle = open(log, "w", encoding="utf-8", errors="replace")
    handle.write("任务  %s\n" % name)
    if note:
        handle.write(note.rstrip() + "\n")
    handle.write("\n")
    handle.flush()
    # 子进程的临时目录、pip 缓存、pycache 都改到 runtime/，不写用户目录。
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    env = os.environ.copy()
    env["TMP"] = str(TMP)
    env["TEMP"] = str(TMP)
    env["PIP_CACHE_DIR"] = str(RUNTIME / "pip-cache")
    env["PYTHONPYCACHEPREFIX"] = str(RUNTIME / "pycache")
    p = subprocess.Popen(
        cmd, cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", creationflags=flags, env=env,
    )
    JOBS[jid] = {
        "id": jid, "name": name, "p": p, "log": log, "handle": handle,
        "started": time.time(), "run_id": run_id, "out_path": out_path,
        "progress_path": progress_path, "kind": kind or "",
        "total_ms": total_ms, "finalized": False,
    }
    return jid


def running_job(kinds=None):
    for j in JOBS.values():
        if j["p"].poll() is None and (kinds is None or j.get("kind") in kinds):
            return j
    return None


def job_state(jid):
    j = JOBS.get(jid)
    if not j:
        return {"ok": False, "error": "未知任务"}
    p = j["p"]
    running = p.poll() is None
    try:
        text = j["log"].read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""
    low = text.lower()
    failed = any(k in low for k in ("没有找到 6 声道", "could not open device", "no such file"))
    if not running:
        finalize_run(j)
    snapshot = None
    if not running and j.get("run_id"):
        mp = RUNS / j["run_id"] / "manifest.json"
        if mp.exists():
            try:
                snapshot = json.loads(mp.read_text(encoding="utf-8")).get("snapshot")
            except Exception:
                snapshot = None
    levels = None
    if j.get("kind") == "record" and j.get("out_path"):
        levels = wav_levels(j["out_path"], DEV["signal_window_sec"])
    progress = job_progress(j)
    return {
        "ok": True, "id": jid, "name": j["name"], "running": running,
        "exit": None if running else p.returncode, "log": text, "failed": failed,
        "elapsed": round(time.time() - j["started"], 1),
        "kind": j.get("kind") or "", "out": j.get("out_path"),
        "levels": levels, "progress": progress, "snapshot": snapshot,
    }


def idle_watchdog(server):
    """空闲超时后关闭服务；页面心跳或任何请求都会刷新 LAST_ACTIVITY。"""
    if IDLE_TIMEOUT_SEC <= 0:
        return
    interval = min(30.0, max(5.0, IDLE_TIMEOUT_SEC / 4.0))
    while True:
        time.sleep(interval)
        if running_job() is not None:
            continue
        idle = time.monotonic() - LAST_ACTIVITY
        if idle >= IDLE_TIMEOUT_SEC:
            log("空闲 %g 分钟，自动关闭服务" % (IDLE_TIMEOUT_SEC / 60.0))
            server.shutdown()
            return


class Handler(BaseHTTPRequestHandler):
    server_version = "MS2130S_5.1ReverseKit/1.0"

    def log_message(self, *args):
        pass

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, data, ctype, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_html(self):
        data = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_css(self, path):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/css; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        touch_activity()
        route = urlparse(self.path).path
        if route == "/":
            return self.send_html()
        if route == "/design-tokens.css":
            return self.send_css(CSS_PATH)
        if route == "/components.css":
            return self.send_css(COMPONENTS_PATH)
        if route == "/api/heartbeat":
            return self.send_json({"ok": True})
        if route == "/api/status":
            # 页面唯一状态快照：设备、环境、固件、WAV 一次返回。
            state = device_state(force=True)
            return self.send_json({
                "ok": True,
                "root": str(ROOT),
                "device": state["items"],
                "env": check_env(),
                "firmwares": firmware_list(),
                "wavs": wav_list(),
                "ffmpeg": find_ffmpeg(),
                "snapshot": latest_valid_snapshot(state),
            })
        if route == "/api/runs":
            q = parse_qs(urlparse(self.path).query)
            try:
                limit = min(50, max(1, int((q.get("limit") or ["20"])[0])))
            except ValueError:
                limit = 20
            items = []
            for p in sorted(RUNS.glob("*/manifest.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                try:
                    items.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    pass
            return self.send_json({"ok": True, "runs": items})
        if route == "/api/run":
            q = parse_qs(urlparse(self.path).query)
            rid = (q.get("id") or [""])[0]
            d = run_path(rid)
            if not d:
                return self.send_json({"ok": False, "error": "未知实验记录"}, 404)
            m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            log = m.get("log")
            if log:
                p = d / log
                if p.exists():
                    m["log_tail"] = p.read_text(encoding="utf-8", errors="replace")[-4000:]
            return self.send_json({"ok": True, "run": m})
        if route == "/api/export":
            q = parse_qs(urlparse(self.path).query)
            rid = (q.get("id") or [""])[0]
            d = run_path(rid)
            if not d:
                return self.send_json({"ok": False, "error": "未知实验记录"}, 404)
            m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            result = m.get("result") or {}
            cmd = m.get("command") or []
            cmd_text = " ".join(str(x) for x in cmd) if cmd else "（无命令，见 manifest.json）"
            readme = (
                "MS2130S_5.1ReverseKit 实验记录\n"
                "ID      %s\n类型    %s\n标题    %s\n开始    %s\n操作者  %s\n"
                "父记录  %s\n"
                "结果    exit=%s  failed=%s  elapsed=%ss\n固件    %s\n\n"
                "复现命令\n%s\n\n"
                "说明：本包由操作台的 /api/export 生成。verify.wav 等大文件如果存在会一并打包；"
                "缺失的文件见 manifest.json 的 outputs。\n"
            ) % (
                m.get("id", ""), m.get("kind", ""), m.get("title", ""), m.get("started", ""),
                m.get("operator", ""), m.get("parent") or "（无）",
                result.get("exit"), result.get("failed"), result.get("elapsed"),
                json.dumps(m.get("firmware"), ensure_ascii=False), cmd_text,
            )
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(d.iterdir()):
                    if f.is_file():
                        z.write(f, f.name)
                z.writestr("README.txt", b"\xef\xbb\xbf" + readme.encode("utf-8"))
            return self.send_bytes(buf.getvalue(), "application/zip", rid + ".zip")
        if route == "/api/job":
            q = parse_qs(urlparse(self.path).query)
            jid = (q.get("id") or [""])[0]
            return self.send_json(job_state(jid))
        if route == "/api/config":
            ui_keys = ("vid", "pid", "product", "channels", "sample_rate", "sample_format", "capture_api", "channel_labels", "channel_labels_fixed", "channel_colors",
                       "level_display_gain", "flash_estimate_sec", "flash_blocks", "signal_window_sec",
                       "poll_ms", "max_record_sec", "min_record_sec", "record_default_sec", "record_presets_sec")
            cfg = {k: DEV[k] for k in ui_keys}
            cfg["server"] = CFG["server"]
            cfg["workspace"] = CFG["workspace"]
            cfg["docs"] = CFG["docs"]
            return self.send_json({"ok": True, "config": cfg})
        if route == "/api/ping":
            return self.send_json({"ok": True, "time": time.time()})
        self.send_json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        touch_activity()
        route = urlparse(self.path).path
        body = self.body_json()

        if route == "/api/record":
            if running_job():
                return self.send_json({"ok": False, "error": "已有任务正在运行，先等它结束再录制"}, 400)
            try:
                seconds = int(body.get("seconds") or DEV["record_default_sec"])
            except (TypeError, ValueError):
                return self.send_json({"ok": False, "error": "录制秒数必须是整数"}, 400)
            if seconds < DEV["min_record_sec"] or seconds > DEV["max_record_sec"]:
                return self.send_json({"ok": False, "error": "秒数需在 %d–%d" % (
                    DEV["min_record_sec"], DEV["max_record_sec"])}, 400)
            state = device_state(force=True)
            if not state["online"]:
                return self.send_json({"ok": False, "error": "设备不在线，录制已阻止"}, 400)
            if not single_device(state):
                return self.send_json({"ok": False, "error": "检测到多台同型号设备，只保留一台再录制"}, 400)
            out = str(body.get("out") or "").strip()
            if out:
                target = workspace_path(out)
                if not target or target.suffix.lower() != ".wav":
                    return self.send_json({"ok": False, "error": "输出路径必须在项目工作区内，且为 .wav"}, 400)
                target.parent.mkdir(parents=True, exist_ok=True)
                out = str(target)
            else:
                out = str(RECORDINGS / ("ns2_51_" + time.strftime("%Y%m%d_%H%M%S") + ".wav"))
            script = str(ROOT / "tooling" / "capture" / "rec51.ps1")
            inner = "& '%s' -Seconds %d -Out '%s'" % (script.replace("'", "''"), seconds, out.replace("'", "''"))
            cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                   "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + inner]
            rid = new_run("record", "录制 5.1 · %d s" % seconds, {
                "command": cmd,
                "notes": "输出 %s" % out,
            })
            jid = spawn("录制 5.1", cmd, "时长 %d 秒\n输出 %s" % (seconds, out),
                        run_id=rid, out_path=out, kind="record")
            return self.send_json({"ok": True, "id": jid, "run": rid, "out": out})

        if route == "/api/fix":
            src = workspace_path(body.get("path"), must_exist=True)
            if not src:
                return self.send_json({"ok": False, "error": "输入文件必须在项目工作区内"}, 400)
            kind = body.get("kind") or "wav"
            if kind not in ("wav", "video"):
                return self.send_json({"ok": False, "error": "类型必须是 wav 或 video"}, 400)
            ff = find_ffmpeg()
            if not ff:
                return self.send_json({"ok": False, "error": "找不到 ffmpeg"}, 400)
            out = FIXED / (src.stem + "_fixed" + (".wav" if kind == "wav" else ".mkv"))
            total_ms = media_duration(src)
            progress = TMP / (uuid.uuid4().hex[:8] + ".progress")
            filter_arg = "pan=5.1|c0=c0|c1=c1|c2=c3|c3=c2|c4=c4|c5=c5"
            cmd = [ff, "-hide_banner", "-loglevel", "warning", "-progress", str(progress),
                   "-nostats", "-i", str(src), "-af", filter_arg]
            if kind == "video":
                cmd += ["-c:v", "copy", "-c:a", "pcm_s24le"]
            else:
                cmd += ["-c:a", "pcm_s24le"]
            cmd += ["-y", str(out)]
            rid = new_run("fix", "修通道 %s" % ("视频" if kind == "video" else "WAV"), {
                "command": cmd,
                "parent": latest_run("record"),
                "notes": "输入 %s\n输出 %s" % (src, out),
            })
            jid = spawn("修通道 %s" % ("视频" if kind == "video" else "WAV"), cmd,
                        "输入 %s\n输出 %s" % (src, out),
                        run_id=rid, out_path=str(out), progress_path=str(progress),
                        kind="fix", total_ms=total_ms)
            return self.send_json({"ok": True, "id": jid, "run": rid, "out": str(out)})

        if route == "/api/lint":
            rel = str(body.get("firmware") or "")
            fw = firmware_path(rel)
            if not fw:
                return self.send_json({"ok": False, "error": "固件必须位于项目 firmware/ 工作区内"}, 400)
            rel = fw.relative_to(ROOT).as_posix()
            t0 = time.time()
            r = subprocess.run(
                [sys.executable, str(ROOT / "tooling" / "reverse" / "uac_desc_lint.py"), str(fw)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            )
            output = (r.stdout or "") + (r.stderr or "")
            ok = r.returncode == 0
            rid = new_run("lint", "刷前检查 %s" % fw.name, {
                "firmware": {"path": rel, "sha": sha256(fw), "size": fw.stat().st_size},
                "command": [sys.executable, "tooling/reverse/uac_desc_lint.py", rel],
            })
            d = RUNS / rid
            (d / "lint.txt").write_text(output, encoding="utf-8")
            finish_sync_run(rid, r.returncode, not ok, round(time.time() - t0, 2),
                            outputs=[{"path": str(d / "lint.txt"), "sha": sha256(d / "lint.txt"),
                                      "size": (d / "lint.txt").stat().st_size, "role": "lint"}],
                            extra={"lint": {"exit": r.returncode, "errors": 0 if ok else output.count("!!")}},
                            log_text=output)
            return self.send_json({
                "ok": ok, "exit": r.returncode, "output": output,
                "sha": sha256(fw), "size": fw.stat().st_size, "run": rid,
            })

        if route == "/api/flash":
            # 门控顺序固定：确认码 → 路径 → 设备 → lint → 快照；任一失败都不建 Run。
            if running_job():
                return self.send_json({"ok": False, "error": "已有任务正在运行，先等它结束再刷写"}, 400)
            rel = str(body.get("firmware") or "")
            confirm = str(body.get("confirm") or "")
            if confirm != "FLASH":
                return self.send_json({"ok": False, "error": "确认码必须是 FLASH"}, 400)
            fw = flashable_path(rel)
            if not fw:
                return self.send_json({"ok": False, "error": "固件必须是 firmware/release/ 或 firmware/experiments/ 下的 .bin"}, 400)
            if "danger" in fw.parts:
                return self.send_json({"ok": False, "error": "danger/ 下的固件禁止从操作台刷写"}, 400)
            state = device_state(force=True)
            if not state["online"]:
                return self.send_json({"ok": False, "error": "设备不在线，刷写已阻止"}, 400)
            if not single_device(state):
                return self.send_json({"ok": False, "error": "检测到多台同型号设备，只保留一台再刷写"}, 400)
            rel = fw.relative_to(ROOT).as_posix()
            lint = subprocess.run(
                [sys.executable, str(ROOT / "tooling" / "reverse" / "uac_desc_lint.py"), str(fw)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            )
            if lint.returncode != 0:
                return self.send_json({"ok": False, "error": "lint 未通过，已阻止刷写", "output": lint.stdout}, 400)
            snap_id = latest_valid_snapshot(state)
            if not snap_id:
                return self.send_json({"ok": False, "error": "刷前必须先做一次有效快照：设备在线、属于当前设备实例、本次服务启动后、基线校验通过，且晚于最近一次刷写尝试"}, 400)
            cmd = [str(ROOT / "tooling" / "flash" / "ms213x_flash.exe"), "-w", str(fw)]
            rid = new_run("flash", "刷写 %s" % fw.name, {
                "firmware": {"path": rel, "sha": sha256(fw), "size": fw.stat().st_size},
                "command": cmd,
                "parent": snap_id,
                "notes": "刷完必须拔卡身断电 10 秒",
            })
            jid = spawn("刷写 %s" % fw.name, cmd,
                        "目标 %s\nSHA %s" % (fw.relative_to(ROOT).as_posix(), sha256(fw)),
                        run_id=rid, kind="flash")
            return self.send_json({"ok": True, "id": jid, "run": rid})

        if route == "/api/snapshot":
            if running_job():
                return self.send_json({"ok": False, "error": "已有任务正在运行，先等它结束再读回"}, 400)
            state = device_state(force=True)
            if not state["online"]:
                return self.send_json({"ok": False, "error": "设备不在线，无法读回"}, 400)
            if not single_device(state):
                return self.send_json({"ok": False, "error": "检测到多台同型号设备，只保留一台再读回"}, 400)
            # 目录不存在就建；文件名带时间戳，不覆盖旧快照。
            snaps = ROOT / "firmware" / "snapshots"
            snaps.mkdir(parents=True, exist_ok=True)
            out = snaps / (time.strftime("%Y%m%d_%H%M%S") + "_readback.bin")
            cmd = [str(ROOT / "tooling" / "flash" / "ms213x_flash.exe"), "-r", str(out)]
            mins = max(1, int(round(DEV["flash_estimate_sec"] / 60)))
            note = "输出 %s；约 %d 分钟，不能拔 USB" % (out, mins)
            rid = new_run("snapshot", "读回当前固件", {
                "command": cmd,
                "notes": note,
            })
            jid = spawn("读回固件", cmd, note, run_id=rid, out_path=str(out), kind="snapshot")
            return self.send_json({"ok": True, "id": jid, "run": rid, "out": str(out)})

        if route == "/api/verify":
            # 四项：枚举、录制、格式、独立性；视频只标人工复核。
            if running_job():
                return self.send_json({"ok": False, "error": "已有任务正在运行，先等它结束再验收"}, 400)
            t0 = time.time()
            state = device_state(force=True)
            if not state["online"]:
                return self.send_json({"ok": False, "error": "设备不在线，验收已阻止"}, 400)
            if not single_device(state):
                return self.send_json({"ok": False, "error": "检测到多台同型号设备，只保留一台再验收"}, 400)
            online = state["items"]
            rid = new_run("verify", "刷后验收", {"parent": latest_run("flash")})
            d = RUNS / rid
            items = []
            items.append({
                "name": "设备枚举",
                "ok": bool(online),
                "detail": (online[0].get("InstanceId", "") if online else "未检测到 " + VID_TOKEN),
            })
            wav = d / "verify.wav"
            script = str(ROOT / "tooling" / "capture" / "rec51.ps1")
            inner = "& '%s' -Seconds %d -Out '%s'" % (
                script.replace("'", "''"), DEV["verify_record_sec"], str(wav).replace("'", "''"))
            rec = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + inner],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
            )
            rec_ok = wav.exists() and wav.stat().st_size > 44
            items.append({
                "name": "录制 %d 秒" % DEV["verify_record_sec"],
                "ok": rec_ok,
                "detail": "退出 %s%s" % (rec.returncode, "" if rec_ok else " · 没有生成 WAV"),
            })
            audio = None
            if rec_ok:
                vr = subprocess.run(
                    [sys.executable, str(ROOT / "tooling" / "ops" / "verify_wav.py"), str(wav)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40,
                )
                try:
                    audio = json.loads(vr.stdout)
                except Exception:
                    audio = None
            fmt_ok = bool(audio and audio.get("channels") == DEV["channels"]
                          and audio.get("rate") == DEV["sample_rate"])
            items.append({
                "name": "录音格式",
                "ok": fmt_ok,
                "detail": ("%sch / %sHz / %sbit" % (audio.get("channels"), audio.get("rate"), audio.get("bits"))
                           if audio else "无法解析 WAV"),
            })
            verdict = (audio or {}).get("verdict", "")
            items.append({
                "name": "通道独立性",
                "ok": verdict == "pass",
                "detail": ("verdict=%s · active=%s · 重复=%s" % (
                    verdict, (audio or {}).get("active"), (audio or {}).get("duplicates"))
                           if audio else "无分析结果"),
            })
            items.append({"name": "视频通路", "ok": None, "detail": "抓一帧人工复核，未自动判定"})
            overall = all(i["ok"] for i in items if i["ok"] is not None)
            outputs = []
            if wav.exists():
                outputs.append({"path": str(wav), "sha": sha256(wav), "size": wav.stat().st_size, "role": "verify"})
            (d / "verify.json").write_text(
                json.dumps({"items": items, "audio": audio, "wav": str(wav)}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            finish_sync_run(rid, 0 if overall else 1, not overall,
                            round(time.time() - t0, 1), outputs=outputs,
                            extra={"verify": items},
                            log_text=json.dumps({"items": items, "audio": audio}, ensure_ascii=False, indent=2))
            return self.send_json({"ok": True, "run": rid, "items": items, "overall": overall})

        if route == "/api/diff":
            def fw_file(rel):
                p = (ROOT / str(rel or "")).resolve()
                base = (ROOT / "firmware").resolve()
                if base not in p.parents or not p.exists():
                    return None
                return p

            pa = fw_file(body.get("a"))
            pb = fw_file(body.get("b"))
            if not pa or not pb:
                return self.send_json({"ok": False, "error": "两个固件都要在 firmware/ 下"}, 400)
            da = pa.read_bytes()
            db = pb.read_bytes()
            # 按 1 KB 块只记同/不同；diff_bytes 也按整块累计，不做字节级精确统计。
            block = 1024
            blocks = []
            diff_bytes = 0
            for off in range(0, max(len(da), len(db)), block):
                x = da[off:off + block]
                y = db[off:off + block]
                same = x == y
                blocks.append(1 if same else 0)
                if not same:
                    diff_bytes += max(len(x), len(y))
            return self.send_json({
                "ok": True,
                "a": pa.relative_to(ROOT).as_posix(),
                "b": pb.relative_to(ROOT).as_posix(),
                "sha_a": sha256(pa), "sha_b": sha256(pb),
                "size_a": len(da), "size_b": len(db),
                "block_size": block, "blocks": blocks,
                "diff_bytes": diff_bytes,
            })

        if route == "/api/regress":
            t0 = time.time()
            r = subprocess.run(
                [sys.executable, str(ROOT / "tooling" / "ops" / "regress.py")],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            )
            try:
                data = json.loads(r.stdout)
            except Exception:
                data = {"ok": False, "error": (r.stdout or "") + (r.stderr or "")}
            rid = new_run("regress", "回归自检", {
                "command": [sys.executable, "tooling/ops/regress.py"],
            })
            d = RUNS / rid
            (d / "regress.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            finish_sync_run(rid, 0 if data.get("ok") else 1, not data.get("ok"),
                            round(time.time() - t0, 1),
                            outputs=[{"path": str(d / "regress.json"), "sha": sha256(d / "regress.json"),
                                      "size": (d / "regress.json").stat().st_size, "role": "regress"}],
                            extra={"regress": data.get("summary")},
                            log_text=r.stdout or (r.stderr or ""))
            return self.send_json({"ok": True, "run": rid, "result": data})

        if route == "/api/open":
            target = str(body.get("target") or "")
            if target not in ALLOWED_DOCS:
                return self.send_json({"ok": False, "error": "不在白名单"}, 400)
            p = ROOT / target
            if not p.exists():
                return self.send_json({"ok": False, "error": "文件不存在：%s" % target}, 404)
            os.startfile(str(p))
            return self.send_json({"ok": True})

        if route == "/api/stop":
            jid = str(body.get("id") or "")
            j = JOBS.get(jid)
            if not j:
                return self.send_json({"ok": False, "error": "未知任务"}, 404)
            if j.get("kind") in ("flash", "snapshot"):
                return self.send_json({"ok": False, "error": "刷写/读回过程中禁止停止，强行中断可能损坏设备"}, 400)
            subprocess.run(["taskkill", "/PID", str(j["p"].pid), "/T", "/F"],
                           capture_output=True, text=True)
            return self.send_json({"ok": True})

        self.send_json({"ok": False, "error": "not found"}, 404)


def log(msg):
    try:
        with open(TMP / "ops.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass
    if sys.stdout:
        print(msg)


def main():
    if not HTML_PATH.exists():
        log("缺少 操作台.html：%s" % HTML_PATH)
        return
    if not CSS_PATH.exists():
        log("缺少 design-tokens.css：%s" % CSS_PATH)
        return
    if not COMPONENTS_PATH.exists():
        log("缺少 components.css：%s" % COMPONENTS_PATH)
        return
    for port in range(PORT, PORT + PORT_SPAN):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        log("%d–%d 都被占用，无法启动。" % (PORT, PORT + PORT_SPAN - 1))
        return
    url = "http://127.0.0.1:%d/" % port
    state_path = TMP / "server.json"
    state_path.write_text(json.dumps({
        "pid": os.getpid(),
        "script": str(Path(__file__).resolve()),
        "port": port,
        "started": SERVER_STARTED,
    }, ensure_ascii=False), encoding="utf-8")
    (TMP / "port.txt").write_text(str(port), encoding="ascii")
    log("=" * 60)
    log("  MS2130S_5.1ReverseKit 操作台")
    log("  %s" % url)
    if IDLE_TIMEOUT_SEC > 0:
        log("  空闲 %g 分钟自动退出" % IDLE_TIMEOUT_MIN)
    else:
        log("  自动退出已禁用")
    log("=" * 60)
    if "--no-browser" not in sys.argv and os.environ.get("OPS_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if IDLE_TIMEOUT_SEC > 0:
        threading.Thread(target=idle_watchdog, args=(server,), name="idle-watchdog", daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            (TMP / "server.json").unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
