'use strict';
// Single-use live handoff controller. Uncertain work stays held for recovery.
const fs=require('fs'),path=require('path');
const {hash}=require('./policy');
const {loadCandidate}=require('./native-candidate');
const {SelectionJournal,managedVersion}=require('./worker-selection');
const {openProductionSession}=require('./production-session');
function check(ok){if(!ok)throw Error('Native migration prerequisites unavailable');}
function createNativeMigration({agent,device,payload,selectionFile}){
 let entered=false,closed=false,phase='idle',failedPhase=null,resuming=false,id=null,hold=null,retirement=null,production=null,begun=false;
 const status=()=>({phase,transaction_id:id});
 const closeTransport=()=>{closed=true;if(production)production.closeTransport();if(retirement)retirement.closeTransport();};
 const move=next=>{check(!closed);phase=next;};
 async function run(manifestSha256){
  check(!entered);entered=true;
  try{
   move('preflight');check(['s90d','qn90a'].includes(device)&&typeof selectionFile==='string'&&path.isAbsolute(selectionFile)&&typeof manifestSha256==='string'&&manifestSha256.length===64&&/^[a-f0-9]+$/.test(manifestSha256));
   const journalDirectory=path.dirname(selectionFile),st=fs.lstatSync(journalDirectory);check(st.isDirectory()&&!st.isSymbolicLink()&&st.uid===process.geteuid()&&(st.mode&0o7777)===0o700);
   for(const name of ['retirement-launch.pending','production-launch.pending','state-install.pending'])try{fs.lstatSync(path.join(journalDirectory,name));throw Error('Existing native transition requires reconciliation');}catch(error){if(error.code!=='ENOENT')throw error;}
   const candidate=loadCandidate(payload,device);check(candidate&&candidate.manifest_sha256===manifestSha256);
   const journal=new SelectionJournal(selectionFile),managed=managedVersion(payload);let state=journal.read();
   if(!state)state=journal.initialize({implementation:'managed',manifest_sha256:managed});
   check(!state.pending&&state.selected.implementation==='managed'&&state.selected.manifest_sha256===managed);
   move('draining');hold=agent.holdAdmission();const inventory=await hold.snapshot(),r=inventory.resources;
   check(r&&!r.transfers.length&&!r.helpers.length&&r.jobs.every(j=>j.monitor_finished&&['completed','cancelled','timed_out','interrupted'].includes(j.state)));
   // SelectionJournal leaves its writer marker on ambiguous publication; do not
   // release the hold if begin may have published despite throwing.
   begun=true;state=journal.begin(state.revision,{implementation:'native-prototype',manifest_sha256:manifestSha256},hash(JSON.stringify(inventory)));id=state.pending.id;
   move('provider');retirement=await hold.prepareNative(id);
   move('stopping-source');const stopped=await hold.shutdown(id);check(stopped.transaction_id===id&&stopped.inventory_sha256===state.pending.quiescence_sha256);
   move('retained-state');await retirement.provider.snapshotManagedJobs();
   const installation=await retirement.provider.installManagedState({id,manifestSha256,journalDirectory,selectionFile});check(installation.id===id&&installation.phase==='ready');
   const accepted=await retirement.provider.acceptManagedState({journalDirectory,selectionFile});check(accepted.pending&&accepted.pending.id===id&&accepted.pending.phase==='state-ready'&&accepted.pending.state_sha256===installation.receipt_sha256);
   move('production');production=await openProductionSession({id,device,payload,journalDirectory,selectionFile,provider:retirement.provider});
   const trial=journal.read();check(trial.pending&&trial.pending.id===id&&trial.pending.phase==='trial-ready'&&trial.pending.readiness_sha256===production.readiness_sha256&&trial.pending.state_sha256===installation.receipt_sha256);
   move('committing');journal.commit(trial.revision,id);
   move('adopting');await hold.adoptProduction(production);
   move('activating');const activated=await hold.completeProduction(retirement);check(activated.transaction_id===id&&activated.admission_held===false);
   move('active');return {...activated,selected_implementation:'native-prototype'};
  }catch(cause){
   if(closed)closeTransport();
   if(!begun&&hold){try{hold.release();}catch(_){begun=true;}}
   failedPhase=phase;phase=begun?'reconciliation-required':'rejected';
   // Keep live session references for explicit recovery. Closing a connection
   // here would destroy useful recovery access without proving remote cleanup.
   throw Object.assign(Error(begun?'Native migration requires reconciliation':'Native migration rejected before handoff'),{outcome:begun?'unknown':'rejected',cause});
  }
 }
 async function resumeActivation(){
  check(!closed&&!resuming&&phase==='reconciliation-required'&&failedPhase==='activating'&&hold&&retirement&&production);resuming=true;
  try{move('resuming-activation');const activated=await hold.completeProduction(retirement,{resume:true});check(activated.transaction_id===id&&activated.admission_held===false);move('active');return {...activated,selected_implementation:'native-prototype'};}
  catch(cause){phase='reconciliation-required';throw Object.assign(Error('Native activation resume requires reconciliation'),{outcome:'unknown',cause});}
  finally{resuming=false;}
 }
 return Object.freeze({run,resumeActivation,status,closeTransport});
}
module.exports={createNativeMigration};
