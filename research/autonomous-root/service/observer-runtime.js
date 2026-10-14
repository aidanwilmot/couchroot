'use strict';
// Non-stopping service probe only. These callbacks require the held managed
// worker to stay alive; they are not a post-shutdown execution transport.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {prepareSupervisedExit}=require('./observer-controller');
const {inspectObserverUnit,retireObserverUnit}=require('./observer-unit');
const STATE='/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state';
function observerTransactionId(requestId){
 if(typeof requestId!=='string'||requestId.length<16||requestId.length>64||!/^[-a-zA-Z0-9]+$/.test(requestId))throw Error('Persistent observer request identity required');
 return crypto.createHash('sha256').update('observer-probe:'+requestId).digest('hex').slice(0,32);
}
function serviceCredentials(){
 const status=fs.readFileSync('/proc/self/status','utf8'),label=fs.readFileSync('/proc/self/attr/current','utf8').trim();
 const field=name=>{const rows=status.split('\n').filter(line=>line.startsWith(name+':'));if(rows.length!==1)throw Error('Service credential evidence unavailable');return rows[0].slice(name.length+1).trim();};
 const ids=name=>field(name).split(/\s+/).map(Number);
 const uids=ids('Uid'),gids=ids('Gid'),groups=ids('Groups').sort((a,b)=>a-b);
 const actual=process.getgroups().slice().sort((a,b)=>a-b);
 if(uids.length!==4||uids.some(id=>id!==5001)||gids.length!==4||gids.some(id=>id!==100)||process.getuid()!==5001||process.geteuid()!==5001||process.getgid()!==100||process.getegid()!==100||groups.length<1||groups.length>32||groups.some(id=>!Number.isInteger(id)||id<1||id>2147483647)||new Set(groups).size!==groups.length||!groups.includes(100)||JSON.stringify(groups)!==JSON.stringify(actual)||label!=='User::Pkg::MiniRoot01'||field('CapEff')!=='0000000000000000')throw Error('Service credentials do not match observer profile');
 return {uid:5001,gid:100,groups,label};
}
function journalDirectory(directory){
 if(directory!==STATE)throw Error('Invalid service observer state path');
 const flags=fs.constants.O_RDONLY|fs.constants.O_DIRECTORY|fs.constants.O_NOFOLLOW;
 const parent=fs.openSync(directory,flags);
 try{
  const st=fs.fstatSync(parent),now=fs.lstatSync(directory);
  if(!st.isDirectory()||st.uid!==process.geteuid()||(st.mode&0o7777)!==0o700||now.dev!==st.dev||now.ino!==st.ino)throw Error('Invalid observer state directory');
  const target=path.join(directory,'observer-launches');let created=false;
  try{fs.mkdirSync(target,{mode:0o700});created=true;}catch(e){if(e.code!=='EEXIST')throw e;}
  const fd=fs.openSync(target,flags);
  try{
   const child=fs.fstatSync(fd);
   if(!child.isDirectory()||child.uid!==process.geteuid())throw Error('Invalid observer journal owner');
   if(created)fs.fchmodSync(fd,0o700);
   if((fs.fstatSync(fd).mode&0o7777)!==0o700)throw Error('Invalid observer journal permissions');
   fs.fsyncSync(fd);fs.fsyncSync(parent);
  }finally{fs.closeSync(fd);}
  return target;
 }finally{fs.closeSync(parent);}
}
async function prepareRuntimeObserver({directory,requestId,staged,bound,confirm,execute}){
 const id=observerTransactionId(requestId),credentials=serviceCredentials();
 const journal=journalDirectory(directory);
 if(!bound||bound.processes.guardian)throw Error('Managed observer probe requires a single worker');
 const unitOptions=unit=>({unit,bootId:bound.boot_id,execute});
 return prepareSupervisedExit({device:'s90d',id,directory,journalDirectory:journal,credentials,
  binary:staged.binary,sha256:staged.sha256,manifestSha256:staged.manifest_sha256,bound,confirm,execute,
  inspectUnit:unit=>inspectObserverUnit(unitOptions(unit)),retireUnit:unit=>retireObserverUnit(unitOptions(unit))});
}
module.exports={prepareRuntimeObserver,observerTransactionId,serviceCredentials};
