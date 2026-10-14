'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const sdb=require('./vendor/sdb'),{tarGz}=require('./vendor/tar'),{RootAgentServer}=require('./vendor/root-agent');
const {read,hash,verifyFirmware,sdkRuntimeGuard}=require('./policy');
const {candidateStatus}=require('./native-candidate');
const {validateReadiness,validateResourceInventory}=require('./worker-readiness');
const {selectionStatus,managedVersion}=require('./worker-selection');
const {processIdentities,observeProcesses,waitForProcessExit}=require('./worker-processes');
const {preparePidfdExit,probeExecutable}=require('./pidfd-observer');
const {stageObserver}=require('./observer-stage');
const {prepareRuntimeObserver,observerTransactionId}=require('./observer-runtime');
const BASE='/home/owner/share/tmp/sdk_tools';
const quote=s=>"'"+s.replace(/'/g,"'\\''")+"'";
function launchRequest(stage,gate){
 const script='mkdir '+quote(gate)+' 2>/dev/null && { . '+quote(stage+'/launch-sdk.sh')+'; }';
 const encoded=Buffer.from(script).toString('base64');
 const request='shell:0 appinstall tpk new2.tpk`printf${IFS}%s${IFS}'+encoded+'|base64${IFS}-d|bash`.tpk';
 if(Buffer.byteLength(request)>510)throw Error('SDK launch command exceeds safe transport limit');
 return request;
}
function createAgent(config,options={}){
 let running=false,connected=false,launching=false,timer=null,channel=null,client=null,stage=null,attempts=0,generation=0,lastError=null,identity=null,lastAcquired=null,workerReady=false,workerStatus=null,workerStatusAt=0;
 const firmware=options.verifyFirmware||verifyFirmware;
 const currentBoot=options.readBootId||(()=>read('/proc/sys/kernel/random/boot_id',128).toString().trim());
 const payload=options.payload||path.join(__dirname,'../payload');
 let nativeCandidate=candidateStatus(payload,config.device);
 let managedDigest=null,admissionHold=null;
 const inFlight=new Set();
 function selection(refresh=false){
  if(!options.selectionFile)return {phase:'legacy-managed',selected_implementation:'managed',launch_allowed:true};
  const state=selectionStatus(options.selectionFile);
  if(state.launch_allowed&&state.phase==='stable'){
   try{if(refresh||managedDigest===null)managedDigest=(options.managedVersion||managedVersion)(payload);if(state.selected_manifest_sha256!==managedDigest)throw Error('mismatch');}
   catch(_){return {...state,phase:'inspection-required',launch_allowed:false,reason:'managed-package-version-mismatch'};}
  }
  return state;
 }

 function diagnostics(){const out={};if(stage)for(const n of ['launcher.log','root-agent.status','root-agent.log']){try{out[n]=read(stage+'/'+n,65536).toString().slice(-2048);}catch(_){}}return out;}
 function status(){const selected=selection();let boot=null,uptime=null;try{boot=fs.readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim();uptime=Number(fs.readFileSync('/proc/uptime','utf8').split(' ')[0]);}catch(_){}if(workerStatus){boot=workerStatus.boot_id;uptime=workerStatus.uptime_seconds+process.uptime()-workerStatusAt;}return {schema:2,admission_held:admissionHold!==null,in_flight_requests:inFlight.size,selected_implementation:selected.selected_implementation||null,worker_selection:selected,native_candidate:nativeCandidate,boot_id:boot,uptime_seconds:uptime,worker_ready:workerReady&&selected.launch_allowed&&!admissionHold,worker_id:workerStatus&&workerStatus.worker_id,capabilities:workerStatus?workerStatus.capabilities:[],last_root_acquired_at:lastAcquired,device:config.device,enabled:running,connected,phase:!selected.launch_allowed?'selection-required':admissionHold?'draining':workerReady?'ready':connected?'checking':launching?'acquiring':running?'waiting':'disabled',attempts,last_error:lastError,identity,diagnostics:diagnostics()};}
 function clean(){
  if(!stage)return;
  // Do not remove other tools' staging directories or recursively delete unknown files.
  for(const n of fs.readdirSync(stage)){
   if(!/^(SamsungTv(RootAgent|ArchiveRoot)\.(dll|runtimeconfig\.json|deps\.json)|public\.pem|passwd|root-agent\.(token|log|status)|launcher\.log|launch-sdk\.sh)$/.test(n))continue;
   const p=path.join(stage,n);if(fs.lstatSync(p).isFile())fs.unlinkSync(p);
  }
  try{fs.rmdirSync(stage+'/launch-once');}catch(_){}
  const pkg=path.basename(stage);for(const suffix of ['.tar.gz','.tar.gz.signature']){const p=BASE+'/on-demand/'+pkg+suffix;if(fs.existsSync(p)&&fs.lstatSync(p).isFile())fs.unlinkSync(p);}
  try{fs.rmdirSync(stage);stage=null;}catch(_){}try{fs.rmdirSync(BASE+'/on-demand');}catch(_){}
 }
 function schedule(){if(!running||timer||connected||admissionHold)return;if(attempts>=8){lastError='Acquisition retry budget exhausted; use authenticated disable/enable after diagnosis';return;}timer=setTimeout(()=>{timer=null;launch();},Math.min(60000,5000*Math.pow(2,Math.max(0,attempts-1))));}
 function prepare(port,secret){
  firmware(config);
  const pkg='archive-root-'+crypto.randomBytes(8).toString('hex');stage=BASE+'/'+pkg;
  fs.mkdirSync(stage,{mode:0o755});
  const onDemand=BASE+'/on-demand';try{fs.mkdirSync(onDemand,{mode:0o755});}catch(e){if(e.code!=='EEXIST')throw e;const s=fs.lstatSync(onDemand);if(!s.isDirectory()||s.isSymbolicLink())throw Error('Unsafe staging directory');}
  const manifest=JSON.parse(read(payload+'/manifest.json'));
  for(const name of ['SamsungTvArchiveRoot','SamsungTvRootAgent'])for(const suffix of ['dll','runtimeconfig.json','deps.json']){
   const file=name+'.'+suffix,bytes=read(payload+'/'+file,4*1024*1024);if(hash(bytes)!==manifest[file])throw Error('Payload mismatch');fs.writeFileSync(stage+'/'+file,bytes,{mode:0o644,flag:'wx'});
  }
  const keys=crypto.generateKeyPairSync('rsa',{modulusLength:2048});
  fs.writeFileSync(stage+'/public.pem',keys.publicKey.export({type:'spki',format:'pem'}),{mode:0o644,flag:'wx'});
  const passwd=read('/etc/passwd').toString().split('\n');let changed=0;
  const view=passwd.map(line=>{const parts=line.split(':');if(parts[0]==='owner'){if(parts.length!==7||parts[2]!=='5001')throw Error('Unexpected owner identity');parts[2]='0';parts[3]='0';changed++;return parts.join(':');}return line;}).join('\n');
  if(changed!==1)throw Error('Missing owner identity');fs.writeFileSync(stage+'/passwd',view,{mode:0o644,flag:'wx'});
  fs.writeFileSync(stage+'/root-agent.token',secret.toString('base64')+'\n',{mode:0o600,flag:'wx'});
  const script='/usr/bin/dotnet '+stage+'/SamsungTvRootAgent.dll 127.0.0.1 '+port+' '+stage+'/root-agent.token '+stage+' </dev/null >'+stage+'/root-agent.log 2>&1 &\n';
  const archive=tarGz([{name:'launch.sh',data:script,mode:0o700}]);
  fs.writeFileSync(onDemand+'/'+pkg+'.tar.gz',archive,{mode:0o644,flag:'wx'});fs.writeFileSync(onDemand+'/'+pkg+'.tar.gz.signature',crypto.sign('RSA-SHA256',archive,keys.privateKey),{mode:0o644,flag:'wx'});
  return pkg;
 }
 async function launch(){
  if(!running||connected||launching||admissionHold)return;
  if(!selection(true).launch_allowed){running=false;lastError='Worker selection requires reconciliation';return;}
  launching=true;attempts++;const gen=++generation;let step='firmware verification';
  try{
   nativeCandidate=candidateStatus(payload,config.device);
   firmware(config);
   const secret=crypto.randomBytes(32);
   if(channel)channel.close();
   channel=new RootAgentServer({secret,onConnect:conn=>{if(!running||gen!==generation||(admissionHold&&admissionHold.stopping)){conn._socket.destroy();return;}connected=true;workerReady=false;identity=conn.identity;conn.operation({op:'status'}).then(info=>{if(!running||gen!==generation||!connected||channel._conn!==conn)return;validateReadiness(info,{implementation:'managed',bootId:currentBoot()});workerStatus=info;workerStatusAt=process.uptime();workerReady=true;lastAcquired=new Date().toISOString();}).catch(error=>{if(gen===generation&&connected&&channel._conn===conn){lastError=String(error.message);conn._socket.destroy();}});lastError=null;launching=false;if(timer){clearTimeout(timer);timer=null;}if(client){sdb.close(client);client=null;}},onClose:()=>{if(gen!==generation)return;connected=false;workerReady=false;identity=null;workerStatus=null;workerStatusAt=0;schedule();}});
   await new Promise((resolve,reject)=>{channel.start(resolve);channel._server.once('error',reject);});
   if(!running||gen!==generation)return;
   step='loopback connection';
   const opened=await sdb.connect({host:'127.0.0.1',port:26101,timeout:8000});
   if(!running||gen!==generation){sdb.close(opened);return;}
   client=opened;
   step='payload staging';clean();const pkg=prepare(channel.listeningPort(),secret);
   const command='/usr/bin/dotnet '+quote(stage+'/SamsungTvArchiveRoot.dll')+' '+quote(pkg);
   // SDK UID 901 cannot create a marker in the app-owned staging directory.
   const gate='/tmp/'+pkg+'-launch-once';
   fs.writeFileSync(stage+'/launch-sdk.sh','set -eu\n'+sdkRuntimeGuard(config)+command+'\n',{mode:0o644,flag:'wx'});
   step='SDK launcher';const output=await sdb.exec(client,launchRequest(stage,gate),{timeout:30000});
   if(!connected&&output)lastError='SDK launcher: '+output.slice(-300).replace(/[\r\n]+/g,' ');
   if(!connected&&running&&gen===generation)throw Error(lastError&&lastError.startsWith('SDK launcher:')?lastError:'Launcher returned without authenticated agent');
  }catch(e){if(running&&gen===generation&&!connected)lastError=(step+': '+String(e.message||e.code)).slice(0,300);}
  finally{if(gen===generation){launching=false;if(client){sdb.close(client);client=null;}if(!connected)schedule();}}
 }
 function start(){if(running)return;running=true;attempts=0;lastError=null;launch();}
 function stop(){admissionHold=null;running=false;connected=false;workerReady=false;identity=null;workerStatus=null;workerStatusAt=0;++generation;if(timer)clearTimeout(timer);timer=null;if(client)sdb.close(client);client=null;if(channel)channel.close();channel=null;launching=false;const stopped=generation;setTimeout(()=>{if(!running&&generation===stopped){try{clean();}catch(e){lastError='Staging cleanup incomplete';}}},1000);}
 function submit(call){
  if(admissionHold||!running||!connected||!workerReady||!channel||!selection().launch_allowed)return Promise.reject(Object.assign(Error('Root worker unavailable or admission held'),{outcome:'rejected'}));
  let request;try{request=Promise.resolve(call(channel));}catch(e){request=Promise.reject(e);}
  // Keep a result classification, not command output, for the handoff drain.
  // Transport errors without an explicit outcome are also uncertain.
  const settled=request.then(()=>true,e=>!!e&&['failed','rejected'].includes(e.outcome));
  inFlight.add(settled);settled.then(()=>inFlight.delete(settled));
  return request;
 }
 function holdAdmission(){
  const selected=selection();
  if(admissionHold||!running||!connected||!workerReady||!channel||!selected.launch_allowed)throw Error('Ready worker required for handoff hold');
  const token={},owner=channel,peer=channel._conn,gen=generation,worker=workerStatus.worker_id,boot=workerStatus.boot_id,pending=Array.from(inFlight),sourceVersion=selected.selected_manifest_sha256;
  admissionHold=token;
  function current(){if(admissionHold!==token||generation!==gen||channel!==owner||owner._conn!==peer||!running||!connected||!workerReady||!workerStatus||workerStatus.worker_id!==worker)throw Error('Worker changed during handoff hold');}
  async function snapshot(full=false){
    current();if(token.stopping)throw Error('Worker shutdown already submitted');const outcomes=await Promise.all(pending);current();
    if(outcomes.some(known=>!known))throw Error('Uncertain request outcome during handoff drain');
    const info=await owner.operation({op:'status'});current();
    validateReadiness(info,{implementation:'managed',bootId:boot});
    if(info.worker_id!==worker)throw Error('Worker identity changed during handoff inventory');
    const resources=validateResourceInventory(info),bound=processIdentities(info,peer.identity.pid);
    // This is a fresh inventory under a held service admission gate, not a
    // durable quiescence receipt or proof that detached work has stopped.
    return full?JSON.parse(JSON.stringify(info)):{...bound,resources:JSON.parse(JSON.stringify(resources))};
  }
  function prepared(id,digest){
   if(!options.selectionFile)throw Error('Durable selection required before shutdown');
   const state=selection(),p=state.pending;
   if(state.phase!=='reconciliation-required'||!p||p.id!==id||p.phase!=='prepared'||p.from.implementation!=='managed'||!sourceVersion||p.from.manifest_sha256!==sourceVersion||p.quiescence_sha256!==digest)throw Error('Selection does not bind this drained worker inventory');
   const target=p.to.implementation+'|'+p.to.manifest_sha256;
   if(token.targetVersion&&token.targetVersion!==target)throw Error('Selection target changed during handoff');
   token.targetVersion=target;
  }
  return {
   snapshot:async()=>{if(token.preparingStop)throw Error('Worker shutdown preparation in progress');return snapshot();},
   probeObserver:async (expectedManifest,requestId)=>{
    current();if(token.preparingStop||token.stopping||token.observerStaging||token.observerProbe)throw Error('Observer probe already pending');
    if(config.device==='s90d'&&options.observerChildProcess===false&&!options.externalObserverDirectory)throw Object.assign(Error('Process observer requires an external launch transport'),{outcome:'rejected'});
    if(typeof expectedManifest!=='string'||expectedManifest.length!==64||!/^[a-f0-9]{64}$/.test(expectedManifest))throw Error('Candidate manifest digest required');
    if(config.device==='s90d'&&options.externalObserverDirectory)observerTransactionId(requestId);
    token.preparingStop=true;
    try{
     const bound=await snapshot();current();
     const staged=await stageObserver({payload,device:config.device,bootId:boot,expectedManifest,execute:async(command,timeout)=>{
      current();token.observerStaging=true;const result=await owner.execute(command,timeout);current();return result;
     }});
     token.observerStaging=false;token.observerProbe=true;
     if(config.device==='s90d'&&options.externalObserverDirectory){
      const observer=await prepareRuntimeObserver({directory:options.externalObserverDirectory,requestId,staged,bound,confirm:()=>snapshot(true),execute:async(command,timeout)=>{
       current();const result=await owner.execute(command,timeout);current();return result;
      }});
      try{observer.assertReady();}finally{await observer.cancel();}
     }else if(config.device==='s90d'){
      try{await probeExecutable(staged);}catch(error){if(['failed','rejected'].includes(error.outcome))token.observerProbe=false;throw error;}current();
      const observer=await preparePidfdExit({...staged,bound,confirm:snapshot});
      try{observer.assertReady();}finally{await observer.cancel();}
     }else{
      // QN90A uses the service's proc-stat reader for the real handoff. Its WRT
      // child-process cleanup crashes in HandleWrap::Close; an unused native
      // executable smoke test must not take down the administration service.
      const result=observeProcesses(bound,options.readProcessFile);
      if(Object.values(result.processes).some(p=>p&&p.observation!=='present'))throw Error('Worker identity changed during observer probe');
     }
     const final=await snapshot();current();
     if(hash(JSON.stringify({boot_id:final.boot_id,worker_id:final.worker_id,processes:final.processes}))!==hash(JSON.stringify({boot_id:bound.boot_id,worker_id:bound.worker_id,processes:bound.processes})))throw Error('Worker changed during observer probe');
     token.observerProbe=false;
     return {verified:true,method:config.device==='s90d'?(options.externalObserverDirectory?'pidfd-external-bind-cancel':'pidfd-bind-cancel'):'proc-stat',manifest_sha256:staged.manifest_sha256,observer_sha256:staged.sha256,boot_id:boot,worker_id:worker,worker_stopped:false};
    }finally{token.preparingStop=false;}
   },
   shutdown:async transactionId=>{
    current();if(token.stopping||token.preparingStop||token.observerStaging)throw Error('Worker shutdown or observer staging requires reconciliation');
    const externalHandoff=config.device==='s90d'&&options.externalObserverDirectory&&options.externalObserverRetirement&&typeof options.externalObserverRetirement.inspectUnit==='function'&&typeof options.externalObserverRetirement.retireUnit==='function';
    if(options.observerChildProcess===false&&(options.processObserver||options.stagePackagedObserver)&&!externalHandoff)throw Object.assign(Error('Process observer requires an external launch transport with independent retirement'),{outcome:'rejected'});
    token.preparingStop=true;
    let observer=null,stagedObserver=null;
    try{
    const inventory=await snapshot();current();if(token.stopping)throw Error('Worker shutdown already submitted');
    const r=inventory.resources;
    if(r.transfers.length||r.helpers.length||r.jobs.some(j=>!j.monitor_finished||!['completed','cancelled','timed_out','interrupted'].includes(j.state)))throw Error('Worker resources must be settled before shutdown');
    const digest=hash(JSON.stringify(inventory));prepared(transactionId,digest);
    // Explicit trusted construction option only. Packaging/staging must provide
    // an immutable manifest-bound observer; never downgrade an EACCES to exit.
    let observerOptions=options.processObserver;
    if(!observerOptions&&options.stagePackagedObserver){
     const target=selection().pending.to;
     if(target.implementation!=='native-prototype')throw Error('Observer staging requires a native candidate target');
     token.observerStaging=true;
     stagedObserver=await stageObserver({payload,device:config.device,bootId:boot,expectedManifest:target.manifest_sha256,execute:async(command,timeout)=>{
      current();prepared(transactionId,digest);
      const result=await owner.execute(command,timeout);
      current();prepared(transactionId,digest);return result;
     }});
     token.observerStaging=false;observerOptions=stagedObserver;
    }
    if(externalHandoff){
     if(!stagedObserver)throw Error('External handoff requires a packaged observer');
     observer=await prepareRuntimeObserver({purpose:'handoff',directory:options.externalObserverDirectory,requestId:transactionId,staged:stagedObserver,bound:inventory,retirement:options.externalObserverRetirement,
      execute:async(command,timeout)=>{current();prepared(transactionId,digest);const result=await owner.execute(command,timeout);current();prepared(transactionId,digest);return result;},
      confirm:async()=>{
       const info=await snapshot(true);current();prepared(transactionId,digest);
       const fresh={...processIdentities(info,peer.identity.pid),resources:JSON.parse(JSON.stringify(validateResourceInventory(info)))};
       if(hash(JSON.stringify(fresh))!==digest)throw Error('Worker inventory changed after external process binding');
       return info;
      }});
     observer.assertReady();
    }else if(observerOptions){
     observer=await preparePidfdExit({...observerOptions,bound:inventory,confirm:async()=>{
      const fresh=await snapshot();current();prepared(transactionId,digest);
      if(hash(JSON.stringify(fresh))!==digest)throw Error('Worker inventory changed after process handle binding');
      return fresh;
     }});
     observer.assertReady();
    }else{
     const before=observeProcesses(inventory,options.readProcessFile);
     if(Object.values(before.processes).some(p=>p&&p.observation!=='present'))throw Error('Worker process identity changed before shutdown');
    }
    current();prepared(transactionId,digest);token.stopping=true;
    const shutdown=await owner.shutdown();
    const exited=await (observer?observer.waitForExit():waitForProcessExit(inventory,{read:options.readProcessFile}));
    if(admissionHold!==token||generation!==gen||channel!==owner||!running)throw Error('Handoff ownership changed during shutdown');
    prepared(transactionId,digest);
    return {transaction_id:transactionId,source_manifest_sha256:sourceVersion,inventory_sha256:digest,shutdown,exited,...(stagedObserver?{observer_stage:stagedObserver}:{})};
    }finally{try{if(observer)await observer.cancel();}finally{token.preparingStop=false;}}
   },
   release:()=>{current();if(token.stopping||token.preparingStop||token.observerStaging||token.observerProbe)throw Error('Cannot release a pending shutdown or unresolved observer staging/probe');admissionHold=null;}
  };
 }
 async function probeObserver(expectedManifest,requestId){
  let hold;try{hold=holdAdmission();}catch(error){throw Object.assign(error,{outcome:'rejected'});}
  try{const result=await hold.probeObserver(expectedManifest,requestId);hold.release();return result;}
  catch(error){try{hold.release();}catch(_){}throw error;}
 }
 return {status,start,stop,holdAdmission,probeObserver,operation:(value,data)=>submit(owner=>owner.operation(value,data)),execute:(command,timeout)=>submit(owner=>owner.execute(command,timeout))};
}
module.exports={createAgent,launchRequest};
