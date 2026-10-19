using System;
using System.IO;
using System.Text;
using System.Text.Json;
internal static partial class SamsungTvRootAgent {
    private static void TestProtocolVectors() {
        using var doc=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"root-protocol.json")));
        var root=doc.RootElement;var nonce=Convert.FromHexString(root.GetProperty("nonce_hex").GetString());var secret=Convert.FromHexString(root.GetProperty("secret_hex").GetString());
        Check(MaximumLineBytes==root.GetProperty("limits").GetProperty("frame_bytes").GetInt32(),"frame limit drift");
        Check(MaximumCommandTimeoutMilliseconds==root.GetProperty("limits").GetProperty("exec_max_ms").GetInt32(),"EXEC timeout drift");
        Check(MaximumPreauthBytes==root.GetProperty("limits").GetProperty("preauth_bytes").GetInt32(),"preauth limit drift");
        foreach(var v in root.GetProperty("exec_timeouts").EnumerateArray())Check(ValidExecTimeout(v.GetProperty("ms").GetInt32())==v.GetProperty("accepted").GetBoolean(),"EXEC timeout acceptance drift");
        foreach(var v in root.GetProperty("frames").EnumerateArray()) {
            var reader=new ProtocolReader(new MemoryStream(Encoding.UTF8.GetBytes(v.GetProperty("wire").GetString())));
            string line=reader.ReadLine();
            if(v.GetProperty("mac_valid").GetBoolean())Check(VerifyAuthenticated(line,nonce,secret)==v.GetProperty("payload").GetString(),"shared frame mismatch");
            else Reject(()=>VerifyAuthenticated(line,nonce,secret),"invalid shared MAC accepted");
        }
        foreach(var v in root.GetProperty("lines").EnumerateArray()) {
            var reader=new ProtocolReader(new MemoryStream(Encoding.UTF8.GetBytes(new string('x',v.GetProperty("bytes").GetInt32())+"\n")));
            int limit=v.GetProperty("limit").GetInt32();
            if(v.GetProperty("accepted").GetBoolean())Check(reader.ReadLine(limit).Length==v.GetProperty("bytes").GetInt32(),"line boundary rejected");
            else Reject(()=>reader.ReadLine(limit),"oversize shared line accepted");
        }
        Console.WriteLine("PASS shared protocol vectors (AUTH admission belongs to the JS server)");
    }
}
