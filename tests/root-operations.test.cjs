const {test}=require('node:test'),assert=require('node:assert/strict'),crypto=require('crypto'),{EventEmitter}=require('events');
const {RootAgentServer}=require('../research/autonomous-root/service/vendor/root-agent');
class Socket extends EventEmitter {
 constructor(){super();this.writes=[];this.destroyed=false;}
 write(data){this.writes.push(data);}
 destroy(){this.destroyed=true;this.emit('close');}
}
function setup(){
 const server=new RootAgentServer(),socket=new Socket();server._handle(socket);
 const nonce=Buffer.from(socket.writes[0].trim().split('\t')[1],'hex');
 const send=payload=>{const mac=crypto.createHmac('sha256',server.secret).update(nonce).update('\x00').update(payload).digest('hex');socket.emit('data',Buffer.from(payload+'\t'+mac+'\n'));};
 send('AUTH\t42\t0\t0\t0\t0\tff\tVXNlcg==');return {server,socket,send};
}
test('authenticated worker operation returns a large binary chunk intact',async()=>{
 const {server,send}=setup();try{
  const data=crypto.randomBytes(1048576),pending=server.operation({op:'file.read',transfer_id:'test',offset:0,length:data.length});
  send('OPRESULT\t1\t'+Buffer.from(JSON.stringify({ok:true,result:{data:data.toString('base64'),sha256:crypto.createHash('sha256').update(data).digest('hex')}})).toString('base64'));
  assert.deepEqual(Buffer.from((await pending).data,'base64'),data);
 }finally{server.close();}
});
test('known worker failure preserves failure outcome and keeps channel usable',async()=>{
 const {server,socket,send}=setup();try{
  const pending=server.operation({op:'file.commit',transfer_id:'test'});
  send('OPRESULT\t1\t'+Buffer.from(JSON.stringify({ok:false,outcome:'failed',error:'hash conflict'})).toString('base64'));
  await assert.rejects(pending,e=>e.outcome==='failed'&&e.message==='hash conflict');assert.equal(socket.destroyed,false);
 }finally{server.close();}
});
test('disconnect leaves operation uncertain instead of claiming rejection',async()=>{
 const {server,socket}=setup();const pending=server.operation({op:'job.start'});socket.destroy();
 await assert.rejects(pending,e=>!e.outcome);server.close();
});
test('binary uploads authenticate metadata and send exact raw bytes without JSON/base64',async()=>{
 const {server,socket,send}=setup();try{
  for(const size of [17,1048576]){
   const data=crypto.randomBytes(size),sha256=crypto.createHash('sha256').update(data).digest('hex');
   const seq=server._conn._sequence+1,start=socket.writes.length;
   const pending=server.operation({op:'file.write',transfer_id:'a'.repeat(32),offset:0,sha256},data);
   assert.equal(socket.writes.length,start+2);
   const fields=socket.writes[start].trimEnd().split('\t'),mac=fields.pop(),payload=fields.join('\t');
   assert.equal(payload,`OPWRITE\t${seq}\t${'a'.repeat(32)}\t0\t${size}\t${sha256}`);
   const nonce=Buffer.from(socket.writes[0].trim().split('\t')[1],'hex');
   assert.equal(mac,crypto.createHmac('sha256',server.secret).update(nonce).update('\0').update(payload).digest('hex'));
   assert.deepEqual(socket.writes[start+1],data);
   send(`OPRESULT\t${seq}\t`+Buffer.from(JSON.stringify({ok:true,result:{offset:size}})).toString('base64'));
   assert.equal((await pending).offset,size);
  }
 }finally{server.close();}
});
test('invalid binary upload metadata sends nothing; lost upload is never replayed',async()=>{
 const {server,socket}=setup(),op={op:'file.write',transfer_id:'a'.repeat(32),offset:0,sha256:'b'.repeat(64)};
 try{
  const before=socket.writes.length;
  for(const [value,data] of [[op,Buffer.alloc(0)],[op,Buffer.alloc(1048577)],[{...op,offset:-1},Buffer.alloc(1)],[{...op,offset:2147483648},Buffer.alloc(1)],[{...op,transfer_id:'bad\nframe'},Buffer.alloc(1)],[{...op,sha256:'bad'},Buffer.alloc(1)],[{...op,transfer_id:op.transfer_id+'\n'},Buffer.alloc(1)],[{...op,sha256:op.sha256+'\n'},Buffer.alloc(1)],[{...op,op:'file.commit'},Buffer.alloc(1)]])
   await assert.rejects(server.operation(value,data),e=>e.outcome==='rejected');
  assert.equal(socket.writes.length,before);
  const pending=server.operation(op,Buffer.alloc(1));socket.destroy();
  await assert.rejects(pending,e=>!e.outcome);assert.equal(socket.writes.length,before+2);
 }finally{server.close();}
});
