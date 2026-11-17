# firmware

固件镜像目录。所有镜像 98356 字节，格式为 `header 0x30 + code 0x18000 + 校验 4 字节`，头部 magic `3C C3`，固件日期 2025-08-26。

## 当前使用

```
ms2130s_51unlock_20210624.bin
  与 backup 差 37 字节
  USB3 配置删掉 alt1、alt2 两个完整块（98 B），wTotalLength 1650 -> 1552
  序列号 20210629 -> 20210624
  代码校验 D9B8 -> D9CA
```

效果：Windows 在 USB 3 口上只能选 `alt=3`，端点变成 `6ch / 48000 Hz / 16 bit`。

## 回退基准

```
ms2130s_backup.bin
  原厂镜像。序列号 20210629，USB2 配置 1074 B，USB3 配置 1650 B，alt1/2/3 齐全
  SHA-256 69DD471F9D7E283E0220782A6692907DAE8F6871D6A5A3D6D170415ABEA140CC
```

刷回原厂：

```powershell
tools\ms213x_flash.exe -w firmware\ms2130s_backup.bin
```

约 6 分钟，刷完拔卡身断电 10 秒。序列号也会还原成 20210629。

## experiments/

5 个实验镜像，保留作证据与反面教材：

| 文件 | 差异 | 改动 | 用途 |
|---|---|---|---|
| `ms2130s_6ch_patch.bin` | 16 B | 两套配置 alt1 改 6ch/16/48；AC 掩码 0x3F | 实验 A 中间版本 |
| `ms2130s_all6ch.bin` | 24 B | 6ch_patch + alt2 改 6ch + 端点 576；序列号 20210620 | 实验 A 完整版，抓到的是字节错位 |
| `ms2130s_all6ch_v2.bin` | 24 B | 同上，序列号 20210621 | 实验 A 复测 |
| `ms2130s_marker_serial.bin` | 18 B | 6ch_patch + 序列号 20210620 | 序列号对照 |
| `ms2130s_alt3only.bin` | 10 B | alt1/alt2 的 `bNumEndpoints` 置 0，保留端点 | **变砖固件，禁止刷** |

`ms2130s_alt3only.bin` 是 2026-11-13 变砖事故的补丁：Windows 拒绝整个配置描述符，HID 刷写通道一起消失，只能用 Linux usbfs 救回。lint 对它报 4 处错误。

## 刷前检查

```powershell
python scripts\uac_desc_lint.py firmware\<待刷镜像>.bin
```

0 错误才刷。只改格式字段（通道数、序列号、掩码）可以反复试；改 `bNumEndpoints` 或增删描述符是单向操作。

## 固件结构速查

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
0x18030-0x18033  头部校验 0x24DC + 代码校验 2 字节
```
