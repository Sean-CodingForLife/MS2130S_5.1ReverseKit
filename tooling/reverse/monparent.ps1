$m = Get-PnpDevice -Class Monitor -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -like '*HD TO USB*' } | Select-Object -First 1
if (-not $m) { "monitor not found"; exit }
"monitor: $($m.FriendlyName)  [$($m.InstanceId)]  status=$($m.Status)"
$p = Get-PnpDeviceProperty -InstanceId $m.InstanceId -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue
if ($p) {
    "parent : $($p.Data)"
    $pp = Get-PnpDevice -InstanceId $p.Data -ErrorAction SilentlyContinue
    if ($pp) { "parent name: $($pp.FriendlyName)" }
}
""
"=== display adapters ==="
Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | ForEach-Object {
    "  {0}  [{1}]" -f $_.FriendlyName, $_.InstanceId
}
""
"=== monitors with their parents ==="
foreach ($mon in (Get-PnpDevice -Class Monitor -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'OK' })) {
    $par = (Get-PnpDeviceProperty -InstanceId $mon.InstanceId -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
    $name = (Get-PnpDevice -InstanceId $par -ErrorAction SilentlyContinue).FriendlyName
    "  {0,-30} -> {1}" -f $mon.FriendlyName, $name
}
