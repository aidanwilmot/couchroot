'use strict';
// One background rehearsal per live coordinator. Durable requests are never replayed.
function check(ok){if(!ok)throw Error('Invalid native administration request');}
const id=v=>typeof v==='string'&&v.length>=16&&v.length<=64&&/^[-a-zA-Z0-9]+$/.test(v);
const digest=v=>typeof v==='string'&&v.length===64&&/^[a-f0-9]+$/.test(v);
function createNativeTasks({agent,journal}){
 let running=false,task=null;
 const status=()=>task?JSON.parse(JSON.stringify(task)):null;
 function launch(kind,value,run,rehearsalId){
  check(!running);journal.begin({id:value.id,command:kind+':'+JSON.stringify(value),timeout_ms:25000});
  const current={id:value.id,rehearsal_id:rehearsalId,kind,state:'submitted',result:null,detail:null};task=current;running=true;
  Promise.resolve().then(async()=>{
   try{const result=await run();journal.finish(current.id,{exit_code:0,timed_out:false});current.result=result;current.state='completed';}
   catch(error){
    let outcome=['rejected','failed'].includes(error&&error.outcome)?error.outcome:'unknown';
    if(outcome!=='unknown')try{journal.finish(current.id,{exit_code:1,timed_out:false});}catch(_){outcome='unknown';}
    current.state=outcome;current.detail=String(error&&error.message||error).slice(0,200);
   }finally{running=false;}
  });
  return {id:current.id,rehearsal_id:current.rehearsal_id,state:'submitted',status_url:'/v1/native/status'};
 }
 return Object.freeze({busy:()=>running,status,
  rehearse:value=>{
   check(value&&!Array.isArray(value)&&Object.keys(value).sort().join('|')==='id|manifest_sha256|runtime_sha256'&&id(value.id)&&digest(value.manifest_sha256)&&digest(value.runtime_sha256));
   check((!task||task.kind==='native.cleanup-restart'&&task.state==='completed')&&typeof agent.rehearseNative==='function');const s=agent.status();check(s.connected&&s.worker_ready===true&&!s.admission_held&&s.selected_implementation==='managed');
   return launch('native.rehearse',value,()=>agent.rehearseNative(value.manifest_sha256,value.runtime_sha256),value.id);
  },
  cleanupRestart:value=>{
   check(value&&!Array.isArray(value)&&Object.keys(value).sort().join('|')==='id|transaction_id'&&id(value.id)&&typeof value.transaction_id==='string'&&/^[a-f0-9]{32}$/.test(value.transaction_id));
   check((!task||task.state!=='unknown')&&typeof agent.cleanupRestart==='function');const s=agent.status();check(s.connected&&s.worker_ready===true&&!s.admission_held&&s.selected_implementation==='managed');
   return launch('native.cleanup-restart',value,()=>agent.cleanupRestart(value.transaction_id),value.id);
  },
  resume:value=>{
   check(value&&!Array.isArray(value)&&Object.keys(value).sort().join('|')==='id|rehearsal_id'&&id(value.id)&&id(value.rehearsal_id)&&value.id!==value.rehearsal_id);
   check(task&&task.rehearsal_id===value.rehearsal_id&&task.state==='unknown'&&typeof agent.resumeManagedActivation==='function');
   return launch('native.resume-managed',value,()=>agent.resumeManagedActivation(),value.rehearsal_id);
  }
 });
}
module.exports={createNativeTasks};
