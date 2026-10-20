'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),EventEmitter=require('node:events');
const crypto=require('node:crypto');
const vectors=require('../fixtures/root-protocol.json');
const {RootAgentServer}=require('../../agent/service/root-agent');
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
  const {exec_min_ms:min,exec_max_ms:max}=vectors.limits;
  const boundaries=[{ms:min-1,accepted:false},{ms:min,accepted:true},{ms:max,accepted:true},{ms:max+1,accepted:false}];
  for(const v of [...vectors.exec_timeouts,...boundaries]){
   const before=socket.writes.length,pending=server.execute('true',v.ms);
   if(v.accepted){assert.equal(socket.writes.length,before+1);server._conn._failPending(Error('test complete'));await assert.rejects(pending,/test complete/);}
   else{await assert.rejects(pending,/timeout/);assert.equal(socket.writes.length,before);}
  }
 }finally{server.close();}
});

test('shared protocol: real auth timer uses the fixture deadline',()=>{
 const schedule=global.setTimeout;let callback,delay;
 global.setTimeout=(fn,ms)=>{callback=fn;delay=ms;return 0;};
 let connection;
 try {connection=open();} finally {global.setTimeout=schedule;}
 try {
  assert.equal(delay,vectors.limits.auth_timeout_ms);
  assert.equal(connection.socket.destroyed,false);callback();
  assert.equal(connection.socket.destroyed,true);
 }finally{connection.server.close();}
});
test('shared protocol: real JS command size admission and whitespace difference',async()=>{
 const {server,socket}=open();
 try {
  socket.emit('data',Buffer.from(vectors.frames[0].wire));
  const pending=server.execute(':'.padEnd(vectors.limits.command_bytes,' '),1000);
  server._conn._failPending(Error('test complete'));await assert.rejects(pending,/test complete/);
  await assert.rejects(server.execute('x'.repeat(vectors.limits.command_bytes+1),1000),/oversized/);
  await assert.rejects(server.execute('   ',1000),/invalid/);
 }finally{server.close();}
});
test('parity limits reference the protocol fixture instead of duplicating values',()=>{
 const contract=require('../worker-parity/contract.json');
 const linked=require(require('node:path').resolve(__dirname,'../worker-parity',contract.shared_protocol_limits.fixture));
 for(const [old,key] of Object.entries(contract.shared_protocol_limits.keys)) {
  assert.equal(Object.hasOwn(contract.limits,old),false);
  assert.equal(linked.limits[key],vectors.limits[key]);assert.equal(typeof linked.limits[key],'number');
 }
});
for(const style of ['uppercase','empty','crlf'])test('shared server framing: '+style,()=>{
 const {server,socket}=open();
 try {
  let auth=vectors.frames[0].wire;
  if(style==='uppercase'){const i=auth.lastIndexOf('\t');auth=auth.slice(0,i+1)+auth.slice(i+1).toUpperCase();}
  if(style==='crlf')auth=auth.replace('\n','\r\n');
  if(style==='empty'){socket.emit('data',Buffer.from('\n'));assert.equal(socket.destroyed,false);}
  socket.emit('data',Buffer.from(auth));
  assert.equal(!!server._conn,style==='empty');
 }finally{server.close();}
});
