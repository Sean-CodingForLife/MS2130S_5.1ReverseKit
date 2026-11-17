# tools51

6 声道录制、通道重排与标定文件。全部围绕“卡已经解锁到 alt3”之后的使用。

## 录制

最简单：双击 `录制5.1.cmd`，回车用默认 60 秒，或输入秒数。录完文件在 Windows 的「视频」文件夹：

```
ns2_51_yyyyMMdd_HHmmss.wav
```

命令行等价写法：

```powershell
powershell -File tools51\rec51.ps1 -Seconds 60
powershell -File tools51\rec51.ps1 -Seconds 60 -Out D:\cap\test.wav
```

`rec51.ps1` 自动枚举采集端点，只挑 `GetMixFormat` 为 6 声道的那个，用 WASAPI 采集并写 float32 WAV。不用手动填端点 GUID。

前提：卡插在 **USB 3 口**。插 USB 2.0 口会走未改动的原厂配置，端点退回 2ch。

## 通道重排

卡的通道顺序是 `FL, FR, LFE, FC, BL, BR`，标准 5.1 是 `FL, FR, FC, LFE, BL, BR`，第 3、4 位相反。

### WAV

把文件拖到 `修正通道顺序.cmd`，输出同目录的 `_fixed.wav`：

```bash
ffmpeg -i in.wav -af "pan=5.1|c0=c0|c1=c1|c2=c3|c3=c2|c4=c4|c5=c5" -c:a pcm_s24le out.wav
```

### 视频

把 `.mkv` / `.mp4` 拖到 `修正通道顺序_视频.cmd`，输出 `_fixed.mkv`，**视频流直接复制，不重编码**：

```bash
ffmpeg -i in.mkv -af "pan=5.1|c0=c0|c1=c1|c2=c3|c3=c2|c4=c4|c5=c5" -c:v copy -c:a pcm_s24le out.mkv
```

两个 `.cmd` 都优先用 `D:\Programs\FFmpeg Upmix\ffmpeg\bin\ffmpeg.exe`，找不到就退回 PATH 里的 `ffmpeg`。如果两处都没有，会打印 `FAILED`。

`pan=5.1` 用的是位置名 `c0..c5`，不依赖输入文件的 channel layout 解析。OBS 录出来的 `channel_layout=unknown` 也能正常重排。

## 标定文件

`chmap_51_100Hz.wav`：6ch / 48kHz / 16bit / 13.50 s。ch0 到 ch5 依次各播 1.50 s 的 100 Hz 正弦，间隔 0.50 s，顺序是 Windows 标准 5.1 `FL, FR, FC, LFE, BL, BR`。

用法：笔记本 HDMI 接采集卡，输出设备设成 5.1，用 mpv 循环播放这个文件，台式机用 `rec51.ps1` 录 130 秒，按 0.25 秒分块找每段落在哪个通道。实测落点：

```
FL  -> ch0      FR  -> ch1      FC  -> ch3
LFE -> ch2      BL  -> ch4      BR  -> ch5
```

这就是“卡把 FC 和 LFE 对调”的直接证据。

## 已知限制

- 录到的 WAV 是 float32（WASAPI 的 mix format），体积约 1.15 MB/s。60 秒约 69 MB。
- OBS 用 `pcm_s24le` 录 6ch/48k 约 864 KB/s（3.1 GB/小时）。长录像可以在 OBS 里把音频编码改成 AAC；重排时视频仍复制，音频会重编码。
- 没有做数小时连续录制压测。目前最长实测 130 秒。
- `录制5.1.cmd` 是 GBK 编码，用 UTF-8 打开会乱码。这是为了在 cmd.exe 里正常显示中文，不要转成 UTF-8。
