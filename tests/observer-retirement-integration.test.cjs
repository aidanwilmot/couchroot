const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto'),{createRequire}=require('node:module'),{spawn}=require('node:child_process'),{once}=require('node:events');
const {RootAgentServer}=require('../research/autonomous-root/service/vendor/root-agent');
const {processIdentities}=require('../research/autonomous-root/service/worker-processes');
test('native retirement channel remains usable after the real managed source exits',{
 skip:process.platform!=='linux'||!process.env.COUCHROOT_PARITY_CONTAINER||!process.env.NATIVE_WORKER||!process.env.MANAGED_PARITY,timeout:20000
},async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'independent-retirement-')),children=[],servers=[];
 async function start(name,native){
  const dir=path.join(root,name);fs.mkdirSync(dir,{mode:0o700});const secret=crypto.randomBytes(32),token=path.join(dir,'token');fs.writeFileSync(token,secret.toString('base64'),{mode:0o600});
  let accept;const ready=new Promise(resolve=>{accept=resolve;}),server=new RootAgentServer({secret,onConnect:accept});servers.push(server);await new Promise(resolve=>server.start(resolve));
  let command,args,sha;
  if(native){const launcher=path.join(dir,'launcher');fs.copyFileSync('/bin/true',launcher);fs.chmodSync(launcher,0o600);sha=crypto.createHash('sha256').update(fs.readFileSync(launcher)).digest('hex');command=process.env.NATIVE_WORKER;args=['127.0.0.1',String(server.listeningPort()),token,dir,launcher,sha];}
  else{command='dotnet';args=[process.env.MANAGED_PARITY,'--parity-wire',String(server.listeningPort()),dir];}
  const child=spawn(command,args,{stdio:['ignore','ignore','pipe']}),ended=once(child,'exit');let stderr='';child.stderr.on('data',data=>{stderr=(stderr+data).slice(-8192);});children.push({child,ended});
  const peer=await Promise.race([ready,ended.then(()=>{throw Error(name+' exited early: '+stderr);})]);
  return {server,peer,child,ended,sha,dir,stderr:()=>stderr};
 }
 try{
  const managed=await start('managed',false),native=await start('native',true);
  // This host build stubs Smack and mount setup. Only that credential field is
  // normalized here; firmware profile/staging qualification is separate.
  assert.equal(native.peer.identity.smack,'host-test-without-Smack');native.peer.identity.smack='System';
  const source=processIdentities(await managed.server.operation({op:'status'}),managed.peer.identity.pid);
  const unit='couchroot-observer-'+'a'.repeat(32)+'.service',bound={unit,bootId:source.boot_id,sha256:'b'.repeat(64)};
  const sourceFile=path.resolve(__dirname,'../research/autonomous-root/service/observer-retirement.js'),real=createRequire(sourceFile),module={exports:{}};
  let commands=0;
  const unitOperations={
   inspectObserverUnit:async o=>{commands++;const r=await o.execute('printf inspected',1000);assert.equal(r.stdout,'inspected');return {unit:o.unit};},
   retireObserverUnit:async o=>{commands++;const r=await o.execute('printf retired',1000);assert.equal(r.stdout,'retired');return {unit:o.unit,boot_id:o.bootId,retired:true};}
  };
  vm.runInNewContext(fs.readFileSync(sourceFile,'utf8'),{module,process,require:name=>name==='./observer-unit'?unitOperations:real(name)});
  const id='a'.repeat(32),record={schema:1,id,phase:'submitted',device:'s90d',manifest_sha256:'b'.repeat(64),worker_sha256:'b'.repeat(64),launcher_sha256:native.sha,observer_sha256:bound.sha256,boot_id:source.boot_id,source,unit:'couchroot-retirement-'+id+'.service',directory:'/opt/couchroot-retirement-'+id,scope:'/opt/couchroot-retirement-'+id+'/state',token_file:'/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state/retirement-ABC123/token',token_sha256:'b'.repeat(64),port:12345};
  const journalDirectory=path.join(root,'journal');fs.mkdirSync(journalDirectory,{mode:0o700});
  fs.writeFileSync(path.join(journalDirectory,id+'.retirement.json'),JSON.stringify(record),{mode:0o600});fs.writeFileSync(path.join(journalDirectory,'retirement-launch.pending'),id+'\n',{mode:0o600});
  const readinessFile=path.resolve(__dirname,'../research/autonomous-root/service/retirement-readiness.js'),readinessRequire=createRequire(readinessFile),readinessModule={exports:{}};
  vm.runInNewContext(fs.readFileSync(readinessFile,'utf8'),{module:readinessModule,process,Buffer,require:name=>name==='./observer-retirement'?{...readinessRequire(name),createObserverRetirement:module.exports.createObserverRetirement}:readinessRequire(name)});
  const {provider}=await readinessModule.exports.readyRetirement({record,journalDirectory,channel:native.server,confirmSource:()=>managed.server.operation({op:'status'}),execute:async()=>({exit_code:0,stdout:`Id=${record.unit}\nLoadState=loaded\nActiveState=active\nSubState=running\nMainPID=${native.child.pid}\nExecMainCode=0\nExecMainStatus=0\nExecMainStartTimestampMonotonic=123\n`})});
  assert.equal(JSON.parse(fs.readFileSync(path.join(journalDirectory,id+'.retirement.json'))).phase,'ready');
  assert.notEqual(provider.identity.worker_id,source.worker_id);
  assert.deepEqual(await managed.server.shutdown(),{acknowledged:true,disconnected:true});assert.deepEqual(await managed.ended,[0,null],managed.stderr());
  await assert.rejects(managed.server.execute('must not execute',1000));
  assert.equal((await provider.inspectUnit(bound)).unit,unit);assert.equal((await provider.retireUnit(bound)).retired,true);assert.equal(commands,2);
  assert.deepEqual(await native.server.shutdown(),{acknowledged:true,disconnected:true});assert.deepEqual(await native.ended,[0,null],native.stderr());
  assert.equal(fs.existsSync(path.join(native.dir,'.jobs','guardian')),false);assert.equal(fs.existsSync(path.join(native.dir,'.views')),false);
  assert.doesNotMatch(native.stderr(),/AddressSanitizer|runtime error:|recovery incomplete/);
 }finally{
  for(const server of servers)server.close();
  for(const {child,ended} of children)if(child.exitCode===null&&child.signalCode===null){child.kill('SIGTERM');await ended;}
  fs.rmSync(root,{recursive:true,force:true});
 }
});
