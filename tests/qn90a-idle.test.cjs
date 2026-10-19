const {test}=require('node:test');
const assert=require('node:assert/strict');
const install=require('../web/qn90a-idle.js');
function rig(launch) {
  let now=0, next=0; const timers=new Map(), listeners={};
  const doc={hidden:false,addEventListener(name,fn){listeners[name]=fn;}};
  const calls=[];
  const state=install(doc,{application:{launch(id,ok,fail){calls.push(id);if(launch)launch(ok,fail);else ok();}}}, {
    now:()=>now,setTimeout(fn,delay){timers.set(++next,{at:now+delay,fn});return next;},clearTimeout(id){timers.delete(id);}
  });
  function advance(ms) {now+=ms; for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}}
  return {doc,state,calls,advance,event:name=>listeners[name](),timers};
}
test('QN90A dashboard waits a full five minutes and launches once',()=>{
  const r=rig();r.advance(299999);assert.equal(r.calls.length,0);r.advance(1);
  assert.deepEqual(r.calls,['MiniSave01.Saver']);r.advance(900000);assert.equal(r.calls.length,1);
});
test('remote input restarts idle; hidden dashboard never launches over another app',()=>{
  const r=rig();r.advance(290000);r.event('keydown');r.advance(299999);assert.equal(r.calls.length,0);
  r.doc.hidden=true;r.event('visibilitychange');r.advance(7200000);assert.equal(r.calls.length,0);
  r.doc.hidden=false;r.event('visibilitychange');r.advance(299999);assert.equal(r.calls.length,0);
  r.advance(1);assert.equal(r.calls.length,1);
});
test('return from saver arms a fresh five minutes and a stale timer cannot launch',()=>{
  const r=rig(),stale=[...r.timers.values()][0].fn;
  r.doc.hidden=true;r.event('visibilitychange');r.advance(300000);stale();assert.equal(r.calls.length,0);
  r.doc.hidden=false;r.event('visibilitychange');r.advance(300000);assert.equal(r.calls.length,1);
  r.doc.hidden=true;r.event('visibilitychange');r.doc.hidden=false;r.event('visibilitychange');
  r.advance(299999);assert.equal(r.calls.length,1);r.advance(1);assert.equal(r.calls.length,2);
});
test('failed saver launch leaves dashboard usable and does not loop',()=>{
  const r=rig((ok,fail)=>fail({name:'NotFoundError'}));r.advance(300000);
  assert.equal(r.state.error,'NotFoundError');r.advance(7200000);assert.equal(r.calls.length,1);
  r.event('keyup');r.advance(300000);assert.equal(r.calls.length,2);
});
