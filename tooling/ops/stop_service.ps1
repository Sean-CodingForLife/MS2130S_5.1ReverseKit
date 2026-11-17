$ErrorActionPreference = 'Stop'

# 关闭本项目的操作台服务。优先读 runtime/tmp/server.json 的 PID 与真实脚本路径；
# 只有 PID、脚本路径都对得上才结束进程，不按项目名模糊匹配，也不碰其他 Python。
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$runtimeRel = 'runtime'
$cfgPath = Join-Path $PSScriptRoot 'ops_config.json'
try {
    $cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.workspace -and $cfg.workspace.runtime) {
        $runtimeRel = [string]$cfg.workspace.runtime
    }
} catch {
}
$runtime = Join-Path $root $runtimeRel
$log = Join-Path $runtime 'logs\stop.log'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null

function Write-StopLog([string]$message) {
    try {
        Add-Content -LiteralPath $log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message) -Encoding UTF8
    } catch {
    }
}

function Get-ProcessInfo([int]$processId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
}

function Test-CommandHas([string]$commandLine, [string]$scriptPath) {
    if (-not $commandLine -or -not $scriptPath) {
        return $false
    }
    return $commandLine.IndexOf($scriptPath, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

$statePath = Join-Path $runtime 'tmp\server.json'
$state = $null
if (Test-Path -LiteralPath $statePath) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
    }
}

$serverPid = 0
$scriptPath = ''
if ($state) {
    $serverPid = [int]$state.pid
    $scriptPath = [string]$state.script
}

if ($serverPid -gt 0 -and $scriptPath) {
    $proc = Get-ProcessInfo $serverPid
    if (-not $proc) {
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
        Write-StopLog '记录的服务进程已不存在'
        exit 0
    }

    if (-not (Test-CommandHas ([string]$proc.CommandLine) $scriptPath)) {
        Write-StopLog ("PID {0} 已被其他进程复用，拒绝结束" -f $serverPid)
        exit 1
    }

    $killPid = $serverPid
    $parentId = [int]$proc.ParentProcessId
    if ($parentId -gt 0) {
        $parent = Get-ProcessInfo $parentId
        if ($parent -and (Test-CommandHas ([string]$parent.CommandLine) $scriptPath)) {
            $killPid = $parentId
        }
    }

    try {
        taskkill /PID $killPid /T /F 2>$null | Out-Null
    } catch {
    }
    Start-Sleep -Milliseconds 600

    if (Get-ProcessInfo $serverPid) {
        Write-StopLog ("进程 {0} 未退出" -f $serverPid)
        exit 1
    }

    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    Write-StopLog ("已关闭服务，进程树: {0}" -f $killPid)
    exit 0
}

# 兼容没有状态文件的旧服务：只按当前项目 server.py 的绝对路径精确匹配。
$currentServer = Join-Path $root 'tooling\ops\server.py'
$targets = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { Test-CommandHas ([string]$_.CommandLine) $currentServer })

if ($targets.Count -eq 0) {
    Write-StopLog '没有发现运行中的操作台服务'
    exit 0
}

$pids = @()
foreach ($t in $targets) {
    $pids += $t.ProcessId
    try {
        taskkill /PID $t.ProcessId /T /F 2>$null | Out-Null
    } catch {
    }
}
Start-Sleep -Milliseconds 600

$left = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { Test-CommandHas ([string]$_.CommandLine) $currentServer })
if ($left.Count -gt 0) {
    Write-StopLog ("仍有服务进程: " + (($left | ForEach-Object { $_.ProcessId }) -join ', '))
    exit 1
}

Write-StopLog ("已关闭服务，进程: " + ($pids -join ', '))
exit 0
