'use strict';
const path=require('path'),{read,config,atomic}=require('./policy'),{Journal}=require('./policy'),{createAgent}=require('./agent'),{createApi}=require('./api');
const DATA='/opt/usr/home/owner/apps_rw/MiniRoot01/data';
let server,agent;
function start(){
 const c=config(JSON.parse(read(DATA+'/config.json')));
 agent=createAgent(c);
 server=createApi({credentials:{key:read(DATA+'/server-key.pem'),cert:read(DATA+'/server.pem'),ca:read(DATA+'/client.pem')},clientPin:c.client_sha256,agent,journal:new Journal(DATA+'/requests.json'),setEnabled:enabled=>{c.enabled=enabled;atomic(DATA+'/config.json',c);}});
 server.on('error',()=>{agent.stop();process.exitCode=1;});
 server.listen(c.port,'0.0.0.0',()=>{if(c.enabled)agent.start();});
}
function stop(){if(agent)agent.stop();if(server)server.close();}
process.on('SIGTERM',stop);process.on('SIGINT',stop);
try{start();}catch(_){console.error('Root agent configuration unavailable; service not started');process.exitCode=1;}
