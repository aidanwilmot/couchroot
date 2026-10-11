'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
function read(file,limit=65536){const stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.size>limit)throw Error('Invalid configuration file');return fs.readFileSync(file);}
function atomic(file,value){const tmp=file+'.new-'+crypto.randomBytes(8).toString('hex');const fd=fs.openSync(tmp,'wx',0o600);try{fs.writeFileSync(fd,JSON.stringify(value));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fs.renameSync(tmp,file);const parent=fs.openSync(path.dirname(file),'r');try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}}
function config(data){
 if(!data||data.schema!==1||!['qn90a','s90d'].includes(data.device)||typeof data.enabled!=='boolean'||!Number.isInteger(data.port)||data.port<1024||data.port>65535)throw Error('Invalid agent configuration');
 if(!/^[a-f0-9]{64}$/.test(data.client_sha256)||!data.firmware||!data.hashes||!Object.keys(data.hashes).length)throw Error('Missing identity guards');
 for(const p of Object.keys(data.hashes))if(!['/usr/bin/dotnet','/usr/bin/dotnet-launcher','/usr/sbin/sdbd-tarlauncher'].includes(p)||!/^[a-f0-9]{64}$/.test(data.hashes[p]))throw Error('Invalid firmware guard');
 if(!data.hashes['/usr/bin/dotnet']||!data.hashes['/usr/sbin/sdbd-tarlauncher'])throw Error('Missing launcher guards');
 return data;
}
function verifyFirmware(c){
 if(!read('/etc/prd_info.ini').toString().split(/\r?\n/).includes('Version='+c.firmware+';'))throw Error('Firmware mismatch');
}
function sdkRuntimeGuard(c){
 config(c);
 // Some TV package labels cannot stat System::Tools. Check the same pinned
 // bytes as SDK, before executing dotnet or the archive launcher; never skip it.
 return Object.keys(c.hashes).sort().map(p=>"test \"$(sha256sum '"+p+"' | cut -d ' ' -f 1)\" = '"+c.hashes[p]+"' || { echo 'Runtime hash mismatch: "+p+"'; exit 74; }").join('\n')+'\n';
}
function validateRequest(v){
 if(!v||Object.keys(v).some(k=>!['id','command','timeout_ms'].includes(k))||!/^[-a-zA-Z0-9]{16,64}$/.test(v.id)||typeof v.command!=='string'||!v.command.trim()||Buffer.byteLength(v.command)>16384||v.command.includes('\0')||!Number.isInteger(v.timeout_ms)||v.timeout_ms<100||v.timeout_ms>25000)throw Error('Invalid command request');
 return v;
}
class Journal{
 constructor(file){this.file=file;this.rows=fs.existsSync(file)?JSON.parse(read(file,262144)):[];if(!Array.isArray(this.rows)||this.rows.length>1000)throw Error('Invalid command journal');}
 begin(v){validateRequest(v);if(this.rows.some(r=>r.id===v.id))throw Error('Request already submitted; inspect outcome, do not replay');if(this.rows.length>=1000)throw Error('Command journal full; archive during maintenance');this.rows.push({id:v.id,sha256:hash(v.command),state:'submitted',at:Date.now()});atomic(this.file,this.rows);}
 finish(id,result){const r=this.rows.find(r=>r.id===id);r.state='completed';r.exit_code=result.exit_code;r.timed_out=result.timed_out;atomic(this.file,this.rows);}
}
module.exports={read,atomic,hash,config,verifyFirmware,sdkRuntimeGuard,validateRequest,Journal};
