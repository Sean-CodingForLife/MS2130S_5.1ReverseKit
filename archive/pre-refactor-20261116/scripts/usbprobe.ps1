Write-Host "sampling USB presence for 10s (instance 20210621 / any VID_345F) ..."
for ($i = 0; $i -lt 10; $i++) {
    $line = (Get-Date -Format 'HH:mm:ss')
    $devs = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_345F' }
    if ($devs) {
        $ids = ($devs | ForEach-Object { "{0}[{1}]" -f ($_.InstanceId -replace '.*\\',''), $_.Status }) -join ' '
        Write-Host "$line  PRESENT: $ids"
    } else {
        Write-Host "$line  absent"
    }
    Start-Sleep -Seconds 1
}
Write-Host ""
Write-Host "=== recent system events (USB / device) ==="
Get-WinEvent -LogName System -MaxEvents 400 -ErrorAction SilentlyContinue |
    Where-Object { $_.ProviderName -match 'USB|Kernel-PnP' -and $_.TimeCreated -gt (Get-Date).AddMinutes(-30) } |
    Select-Object -First 15 TimeCreated, Id, LevelDisplayName, ProviderName |
    Format-Table -AutoSize | Out-String -Width 140
