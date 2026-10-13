'use strict';
const https=require('https'),crypto=require('crypto');
const {hash,validateRequest}=require('./policy');
function createApi(options){
 const {credentials,clientPin,agent,journal,setEnabled}=options;
 let busy=false;
 const server=https.createServer(Object.assign({},credentials,{requestCert:true,rejectUnauthorized:true,minVersion:'TLSv1.2'}),async(req,res)=>{
  const cert=req.socket.getPeerCertificate();
  const reply=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store','Connection':'close'});res.end(JSON.stringify(value));};
  if(!req.socket.authorized||!cert.raw||!crypto.timingSafeEqual(Buffer.from(hash(cert.raw),'hex'),Buffer.from(clientPin,'hex'))){reply(403,{error:'Client not enrolled'});return;}
  if(req.headers.origin){reply(403,{error:'Browser access is disabled'});return;}
  if(req.method==='GET'&&req.url==='/v1/status'){reply(200,agent.status());return;}
  if(req.method==='GET'&&req.url==='/v1/requests'){reply(200,{requests:journal.rows,sha256:journal.digest()});return;}
  if(req.method!=='POST'||!['/v1/exec','/v1/disable','/v1/enable','/v1/journal/archive','/v1/op','/v1/files/read','/v1/files/write'].includes(req.url)){reply(404,{error:'Unknown operation'});return;}
  if(busy){reply(409,{error:'Another administrative operation is in progress'});return;}
  busy=true;
  let submitted=false,operationId=null;
  try{
   let bytes=0,chunks=[];for await(const part of req){bytes+=part.length;if(bytes>(req.url==='/v1/files/write'?1048576:20000)){reply(413,{error:'Request too large'});req.destroy();return;}chunks.push(part);}
   const raw=Buffer.concat(chunks);
   const value=JSON.parse(req.url==='/v1/files/write'?(req.headers['x-operation']||'{}'):(raw.toString()||'{}'));
   if(['/v1/op','/v1/files/read','/v1/files/write'].includes(req.url)){
    const operation=value.operation;
    if(!/^[-a-zA-Z0-9]{16,64}$/.test(value.id)||!operation||typeof operation!=='object'||Array.isArray(operation))throw Error('Invalid operation envelope');
    const allowed=['file.open','file.begin','file.read','file.write','file.status','file.commit','file.close','job.start','job.status','job.output','job.cancel','job.forget','app.exec','helper.prepare','helper.release'];
    if(!allowed.includes(operation.op))throw Error('Unknown worker operation');
    if(req.url==='/v1/files/write'){
     if(operation.op!=='file.write'||!raw.length)throw Error('Expected file.write bytes');
     operation.data=raw.toString('base64');
    }else if(operation.op==='file.write')throw Error('Use the binary upload endpoint');
    if((req.url==='/v1/files/read')!==(operation.op==='file.read'))throw Error('Use the binary download endpoint');
    if(!agent.status().connected||agent.status().worker_ready===false){reply(503,{outcome:'rejected',error:'Root agent unavailable'});return;}
    const readOnly=['file.read','file.status','job.status','job.output'].includes(operation.op);
    if(!readOnly){journal.begin({id:value.id,command:'operation:'+hash(JSON.stringify(operation)),timeout_ms:25000});operationId=value.id;}
    submitted=true;
    const result=await agent.operation(operation);
    if(operationId)journal.finish(operationId,{exit_code:Number.isInteger(result.exit_code)?result.exit_code:0,timed_out:!!result.timed_out});
    if(operation.op==='file.read'){
     const data=Buffer.from(result.data,'base64');
     if(data.length>1048576||hash(data)!==result.sha256)throw Error('Invalid worker chunk digest');
     res.writeHead(200,{'Content-Type':'application/octet-stream','Cache-Control':'no-store','Connection':'close','X-SHA256':result.sha256,'X-Offset':String(result.offset)});res.end(data);
    }else reply(200,{id:value.id,...result});
    return;
   }
   if(req.url==='/v1/disable'||req.url==='/v1/enable'){
    if(Object.keys(value).length)throw Error('This operation takes no arguments');
    const enabled=req.url==='/v1/enable';setEnabled(enabled);if(enabled)agent.start();else agent.stop();reply(200,{enabled});return;
   }
   if(req.url==='/v1/journal/archive'){
    if(!value||Object.keys(value).length!==1||!/^[a-f0-9]{64}$/.test(value.expected_sha256))throw Error('Expected journal digest required');
    reply(200,journal.archive(value.expected_sha256));return;
   }
   validateRequest(value);
   if(!agent.status().connected||agent.status().worker_ready===false){reply(503,{error:'Root agent unavailable'});return;}
   journal.begin(value);
   submitted=true;
   const result=await agent.execute(value.command,value.timeout_ms);
   journal.finish(value.id,result);reply(200,Object.assign({id:value.id},result));
  }catch(e){
   let outcome=submitted?(e.outcome||'unknown'):'rejected';
   if(operationId && ['failed','rejected'].includes(e.outcome)){try{journal.finish(operationId,{exit_code:1,timed_out:false});}catch(_){outcome='unknown';}}
   reply(409,{outcome,error:outcome==='unknown'?'Command outcome unknown; inspect request journal':'Operation '+outcome,detail:String(e.message).slice(0,200)});
  }
  finally{busy=false;}
 });
 server.timeout=35000;server.headersTimeout=10000;server.maxHeadersCount=20;server.maxConnections=8;
 server.on('clientError',(_,socket)=>socket.destroy());server.on('tlsClientError',()=>{});
 return server;
}
module.exports={createApi};
