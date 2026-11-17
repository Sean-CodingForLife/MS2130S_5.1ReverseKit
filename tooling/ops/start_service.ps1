$ErrorActionPreference = 'Stop'

# 单一启动入口的后端：首次运行在工作区内建 venv、装依赖，然后启动服务。
# 所有运行时文件、venv、日志、临时文件都在项目根目录下，不写 %TEMP% 或用户目录。
$opsDir = $PSScriptRoot
$workspace = Split-Path -Parent (Split-Path -Parent $opsDir)
$server = Join-Path $opsDir 'server.py'
$requirements = Join-Path $opsDir 'requirements.txt'
$runtime = Join-Path $workspace 'runtime'
$logs = Join-Path $runtime 'logs'
$tmp = Join-Path $runtime 'tmp'
$pipCache = Join-Path $runtime 'pip-cache'
$pycache = Join-Path $runtime 'pycache'
$venv = Join-Path $runtime 'venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
$venvPyw = Join-Path $venv 'Scripts\pythonw.exe'
$venvSite = Join-Path $venv 'Lib\site-packages'
$bootstrapLog = Join-Path $logs 'bootstrap.log'

foreach ($dir in @($runtime, $logs, $tmp, $pipCache, $pycache)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$env:TMP = $tmp
$env:TEMP = $tmp
$env:PIP_CACHE_DIR = $pipCache
$env:PYTHONPYCACHEPREFIX = $pycache

function Write-DeployLog([string]$message) {
    try {
        Add-Content -LiteralPath $bootstrapLog -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message) -Encoding UTF8
    } catch {
    }
}

function Test-Ops([int]$p) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$p/api/ping" -UseBasicParsing -TimeoutSec 1
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-PythonModule([string]$python, [string]$module) {
    & $python -c "import $module" 2>$null
    return $LASTEXITCODE -eq 0
}

function Find-BasePython {
    # 优先 py 启动器；没有就退回 PATH 里的 python.exe / python3.exe。
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $out = & $py.Source -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $exe = ([string]($out | Select-Object -Last 1)).Trim()
                if ($exe -and (Test-Path -LiteralPath $exe)) { return $exe }
            }
        } catch {
        }
    }
    foreach ($name in @('python.exe', 'python3.exe')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
            return $cmd.Source
        }
    }
    throw '未找到 Python 3；请先安装 Python 3.10+'
}

# venv 用 --without-pip：Python 3.14 的 ensurepip 在清理临时目录时会报 WinError 145；
# 依赖改由基础 Python 的 pip --target 装进 venv 的 site-packages。
function Ensure-Venv {
    if (Test-Path -LiteralPath $venvPy) {
        return
    }
    $base = Find-BasePython
    Write-DeployLog ("创建运行时环境: " + $venv)
    $venvOut = & $base -m venv --without-pip --clear $venv 2>&1
    $venvExit = $LASTEXITCODE
    if ($venvOut) { $venvOut | Out-File -LiteralPath $bootstrapLog -Append -Encoding utf8 }
    if ($venvExit -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) {
        throw '创建 runtime\venv 失败；见 runtime\logs\bootstrap.log'
    }
}

function Ensure-Dependencies {
    $needInstall = $false
    if (-not (Test-PythonModule $venvPy 'numpy')) { $needInstall = $true }
    if (-not (Test-PythonModule $venvPy 'imageio_ffmpeg')) { $needInstall = $true }
    if (-not $needInstall) { return }

    Write-DeployLog '安装 Python 依赖: numpy / imageio-ffmpeg'
    New-Item -ItemType Directory -Force -Path $venvSite | Out-Null
    $base = Find-BasePython
    $pipOut = & $base -m pip install --disable-pip-version-check --no-cache-dir --upgrade --target $venvSite -r $requirements 2>&1
    $pipExit = $LASTEXITCODE
    if ($pipOut) { $pipOut | Out-File -LiteralPath $bootstrapLog -Append -Encoding utf8 }
    if ($pipExit -ne 0) {
        Write-DeployLog ("依赖安装返回 " + $pipExit)
        if (-not (Test-PythonModule $venvPy 'numpy')) {
            throw '依赖安装失败；见 runtime\logs\bootstrap.log'
        }
        Write-DeployLog 'numpy 可用，继续启动；ffmpeg 优先用 venv 内置，缺省时回退系统 PATH'
    }
}

$cfgPath = Join-Path $opsDir 'ops_config.json'
$cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$startPort = [int]$cfg.server.port
$span = [int]$cfg.server.port_span
$ports = $startPort..($startPort + $span - 1)

# 已有服务在跑就直接复用端口，避免重复启动。
foreach ($p in $ports) {
    if (Test-Ops $p) {
        Write-Output $p
        exit 0
    }
}

try {
    Ensure-Venv
    Ensure-Dependencies
} catch {
    Write-DeployLog ("部署失败: " + $_.Exception.Message)
    exit 1
}

$serverOut = Join-Path $logs 'server.out.log'
$serverErr = Join-Path $logs 'server.err.log'
try {
    Start-Process -FilePath $venvPyw -ArgumentList @($server, '--no-browser') -WindowStyle Hidden -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr
} catch {
    Write-DeployLog ("启动失败: " + $_.Exception.Message)
    exit 1
}

for ($i = 0; $i -lt 80; $i++) {
    Start-Sleep -Milliseconds 250
    foreach ($p in $ports) {
        if (Test-Ops $p) {
            Write-Output $p
            exit 0
        }
    }
}

Write-DeployLog '服务启动超时；见 runtime\logs\server.err.log'
exit 1
