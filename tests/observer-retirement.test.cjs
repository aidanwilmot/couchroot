const {test}=require('node:test'),assert=require('node:assert/strict');
const {createObserverRetirement,validateProvider}=require('../research/autonomous-root/service/observer-retirement');
const boot='00000000-0000-0000-0000-000000000001',sha='a'.repeat(64),unit='couchroot-observer-'+'b'.repeat(32)+'.service';
const bound={unit,bootId:boot,sha256:sha};
const source={boot_id:boot,worker_id:'c'.repeat(32),processes:{worker:{pid:42,start_ticks:'100'},guardian:null}};
function status(){return {implementation:'native-prototype',boot_id:boot,worker_id:'d'.repeat(32),lifetime_mode:'bounded',lifetime_seconds:300,guardian_pid:76,processes:{worker:{pid:77,start_ticks:'200'},guardian:{pid:76,start_ticks:'199'}},capabilities:['prototype-scoped-files-v1','worker-process-identity-v1','guardian-parent-identity-v1','resource-inventory-v1','prototype-independent-launcher-v1','prototype-crash-guardian-v1'],app_launcher:{sha256:sha,independently_staged:true},resources:{schema:1,scope:'worker-owned',jobs:[],transfers:[],helpers:[]}};}
function fixture(){
 let info=status(),calls=[];
 const peer={identity:{pid:77,uid:0,euid:0,gid:0,egid:0,smack:'System'}};
 const channel={_conn:peer,operation:async()=>structuredClone(info),execute:async(command,timeout)=>{
  calls.push({command,timeout});
  return {exit_code:0,stdout:command.includes('systemctl stop')?'OBSERVER-UNIT-RETIRED\n':`Id=${unit}\nLoadState=loaded\nActiveState=active\nSubState=exited\nMainPID=0\nExecMainCode=1\nExecMainStatus=0\nExecMainStartTimestampMonotonic=123\n`};
 }};
 return {channel,peer,calls,info,create:()=>createObserverRetirement({channel,source,bound,launcherSha256:sha})};
}
test('retirement uses a distinct native identity and exposes no general executor',async()=>{
 const f=fixture(),provider=await f.create();assert.equal(provider.execute,undefined);
 const got=await provider.inspectUnit(bound);assert.equal(got.main_pid,0);
 const done=await provider.retireUnit(bound);assert.equal(done.retired,true);assert.equal(f.calls.length,3);
 assert.match(f.calls[2].command,/systemctl stop --no-block/);
 await assert.rejects(provider.retireUnit(bound));assert.equal(f.calls.length,3);
});
test('retirement rejects source overlap, broad lifetime, active resources and wrong profile',async()=>{
 const mutations=[v=>v.worker_id=source.worker_id,v=>v.boot_id=boot.slice(0,-1)+'2',v=>v.lifetime_mode='production',v=>v.lifetime_seconds=0,v=>v.lifetime_seconds=301,v=>v.guardian_pid=42,v=>{v.processes.guardian.pid=42;v.guardian_pid=42;},v=>v.resources.jobs.push({id:'retained-job-identity',state:'completed',monitor_finished:true}),v=>v.capabilities.push('prototype-production-files-v1'),v=>v.app_launcher.sha256='b'.repeat(64),v=>v.app_launcher.independently_staged=false,v=>v.capabilities.pop()];
 for(const mutate of mutations){const f=fixture();mutate(f.info);await assert.rejects(f.create());assert.equal(f.calls.length,0);}
 const f=fixture();f.peer.identity.smack='User';await assert.rejects(f.create());
});
test('binding mismatches are rejected without issuing commands',async()=>{
 const f=fixture(),p=await f.create();
 for(const patch of [{unit:unit+'\n'},{sha256:'f'.repeat(64)},{bootId:boot.slice(0,-1)+'2'},{execute:()=>{}}])await assert.rejects(p.retireUnit({...bound,...patch}));
 assert.equal(f.calls.length,0);assert.equal((await p.inspectUnit(bound)).unit,unit);
});
test('connection replacement, status drift, and uncertain results poison the provider without retry',async()=>{
 for(const mode of ['replacement','before','after','lost']){
  const f=fixture(),p=await f.create();
  if(mode==='replacement')f.channel._conn={...f.peer};
  if(mode==='before')f.info.worker_id='e'.repeat(32);
  if(mode==='after'||mode==='lost'){const old=f.channel.execute;f.channel.execute=async(...args)=>{const r=await old(...args);if(mode==='lost')throw Error('reply lost');f.info.processes.worker.start_ticks='999';return r;};}
  await assert.rejects(p.retireUnit(bound));const count=f.calls.length;await assert.rejects(p.retireUnit(bound));await assert.rejects(p.inspectUnit(bound));assert.equal(f.calls.length,count);
 }
});
test('parallel requests cannot overlap retirement',async()=>{
 const f=fixture(),p=await f.create();let release;const old=f.channel.operation;
 f.channel.operation=()=>new Promise(resolve=>{release=()=>old().then(resolve);});
 const pending=p.inspectUnit(bound);await assert.rejects(p.retireUnit(bound));f.channel.operation=old;release();await pending;
 assert.equal(f.calls.length,1);
});
test('late readiness cannot issue a retirement command after its deadline',async()=>{
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{createRequire}=require('node:module');
 const file=path.resolve(__dirname,'../research/autonomous-root/service/observer-retirement.js'),module={exports:{}},real=createRequire(file);let now=0;
 vm.runInNewContext(fs.readFileSync(file,'utf8'),{module,require:real,process:{hrtime:()=>[Math.floor(now/1000),(now%1000)*1000000]}});
 const f=fixture(),p=await module.exports.createObserverRetirement({channel:f.channel,source,bound,launcherSha256:sha});
 f.channel.operation=async()=>{now=9000;return f.info;};
 await assert.rejects(p.retireUnit(bound));assert.equal(f.calls.length,0);await assert.rejects(p.retireUnit(bound));
});
test('provider can snapshot retained managed jobs after observer retirement without exposing execution',async()=>{
 const f=fixture(),p=await f.create();await p.retireUnit(bound);f.channel.execute=async command=>{f.calls.push({command});return {exit_code:0,stdout:'SNAPSHOT-END\n'};};
 const result=await p.snapshotManagedJobs();assert.equal(result.implementation,'managed');assert.equal(result.records.length,0);assert.equal(result.source.worker_id,source.worker_id);assert.equal(f.calls.length,4);
 assert.ok(f.calls.slice(2).every(c=>c.command.includes('/proc/42/stat')&&c.command.includes('/opt/couchroot-agent/jobs')));
 await assert.rejects(p.snapshotManagedJobs());assert.equal(f.calls.length,4);assert.equal(p.execute,undefined);
});
test('failed source-exit check cannot be retried or followed by mutation',async()=>{
 const f=fixture(),p=await f.create();let calls=0;f.channel.execute=async()=>{calls++;return {exit_code:1,stdout:''};};
 await assert.rejects(p.snapshotManagedJobs());await assert.rejects(p.snapshotManagedJobs());await assert.rejects(p.retireUnit(bound));assert.equal(calls,1);
});
