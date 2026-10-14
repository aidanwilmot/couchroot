const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm'),crypto=require('node:crypto'),{EventEmitter}=require('node:events'),{createRequire}=require('node:module');
const file=path.resolve(__dirname,'../research/autonomous-root/service/retirement-session.js'),real=createRequire(file);
async function fixture(mode,run){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'retirement-session-'));
 let instance,launches=0,readiness=0,launchOptions,closed=0;
 class Server{
  constructor(options){this.options=options;this._server=new EventEmitter();instance=this;}
  start(callback){if(mode==='listen-error')queueMicrotask(()=>this._server.emit('error',Error('bind failed')));else callback();}
  listeningPort(){return 12345;}
  connect(){this._conn={_socket:{destroy(){}}};this.options.onConnect(this._conn);}
  close(){closed++;this._conn=null;}
 }
 const module={exports:{}};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),{module,process,Buffer,setTimeout,clearTimeout,require:name=>{
  if(name==='./vendor/root-agent')return {RootAgentServer:Server};
  if(name==='./retirement-launch')return {submitRetirement:async options=>{
   launches++;launchOptions=options;
   const token=fs.readFileSync(options.tokenFile);
   assert.equal(token.length,44);assert.equal(crypto.createHash('sha256').update(token).digest('hex'),options.tokenSha256);
   assert.equal(Buffer.from(token.toString(),'base64').equals(instance.options.secret),true);
   assert.equal(fs.statSync(options.tokenFile).mode&0o777,0o600);
   assert.equal(fs.statSync(path.dirname(options.tokenFile)).mode&0o777,0o700);
   fs.writeFileSync(path.join(directory,'retirement-launch.pending'),'owned');
   if(mode==='launch-error')throw Error('unknown launch');
   instance.connect();if(mode==='disconnect')instance._conn=null;
   return {phase:'submitted'};
  }};
  if(name==='./retirement-readiness')return {readyRetirement:async options=>{readiness++;assert.equal(options.channel,instance);assert.equal(options.record.phase,'submitted');if(mode==='ready-error')throw Error('identity mismatch');return {record:{phase:'ready'},provider:{identity:'verified'}};}};
  return real(name);
 }});
 try{await run({directory,open:()=>module.exports.openRetirementSession({journalDirectory:directory}),state:()=>({instance,launches,readiness,launchOptions,closed})});}finally{fs.rmSync(directory,{recursive:true,force:true});}
}
test('session binds private token to loopback listener and requires readiness before returning',()=>fixture('ok',async f=>{
 const session=await f.open(),s=f.state();assert.equal(s.instance.options.bindHost,'127.0.0.1');assert.equal(s.launchOptions.port,12345);assert.equal(s.readiness,1);assert.equal(session.record.phase,'ready');assert.equal(session.provider.identity,'verified');assert.equal(session.channel,undefined);
 session.closeTransport();session.closeTransport();assert.equal(f.state().closed,1);assert.equal(fs.existsSync(s.launchOptions.tokenFile),true);assert.equal(fs.existsSync(path.join(f.directory,'retirement-launch.pending')),true);
 await assert.rejects(f.open(),/reconciliation/);assert.equal(f.state().launches,1);
}));
test('uncertain launch and readiness retain token ownership but close transport',async()=>{
 for(const mode of ['launch-error','disconnect','ready-error'])await fixture(mode,async f=>{
  await assert.rejects(f.open(),e=>e.outcome==='unknown');const s=f.state();assert.equal(s.closed,1);assert.equal(fs.existsSync(s.launchOptions.tokenFile),true);assert.equal(s.readiness,mode==='ready-error'?1:0);
  await assert.rejects(f.open(),/reconciliation/);assert.equal(f.state().launches,1);
 });
});
test('listener failure before submission removes unused token and never launches',()=>fixture('listen-error',async f=>{
 await assert.rejects(f.open(),e=>e.outcome==='rejected');assert.equal(f.state().launches,0);assert.deepEqual(fs.readdirSync(f.directory),[]);
}));
test('existing pending ownership refuses allocation',()=>fixture('ok',async f=>{
 fs.writeFileSync(path.join(f.directory,'retirement-launch.pending'),'previous');await assert.rejects(f.open(),/reconciliation/);assert.equal(f.state().instance,undefined);assert.deepEqual(fs.readdirSync(f.directory),['retirement-launch.pending']);
}));
