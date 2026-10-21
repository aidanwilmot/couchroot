'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {fixture,nextSha}=require('./native-upgrade-fixture.cjs');
const {hash}=require('../agent/service/policy');
for(const device of ['qn90a','s90d'])test(device+' upgrades through real selection, importer, launch, readiness and committed startup',()=>fixture(async f=>{
 const before=fs.readFileSync(f.options.selectionFile),review=f.api.reviewUpgrade(f.options);
 assert.deepEqual(fs.readFileSync(f.options.selectionFile),before);
 const result=await f.api.runUpgrade({...f.options,reviewSha256:review.sha256});
 assert.equal(result.worker_sha256,nextSha);assert.equal(result.phase,'committed');
 assert.equal(f.state().stopped,1);assert.equal(f.state().launches,1);assert.equal(f.state().retired,1);
 const current=f.startup.startupCandidate(f.options.selectionFile);assert.equal(current.record.schema,2);assert.equal(current.record.worker_sha256,nextSha);
 assert.equal(f.journal.read().pending,null);assert.equal(f.api.upgradeStatus(f.options.selectionFile),null);
 assert.equal(fs.readFileSync(f.dir+'/'+f.id+'.production.json','utf8'),JSON.stringify(f.record));
 assert.equal(fs.readFileSync(f.dir+'/'+f.id+'.activation.json','utf8'),JSON.stringify(f.activation));
 const retained=JSON.parse(fs.readFileSync(f.dir+'/'+result.transaction_id+'.retained-snapshot.json'));
 assert.deepEqual(retained.records,f.records);assert.equal(retained.implementation,'native-prototype');
 const rollback=f.api.reviewUpgrade({...f.options,target:'previous'});assert.equal(rollback.to.worker_sha256,f.record.worker_sha256);
 assert.equal(rollback.target,'previous');assert.notEqual(rollback.sha256,review.sha256);
 assert.ok(f.commands.some(c=>c.includes('sha256sum')&&c.includes('/code/worker')));
 assert.ok(f.commands.some(c=>c.includes('/proc/97/exe -ef')));
 assert.ok(f.commands.some(c=>c.includes('couchroot-startup-fence-')));
}, {device,count:64}));
test('stale review, active resources and wrong identity never shut down or launch',async()=>{
 for(const mode of ['review','resources','identity'])await fixture(async f=>{
 const review=f.api.reviewUpgrade(f.options),original=f.options.hold.status;
 f.options.hold.status=async()=>{const s=await original();if(mode==='resources')s.resources.transfers=['a'.repeat(32)];if(mode==='identity')s.worker_id='f'.repeat(32);return s;};
 await assert.rejects(f.api.runUpgrade({...f.options,reviewSha256:mode==='review'?'0'.repeat(64):review.sha256}));
 assert.equal(f.state().stopped,0);assert.equal(f.state().launches,0);assert.equal(f.journal.read().pending,null);
 });
});
for(const fail of ['provider-submitted-after','source-stop-submitted-before','exit','state-submitted-after','state-submitted-reply','candidate-submitted-reply','candidate-ready-after','retire','commit-submitted-before','commit-submitted-after'])
 test('interruption at '+fail+' retains old receipts and blocks implicit replay',()=>fixture(async f=>{
 const review=f.api.reviewUpgrade(f.options);
 await assert.rejects(f.api.runUpgrade({...f.options,reviewSha256:review.sha256}));
 assert.ok(f.api.upgradeStatus(f.options.selectionFile));assert.ok(f.journal.read().pending);
 assert.equal(f.journal.read().selected.manifest_sha256,f.record.manifest_sha256);
 assert.equal(hash(fs.readFileSync(f.dir+'/'+f.id+'.production.json')),hash(JSON.stringify(f.record)));
 const count=f.commands.length;await assert.rejects(f.api.runUpgrade({...f.options,reviewSha256:review.sha256}));assert.equal(f.commands.length,count);
 const plan=f.recovery.recoveryPlan(f.options.selectionFile);assert.equal(plan.candidate.record.id,f.id);assert.equal(plan.committed,false);
 },{fail}));
test('recovery refuses altered immutable source and changed selection rather than repairing them',()=>fixture(async f=>{
 const review=f.api.reviewUpgrade(f.options);await assert.rejects(f.api.runUpgrade({...f.options,reviewSha256:review.sha256}));
 const file=f.dir+'/'+f.id+'.production.json';fs.writeFileSync(file,JSON.stringify({...f.record,worker_sha256:'0'.repeat(64)}));
 assert.throws(()=>f.recovery.recoveryPlan(f.options.selectionFile));
},{fail:'exit'}));

for(const newBoot of [undefined,'00000000-0000-0000-0000-000000000002'])
test('explicit recovery restarts the unchanged old runtime '+(newBoot?'after reboot':'on the same boot'),()=>fixture(async f=>{
 const review=f.api.reviewUpgrade(f.options);
 await assert.rejects(f.api.runUpgrade({...f.options,reviewSha256:review.sha256}));
 const result=await f.recover(newBoot);
 assert.equal(result.record.id,f.id);assert.equal(result.record.worker_sha256,f.record.worker_sha256);
 assert.ok(f.journal.read().pending); // Caller must retire its bootstrap first.
 result.finish();
 assert.equal(f.journal.read().pending,null);
 assert.equal(f.journal.read().history.at(-1).outcome,'rolled-back');
 const selected=f.startup.startupCandidate(f.options.selectionFile);
 assert.equal(selected.record.worker_sha256,f.record.worker_sha256);
 assert.equal(selected.record.boot_id,newBoot||f.record.boot_id);
 assert.equal(f.api.upgradeStatus(f.options.selectionFile),null);
 assert.equal(fs.readFileSync(f.dir+'/'+f.id+'.production.json','utf8'),JSON.stringify(f.record));
},{fail:'candidate-submitted-reply'}));

test('interruption after selection commits recovers the committed candidate, not the old worker',()=>fixture(async f=>{
 const review=f.api.reviewUpgrade(f.options);
 await assert.rejects(f.api.runUpgrade({...f.options,reviewSha256:review.sha256}));
 assert.equal(f.journal.read().pending,null);
 assert.equal(f.journal.read().selected.manifest_sha256,nextSha);
 assert.equal(f.recovery.recoveryPlan(f.options.selectionFile).committed,true);
 const result=await f.recover();result.finish();
 assert.equal(f.startup.startupCandidate(f.options.selectionFile).record.worker_sha256,nextSha);
 assert.equal(f.api.upgradeStatus(f.options.selectionFile),null);
},{fail:'committed-before'}));
