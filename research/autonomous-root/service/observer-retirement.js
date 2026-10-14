'use strict';
// Narrow adapter over an independently launched, authenticated native instance.
// Launch ownership, artifact staging and provider teardown belong to its caller.
const {processIdentities}=require('./worker-processes');
const {validateResourceInventory}=require('./worker-readiness');
const {snapshotManagedJobs}=require('./retained-state');
const {installRetainedState,acceptRetainedState}=require('./retained-install');
const {inspectObserverUnit,retireObserverUnit}=require('./observer-unit');
const HEX=/^[a-f0-9]{64}$/,BOOT=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const CAPS=['prototype-scoped-files-v1','worker-process-identity-v1','guardian-parent-identity-v1','resource-inventory-v1','prototype-independent-launcher-v1','prototype-crash-guardian-v1'];
function requireValue(ok){if(!ok)throw Error('Independent observer retirement identity unavailable');}
function binding(value){
 requireValue(value&&Object.keys(value).sort().join('|')==='bootId|sha256|unit'&&typeof value.unit==='string'&&value.unit.length===59&&/^couchroot-observer-[a-f0-9]{32}\.service$/.test(value.unit)&&typeof value.bootId==='string'&&value.bootId.length===36&&BOOT.test(value.bootId)&&typeof value.sha256==='string'&&value.sha256.length===64&&HEX.test(value.sha256));
 return Object.freeze({unit:value.unit,bootId:value.bootId,sha256:value.sha256});
}
function validateProvider(info,peer,expected,source){
 requireValue(peer&&peer.identity&&Number.isInteger(peer.identity.pid)&&peer.identity.pid>1&&['uid','euid','gid','egid'].every(k=>peer.identity[k]===0)&&peer.identity.smack==='System');
 requireValue(info&&info.implementation==='native-prototype'&&info.boot_id===expected.bootId&&info.boot_id===source.boot_id&&info.worker_id!==source.worker_id&&info.lifetime_mode==='bounded'&&info.lifetime_seconds===300);
 requireValue(Array.isArray(info.capabilities)&&info.capabilities.length<=64&&info.capabilities.every(c=>typeof c==='string'&&c.length<=128)&&new Set(info.capabilities).size===info.capabilities.length&&CAPS.every(c=>info.capabilities.includes(c))&&!info.capabilities.includes('prototype-production-files-v1'));
 requireValue(info.app_launcher&&info.app_launcher.sha256===expected.launcherSha256&&info.app_launcher.independently_staged===true);
 const observed=processIdentities(info,peer.identity.pid),resources=validateResourceInventory(info);
 requireValue(observed.processes.guardian.pid>1);
 requireValue(!resources.jobs.length&&!resources.transfers.length&&!resources.helpers.length);
 const sourcePids=Object.values(source.processes).filter(Boolean).map(p=>p.pid);
 requireValue(Object.values(observed.processes).every(p=>!sourcePids.includes(p.pid)));
 return observed;
}
async function createObserverRetirement({channel,source,bound,launcherSha256}){
 const target=binding(bound);
 requireValue(typeof launcherSha256==='string'&&launcherSha256.length===64&&HEX.test(launcherSha256));
 requireValue(source&&source.processes&&source.processes.worker);
 // Validate the complete source identity as well; malformed exclusions cannot
 // accidentally admit a source worker or its guardian as the independent peer.
 const sourceIdentity=processIdentities({...source,capabilities:['worker-process-identity-v1'],...(source.processes.guardian?{implementation:'native-prototype',guardian_pid:source.processes.guardian.pid}:{})},source.processes.worker.pid);
 requireValue(channel&&typeof channel.operation==='function'&&typeof channel.execute==='function');
 const clock=()=>{const t=process.hrtime();return t[0]*1000+t[1]/1000000;};
 let expires=clock()+5000;
 const peer=channel._conn,expected={bootId:target.bootId,launcherSha256};
 let pinned=null,busy=false,failed=false,retirementEntered=false,retired=false,snapshotEntered=false,retainedSnapshot=null,installEntered=false,retainedInstallation=null,acceptEntered=false;
 function current(){requireValue(!failed&&channel._conn===peer&&peer&&clock()<expires);}
 async function verify(){
  current();const info=await channel.operation({op:'status'});current();
  const actual=validateProvider(info,peer,expected,sourceIdentity),serialized=JSON.stringify(actual);
  if(pinned===null)pinned=serialized;else requireValue(pinned===serialized);
 }
 await verify();
 function match(request){const actual=binding(request);requireValue(JSON.stringify(actual)===JSON.stringify(target));}
 async function execute(command,timeout){
  await verify();const remaining=Math.floor(expires-clock());requireValue(remaining>=100);const result=await channel.execute(command,Math.min(timeout,remaining));await verify();return result;
 }
 async function operation(request,mutating){
  match(request);requireValue(!busy&&!failed&&!retired&&(!mutating||!retirementEntered));
  busy=true;expires=clock()+(mutating?8000:5000);if(mutating)retirementEntered=true;
  try{
   const options={...target,execute};
   const result=await (mutating?retireObserverUnit(options):inspectObserverUnit(options));
   if(mutating)retired=true;
   return result;
  }catch(error){failed=true;throw error;}
  finally{busy=false;}
 }
 const identity=JSON.parse(pinned);Object.freeze(identity.processes.worker);Object.freeze(identity.processes.guardian);Object.freeze(identity.processes);Object.freeze(identity);
 return Object.freeze({
  identity,
  inspectUnit:request=>operation(request,false),
  retireUnit:request=>operation(request,true),
  snapshotManagedJobs:async()=>{
   requireValue(!busy&&!failed&&!snapshotEntered);busy=true;snapshotEntered=true;expires=clock()+60000;
   try{const result=await snapshotManagedJobs({source:sourceIdentity,execute});retainedSnapshot=JSON.parse(JSON.stringify(result));return result;}
   catch(error){failed=true;throw error;}
   finally{busy=false;}
  },
  acceptManagedState:async options=>{
   requireValue(!busy&&!failed&&!acceptEntered&&retainedInstallation);busy=true;acceptEntered=true;expires=clock()+120000;
   try{return await acceptRetainedState({...options,id:retainedInstallation.id,manifestSha256:retainedInstallation.manifest_sha256,receiptSha256:retainedInstallation.receipt_sha256,execute});}
   catch(error){failed=true;throw error;}
   finally{busy=false;}
  },
  installManagedState:async options=>{
   requireValue(!busy&&!failed&&!installEntered&&retainedSnapshot);busy=true;installEntered=true;expires=clock()+120000;
   try{retainedInstallation=await installRetainedState({...options,snapshot:retainedSnapshot,execute});return retainedInstallation;}
   catch(error){failed=true;throw error;}
   finally{busy=false;}
  }
 });
}
module.exports={createObserverRetirement,validateProvider};
