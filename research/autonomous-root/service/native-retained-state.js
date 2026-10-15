'use strict';
// Read a stopped production worker's records for managed rollback. No mutation.
const {hash}=require('./policy');
const {validateLaunch}=require('./production-readiness');
const {processIdentities}=require('./worker-processes');
const {validateRecord,parseManifest,sourceExitGuard}=require('./retained-state');
function check(ok){if(!ok)throw Error('Native rollback snapshot unavailable');}
function planNativeSnapshot(record,installation){
 check(record&&record.phase==='ready');const {worker_identity,unit_started_monotonic,...launch}=record;validateLaunch({...launch,phase:'submitted'});
 check(typeof unit_started_monotonic==='string'&&/^[1-9][0-9]{0,19}$/.test(unit_started_monotonic)&&unit_started_monotonic.trim()===unit_started_monotonic);
 check(worker_identity&&worker_identity.processes&&worker_identity.processes.guardian&&worker_identity.boot_id===record.boot_id);
 check(JSON.stringify(processIdentities({...worker_identity,implementation:'native-prototype',guardian_pid:worker_identity.processes.guardian.pid,capabilities:['worker-process-identity-v1']},worker_identity.processes.worker.pid))===JSON.stringify(worker_identity));
 check(Object.values(worker_identity.processes).every(p=>p.pid>1));
 check(installation&&installation.schema===1&&installation.phase==='ready'&&installation.id===record.id&&installation.directory===record.directory&&installation.scope===record.scope&&installation.manifest_sha256===record.manifest_sha256&&JSON.stringify(installation.source)===JSON.stringify(record.source)&&hash(JSON.stringify(installation))===record.state_receipt_sha256);
 check(typeof installation.installed_manifest_sha256==='string'&&installation.installed_manifest_sha256.length===64&&/^[a-f0-9]+$/.test(installation.installed_manifest_sha256));
 const root=record.scope+'/.jobs';
 const guard=sourceExitGuard(record.source)+Object.values(worker_identity.processes).map(p=>'if test -e /proc/'+p.pid+'/stat; then line=$(cat /proc/'+p.pid+'/stat); rest=${line##*) }; set -- $rest; test "$#" -ge 20; shift 19; test "$1" != '+p.start_ticks+'; fi\n').join('');
 const fileGuard=p=>'test -f '+p+'; test ! -L '+p+'; test "$(stat -c "%u:%h:%a" '+p+')" = 0:1:600\n';
 const prefix='set -eu\nPATH=/usr/bin:/bin\nexport PATH\n'+guard+
  [record.directory,record.scope,root].map(p=>'test -d '+p+'; test ! -L '+p+'; test "$(stat -c "%u:%a" '+p+')" = 0:700\n').join('')+
  fileGuard(root+'/lock')+'test "$(stat -c %s '+root+'/lock)" -eq 0\n'+fileGuard(root+'/.import-manifest')+'test "$(sha256sum '+root+'/.import-manifest | cut -d " " -f1)" = '+installation.installed_manifest_sha256+'\n'+
  'test ! -e '+root+'/guardian; test ! -L '+root+'/guardian\n';
 const manifest=prefix+'listing=$(find '+root+' -mindepth 1 -maxdepth 1 ! -name lock ! -name .import-manifest -print)\nif test -n "$listing"; then printf "%s\\n" "$listing" | (count=0; while IFS= read -r file; do\ncount=$((count+1)); test "$count" -le 64\nname=${file##*/}; id=${name%.json}; test "$name" != "$id"\ncase "$id" in *[!a-zA-Z0-9-]*) exit 1;; esac\ntest "${#id}" -ge 16; test "${#id}" -le 64\n'+fileGuard('"$file"')+'size=$(stat -c %s "$file"); test "$size" -ge 1; test "$size" -lt 2048\nsum=$(sha256sum "$file"); printf "%s %s %s\\n" "$name" "$size" "${sum%% *}"\ndone)\nfi\n'+guard+'printf "SNAPSHOT-END\\n"\n';
 return {root,guard,prefix,manifest,fileGuard};
}
async function snapshotNativeJobs({record,installation,execute}){
 check(typeof execute==='function');const plan=planNativeSnapshot(record,installation),started=process.hrtime();
 const run=async command=>{const r=await execute(command,5000),t=process.hrtime(started);check(t[0]*1000+t[1]/1000000<60000&&r&&r.exit_code===0&&!r.timed_out&&!r.stderr&&typeof r.stdout==='string'&&r.stdout.length<=12000);return r.stdout;};
 const before=parseManifest(await run(plan.manifest)),records=[];
 for(const entry of before){
  const file=plan.root+'/'+entry.name,command=plan.prefix+plan.fileGuard(file)+'test "$(stat -c %s '+file+')" -eq '+entry.size+'\ntest "$(sha256sum '+file+' | cut -d " " -f1)" = '+entry.sha256+'\nbase64 '+file+'\n'+plan.guard;
  const compact=(await run(command)).replace(/\n/g,'');check(/^[A-Za-z0-9+/]+={0,2}$/.test(compact));const bytes=Buffer.from(compact,'base64');check(bytes.toString('base64')===compact&&bytes.length===entry.size&&hash(bytes)===entry.sha256);validateRecord(entry.name,bytes);records.push({...entry,base64:compact});
 }
 check(JSON.stringify(parseManifest(await run(plan.manifest)))===JSON.stringify(before));
 const value={schema:1,implementation:'native-prototype',source:JSON.parse(JSON.stringify(record.worker_identity)),origin:{transaction_id:record.id,manifest_sha256:record.manifest_sha256,installation_sha256:record.state_receipt_sha256},records};
 return {...value,sha256:hash(JSON.stringify(value))};
}
module.exports={snapshotNativeJobs,planNativeSnapshot};
