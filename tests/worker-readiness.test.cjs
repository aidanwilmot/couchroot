'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{EventEmitter}=require('node:events');
const {createRequire}=require('node:module');
const {validateReadiness}=require('../research/autonomous-root/service/worker-readiness');
const BOOT='00000000-0000-0000-0000-000000000001',DIGEST='a'.repeat(64);
function managed(){return {boot_id:BOOT,uptime_seconds:3,worker_id:'b'.repeat(32),capabilities:['file-transfer-v1','binary-download-v1','binary-upload-v1','jobs-v1','app-profile-v1','helper-view-v1','native-app-launcher-v1'],app_launcher:{implementation:'native',sha256:DIGEST}};}
function native(){return {...managed(),implementation:'native-prototype',lifetime_mode:'production',lifetime_seconds:0,guardian_pid:42,capabilities:['prototype-production-files-v1','binary-upload-v1','binary-download-v1','prototype-app-exec-v1','prototype-jobs-v1','prototype-helper-lifecycle-v1','prototype-independent-launcher-v1','prototype-crash-guardian-v1','prototype-command-fault-diagnostics-v1'],app_launcher:{sha256:DIGEST,independently_staged:true}};}
test('managed deployed shape and additive diagnostics remain compatible',()=>{
 const info=managed();info.extra='diagnostic';info.capabilities.push('future-diagnostic-v1');
 assert.equal(validateReadiness(info,{implementation:'managed',bootId:BOOT}),info);
 info.implementation='managed';assert.equal(validateReadiness(info,{implementation:'managed',bootId:BOOT,launcherSha256:DIGEST}),info);
});
test('wrong boot identities capabilities implementations and launchers cannot become ready',()=>{
 const cases=[v=>v.boot_id='00000000-0000-0000-0000-000000000002',v=>v.uptime_seconds=-1,v=>v.uptime_seconds=NaN,
  v=>v.worker_id='not-a-worker',v=>v.capabilities.pop(),v=>v.capabilities.push(v.capabilities[0]),v=>v.implementation='native-prototype',
  v=>v.app_launcher.sha256='invalid',v=>v.app_launcher.implementation='managed',v=>v.capabilities=undefined];
 for(const change of cases){const info=managed();change(info);assert.throws(()=>validateReadiness(info,{implementation:'managed',bootId:BOOT}));}
 assert.throws(()=>validateReadiness(managed(),{implementation:'managed',bootId:BOOT,launcherSha256:'c'.repeat(64)}));
 assert.throws(()=>validateReadiness(managed(),{implementation:'managed',bootId:'not-a-boot'}));
});
test('native readiness requires pinned launcher and production lifetime',()=>{
 const expected={implementation:'native-prototype',bootId:BOOT,launcherSha256:DIGEST};
 assert.equal(validateReadiness(native(),expected).implementation,'native-prototype');
 for(const change of [v=>v.lifetime_seconds=300,v=>v.lifetime_mode='bounded',v=>v.guardian_pid=0,v=>v.app_launcher.independently_staged=false,v=>v.capabilities[0]='prototype-scoped-files-v1']){const info=native();change(info);assert.throws(()=>validateReadiness(info,expected));}
 assert.throws(()=>validateReadiness(native(),{implementation:'native-prototype',bootId:BOOT}));
 assert.throws(()=>validateReadiness(managed(),expected));
});
function fixture(options={}){
 const source=path.resolve(__dirname,'../research/autonomous-root/service/agent.js');
 const realRequire=createRequire(source),channels=[],timers=[];
 class Channel {
  constructor(options){this.options=options;this._conn=null;this._server=new EventEmitter();this.executions=0;channels.push(this);}
  start(callback){callback();}
  close(){if(this._conn)this._conn._socket.destroy();}
  listeningPort(){return 12345;}
  operation(){this.executions++;return Promise.resolve({});}
  execute(){this.executions++;return Promise.resolve({exit_code:0});}
  connect(){
   let resolve,reject;const pending=new Promise((yes,no)=>{resolve=yes;reject=no;});
   const conn={identity:{uid:0},operation:()=>pending,_socket:{destroy:()=>{if(this._conn===conn){this._conn=null;this.options.onClose();}}}};
   this._conn=conn;this.options.onConnect(conn);return {resolve,reject,conn};
  }
 }
 const module={exports:{}};
 vm.runInNewContext(fs.readFileSync(source,'utf8'),{module,exports:module.exports,__dirname:path.dirname(source),process,Buffer,
  setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout:()=>{},
  require:name=>name==='./vendor/root-agent'?{RootAgentServer:Channel}:name==='./vendor/sdb'?{connect:()=>new Promise(()=>{}),close:()=>{}}:realRequire(name)});
 const agent=module.exports.createAgent({device:'qn90a'},{verifyFirmware:()=>{},readBootId:()=>BOOT,...options});
 return {agent,channels,timers};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('service blocks operations while checking and clears readiness on disconnect',async()=>{
 const {agent,channels}=fixture();agent.start();const channel=channels[0],pending=channel.connect();
 try{
  assert.equal(agent.status().phase,'checking');
  await assert.rejects(agent.execute('true',100),e=>e.outcome==='rejected');
  await assert.rejects(agent.operation({op:'file.status'}),e=>e.outcome==='rejected');
  assert.equal(channel.executions,0);
  pending.resolve(managed());await flush();assert.equal(agent.status().worker_ready,true);
  await agent.execute('true',100);assert.equal(channel.executions,1);
  pending.conn._socket.destroy();assert.equal(agent.status().worker_ready,false);assert.equal(agent.status().worker_id,null);assert.deepEqual(Array.from(agent.status().capabilities),[]);
 }finally{agent.stop();}
});
test('late status cannot revive disconnected or superseded generations',async()=>{
 for(const restart of [false,true]){
  const {agent,channels}=fixture();agent.start();const pending=channels[0].connect();
  try{
   if(restart){agent.stop();agent.start();}else pending.conn._socket.destroy();
   pending.resolve(managed());await flush();assert.equal(agent.status().worker_ready,false);assert.equal(agent.status().last_root_acquired_at,null);
  }finally{agent.stop();}
 }
});
test('invalid managed readiness closes the connection before command admission',async()=>{
 const {agent,channels}=fixture();agent.start();const pending=channels[0].connect();
 try{
  pending.resolve(native());await flush();assert.equal(agent.status().connected,false);assert.equal(agent.status().worker_ready,false);
  assert.match(agent.status().last_error,/implementation mismatch/);await assert.rejects(agent.execute('true',100));assert.equal(channels[0].executions,0);
 }finally{agent.stop();}
});

test('late rejection from a closed peer cannot overwrite its replacement readiness',async()=>{
 const {agent,channels}=fixture();agent.start();const old=channels[0].connect();old.conn._socket.destroy();
 const replacement=channels[0].connect();
 try{
  replacement.resolve(managed());await flush();assert.equal(agent.status().worker_ready,true);
  old.reject(Error('stale status failure'));await flush();
  assert.equal(agent.status().worker_ready,true);assert.equal(agent.status().last_error,null);
 }finally{agent.stop();}
});

test('a newly pending selection blocks admission without silently killing active work',async()=>{
 const os=require('node:os'),{SelectionJournal}=require('../research/autonomous-root/service/worker-selection');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'selection-admission-')),file=path.join(dir,'selection.json'),journal=new SelectionJournal(file);
 const managedVersion='a'.repeat(64);journal.initialize({implementation:'managed',manifest_sha256:managedVersion});
 const {agent,channels}=fixture({selectionFile:file,managedVersion:()=>managedVersion});agent.start();const pending=channels[0].connect();
 try{
  pending.resolve(managed());await flush();assert.equal(agent.status().worker_ready,true);
  journal.begin(1,{implementation:'native-prototype',manifest_sha256:'b'.repeat(64)},'c'.repeat(64));
  assert.equal(agent.status().phase,'selection-required');assert.equal(agent.status().worker_ready,false);assert.equal(agent.status().connected,true);
  await assert.rejects(agent.execute('true',100),e=>e.outcome==='rejected');await assert.rejects(agent.operation({op:'job.start'}),e=>e.outcome==='rejected');assert.equal(channels[0].executions,0);
 }finally{agent.stop();fs.rmSync(dir,{recursive:true,force:true});}
});
