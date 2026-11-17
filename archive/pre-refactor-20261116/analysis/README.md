# analysis

2026-11-13 晚写的三个取证脚本，用来判断“6 声道数据到底是真音频还是字节错位”。结论已经写进简报第 11 节，脚本保留作方法记录。

## 三个脚本

| 脚本 | 作用 |
|---|---|
| `wav_scan.py` | 读 WAV，打印每通道 RMS / std、通道间平均差矩阵、偏移 1–5 的重复检测、0.5 秒分块 RMS 表 |
| `wav_deep.py` | 对指定文件、指定时间点取 8 帧原始 int16，打印逐位相等的通道对与相关系数 |
| `wav_bytes.py` | 把指定时间点的样本还原成字节，按 4 字节分组解释成 float32，看原始布局 |

这三个脚本支撑了那次关键修正：`std = 0.5772` 不是 SRAM 噪声，而是 24bit 样本的低 16 位被当成独立声道。`wav_scan.py` 的通道 std 与 `wav_deep.py` 的逐位相等比例是主要判据。

## 现在跑不起来

三个脚本都硬编码：

```python
D = r'D:\Backups\workspace\_resume'
```

这个目录已经不存在。`wav_scan.py` 在模块加载时就调用 `main()`（没有 `if __name__ == '__main__'` 保护），所以 `wav_deep.py` / `wav_bytes.py` 里的 `import wav_scan as W` 会立刻触发一次目录扫描，直接报 `FileNotFoundError`。

另外需要 numpy，当前机器的 Python 3.13 没有安装。

## 修复方法

如果只是想复跑分析，改三处：

1. 把三个脚本里的 `D` 改成 `C:\Users\Administrator\Desktop\MS2130S_5.1逆向\captures\audio`。
2. 把 `wav_scan.py` 末尾的 `main()` 改成：

```python
if __name__ == '__main__':
    main()
```

3. 安装 numpy：

```powershell
python -m pip install numpy
```

然后：

```powershell
python analysis\wav_scan.py ns2_51_unlocked_test.wav
python analysis\wav_deep.py
python analysis\wav_bytes.py
```

`wav_deep.py` 和 `wav_bytes.py` 里的文件名与时间点是写死的（`ns2_selftest.wav`、`game_51.wav`、`ns2_51_test.wav` 等早期文件），按需改。

## 替代方案

不想装 numpy 也可以。`docs/核对记录.md` 第四节的复算全部用标准库完成，能直接验证通道落点、RMS 和标定映射。取证脚本的价值在于“原始字节布局”这一层，如果只是核实结论，标准库足够。
