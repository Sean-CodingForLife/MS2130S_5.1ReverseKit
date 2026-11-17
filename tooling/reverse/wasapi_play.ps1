param(
    [string]$GuidPart = "",
    [double]$ToneSeconds = 1.2,
    [double]$GapSeconds = 0.4,
    [double]$Amplitude = 0.25
)

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Generic;

public static class Play
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

    [ComImport, Guid("F294ACFC-3146-4483-A7BF-ADDCA7C260E2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IARC {
        int GetBuffer(uint frames, out IntPtr data);
        int ReleaseBuffer(uint frames, uint flags);
    }

    public static string Run(string guidPart, double toneSec, double gapSec, double amp)
    {
        var sb = new System.Text.StringBuilder();
        var e = (IE)(new EO());
        IC c; e.EnumAudioEndpoints(0, 1, out c);
        int n; c.GetCount(out n);

        ID target = null; string targetId = null; int targetCh = 0;
        for (int i = 0; i < n; i++)
        {
            ID d; c.Item(i, out d);
            string id; d.GetId(out id);
            Guid iid = typeof(IAC).GUID; object o;
            if (d.Activate(ref iid, 0x17, IntPtr.Zero, out o) != 0) continue;
            var ac = (IAC)o;
            IntPtr f; ac.GetMixFormat(out f);
            int ch = Marshal.ReadInt16(f, 2);
            sb.AppendLine("candidate " + id + "  " + ch + "ch");
            bool match = guidPart.Length > 0 ? id.Contains(guidPart) : (ch >= 6);
            if (match && (target == null || ch > targetCh)) { target = d; targetId = id; targetCh = ch; }
        }
        if (target == null) return sb.AppendLine("no matching render endpoint").ToString();
        sb.AppendLine("TARGET " + targetId + "  " + targetCh + "ch");

        Guid gi = typeof(IAC).GUID; object obj;
        target.Activate(ref gi, 0x17, IntPtr.Zero, out obj);
        var client = (IAC)obj;
        IntPtr fmt; client.GetMixFormat(out fmt);
        int ch2 = Marshal.ReadInt16(fmt, 2);
        int rate = Marshal.ReadInt32(fmt, 4);
        int bits = Marshal.ReadInt16(fmt, 14);
        sb.AppendLine("mix " + ch2 + "ch " + rate + "Hz " + bits + "bit");

        int hr = client.Initialize(0, 0, 20000000L, 0, fmt, IntPtr.Zero);
        if (hr != 0) return sb.AppendLine("Initialize failed 0x" + hr.ToString("X8")).ToString();

        uint bufFrames; client.GetBufferSize(out bufFrames);
        Guid arc = typeof(IARC).GUID; object ro;
        client.GetService(ref arc, out ro);
        var render = (IARC)ro;

        // plan: 1s silence, then one tone per channel, then 1s silence
        int nch = ch2;
        double[] planStart = new double[nch];
        for (int k = 0; k < nch; k++) planStart[k] = 1.0 + k * (toneSec + gapSec);
        double total = 1.0 + nch * (toneSec + gapSec) + 1.0;

        int framesWritten = 0;
        long totalFrames = (long)(total * rate);
        client.Start();
        var sw = System.Diagnostics.Stopwatch.StartNew();
        byte[] block = null;

        while (framesWritten < totalFrames)
        {
            uint pad; client.GetCurrentPadding(out pad);
            uint avail = bufFrames - pad;
            if (avail > 512) avail = 512;
            if (avail == 0) { Thread.Sleep(5); continue; }

            IntPtr p; render.GetBuffer(avail, out p);
            block = new byte[avail * nch * 4];
            for (uint f = 0; f < avail; f++)
            {
                double t = (framesWritten + f) / (double)rate;
                for (int k = 0; k < nch; k++)
                {
                    double v = 0;
                    double dt = t - planStart[k];
                    if (dt >= 0 && dt < toneSec)
                    {
                        double freq = 400 + 200 * k;
                        v = amp * Math.Sin(2 * Math.PI * freq * dt);
                    }
                    float fv = (float)v;
                    byte[] b = BitConverter.GetBytes(fv);
                    int off = (int)((f * nch + k) * 4);
                    block[off] = b[0]; block[off+1] = b[1]; block[off+2] = b[2]; block[off+3] = b[3];
                }
            }
            Marshal.Copy(block, 0, p, block.Length);
            render.ReleaseBuffer(avail, 0);
            framesWritten += (int)avail;
        }
        client.Stop();
        sb.AppendLine("played " + (framesWritten / (double)rate).ToString("F2") + "s");
        return sb.ToString();
    }
}
'@

[Play]::Run($GuidPart, $ToneSeconds, $GapSeconds, $Amplitude)
