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
