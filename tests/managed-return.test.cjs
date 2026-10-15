'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm'),{createRequire}=require('node:module');
const {SelectionJournal}=require('../research/autonomous-root/service/worker-selection'),{hash}=require('../research/autonomous-root/service/policy'),{planInstallation}=require('../research/autonomous-root/service/retained-install');
const file=path.resolve(__dirname,'../research/autonomous-root/service/managed-return.js'),real=createRequire(file),managed='a'.repeat(64),native='b'.repeat(64),boot='00000000-0000-0000-0000-000000000001';
async function fixture(failure,run){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'managed-return-')),selectionFile=dir+'/selection.json',journal=new SelectionJournal(selectionFile),events=[];let closes=0,controller;
 journal.initialize({implementation:'managed',manifest_sha256:managed});const id=journal.begin(1,{implementation:'native-prototype',manifest_sha256:native},'c'.repeat(64)).pending.id;
 const source={boot_id:boot,worker_id:'d'.repeat(32),processes:{worker:{pid:42,start_ticks:'100'},guardian:null}},body={schema:1,implementation:'managed',source,records:[]},baseline={...body,sha256:hash(JSON.stringify(body))};
 const installation={...planInstallation({snapshot:baseline,id,manifestSha256:native}).record,phase:'ready',quiescence_sha256:'c'.repeat(64)},state=hash(JSON.stringify(installation));
 const identity={boot_id:boot,worker_id:'e'.repeat(32),processes:{worker:{pid:87,start_ticks:'300'},guardian:{pid:86,start_ticks:'299'}}};
 const record={schema:1,id,phase:'ready',device:'s90d',manifest_sha256:native,state_receipt_sha256:state,worker_sha256:native,launcher_sha256:native,source,boot_id:boot,unit:'couchroot-worker-'+id+'.service',directory:'/opt/couchroot-worker-'+id,scope:'/opt/couchroot-worker-'+id+'/state',port:12345,token_file:'/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state/production-ABC123/token',token_sha256:native,worker_identity:identity,unit_started_monotonic:'123'};
 journal.advance(2,id,'state-ready',state);journal.advance(3,id,'trial-ready',hash(JSON.stringify(record)));journal.commit(4,id);
 for(const [name,value] of [[id+'.production.json',record],[id+'.state-install.json',installation],[id+'.retained-snapshot.json',baseline]])fs.writeFileSync(dir+'/'+name,JSON.stringify(value),{mode:0o600});
 const step=name=>{events.push(name);if(failure===name)throw Error('injected '+name);};
 const hold={snapshotNative:async()=>{step('drain');if(failure==='drift')fs.writeFileSync(dir+'/'+id+'.production.json','{}');return {...identity,resources:{jobs:[],helpers:[],transfers:failure==='resources'?[{}]:[]}};},shutdownNative:async tx=>{step('stop');return {phase:'stopped',id:tx,origin_id:id,inventory_sha256:journal.read().pending.quiescence_sha256};},adoptManaged:async session=>{step('adopt');assert.equal(journal.read().selected.implementation,'managed');assert.equal(session.readiness_sha256,'f'.repeat(64));},completeManaged:async(r,o={})=>{if(!o.resume)step('activate');else events.push('resume');return {transaction_id:journal.read().history.at(-1).id,admission_held:false};}};
 const provider={snapshotNativeJobs:async inputs=>{step('snapshot');assert.equal(inputs.record.id,id);assert.equal(inputs.baseline.sha256,baseline.sha256);},restoreManagedState:async()=>{step('restore');return {phase:'restored',id,transition_id:journal.read().pending.id,receipt_sha256:'9'.repeat(64)};},acceptManagedRestore:async()=>{step('accept');const s=journal.read();return journal.advance(s.revision,s.pending.id,'state-ready','9'.repeat(64));},launchManaged:async()=>{},verifyManaged:async()=>{}};
 const module={exports:{}};vm.runInNewContext(fs.readFileSync(file,'utf8'),{module,process,require:n=>n==='./worker-selection'?{...real(n),managedVersion:()=>managed}:n==='./managed-session'?{openManagedSession:async o=>{step('session');assert.equal(o.provider,provider);assert.equal(o.runtimeSha256,'8'.repeat(64));assert.equal(o.managedSha256,managed);const s=journal.read();journal.advance(s.revision,s.pending.id,'trial-ready','f'.repeat(64));if(failure==='close')controller.closeTransport();return {readiness_sha256:'f'.repeat(64),closeTransport:()=>closes++};}}:real(n)});
 controller=module.exports.createManagedReturn({hold,retirement:{provider},record,payload:'/fixture/payload',selectionFile,runtimeSha256:'8'.repeat(64)});
 try{await run({controller,events,journal,dir,record,closes:()=>closes});}finally{fs.rmSync(dir,{recursive:true,force:true});}
}
test('managed return orders stopped native state restoration, managed session, commit and activation',()=>fixture(null,async f=>{
 const result=await f.controller.run();assert.equal(result.selected_implementation,'managed');assert.equal(result.native_origin_id,f.record.id);assert.equal(result.admission_held,false);assert.deepEqual(f.events,['drain','stop','snapshot','restore','accept','session','adopt','activate']);assert.equal(f.journal.read().pending,null);assert.equal(f.journal.read().history.length,2);assert.equal(f.controller.status().phase,'active');await assert.rejects(f.controller.run());
}));
test('every return failure retains hold and refuses implicit replay',async()=>{
 for(const failure of ['drain','resources','drift','stop','snapshot','restore','accept','session','adopt','activate'])await fixture(failure,async f=>{
  await assert.rejects(f.controller.run(),e=>e.outcome==='unknown');assert.equal(f.controller.status().phase,'reconciliation-required');assert.equal(f.closes(),0);const count=f.events.length;await assert.rejects(f.controller.run());assert.equal(f.events.length,count);
  if(failure!=='activate'){await assert.rejects(f.controller.resumeActivation());assert.equal(f.events.length,count);}else{const result=await f.controller.resumeActivation();assert.equal(result.admission_held,false);assert.deepEqual(f.events.slice(count),['resume']);}
 });
});
test('existing managed ownership refuses return before native shutdown',()=>fixture(null,async f=>{
 fs.writeFileSync(f.dir+'/managed-launch.pending','owned',{mode:0o600});await assert.rejects(f.controller.run());assert.deepEqual(f.events,[]);assert.equal(f.journal.read().pending,null);
}));
test('closing while managed listener resolves prevents commit and retains transition',()=>fixture('close',async f=>{
 await assert.rejects(f.controller.run());assert.equal(f.journal.read().pending.phase,'trial-ready');assert.equal(f.events.includes('adopt'),false);assert.equal(f.closes(),1);
}));
