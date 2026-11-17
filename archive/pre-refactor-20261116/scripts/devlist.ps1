Write-Host "=== monitors ==="
Get-PnpDevice -Class Monitor -ErrorAction SilentlyContinue |
    Select-Object Status, FriendlyName, InstanceId |
    Format-Table -AutoSize | Out-String -Width 160

Write-Host "=== media (audio) devices ==="
Get-PnpDevice -Class MEDIA -ErrorAction SilentlyContinue |
    Select-Object Status, FriendlyName |
    Format-Table -AutoSize | Out-String -Width 120

Write-Host "=== display adapters ==="
Get-PnpDevice -Class Display -ErrorAction SilentlyContinue |
    Select-Object Status, FriendlyName |
    Format-Table -AutoSize | Out-String -Width 120
