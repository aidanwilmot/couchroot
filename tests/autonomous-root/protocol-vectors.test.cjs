'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),EventEmitter=require('node:events');
const crypto=require('node:crypto');
const vectors=require('../fixtures/root-protocol.json');
const {RootAgentServer}=require('../../research/autonomous-root/service/root-agent');
class Socket extends EventEmitter {
 constructor(){super();this.writes=[];this.destroyed=false;}
 write(value){this.writes.push(value);}
 destroy(){if(!this.destroyed){this.destroyed=true;this.emit('close');}}
}
const secret=Buffer.from(vectors.secret_hex,'hex'),nonce=Buffer.from(vectors.nonce_hex,'hex');
function open(){
 const server=new RootAgentServer({secret}),socket=new Socket();
 const random=crypto.randomBytes;crypto.randomBytes=()=>nonce;
 try {server._handle(socket);}finally{crypto.randomBytes=random;}
 return {server,socket};
}
for(const vector of vectors.frames)test('shared protocol: '+vector.name,()=>{
 const {server,socket}=open();
 try {
  const verify=()=>server._verify(vector.wire.slice(0,-1),nonce);
  if(vector.mac_valid)assert.equal(verify(),vector.payload);else assert.throws(verify);
  if('auth_valid' in vector){socket.emit('data',Buffer.from(vector.wire));assert.equal(!!server._conn,vector.auth_valid);}
 }finally{server.close();}
});
for(const vector of vectors.lines)test('shared protocol: '+vector.name,()=>{
 const {server,socket}=open();let verified=false;
 try {
  if(vector.limit===vectors.limits.frame_bytes)socket.emit('data',Buffer.from(vectors.frames[0].wire));
  const verify=server._verify.bind(server);server._verify=(...args)=>{verified=true;return verify(...args);};
  socket.emit('data',Buffer.from('x'.repeat(vector.bytes)+'\n'));
  assert.equal(verified,vector.accepted);assert.equal(socket.destroyed,true);
 }finally{server.close();}
});
test('shared protocol: pre-auth admission and EXEC timeout limits',async()=>{
 const {server,socket}=open();
 try {
  const peers=[socket];for(let n=1;n<vectors.limits.preauth_peers;n++){const peer=new Socket();peers.push(peer);server._handle(peer);assert.equal(peer.destroyed,false);}
  const extra=new Socket();server._handle(extra);assert.equal(extra.destroyed,true);
  socket.emit('data',Buffer.from(vectors.frames[0].wire));
  for(const v of vectors.exec_timeouts){
   const before=socket.writes.length,pending=server.execute('true',v.ms);
   if(v.accepted){assert.equal(socket.writes.length,before+1);server._conn._failPending(Error('test complete'));await assert.rejects(pending,/test complete/);}
   else{await assert.rejects(pending,/timeout/);assert.equal(socket.writes.length,before);}
  }
 }finally{server.close();}
});
