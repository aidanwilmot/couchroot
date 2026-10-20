'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{EventEmitter}=require('node:events');
const {createRequire}=require('node:module');
const {validateReadiness,validateResourceInventory}=require('../agent/service/worker-readiness');
const BOOT='00000000-0000-0000-0000-000000000001',DIGEST='a'.repeat(64);
function managed(){return {boot_id:BOOT,uptime_seconds:3,worker_id:'b'.repeat(32),capabilities:['file-transfer-v1','binary-download-v1','binary-upload-v1','jobs-v1','app-profile-v1','helper-view-v1','native-app-launcher-v1'],app_launcher:{implementation:'native',sha256:DIGEST}};}
function native(){return {...managed(),implementation:'native-prototype',lifetime_mode:'production',lifetime_seconds:0,guardian_pid:42,capabilities:['prototype-production-files-v1','binary-upload-v1','binary-download-v1','prototype-app-exec-v1','prototype-jobs-v1','prototype-helper-lifecycle-v1','prototype-independent-launcher-v1','prototype-crash-guardian-v1','prototype-command-fault-diagnostics-v1'],app_launcher:{sha256:DIGEST,independently_staged:true}};}
function inventoried(){const info=managed();info.capabilities.push('resource-inventory-v1','worker-process-identity-v1');info.processes={worker:{pid:42,start_ticks:'123'},guardian:null};info.resources={schema:1,scope:'worker-owned',transfers:[],jobs:[],helpers:[]};return info;}
test('managed deployed shape and additive diagnostics remain compatible',()=>{
 const info=managed();info.extra='diagnostic';info.capabilities.push('future-diagnostic-v1');
 assert.equal(validateReadiness(info,{implementation:'managed',bootId:BOOT}),info);
 info.implementation='managed';assert.equal(validateReadiness(info,{implementation:'managed',bootId:BOOT,launcherSha256:DIGEST}),info);
});
test('wrong boot identities capabilities implementations and launchers cannot become ready',()=>{
 const cases=[v=>v.boot_id='00000000-0000-0000-0000-000000000002',v=>v.uptime_seconds=-1,v=>v.uptime_seconds=NaN,
  v=>v.worker_id='not-a-worker',v=>v.capabilities.pop(),v=>v.capabilities.push(v.capabilities[0]),v=>v.implementation='native-prototype',
  v=>v.app_launcher.sha256='invalid',v=>v.app_launcher.implementation='managed',v=>v.capabilities=undefined];
 for(const change of cases){const info=managed();change(info);assert.throws(()=>validateReadiness(info,{implementation:'managed',bootId:BOOT}));}
 assert.throws(()=>validateReadiness(managed(),{implementation:'managed',bootId:BOOT,launcherSha256:'c'.repeat(64)}));
 assert.throws(()=>validateReadiness(managed(),{implementation:'managed',bootId:'not-a-boot'}));
});
test('native readiness requires pinned launcher and production lifetime',()=>{
 const expected={implementation:'native-prototype',bootId:BOOT,launcherSha256:DIGEST};
 assert.equal(validateReadiness(native(),expected).implementation,'native-prototype');
 for(const change of [v=>v.lifetime_seconds=300,v=>v.lifetime_mode='bounded',v=>v.guardian_pid=0,v=>v.app_launcher.independently_staged=false,v=>v.capabilities[0]='prototype-scoped-files-v1']){const info=native();change(info);assert.throws(()=>validateReadiness(info,expected));}
 assert.throws(()=>validateReadiness(native(),{implementation:'native-prototype',bootId:BOOT}));
 assert.throws(()=>validateReadiness(managed(),expected));
});
test('inventory requires explicit capability bounded identities and known shapes',()=>{
 const info=inventoried();assert.equal(validateResourceInventory(info),info.resources);
 const invalid=[v=>v.capabilities=v.capabilities.filter(c=>c!=='resource-inventory-v1'),v=>v.resources.scope='all',v=>v.resources.extra=true,
  v=>v.resources.jobs.push({id:'valid-job-identity',state:'running',monitor_finished:'false'}),
  v=>v.resources.transfers.push({id:'a'.repeat(32),direction:'other'}),
  v=>v.resources.helpers=Array(9).fill('a'.repeat(32)),v=>v.resources.helpers=['a'.repeat(32),'a'.repeat(32)],
  v=>v.resources.jobs=Array(17).fill({id:'valid-job-identity',state:'running',monitor_finished:false})];
 for(const change of invalid){const v=inventoried();change(v);assert.throws(()=>validateResourceInventory(v));}
 assert.throws(()=>validateResourceInventory(managed()));
});
