$id = 'USB\VID_345F&PID_2132\20210629'
foreach ($k in 'DEVPKEY_Device_LastArrivalDate','DEVPKEY_Device_InstallDate','DEVPKEY_Device_LastRemovalDate') {
    try {
        $p = Get-PnpDeviceProperty -InstanceId $id -KeyName $k -ErrorAction Stop
        "{0,-32}: {1}" -f $k, $p.Data
    } catch {
        "{0,-32}: failed ({1})" -f $k, $_.Exception.Message
    }
}
try {
    $d = Get-PnpDevice -InstanceId $id -ErrorAction Stop
    "Status                          : {0}  Problem={1}" -f $d.Status, $d.Problem
} catch {
    "Get-PnpDevice failed: $($_.Exception.Message)"
}
