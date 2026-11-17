# tooling

`MS2130S_5.1ReverseKit` 的全部可执行工具，按用途分组。

| 目录 | 用途 | 入口 |
|---|---|---|
| `ops/` | 操作台本地服务、Run 记录、快照/验收/diff/回归、通道实时电平；配置在 `ops_config.json`，样式令牌在根 `design-tokens.css`，共享组件在根 `components.css`，两者各有只读路由 | 根 `启动操作台.vbs` |
| `flash/` | 厂商 HID 刷写工具与第三方许可证 | `ms213x_flash.exe` |
| `capture/` | 解锁后的 6 声道录制、标定源 | `rec51.ps1`、`chmap_51_100Hz.wav` |
| `reverse/` | 描述符 lint、生成解锁固件、寄存器读写、WASAPI、Linux 救砖 | `uac_desc_lint.py`、`ms213x_restore.py` |
| `analysis/` | WAV 取证：通道统计、位宽假设、字节布局 | `wav_scan.py` |

## 常用命令

```powershell
# 操作台（浏览器操作，无控制台窗口）
.\启动操作台.vbs

# 刷前 lint
python tooling\reverse\uac_desc_lint.py firmware\release\ms2130s_51unlock_20210624.bin

# 刷写解锁固件（约 6 分钟）
tooling\flash\ms213x_flash.exe -w firmware\release\ms2130s_51unlock_20210624.bin

# 回退原厂（同样约 6 分钟）
tooling\flash\ms213x_flash.exe -w firmware\release\ms2130s_backup.bin

# 录制 5.1
powershell -File tooling\capture\rec51.ps1 -Seconds 60

# 修通道（页面“一键修通道”，或手动 ffmpeg）
ffmpeg -i in.wav -af "pan=5.1|c0=c0|c1=c1|c2=c3|c3=c2|c4=c4|c5=c5" -c:a pcm_s24le out.wav

# 读 XDATA
powershell -File tooling\reverse\ms213x_xdata.ps1 -Start 0xF000 -End 0xFFFF -Out registers\batch-2026-11-14\new.bin

# 复算通道落点
python tooling\analysis\wav_scan.py captures\evidence\ns2_51_unlocked_test.wav

# 无硬件回归（7 SHA / 7 lint / 链接 / 路径 / HTML / 18 脚本编码）
python tooling\ops\regress.py

# 只分析一段 WAV 的六通道独立性（当前采集格式 float32）
python tooling\ops\verify_wav.py captures\evidence\game_51_unlocked_5s.wav
```

## 约定

- `flash/` 里的 `.exe` 依赖同目录文件，移动整个目录不会破坏相对路径。
- `reverse/` 里的 ps1 用 `Add-Type` 内联 C#，不需要安装模块；Python 脚本只用标准库。
- `analysis/` 需要 numpy（项目 venv 内由启动脚本安装 2.5.4；系统 Python 需自行安装）。
- `reverse/patch_alt3.py` 是变砖补丁的反面教材，不要运行。
