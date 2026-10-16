'use strict';
// Synthetic historical boot for the disposable restart integration fixture.
// This rewrites only fixture receipts before the system under test restarts;
// subsequent assertions require those original receipts to remain immutable.
const fs=require('node:fs'),crypto=require('node:crypto');
const hash=v=>crypto.createHash('sha256').update(v).digest('hex');
function historicalBoot(state,id){
 const read=name=>JSON.parse(fs.readFileSync(state+'/'+name));
 const write=(name,value)=>fs.writeFileSync(state+'/'+name,JSON.stringify(value),{mode:0o600});
 const boot='00000000-0000-0000-0000-000000000001',record=read(id+'.production.json');
 if(record.boot_id===boot)throw Error('Synthetic historical boot must differ');
 const stat=fs.readFileSync('/proc/self/stat','utf8'),ticks=stat.slice(stat.lastIndexOf(')')+2).trim().split(/\s+/)[19];
 const source={...record.source,boot_id:boot,processes:{worker:{pid:process.pid,start_ticks:ticks},guardian:null}};
 const snapshot=read(id+'.retained-snapshot.json');snapshot.source=source;delete snapshot.sha256;snapshot.sha256=hash(JSON.stringify(snapshot));write(id+'.retained-snapshot.json',snapshot);
 const installation=read(id+'.state-install.json');installation.source=source;installation.snapshot_sha256=snapshot.sha256;write(id+'.state-install.json',installation);
 record.source=source;record.boot_id=boot;record.state_receipt_sha256=hash(JSON.stringify(installation));record.worker_identity.boot_id=boot;
 record.worker_identity.processes.guardian={pid:process.pid,start_ticks:ticks};write(id+'.production.json',record);
 const activation=read(id+'.activation.json');activation.boot_id=boot;activation.worker_identity=record.worker_identity;activation.readiness_sha256=hash(JSON.stringify(record));write(id+'.activation.json',activation);
 const selection=read('selection.json'),entry=selection.history.find(e=>e.id===id);entry.readiness_sha256=activation.readiness_sha256;entry.state_sha256=record.state_receipt_sha256;write('selection.json',selection);
 const journal=JSON.parse(fs.readFileSync(record.scope+'/.jobs/guardian'));journal.boot_id=boot;journal.pid=process.pid;journal.process_start=ticks;fs.writeFileSync(record.scope+'/.jobs/guardian',JSON.stringify(journal));
 const live=record.scope+'/.jobs/native-live-00001.json',job=JSON.parse(fs.readFileSync(live));job.boot_id=boot;fs.writeFileSync(live,JSON.stringify(job));
 return {record,committed:fs.readFileSync(state+'/'+id+'.production.json'),activation:fs.readFileSync(state+'/'+id+'.activation.json'),history:JSON.stringify(selection.history)};
}
module.exports={historicalBoot};
