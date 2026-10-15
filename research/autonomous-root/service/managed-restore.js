'use strict';
// Durable state restoration only. Admission must remain held until managed
// launch/readiness and selection are reconciled by the owning controller.
const fs=require('fs'),path=require('path');
const {atomic,hash}=require('./policy');
const {privateRead}=require('./private-state');
const {selectionStatus}=require('./worker-selection');
const {snapshotNativeJobs}=require('./native-retained-state');
const {planManagedRestore}=require('./managed-restore-plan');
function check(ok){if(!ok)throw Error('Managed restoration evidence unavailable');}
async function restoreManagedJobs(options){
 const {journalDirectory,selectionFile,execute}=options;
 check(typeof execute==='function'&&typeof journalDirectory==='string'&&path.isAbsolute(journalDirectory)&&path.dirname(selectionFile)===journalDirectory);
 const st=fs.lstatSync(journalDirectory);check(st.isDirectory()&&!st.isSymbolicLink()&&st.uid===process.geteuid()&&(st.mode&0o7777)===0o700);
 const {record,installation,baseline,snapshot}=JSON.parse(JSON.stringify(options));
 const plan=planManagedRestore({record,installation,baseline,snapshot}),id=record.id;
 const initial=selectionStatus(selectionFile),p=initial.pending;
 check(initial.phase==='reconciliation-required'&&p);
 // A failed native trial rolls back its existing transaction. Once native was
 // committed, returning to managed is a new, separately quiesced transition.
 if(p.phase==='rollback-required')check(p.id===id&&p.from.implementation==='managed'&&p.to.implementation==='native-prototype'&&p.to.manifest_sha256===record.manifest_sha256);
 else{
  check(p.phase==='prepared'&&p.from.implementation==='native-prototype'&&p.from.manifest_sha256===record.manifest_sha256&&p.to.implementation==='managed');
  const h=initial.history[initial.history.length-1];check(h&&h.id===id&&h.outcome==='committed'&&h.from.implementation==='managed'&&h.from.manifest_sha256===p.to.manifest_sha256&&h.state_sha256===record.state_receipt_sha256&&h.readiness_sha256===hash(JSON.stringify(record)));
 }
 const selectionText=JSON.stringify(initial),inputs={record,installation,baseline,snapshot},inputText=JSON.stringify(inputs);
 const file=path.join(journalDirectory,p.id+'.managed-restore.json'),saved=path.join(journalDirectory,p.id+'.managed-restore-input.json'),marker=path.join(journalDirectory,'managed-restore.pending');
 const receipt={...plan.receipt,transition_id:p.id,quiescence_sha256:p.quiescence_sha256,input_sha256:hash(inputText)},pending={...receipt,phase:'pending'};
 const refs=[[id+'.production.json',record],[id+'.state-install.json',installation],[id+'.retained-snapshot.json',baseline]];
 const checkInputs=()=>{check(JSON.stringify(selectionStatus(selectionFile))===selectionText);for(const [name,value] of refs)check(privateRead(path.join(journalDirectory,name),262144)===JSON.stringify(value));};
 checkInputs();
 const sync=()=>{const fd=fs.openSync(journalDirectory,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY|fs.constants.O_NOFOLLOW);try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}};
 const create=(name,value)=>{const fd=fs.openSync(name,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);try{fs.writeFileSync(fd,value);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}};
 let localText=JSON.stringify(pending);
 if(options.resume===true){localText=privateRead(file,16384);check([JSON.stringify(pending),JSON.stringify(receipt)].includes(localText)&&privateRead(saved,524288)===inputText&&privateRead(marker,64)===p.id+'\n');}
 else{
  check(options.resume===undefined||options.resume===false);
  for(const name of [file,saved,marker])try{fs.lstatSync(name);throw Error('Managed restore requires reconciliation');}catch(e){if(e.code!=='ENOENT')throw e;}
  create(marker,p.id+'\n');create(saved,inputText);create(file,localText);sync();
 }
 const owned=()=>{checkInputs();check(privateRead(marker,64)===p.id+'\n'&&privateRead(saved,524288)===inputText&&privateRead(file,16384)===localText);};
 const started=process.hrtime();
 const checkedExecute=async(command,timeout)=>{owned();const r=await execute(command,timeout),t=process.hrtime(started);owned();check(t[0]*1000+t[1]/1000000<120000);return r;};
 const run=async c=>{const r=await checkedExecute(c,25000);check(r&&r.exit_code===0&&!r.timed_out&&!r.stderr&&typeof r.stdout==='string'&&r.stdout.length<128);return r.stdout;};
 const recheck=async()=>{const current=await snapshotNativeJobs({record,installation,execute:checkedExecute});check(current.sha256===snapshot.sha256);};
 try{
  await recheck();let phase=await run(plan.inspect);
  if(localText===JSON.stringify(receipt))check(phase==='RESTORE-READY\n');
  if(phase==='RESTORE-ABSENT\n'){check(await run(plan.begin)==='RESTORE-PENDING\n');phase='RESTORE-PENDING\n';}
  if(phase==='RESTORE-PENDING\n'){for(const c of plan.copies)check(await run(c)==='');phase=await run(plan.inspect);}
  if(phase==='RESTORE-STAGED\n'){await recheck();check(await run(plan.retire)==='');phase=await run(plan.inspect);}
  if(phase==='RESTORE-CUTOVER\n'){await recheck();check(await run(plan.publish)==='RESTORE-READY\n');phase=await run(plan.inspect);}
  check(phase==='RESTORE-READY\n');await recheck();check(await run(plan.verify)==='RESTORE-READY\n');owned();
  if(localText!==JSON.stringify(receipt))atomic(file,receipt);
  // Keep the marker and preserved baseline until managed readiness is accepted.
  return Object.freeze({...receipt,receipt_sha256:hash(JSON.stringify(receipt))});
 }catch(cause){throw Object.assign(Error('Managed state restoration requires reconciliation'),{outcome:'unknown',cause});}
}
module.exports={restoreManagedJobs};
