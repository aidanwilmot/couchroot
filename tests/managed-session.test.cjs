const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm'),crypto=require('node:crypto'),{EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const {SelectionJournal}=require('../agent/service/worker-selection');
const file=path.resolve(__dirname,'../agent/service/managed-session.js'),real=createRequire(file),hash=s=>crypto.createHash('sha256').update(s).digest('hex'),sha='b'.repeat(64);
async function fixture(mode,run){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'managed-session-')),selectionFile=directory+'/selection.json',journal=new SelectionJournal(selectionFile);journal.initialize({implementation:'managed',manifest_sha256:'a'.repeat(64)});let transition=journal.begin(1,{implementation:'native-prototype',manifest_sha256:sha},'c'.repeat(64)),id=transition.pending.id;
 if(mode==='return'){journal.advance(2,id,'state-ready',sha);journal.advance(3,id,'trial-ready',sha);journal.commit(4,id);transition=journal.begin(5,{implementation:'managed',manifest_sha256:'a'.repeat(64)},'c'.repeat(64));id=transition.pending.id;journal.advance(6,id,'state-ready','d'.repeat(64));}
 else{journal.advance(2,id,'rollback-required','c'.repeat(64));journal.advance(3,id,'rollback-state-ready','d'.repeat(64));}
 fs.writeFileSync(directory+'/'+id+'.managed-restore-input.json',JSON.stringify({record:{source:{worker_id:'2'.repeat(32)}}}),{mode:0o600});

 let instance,launches=0,readiness=0,launchOptions,closed=0;const identity={worker_id:'e'.repeat(32)};
 class Server{
  constructor(options){this.options=options;this._server=new EventEmitter();instance=this;}
  start(callback){if(mode==='listen-error')queueMicrotask(()=>this._server.emit('error',Error('bind failed')));else callback();}
  listeningPort(){return 12345;}
  connect(){this._conn={_socket:{destroy(){}}};this.options.onConnect(this._conn);}
  close(){closed++;this._conn=null;}
  async operation(request){assert.equal(request.op,'status');return {...(mode==='adoption-drift'?{worker_id:'f'.repeat(32)}:identity),app_launcher:{sha256:mode==='launcher-drift'?'f'.repeat(64):sha}};}
 }
 let record;
 const provider={identity:{worker_id:'1'.repeat(32)},launchManaged:async options=>{
  launches++;launchOptions=options;assert.equal(instance.options.bindHost,'127.0.0.1');assert.equal(options.port,12345);
  const token=fs.readFileSync(options.tokenFile);assert.equal(token.length,44);assert.equal(hash(token),options.tokenSha256);assert.equal(Buffer.from(token.toString(),'base64').equals(instance.options.secret),true);assert.equal(fs.statSync(options.tokenFile).mode&0o777,0o600);assert.equal(fs.statSync(path.dirname(options.tokenFile)).mode&0o777,0o700);
  fs.writeFileSync(directory+'/managed-launch.pending',id+'\n',{mode:0o600});
  if(mode==='launch-hangs')return new Promise(()=>{});
  if(mode==='launch-error')throw Error('unknown launch');
  record={id,phase:'submitted',port:options.port,token_file:options.tokenFile,token_sha256:options.tokenSha256,state_receipt_sha256:'d'.repeat(64),manifest_sha256:'a'.repeat(64)};
  if(mode!=='no-connect')instance.connect();if(mode==='disconnect')instance._conn=null;return record;
 },verifyManaged:async options=>{
  if(mode==='ready-hangs')return new Promise(()=>{});
  readiness++;assert.equal(options.channel,instance);if(mode==='ready-error')throw Error('readiness mismatch');
  const ready={...record,phase:'ready',worker_identity:identity,unit_started_monotonic:'123',launcher_sha256:sha},digest=hash(JSON.stringify(ready));fs.writeFileSync(directory+'/'+id+'.managed-launch.json',JSON.stringify(ready),{mode:0o600});
  return {record:ready,readiness_sha256:digest};
 }};
 const module={exports:{}};vm.runInNewContext(fs.readFileSync(file,'utf8'),{module,process,Buffer,setTimeout:(fn,ms)=>setTimeout(fn,['no-connect','launch-hangs','ready-hangs'].includes(mode)?20:ms),clearTimeout,require:name=>name==='./root-agent'?{RootAgentServer:Server}:name==='./managed-readiness'?{managedIdentity:info=>({worker_id:info.worker_id})}:real(name)});
 const open=()=>module.exports.openManagedSession({journalDirectory:directory,selectionFile,id,provider});
 try{await run({open,directory,id,journal,state:()=>({instance,launches,readiness,launchOptions,closed})});}finally{fs.rmSync(directory,{recursive:true,force:true});}
}
test('session binds launch and readiness and exposes no channel before committed adoption',()=>fixture('ok',async f=>{
 const session=await f.open();assert.equal(session.record.phase,'ready');assert.equal(session.channel,undefined);assert.equal(f.state().readiness,1);assert.equal(f.journal.read().selected.implementation,'managed');
 f.journal.commitRollback(f.journal.read().revision,f.id,session.readiness_sha256);const channel=await session.takeChannel();assert.equal(channel,f.state().instance);await assert.rejects(session.takeChannel());assert.equal(f.state().closed,0);
 session.closeTransport();session.closeTransport();assert.equal(f.state().closed,1);assert.equal(fs.existsSync(f.state().launchOptions.tokenFile),true);
 await assert.rejects(f.open(),/reconciliation/);assert.equal(f.state().launches,1);
}));
test('precommit or changed-identity adoption closes transport and retains evidence',async()=>{
 for(const mode of ['precommit','adoption-drift','launcher-drift'])await fixture(mode,async f=>{const session=await f.open();if(mode!=='precommit')f.journal.commitRollback(f.journal.read().revision,f.id,session.readiness_sha256);await assert.rejects(session.takeChannel(),e=>e.outcome==='unknown');assert.equal(f.state().closed,1);assert.equal(fs.existsSync(f.state().launchOptions.tokenFile),true);await assert.rejects(session.takeChannel());});
});
test('unknown launch and failed readiness keep token and launch ownership',async()=>{
 for(const mode of ['launch-error','disconnect','ready-error','no-connect','launch-hangs','ready-hangs'])await fixture(mode,async f=>{await assert.rejects(f.open(),e=>e.outcome==='unknown');assert.equal(f.state().closed,1);assert.equal(fs.existsSync(f.state().launchOptions.tokenFile),true);await assert.rejects(f.open(),/reconciliation/);assert.equal(f.state().launches,1);});
});
test('listener failure removes unused private material without starting a worker',()=>fixture('listen-error',async f=>{
 await assert.rejects(f.open(),e=>e.outcome==='rejected');assert.equal(f.state().launches,0);assert.deepEqual(fs.readdirSync(f.directory).sort(),[f.id+'.managed-restore-input.json','selection.json'].sort());
}));
test('existing pending launch or wrong transition refuses listener allocation',async()=>{
 for(const mode of ['pending','selection'])await fixture('ok',async f=>{
  if(mode==='pending')fs.writeFileSync(f.directory+'/managed-launch.pending','old');else f.journal.commitRollback(f.journal.read().revision,f.id,'f'.repeat(64));
  await assert.rejects(f.open());assert.equal(f.state().instance,undefined);assert.equal(f.state().launches,0);
 });
});
test('disconnect after readiness closes transport without pretending process cleanup',()=>fixture('ok',async f=>{
 const session=await f.open();f.state().instance.options.onClose(Error('disconnected'));assert.equal(f.state().closed,1);await assert.rejects(session.takeChannel());assert.equal(fs.existsSync(f.directory+'/managed-launch.pending'),true);assert.equal(f.journal.read().pending.phase,'rollback-state-ready');
}));
test('return from committed native selection advances a managed trial and requires that exact commit',()=>fixture('return',async f=>{
 const session=await f.open();assert.equal(f.journal.read().pending.phase,'trial-ready');assert.equal(f.journal.read().selected.implementation,'native-prototype');
 f.journal.commit(f.journal.read().revision,f.id);assert.equal(await session.takeChannel(),f.state().instance);session.closeTransport();
}));
test('changed token, restoration input and committed quiescence refuse channel adoption',async()=>{
 for(const mode of ['token','input','quiescence'])await fixture('ok',async f=>{
  const session=await f.open();f.journal.commitRollback(f.journal.read().revision,f.id,session.readiness_sha256);
  if(mode==='token')fs.writeFileSync(f.state().launchOptions.tokenFile,'changed');
  if(mode==='input')fs.writeFileSync(f.directory+'/'+f.id+'.managed-restore-input.json','{}');
  if(mode==='quiescence'){const s=f.journal.read();s.history[s.history.length-1].quiescence_sha256='f'.repeat(64);fs.writeFileSync(f.directory+'/selection.json',JSON.stringify(s));}
  await assert.rejects(session.takeChannel(),e=>e.outcome==='unknown');assert.equal(f.state().closed,1);
 });
});
