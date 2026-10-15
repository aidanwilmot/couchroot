'use strict';
// Publish local rollback activation only after combined live completion evidence.
const fs=require('fs'),path=require('path');
const {hash,atomic}=require('./policy');
const {privateRead}=require('./private-state');
const {verifyManagedCompletion}=require('./managed-completion');
const {selectionStatus}=require('./worker-selection');
function check(ok){if(!ok)throw Error('Managed activation ownership unavailable');}
function exists(p){try{fs.lstatSync(p);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
async function activateManaged(options){
 const {journalDirectory,selectionFile}=options,managed=JSON.parse(JSON.stringify(options.managed));
 const proof=await verifyManagedCompletion({...options,managed});
 const inputsText=privateRead(path.join(journalDirectory,managed.id+'.managed-restore-input.json'),524288),inputs=JSON.parse(inputsText),native=inputs.record;
 const file=path.join(journalDirectory,managed.id+'.managed-activation.json'),intent=file+'.pending';check(!exists(file)&&!exists(intent));
 const tokenState=record=>{const directory=path.dirname(record.token_file);check(path.dirname(directory)===journalDirectory&&record.token_file===directory+'/token');
  if(!exists(directory))return false;
  const st=fs.lstatSync(directory);check(st.isDirectory()&&!st.isSymbolicLink()&&st.uid===process.geteuid()&&(st.mode&0o7777)===0o700&&fs.readdirSync(directory).join('|')==='token'&&hash(privateRead(record.token_file,44))===record.token_sha256);return true;};
 const marker=(name,id)=>{const p=path.join(journalDirectory,name);if(!exists(p))return false;check(privateRead(p,64)===id+'\n');return true;};
 check(tokenState(managed)&&marker('managed-restore.pending',managed.id)&&marker('managed-launch.pending',managed.id));
 const nativeToken=tokenState(native),state=marker('state-install.pending',native.id),launch=marker('production-launch.pending',native.id);
 check(nativeToken===state&&state===launch);
 if(!nativeToken){
  // Native activation may already have retired its local ownership. Require
  // its durable receipt; absence alone does not prove completed activation.
  const active=JSON.parse(privateRead(path.join(journalDirectory,native.id+'.activation.json'),16384)),selected=selectionStatus(selectionFile);
  check(selected.history&&selected.history.some(h=>h.id===native.id&&h.outcome==='committed'&&h.to.implementation==='native-prototype'&&h.to.manifest_sha256===native.manifest_sha256&&h.readiness_sha256===hash(JSON.stringify(native))));
  check(active.schema===1&&active.id===native.id&&active.phase==='active'&&active.boot_id===native.boot_id&&active.manifest_sha256===native.manifest_sha256&&active.readiness_sha256===hash(JSON.stringify(native))&&JSON.stringify(active.worker_identity)===JSON.stringify(native.worker_identity));
 }
 const activation={schema:1,id:managed.id,phase:'active',boot_id:managed.boot_id,manifest_sha256:managed.manifest_sha256,readiness_sha256:proof.managed_readiness_sha256,production_retirement_sha256:proof.production_retirement_sha256,provider_retirement_sha256:proof.provider_retirement_sha256,worker_identity:managed.worker_identity},text=JSON.stringify(activation);
 const steps=[];if(nativeToken)steps.push({kind:'file',path:native.token_file,sha256:native.token_sha256},{kind:'directory',path:path.dirname(native.token_file)},{kind:'file',path:path.join(journalDirectory,'state-install.pending'),sha256:hash(native.id+'\n')},{kind:'file',path:path.join(journalDirectory,'production-launch.pending'),sha256:hash(native.id+'\n')});
 steps.push({kind:'file',path:managed.token_file,sha256:managed.token_sha256},{kind:'directory',path:path.dirname(managed.token_file)},{kind:'file',path:path.join(journalDirectory,'managed-restore.pending'),sha256:hash(managed.id+'\n')},{kind:'file',path:path.join(journalDirectory,'managed-launch.pending'),sha256:hash(managed.id+'\n')});
 const selected=JSON.stringify(selectionStatus(selectionFile)),ownership={schema:1,activation,input_sha256:hash(inputsText),steps},intentText=JSON.stringify(ownership);
 const owned=()=>{check(JSON.stringify(selectionStatus(selectionFile))===selected&&privateRead(path.join(journalDirectory,managed.id+'.managed-restore-input.json'),524288)===inputsText&&privateRead(path.join(journalDirectory,managed.id+'.managed-launch.json'),16384)===JSON.stringify(managed)&&privateRead(intent,16384)===intentText);};
 const sync=()=>{const fd=fs.openSync(journalDirectory,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY|fs.constants.O_NOFOLLOW);try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}};
 const fd=fs.openSync(intent,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);try{fs.writeFileSync(fd,intentText);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}sync();
 try{
  owned();check(JSON.stringify(await verifyManagedCompletion({...options,managed}))===JSON.stringify(proof));owned();
  for(const step of steps){owned();if(step.kind==='file'){check(hash(privateRead(step.path,64))===step.sha256);fs.unlinkSync(step.path);}else{const st=fs.lstatSync(step.path);check(st.isDirectory()&&!st.isSymbolicLink()&&st.uid===process.geteuid()&&(st.mode&0o7777)===0o700&&fs.readdirSync(step.path).length===0);fs.rmdirSync(step.path);}sync();}
  owned();atomic(file,activation);check(privateRead(file,16384)===text);fs.unlinkSync(intent);sync();return Object.freeze({...activation,receipt_sha256:hash(text)});
 }catch(cause){throw Object.assign(Error('Managed activation requires reconciliation'),{outcome:'unknown',cause});}
}
module.exports={activateManaged};
