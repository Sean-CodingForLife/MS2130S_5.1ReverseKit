param(
    [string]$Start = "0xF000",
    [string]$End   = "0xF0FF",
    [string]$Out   = "D:\Backups\workspace\xdata_dump.bin"
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.ComponentModel;
using Microsoft.Win32.SafeHandles;

public class Xd
{
    const uint GENERIC_READ  = 0x80000000;
    const uint GENERIC_WRITE = 0x40000000;
    const uint FILE_SHARE_RW = 0x00000003;
    const uint OPEN_EXISTING = 3;

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern SafeFileHandle CreateFileW(string name, uint access, uint share,
        IntPtr sec, uint disp, uint flags, IntPtr tmpl);
    [DllImport("hid.dll", SetLastError = true)]
    static extern bool HidD_SetFeature(SafeFileHandle h, byte[] buf, int len);
    [DllImport("hid.dll", SetLastError = true)]
    static extern bool HidD_GetFeature(SafeFileHandle h, byte[] buf, int len);
    [DllImport("hid.dll", SetLastError = true)]
    static extern bool HidD_GetPreparsedData(SafeFileHandle h, out IntPtr data);
    [DllImport("hid.dll", SetLastError = true)]
    static extern bool HidD_FreePreparsedData(IntPtr data);
    [DllImport("hid.dll")]
    static extern int HidP_GetCaps(IntPtr prep, out HIDP_CAPS caps);

    [StructLayout(LayoutKind.Sequential)]
    public struct HIDP_CAPS
    {
        public ushort Usage, UsagePage, InputReportByteLength, OutputReportByteLength, FeatureReportByteLength;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 17)] public ushort[] Reserved;
        public ushort NumberLinkCollectionNodes, NumberInputButtonCaps, NumberInputValueCaps, NumberInputDataIndices;
        public ushort NumberOutputButtonCaps, NumberOutputValueCaps, NumberOutputDataIndices;
        public ushort NumberFeatureButtonCaps, NumberFeatureValueCaps, NumberFeatureDataIndices;
    }

    SafeFileHandle h; int featLen;

    public void Open(string path)
    {
        h = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
        if (h.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateFile");
        IntPtr prep;
        if (!HidD_GetPreparsedData(h, out prep)) throw new Win32Exception(Marshal.GetLastWin32Error(), "GetPreparsedData");
        HIDP_CAPS caps; int st = HidP_GetCaps(prep, out caps);
        HidD_FreePreparsedData(prep);
        if (st != 0x00110000) throw new Exception("GetCaps 0x" + st.ToString("X8"));
        featLen = caps.FeatureReportByteLength; if (featLen < 9) featLen = 9;
    }

    void Send(byte[] cmd)
    {
        byte[] buf = new byte[featLen]; buf[0] = 0x01;
        Array.Copy(cmd, 0, buf, 1, Math.Min(cmd.Length, featLen - 1));
        if (!HidD_SetFeature(h, buf, buf.Length)) throw new Win32Exception(Marshal.GetLastWin32Error(), "SetFeature");
    }

    byte[] Recv()
    {
        byte[] buf = new byte[featLen]; buf[0] = 0x01;
        if (!HidD_GetFeature(h, buf, buf.Length)) throw new Win32Exception(Marshal.GetLastWin32Error(), "GetFeature");
        return buf;
    }

    public byte ReadReg(ushort addr)
    {
        Send(new byte[] { 0xb5, (byte)(addr >> 8), (byte)(addr & 0xff), 0, 0, 0, 0, 0 });
        return Recv()[4];
    }

    public byte[] Dump(ushort from, ushort to)
    {
        int n = to - from + 1;
        byte[] r = new byte[n];
        for (int i = 0; i < n; i++) r[i] = ReadReg((ushort)(from + i));
        return r;
    }

    public void Close() { if (h != null) h.Dispose(); }
}
'@

$guid = '{4d1e55b2-f16f-11cf-88cb-001111000030}'
$root = "HKLM:\SYSTEM\CurrentControlSet\Control\DeviceClasses\$guid"
$paths = @()
foreach ($k in Get-ChildItem $root) {
    if ($k.PSChildName -match 'vid_345f' -and $k.PSChildName -match 'pid_2132') {
        $paths += ($k.PSChildName -replace '^##\?#', '\\?\')
    }
}
if (-not $paths) { throw "capture card HID interface not found" }

$dev = $null
foreach ($p in $paths) {
    try {
        $cand = New-Object Xd
        $cand.Open($p)
        $dev = $cand
        Write-Host "opened: $p"
        break
    } catch {
        Write-Host "skip (not present): $p"
    }
}
if (-not $dev) { throw "could not open any HID interface" }

$from = [Convert]::ToUInt16($Start, 16)
$to   = [Convert]::ToUInt16($End, 16)
Write-Host ("dumping XDATA 0x{0:X4}-0x{1:X4} ({2} bytes) ..." -f $from, $to, ($to - $from + 1))
$data = $dev.Dump($from, $to)
[IO.File]::WriteAllBytes($Out, $data)
$dev.Close()

$hex = ($data[0..([Math]::Min(63, $data.Length - 1))] | ForEach-Object { $_.ToString('x2') }) -join ' '
Write-Host "first 64 bytes: $hex"
Write-Host "saved to $Out"
