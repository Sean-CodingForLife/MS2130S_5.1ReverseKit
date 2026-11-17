# captures

录音与视频帧。录音以 6ch / 48000 Hz / float32 为主（WASAPI 采集的原始格式）；格式例外在表内标注。完整格式链见根 `README.md` 的「关键口径」表。

## 证据等级

| 等级 | 含义 | 目录 |
|---|---|---|
| A | 解锁固件下采集，能证明“6 个独立通道” | `evidence/` |
| B | 早期实验，结果已被后续结论修正 | `archive/` |
| C | 对照 / 原厂状态，不作为 6ch 证据 | `archive/` |

## A 级：解锁后的关键证据

`evidence/` 保存 A 级证据；`recordings/` 是操作台新录制的默认输出目录，`fixed/` 是修通道输出目录，三者都在项目工作区内。

| 文件 | 时长 | 内容 | 复算结果 |
|---|---|---|---|
| `evidence/ns2_51_unlocked_test.wav` | 119.96 s | NS2「输出测试」六喇叭逐段播放 | 六段落在 ch0、ch3、ch1、ch5、ch4、ch2，其余通道 RMS `0.0000` |
| `evidence/game_51_unlocked_5s.wav` | 4.97 s | 游戏 5.1 片段 | RMS `0.0173 / 0.0116 / 0.0023 / 0.0093 / 0.0104 / 0.0037` |
| `evidence/chmap_stereo_probe_sample.wav` | 13.00 s | 100 Hz 正弦逐通道标定；16 bit / 6ch / 48 kHz | 源 `FL,FR,FC,LFE,BL,BR` → `ch0,ch1,ch3,ch2,ch4,ch5` |

三条证据的用法：

1. **NS2 测试**证明六个通道互相独立：每段只有一个通道有能量，其余五通道在 float32 精度下为零。
2. **游戏片段**证明真实内容下六通道都有信号，不是只测试音有效。
3. **标定录音**证明通道语义正确、排列次序是 `FL, FR, LFE, FC, BL, BR`，需要交换 c2/c3。

`chmap_stereo_probe_sample.wav` 的名字有误导：它实际是 6 声道标定录音，不是 stereo probe。改名会破坏文档引用，保留原名，在此说明。

## B 级：早期实验

| 文件 | 时长 | 说明 |
|---|---|---|
| `archive/capture6ch.wav` | 4.96 s | 实验 A 早期 6ch 抓取，曾被误判为 SRAM 噪声 |
| `archive/game_51.wav` | 11.95 s | 实验 A 游戏片段 |
| `archive/game_long.wav` | 59.97 s | 实验 A 60 秒长抓，用于看 RMS 是否恒定 |
| `archive/ns2_51_test.wav` | 7.95 s | 实验 A NS2 测试 |
| `archive/ns2_now.wav` | 5.98 s | 实验 A 即时抓取 |
| `archive/ns2_selftest.wav` | 44.99 s | NS2 自测 |
| `archive/phone_71_test.wav` | 14.96 s | 手机 HDMI 源测试 |
| `archive/phone_test2.wav` | 9.98 s | 手机源复测 |
| `archive/tone_test.wav` | 19.97 s | 测试音 |
| `archive/tone_test2.wav` | 9.95 s | 测试音复测 |

这一批的共同点：固件是实验 A（把 alt1/alt2 声明成 6ch），卡实际按 alt1 出 2ch/24bit/96k，主机按 16bit 读，于是每个 24bit 样本的低 16 位被当成一个“声道”。`std = 1/√3 = 0.5774` 是数学必然，不是随机垃圾。详细推导见原始简报第 11 节。

## C 级：对照与原厂状态

| 文件 | 格式 | 说明 |
|---|---|---|
| `archive/stock_check.wav` | 2ch / 48k / float32 / 3.97 s | 原厂固件、无音源，双通道 RMS 0.000，确认纯静音 |
| `archive/test6ch.wav` | 6ch / **44.1k** / 16bit / 2.97 s | 虚拟声卡回环。采样率不是采集卡的 48k，不能当卡证据 |
| `archive/vac_control.wav` | 8ch / 48k / float32 / 7.97 s | Virtual Audio Cable 8 声道回环，用于验证采集代码本身没问题 |

## 视频

| 文件 | 说明 |
|---|---|
| `video/unlocked_video_frame.png` | 解锁固件下的 1080p 抓帧，画面为 NS2 游戏。用来证明 UVC 通路未受固件改动影响 |

## 录制与复算

录制（脚本只接受项目工作区内的输出路径；默认写入 `captures/recordings/`）：

```powershell
powershell -File tooling\capture\rec51.ps1 -Seconds 60
```

复算通道落点：按 0.25 秒分块算每通道 RMS，取最大值通道。标准库写法见 [核对记录](../docs/核对记录.md) 第四节；也可以直接跑已修好路径的 `tooling/analysis/wav_scan.py`：

```powershell
python tooling\analysis\wav_scan.py captures\evidence\ns2_51_unlocked_test.wav
```

## 文件大小

长录音单个在几十到一百多 MB；录音与视频合计是项目体积的主体。具体体积以目录为准，传输或备份前先看实际大小。
