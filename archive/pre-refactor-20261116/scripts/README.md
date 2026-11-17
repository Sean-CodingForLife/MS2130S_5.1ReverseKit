# scripts

刷写、描述符、寄存器、WASAPI 脚本。PowerShell 脚本直接在 Windows 跑；Python 脚本用系统 `python`（3.13）。

## 刷写与固件

| 脚本 | 用法 | 说明 |
|---|---|---|
| `uac_desc_lint.py` | `python uac_desc_lint.py <fw.bin>` | 刷前必跑。按 `bLength` 走一遍配置描述符，检查 `bNumEndpoints` 与实际端点数、长度和、`bNumInterfaces`。0 错误才刷 |
| `mk_alt3_usb3only.py` | `python mk_alt3_usb3only.py backup.bin out.bin` | 从原厂生成解锁固件：只改 USB3 配置，删 alt1/alt2 整块，`wTotalLength` 减 98，重算代码校验。序列号需要另外改 |
| `ms213x_uac_tool.py` | `python ms213x_uac_tool.py scan fw.bin` | 扫描 EDID 与 UAC1 `FORMAT_TYPE_I`，打印通道数、位深、采样率与端点需求 |
|  | `python ms213x_uac_tool.py patch fw.bin --channels 6 --out out.bin` | 只改 `bNrChannels` 与匹配端点包长，**不修校验和** |
| `ms213x_dump.ps1` | `powershell -File ms213x_dump.ps1 -Dump backup.bin` | 通过厂商 HID 读整片 flash，只读 |
| `ms213x_restore.py` | `sudo python3 ms213x_restore.py probe` | Linux usbfs 探测 |
|  | `sudo python3 ms213x_restore.py backup out.bin` | Linux 读整片 |
|  | `sudo python3 ms213x_restore.py restore backup.bin` | Linux 刷写。擦除前检查 magic `3C C3` 与校验和 |

`ms213x_dump.ps1`、`ms213x_restore.py` 的协议来自 `steve-m/ms213x_flash`（MIT），许可证在 `tools/`。

## 寄存器

| 脚本 | 用法 | 说明 |
|---|---|---|
| `ms213x_regs.ps1` | `powershell -File ms213x_regs.ps1 0xF00B 0xF00E` | 读 XDATA 字寄存器，默认可读 9 个地址 |
| `ms213x_xdata.ps1` | `powershell -File ms213x_xdata.ps1 -Start 0xF000 -End 0xFFFF -Out xd.bin` | 批量读 XDATA |

`ms213x_xdata.ps1` 的 `-Out` 默认值是 `D:\Backups\workspace\xdata_dump.bin`，该目录已不存在。**运行时必须显式传 `-Out`**，否则写入失败。

HID 读写的两个细节：

- 命令 `0xb5` 读、`0xb6` 写；读回值在响应缓冲区 `buf[4]`，不是 `buf[3]`。
- 设备可能枚举出多个 HID 路径（历史实例残留），脚本会逐个尝试，选能打开的那个。
- 单字节读写不会破坏固件，但盲写未知寄存器有把芯片写挂的风险。写前先读原值备份。

## WASAPI

| 脚本 | 用法 | 说明 |
|---|---|---|
| `wasapi_probe.ps1` | `powershell -File wasapi_probe.ps1 -NamePart USB3` | 枚举端点支持的 shared/exclusive 格式。用来证明 Windows 只暴露一个 alt |
| `wasapi_rec.ps1` | `powershell -File wasapi_rec.ps1` | 2ch 录制 |
| `wasapi_rec6.ps1` | `powershell -File wasapi_rec6.ps1 -GuidPart <8位> -Seconds 10 -Out out.wav` | 6ch 录制。`-Out` 默认值同样指向已不存在的 `D:\Backups\workspace`，必须显式传 |
| `wasapi_play.ps1` | `powershell -File wasapi_play.ps1 -GuidPart <8位>` | 在 ch0–ch7 依次播放 400/600/…/1800 Hz 正弦，每声道 1.2 s、间隔 0.4 s，幅度 0.25 |

6 声道录制必须走 WASAPI。DirectShow（ffmpeg dshow）只给 2 声道。

## 设备排查

这些是当时排查枚举问题留下的，日常用不到：

| 脚本 | 作用 |
|---|---|
| `devlist.ps1` | 列出显示器 / 音频 / 显卡设备 |
| `devparent.ps1` | 查 `USB\VID_345F&PID_2132\20210629` 的父设备与位置信息（硬编码实例 ID） |
| `devstate.ps1` | 查 4 个历史实例的状态 + 采集端点注册表 |
| `devtime.ps1` / `devtime2.ps1` | 查设备到达 / 移除时间 |
| `monparent.ps1` | 查 `HD TO USB` 显示器的父设备 |
| `usbprobe.ps1` | 10 秒采样 `VID_345F` 是否在线，附最近 USB 事件日志 |
| `ms213x_probe.ps1` | 探测 HID 接口与 feature report 能力 |

## 危险

| 脚本 | 说明 |
|---|---|
| `patch_alt3.py` | **不要运行。** 它把 alt1/alt2 的 `bNumEndpoints` 置 0 但保留端点描述符，生成的就是 `firmware/experiments/ms2130s_alt3only.bin`，会把卡刷成 `USB\CONFIGURATION_DESCRIPTOR_VALIDATION_FAILURE` |

保留它是为了留证据：这次事故的直接原因就在这 10 个字节。

## 依赖

- PowerShell 5.1 或 7。脚本用 `Add-Type` 内联 C#，不需要额外模块。
- Python 3。`uac_desc_lint.py`、`mk_alt3_usb3only.py`、`ms213x_uac_tool.py` 只用标准库；`ms213x_restore.py` 也只用标准库（Linux 上跑）。
- `analysis/wav_scan.py` 等三个脚本需要 numpy，当前机器未安装。它们不在刷写链路里，不影响主流程。
