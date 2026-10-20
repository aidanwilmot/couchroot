const {test}=require('node:test'),assert=require('node:assert/strict'),crypto=require('crypto'),{EventEmitter}=require('events');
const {RootAgentServer}=require('../agent/service/root-agent');
class Socket extends EventEmitter {
 constructor(){super();this.writes=[];this.destroyed=false;}
 write(data){this.writes.push(data);}
 destroy(){if(!this.destroyed){this.destroyed=true;this.emit('close');}}
}
const digest=data=>crypto.createHash('sha256').update(data).digest('hex');
function setup(){
 const server=new RootAgentServer(),socket=new Socket();server._handle(socket);
 const nonce=Buffer.from(socket.writes[0].trim().split('\t')[1],'hex');
 const frame=payload=>Buffer.from(payload+'\t'+crypto.createHmac('sha256',server.secret).update(nonce).update('\x00').update(payload).digest('hex')+'\n');
 socket.emit('data',frame('AUTH\t42\t0\t0\t0\t0\tff\tVXNlcg=='));
 return {server,socket,frame};
}
for(const size of [0,17,1048576])test('binary download framing, size '+size,async()=>{
 const {server,socket,frame}=setup();try{
  const data=crypto.randomBytes(size),read=server.operation({op:'file.read',offset:13,length:1048576}),exec=server.execute('true',1000);
  const wire=Buffer.concat([frame('OPDATA\t1\t13\t'+size+'\t'+digest(data)),data,frame('RESULT\t2\t0\t0\tb2s=\t')]);
  // Splits the authenticated header and body; the final fragment includes the next frame.
  for(let offset=0;offset<wire.length;){const end=Math.min(wire.length,offset+(offset<100?1:65521));socket.emit('data',wire.subarray(offset,end));offset=end;}
  assert.deepEqual(await read,{data,offset:13,sha256:digest(data)});assert.equal((await exec).stdout,'ok');
 }finally{server.close();}
});
for(const [name,header] of Object.entries({sequence:'OPDATA\t2\t0\t3\t',offset:'OPDATA\t1\t1\t3\t',oversize:'OPDATA\t1\t0\t1048577\t',requestedLength:'OPDATA\t1\t0\t4\t',negative:'OPDATA\t1\t0\t-1\t',unsafeOffset:'OPDATA\t1\t9007199254740992\t3\t'})){
 test('rejects binary '+name,async()=>{const {server,socket,frame}=setup();try{
  const pending=server.operation({op:'file.read',offset:0,length:3});const rejected=assert.rejects(pending,/disconnected/);
  socket.emit('data',frame(header+digest(Buffer.from('abc'))));await rejected;assert.equal(socket.destroyed,true);
 }finally{server.close();}});
}
test('binary digest tampering and truncation never resolve a read',async()=>{
 for(const truncate of [false,true]){const {server,socket,frame}=setup();try{
  const pending=server.operation({op:'file.read',offset:0,length:3});const rejected=assert.rejects(pending,/disconnected/);
  socket.emit('data',Buffer.concat([frame('OPDATA\t1\t0\t3\t'+digest(Buffer.from('abc'))),Buffer.from(truncate?'ab':'abd')]));
  if(truncate)socket.destroy();await rejected;
 }finally{server.close();}}
});
test('binary body cannot be admitted by an unauthenticated header or non-read request',async()=>{
 for(const corrupt of [false,true]){const {server,socket,frame}=setup();try{
  const pending=server.operation({op:corrupt?'file.read':'file.commit',offset:0,length:3});const rejected=assert.rejects(pending,/disconnected/);
  const header=frame('OPDATA\t1\t0\t3\t'+digest(Buffer.from('abc')));if(corrupt)header[header.length-2]^=1;
  socket.emit('data',Buffer.concat([header,Buffer.from('abc')]));await rejected;
 }finally{server.close();}}
});
test('oversized unterminated text frame remains bounded',()=>{
 const {server,socket}=setup();try{socket.emit('data',Buffer.alloc(8*1024*1024+1,65));assert.equal(socket.destroyed,true);}finally{server.close();}
});
