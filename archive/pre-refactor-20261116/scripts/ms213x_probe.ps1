$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.ComponentModel;
using Microsoft.Win32.SafeHandles;

public class Xp
{
    const uint GR = 0x80000000, GW = 0x40000000, SH = 3, OE = 3;
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern SafeFileHandle CreateFileW(string n, uint a, uint s, IntPtr sec, uint d, uint f, IntPtr t);
    [DllImport("hid.dll", SetLastError = true)] static extern bool HidD_SetFeature(SafeFileHandle h, byte[] b, int l);
    [DllImport("hid.dll", SetLastError = true)] static extern bool HidD_GetFeature(SafeFileHandle h, byte[] b, int l);
    [DllImport("hid.dll", SetLastError = true)] static extern bool HidD_GetPreparsedData(SafeFileHandle h, out IntPtr p);
    [DllImport("hid.dll", SetLastError = true)] static extern bool HidD_FreePreparsedData(IntPtr p);
    [DllImport("hid.dll")] static extern int HidP_GetCaps(IntPtr p, out CAPS c);

    [StructLayout(LayoutKind.Sequential)]
    public struct CAPS {
        public ushort Usage, UsagePage, InputReportByteLength, OutputReportByteLength, FeatureReportByteLength;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 17)] public ushort[] Reserved;
        public ushort A,B,C,D,E,F,G,H,I,J;
    }

    SafeFileHandle h; int len;

    public void Open(string p)
    {
        h = CreateFileW(p, GR | GW, SH, IntPtr.Zero, OE, 0, IntPtr.Zero);
        if (h.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateFile");
        IntPtr prep; HidD_GetPreparsedData(h, out prep);
        CAPS c; HidP_GetCaps(prep, out c); HidD_FreePreparsedData(prep);
        len = c.FeatureReportByteLength; if (len < 9) len = 9;
    }

    public string Probe(ushort addr)
    {
        byte[] cmd = new byte[len]; cmd[0] = 0x01;
        cmd[1] = 0xb5; cmd[2] = (byte)(addr >> 8); cmd[3] = (byte)(addr & 0xff);
        if (!HidD_SetFeature(h, cmd, cmd.Length)) return "setfail";
        byte[] r = new byte[len]; r[0] = 0x01;
        if (!HidD_GetFeature(h, r, r.Length)) return "getfail";
        var sb = new System.Text.StringBuilder();
        for (int i = 0; i < 9; i++) sb.Append(r[i].ToString("x2") + " ");
        return sb.ToString();
    }
}
'@

$guid = '{4d1e55b2-f16f-11cf-88cb-001111000030}'
$root = "HKLM:\SYSTEM\CurrentControlSet\Control\DeviceClasses\$guid"
$dev = $null
foreach ($k in Get-ChildItem $root) {
    if ($k.PSChildName -match 'vid_345f' -and $k.PSChildName -match 'pid_2132') {
        $p = ($k.PSChildName -replace '^##\?#', '\\?\')
        try { $c = New-Object Xp; $c.Open($p); $dev = $c; break } catch { }
    }
}
if (-not $dev) { throw "no device" }

foreach ($a in @(0xF000, 0xF001, 0xF002, 0xF010, 0xF0F0, 0x0000, 0x1234)) {
    "0x{0:X4} : {1}" -f $a, $dev.Probe([Convert]::ToUInt16($a))
}
