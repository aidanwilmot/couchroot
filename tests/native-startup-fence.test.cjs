'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),crypto=require('node:crypto'),{spawn,spawnSync}=require('node:child_process'),{once}=require('node:events');
const {fenceCommand}=require('../research/autonomous-root/service/launch-fence');
const linux={skip:process.platform!=='linux'||process.env.COUCHROOT_REHEARSAL!=='1'||process.getuid()!==0};
function fixture(){const id=crypto.randomBytes(16).toString('hex'),fence='/opt/couchroot-startup-fence-'+id,tmp=fs.mkdtempSync(os.tmpdir()+'/startup-fence-'),r={id,fence,boot_id:fs.readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim()};
 const command=(body,seal=false)=>fenceCommand(r,body,{kind:'startup',seal}),run=(body,seal=false)=>spawnSync('/bin/sh',['-c',command(body,seal)],{encoding:'utf8',timeout:3000});
 return {r,tmp,command,run,clean:()=>{fs.rmSync(fence,{recursive:true,force:true});fs.rmSync(tmp,{recursive:true,force:true});}};
}
test('startup retirement cannot overtake its launch and a sealed attempt cannot launch again',linux,async()=>{
 const f=fixture();let child;try{
  child=spawn('/bin/sh',['-c',f.command('touch '+f.tmp+'/entered\nsleep 0.3\n')]);const exited=once(child,'exit');
  for(let i=0;i<100&&!fs.existsSync(f.tmp+'/entered');i++)await new Promise(r=>setTimeout(r,10));assert(fs.existsSync(f.tmp+'/entered'));
  assert.notEqual(f.run('printf RETIRED',true).status,0);assert(!fs.existsSync(f.r.fence+'/sealed'));
  await exited;assert.equal(child.exitCode,0);
  assert.equal(f.run('printf RETIRED',true).stdout,'RETIRED');assert.equal(fs.readFileSync(f.r.fence+'/sealed','utf8'),f.r.id+'\n');
  assert.notEqual(f.run('touch '+f.tmp+'/replayed\n').status,0);assert(!fs.existsSync(f.tmp+'/replayed'));
  assert.equal(f.run('printf RETIRED',true).stdout,'RETIRED');
 }finally{if(child&&child.exitCode===null){child.kill('SIGTERM');await once(child,'exit');}f.clean();}
});
test('an unsubmitted delayed startup is fenced before retirement inspection',linux,()=>{
 const f=fixture();try{assert.equal(f.run('printf EMPTY',true).stdout,'EMPTY');assert(!fs.existsSync(f.r.fence+'/started'));
  assert.notEqual(f.run('touch '+f.tmp+'/late').status,0);assert(!fs.existsSync(f.tmp+'/late'));
 }finally{f.clean();}
});
test('startup fences refuse a mismatched kind or foreign path before command creation',()=>{
 const id='a'.repeat(32),boot_id='00000000-0000-0000-0000-000000000001',r={id,boot_id,fence:'/opt/couchroot-startup-fence-'+id};
 assert.throws(()=>fenceCommand(r,'true'));
 assert.throws(()=>fenceCommand({...r,fence:'/tmp/foreign'},'true',{kind:'startup'}));
 assert.throws(()=>fenceCommand(r,'true',{kind:'anything'}));
 assert.match(fenceCommand(r,'true',{kind:'startup'}),/flock -n 9/);
});
