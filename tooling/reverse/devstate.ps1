$ids = @(
    'USB\VID_345F&PID_2132\20210620',
    'USB\VID_345F&PID_2132\20210629',
    'USB\VID_345F&PID_2132&MI_02\6&36abc626&0&0002',
    'USB\VID_345F&PID_2132&MI_02\7&3640a5a0&0&0002'
)
foreach ($id in $ids) {
    try {
        $d = Get-PnpDevice -InstanceId $id -ErrorAction Stop
        "{0}`n   Status={1} Problem={2} Present={3}" -f $id, $d.Status, $d.Problem, $d.Present
    } catch {
        "{0}`n   <not found>" -f $id
    }
}
"--- audio capture endpoints for USB3 PLUS ---"
Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture' | ForEach-Object {
    $p = Join-Path $_.PSPath 'Properties'
    if (Test-Path $p) {
        $pr = Get-ItemProperty $p
        foreach ($prop in $pr.PSObject.Properties) {
            if ($prop.Value -is [string] -and $prop.Value -match 'USB3 PLUS') {
                "   {0}  state={1}  name={2}" -f $_.PSChildName, (Get-ItemProperty $_.PSPath).DeviceState, $prop.Value
            }
        }
    }
}
