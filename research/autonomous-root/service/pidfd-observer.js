'use strict';
// Internal bridge. Callers must supply a verified, staged executable and obtain
// fresh authenticated worker status AFTER BOUND, before submitting SHUTDOWN.
const {spawn}=require('child_process');
const fs=require('fs'),crypto=require('crypto');
const {processIdentities}=require('./worker-processes');

function preparePidfdExit({binary,sha256,bound,confirm}){
 if(typeof binary!=='string'||!binary.startsWith('/')||binary.includes('\0')||typeof sha256!=='string'||!/^[a-f0-9]{64}$/.test(sha256)||typeof confirm!=='function')return Promise.reject(Error('Invalid process observer configuration'));
 let identity;
 try{
  identity=processIdentities({...bound,capabilities:['worker-process-identity-v1']},bound.processes.worker.pid);
  // Native's cached guardian identity is not fresh confirmation. Do not allow
  // a caller to infer guardian ownership merely from a previously returned PID.
  if(identity.processes.guardian!==null)throw Error('Guardian observation is not integrated');
  // Package/staging owner must keep this executable immutable through spawn.
  // The digest is supplied by that trusted manifest, never by a request body.
  const fd=fs.openSync(binary,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
  try{
   const stat=fs.fstatSync(fd);
   if(!stat.isFile()||stat.size<1||stat.size>128*1024)throw Error('Invalid observer artifact');
   const bytes=Buffer.alloc(stat.size+1);let used=0;
   while(used<bytes.length){const n=fs.readSync(fd,bytes,used,bytes.length-used,null);if(!n)break;used+=n;}
   if(used!==stat.size||crypto.createHash('sha256').update(bytes.subarray(0,used)).digest('hex')!==sha256)throw Error('Observer artifact digest mismatch');
  }finally{fs.closeSync(fd);}
 }catch(e){return Promise.reject(e);}
 const expected=JSON.stringify(identity);
 let readyResolve,readyReject,exitResolve,exitReject,closedResolve;
 const ready=new Promise((yes,no)=>{readyResolve=yes;readyReject=no;});
 const exited=new Promise((yes,no)=>{exitResolve=yes;exitReject=no;});
 exited.catch(()=>{}); // May fail while the caller is awaiting its shutdown ACK.
 const closed=new Promise(yes=>{closedResolve=yes;});
 let child,phase='binding',buffer='',outputBytes=0,errorBytes=0,failed=false,done=false;
 const timer=setTimeout(()=>fail(Error('Process observer deadline expired')),32000);
 function fail(error){
  if(failed||done)return;
  failed=true;clearTimeout(timer);
  if(child)child.kill('SIGKILL'); // Our observer child only, never the target PID.
  readyReject(error);exitReject(error);
 }
 async function cancel(){
  if(!done)fail(Error('Process observation cancelled'));
  let timeout;
  try{await Promise.race([closed,new Promise((_,no)=>{timeout=setTimeout(()=>no(Error('Observer child exit not confirmed')),2000);})]);}
  finally{clearTimeout(timeout);}
 }
 function line(value){
  if(failed)return;
  if(phase==='binding'&&value==='BOUND'){
   phase='confirming';
   Promise.resolve().then(()=>confirm()).then(fresh=>{
    if(failed)return;
    const value=processIdentities({...fresh,capabilities:['worker-process-identity-v1']},identity.processes.worker.pid);
    if(JSON.stringify(value)!==expected)throw Error('Worker identity changed after pidfd binding');
    phase='arming';child.stdin.write('ARM\n');
   }).catch(fail);
  }else if(phase==='arming'&&value==='ARMED'){
   phase='waiting';
   readyResolve(Object.freeze({waitForExit:()=>exited,cancel,assertReady:()=>{if(failed||done||phase!=='waiting')throw Error('Process observer is no longer armed');}}));
  }else if(phase==='waiting'&&value==='EXITED')phase='exited';
  else fail(Error('Invalid process observer response'));
 }
 try{child=spawn(binary,[identity.boot_id,String(identity.processes.worker.pid)],{cwd:'/',env:{PATH:'/usr/bin:/bin',LANG:'C'},stdio:['pipe','pipe','pipe']});}
 catch(e){closedResolve();fail(e);return ready;}
 child.on('error',fail);
 child.stdin.on('error',fail);
 child.stdout.on('error',fail);child.stderr.on('error',fail);
 child.stdout.on('data',bytes=>{
  outputBytes+=bytes.length;
  if(outputBytes>64||bytes.some(b=>b>127)){fail(Error('Invalid process observer output'));return;}
  buffer+=bytes.toString('ascii');
  let index;
  while((index=buffer.indexOf('\n'))!==-1){const value=buffer.slice(0,index);buffer=buffer.slice(index+1);line(value);}
 });
 child.stderr.on('data',bytes=>{errorBytes+=bytes.length;if(errorBytes>256)fail(Error('Process observer diagnostics exceeded limit'));});
 child.on('close',(code,signal)=>{
  closedResolve();clearTimeout(timer);
  if(failed)return;
  if(code!==0||signal||phase!=='exited'||buffer||errorBytes){fail(Error('Process observer did not confirm exit'));return;}
  done=true;
  exitResolve({boot_id:identity.boot_id,worker_id:identity.worker_id,method:'pidfd',processes:{worker:{...identity.processes.worker,observation:'exited'},guardian:null}});
 });
 return ready;
}
module.exports={preparePidfdExit};
