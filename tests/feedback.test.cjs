const {test}=require('node:test');const assert=require('node:assert/strict');const {create,KEY}=require('../web/feedback.js');
test('sound is deferred, coalesced and rate-limited without delaying navigation',()=>{
 let time=100;const tasks=[],calls=[];
 const f=create({tvaudiocontrol:{playSound:t=>calls.push(t)}},{getItem:()=>null},task=>tasks.push(task),()=>time);
 f.play('MOVE');f.play('MOVE');assert.deepEqual(calls,[]);assert.equal(tasks.length,1);tasks.shift()();assert.deepEqual(calls,['MOVE']);
 time=120;f.play('MOVE');tasks.shift()();assert.deepEqual(calls,['MOVE']);
 f.play('MOVE');f.play('SELECT');tasks.shift()();assert.deepEqual(calls,['MOVE','SELECT']);
});
test('sound preference persists and storage failure leaves it unchanged',()=>{
 let value=null;const storage={getItem:()=>value,setItem:(key,next)=>{assert.equal(key,KEY);value=next;}};
 const f=create(null,storage);assert.equal(f.toggle(),false);assert.equal(create(null,storage).enabled(),false);
 storage.setItem=()=>{throw Error('Full');};assert.throws(()=>f.toggle(),/Full/);assert.equal(f.enabled(),false);
});
test('Web Audio avoids loading the unused native sound extension at startup',()=>{
 let probes=0;
 const f=create({get tvaudiocontrol(){probes++;throw Error('Native extension should stay unloaded');}}, {getItem:()=>null}, ()=>{}, ()=>0, ()=>({}));
 f.play('MOVE');assert.equal(probes,0);assert.equal(f.enabled(),true);
});
test('unsupported audio, failed native sound and disabling queued sound remain harmless',()=>{
 let calls=0;const tasks=[];const storage={getItem:()=>null,setItem(){}};
 const f=create({tvaudiocontrol:{playSound(){calls++;throw Error('Denied');}}},storage,t=>tasks.push(t));
 f.play('MOVE');assert.doesNotThrow(()=>tasks.shift()());f.play('MOVE');assert.equal(calls,1);assert.equal(tasks.length,0);
 const silent=create({get tvaudiocontrol(){throw Error('Denied');}},storage);assert.doesNotThrow(()=>silent.play('SELECT'));
 const toggle=create({tvaudiocontrol:{playSound(){assert.fail();}}},storage,t=>tasks.push(t));toggle.play('MOVE');toggle.toggle();tasks.shift()();
});

test('mellow tone uses a short low-gain sine envelope after scheduling and disconnects',()=>{
 const tasks=[],events=[];let oscillator;
 const context={state:'running',currentTime:10,destination:{},createOscillator(){oscillator={frequency:{setValueAtTime:(...v)=>events.push(['pitch',...v])},connect(){},start:t=>events.push(['start',t]),stop:t=>events.push(['stop',t]),disconnect:()=>events.push(['disconnect'])};return oscillator;},createGain(){return {gain:{setValueAtTime:(...v)=>events.push(['initial',...v]),linearRampToValueAtTime:(...v)=>events.push(['attack',...v]),exponentialRampToValueAtTime:(...v)=>events.push(['decay',...v])},connect(){},disconnect(){}};}};
 const f=create(null,{getItem:()=>null},t=>tasks.push(t),()=>100,()=>context);f.play('MOVE');assert.equal(events.length,0);tasks.shift()();assert.equal(oscillator.type,'sine');assert.deepEqual(events[0],['pitch',320,10]);assert.deepEqual(events[2],['attack',.035,10.012]);assert.deepEqual(events[3],['decay',.0001,10.075]);oscillator.onended();assert.deepEqual(events.at(-1),['disconnect']);
});
