const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto'),{spawnSync}=require('node:child_process');
const {snapshotNativeJobs,planNativeSnapshot}=require('../research/autonomous-root/service/native-retained-state');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex'),sha='b'.repeat(64),boot='00000000-0000-0000-0000-000000000001';
const linux={skip:process.platform!=='linux'||!process.env.COUCHROOT_PARITY_CONTAINER||process.geteuid()!==0};
async function fixture(fn,count=2){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-retained-')),id='a'.repeat(32),source={boot_id:boot,worker_id:'c'.repeat(32),processes:{worker:{pid:42,start_ticks:'100'},guardian:null}},worker_identity={boot_id:boot,worker_id:'d'.repeat(32),processes:{worker:{pid:52,start_ticks:'200'},guardian:{pid:51,start_ticks:'199'}}};
 const manifest=Buffer.from('{"fixture":"original-import"}'),directory='/opt/couchroot-worker-'+id,scope=directory+'/state';
 const installation={schema:1,id,phase:'ready',source,snapshot_sha256:sha,manifest_sha256:sha,installed_manifest_sha256:hash(manifest),directory,scope,quiescence_sha256:sha};
 const record={schema:1,id,phase:'ready',device:'s90d',manifest_sha256:sha,state_receipt_sha256:hash(JSON.stringify(installation)),worker_sha256:sha,launcher_sha256:sha,source,boot_id:boot,unit:'couchroot-worker-'+id+'.service',directory,scope,port:12345,token_file:'/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state/production-ABC123/token',token_sha256:sha,worker_identity,unit_started_monotonic:'123'};
 const target=root+'/native',jobs=target+'/state/.jobs';fs.mkdirSync(jobs,{recursive:true,mode:0o700});fs.mkdirSync(root+'/proc',{mode:0o700});fs.writeFileSync(root+'/boot',boot+'\n');fs.writeFileSync(jobs+'/lock','',{mode:0o600});fs.writeFileSync(jobs+'/.import-manifest',manifest,{mode:0o600});
 const records=[];for(let i=0;i<count;i++){const name=('native-retained-'+String(i).padStart(4,'0')).padEnd(64,'x')+'.json',bytes=Buffer.from((i===1?'\uFEFF':'')+JSON.stringify({id:name.slice(0,-5),boot_id:boot,state:i?'unknown':'completed',pid:0,exit_code:i?null:7}));fs.writeFileSync(jobs+'/'+name,bytes,{mode:0o600});records.push({name,bytes});}
 const commands=[],execute=async command=>{commands.push(command);let mapped=command.replaceAll(directory,target).replaceAll('/proc/sys/kernel/random/boot_id',root+'/boot');for(const pid of [42,51,52])mapped=mapped.replaceAll('/proc/'+pid+'/stat',root+'/proc/'+pid+'/stat');const r=spawnSync('/bin/sh',[],{input:mapped,encoding:'utf8'});return {exit_code:r.status,stdout:r.stdout,stderr:r.stderr};};
 try{await fn({root,jobs,records,commands,options:{record,installation,execute},execute});}finally{fs.rmSync(root,{recursive:true,force:true});}
}
test('native snapshot preserves bytes and binds production identity and original installation',linux,()=>fixture(async f=>{
 const result=await snapshotNativeJobs(f.options);assert.equal(result.implementation,'native-prototype');assert.deepEqual(result.source,f.options.record.worker_identity);assert.equal(result.origin.installation_sha256,f.options.record.state_receipt_sha256);assert.equal(result.records.length,2);
 const {sha256,...value}=result;assert.equal(sha256,hash(JSON.stringify(value)));for(let i=0;i<2;i++){assert.deepEqual(Buffer.from(result.records[i].base64,'base64'),f.records[i].bytes);assert.deepEqual(fs.readFileSync(f.jobs+'/'+f.records[i].name),f.records[i].bytes);}
 for(const command of f.commands)assert.equal(spawnSync('/bin/sh',['-n'],{input:command}).status,0);
}));
test('empty and full native retention inventories remain exact',linux,async()=>{
 for(const count of [0,64])await fixture(async f=>{const result=await snapshotNativeJobs(f.options);assert.equal(result.records.length,count);assert.deepEqual(fs.readdirSync(f.jobs).sort(),['lock','.import-manifest',...f.records.map(r=>r.name)].sort());},count);
});
test('live worker or guardian and unresolved metadata refuse rollback snapshots',linux,async()=>{
 for(const mode of ['worker','guardian','old-source','journal','pending','intent','repair','next','link','manifest'])await fixture(async f=>{
  if(['worker','guardian','old-source'].includes(mode)){const pid=mode==='worker'?52:mode==='guardian'?51:42,ticks=mode==='worker'?'200':mode==='guardian'?'199':'100';fs.mkdirSync(f.root+'/proc/'+pid);fs.writeFileSync(f.root+'/proc/'+pid+'/stat',pid+' (worker) S '+Array(18).fill('0').join(' ')+' '+ticks+' 0\n');}
  else if(mode==='link'){fs.unlinkSync(f.jobs+'/'+f.records[0].name);fs.symlinkSync('/dev/null',f.jobs+'/'+f.records[0].name);}
  else if(mode==='manifest')fs.writeFileSync(f.jobs+'/.import-manifest','changed');
  else fs.writeFileSync(f.jobs+'/'+({journal:'guardian',pending:'.import-pending',intent:'.intent-unknown',repair:'.repair-unknown',next:'record.next'}[mode]),'unfinished',{mode:0o600});
  await assert.rejects(snapshotNativeJobs(f.options));
 });
});
test('inventory changes during reads are detected and forgotten jobs are not resurrected',linux,async()=>{
 await fixture(async f=>{let changed=false;await assert.rejects(snapshotNativeJobs({...f.options,execute:async command=>{const result=await f.execute(command);if(!changed&&command.includes('\nbase64 ')){changed=true;fs.unlinkSync(f.jobs+'/'+f.records[0].name);}return result;}}));});
 await fixture(async f=>{fs.unlinkSync(f.jobs+'/'+f.records[0].name);const result=await snapshotNativeJobs(f.options);assert.deepEqual(result.records.map(r=>r.name),[f.records[1].name]);});
});
test('wrong installation binding and metadata are refused',linux,()=>fixture(async f=>{
 await assert.rejects(snapshotNativeJobs({...f.options,installation:{...f.options.installation,installed_manifest_sha256:'f'.repeat(64)}}));assert.equal(f.commands.length,0);
 fs.chmodSync(f.jobs+'/lock',0o644);await assert.rejects(snapshotNativeJobs(f.options));
}));

const {planManagedRestore}=require('../research/autonomous-root/service/managed-restore-plan');
async function restoreFixture(f){
 const baselineBody={schema:1,implementation:'managed',source:f.options.record.source,records:f.records.map(r=>({name:r.name,size:r.bytes.length,sha256:hash(r.bytes),base64:r.bytes.toString('base64')}))};
 const baseline={...baselineBody,sha256:hash(JSON.stringify(baselineBody))};
 f.options.installation.snapshot_sha256=baseline.sha256;f.options.record.state_receipt_sha256=hash(JSON.stringify(f.options.installation));
 const snapshot=await snapshotNativeJobs(f.options);
 const parent=f.root+'/managed';fs.mkdirSync(parent,{mode:0o755});fs.mkdirSync(parent+'/jobs',{mode:0o700});
 for(const r of f.records)fs.writeFileSync(parent+'/jobs/'+r.name,r.bytes,{mode:0o600});
 const plan=planManagedRestore({...f.options,snapshot,baseline});
 const execute=c=>f.execute(c.replaceAll('/opt/couchroot-agent',parent));
 const run=async c=>{const r=await execute(c);assert.equal(r.exit_code,0,r.stderr);return r.stdout;};
 return {snapshot,baseline,parent,plan,execute,run};
}
test('managed rollback replaces inventory exactly and retains original bytes across cutover interruption',linux,()=>fixture(async f=>{
 // Forget one existing record and change the retained result under native.
 fs.unlinkSync(f.jobs+'/'+f.records[0].name);
 const changed=Buffer.from(f.records[1].bytes.toString().replace('unknown','interrupted'));fs.writeFileSync(f.jobs+'/'+f.records[1].name,changed);
 const r=await restoreFixture(f);await r.run(r.plan.begin);for(const c of r.plan.copies)await r.run(c);
 assert.equal(await r.run(r.plan.inspect),'RESTORE-STAGED\n');
 await r.run(r.plan.retire);assert.equal(fs.existsSync(r.parent+'/jobs'),false);
 // A restart can identify the exact two-rename window without replaying retire.
 assert.equal(await r.run(r.plan.inspect),'RESTORE-CUTOVER\n');await r.run(r.plan.publish);
 assert.equal(await r.run(r.plan.inspect),'RESTORE-READY\n');await r.run(r.plan.verify);
 assert.deepEqual(fs.readdirSync(r.parent+'/jobs'),[f.records[1].name]);assert.deepEqual(fs.readFileSync(r.parent+'/jobs/'+f.records[1].name),changed);
 const backup=r.parent+'/rollback-'+f.options.record.id+'/previous';for(const old of f.records)assert.deepEqual(fs.readFileSync(backup+'/'+old.name),old.bytes);
 assert.notEqual((await r.execute(r.plan.retire)).exit_code,0);assert.notEqual((await r.execute(r.plan.publish)).exit_code,0);
}));
test('managed restoration rejects drift, foreign staging and live native processes without replacing baseline',linux,async()=>{
 for(const mode of ['baseline','extra','symlink','worker'])await fixture(async f=>{
  const r=await restoreFixture(f);await r.run(r.plan.begin);for(const c of r.plan.copies)await r.run(c);
  const staged=r.parent+'/rollback-'+f.options.record.id+'/next';
  if(mode==='baseline')fs.writeFileSync(r.parent+'/jobs/'+f.records[0].name,'changed');
  if(mode==='extra')fs.writeFileSync(staged+'/extra','unexpected');
  if(mode==='symlink'){fs.unlinkSync(staged+'/'+f.records[0].name);fs.symlinkSync(r.parent+'/jobs/'+f.records[0].name,staged+'/'+f.records[0].name);}
  if(mode==='worker'){fs.mkdirSync(f.root+'/proc/52');fs.writeFileSync(f.root+'/proc/52/stat','52 (worker) S '+Array(18).fill('0').join(' ')+' 200 0\n');}
  assert.notEqual((await r.execute(r.plan.retire)).exit_code,0);assert(fs.existsSync(r.parent+'/jobs'));assert(!fs.existsSync(r.parent+'/rollback-'+f.options.record.id+'/previous'));
 });
});
test('managed restore supports empty and full inventories and rejects altered snapshot receipts',linux,async()=>{
 for(const count of [0,64])await fixture(async f=>{
  const r=await restoreFixture(f);assert.throws(()=>planManagedRestore({...f.options,snapshot:{...r.snapshot,sha256:'f'.repeat(64)},baseline:r.baseline}));
  if(count===0)fs.rmdirSync(r.parent+'/jobs');
  await r.run(r.plan.begin);for(const c of r.plan.copies)await r.run(c);await r.run(r.plan.retire);await r.run(r.plan.publish);await r.run(r.plan.verify);
  assert.equal(fs.readdirSync(r.parent+'/jobs').length,count);
 },count);
});

const {restoreManagedJobs}=require('../research/autonomous-root/service/managed-restore');
const {SelectionJournal,selectionStatus}=require('../research/autonomous-root/service/worker-selection');
async function durableRestoreFixture(f,committed=false){
 const r=await restoreFixture(f),journalDirectory=f.root+'/journal';fs.mkdirSync(journalDirectory,{mode:0o700});
 const selectionFile=journalDirectory+'/selection.json',j=new SelectionJournal(selectionFile);let s=j.initialize({implementation:'managed',manifest_sha256:'e'.repeat(64)});
 s=j.begin(s.revision,{implementation:'native-prototype',manifest_sha256:f.options.record.manifest_sha256},sha);
 s.pending.id=f.options.record.id;fs.writeFileSync(selectionFile,JSON.stringify(s));
 if(committed){s=j.advance(s.revision,s.pending.id,'state-ready',f.options.record.state_receipt_sha256);s=j.advance(s.revision,s.pending.id,'trial-ready',hash(JSON.stringify(f.options.record)));s=j.commit(s.revision,s.pending.id);s=j.begin(s.revision,{implementation:'managed',manifest_sha256:'e'.repeat(64)},sha);}
 else s=j.advance(s.revision,s.pending.id,'rollback-required',sha);
 for(const [suffix,value] of [['.production.json',f.options.record],['.state-install.json',f.options.installation],['.retained-snapshot.json',r.baseline]])fs.writeFileSync(journalDirectory+'/'+f.options.record.id+suffix,JSON.stringify(value),{mode:0o600});
 const options={...f.options,baseline:r.baseline,snapshot:r.snapshot,journalDirectory,selectionFile,execute:r.execute};
 return {...r,options,selection:s,marker:journalDirectory+'/managed-restore.pending'};
}
test('durable restore supports failed trial and committed native rollback without selecting or starting managed',linux,async()=>{
 for(const committed of [false,true])await fixture(async f=>{
  const r=await durableRestoreFixture(f,committed),before=selectionStatus(r.options.selectionFile),result=await restoreManagedJobs(r.options);
  assert.equal(result.phase,'restored');assert.equal(result.transition_id,r.selection.pending.id);assert.deepEqual(selectionStatus(r.options.selectionFile),before);assert(fs.existsSync(r.marker));
  assert.deepEqual(await restoreManagedJobs({...r.options,resume:true}),result);
  await assert.rejects(restoreManagedJobs(r.options));
 });
});
test('durable restore resumes lost replies without repeating completed directory moves',linux,async()=>{
 for(const boundary of ['begin','copy','retire','publish'])await fixture(async f=>{
  const r=await durableRestoreFixture(f),target=boundary==='copy'?r.plan.copies[0]:r.plan[boundary];let failed=false;
  await assert.rejects(restoreManagedJobs({...r.options,execute:async c=>{const result=await r.execute(c);if(!failed&&c===target){failed=true;throw Error('lost reply');}return result;}}),e=>e.outcome==='unknown');assert(failed);assert(fs.existsSync(r.marker));
  const replay=[];await restoreManagedJobs({...r.options,resume:true,execute:async c=>{replay.push(c);return r.execute(c);}});
  if(['begin','retire','publish'].includes(boundary))assert(!replay.includes(target));
  assert.equal(await r.run(r.plan.verify),'RESTORE-READY\n');
 });
});
test('durable restore refuses changed native state, local ownership and selection on resume',linux,async()=>{
 for(const mode of ['native','marker','selection','receipt'])await fixture(async f=>{
  const r=await durableRestoreFixture(f);let interrupted=false;
  await assert.rejects(restoreManagedJobs({...r.options,execute:async c=>{const result=await r.execute(c);if(c===r.plan.begin&&!interrupted){interrupted=true;throw Error('lost reply');}return result;}}));
  if(mode==='native')fs.unlinkSync(f.jobs+'/'+f.records[0].name);
  if(mode==='marker')fs.writeFileSync(r.marker,'f'.repeat(32)+'\n');
  if(mode==='selection'){const s=JSON.parse(fs.readFileSync(r.options.selectionFile));s.pending.quiescence_sha256='f'.repeat(64);fs.writeFileSync(r.options.selectionFile,JSON.stringify(s));}
  if(mode==='receipt')fs.writeFileSync(r.options.journalDirectory+'/'+f.options.record.id+'.production.json','{}');
  await assert.rejects(restoreManagedJobs({...r.options,resume:true}));
  assert(fs.existsSync(r.parent+'/jobs'));assert(!fs.existsSync(r.parent+'/rollback-'+f.options.record.id+'/previous'));
 });
});

const {acceptManagedRestore}=require('../research/autonomous-root/service/managed-restore');
async function restoredForAcceptance(f,committed=false){
 const r=await durableRestoreFixture(f,committed),receipt=await restoreManagedJobs(r.options);
 return {...r,receipt,accept:{transitionId:receipt.transition_id,receiptSha256:receipt.receipt_sha256,journalDirectory:r.options.journalDirectory,selectionFile:r.options.selectionFile,execute:r.execute}};
}
test('restore acceptance rechecks bytes and advances only the proper state gate, including repeat readback',linux,async()=>{
 for(const committed of [false,true])await fixture(async f=>{
  const r=await restoredForAcceptance(f,committed),before=selectionStatus(r.options.selectionFile),accepted=await acceptManagedRestore(r.accept);
  assert.equal(accepted.pending.phase,committed?'state-ready':'rollback-state-ready');assert.equal(accepted.pending.state_sha256,r.receipt.receipt_sha256);assert.equal(accepted.selected.implementation,before.selected_implementation);assert(fs.existsSync(r.marker));
  assert.deepEqual(await acceptManagedRestore(r.accept),accepted);
  fs.writeFileSync(r.parent+'/jobs/'+f.records[0].name,'changed');await assert.rejects(acceptManagedRestore(r.accept));
 });
});
test('restore acceptance rejects changed receipt, marker, source, backup and destination',linux,async()=>{
 for(const mode of ['receipt','digest','marker','source','backup','destination','extra','writer'])await fixture(async f=>{
  const r=await restoredForAcceptance(f),before=fs.readFileSync(r.options.selectionFile,'utf8');
  if(mode==='receipt')fs.writeFileSync(r.options.journalDirectory+'/'+r.receipt.transition_id+'.managed-restore.json','{}');
  if(mode==='digest')r.accept.receiptSha256='f'.repeat(64);
  if(mode==='marker')fs.unlinkSync(r.marker);
  if(mode==='source')fs.unlinkSync(f.jobs+'/'+f.records[0].name);
  if(mode==='backup')fs.writeFileSync(r.parent+'/rollback-'+f.options.record.id+'/previous/'+f.records[0].name,'changed');
  if(mode==='destination')fs.writeFileSync(r.parent+'/jobs/'+f.records[0].name,'changed');
  if(mode==='extra')fs.writeFileSync(r.parent+'/jobs/extra','changed');
  if(mode==='writer')fs.writeFileSync(r.options.selectionFile+'.writer','busy',{mode:0o600});
  await assert.rejects(acceptManagedRestore(r.accept));assert.equal(fs.readFileSync(r.options.selectionFile,'utf8'),before);
 });
});
test('restore acceptance catches mutation during asynchronous verification before advancing selection',linux,async()=>{
 for(const mode of ['selection','receipt','native'])await fixture(async f=>{
  const r=await restoredForAcceptance(f);let changed=false;
  await assert.rejects(acceptManagedRestore({...r.accept,execute:async c=>{const result=await r.execute(c);if(!changed&&c===r.plan.verify){changed=true;
   if(mode==='selection'){const s=JSON.parse(fs.readFileSync(r.options.selectionFile));s.pending.quiescence_sha256='f'.repeat(64);fs.writeFileSync(r.options.selectionFile,JSON.stringify(s));}
   if(mode==='receipt')fs.writeFileSync(r.options.journalDirectory+'/'+r.receipt.transition_id+'.managed-restore.json','{}');
   if(mode==='native')fs.unlinkSync(f.jobs+'/'+f.records[0].name);
  }return result;}}));assert(changed);assert.equal(selectionStatus(r.options.selectionFile).pending.phase,'rollback-required');
 });
});
