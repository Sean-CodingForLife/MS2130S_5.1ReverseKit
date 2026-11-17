# firmware

固件镜像目录。所有镜像 98356 字节：`header 0x30 + code 0x18000 + 校验 4 字节`。头部 magic `3C C3`，固件日期 2025-08-26。

`SHA256SUMS` 是全部镜像的 SHA-256 基线，`tooling/ops/regress.py` 按它比对；新增或改固件后运行 `python tooling/ops/regress.py --update-baseline` 重建。

## release/

当前使用与回退基准。

| 文件 | 角色 | SHA-256 |
|---|---|---|
| `ms2130s_51unlock_20210624.bin` | 当前使用；与 backup 差 37 B | `7B055136D233C09B9B5D88094AB172A523B75EFD3B14058A193FBAC184AF4B3E` |
| `ms2130s_backup.bin` | 原厂回退；序列号 20210629 | `69DD471F9D7E283E0220782A6692907DAE8F6871D6A5A3D6D170415ABEA140CC` |

解锁固件的改动：USB3 配置删掉 alt1、alt2 两个完整块（98 B），`wTotalLength` 1650 → 1552，序列号 20210629 → 20210624，代码校验 D9B8 → D9CA。效果是 Windows 在 USB 3 口上只能选 `alt=3`，端点变成 `6ch / 48000 Hz / 16 bit`（端点格式；WASAPI 采集落 float32）。

刷回原厂：

```powershell
tooling\flash\ms213x_flash.exe -w firmware\release\ms2130s_backup.bin
```

约 6 分钟，刷完拔卡身断电 10 秒。序列号也会还原成 20210629。

## experiments/

4 个实验镜像，保留作证据：

| 文件 | 差异 | 改动 | 用途 |
|---|---|---|---|
| `ms2130s_6ch_patch.bin` | 16 B | 两套配置 alt1 改 6ch/16/48；AC 掩码 0x3F | 实验 A 中间版本 |
| `ms2130s_all6ch.bin` | 24 B | 6ch_patch + alt2 改 6ch + 端点 576；序列号 20210620 | 实验 A 完整版，抓到的是字节错位 |
| `ms2130s_all6ch_v2.bin` | 24 B | 同上，序列号 20210621 | 实验 A 复测 |
| `ms2130s_marker_serial.bin` | 18 B | 6ch_patch + 序列号 20210620 | 序列号对照 |

## danger/

| 文件 | 说明 |
|---|---|
| `ms2130s_alt3only.bin` | 2026-11-13 变砖事故的补丁：alt1/alt2 的 `bNumEndpoints` 置 0 但保留端点。Windows 拒绝整个配置描述符，HID 刷写通道一起消失，只能用 Linux usbfs 救回。lint 报 4 处错误。**禁止刷。** |

## 刷前检查

```powershell
python tooling\reverse\uac_desc_lint.py firmware\<待刷镜像>.bin
```

0 错误才刷。只改格式字段（通道数、序列号、掩码）可以反复试；改 `bNumEndpoints` 或增删描述符是单向操作。

## 结构速查

```
0x0000-0x002F  header（magic 3C C3，日期 19 08 1A，bank 大小 80 00）
0x02F8         EDID（LPCM 8ch）
0x0640         USB2 配置描述符（1074 B）
0x0A94         USB3 配置描述符（1650 B / 解锁版 1552 B）
0x09E8         USB2 alt1 格式（2ch/24bit/96k）
0x0A13         USB2 alt2 格式（2ch/16bit/48k）
0x0A3E         USB2 alt3 格式（6ch/16bit/48k）
0x1064         USB3 alt1 格式
0x1095         USB3 alt2 格式
0x10C6         USB3 alt3 格式
0x1A6E / 0x1A83  序列号字符串（UTF-16LE，各 8 字符）
0x18030-0x18033  24 DC D9 B8（头部校验字段 24 DC + 代码校验 D9 B8）
```
