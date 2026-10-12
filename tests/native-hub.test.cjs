'use strict';
const {test}=require('node:test');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
test('native Hub remote state, bounded persistence, async launch and admission guards',()=>{
 execFileSync('sh',['native-hub/test.sh'],{cwd:path.join(__dirname,'..'),stdio:'pipe'});
});
const assert=require('node:assert/strict');
const {convert}=require('../native-hub/import-web-state.cjs');
test('native migration preserves favorites, order, empty Home, clock and startup selection',()=>{
 const apps=[{id:'test.second',name:'Second'},{id:'test.first',name:'First'}];
 const exportData={'minimal-hub.shortcuts.v1':JSON.stringify({version:1,apps}),'minimal-hub.layout.v1':'compact','minimal-hub.clock.v1':'24h','minimal-hub.start.v1':'first','minimal-hub.selection.v1':'test.first'};
 const before=JSON.stringify(exportData);
 assert.equal(convert(exportData),'COUCHROOT1 1 2 1 1\ntest.second\tSecond\ntest.first\tFirst\n');
 assert.equal(JSON.stringify(exportData),before);
 assert.equal(convert({'minimal-hub.shortcuts.v1':'{"version":1,"apps":[]}'}),'COUCHROOT1 0 0 0 0\n');
});
test('native migration refuses data loss and malformed entries',()=>{
 const input=apps=>({'minimal-hub.shortcuts.v1':JSON.stringify({version:1,apps})});
 assert.throws(()=>convert(input(Array.from({length:129},(_,i)=>({id:'app.'+i,name:'App'})))),/refusing to truncate/);
 for(const apps of [[{id:'a',name:'Bad\nname'}],[{id:'a',name:'A'},{id:'a',name:'B'}],[{id:'com.samsung.tv.csfs',name:'Home'}],[{id:'a',name:'é'.repeat(61)}]]) assert.throws(()=>convert(input(apps)));
 assert.throws(()=>convert({'minimal-hub.clock.v1':'bad'}),/Unsupported clock/);
});
