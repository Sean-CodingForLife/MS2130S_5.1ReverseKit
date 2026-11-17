param([string]$NamePart = "")
if ($NamePart -eq "ALL") { $NamePart = "" }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class Wprobe
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
        int IsFormatSupported(int share, IntPtr fmt, out IntPtr closest);
        int GetMixFormat(out IntPtr fmt);
        int GetDevicePeriod(out long a, out long b);
    }

    static readonly Guid SUB_PCM   = new Guid("00000001-0000-0010-8000-00AA00389B71");
    static readonly Guid SUB_FLOAT = new Guid("00000003-0000-0010-8000-00AA00389B71");

    static IntPtr MK(int ch, int rate, int bits, int container, int mask, bool flt)
    {
        int cb = 18 + 22;
        IntPtr p = Marshal.AllocHGlobal(cb);
        for (int i = 0; i < cb; i++) Marshal.WriteByte(p, i, 0);
        Marshal.WriteInt16(p, 0, unchecked((short)0xFFFE));
        Marshal.WriteInt16(p, 2, (short)ch);
        Marshal.WriteInt32(p, 4, rate);
        Marshal.WriteInt32(p, 8, rate * ch * (container / 8));
        Marshal.WriteInt16(p, 12, (short)(ch * (container / 8)));
        Marshal.WriteInt16(p, 14, (short)container);
        Marshal.WriteInt16(p, 16, (short)22);
        Marshal.WriteInt16(p, 18, (short)bits);
        Marshal.WriteInt32(p, 20, mask);
        byte[] g = (flt ? SUB_FLOAT : SUB_PCM).ToByteArray();
        Marshal.Copy(g, 0, (IntPtr)(p.ToInt64() + 24), 16);
        return p;
    }

    public static string Run(string namePart)
    {
        var sb = new System.Text.StringBuilder();
        var e = (IE)(new EO());
        IC c; e.EnumAudioEndpoints(1, 1, out c);
        int n; c.GetCount(out n);
        for (int i = 0; i < n; i++)
        {
            ID d; c.Item(i, out d);
            string id; d.GetId(out id);
            if (namePart.Length > 0 && id.IndexOf(namePart, StringComparison.OrdinalIgnoreCase) < 0) continue;

            Guid iid = typeof(IAC).GUID; object o;
            if (d.Activate(ref iid, 0x17, IntPtr.Zero, out o) != 0) { sb.AppendLine("activate failed"); continue; }
            var ac = (IAC)o;

            IntPtr mf;
            string mix = "?";
            try {
                ac.GetMixFormat(out mf);
                mix = Marshal.ReadInt16(mf, 2) + "ch/" + Marshal.ReadInt32(mf, 4) + "Hz/" +
                      Marshal.ReadInt16(mf, 14) + "bit container, validbits=" + Marshal.ReadInt16(mf, 18) +
                      " mask=0x" + Marshal.ReadInt32(mf, 20).ToString("X");
            } catch (Exception ex) { mix = "GetMixFormat ERR " + ex.Message; }
            sb.AppendLine("ENDPOINT " + id);
            sb.AppendLine("  mixformat: " + mix);

            int[][] cases = new int[][] {
                new int[]{2,48000,16,16,0x3,0},
                new int[]{6,48000,16,16,0x3F,0},
                new int[]{6,48000,24,32,0x3F,0},
                new int[]{6,48000,32,32,0x3F,1},
                new int[]{8,48000,16,16,0x63F,0},
                new int[]{2,96000,24,32,0x3,0},
                new int[]{2,96000,16,16,0x3,0},
                new int[]{6,96000,24,32,0x3F,0},
            };
            foreach (int[] k in cases)
            {
                IntPtr f = MK(k[0], k[1], k[2], k[3], k[4], k[5] != 0);
                string label = k[0] + "ch/" + k[1] + "Hz/" + k[2] + "in" + k[3] + (k[5] != 0 ? "f" : "") + " mask=0x" + k[4].ToString("X");
                IntPtr clo;
                string rs = "ERR", rx = "ERR";
                try { int hs = ac.IsFormatSupported(0, f, out clo); rs = "0x" + hs.ToString("X8"); }
                catch (Exception ex) { rs = "EX:" + (uint)ex.HResult; }
                try { int hx = ac.IsFormatSupported(1, f, out clo); rx = "0x" + hx.ToString("X8"); }
                catch (Exception ex) { rx = "EX:" + (uint)ex.HResult; }
                sb.AppendLine("  " + label.PadRight(38) + " shared=" + rs + "  exclusive=" + rx);
                Marshal.FreeHGlobal(f);
            }
        }
        return sb.ToString();
    }
}
'@

[Wprobe]::Run($NamePart)
