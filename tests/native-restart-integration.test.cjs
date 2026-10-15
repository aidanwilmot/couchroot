'use strict';
// Run separately in an otherwise idle disposable container, like the rehearsal
// fixture: it owns the real managed job directory. A service restart is modelled
// by closing every listener of the first agent and starting a second agent with
// fresh module instances; TV signing, systemd and SDK acquisition are fixtures.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto'),{spawn}=require('node:child_process'),{once}=require('node:events'),{createRequire}=require('node:module');
const {RootAgentServer}=require('../research/autonomous-root/service/vendor/root-agent');
const {withRetirementState}=require('./retirement-test-state.cjs');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),pause=()=>new Promise(r=>setTimeout(r,20));
const MUTATION=/(^|[\s;|&(])(rm|rmdir|mv|mkdir|cp|ln|chmod|chown|kill|pkill|touch|truncate|dd|systemd-run|sqlite3)\s|systemctl (stop|start|kill|restart)|>(?!\s*&)\s*\/|set -C/m;
for(const mode of ['abandon-prepared','provider-ready','state-ready','trial-ready'])test('service restart reconciles an interrupted forward trial ('+mode+')',{
 skip:process.platform!=='linux'||process.env.COUCHROOT_REHEARSAL!=='1'||!process.env.NATIVE_WORKER||!process.env.MANAGED_PARITY,timeout:90000
},async()=>withRetirementState(async()=>{
 assert(!fs.existsSync('/opt/couchroot-agent'),'Run in a separate fresh container');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-restart-')),state='/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state',selectionFile=state+'/selection.json';fs.mkdirSync(state,{recursive:true,mode:0o700});
 const managed='a'.repeat(64),native='b'.repeat(64),boot=fs.readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim(),launcherSha=sha(fs.readFileSync('/bin/true')),workerSha=sha(fs.readFileSync(process.env.NATIVE_WORKER)),runtimeSha=sha(fs.readFileSync('/opt/dotnet/bin/dotnet'));
 const children=[],servers=[],roots=['/opt/couchroot-agent'],units=new Map(),commands=new Map();let first,second;
 const unitRoot=root+'/units';fs.mkdirSync(unitRoot);
 // Unknown units report systemd's not-found defaults; the fixture has no cgroups.
 const systemctl=root+'/systemctl';fs.writeFileSync(systemctl,`#!/bin/sh
set -eu
base='${unitRoot}'
action=$1; shift
props=''
while test "$#" -gt 1; do
 case "$1" in -p) shift; props="$props $1";; --property=*) props=$(printf %s "\${1#--property=}" | tr ',' ' ');; --no-block) :;; *) exit 2;; esac
 shift
done
unit=$1; dir="$base/$unit"
if test "$action" = stop || test "$action" = reset-failed; then
 test "$(cat "$dir/MainPID")" = 0
 touch "$dir/stopped"
 printf not-found > "$dir/LoadState"; printf inactive > "$dir/ActiveState"; printf dead > "$dir/SubState"
 for key in MainPID ExecMainCode ExecMainStatus ExecMainStartTimestampMonotonic; do printf 0 > "$dir/$key"; done
 exit 0
fi
test "$action" = show
for key in $props; do
 if test -d "$dir"; then value=$(cat "$dir/$key"); else case "$key" in LoadState) value=not-found;; ActiveState) value=inactive;; SubState) value=dead;; Id) value=$unit;; ControlGroup) value=;; *) value=0;; esac; fi
 printf '%s=%s\\n' "$key" "$value"
done
`,{mode:0o700});
 function syncUnits(){for(const [unit,v] of units){const d=unitRoot+'/'+unit;if(!fs.existsSync(d))fs.mkdirSync(d);if(fs.existsSync(d+'/stopped'))continue;const exited=v.child.exitCode!==null||v.child.signalCode!==null;
  const values={Id:unit,LoadState:'loaded',ActiveState:'active',SubState:exited?'exited':'running',MainPID:exited?0:v.child.pid,ExecMainCode:exited?1:0,ExecMainStatus:exited?v.child.exitCode===0?0:1:0,ExecMainStartTimestampMonotonic:'123',ControlGroup:''};for(const [k,value] of Object.entries(values))fs.writeFileSync(d+'/'+k,String(value));}}
 class HostServer extends RootAgentServer{
  constructor(options){super({...options,onConnect:peer=>{const executable=fs.readlinkSync('/proc/'+peer.identity.pid+'/exe'),launched=children.find(v=>v.child.pid===peer.identity.pid||v.command===executable);assert(launched);peer.identity.smack=launched.command==='dotnet'?'User':'System';options.onConnect(peer);}});servers.push(this);commands.set(this,[]);}
  async execute(command,timeout){
   syncUnits();commands.get(this).push(command);
   if(command.includes('FALLBACK-RUNTIME-VERIFIED'))command=command.replaceAll('/usr/bin/dotnet','/opt/dotnet/bin/dotnet');
   if(command.includes('MANAGED-VERIFIED')){
    // As in the rehearsal fixture: substitute only the TV runtime/mount gate.
    const names=fs.readdirSync(state).filter(n=>n.endsWith('.managed-launch.json'));assert.equal(names.length,1);const r=JSON.parse(fs.readFileSync(state+'/'+names[0]));
    const inputs=JSON.parse(fs.readFileSync(state+'/'+r.id+'.managed-restore-input.json'));command=require('../research/autonomous-root/service/managed-restore-plan').planManagedRestore(inputs).verify+'printf "MANAGED-VERIFIED\\n"\n';
   }
   return super.execute(command.replaceAll('systemctl ',systemctl+' '),timeout);
  }
 }
 function start(command,args,unit){const child=spawn(command,args,{stdio:['ignore','ignore','pipe']}),ended=once(child,'exit');let stderr='';child.stderr.on('data',v=>{stderr=(stderr+v).slice(-16384);});const v={child,ended,command,stderr:()=>stderr};children.push(v);if(unit)units.set(unit,v);return v;}
 function write(name,value){fs.writeFileSync(state+'/'+name,typeof value==='string'?value:JSON.stringify(value),{mode:0o600});}
 function nativeStage(id,kind,options){
  const directory='/opt/couchroot-'+kind+'-'+id,scope=directory+'/state';if(kind==='retirement'){assert(!fs.existsSync(directory));roots.push(directory);fs.mkdirSync(directory,{mode:0o700});fs.mkdirSync(scope,{mode:0o700});}else roots.push(directory);
  fs.mkdirSync(directory+'/code',{mode:0o700});fs.copyFileSync(process.env.NATIVE_WORKER,directory+'/code/worker');fs.chmodSync(directory+'/code/worker',0o500);fs.copyFileSync('/bin/true',scope+'/launcher');fs.chmodSync(scope+'/launcher',0o400);fs.copyFileSync(options.tokenFile,scope+'/token');fs.chmodSync(scope+'/token',0o600);
  return {directory,scope};
 }
 const launchers={
  'retirement-launch':{submitRetirement:async o=>{const {directory,scope}=nativeStage(o.id,'retirement',o),unit='couchroot-retirement-'+o.id+'.service',r={schema:1,id:o.id,phase:'submitted',device:o.device,manifest_sha256:o.manifestSha256,worker_sha256:workerSha,launcher_sha256:launcherSha,observer_sha256:native,boot_id:boot,source:o.source,unit,directory,scope,token_file:o.tokenFile,token_sha256:o.tokenSha256,port:o.port};write('retirement-launch.pending',o.id+'\n');write(o.id+'.retirement.json',r);start(directory+'/code/worker',['127.0.0.1',String(o.port),scope+'/token',scope,scope+'/launcher',launcherSha],unit);return r;}},
  'managed-launch':{submitManaged:async o=>{const inputs=JSON.parse(fs.readFileSync(state+'/'+o.transitionId+'.managed-restore-input.json')),id=o.transitionId,directory='/opt/couchroot-managed-'+id,stage='/opt/usr/home/owner/share/tmp/sdk_tools/managed-'+id,unit='couchroot-managed-'+id+'.service';for(const p of [directory,stage]){assert(!fs.existsSync(p));roots.push(p);fs.mkdirSync(p,{recursive:true,mode:0o700});}fs.copyFileSync(o.tokenFile,stage+'/token');fs.chmodSync(stage+'/token',0o600);
   const r={schema:1,id,phase:'submitted',implementation:'managed',manifest_sha256:o.managedSha256,runtime_sha256:o.runtimeSha256,state_receipt_sha256:o.receiptSha256,origin_id:inputs.record.id,source:inputs.record.worker_identity,boot_id:boot,unit,directory,stage,files:{'SamsungTvRootAgent.dll':managed,'SamsungTvRootAgent.runtimeconfig.json':managed,'SamsungTvRootAgent.deps.json':managed},port:o.port,token_file:o.tokenFile,token_sha256:o.tokenSha256};write('managed-launch.pending',id+'\n');write(id+'.managed-launch.json',r);start('dotnet',[process.env.MANAGED_PARITY,'--parity-wire',String(o.port),stage],unit);return r;}},
  'production-launch':{submitProduction:async o=>{const installation=JSON.parse(fs.readFileSync(state+'/'+o.id+'.state-install.json')),{directory,scope}=nativeStage(o.id,'worker',o),unit='couchroot-worker-'+o.id+'.service',r={schema:1,id:o.id,phase:'submitted',device:o.device,manifest_sha256:o.manifestSha256,state_receipt_sha256:o.receiptSha256,worker_sha256:workerSha,launcher_sha256:launcherSha,source:installation.source,boot_id:boot,unit,directory,scope,token_file:o.tokenFile,token_sha256:o.tokenSha256,port:o.port};write('production-launch.pending',o.id+'\n');write(o.id+'.production.json',r);start(directory+'/code/worker',['127.0.0.1',String(o.port),scope+'/token',scope,scope+'/launcher',launcherSha,'--production'],unit);return r;}}
 };
 const base=path.resolve(__dirname,'../research/autonomous-root/service');
 // Each agent gets its own module instances, as a restarted service process would.
 function loader(modules,inject){
  return function load(name){if(modules.has(name))return modules.get(name).exports;if(launchers[name])return launchers[name];if(name==='vendor/root-agent')return {RootAgentServer:HostServer};if(name==='vendor/sdb')return {connect:()=>new Promise(()=>{}),close:()=>{}};
   if(name==='worker-selection')return {...require(base+'/'+name),managedVersion:()=>managed};if(name==='native-candidate')return {candidateStatus:()=>({state:'verified'}),loadCandidate:()=>({manifest_sha256:native})};
   const file=base+'/'+name+'.js',real=createRequire(file),module={exports:{}};modules.set(name,module);vm.runInNewContext(fs.readFileSync(file,'utf8'),{module,exports:module.exports,__dirname:path.dirname(file),__filename:file,process,Buffer,URL,setTimeout,clearTimeout,setInterval,clearInterval,setImmediate,clearImmediate,require:n=>n.startsWith('./')&&fs.existsSync(path.resolve(path.dirname(file),n)+'.js')?load(path.relative(base,path.resolve(path.dirname(file),n))):real(n)});
   if(inject)inject(name,module);return module.exports;
  };
 }
 const until=async(predicate,ms=5000)=>{const end=Date.now()+ms;while(!await predicate()){if(Date.now()>end)throw Error('Restart rehearsal deadline '+children.map(c=>c.stderr()).join('\n'));await pause();}};
 const createAgent=load=>load('agent').createAgent({device:'qn90a',hashes:{'/usr/bin/dotnet':runtimeSha}},{selectionFile,verifyFirmware:()=>{},managedVersion:()=>managed,restartRollbackRetryMs:200});
 // Acquisition: the fixture starts the managed parity worker against the agent's listener.
 async function acquire(agent){const before=servers.length;agent.start();await until(()=>servers.length>before&&servers[servers.length-1].listeningPort());const server=servers[servers.length-1];fs.writeFileSync(root+'/token',server.secret.toString('base64'),{mode:0o600});return {server,worker:start('dotnet',[process.env.MANAGED_PARITY,'--parity-wire',String(server.listeningPort()),root])};}
 const injected=Error('injected service restart');
 try{
  first=createAgent(loader(new Map(),(name,module)=>{
   if(name==='production-session'&&['state-ready','trial-ready'].includes(mode)){const open=module.exports.openProductionSession;module.exports.openProductionSession=async options=>{if(mode==='state-ready')throw injected;await open(options);throw injected;};}
  }));
  const source=await acquire(first);await until(()=>first.status().worker_ready);
  await first.operation({op:'job.start',id:'retained-keep-0001',profile:'root',timeout_ms:1000,command:'exit 7'});await until(async()=>(await first.operation({op:'status'})).resources.jobs.every(j=>j.monitor_finished));
  const saved=fs.readFileSync('/opt/couchroot-agent/jobs/retained-keep-0001.json');
  const originalHold=first.holdAdmission;first.holdAdmission=()=>{const hold=originalHold();
   if(mode==='abandon-prepared')hold.prepareNative=async()=>{throw injected;};
   if(mode==='provider-ready'){const prepare=hold.prepareNative;hold.prepareNative=async id=>{await prepare(id);throw injected;};}
   return hold;};
  await assert.rejects(first.rehearseNative(native,runtimeSha),e=>{for(let c=e;c;c=c.cause)if(c===injected)return true;return false;});
  const pending=load=>load('worker-selection').selectionStatus(selectionFile).pending;
  const id=pending(loader(new Map()))&&pending(loader(new Map())).id;assert(id);
  assert.equal(pending(loader(new Map())).phase,{'abandon-prepared':'prepared','provider-ready':'prepared','state-ready':'state-ready','trial-ready':'trial-ready'}[mode]);
  // Restart: the old process and every listener it owned disappear.
  const old=children.slice();first.stop();for(const s of servers.slice())s.close();
  await until(()=>old.every(c=>c.child.exitCode!==null||c.child.signalCode!==null),10000);
  const listing=()=>fs.readdirSync(state).sort().map(n=>[n,fs.statSync(state+'/'+n).isFile()?fs.readFileSync(state+'/'+n,'utf8'):'dir']),before=new Map(listing());
  second=createAgent(loader(new Map()));const {server}=await acquire(second);
  if(mode==='abandon-prepared'){await until(()=>second.status().worker_ready,10000);assert.equal(second.restartInventory().startup_reconciliation.abandoned,true);}
  else{
   await until(()=>{const r=second.restartInventory().restart_rollback;return r&&r.phase==='complete';},15000);
   const r=second.restartInventory();assert.equal(r.restart_rollback.transaction_id,id);
   for(const c of commands.get(server))assert(!MUTATION.test(c),'held executor received a mutating command: '+c.slice(0,200));
   const receipt=JSON.parse(fs.readFileSync(state+'/'+id+'.restart-rollback.json'));assert.equal(receipt.outcome,'restart-rollback');
   // Ownership markers, records and staging remain for explicit cleanup and block another handoff.
   const after=new Map(listing());for(const [n,v] of before)if(n!=='selection.json')assert.equal(after.get(n),v,n);
   assert(r.markers.includes('retirement-launch.pending'));assert.equal(r.action,'pending-reconciliation');
   if(mode!=='provider-ready')assert(fs.existsSync('/opt/couchroot-worker-'+id+'/state/.jobs'));
  }
  await until(()=>second.status().worker_ready);
  const s=load=>load('worker-selection').selectionStatus(selectionFile),final=s(loader(new Map())),h=final.history[final.history.length-1];
  assert.equal(final.phase,'stable');assert.equal(final.selected_implementation,'managed');assert.equal(h.id,id);assert.equal(h.outcome,mode==='abandon-prepared'?'abandoned':'rolled-back');
  assert.equal(second.status().boot_id,boot);assert.equal((await second.execute('printf restored',1000)).stdout,'restored');
  assert.equal((await second.operation({op:'job.status',id:'retained-keep-0001'})).record.exit_code,7);assert.deepEqual(fs.readFileSync('/opt/couchroot-agent/jobs/retained-keep-0001.json'),saved);
  if(mode!=='abandon-prepared'){
   await assert.rejects(second.migrateNative(native,runtimeSha),e=>e.outcome==='rejected'&&/Existing native transition requires reconciliation/.test(e.cause&&e.cause.message));
   const obs=require('../research/autonomous-root/service/restart-inventory').providerId(id),cleaned=await second.cleanupRestart(id);
   assert.equal(cleaned.id,id);assert.equal(second.status().admission_held,false);
   for(const p of ['/opt/couchroot-worker-'+id,'/opt/couchroot-retirement-'+obs])assert(!fs.existsSync(p),p);
   for(const n of ['retirement-launch.pending','state-install.pending','production-launch.pending'])assert(!fs.existsSync(state+'/'+n),n);
   assert(!fs.readdirSync(state).some(n=>/^(production|retirement)-[A-Za-z0-9]{6}$/.test(n)));assert(fs.existsSync(state+'/'+id+'.restart-cleanup.json'));
   {const r=second.restartInventory();assert.equal(r.action,'none',JSON.stringify(r));assert.equal(r.boundary,'settled');}
   assert.deepEqual(JSON.parse(JSON.stringify(await second.cleanupRestart(id))),{id,already_clean:true,receipt_sha256:cleaned.receipt_sha256});
  }
  // The restarted service can complete an ordinary round trip afterwards.
  const round=await second.rehearseNative(native,runtimeSha);assert.equal(round.selected_implementation,'managed');assert.equal(round.admission_held,false);
  {const r=second.restartInventory();assert.equal(r.action,'none',JSON.stringify(r));}
  assert.deepEqual(fs.readFileSync('/opt/couchroot-agent/jobs/retained-keep-0001.json'),saved);
  // A source never asked to stop ends with its transport; a stopped one exits cleanly.
  if(['state-ready','trial-ready'].includes(mode))assert.equal(source.worker.child.exitCode,0);else assert(source.worker.child.exitCode!==null||source.worker.child.signalCode!==null,'source still running');
 }finally{
  for(const agent of [first,second])if(agent)agent.stop();for(const s of servers)s.close();for(const c of children)if(c.child.exitCode===null&&c.child.signalCode===null){c.child.kill('SIGTERM');await c.ended;}for(const p of roots.reverse())fs.rmSync(p,{recursive:true,force:true});fs.rmSync(root,{recursive:true,force:true});
 }
}));
