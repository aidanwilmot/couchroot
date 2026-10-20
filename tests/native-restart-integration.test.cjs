'use strict';
// Real native workers and journals in a disposable Linux container. Only SDK,
// systemd and firmware labels are substituted; no managed worker is available.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm'),{createRequire}=require('node:module'),{spawn}=require('node:child_process'),{once}=require('node:events');
const {RootAgentServer}=require('../agent/service/root-agent');
const {SelectionJournal}=require('../agent/service/worker-selection');
const {withRetirementState}=require('./retirement-test-state.cjs');
const {processIdentities}=require('../agent/service/worker-processes');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex'),pause=()=>new Promise(r=>setTimeout(r,20));
for(const mode of ['restart','guardian-loss','new-boot','journal-runtime','partial-runtime','initial-created'])test('native-only startup preserves jobs and recovery: '+mode,{
 skip:process.platform!=='linux'||process.env.COUCHROOT_REHEARSAL!=='1'||!process.env.NATIVE_WORKER,timeout:90000
},async()=>withRetirementState(async()=>{
 const root=fs.mkdtempSync(os.tmpdir()+'/native-restart-'),state='/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state',file=state+'/selection.json';
 fs.mkdirSync(state,{recursive:true,mode:0o700});
 const boot=fs.readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim(),manifest='b'.repeat(64),launcherSha=hash(fs.readFileSync('/bin/true')),workerSha=hash(fs.readFileSync(process.env.NATIVE_WORKER));
 const journal=new SelectionJournal(file);journal.initialize({implementation:'managed',manifest_sha256:'a'.repeat(64)});
 const id=journal.begin(1,{implementation:'native-prototype',manifest_sha256:manifest},manifest).pending.id;
 const directory='/opt/couchroot-worker-'+id,scope=directory+'/state',tokenDir=state+'/production-ABC123',unit='couchroot-worker-'+id+'.service';
 const children=[],servers=[],fences=[];let unitChild=null,inject=['journal-runtime','partial-runtime','initial-created'].includes(mode);
 const put=(p,b,mode=0o600)=>fs.writeFileSync(p,b,{mode});
 for(const d of [directory,directory+'/code',scope])fs.mkdirSync(d,{mode:0o700});
 fs.copyFileSync(process.env.NATIVE_WORKER,directory+'/code/worker');fs.chmodSync(directory+'/code/worker',0o500);
 fs.copyFileSync('/bin/true',scope+'/launcher');fs.chmodSync(scope+'/launcher',0o400);
 function start(command,args,extra={}){const child=spawn(command,args,{env:{...process.env,...extra},stdio:['ignore','ignore','pipe']}),ended=once(child,'exit');let err='';child.stderr.on('data',v=>err+=v);const r={child,ended,err:()=>err};children.push(r);return r;}
 const until=async(fn,ms=10000)=>{const end=Date.now()+ms;while(!await fn()){if(Date.now()>end)throw Error('native fixture deadline: '+children.map(c=>c.err()).join('\n'));await pause();}};
 const systemctl=root+'/systemctl';
 function syncUnit(){const exited=!unitChild||unitChild.child.exitCode!==null||unitChild.child.signalCode!==null;
  const values={Id:unit,LoadState:unitChild?'loaded':'not-found',ActiveState:unitChild?'active':'inactive',SubState:exited?'exited':'running',MainPID:exited?0:unitChild.child.pid,ExecMainCode:exited?1:0,ExecMainStatus:exited&&unitChild?unitChild.child.exitCode||1:0,ExecMainStartTimestampMonotonic:unitChild?'123':'0',ControlGroup:''};
  for(const [k,v] of Object.entries(values))put(root+'/'+k,String(v));
 }
 put(systemctl,`#!/bin/sh
set -eu
action=$1; shift
props=''
while test "$#" -gt 1; do
 case "$1" in -p) shift; props="$props $1";; --property=*) props=$(printf %s "\${1#--property=}" | tr ',' ' ');; --no-block) :;; *) exit 2;; esac
 shift
done
test "$action" = show
for key in $props; do printf '%s=%s\\n' "$key" "$(cat '${root}/'$key)"; done
`,0o700);
 class HostServer extends RootAgentServer {
  constructor(options){super({...options,onConnect:peer=>{peer.identity.smack='System';options.onConnect(peer);}});servers.push(this);}
  async execute(command,timeout){syncUnit();
   if(command.includes('NATIVE-RESTART-SUBMITTED')){
    const a=JSON.parse(fs.readFileSync(state+'/'+id+'.startup.json'));fences.push(a.fence);
    const fenced=await super.execute(require('../agent/service/launch-fence').fenceCommand(a,'printf FENCED\\n',{kind:'startup'}),5000);assert.equal(fenced.exit_code,0,fenced.stderr);
    fs.copyFileSync(a.token_file,scope+'/token');fs.chmodSync(scope+'/token',0o600);
    const env=inject?{COUCHROOT_NATIVE_STARTUP_FAULT:mode}:{};inject=false;
    unitChild=start(directory+'/code/worker',['127.0.0.1',String(a.port),scope+'/token',scope,scope+'/launcher',launcherSha,'--production'],env);
    return {exit_code:0,timed_out:false,stdout:'NATIVE-RESTART-SUBMITTED\n',stderr:''};
   }
   return super.execute(command.replaceAll('systemctl ',systemctl+' '),timeout);
  }
 }
 async function connect(scope,flag,command=process.env.NATIVE_WORKER){
  const secret=crypto.randomBytes(32);put(scope+'/token',secret.toString('base64'));
  if(!fs.existsSync(scope+'/launcher')){fs.copyFileSync('/bin/true',scope+'/launcher');fs.chmodSync(scope+'/launcher',0o400);}
  let accept;const ready=new Promise(r=>accept=r),server=new HostServer({secret,onConnect:accept});await new Promise(r=>server.start(r));
  const worker=start(command,['127.0.0.1',String(server.listeningPort()),scope+'/token',scope,scope+'/launcher',launcherSha,flag]);
  await Promise.race([ready,worker.ended.then(()=>{throw Error(worker.err());})]);return {server,worker};
 }
 try{
  const original=await connect(scope,'--production',directory+'/code/worker');unitChild=original.worker;
  const info=await original.server.operation({op:'status'}),source={boot_id:boot,worker_id:'d'.repeat(32),processes:{worker:{pid:2147483646,start_ticks:'100'},guardian:null}};
  put(scope+'/.jobs/.import-manifest','{}');
  const installation={schema:1,phase:'ready',id,directory,scope,manifest_sha256:manifest,source,installed_manifest_sha256:hash('{}')};
  const record={schema:1,id,phase:'ready',device:'qn90a',manifest_sha256:manifest,state_receipt_sha256:hash(JSON.stringify(installation)),worker_sha256:workerSha,launcher_sha256:launcherSha,source,boot_id:boot,unit,directory,scope,port:original.server.listeningPort(),token_file:tokenDir+'/token',token_sha256:hash('old'),worker_identity:processIdentities(info,original.server._conn.identity.pid),unit_started_monotonic:'123'};
  const activation={schema:1,id,phase:'active',boot_id:boot,manifest_sha256:manifest,readiness_sha256:hash(JSON.stringify(record)),retirement_sha256:manifest,worker_identity:record.worker_identity};
  put(state+'/'+id+'.retained-snapshot.json',JSON.stringify({source,records:[]}));
  for(const [suffix,value] of [['production',record],['activation',activation],['state-install',installation]])put(state+'/'+id+'.'+suffix+'.json',JSON.stringify(value));
  journal.advance(2,id,'state-ready',record.state_receipt_sha256);journal.advance(3,id,'trial-ready',activation.readiness_sha256);journal.commit(4,id);
  await original.server.operation({op:'job.start',id:'native-keep-00001',profile:'root',timeout_ms:1000,command:'exit 9'});
  await until(async()=>(await original.server.operation({op:'status'})).resources.jobs.every(j=>j.monitor_finished));
  const saved=fs.readFileSync(scope+'/.jobs/native-keep-00001.json');
  if(mode==='guardian-loss'){
   await original.server.operation({op:'job.start',id:'native-live-00001',profile:'root',timeout_ms:30000,command:'printf x >> '+root+'/effect; sleep 25'});
   await until(()=>fs.existsSync(root+'/effect'));
   original.worker.child.kill('SIGKILL');
  }else original.server.close();
  await original.worker.ended;await pause();
  if(mode==='new-boot')require('./native-reboot-state.cjs').historicalBoot(state,id);
  const committed=fs.readFileSync(state+'/'+id+'.production.json'),active=fs.readFileSync(state+'/'+id+'.activation.json'),selection=fs.readFileSync(file);
  const bootstrap=root+'/bootstrap';fs.mkdirSync(bootstrap,{mode:0o700});const held=await connect(bootstrap,'--held-bootstrap');
  const sourceFile=path.resolve(__dirname,'../agent/service/native-startup.js'),real=createRequire(sourceFile),module={exports:{}};
  vm.runInNewContext(fs.readFileSync(sourceFile,'utf8'),{module,process,Buffer,setTimeout,clearTimeout,require:n=>n==='./root-agent'?{RootAgentServer:HostServer}:real(n)});
  const options={selectionFile:file,executor:{implementation:'native-bootstrap',launcherSha256:launcherSha,pid:held.server._conn.identity.pid,status:()=>held.server.operation({op:'status'}),execute:(c,t)=>held.server.execute(c,t)}};
  if(inject){await assert.rejects(module.exports.startSelectedNative(options));await unitChild.ended;assert.equal(unitChild.child.exitCode,86,unitChild.err());}
  const result=await module.exports.startSelectedNative(options).catch(e=>{for(let c=e;c;c=c.cause)console.error(c.stack);throw e;});
  assert.equal((await result.channel.execute('printf restarted',1000)).stdout,'restarted');
  assert.equal((await result.channel.operation({op:'job.status',id:'native-keep-00001'})).record.exit_code,9);
  assert.deepEqual(fs.readFileSync(scope+'/.jobs/native-keep-00001.json'),saved);
  assert.deepEqual(fs.readFileSync(file),selection);assert.deepEqual(fs.readFileSync(state+'/'+id+'.production.json'),committed);assert.deepEqual(fs.readFileSync(state+'/'+id+'.activation.json'),active);
  if(mode==='guardian-loss'){assert.equal(fs.readFileSync(root+'/effect','utf8'),'x');assert.equal((await result.channel.operation({op:'job.status',id:'native-live-00001'})).record.state,'interrupted');}
  result.channel.close();
 }finally{
  for(const s of servers)s.close();
  for(const c of children)if(c.child.exitCode===null&&c.child.signalCode===null){c.child.kill('SIGTERM');await c.ended;}
  for(const d of new Set(fences))fs.rmSync(d,{recursive:true,force:true});fs.rmSync(directory,{recursive:true,force:true});fs.rmSync(root,{recursive:true,force:true});
 }
}));
