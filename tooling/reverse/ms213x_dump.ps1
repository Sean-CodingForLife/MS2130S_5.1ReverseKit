# MS2130S flash backup over the vendor HID interface (read-only).
# Protocol re-implemented from steve-m/ms213x_flash (MIT).
#
#   .\ms213x_dump.ps1 -Test
#   .\ms213x_dump.ps1 -Dump .\backup.bin

param(
    [switch]$Test,
    [string]$Dump
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using System.ComponentModel;
using System.Collections.Generic;
using Microsoft.Win32.SafeHandles;

public class Ms213x
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
    static extern int HidP_GetCaps(IntPtr preparsed, out HIDP_CAPS caps);

    [StructLayout(LayoutKind.Sequential)]
    public struct HIDP_CAPS
    {
        public ushort Usage;
        public ushort UsagePage;
        public ushort InputReportByteLength;
        public ushort OutputReportByteLength;
        public ushort FeatureReportByteLength;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 17)]
        public ushort[] Reserved;
        public ushort NumberLinkCollectionNodes;
        public ushort NumberInputButtonCaps;
        public ushort NumberInputValueCaps;
        public ushort NumberInputDataIndices;
        public ushort NumberOutputButtonCaps;
        public ushort NumberOutputValueCaps;
        public ushort NumberOutputDataIndices;
        public ushort NumberFeatureButtonCaps;
        public ushort NumberFeatureValueCaps;
        public ushort NumberFeatureDataIndices;
    }

    SafeFileHandle h;
    int featLen;

    public int FeatureLength { get { return featLen; } }

    public void Open(string path)
    {
        h = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW,
                        IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
        if (h.IsInvalid)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "CreateFile failed");

        IntPtr prep;
        if (!HidD_GetPreparsedData(h, out prep))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "HidD_GetPreparsedData failed");

        HIDP_CAPS caps;
        int st = HidP_GetCaps(prep, out caps);
        HidD_FreePreparsedData(prep);
        if (st != 0x00110000)   // HIDP_STATUS_SUCCESS
            throw new Exception("HidP_GetCaps failed: 0x" + st.ToString("X8"));

        featLen = caps.FeatureReportByteLength;
        if (featLen < 9) featLen = 9;
    }

    void Send(byte[] cmd)
    {
        byte[] buf = new byte[featLen];
        buf[0] = 0x01;
        Array.Copy(cmd, 0, buf, 1, Math.Min(cmd.Length, featLen - 1));
        if (!HidD_SetFeature(h, buf, buf.Length))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "HidD_SetFeature failed");
    }

    byte[] Recv()
    {
        byte[] buf = new byte[featLen];
        buf[0] = 0x01;
        if (!HidD_GetFeature(h, buf, buf.Length))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "HidD_GetFeature failed");
        return buf;
    }

    public void WriteReg(ushort addr, byte val)
    {
        Send(new byte[] { 0xb6, (byte)(addr >> 8), (byte)addr, val, 0, 0, 0, 0 });
    }

    public byte ReadSfr(byte addr)
    {
        Send(new byte[] { 0xc5, addr, 0, 0, 0, 0, 0, 0 });
        return Recv()[2];
    }

    public void WriteSfr(byte addr, byte val)
    {
        Send(new byte[] { 0xc6, addr, val, 0, 0, 0, 0, 0 });
    }

    public void SetupSpi()
    {
        WriteReg(0xf01f, 0x00);

        byte p3 = ReadSfr(0xb0);
        p3 |= 0x20;
        p3 = (byte)(p3 & ~0x1c);
        WriteSfr(0xb0, p3);

        byte p2 = ReadSfr(0xa0);
        p2 |= 0x1c;
        WriteSfr(0xa0, p2);

        WriteReg(0xf01f, 0x10);
    }

    public void ReadPage(int addr, byte[] dst, int off)
    {
        Send(new byte[] { 0xf7, 0x01, (byte)((addr >> 16) & 0xff), (byte)((addr >> 8) & 0xff),
                          (byte)(addr & 0xff), 0x01, 0x00, 0x00 });

        for (int o = 0; o < 256; o += 8)
        {
            Send(new byte[] { 0xf7, 0x00, 0x00, 0x00, 0x00, (byte)(o >> 8), (byte)(o & 0xff), 0x00 });
            byte[] r = Recv();
            Array.Copy(r, 1, dst, off + o, 8);
        }
    }

    public byte[] Dump(int total)
    {
        byte[] buf = new byte[total + 256];
        for (int a = 0; a < total; a += 256)
            ReadPage(a, buf, a);
        byte[] res = new byte[total];
        Array.Copy(buf, res, total);
        return res;
    }

    public void Close()
    {
        if (h != null) h.Dispose();
    }
}
'@

function Find-DevicePath {
    $guid = '{4d1e55b2-f16f-11cf-88cb-001111000030}'
    $root = "HKLM:\SYSTEM\CurrentControlSet\Control\DeviceClasses\$guid"
    foreach ($k in Get-ChildItem $root) {
        $name = $k.PSChildName
        if ($name -match 'vid_345f' -and $name -match 'pid_2132') {
            # registry escapes the leading \\?\ as ##?#
            return ($name -replace '^##\?#', '\\?\')
        }
    }
    return $null
}

$path = Find-DevicePath
if (-not $path) { throw "capture card HID interface not found" }
Write-Host "device: $path"

$dev = New-Object Ms213x
$dev.Open($path)
Write-Host ("feature report length: {0}" -f $dev.FeatureLength)

Write-Host "SPI setup..."
$dev.SetupSpi()

if ($Test) {
    $buf = New-Object byte[] 512
    $dev.ReadPage(0, $buf, 0)
    $hex = ($buf[0..63] | ForEach-Object { $_.ToString('x2') }) -join ' '
    Write-Host "first 64 bytes of flash:"
    Write-Host $hex
    Write-Host ("header magic: {0:X2} {1:X2}  (expect 3C C3)" -f $buf[0], $buf[1])
    $dev.Close()
    return
}

if ($Dump) {
    $total = 98356
    $sw = [Diagnostics.Stopwatch]::StartNew()
    Write-Host "reading $total bytes..."
    $data = $dev.Dump($total)
    $sw.Stop()
    [IO.File]::WriteAllBytes((Resolve-Path -LiteralPath (Split-Path -Parent $Dump)).Path + '\' + (Split-Path -Leaf $Dump), $data)
    Write-Host ("read {0} bytes in {1:N1}s" -f $total, $sw.Elapsed.TotalSeconds)

    $headerLen = 0x30
    $codeLen = 98304
    $hdr = 0; for ($i = 2; $i -lt $headerLen; $i++) { if (($i -lt 0x0c) -or ($i -gt 0x0f)) { $hdr += $data[$i] } }
    $hdr = $hdr -band 0xffff
    $code = 0; for ($i = 0; $i -lt $codeLen; $i++) { $code += $data[$headerLen + $i] }
    $code = $code -band 0xffff

    $hStored = ($data[$headerLen + $codeLen] -shl 8) -bor $data[$headerLen + $codeLen + 1]
    $cStored = ($data[$headerLen + $codeLen + 2] -shl 8) -bor $data[$headerLen + $codeLen + 3]

    Write-Host ("header checksum: calc {0:X4} / stored {1:X4}  {2}" -f $hdr, $hStored, $(if ($hdr -eq $hStored) { 'OK' } else { 'MISMATCH' }))
    Write-Host ("code   checksum: calc {0:X4} / stored {1:X4}  {2}" -f $code, $cStored, $(if ($code -eq $cStored) { 'OK' } else { 'MISMATCH' }))
    $dev.Close()
    return
}

Write-Host "nothing to do; use -Test or -Dump <file>"
$dev.Close()
