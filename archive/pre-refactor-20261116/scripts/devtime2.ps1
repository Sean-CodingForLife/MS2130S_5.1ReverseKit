$ids = @('USB\VID_345F&PID_2132\20210620','USB\VID_345F&PID_2132\20210629')
foreach ($id in $ids) {
    try {
        $d = Get-PnpDevice -InstanceId $id -ErrorAction Stop
        "== $id"
        "   Status=$($d.Status)  Problem=$($d.Problem)  Present=$($d.Present)"
        foreach ($k in 'DEVPKEY_Device_LastArrivalDate','DEVPKEY_Device_LastRemovalDate') {
            try {
                $p = Get-PnpDeviceProperty -InstanceId $id -KeyName $k -ErrorAction Stop
                "   {0,-28}: {1}" -f $k, $p.Data
            } catch { }
        }
    } catch {
        "== $id  <not found>"
    }
}
