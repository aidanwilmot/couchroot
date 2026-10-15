'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),crypto=require('node:crypto'),{spawn,spawnSync}=require('node:child_process'),{once}=require('node:events');
const {hash}=require('../research/autonomous-root/service/policy');
const {fenceCommand,recoveryCommand}=require('../research/autonomous-root/service/bootstrap-recovery');
const enabled=process.platform==='linux'&&process.env.COUCHROOT_REHEARSAL==='1'&&process.getuid()===0;
const pause=()=>new Promise(r=>setTimeout(r,20));
function fixture(){
 const id=crypto.randomBytes(8).toString('hex').repeat(2),d='/opt/couchroot-bootstrap-'+id,f='/opt/couchroot-bootstrap-fence-'+id,tmp=fs.mkdtempSync(os.tmpdir()+'/bootstrap-fence-');
 const record={id,directory:d,scope:d+'/state',unit:'couchroot-bootstrap-'+id+'.service',fence:f,boot_id:fs.readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim(),worker_sha256:hash('worker'),launcher_sha256:hash('launcher'),token_sha256:hash('token')};
 // Substitute only systemd inspection; filesystem, flock, /proc and shell are real.
 fs.writeFileSync(tmp+'/systemctl','#!/bin/sh\ncase "$*" in\n"show -p MainPID "*) echo MainPID=${TEST_PID:-0};;\n"show -p ControlGroup "*) echo ControlGroup=;;\n"show -p LoadState "*) if test -n "$TEST_FAILED"; then echo LoadState=loaded; else echo LoadState=not-found; fi;;\n"show -p ActiveState "*) if test -n "$TEST_FAILED" && test ! -e "$TEST_FAILED/reset"; then echo ActiveState=failed; else echo ActiveState=inactive; fi;;\n"stop --no-block "*) exit 0;;\n"reset-failed "*) touch "$TEST_FAILED/reset";;\n*) exit 1;;\nesac\n',{mode:0o700});
 const run=(command,env={})=>spawnSync('/bin/sh',['-c',command.replaceAll('PATH=/usr/bin:/bin','PATH='+tmp+':/usr/bin:/bin')],{encoding:'utf8',env:{...process.env,...env},timeout:5000});
 const stage=()=>{for(const p of [d,d+'/code',d+'/state',d+'/state/.jobs'])fs.mkdirSync(p,{mode:0o700});for(const [name,bytes,mode] of [['code/worker','worker',0o500],['state/launcher','launcher',0o400],['state/token','token',0o600],['state/.jobs/lock','',0o600]])fs.writeFileSync(d+'/'+name,bytes,{mode});};
 const clean=()=>{for(const p of [d,f,tmp])fs.rmSync(p,{recursive:true,force:true});};return {record,d,f,tmp,run,stage,clean};
}
test('real launch fence excludes recovery while launch runs, then seals against a late launch',{skip:!enabled,timeout:10000},async()=>{
 const x=fixture();let child;
 try{
  child=spawn('/bin/sh',['-c',fenceCommand(x.record,'touch '+x.tmp+'/entered\nsleep 0.4\n')],{stdio:['ignore','ignore','pipe']});const ended=once(child,'exit');
  for(let n=0;!fs.existsSync(x.tmp+'/entered')&&n<100;n++)await pause();assert(fs.existsSync(x.tmp+'/entered'));
  assert.notEqual(x.run(recoveryCommand(x.record)).status,0);assert(!fs.existsSync(x.f+'/sealed'));
  await ended;assert.equal(child.exitCode,0);
  const result=x.run(recoveryCommand(x.record));assert.equal(result.status,0,result.stderr);assert.equal(result.stdout,'BOOTSTRAP-RECONCILED\n');
  assert.notEqual(x.run(fenceCommand(x.record,'touch '+x.tmp+'/replayed\n')).status,0);assert(!fs.existsSync(x.tmp+'/replayed'));
 }finally{if(child&&child.exitCode===null){child.kill('SIGTERM');await once(child,'exit');}x.clean();}
});
test('recovery before SDK launch seals it without creating a bootstrap scope',{skip:!enabled},()=>{const x=fixture();try{
 assert.equal(x.run(recoveryCommand(x.record)).status,0);assert(!fs.existsSync(x.d));
 assert.notEqual(x.run(fenceCommand(x.record,'mkdir '+x.d+'\n')).status,0);assert(!fs.existsSync(x.d));
}finally{x.clean();}});
test('partial exact staging and lost cleanup replies converge without launch replay',{skip:!enabled},()=>{const x=fixture();try{
 x.stage();fs.unlinkSync(x.d+'/state/launcher');
 let r=x.run(recoveryCommand(x.record));assert.equal(r.status,0,r.stderr);assert(!fs.existsSync(x.d));
 r=x.run(recoveryCommand(x.record));assert.equal(r.status,0,r.stderr);assert.equal(r.stdout,'BOOTSTRAP-RECONCILED\n');assert(fs.existsSync(x.f+'/sealed'));
}finally{x.clean();}});
test('drift, foreign files, links and live unit ownership preserve all remaining bytes',{skip:!enabled},()=>{
 for(const mode of ['drift','foreign','symlink','hardlink','live']){const x=fixture();try{
  x.stage();if(mode==='drift')fs.writeFileSync(x.d+'/code/worker','changed');
  if(mode==='foreign')fs.writeFileSync(x.d+'/unknown','foreign');
  if(mode==='symlink'){fs.unlinkSync(x.d+'/state/token');fs.symlinkSync(x.tmp+'/outside',x.d+'/state/token');fs.writeFileSync(x.tmp+'/outside','token');}
  if(mode==='hardlink')fs.linkSync(x.d+'/state/token',x.tmp+'/token-alias');
  const before=fs.readFileSync(x.d+'/code/worker');const r=x.run(recoveryCommand(x.record),mode==='live'?{TEST_PID:'12345'}:{});assert.notEqual(r.status,0,mode);assert.deepEqual(fs.readFileSync(x.d+'/code/worker'),before);assert(fs.existsSync(x.d+'/state/launcher'));
 }finally{x.clean();}}
});
test('foreign fence ownership and unsafe lock files refuse before cleanup',{skip:!enabled},()=>{
 for(const mode of ['directory','symlink','nonempty']){const x=fixture();try{
  x.stage();fs.mkdirSync(x.f,{mode:mode==='directory'?0o755:0o700});
  if(mode==='symlink')fs.symlinkSync(x.d+'/state/token',x.f+'/lock');
  if(mode==='nonempty')fs.writeFileSync(x.f+'/lock','x',{mode:0o600});
  assert.notEqual(x.run(recoveryCommand(x.record)).status,0);assert(fs.existsSync(x.d+'/code/worker'));
 }finally{x.clean();}}
});

test('failed unit with no processes is reset before retirement; live ownership still refuses',{skip:!enabled},()=>{const x=fixture();try{
 x.stage();const env={TEST_FAILED:x.tmp};let r=x.run(recoveryCommand(x.record),{...env,TEST_PID:'12345'});assert.notEqual(r.status,0);assert(!fs.existsSync(x.tmp+'/reset'));assert(fs.existsSync(x.d+'/code/worker'));
 r=x.run(recoveryCommand(x.record),env);assert.equal(r.status,0,r.stderr);assert(fs.existsSync(x.tmp+'/reset'));assert(!fs.existsSync(x.d));
}finally{x.clean();}});
