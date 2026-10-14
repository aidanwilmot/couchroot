'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRequire}=require('node:module');
const runtime=require('../research/autonomous-root/service/observer-runtime');
test('observer transaction is stable and rejects absent or ambiguous request identities',()=>{
 const id=runtime.observerTransactionId('request-identity-001');assert.match(id,/^[a-f0-9]{32}$/);
 assert.equal(runtime.observerTransactionId('request-identity-001'),id);assert.notEqual(runtime.observerTransactionId('request-identity-002'),id);
 for(const input of [undefined,'','short','x'.repeat(65),'request-identity-001\n','request/identity-001'])assert.throws(()=>runtime.observerTransactionId(input));
});
function credentials(change={}){
 const source=path.resolve(__dirname,'../research/autonomous-root/service/observer-runtime.js'),real=createRequire(source),module={exports:{}};
 const defaults={Uid:'5001 5001 5001 5001',Gid:'100 100 100 100',Groups:'29 100 201',CapEff:'0000000000000000',...change};
 const fakeFs={readFileSync:file=>file.endsWith('status')?['Uid','Gid','Groups','CapEff'].map(key=>key+':\t'+defaults[key]).join('\n'):(change.label||'User::Pkg::MiniRoot01')};
 const fakeProcess={getuid:()=>5001,geteuid:()=>5001,getgid:()=>100,getegid:()=>100,getgroups:()=>change.actualGroups||[100,29,201]};
 vm.runInNewContext(fs.readFileSync(source,'utf8'),{module,process:fakeProcess,require:name=>name==='fs'?fakeFs:real(name)});
 return module.exports.serviceCredentials();
}
test('observer captures exact service identity and refuses altered credentials',()=>{
 assert.equal(JSON.stringify(credentials()),JSON.stringify({uid:5001,gid:100,groups:[29,100,201],label:'User::Pkg::MiniRoot01'}));
 for(const change of [{Uid:'5001 0 5001 5001'},{Gid:'100 100 100 0'},{CapEff:'0000000000000001'},{Groups:'29 100 100'},{Groups:'0 100 201'},{label:'User'},{actualGroups:[100,201]},{Groups:'29 201'},{Uid:'5001'}])assert.throws(()=>credentials(change));
});
