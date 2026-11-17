# tooling/analysis

2026-11-13 晚写的三个取证脚本，用来判断“6 声道数据到底是真音频还是字节错位”。结论已经写进原始简报第 11 节，脚本保留作方法记录。

## 三个脚本

| 脚本 | 作用 |
|---|---|
| `wav_scan.py` | 读 WAV，打印每通道 RMS / std、通道间平均差矩阵、偏移 1–5 的重复检测、0.5 秒分块 RMS 表 |
| `wav_deep.py` | 对指定文件、指定时间点取 8 帧原始 int16，打印逐位相等的通道对与相关系数 |
| `wav_bytes.py` | 把指定时间点的样本还原成字节，按 4 字节分组解释成 float32，看原始布局 |

这三个脚本支撑了那次关键修正：`std = 0.5772` 不是 SRAM 噪声，而是 24bit 样本的低 16 位被当成独立声道。`wav_scan.py` 的通道 std 与 `wav_deep.py` 的逐位相等比例是主要判据。

## 已修复

2026-11-16 重构时改了三处：

1. 根目录不再硬编码 `D:\Backups\workspace\_resume`，改为按脚本位置推导：

```python
D = Path(__file__).resolve().parents[2] / "captures"
```

`parents[0]` = `tooling/analysis`，`parents[1]` = `tooling`，`parents[2]` = 项目根。

2. `wav_scan.py` 的 `main()` 加了 `if __name__ == '__main__'` 保护，`wav_deep.py` / `wav_bytes.py` 的顶层执行也收进 `main()`，import 不会再触发扫描。
3. 项目 venv 内由 `start_service.ps1` 安装 numpy 2.5.4；直接用系统 Python 时需自行 `pip install numpy==2.5.4`。

传文件名时先查 `captures/` 根，找不到再在 `evidence/`、`archive/` 里递归查找；不传参数时递归扫描 `captures/` 下所有 `.wav`。

## 用法

```powershell
python tooling\analysis\wav_scan.py captures\evidence\ns2_51_unlocked_test.wav
python tooling\analysis\wav_scan.py ns2_selftest.wav
python tooling\analysis\wav_deep.py
python tooling\analysis\wav_bytes.py
```

`wav_scan.py` 对 119.96 秒的六通道文件会输出完整的配对矩阵与 0.5 秒分块表，行数较多，可以重定向到文件再看。

`wav_deep.py` 和 `wav_bytes.py` 里的文件名与时间点是写死的（`ns2_selftest.wav`、`game_51.wav`、`ns2_51_test.wav` 等早期文件），按需改。

## 替代方案

不装 numpy 也能核实结论：`docs/核对记录.md` 第四节的复算全部用标准库完成，能直接验证通道落点、RMS 和标定映射。取证脚本的价值在“原始字节布局”这一层。
