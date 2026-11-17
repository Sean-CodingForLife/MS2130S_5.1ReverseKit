param(
    [int]$Seconds = 60,
    [string]$Out = ""
)

# 录制采集卡的 6 声道输出（自动挑选 6 声道的采集端点）
# 用法: powershell -File rec51.ps1 -Seconds 60

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.IO;

public static class Rec51
{
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class EO { }

    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IE { int EnumAudioEndpoints(int f, int m, out IC c); }

    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IC { int GetCount(out int n); int Item(int i, out ID d); }

    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ID {
        int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o);
        int OpenPropertyStore(int a, out IntPtr s);
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
        int GetState(out int st);
    }

    [ComImport, Guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAC {
        int Initialize(int s, int f, long d, long p, IntPtr fmt, IntPtr g);
        int GetBufferSize(out uint n);
        int GetStreamLatency(out long l);
        int GetCurrentPadding(out uint n);
        int IsFormatSupported(int share, IntPtr fmt, out IntPtr c);
        int GetMixFormat(out IntPtr fmt);
        int GetDevicePeriod(out long a, out long b);
        int Start(); int Stop(); int Reset();
        int SetEventHandle(IntPtr h);
        int GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object o);
    }

    [ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IACC {
        int GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong devPos, out ulong qpcPos);
        int ReleaseBuffer(uint frames);
        int GetNextPacketSize(out uint frames);
    }

    public static string Run(int seconds, string outPath)
    {
        var sb = new System.Text.StringBuilder();
        var e = (IE)(new EO());
        IC c; e.EnumAudioEndpoints(1, 1, out c);
        int n; c.GetCount(out n);
        bool done = false;
        for (int i = 0; i < n && !done; i++)
        {
            ID d; c.Item(i, out d);
            string id; d.GetId(out id);
            Guid iid = typeof(IAC).GUID; object o;
            if (d.Activate(ref iid, 0x17, IntPtr.Zero, out o) != 0) continue;
            var ac = (IAC)o;
            IntPtr fmt;
            if (ac.GetMixFormat(out fmt) != 0) continue;
            int ch = Marshal.ReadInt16(fmt, 2);
            if (ch != 6) continue;                       // 只挑 6 声道端点
            int rate = Marshal.ReadInt32(fmt, 4);
            int bits = Marshal.ReadInt16(fmt, 14);

            if (ac.Initialize(0, 0, 20000000L, 0, fmt, IntPtr.Zero) != 0) { sb.AppendLine("Initialize failed"); continue; }
            Guid icc = typeof(IACC).GUID; object so;
            if (ac.GetService(ref icc, out so) != 0) { sb.AppendLine("GetService failed"); continue; }
            var cap = (IACC)so;

            using (var fs = new FileStream(outPath, FileMode.Create, FileAccess.Write))
            using (var bw = new BinaryWriter(fs))
            {
                bw.Write(new char[] { 'R','I','F','F' }); bw.Write(0);
                bw.Write(new char[] { 'W','A','V','E' });
                bw.Write(new char[] { 'f','m','t',' ' }); bw.Write(16);
                bw.Write((short)3); bw.Write((short)ch); bw.Write(rate);
                bw.Write(rate * ch * 4); bw.Write((short)(ch * 4)); bw.Write((short)32);
                bw.Write(new char[] { 'd','a','t','a' });
                long dataBytesPos = fs.Position; bw.Write(0);

                long total = 0;
                ac.Start();
                var end = DateTime.Now.AddSeconds(seconds);
                while (DateTime.Now < end)
                {
                    uint avail; cap.GetNextPacketSize(out avail);
                    if (avail == 0) { Thread.Sleep(10); continue; }
                    IntPtr data; uint frames, flags; ulong dp, qp;
                    if (cap.GetBuffer(out data, out frames, out flags, out dp, out qp) != 0) break;
                    if (data != IntPtr.Zero && frames > 0)
                    {
                        byte[] buf = new byte[frames * ch * 4];
                        if ((flags & 2) == 0) Marshal.Copy(data, buf, 0, buf.Length);
                        bw.Write(buf);
                        total += frames;
                    }
                    cap.ReleaseBuffer(frames);
                }
                ac.Stop();
                long endPos = fs.Position;
                fs.Position = 4; bw.Write((int)(endPos - 8));
                fs.Position = dataBytesPos; bw.Write((int)(endPos - dataBytesPos - 4));
                sb.AppendLine("端点   : " + id);
                sb.AppendLine("格式   : " + ch + "ch / " + rate + "Hz / " + bits + "bit");
                sb.AppendLine("帧数   : " + total + "  (" + (total / (double)rate).ToString("F1") + " 秒)");
                sb.AppendLine("输出   : " + outPath);
                done = true;
            }
        }
        if (!done) sb.AppendLine("没有找到 6 声道的采集端点。请确认采集卡插在 USB 3 口上。");
        return sb.ToString();
    }
}
'@

if ($Out -eq "") {
    $Out = Join-Path ([Environment]::GetFolderPath('MyVideos')) ("ns2_51_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".wav")
}
[Rec51]::Run($Seconds, $Out)
