'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
const {planInstallation}=require('../agent/service/retained-install'),{hash}=require('../agent/service/policy');
const linux={skip:process.platform!=='linux'||process.geteuid()!==0||process.env.COUCHROOT_PARITY_CONTAINER!=='1'};
for(const active of [null,'worker','guardian'])test('native state importer checks both old processes: '+active,linux,()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-upgrade-shell-')),boot='00000000-0000-0000-0000-000000000001',id='c'.repeat(32);
 const source={boot_id:boot,worker_id:'a'.repeat(32),processes:{worker:{pid:42001,start_ticks:'123'},guardian:{pid:42002,start_ticks:'122'}}};
 const records=Array.from({length:64},(_,i)=>{const name='retained-job-'+String(i).padStart(4,'0'),bytes=Buffer.from(JSON.stringify({id:name,state:'completed',boot_id:boot,exit_code:i}));return {name:name+'.json',size:bytes.length,sha256:hash(bytes),base64:bytes.toString('base64')};});
 const body={schema:1,implementation:'native-prototype',source,records},snapshot={...body,sha256:hash(JSON.stringify(body))};
 const plan=planInstallation({snapshot,id,manifestSha256:'b'.repeat(64)});
 fs.mkdirSync(root+'/opt',{mode:0o700});fs.mkdirSync(root+'/proc',{mode:0o700});fs.writeFileSync(root+'/boot',boot+'\n');
 if(active){const p=source.processes[active];fs.mkdirSync(root+'/proc/'+p.pid);fs.writeFileSync(root+'/proc/'+p.pid+'/stat',p.pid+' (worker) S '+Array(18).fill('0').join(' ')+' '+p.start_ticks+' 0\n');}
 const run=command=>spawnSync('/bin/sh',['-c',command.replaceAll('/opt',root+'/opt').replaceAll('/proc/sys/kernel/random/boot_id',root+'/boot').replace(/\/proc\/(42001|42002)\/stat/g,root+'/proc/$1/stat')],{encoding:'utf8'});
 try{
  const start=run(plan.begin);
  if(active){assert.notEqual(start.status,0);assert.equal(fs.existsSync(root+plan.record.directory),false);return;}
  assert.equal(start.status,0,start.stderr);
  for(const c of [...plan.copies,plan.commit,plan.verifyReady]){const r=run(c);assert.equal(r.status,0,r.stderr);}
  for(const r of records)assert.equal(hash(fs.readFileSync(root+plan.record.scope+'/.jobs/'+r.name)),r.sha256);
  assert.equal(plan.record.schema,2);
  assert.notEqual(run(plan.begin).status,0,'an existing destination is never blindly reused');
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
