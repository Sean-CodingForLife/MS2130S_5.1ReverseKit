# registers

XDATA 寄存器 dump，每份 4096 字节，覆盖 `0xF000–0xFFFF`。读寄存器用 `tooling/reverse/ms213x_xdata.ps1`，HID 命令 `0xb5/0xb6`，读回值在响应缓冲区 `buf[4]`。

## batch-2026-11-13/

早期两态实验，对应原始简报第 9 节。

| 文件 | 大小 | 状态 | 用途 |
|---|---|---|---|
| `xd_f000.bin` | 256 B | 早期 | 只覆盖 `0xF000–0xF0FF` 的片段 |
| `xd_full.bin` | 4096 B | 实验 A 假 6ch，有音频 | 第 9 节的 6ch 侧 |
| `xd_stock.bin` | 4096 B | 原厂 2ch，无音频 | 第 9 节的 2ch 基准 |
| `xd_stock2.bin` | 4096 B | 原厂 2ch，无音频 | 第 9 节噪声底 |

## batch-2026-11-14/

三态对照，对应原始简报第 18 节。dump 都在音频流打开时取。

| 文件 | 大小 | 状态 | 用途 |
|---|---|---|---|
| `xdata_6ch_streaming.bin` | 4096 B | 解锁 6ch，流中 | A 状态 |
| `xdata_2ch_streaming.bin` | 4096 B | 原厂 2ch，流中 | B 状态 |
| `xdata_2ch_streaming_b.bin` | 4096 B | 原厂 2ch，流中 | B2，噪声底 |

## 不能跨批比较

```
xd_full  vs xdata_6ch_streaming   640 字节不同
xd_stock vs xdata_2ch_streaming   805 字节不同
```

即使标签都是“6ch”或“2ch”，早期批次和 11-14 流中批次也不是同一运行状态。第 9 节只和第 9 节比，第 18 节只和第 18 节比。

## 已复算的结论

第 18 节（三态对照）：

```
B vs B2     8 个差异（噪声底）
A vs B      273 个差异
排除动态后   266 个稳定差异，63 个连续区，0xF003–0xFE7F
```

第 9 节（早期两态）：

```
xd_full vs xd_stock       20 个差异
xd_stock vs xd_stock2      9 个动态位
排除后                    13 个稳定地址
```

两轮交集 9 个地址。其中 6 个值一致（`0xF0C3、0xF5B5、0xF5B6、0xF5BE、0xF706、0xF707`），更像固定配置位；3 个值不同（`0xF0B0、0xF77E、0xF7AC`），更像运行时状态。

`0xF00E` 在 7 份 dump 中始终 `0x3F`，是常量。`0xF00B` 不是：早期 dump 都是 `0x07`，流中 dump 在 6ch 下 `0xFF`、2ch 下 `0x43`。原始简报第 9 节把它当常量的结论只对早期 dump 成立。

## 复算方法

```python
from pathlib import Path

root = Path(__file__).resolve().parent
load = lambda p: (root / p).read_bytes()

A = load(r"batch-2026-11-14\xdata_6ch_streaming.bin")
B = load(r"batch-2026-11-14\xdata_2ch_streaming.bin")
B2 = load(r"batch-2026-11-14\xdata_2ch_streaming_b.bin")

dyn = {i for i in range(4096) if B[i] != B2[i]}
stable = [i for i in range(4096) if A[i] != B[i] and i not in dyn]
print(len(stable))   # 266
```

详细结果见 [核对记录](../docs/核对记录.md) 第三节。
