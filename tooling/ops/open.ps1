$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# start_service.ps1 会复用已在跑的服务；拿不到端口说明部署失败，直接打开部署日志。
$port = & (Join-Path $PSScriptRoot 'start_service.ps1')
if (-not $port) {
    $log = Join-Path $root 'runtime\logs\bootstrap.log'
    if (Test-Path -LiteralPath $log) {
        Start-Process -FilePath $log
    }
    exit 1
}
Start-Process "http://127.0.0.1:$port/"
