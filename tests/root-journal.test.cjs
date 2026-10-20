const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path'),crypto=require('crypto');
const {Journal,hash}=require('../agent/service/policy');
const req=id=>({id:id||crypto.randomUUID(),command:'id',timeout_ms:1000});
const rows=n=>Array.from({length:n},(_,i)=>({id:crypto.randomUUID(),sha256:hash('id'),state:'completed',at:i,exit_code:0,timed_out:false}));
function fixture(n,fn){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'tv-journal-'));try{const file=dir+'/requests.json',seed=rows(n);fs.writeFileSync(file,JSON.stringify(seed));fn({dir,file,seed});}finally{fs.rmSync(dir,{recursive:true,force:true});}}
test('full journal archives before next command, retains uncertain requests and rejects archived replay after restart',()=>fixture(1000,({file,seed})=>{
 seed[0].state='submitted';delete seed[0].exit_code;delete seed[0].timed_out;fs.writeFileSync(file,JSON.stringify(seed));
 const j=new Journal(file),v=req();j.begin(v);assert.equal(j.rows.length,102);assert.ok(j.rows.some(r=>r.id===seed[0].id));
 const names=fs.readdirSync(file+'.archives');assert.equal(names.length,1);const bytes=fs.readFileSync(path.join(file+'.archives',names[0]));assert.equal(hash(bytes)+'.json',names[0]);assert.deepEqual(JSON.parse(bytes),seed);
 assert.throws(()=>j.begin(req(seed[1].id)),/already submitted/);const restarted=new Journal(file);assert.throws(()=>restarted.begin(req(seed[1].id)),/already submitted/);assert.throws(()=>restarted.begin(v),/already submitted/);
 assert.equal(bytes.toString().includes('"command"'),false);
}));
test('manual archive requires matching snapshot, and never discards pending records',()=>fixture(200,({file,seed})=>{
 const j=new Journal(file),before=j.digest();assert.throws(()=>j.archive('0'.repeat(64)),/changed/);assert.equal(j.rows.length,200);
 const result=j.archive(before);assert.equal(result.archived_entries,100);assert.equal(result.retained_entries,100);assert.equal(result.sha256,j.digest());assert.equal(j.archive(j.digest()).archived_entries,0);
 const pending=seed.map(r=>({...r,state:'submitted'}));fs.writeFileSync(file,JSON.stringify(pending));const p=new Journal(file);assert.equal(p.archive().archived_entries,0);assert.equal(p.rows.length,200);
}));
test('full unfinished journal refuses new command without removing evidence',()=>fixture(1000,({file,seed})=>{
 fs.writeFileSync(file,JSON.stringify(seed.map(r=>({...r,state:'submitted'}))));const j=new Journal(file);assert.throws(()=>j.begin(req()),/unfinished/);assert.equal(j.rows.length,1000);assert.equal(fs.existsSync(file+'.archives'),false);
}));
test('interrupted active-file replacement keeps complete archive and fails closed until restart',()=>fixture(1000,({file,seed})=>{
 const j=new Journal(file),rename=fs.renameSync;fs.renameSync=(a,b)=>{if(b===file)throw Error('injected rename failure');return rename(a,b);};
 try{assert.throws(()=>j.begin(req()),/rename failure/);assert.throws(()=>j.begin(req()),/storage failed/);}finally{fs.renameSync=rename;}
 assert.equal(JSON.parse(fs.readFileSync(file)).length,1000);assert.equal(fs.readdirSync(file+'.archives').length,1);
 const recovered=new Journal(file);assert.throws(()=>recovered.begin(req(seed[0].id)),/already submitted/);recovered.begin(req());assert.equal(recovered.rows.length,101);
}));
test('archive corruption and symlink destinations fail closed',()=>fixture(200,({dir,file})=>{
 const j=new Journal(file);j.archive();const archive=path.join(file+'.archives',fs.readdirSync(file+'.archives')[0]);fs.writeFileSync(archive,'[]');assert.throws(()=>new Journal(file),/hash mismatch/);
 fs.rmSync(file+'.archives',{recursive:true});fs.mkdirSync(dir+'/elsewhere');fs.symlinkSync(dir+'/elsewhere',file+'.archives');assert.throws(()=>new Journal(file),/archive directory/);
}));
test('legacy SDK maintenance archives retain replay protection',()=>fixture(1,({dir,file})=>{
 const old=rows(2);old[0].state='submitted';fs.writeFileSync(dir+'/requests.archive-previous-maintenance.json',JSON.stringify(old));const j=new Journal(file);for(const r of old)assert.throws(()=>j.begin(req(r.id)),/already submitted/);
}));

test('dangling journal and archive symlinks are refused rather than treated as missing',()=>fixture(1,({dir,file})=>{
 fs.symlinkSync(dir+'/missing',file+'.archives');assert.throws(()=>new Journal(file),/archive directory/);fs.unlinkSync(file+'.archives');fs.unlinkSync(file);fs.symlinkSync(dir+'/missing',file);assert.throws(()=>new Journal(file),/configuration file/);
}));
