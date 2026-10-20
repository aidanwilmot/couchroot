'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');

test('agent cleanup removes only its own staging and never the shared on-demand directory',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../agent/service/agent.js'),'utf8');
  const start=source.indexOf('  function clean() {');
  const end=source.indexOf('  function schedule() {',start);
  assert(start>=0 && end>start);
  const BASE='/home/owner/share/tmp/sdk_tools',stage=BASE+'/archive-root-fixture';
  const removed=[],unlinked=[];
  const context={BASE,stage,path,fs:{
    existsSync:()=>true,
    lstatSync:()=>({isDirectory:()=>true,isSymbolicLink:()=>false,isFile:()=>true}),
    readdirSync:()=>['operation.sh'],
    rmdirSync:p=>removed.push(p),
    unlinkSync:p=>unlinked.push(p),
  }};
  vm.runInNewContext(source.slice(start,end)+'\nclean();',context);
  assert(removed.includes(stage));
  assert(unlinked.includes(BASE+'/on-demand/archive-root-fixture.tar.gz'));
  assert(!removed.includes(BASE+'/on-demand'));
});
