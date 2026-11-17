# MS2130S 5.1 声道逆向

一块 56 元的公版 MS2130S USB 采集棒（`VID_345F / PID_2132`，产品名 `USB3 PLUS`）的 6 声道解锁记录。

**结论**：芯片硬件支持 6 声道。厂商把 `6ch / 48kHz / 16bit` 挂在 USB 音频流接口的 `alt=3` 上，而 Windows 的 USB Audio 驱动只取一个 alternate setting，永远选不到它。把 USB 3.x 配置里的 alt1、alt2 整块删掉（USB 2.0 配置留作退路），再改序列号强制 Windows 重建音频端点，Windows 就只能选 alt3，录到的是六个真正独立的通道。

## 当前状态

| 项 | 值 |
|---|---|
| 固件 | `firmware/ms2130s_51unlock_20210624.bin`（USB3 只留 alt0 + alt3，序列号 20210624） |
| 端点 | 6ch / 48000 Hz / 16 bit |
| 通道顺序 | `FL, FR, LFE, FC, BL, BR`（第 3、4 位与标准相反） |
| 视频 | UVC 通路未受影响，4K120 可采 |
| 回退 | 刷 `firmware/ms2130s_backup.bin`，序列号还原 20210629 |
| 现场复查 | 2026-11-14 整理时卡未连接，未能现场读端点；最后一次验证记录见简报第 16 节 |

## 目录

| 目录 | 内容 | 入口 |
|---|---|---|
| `docs/` | 逆向简报、对外解锁指南、本次整理新增的清单与核对记录 | `docs/项目全景.html` |
| `firmware/` | 原厂固件、解锁固件、5 个实验镜像 | `firmware/README.md` |
| `registers/` | 7 份 XDATA dump（两批，不可跨批比较） | `registers/README.md` |
| `captures/` | 17 段录音、1 张视频帧 | `captures/README.md` |
| `scripts/` | 刷写、描述符、寄存器、WASAPI 脚本 | `scripts/README.md` |
| `tools/` | 厂商刷写工具 `ms213x_flash.exe` 及第三方许可证 | — |
| `tools51/` | 6 声道录制、通道重排、标定文件 | `tools51/README.md` |
| `analysis/` | 声道取证脚本（硬编码路径已失效） | `analysis/README.md` |
| `stick/` | 早期 WinPE 恢复方案（历史遗留） | `stick/1-操作步骤.txt` |

## 五分钟上手

```powershell
# 录制 5.1：双击 tools51\录制5.1.cmd，或
powershell -File tools51\rec51.ps1 -Seconds 60

# 录完修通道：把 WAV 拖到 tools51\修正通道顺序.cmd
# 视频同理，拖到 tools51\修正通道顺序_视频.cmd（视频流不重编码）

# 刷任何固件前，先过描述符 lint（0 错误才刷）
python scripts\uac_desc_lint.py firmware\ms2130s_51unlock_20210624.bin

# 回退原厂（约 6 分钟，过程中不能拔 USB）
tools\ms213x_flash.exe -w firmware\ms2130s_backup.bin
```

刷完必须**真正断电**：拔卡身上的 USB 头，等 10 秒再插。拔 HUB 到电脑那根线不算断电。

## 三条关键机制

1. **描述符不由固件搬运。** USB 描述符由 SIE 硬件直接从 flash 固定区读取，固件只负责初始化与控制。所以改描述符后 Windows 立刻能识别，也解释了为什么改描述符不改变实际音频格式。
2. **固件按 `SET_INTERFACE` 的 alt 序号查死表。** alt1 → 2ch/24bit/96k，alt2 → 2ch/16bit/48k，alt3 → 6ch/16bit/48k。改描述符文本只骗 Windows，卡本身仍按 alt 序号出数据。
3. **Windows 只暴露一个 alt 的格式。** 独占模式请求 6ch/8ch/96k 全部返回 `0x88890048`，只有被选中的那个 alt 可用。所以要拿 6 声道，必须让 alt3 成为唯一可选的 streaming 设置。

## 红线

- **只改格式字段可以反复试；改 `bNumEndpoints`、增删描述符是单向操作。** 结构不合法会让 Windows 拒绝整个配置描述符，连 HID 刷写通道一起消失。
- **刷写过程中不能拔 USB。** 刷完必须真断电，芯片只在启动时从 flash 加载描述符。
- **每次改描述符必须同时改序列号。** Windows 按设备实例缓存音频端点格式，不改序列号会一直沿用旧端点。
- **插 USB 2.0 口会走未改动的原厂配置，退回 2ch，不会损坏。** 这也是 USB3 配置改坏后的退路。
- **`firmware/experiments/ms2130s_alt3only.bin` 是变砖固件，不要刷。** 它把 alt1/alt2 的 `bNumEndpoints` 置 0 却保留端点描述符，lint 报 4 处错误。

## 文档

| 文档 | 定位 |
|---|---|
| `docs/MS2130S_5.1_解锁指南.md` | 对外分享版，自包含，只讲结论与操作 |
| `docs/MS2130S_5.1_逆向简报.md` | 完整实验记录，1–20 节，按时间顺序，含自我更正 |
| `docs/资产清单.md` | 本次整理新增：逐文件角色、状态、证据等级 |
| `docs/核对记录.md` | 本次整理新增：可复现验证与文档勘误 |
| `docs/项目全景.html` | 本次整理新增：交互式全景（机制、证据、资产、时间线） |

简报第 4 节和第 10.5 节把 6 声道数据判为“SRAM 噪声”，这个结论已被第 11 节推翻（实际是 24bit/16bit 字节错位）。读简报时从第 11 节切入，再回看前面的实验记录。
