'use strict';
// Real coordinator, selection, importer, launch, readiness and session code.
// Only the TV transport/provider/process observations are simulated here.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const {SelectionJournal}=require('../agent/service/worker-selection');
const {hash,atomic}=require('../agent/service/policy');
const boot='00000000-0000-0000-0000-000000000001',sha='b'.repeat(64),nextSha='c'.repeat(64);
function identity(worker,guardian,mark){return {boot_id:boot,worker_id:mark.repeat(32),processes:{worker:{pid:worker,start_ticks:String(worker*100)},guardian:guardian?{pid:guardian,start_ticks:String(guardian*100)}:null}};}
function info(i,launcher=sha){return {...i,implementation:'native-prototype',uptime_seconds:1,lifetime_mode:'production',lifetime_seconds:0,guardian_pid:i.processes.guardian.pid,app_launcher:{sha256:launcher,independently_staged:true},resources:{schema:1,scope:'worker-owned',jobs:[],transfers:[],helpers:[]},capabilities:['worker-process-identity-v1','guardian-parent-identity-v1','resource-inventory-v1','prototype-production-files-v1','binary-upload-v1','binary-download-v1','prototype-app-exec-v1','prototype-jobs-v1','prototype-helper-lifecycle-v1','prototype-independent-launcher-v1','prototype-crash-guardian-v1','prototype-command-fault-diagnostics-v1']};}
async function fixture(run,{device='s90d',fail=null,count=2}={}){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'native-upgrade-')),selectionFile=dir+'/selection.json',journal=new SelectionJournal(selectionFile);
 const source=identity(42,null,'a'),oldIdentity=identity(87,86,'b'),newIdentity=identity(97,96,'c'),providerIdentity=identity(77,76,'d');
 journal.initialize({implementation:'managed',manifest_sha256:'a'.repeat(64)});
 const id=journal.begin(1,{implementation:'native-prototype',manifest_sha256:sha},sha).pending.id;
 const installation={schema:1,id,phase:'ready',directory:'/opt/couchroot-worker-'+id,scope:'/opt/couchroot-worker-'+id+'/state',manifest_sha256:sha,source,installed_manifest_sha256:sha};
 const record={schema:1,id,phase:'ready',device,manifest_sha256:sha,state_receipt_sha256:hash(JSON.stringify(installation)),worker_sha256:sha,launcher_sha256:sha,source,boot_id:boot,unit:'couchroot-worker-'+id+'.service',directory:installation.directory,scope:installation.scope,port:12345,token_file:'/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state/production-OLD123/token',token_sha256:sha,worker_identity:oldIdentity,unit_started_monotonic:'123'};
 const activation={schema:1,id,phase:'active',boot_id:boot,manifest_sha256:sha,readiness_sha256:hash(JSON.stringify(record)),retirement_sha256:sha,worker_identity:oldIdentity};
 atomic(dir+'/'+id+'.production.json',record);atomic(dir+'/'+id+'.activation.json',activation);atomic(dir+'/'+id+'.state-install.json',installation);
 journal.advance(2,id,'state-ready',record.state_receipt_sha256);journal.advance(3,id,'trial-ready',activation.readiness_sha256);journal.commit(4,id);
 const records=Array.from({length:count},(_,n)=>{const name='retained-job-'+String(n).padStart(4,'0'),bytes=Buffer.from(JSON.stringify({id:name,boot_id:boot,state:'completed',exit_code:n}));return {name:name+'.json',size:bytes.length,sha256:hash(bytes),base64:bytes.toString('base64')};});
 const body={schema:1,implementation:'native-prototype',source:oldIdentity,origin:{transaction_id:id,manifest_sha256:sha,installation_sha256:record.state_receipt_sha256},records};
 const snapshot={...body,sha256:hash(JSON.stringify(body))};
 const candidate={manifest_sha256:nextSha,artifacts:{'native-worker':{sha256:nextSha},'native-app-launcher':{sha256:sha}}};
 let observedBoot=boot, channelCount=0;
 let channel,stopped=0,adopted=null,released=0,retired=0,launches=0,phase=null;
 const commands=[],phases=[],tokenRoot='/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state/';
 const map=p=>typeof p==='string'&&p.startsWith(tokenRoot)?dir+'/tokens/'+p.slice(tokenRoot.length):p;
 const proxy={...fs};
 for(const name of ['mkdirSync','openSync','readFileSync','writeFileSync','unlinkSync','lstatSync','statSync','existsSync'])proxy[name]=(p,...args)=>fs[name](map(p),...args);
 proxy.rmdirSync=p=>fs.rmdirSync(typeof p==='string'&&p.startsWith(tokenRoot)?dir+'/tokens/'+path.basename(p):p);
 proxy.chmodSync=(p,mode)=>fs.chmodSync(p.startsWith(tokenRoot)?dir+'/tokens/'+path.basename(p):p,mode);
 proxy.mkdtempSync=prefix=>{fs.mkdirSync(dir+'/tokens',{recursive:true,mode:0o700});const real=fs.mkdtempSync(dir+'/tokens/production-');return tokenRoot+path.basename(real);};
 class Channel {
  constructor(options){channelCount++;this.identity=identity(87+channelCount*10,86+channelCount*10,channelCount===1?'c':'e');this.options=options;this._server=new EventEmitter();this._conn=null;channel=this;}
  start(yes){yes();}listeningPort(){return 12345;}
  connect(){this._conn={identity:{uid:0,euid:0,gid:0,egid:0,pid:this.identity.processes.worker.pid,smack:'System'}};this.options.onConnect(this._conn);}
  async operation(v){if(v.op==='status'){const value=info({...this.identity,boot_id:observedBoot});value.capabilities.push('startup-token-binding-v1');const intent=fs.readdirSync(dir).find(n=>n.endsWith('.startup.json'));if(intent)value.startup_token_sha256=JSON.parse(fs.readFileSync(dir+'/'+intent)).token_sha256;return value;}const entry=records.find(r=>r.name===v.id+'.json'),record=JSON.parse(Buffer.from(entry.base64,'base64'));return {...record,record,output_available:false};}
  close(){this._conn=null;}
 }
 const execute=async command=>{
  commands.push(command);
  let stdout;
  if(command.includes('vconftool get db/sdk/develop/ip'))stdout='db/sdk/develop/ip, value = 127.0.0.1 (String)\n';
  else if(command.includes('UPGRADE-FENCED'))stdout='UPGRADE-FENCED\n';
  else if(command.includes('RESTART-ROLLBACK-OBSERVED')){const unit=command.match(/couchroot-worker-[a-f0-9]{32}\.service/)[0];stdout=`Unit=${unit}\nLoadState=loaded\nActiveState=active\nSubState=exited\nMainPID=0\nControlGroup=\nProcs=absent\nRESTART-ROLLBACK-OBSERVED\n`;}
  else if(command.includes('NATIVE-RESTART-SUBMITTED')){launches++;channel.connect();stdout='NATIVE-RESTART-SUBMITTED\n';}
  else if(command.includes('NATIVE-RESTART-VERIFIED'))stdout='NATIVE-RESTART-VERIFIED\n';
  else if(command.includes('UPGRADE-SOURCE-VERIFIED'))stdout='UPGRADE-SOURCE-VERIFIED\n';
  else if(command.includes('PRODUCTION-SUBMITTED')){launches++;channel.connect();stdout='STATE-READY\nPRODUCTION-SUBMITTED\n';}
  else if(command.includes('--property=Id,')){const target=command.match(/couchroot-worker-([a-f0-9]{32})\.service/)[1];stdout=`Id=couchroot-worker-${target}.service\nLoadState=loaded\nActiveState=active\nSubState=running\nMainPID=${channel.identity.processes.guardian.pid}\nExecMainCode=0\nExecMainStatus=0\nExecMainStartTimestampMonotonic=456\n`;}
  else if(command.includes('PRODUCTION-VERIFIED'))stdout='PRODUCTION-VERIFIED\n';
  else if(command.includes('STATE-RECORD'))stdout='STATE-RECORD\n';
  else if(command.includes('STATE-READY'))stdout='STATE-READY\n';
  else if(command.includes('STATE-PENDING'))stdout='STATE-PENDING\n';
  else if(command.includes('LC_ALL=C') && command.includes('listing=$(find'))stdout=records.map(r=>r.name).sort().join('\n')+'\n';
  else throw Error('Unexpected command');
  if(fail===phase+'-reply')throw Error('Lost reply at '+phase);
  return {exit_code:0,timed_out:false,stderr:'',stdout};
 };
 const cache=new Map(),base=path.resolve(__dirname,'../agent/service');
 const mocks={
  './native-candidate':{loadCandidate:()=>candidate},
  './native-upgrade-provider':{openUpgradeProvider:async()=>({record:{worker_identity:providerIdentity},channel:{close(){}},execute,retire:async()=>{retired++;if(fail==='retire')throw Error('Retirement lost reply');}})},
  './production-exit':{prepareProductionExit:async()=>({waitForExit:async()=>{if(fail==='exit')throw Error('Exit unconfirmed');}})},
  './native-retained-state':{snapshotNativeJobs:async()=>snapshot,snapshotNativeRestartJobs:async()=>({snapshot,metadata:[],reconciliation_required:false,checkpoint_files:[]})},
  './root-agent':{RootAgentServer:Channel},
 };
 function load(file){file=path.resolve(base,file);if(!file.endsWith('.js'))file+='.js';if(cache.has(file))return cache.get(file).exports;const module={exports:{}};cache.set(file,module);
 vm.runInNewContext(fs.readFileSync(file,'utf8'),{module,exports:module.exports,process,Buffer,setTimeout,clearTimeout,console,__dirname:path.dirname(file),require:name=>{
  if(name==='fs')return proxy;
  if(mocks[name])return mocks[name];
  if(name==='./policy')return {...load('policy'),atomic:(p,value)=>{if(p.endsWith('.upgrade.json')){phase=value.phase;phases.push(phase);if(fail===phase+'-before')throw Error('Before publication');}atomic(p,value);if(p.endsWith('.upgrade.json')&&fail===phase+'-after')throw Error('After publication');}};
  if(name.startsWith('.'))return load(path.resolve(path.dirname(file),name));return require(name);
 }},{filename:file});return module.exports;}
 const api=load('native-upgrade'),startup=load('native-startup'),recovery=load('native-upgrade-recovery');
 const recover=async(newBoot=boot)=>{
  observedBoot=newBoot;fail=null;
  const executor={implementation:'native-bootstrap',launcherSha256:sha,pid:77,
    status:async()=>({...providerIdentity,boot_id:newBoot,implementation:'native-bootstrap',guardian_pid:76,uptime_seconds:1,lifetime_mode:'held-bootstrap',lifetime_seconds:300,
      app_launcher:{sha256:sha,independently_staged:true},resources:{schema:1,scope:'worker-owned',jobs:[],transfers:[],helpers:[]},
      capabilities:['held-bootstrap-v1','resource-inventory-v1','worker-process-identity-v1','guardian-parent-identity-v1']}),execute};
  return recovery.recoverUpgrade({selectionFile,executor});
 };
 const options={selectionFile,payload:'/opt/usr/apps/MiniRoot01/res/wgt/payload',device,hold:{pid:87,check(){},status:async()=>info(oldIdentity),execute,shutdown:async()=>{stopped++;return {acknowledged:true,disconnected:true};},release:()=>released++,adopt:async result=>{adopted=result;}}};
 try{await run({dir,id,record,activation,installation,journal,api,startup,recovery,options,records,candidate,commands,phases,recover,state:()=>({stopped,adopted,released,retired,launches})});}
 finally{fs.rmSync(dir,{recursive:true,force:true});}
}
module.exports={fixture,info,identity,boot,sha,nextSha};
