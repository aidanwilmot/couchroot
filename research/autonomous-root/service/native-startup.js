'use strict';
// Bootstrap selected native through a held authenticated executor. No public request
// is replayed. Old processes and the unit must be idle before a new launch.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {RootAgentServer}=require('./vendor/root-agent');
const {privateRead,privateDirectory}=require('./private-state');
const {hash,atomic}=require('./policy');
const {selectionStatus}=require('./worker-selection');
const {readRuntime}=require('./native-runtime');
const {validateReadiness,validateResourceInventory}=require('./worker-readiness');
const {validateBootstrap}=require('./held-bootstrap');
const {processIdentities}=require('./worker-processes');
const {observeCommand,parseObservation}=require('./restart-rollback');
const {inspectProductionUnit}=require('./observer-unit');
const {snapshotNativeJobs}=require('./native-retained-state');
function check(v){if(!v)throw Error('Selected native startup evidence unavailable');}
function exists(p){try{fs.lstatSync(p);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
function sync(p){const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY|fs.constants.O_NOFOLLOW);try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
function startupCandidate(selectionFile){
 const selected=selectionStatus(selectionFile),h=selected.history&&selected.history.slice(-1)[0];
 if(selected.phase!=='stable'||selected.selected_implementation!=='native-prototype')return null;
 const directory=path.dirname(selectionFile);check(privateDirectory(fs.lstatSync(directory))&&h&&h.outcome==='committed');
 const binding=readRuntime(directory,h.id),{record,original}=binding;
 const activationText=privateRead(path.join(directory,h.id+'.activation.json'),16384),activation=JSON.parse(activationText);
 check(h.to.implementation==='native-prototype'&&h.to.manifest_sha256===record.manifest_sha256&&selected.selected_manifest_sha256===record.manifest_sha256&&h.readiness_sha256===binding.readiness_sha256&&h.state_sha256===record.state_receipt_sha256);
 check(activation.schema===1&&activation.id===record.id&&activation.phase==='active'&&activation.boot_id===record.boot_id&&activation.manifest_sha256===record.manifest_sha256&&activation.readiness_sha256===binding.readiness_sha256&&JSON.stringify(activation.worker_identity)===JSON.stringify(original.worker_identity));
 for(const name of ['retirement-launch.pending','production-launch.pending','state-install.pending','managed-restore.pending','managed-launch.pending',h.id+'.activation.json.pending'])check(!exists(path.join(directory,name)));
 const installation=JSON.parse(privateRead(path.join(directory,h.id+'.state-install.json'),16384));check(hash(JSON.stringify(installation))===record.state_receipt_sha256);
 return {...binding,activation:{...activation,receipt_sha256:hash(activationText)},installation,selected};
}
function launchCommand(record,attempt){
 check(/^[a-f0-9]{32}$/.test(attempt.id)&&/^[a-f0-9]{64}$/.test(attempt.token_sha256)&&Number.isInteger(attempt.port)&&attempt.port>=1024&&attempt.port<=65535);
 check(attempt.token_file===path.dirname(record.token_file)+'/restart-'+attempt.id); // a fixed, previously verified service directory
 const d=record.directory,s=record.scope,q=v=>"'"+v.replace(/'/g,"'\\''")+"'";
 const digest=(p,sha)=>'test "$(sha256sum '+q(p)+' | cut -d " " -f1)" = '+sha+'\n';
 const file=(p,mode,sha)=>'test -f '+q(p)+'; test ! -L '+q(p)+'\ntest "$(stat -c "%u:%h:%a" '+q(p)+')" = 0:1:'+mode+'\n'+digest(p,sha);
 return 'set -eu\nPATH=/usr/bin:/bin\nexport PATH\nexport DBUS_SYSTEM_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/0-system/bus\n'+
  'test "$(cat /proc/sys/kernel/random/boot_id)" = '+record.boot_id+'\n'+
  [d,d+'/code',s].map(p=>'test -d '+p+'; test ! -L '+p+'; test "$(stat -c "%u:%a" '+p+')" = 0:700\n').join('')+
  file(d+'/code/worker','500',record.worker_sha256)+file(s+'/launcher','400',record.launcher_sha256)+
  'test -f '+q(attempt.token_file)+'; test ! -L '+q(attempt.token_file)+'\ntest "$(stat -c "%u:%h:%a:%s" '+q(attempt.token_file)+')" = 5001:1:600:44\n'+digest(attempt.token_file,attempt.token_sha256)+
  'test ! -e '+s+'/token; test ! -L '+s+'/token\n'+
  'test "$(systemctl show -p MainPID '+record.unit+')" = MainPID=0\ncg=$(systemctl show -p ControlGroup '+record.unit+' | sed -n "s/^ControlGroup=//p")\ncase "$cg" in "") ;; /system.slice/'+record.unit+') if test -e "/sys/fs/cgroup/systemd$cg/cgroup.procs"; then test "$(wc -l < "/sys/fs/cgroup/systemd$cg/cgroup.procs")" -eq 0; fi;; *) exit 1;; esac\n'+
  'systemctl stop '+record.unit+'\nsystemctl reset-failed '+record.unit+' 2>/dev/null || true\n'+
  '(set -C; cat '+q(attempt.token_file)+' > '+s+'/token)\nchmod 600 '+s+'/token\n'+digest(s+'/token',attempt.token_sha256)+
  'systemd-run --quiet --unit='+record.unit+' '+['User=0','Group=0','SmackProcessLabel=System','PrivateMounts=yes','BindReadOnlyPaths='+d+'/code','TimeoutStopSec=5s','RemainAfterExit=yes','KillMode=control-group','NoNewPrivileges=yes','AmbientCapabilities=','StandardOutput=null','StandardError=null'].map(p=>'--property='+q(p)).join(' ')+' '+[d+'/code/worker','127.0.0.1',String(attempt.port),s+'/token',s,s+'/launcher',record.launcher_sha256,'--production'].map(q).join(' ')+'\nprintf "NATIVE-RESTART-SUBMITTED\\n"\n';
}
async function startSelectedNative({selectionFile,executor}){
 const candidate=startupCandidate(selectionFile);check(candidate);const {record,activation,installation,selected}=candidate,directory=path.dirname(selectionFile),intent=path.join(directory,record.id+'.startup.json');
 const bound=()=>check(JSON.stringify(startupCandidate(selectionFile))===JSON.stringify(candidate));
 const confirm=async()=>{bound();const info=await executor.status();if(executor.implementation==='native-bootstrap')validateBootstrap(info,{bootId:record.boot_id,launcherSha256:executor.launcherSha256});else validateReadiness(info,{implementation:'managed',bootId:record.boot_id});const r=validateResourceInventory(info);check(!r.jobs.length&&!r.transfers.length&&!r.helpers.length);return processIdentities(info,executor.pid);};
 const own=await confirm(),run=async(c,t)=>{check(JSON.stringify(await confirm())===JSON.stringify(own));const result=await executor.execute(c,t);check(JSON.stringify(await confirm())===JSON.stringify(own));return result;};
 const evidence={source:record.source,known:Object.entries(record.worker_identity.processes),units:[record.unit]};
 const observe=async()=>{const r=await run(observeCommand(evidence),10000);check(r&&r.exit_code===0&&!r.timed_out&&!r.stderr);parseObservation(r.stdout,evidence.units);};
 await observe();
 // A prior uncertain launch is never retried until its unit is empty. Its token
 // can be removed only with the persisted digest; archive the resolved attempt.
 if(exists(intent)){
  const prior=JSON.parse(privateRead(intent,16384));check(prior.schema===1&&prior.origin_id===record.id&&/^[a-f0-9]{32}$/.test(prior.id)&&['submitted','ready','retired'].includes(prior.phase)&&/^[a-f0-9]{64}$/.test(prior.token_sha256)&&prior.token_file===path.dirname(record.token_file)+'/restart-'+prior.id);
  const r=await run('set -eu\nif test -e '+record.scope+'/token || test -L '+record.scope+'/token; then test -f '+record.scope+'/token; test ! -L '+record.scope+'/token; test "$(sha256sum '+record.scope+'/token | cut -d " " -f1)" = '+prior.token_sha256+'; rm '+record.scope+'/token; fi\n',5000);check(r.exit_code===0&&!r.timed_out&&!r.stderr);
  if(exists(prior.token_file)){check(hash(privateRead(prior.token_file,44))===prior.token_sha256);fs.unlinkSync(prior.token_file);}
  if(exists(path.dirname(prior.token_file)))fs.rmdirSync(path.dirname(prior.token_file));
  atomic(path.join(directory,record.id+'.startup-'+prior.id+'.json'),{...prior,phase:'retired'});fs.unlinkSync(intent);sync(directory);
 }
 await snapshotNativeJobs({record,installation,execute:run});
 const tokenDirectory=path.dirname(record.token_file);check(!exists(tokenDirectory));fs.mkdirSync(tokenDirectory,{mode:0o700});
 const secret=crypto.randomBytes(32),id=crypto.randomBytes(16).toString('hex'),tokenFile=tokenDirectory+'/restart-'+id;fs.writeFileSync(tokenFile,secret.toString('base64'),{mode:0o600,flag:'wx'});sync(tokenDirectory);sync(directory);
 let channel,timer,resolve,reject,closed=false;
 const connection=new Promise((yes,no)=>{resolve=yes;reject=no;});connection.catch(()=>{});
 channel=new RootAgentServer({secret,bindHost:'127.0.0.1',port:0,onConnect:peer=>resolve(peer),onClose:()=>{closed=true;reject(Error('Native restart transport closed'));}});
 try{
  await new Promise((yes,no)=>{channel.start(yes);channel._server.once('error',no);});
  const attempt={schema:1,id,origin_id:record.id,phase:'submitted',port:channel.listeningPort(),token_file:tokenFile,token_sha256:hash(secret.toString('base64'))};
  await observe();bound();atomic(intent,attempt);timer=setTimeout(()=>reject(Error('Native restart connection deadline')),35000);
  const r=await run(launchCommand(record,attempt),25000);check(r&&r.exit_code===0&&!r.timed_out&&!r.stderr&&r.stdout==='NATIVE-RESTART-SUBMITTED\n');
  const peer=await connection;clearTimeout(timer);check(!closed&&channel._conn===peer&&['uid','euid','gid','egid'].every(k=>peer.identity[k]===0)&&peer.identity.smack==='System');
  const info=await channel.operation({op:'status'});validateReadiness(info,{implementation:'native-prototype',bootId:record.boot_id,launcherSha256:record.launcher_sha256});
  const identity=processIdentities(info,peer.identity.pid),resources=validateResourceInventory(info);check(!resources.jobs.length&&!resources.transfers.length&&!resources.helpers.length&&identity.worker_id!==record.worker_identity.worker_id);
  const unit=await inspectProductionUnit({unit:record.unit,bootId:record.boot_id,execute:run});check(unit.active_state==='active'&&unit.sub_state==='running'&&unit.main_pid===identity.processes.guardian.pid&&unit.exec_code===0&&unit.exec_status===0);
  const verify='set -eu\n'+Object.values(identity.processes).map(p=>'line=$(cat /proc/'+p.pid+'/stat); rest=${line##*) }; set -- $rest; test "$#" -ge 20; shift 19; test "$1" = '+p.start_ticks+'\ntest /proc/'+p.pid+'/exe -ef '+record.directory+'/code/worker\n').join('')+'test ! -e '+record.scope+'/token\nprintf "NATIVE-RESTART-VERIFIED\\n"\n';
  const verified=await run(verify,5000);check(verified.exit_code===0&&!verified.timed_out&&!verified.stderr&&verified.stdout==='NATIVE-RESTART-VERIFIED\n');
  check(!closed&&channel._conn===peer&&JSON.stringify(processIdentities(await channel.operation({op:'status'}),peer.identity.pid))===JSON.stringify(identity));bound();
  const next={...record,worker_identity:identity,unit_started_monotonic:unit.started_monotonic};
  atomic(path.join(directory,record.id+'.runtime.json'),{schema:1,id:record.id,phase:'ready',readiness_sha256:candidate.readiness_sha256,activation_sha256:activation.receipt_sha256,record:next});
  atomic(intent,{...attempt,phase:'ready'});fs.unlinkSync(tokenFile);fs.rmdirSync(tokenDirectory);sync(directory);
  return {channel,record:next,activation,info,selection:JSON.stringify(selected)};
 }catch(cause){channel.close();throw Object.assign(Error('Selected native startup requires reconciliation'),{outcome:'unknown',cause});}
 finally{clearTimeout(timer);}
}
module.exports={startupCandidate,startSelectedNative,launchCommand};
