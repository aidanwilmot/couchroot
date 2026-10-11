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
  if(req.method==='GET'&&req.url==='/v1/requests'){reply(200,{requests:journal.rows});return;}
  if(req.method!=='POST'||!['/v1/exec','/v1/disable','/v1/enable'].includes(req.url)){reply(404,{error:'Unknown operation'});return;}
  if(busy){reply(409,{error:'Another administrative operation is in progress'});return;}
  busy=true;
  try{
   let bytes=0,chunks=[];for await(const part of req){bytes+=part.length;if(bytes>20000){reply(413,{error:'Request too large'});req.destroy();return;}chunks.push(part);}
   const value=JSON.parse(Buffer.concat(chunks).toString()||'{}');
   if(req.url==='/v1/disable'||req.url==='/v1/enable'){
    if(Object.keys(value).length)throw Error('This operation takes no arguments');
    const enabled=req.url==='/v1/enable';setEnabled(enabled);if(enabled)agent.start();else agent.stop();reply(200,{enabled});return;
   }
   validateRequest(value);
   if(!agent.status().connected){reply(503,{error:'Root agent unavailable'});return;}
   journal.begin(value);
   const result=await agent.execute(value.command,value.timeout_ms);
   journal.finish(value.id,result);reply(200,Object.assign({id:value.id},result));
  }catch(e){reply(409,{error:'Operation rejected or outcome uncertain; inspect request journal',detail:String(e.message).slice(0,200)});}
  finally{busy=false;}
 });
 server.timeout=35000;server.headersTimeout=10000;server.maxHeadersCount=20;server.maxConnections=8;
 server.on('clientError',(_,socket)=>socket.destroy());server.on('tlsClientError',()=>{});
 return server;
}
module.exports={createApi};
