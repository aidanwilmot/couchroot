using System;
using System.IO;
using System.Linq;
using System.Text;
internal static partial class SamsungTvRootAgent
{
    private sealed class FragmentStream : MemoryStream
    {
        private readonly int fragment;
        public int Calls;
        public FragmentStream(byte[] data, int fragment) : base(data) { this.fragment = fragment; }
        public override int Read(byte[] data, int offset, int count)
        { Calls++; return base.Read(data, offset, Math.Min(count, fragment)); }
        public override int ReadByte() { throw new Exception("Unbuffered byte read"); }
    }
    private static void RejectOversized(ProtocolReader reader)
    {
        try { reader.ReadLine(); } catch (InvalidDataException) { return; }
        throw new Exception("oversized line accepted");
    }
    private static void TestProtocolReader()
    {
        byte[] binary = new byte[] { 0, 10, 13, 255, 128 };
        byte[] wire = Encoding.UTF8.GetBytes("hello ☃\r\n").Concat(binary)
            .Concat(Encoding.UTF8.GetBytes("next\n\n")).ToArray();
        foreach (int fragment in new[] { 1, 3, 65536 })
        {
            using (var stream = new FragmentStream(wire, fragment))
            {
                var reader = new ProtocolReader(stream);
                Check(reader.ReadLine() == "hello ☃", "fragmented UTF-8/CRLF");
                Check(reader.ReadExact(0).Length == 0, "zero length read");
                Check(reader.ReadExact(binary.Length).SequenceEqual(binary), "prefetched binary lost");
                Check(reader.ReadLine() == "next" && reader.ReadLine() == "", "coalesced lines lost");
                Reject(() => reader.ReadLine(), "EOF accepted");
            }
        }
        foreach (int size in new[] { 65535, 65536, MaximumLineBytes, MaximumLineBytes + 1 })
        {
            byte[] data = Enumerable.Repeat((byte)'x', size).Concat(new byte[] { 10 }).ToArray();
            using (var stream = new FragmentStream(data, 65536))
            {
                var reader = new ProtocolReader(stream);
                if (size > MaximumLineBytes) RejectOversized(reader);
                else Check(reader.ReadLine().Length == size, "boundary line corrupted");
                Check(stream.Calls <= size / 65536 + 1, "excessive underlying reads");
            }
        }
        byte[] largeBinary = new byte[128 * 1024 + 17];
        new Random(9).NextBytes(largeBinary);
        using (var stream = new FragmentStream(Encoding.UTF8.GetBytes("payload\n")
            .Concat(largeBinary).Concat(Encoding.UTF8.GetBytes("done\n")).ToArray(), 65536))
        {
            var reader = new ProtocolReader(stream);
            Check(reader.ReadLine() == "payload", "binary prefix corrupted");
            Check(reader.ReadExact(largeBinary.Length).SequenceEqual(largeBinary), "multi-buffer binary corrupted");
            Check(reader.ReadLine() == "done", "binary suffix corrupted");
        }
        Reject(() => new ProtocolReader(new MemoryStream(new byte[] { 1 })).ReadExact(2), "truncated binary accepted");
        Reject(() => new ProtocolReader(new MemoryStream(new byte[] { 1 })).ReadLine(), "unterminated line accepted");
        Console.WriteLine("PASS buffered protocol: fragmented/coalesced frames, UTF-8, binary read-ahead, limits, EOF and bounded read calls");
    }
}
