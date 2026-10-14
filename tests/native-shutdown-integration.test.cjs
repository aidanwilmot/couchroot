const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto'),{spawn}=require('node:child_process'),{once}=require('node:events');
const {RootAgentServer}=require('../research/autonomous-root/service/vendor/root-agent');
const {processIdentities,observeProcesses,waitForProcessExit}=require('../research/autonomous-root/service/worker-processes');
test('ordinary native worker acknowledges shutdown and its guardian finishes cleanup',{
 skip:process.platform!=='linux'||!process.env.COUCHROOT_PARITY_CONTAINER||!process.env.NATIVE_WORKER,
 timeout:20000
},async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-stop-'));fs.chmodSync(root,0o700);
 const secret=crypto.randomBytes(32),token=path.join(root,'token'),launcher=path.join(root,'launcher-source');
 fs.writeFileSync(token,secret.toString('base64'),{mode:0o600});fs.copyFileSync('/bin/true',launcher);fs.chmodSync(launcher,0o600);
 const sha=crypto.createHash('sha256').update(fs.readFileSync(launcher)).digest('hex');
 let accept;const connected=new Promise(resolve=>{accept=resolve;}),server=new RootAgentServer({secret,onConnect:accept});
 let child,ended,stderr='';
 try{
  await new Promise(resolve=>server.start(resolve));
  child=spawn(process.env.NATIVE_WORKER,['127.0.0.1',String(server.listeningPort()),token,root,launcher,sha,'--production'],{stdio:['ignore','ignore','pipe']});
  ended=once(child,'exit');child.stderr.on('data',data=>{stderr=(stderr+data).slice(-8192);});
  const connection=await Promise.race([connected,ended.then(()=>{throw Error('Native worker exited before connecting: '+stderr);})]);
  const status=await server.operation({op:'status'}),bound=processIdentities(status,connection.identity.pid);
  assert.equal(bound.processes.guardian.pid,child.pid);assert.notEqual(bound.processes.worker.pid,child.pid);
  const before=observeProcesses(bound);assert.equal(before.processes.worker.observation,'present');assert.equal(before.processes.guardian.observation,'present');
  assert.deepEqual(await server.shutdown(),{acknowledged:true,disconnected:true});
  const exited=await waitForProcessExit(bound);assert.equal(exited.processes.worker.observation,'absent');assert.equal(exited.processes.guardian.observation,'absent');
  assert.deepEqual(await ended,[0,null],stderr);
  assert.equal(fs.existsSync(path.join(root,'.jobs','guardian')),false);
  assert.equal(fs.existsSync(path.join(root,'.views')),false);
  assert.doesNotMatch(stderr,/AddressSanitizer|runtime error:|recovery incomplete/);
 }finally{
  server.close();
  if(child&&child.exitCode===null&&child.signalCode===null){child.kill('SIGTERM');await ended;}
  fs.rmSync(root,{recursive:true,force:true});
 }
});
