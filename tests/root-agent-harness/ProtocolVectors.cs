using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
internal static partial class SamsungTvRootAgent {
    // Test-only peer. The worker side is the complete production RunSession;
    // no fixture value is ever passed to its reader or admission helpers.
    private sealed class ProtocolPeer : IDisposable {
        internal readonly NetworkStream Wire;
        internal readonly ProtocolReader Reader;
        internal readonly byte[] Secret, Nonce;
        private readonly TcpClient client;
        private readonly Task<Exception> session;
        private readonly string root;
        internal ProtocolPeer(JsonElement vectors, bool hello=true) {
            Secret=Convert.FromHexString(vectors.GetProperty("secret_hex").GetString());
            Nonce=Convert.FromHexString(vectors.GetProperty("nonce_hex").GetString());
            root=Path.Combine(Path.GetTempPath(),"protocol-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
            using var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();
            int port=((IPEndPoint)listener.LocalEndpoint).Port;
            session=Task.Run(()=>{try{RunSession("127.0.0.1",port,Secret,root+"/",root+"/");return null;}catch(Exception e){return e;}});
            client=listener.AcceptTcpClient();Wire=client.GetStream();Wire.ReadTimeout=3000;Wire.WriteTimeout=3000;Reader=new ProtocolReader(Wire);
            if(hello){Raw("SAMSUNG-TV-ROOT/1\t"+HexEncode(Nonce)+"\n");Check(Receive().StartsWith("AUTH\t"),"missing real AUTH");}
        }
        internal void Raw(string value){Wire.Write(Encoding.UTF8.GetBytes(value));}
        internal void Send(string value,bool upper=false,bool bad=false,bool crlf=false) {
            string mac=bad?new string('0',64):Authenticate(Nonce,Secret,value);
            Raw(value+"\t"+(upper?mac.ToUpperInvariant():mac)+(crlf?"\r\n":"\n"));
        }
        internal string Receive(){return VerifyAuthenticated(Reader.ReadLine(),Nonce,Secret);}
        internal void StillOpen() {Check(!session.Wait(100),"exact line limit closed before LF");}
        internal void Rejected(string name) {
            Check(session.Wait(2000),name+": worker did not promptly terminate");
            Check(session.Result!=null,name+": worker accepted invalid input");
        }
        public void Dispose(){client.Dispose();Check(session.Wait(3000),"real session did not close");Directory.Delete(root,true);}
    }
    public static void TestProtocolVectors() {
        if (!OperatingSystem.IsLinux()) { Console.WriteLine("SKIP real worker sessions require Linux setsid (covered by Linux CI)"); return; }
        using var doc=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"root-protocol.json")));
        var root=doc.RootElement;var limits=root.GetProperty("limits");
        using(var peer=new ProtocolPeer(root,false)) {
            peer.Raw(new string('x',limits.GetProperty("preauth_bytes").GetInt32()+1));
            peer.Rejected("oversized unterminated greeting");
        }
        foreach(var v in root.GetProperty("exec_timeouts").EnumerateArray()) {
            using var peer=new ProtocolPeer(root);
            peer.Send("EXEC\t1\t"+v.GetProperty("ms").GetInt32()+"\t"+Convert.ToBase64String(Encoding.UTF8.GetBytes("printf ok")));
            if(v.GetProperty("accepted").GetBoolean())Check(peer.Receive()=="RESULT\t1\t0\t0\tb2s=\t","real EXEC timeout dispatch mismatch");
            else peer.Rejected("EXEC timeout");
        }
        int max=limits.GetProperty("command_bytes").GetInt32();
        foreach(int length in new[]{0,max,max+1}) {
            using var peer=new ProtocolPeer(root);
            string command=length==0?"":":"+new string(' ',length-1);
            peer.Send("EXEC\t1\t1000\t"+Convert.ToBase64String(Encoding.UTF8.GetBytes(command)));
            if(length>0&&length<=max)Check(peer.Receive()=="RESULT\t1\t0\t0\t\t","real EXEC command boundary rejected");
            else peer.Rejected("EXEC command length");
        }
        int output=limits.GetProperty("output_bytes").GetInt32();
        using(var peer=new ProtocolPeer(root)) {
            string command=$"head -c {output+17} /dev/zero; head -c {output+17} /dev/zero >&2";
            peer.Send("EXEC\t1\t5000\t"+Convert.ToBase64String(Encoding.UTF8.GetBytes(command)));
            var result=peer.Receive().Split('\t');
            Check(result[0]=="RESULT"&&result[2]=="0"&&result[3]=="0","real output command failed");
            Check(Convert.FromBase64String(result[4]).SequenceEqual(new byte[output]),"real stdout bound mismatch");
            Check(Convert.FromBase64String(result[5]).SequenceEqual(new byte[output].Concat(Encoding.UTF8.GetBytes(root.GetProperty("output_limit_notice").GetString()))),"real stderr bound mismatch");
        }
        foreach(var v in root.GetProperty("session_frames").EnumerateArray()) {
            using var peer=new ProtocolPeer(root);peer.Send("PING\t1");Check(peer.Receive().StartsWith("PONG\t1\t"),"real PING failed");
            bool Flag(string name)=>v.TryGetProperty(name,out var flag)&&flag.GetBoolean();
            if(v.TryGetProperty("raw",out var raw))peer.Raw(raw.GetString());
            else peer.Send(v.GetProperty("payload").GetString(),Flag("uppercase_mac"),Flag("bad_mac"),Flag("crlf"));
            if(v.GetProperty("managed").GetBoolean())Check(peer.Receive().StartsWith("PONG\t2\t"),"real session frame mismatch");
            else peer.Rejected(v.GetProperty("name").GetString());
        }
        using(var peer=new ProtocolPeer(root)) {
            peer.Raw(new string('x',limits.GetProperty("frame_bytes").GetInt32()));peer.StillOpen();
            peer.Raw("x");peer.Rejected("authenticated line bound");
        }
        Check(ChunkBytes==limits.GetProperty("binary_chunk_bytes").GetInt32(),"binary chunk limit drift");
        Console.WriteLine("PASS shared vectors through real managed greeting/EXEC/session dispatch");
    }
}
