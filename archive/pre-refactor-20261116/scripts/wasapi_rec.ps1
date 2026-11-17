Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;

public static class Wrec
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

    public static string Capture(string guidPart, int seconds)
    {
        var sb = new System.Text.StringBuilder();
        var e = (IE)(new EO());
        IC c; e.EnumAudioEndpoints(1, 1, out c);
        int n; c.GetCount(out n);
        for (int i = 0; i < n; i++)
        {
            ID d; c.Item(i, out d);
            string id; d.GetId(out id);
            if (!id.Contains(guidPart)) continue;

            Guid iid = typeof(IAC).GUID; object o;
            if (d.Activate(ref iid, 0x17, IntPtr.Zero, out o) != 0) { sb.AppendLine("activate failed"); continue; }
            var ac = (IAC)o;

            IntPtr fmt; ac.GetMixFormat(out fmt);
            int ch = Marshal.ReadInt16(fmt, 2);
            int rate = Marshal.ReadInt32(fmt, 4);
            int bits = Marshal.ReadInt16(fmt, 14);
            int tag = Marshal.ReadInt16(fmt, 0);
            sb.AppendLine("mix: " + ch + "ch " + rate + "Hz " + bits + "bit tag=0x" + tag.ToString("X"));

            int hr = ac.Initialize(0, 0, 20000000L, 0, fmt, IntPtr.Zero);
            if (hr != 0) { sb.AppendLine("Initialize failed 0x" + hr.ToString("X8")); continue; }

            Guid icc = typeof(IACC).GUID; object so;
            if (ac.GetService(ref icc, out so) != 0) { sb.AppendLine("GetService failed"); continue; }
            var cap = (IACC)so;

            double[] sum = new double[ch];
            long count = 0;

            ac.Start();
            var end = DateTime.Now.AddSeconds(seconds);
            while (DateTime.Now < end)
            {
                uint avail;
                cap.GetNextPacketSize(out avail);
                if (avail == 0) { Thread.Sleep(20); continue; }
                IntPtr data; uint frames, flags; ulong dp, qp;
                if (cap.GetBuffer(out data, out frames, out flags, out dp, out qp) != 0) break;
                bool silent = (flags & 2) != 0;
                if (!silent && data != IntPtr.Zero && frames > 0)
                {
                    float[] tmp = new float[frames * ch];
                    Marshal.Copy(data, tmp, 0, tmp.Length);
                    for (int f = 0; f < frames; f++)
                        for (int k = 0; k < ch; k++)
                            sum[k] += tmp[f * ch + k] * tmp[f * ch + k];
                    count += frames;
                }
                cap.ReleaseBuffer(frames);
            }
            ac.Stop();

            sb.AppendLine("frames captured: " + count);
            for (int k = 0; k < ch; k++)
            {
                double rms = count > 0 ? Math.Sqrt(sum[k] / count) : 0;
                double db = rms > 0 ? 20 * Math.Log10(rms) : -120;
                sb.AppendLine(string.Format("  ch{0}: rms={1:F5}  {2:F1} dBFS", k, rms, db));
            }
        }
        return sb.ToString();
    }
}
'@
[Wrec]::Capture("f7a7c431", 4)
