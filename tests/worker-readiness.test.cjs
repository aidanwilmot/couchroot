'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{EventEmitter}=require('node:events');
const {createRequire}=require('node:module');
const {validateReadiness,validateResourceInventory}=require('../research/autonomous-root/service/worker-readiness');
const BOOT='00000000-0000-0000-0000-000000000001',DIGEST='a'.repeat(64);
function managed(){return {boot_id:BOOT,uptime_seconds:3,worker_id:'b'.repeat(32),capabilities:['file-transfer-v1','binary-download-v1','binary-upload-v1','jobs-v1','app-profile-v1','helper-view-v1','native-app-launcher-v1'],app_launcher:{implementation:'native',sha256:DIGEST}};}
function native(){return {...managed(),implementation:'native-prototype',lifetime_mode:'production',lifetime_seconds:0,guardian_pid:42,capabilities:['prototype-production-files-v1','binary-upload-v1','binary-download-v1','prototype-app-exec-v1','prototype-jobs-v1','prototype-helper-lifecycle-v1','prototype-independent-launcher-v1','prototype-crash-guardian-v1','prototype-command-fault-diagnostics-v1'],app_launcher:{sha256:DIGEST,independently_staged:true}};}
function inventoried(){const info=managed();info.capabilities.push('resource-inventory-v1','worker-process-identity-v1');info.processes={worker:{pid:42,start_ticks:'123'},guardian:null};info.resources={schema:1,scope:'worker-owned',transfers:[],jobs:[],helpers:[]};return info;}
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
   const conn={identity:{uid:0,pid:42},operation:()=>pending,_socket:{destroy:()=>{if(this._conn===conn){this._conn=null;this.options.onClose();}}}};
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
test('inventory requires explicit capability bounded identities and known shapes',()=>{
 const info=inventoried();assert.equal(validateResourceInventory(info),info.resources);
 const invalid=[v=>v.capabilities=v.capabilities.filter(c=>c!=='resource-inventory-v1'),v=>v.resources.scope='all',v=>v.resources.extra=true,
  v=>v.resources.jobs.push({id:'valid-job-identity',state:'running',monitor_finished:'false'}),
  v=>v.resources.transfers.push({id:'a'.repeat(32),direction:'other'}),
  v=>v.resources.helpers=Array(9).fill('a'.repeat(32)),v=>v.resources.helpers=['a'.repeat(32),'a'.repeat(32)],
  v=>v.resources.jobs=Array(17).fill({id:'valid-job-identity',state:'running',monitor_finished:false})];
 for(const change of invalid){const v=inventoried();change(v);assert.throws(()=>validateResourceInventory(v));}
 assert.throws(()=>validateResourceInventory(managed()));
});
test('handoff hold drains admitted work and takes fresh inventory before explicit release',async()=>{
 const {agent,channels}=fixture();agent.start();const channel=channels[0],ready=channel.connect();
 try{
  ready.resolve(managed());await flush();
  let complete;channel.execute=()=>new Promise(resolve=>{complete=resolve;});
  let reads=0;const info=inventoried();info.resources.jobs.push({id:'active-job-identity',state:'running',monitor_finished:false});
  channel.operation=async value=>{assert.equal(value.op,'status');reads++;return info;};
  const execution=agent.execute('running command',1000),hold=agent.holdAdmission();
  assert.equal(agent.status().admission_held,true);assert.equal(agent.status().in_flight_requests,1);
  assert.equal(agent.status().worker_ready,false);assert.equal(agent.status().phase,'draining');
  assert.throws(()=>agent.holdAdmission());
  await assert.rejects(agent.operation({op:'job.start'}),e=>e.outcome==='rejected');
  await assert.rejects(agent.execute('must not run',100),e=>e.outcome==='rejected');
  const inventory=hold.snapshot();await flush();assert.equal(reads,0);
  complete({exit_code:0});await execution;const snapshot=await inventory;
  assert.equal(reads,1);assert.equal(snapshot.worker_id,managed().worker_id);assert.equal(snapshot.resources.jobs[0].state,'running');
  assert.equal(agent.status().in_flight_requests,0);assert.equal(agent.status().admission_held,true);
  snapshot.resources.jobs.length=0;assert.equal(info.resources.jobs.length,1);
  hold.release();assert.equal(agent.status().admission_held,false);assert.throws(()=>hold.release());
  assert.equal(agent.status().worker_ready,true);
  await agent.operation({op:'status'});assert.equal(reads,2);
 }finally{agent.stop();}
});
test('uncertain drain and old workers leave admission held without reading or replaying',async()=>{
 for(const outcome of ['unknown',undefined,'failed','rejected']){
  const {agent,channels}=fixture();agent.start();const channel=channels[0],ready=channel.connect();
  try{
   ready.resolve(managed());await flush();let reject;
   channel.execute=()=>new Promise((yes,no)=>{reject=no;});let reads=0;
   channel.operation=async()=>{reads++;return inventoried();};
   const request=agent.execute('once',1000);const failed=assert.rejects(request);
   const hold=agent.holdAdmission(),snapshot=hold.snapshot();
   const expected=['failed','rejected'].includes(outcome)?snapshot:assert.rejects(snapshot,/Uncertain request/);
   reject(Object.assign(Error('failure'),{outcome}));await failed;await expected;
   assert.equal(reads,['failed','rejected'].includes(outcome)?1:0);assert.equal(agent.status().admission_held,true);
   hold.release();
  }finally{agent.stop();}
 }
});
test('handoff inventory refuses replacement connections late replies and legacy status',async()=>{
 for(const mode of ['replacement','stop','legacy','wrong-worker']){
  const {agent,channels}=fixture();agent.start();const channel=channels[0],ready=channel.connect();
  try{
   ready.resolve(managed());await flush();let finish;
   channel.operation=()=>new Promise(resolve=>{finish=resolve;});
   const hold=agent.holdAdmission(),snapshot=hold.snapshot(),refused=assert.rejects(snapshot);await flush();
   if(mode==='replacement'){ready.conn._socket.destroy();const next=channel.connect();next.resolve(managed());await flush();}
   if(mode==='stop')agent.stop();
   const info=mode==='legacy'?managed():inventoried();if(mode==='wrong-worker')info.worker_id='c'.repeat(32);
   finish(info);await refused;
   if(['replacement','stop'].includes(mode))assert.throws(()=>hold.release());
   else{assert.equal(agent.status().admission_held,true);hold.release();}
  }finally{agent.stop();}
 }
});
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

test('handoff shutdown binds durable inventory, observes exit, and suppresses reacquisition',async()=>{
 const os=require('node:os'),crypto=require('node:crypto'),{SelectionJournal}=require('../research/autonomous-root/service/worker-selection');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'handoff-stop-')),file=path.join(dir,'selection.json'),journal=new SelectionJournal(file);
 journal.initialize({implementation:'managed',manifest_sha256:DIGEST});let live=true,stops=0;
 const readProcessFile=p=>{if(p.endsWith('boot_id'))return BOOT;if(!live)throw Object.assign(Error('gone'),{code:'ENOENT'});return '42 (worker) S '+Array(18).fill('0').join(' ')+' 123 0';};
 const {agent,channels,timers}=fixture({selectionFile:file,managedVersion:()=>DIGEST,readProcessFile});
 agent.start();const channel=channels[0],ready=channel.connect();
 try{
  ready.resolve(managed());await flush();channel.operation=async()=>inventoried();
  const hold=agent.holdAdmission(),inventory=await hold.snapshot();
  await assert.rejects(hold.shutdown('unbound'),/Selection/);assert.equal(stops,0);
  const digest=crypto.createHash('sha256').update(JSON.stringify(inventory)).digest('hex');
  const state=journal.begin(1,{implementation:'native-prototype',manifest_sha256:'c'.repeat(64)},digest);
  channel.shutdown=async()=>{stops++;live=false;ready.conn._socket.destroy();return {acknowledged:true,disconnected:true};};
  const outcomes=await Promise.allSettled([hold.shutdown(state.pending.id),hold.shutdown(state.pending.id)]);
  assert.equal(outcomes.filter(r=>r.status==='fulfilled').length,1);assert.equal(outcomes.filter(r=>r.status==='rejected').length,1);
  const result=outcomes.find(r=>r.status==='fulfilled').value;
  assert.equal(result.transaction_id,state.pending.id);assert.equal(result.source_manifest_sha256,DIGEST);
  assert.equal(result.inventory_sha256,digest);assert.equal(result.exited.processes.worker.observation,'absent');assert.equal(stops,1);
  assert.equal(agent.status().connected,false);assert.equal(agent.status().admission_held,true);assert.equal(timers.length,0);
  await assert.rejects(agent.execute('must not replay',100),e=>e.outcome==='rejected');
  await assert.rejects(hold.shutdown(state.pending.id));assert.throws(()=>hold.release());
  const unwanted=channel.connect();assert.equal(channel._conn,null);assert.equal(timers.length,0);unwanted.resolve(managed());await flush();assert.equal(agent.status().worker_ready,false);
  assert.equal(journal.read().pending.phase,'prepared'); // No state installation or commit is implied.
 }finally{agent.stop();fs.rmSync(dir,{recursive:true,force:true});}
});

test('shutdown refuses active resources changed inventory and unreadable process identity',async()=>{
 const os=require('node:os'),crypto=require('node:crypto'),{SelectionJournal}=require('../research/autonomous-root/service/worker-selection');
 for(const mode of ['transfer','helper','running','unknown','not-monitored','changed-inventory','denied','reused']){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'handoff-refuse-')),file=path.join(dir,'selection.json'),journal=new SelectionJournal(file);
  journal.initialize({implementation:'managed',manifest_sha256:DIGEST});let stops=0;
  const readProcessFile=p=>{if(p.endsWith('boot_id'))return BOOT;if(mode==='denied')throw Object.assign(Error('denied'),{code:'EACCES'});return '42 (worker) S '+Array(18).fill('0').join(' ')+' '+(mode==='reused'?'124':'123')+' 0';};
  const {agent,channels}=fixture({selectionFile:file,managedVersion:()=>DIGEST,readProcessFile});agent.start();const channel=channels[0],ready=channel.connect();
  try{
   ready.resolve(managed());await flush();const info=inventoried();
   if(mode==='transfer')info.resources.transfers.push({id:'a'.repeat(32),direction:'upload'});
   if(mode==='helper')info.resources.helpers.push('a'.repeat(32));
   if(['running','unknown','not-monitored'].includes(mode))info.resources.jobs.push({id:'active-job-identity',state:mode==='not-monitored'?'completed':mode,monitor_finished:mode==='unknown'});
   channel.operation=async()=>info;channel.shutdown=async()=>{stops++;throw Error('must not stop');};
   const hold=agent.holdAdmission(),inventory=await hold.snapshot(),digest=crypto.createHash('sha256').update(JSON.stringify(inventory)).digest('hex');
   const state=journal.begin(1,{implementation:'native-prototype',manifest_sha256:'c'.repeat(64)},digest);
   if(mode==='changed-inventory')info.resources.jobs.push({id:'completed-job-identity',state:'completed',monitor_finished:true});
   await assert.rejects(hold.shutdown(state.pending.id));assert.equal(stops,0);assert.equal(agent.status().admission_held,true);
   assert.equal(journal.read().pending.phase,'prepared');
  }finally{agent.stop();fs.rmSync(dir,{recursive:true,force:true});}
 }
});
