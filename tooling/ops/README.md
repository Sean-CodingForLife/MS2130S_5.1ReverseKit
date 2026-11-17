# tooling/ops

操作台（`MS2130S_5.1ReverseKit`）的本地服务与启动脚本。页面在项目根 `操作台.html`，样式令牌在根 `design-tokens.css`，共享组件在根 `components.css`；`server.py` 通过 `/design-tokens.css` 与 `/components.css` 两个精确路由只读返回。

## 启动

双击根目录的 `启动操作台.vbs`。它用 `pythonw.exe` 在后台启动 `server.py`，不显示控制台窗口，然后打开浏览器：

```
http://127.0.0.1:8765/
```

首次双击根目录的 `启动操作台.vbs` 会自动在 `runtime/` 下创建 venv，并用基础 Python 把 `numpy` 与 `imageio-ffmpeg` 装进 venv 的 site-packages；不修改系统 Python、不写用户目录。依赖只装一次，之后直接复用。服务只绑 `127.0.0.1`；关掉浏览器或连续无操作后服务会自动退出，下次双击 `启动操作台.vbs` 会重新启动或复用已在跑的服务。已运行的服务不会热加载 `server.py`；改完代码要结束对应 `pythonw.exe` 后重新双击 `启动操作台.vbs`。改 `.ps1` 时保持 UTF-8 BOM：Windows PowerShell 5.1 会把无 BOM 的 UTF-8 当 ANSI，中文会乱码；`regress.py` 会拦住无 BOM 且含非 ASCII 的脚本。

## 关闭

双击根目录 `停止操作台.vbs`。它调用 `tooling/ops/stop_service.ps1`：优先读 `runtime/tmp/server.json` 记录的 PID 与真实 `server.py` 路径，只有进程命令行与记录一致时才结束进程树；PID 被其他进程复用会拒绝结束，不按项目名模糊匹配，也不动其他 Python。没有状态文件时，只按当前项目 `server.py` 的绝对路径精确匹配。

也可以直接关掉浏览器：页面有操作时每 60 秒请求一次 `/api/heartbeat` 保活；关掉浏览器或连续 `server.idle_timeout_minutes`（默认 30 分钟）无操作后，服务自动退出。页面里的“停止”只停当前任务，不是关服务。把阈值设为 `0` 可禁用自动退出。

## 工作区边界

- 部署与运行时只写项目根 `runtime/`（venv、日志、临时文件、pip 缓存）和项目内业务目录。
- 录制默认输出 `captures/recordings/`，修通道输出 `captures/fixed/`；用户手填路径必须是项目工作区内的绝对路径。
- `/api/lint` 只接受 `firmware/` 下的 `.bin`；`/api/flash` 进一步只允许 `release/`、`experiments/`，并在 lint 与快照门控后执行。
- 一键部署路径不写 Windows 启动项；启动入口只有根目录 `启动操作台.vbs`，关闭入口是 `停止操作台.vbs`。

## 页面能做什么

页面主流程按第一步接卡、第二步录制、第三步修通道、第四步刷前检查、第五步读回快照、第六步安全刷写、第七步刷后验收编号；固件对比标辅助，不影响主流程。

| 区域 | 动作 | 背后调用 |
|---|---|---|
| 设备 | 显示在线状态、VID/PID、友好名 | `Get-PnpDevice` |
| 录制 5.1 | 选时长、可选输出路径，进度条按秒推进；右侧通道电平实时刷新 | `tooling/capture/rec51.ps1` + WAV 尾部 RMS |
| 修通道 | WAV / 视频，交换 c2/c3，页面画通道映射与处理进度 | `ffmpeg` + `-progress` |
| 固件 | 刷前检查、安全刷写，选中项显示风险标签与 SHA | `uac_desc_lint.py` → `ms213x_flash.exe` |
| 刷前快照 | 读回当前固件，magic 与长度是否与 backup 基准一致 | `tooling/flash/ms213x_flash.exe -r` |
| 刷后验收 | 枚举 / 按配置录制 / 格式 / 通道独立性；视频人工复核 | `/api/verify`、`verify_wav.py` |
| 固件对比 | 1 KB 块热图、差异字节、两边 SHA | `/api/diff` |
| 回归自检 | SHA 基线、lint、文档链接、关键路径、HTML、PowerShell 编码 | `regress.py` |
| 实验记录 | 每次录制、修通道、lint、刷写、快照、验收、回归生成 Run，可看详情、导出 zip | `/api/runs`、`/api/run`、`/api/export` |
| 运行看板 | 阶段、进度条、计时、日志、停止；刷写块矩阵 | `/api/job` 轮询 |
| 操作指南 | 右上角按钮，首次自动弹出（页面 7 步、指南 8 节），关闭后收纳 | 页面内 `dialog` |
| 救砖流程 | 五步弹窗，指向 `docs/05-变砖与救砖.md` | 页面内 `dialog` |
| 文档 | 在默认应用里打开 | `os.startfile`，白名单 |

## 实验记录

每次录制、修通道、lint、刷写、快照、验收、回归都会在 `tooling/ops/runs/<run_id>/` 生成 `manifest.json`，Run 列表只扫描这些目录，不再维护 `runs.jsonl` 第二索引。完整日志写入 `record.log` / `fix.log` / `lint.log` / `flash.log` / `snapshot.log` / `verify.log` / `regress.log`。

| 接口 | 方法 | 作用 |
|---|---|---|
| `/api/runs?limit=` | GET | 最近 Run 列表 |
| `/api/run?id=` | GET | 单个 manifest |
| `/api/export?id=` | GET | zip 证据包，含自动生成的 `README.txt` |
| `/api/snapshot` | POST | 读回当前固件；设备离线返回 400 |
| `/api/verify` | POST | 枚举 + 按配置录制 + 分析；设备离线或多台同型号返回 400 |
| `/api/diff` | POST `{a,b}` | 1 KB 块差异，返回块数组、差异字节、两边 SHA |
| `/api/regress` | POST | 回归自检，结果写 `regress.json` |
| `/api/job?id=` | GET | 任务状态，含 `levels` / `progress` / `out` |

`runs/` 是运行时目录，不纳入项目文件数。测试生成的记录可以直接删目录；页面按 `manifest.json` 扫描，不依赖索引文件。

## 安全边界

- 服务只监听本机回环地址，不接受外部连接。
- 刷写必须输入确认码 `FLASH`；`firmware/danger/` 与快照目录不能进入刷写，只允许 `release/`、`experiments/`。
- 刷写前强制跑 lint，未通过直接阻止。
- 刷写前强制要求当前设备在线，且快照在当前服务启动后完成、通过基线校验、晚于最近一次刷写尝试，并与当前设备实例匹配；没有快照、快照失效或设备不在线时 `/api/flash` 直接返回 400。
- 录制、读回、刷写、验收都要求只有一台同型号设备；检测到多台时接口返回 400，页面锁住设备动作，避免端点匹配选错卡。
- `/api/verify` 在设备离线时直接返回 400，不再生成失败记录；页面按钮同步禁用。
- 刷写/读回期间页面“停止”按钮锁住，`/api/stop` 也拒绝停止；强行中断可能损坏设备。
- 打开文档只允许 `ops_config.json` 的 `docs` 清单里的路径（当前 13 个）；页面只渲染一个“文档索引”，其余路径作为索引内页保留。

## 服务脚本

| 文件 | 作用 |
|---|---|
| `server.py` | HTTP 服务与任务调度；用户提供的路径都经工作区校验，运行时写入固定在 `runtime/` 与 `runs/` |
| `ops_config.json` | 单一配置源：工作区、设备期望、电平窗口、刷新、刷写估算、文档清单、回归路径 |
| `requirements.txt` | 首次部署安装到 `runtime/venv` 的依赖版本 |
| `verify_wav.py` | 标准库 WAV 分析：通道 RMS、相关、重复、verdict；同时校验通道数、采样率、WAV format tag 与 bits |
| `regress.py` | 无硬件回归：SHA 基线 / lint / 链接 / 路径 / HTML / 脚本编码 |
| `runs/` | 运行时实验记录，页面实验记录卡读取 |
| `start_service.ps1` | 首次建 venv/装依赖，然后隐藏启动服务，输出实际端口 |
| `open.ps1` | 调 `start_service.ps1`，拿到端口后打开浏览器；失败时打开部署日志 |
| `stop_service.ps1` | 停止本项目服务；按命令行匹配 `server.py`，结束进程树并校验 8765–8769 无监听 |

## 配置

`ops_config.json` 是单一可变配置：通道数、采样率、电平窗口、刷新间隔、刷写估算、文档清单、回归关键路径、服务空闲超时。改这些值不需要改 Python 或 HTML；页面通过 `/api/config` 读取，`verify_wav.py` 与 `regress.py` 直接读同一个文件。`device.channel_labels` 是卡实际输出顺序 `FL,FR,LFE,FC,BL,BR`，`device.channel_labels_fixed` 是修通道后的标准顺序 `FL,FR,FC,LFE,BL,BR`。

## 依赖

- Python 3.10+；首次部署会在 `runtime/venv` 内使用同一版本 Python，不改系统环境。基础 Python 必须带 pip（venv 本身不装 pip），依赖由基础 pip 直接装进 venv 的 site-packages。
- `numpy` 与 `imageio-ffmpeg` 由 `requirements.txt` 安装到 `runtime/venv`；`imageio-ffmpeg` 自带 ffmpeg，作为 PATH 中找不到 ffmpeg 时的回退。
- PowerShell（录制脚本与设备查询）。
- 修通道优先用 `FFMPEG_PATH` 或 `runtime/bin`，其次使用 `runtime/venv` 内置 ffmpeg；只有都没有时才回退 PATH。

## 故障

| 现象 | 处理 |
|---|---|
| 双击 `启动操作台.vbs` 没反应 | 看 `runtime\logs\bootstrap.log`；再手动跑 `start_service.ps1` 看输出 |
| 页面打开但状态全灰 | 访问 `http://127.0.0.1:8765/api/ping`；不通就重新双击 `启动操作台.vbs` |
| 修通道提示找不到 ffmpeg | 确认 `runtime\venv` 已装 `imageio-ffmpeg`，或设 `FFMPEG_PATH` |
| 录制提示没有 6 声道端点 | 卡不在线，或插在 USB 2.0 口；先看页面顶部设备卡 |
| 端口被占用 | 服务会自动试 8766–8769；也可先结束已在运行的 `pythonw.exe` |
| 服务自己退出、页面显示离线 | 可能已触发空闲自动退出；重新双击 `启动操作台.vbs`。要常驻就把 `server.idle_timeout_minutes` 调大或设为 `0` |
