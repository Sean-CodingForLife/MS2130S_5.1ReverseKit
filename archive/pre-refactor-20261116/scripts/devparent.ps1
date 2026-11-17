$id = 'USB\VID_345F&PID_2132\20210629'
foreach ($k in 'DEVPKEY_Device_Parent','DEVPKEY_Device_LocationInfo','DEVPKEY_Device_Address') {
    try {
        $p = Get-PnpDeviceProperty -InstanceId $id -KeyName $k -ErrorAction Stop
        "{0,-30}: {1}" -f $k, $p.Data
    } catch {
        "{0,-30}: failed ({1})" -f $k, $_.Exception.Message
    }
}
try {
    $parentId = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_Parent').Data
    if ($parentId) {
        $pp = Get-PnpDevice -InstanceId $parentId -ErrorAction SilentlyContinue
        if ($pp) {
            "parent device              : {0} [{1}]" -f $pp.FriendlyName, $pp.InstanceId
            $pn = Get-PnpDeviceProperty -InstanceId $parentId -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue
            if ($pn) {
                $gp = Get-PnpDevice -InstanceId $pn.Data -ErrorAction SilentlyContinue
                if ($gp) { "grandparent                : {0} [{1}]" -f $gp.FriendlyName, $gp.InstanceId }
            }
        }
    }
} catch { "parent lookup failed: $($_.Exception.Message)" }
