'use strict';
// Read-only, single-attempt query. Caller chooses a live, authenticated executor;
// a disconnected worker cannot establish its former supervisor's unit state.
const UNIT=/^couchroot-observer-[a-f0-9]{32}\.service$/;
const BOOT=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
async function inspectObserverUnit({unit,bootId,execute}){
 if(typeof unit!=='string'||unit.length!==59||!UNIT.test(unit)||typeof bootId!=='string'||bootId.length!==36||!BOOT.test(bootId)||typeof execute!=='function')throw Error('Invalid observer unit inspection');
 const guard='test "$(cat /proc/sys/kernel/random/boot_id)" = '+bootId+'\n';
 const command='set -eu\nPATH=/usr/bin:/bin\nexport PATH\nexport DBUS_SYSTEM_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/0-system/bus\n'+guard+
  'systemctl show --property=Id,LoadState,ActiveState,SubState,MainPID,ExecMainCode,ExecMainStatus,ExecMainStartTimestampMonotonic '+unit+'\n'+guard;
 const r=await execute(command,5000);
 if(!r||r.exit_code!==0||r.timed_out||r.stderr||typeof r.stdout!=='string'||r.stdout.length>2048)throw Error('Observer unit inspection unavailable');
 const values=Object.create(null);
 for(const line of r.stdout.trimEnd().split('\n')){
  const i=line.indexOf('=');if(i<1||Object.prototype.hasOwnProperty.call(values,line.slice(0,i)))throw Error('Malformed observer unit inspection');
  values[line.slice(0,i)]=line.slice(i+1);
 }
 if(Object.keys(values).sort().join('|')!=='ActiveState|ExecMainCode|ExecMainStartTimestampMonotonic|ExecMainStatus|Id|LoadState|MainPID|SubState'||values.Id!==unit||values.LoadState!=='loaded'||!['inactive','active','activating','deactivating','failed','reloading'].includes(values.ActiveState))throw Error('Observer unit identity unavailable');
 for(const key of ['MainPID','ExecMainCode','ExecMainStatus','ExecMainStartTimestampMonotonic'])if(!/^(0|[1-9][0-9]{0,19})$/.test(values[key])||values[key].trim()!==values[key])throw Error('Invalid observer unit counter');
 const pid=Number(values.MainPID),code=Number(values.ExecMainCode),status=Number(values.ExecMainStatus);
 if(!Number.isSafeInteger(pid)||pid>2147483647||code>3||status>255)throw Error('Observer unit counter exceeds limits');
 return {unit,boot_id:bootId,active_state:values.ActiveState,sub_state:values.SubState,main_pid:pid,exec_code:code,exec_status:status,started_monotonic:values.ExecMainStartTimestampMonotonic};
}
async function retireObserverUnit(options){
 const {unit,bootId,execute}=options;
 const evidence=await inspectObserverUnit(options);
 require('./observer-controller').terminationEvidence(evidence,{unit,boot_id:bootId});
 const guard='test "$(cat /proc/sys/kernel/random/boot_id)" = '+bootId+'\n';
 const command='set -eu\nPATH=/usr/bin:/bin\nexport PATH\nexport DBUS_SYSTEM_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/0-system/bus\n'+guard+
  'systemctl stop '+unit+'\n'+
  'state=$(systemctl show -p LoadState '+unit+')\n'+
  'if test "$state" = LoadState=loaded; then test "$(systemctl show -p ActiveState '+unit+')" = ActiveState=inactive; test "$(systemctl show -p MainPID '+unit+')" = MainPID=0; else test "$state" = LoadState=not-found; fi\n'+guard+
  'printf "OBSERVER-UNIT-RETIRED\\n"\n';
 const r=await execute(command,5000);
 if(!r||r.exit_code!==0||r.timed_out||r.stdout!=='OBSERVER-UNIT-RETIRED\n')throw Error('Observer unit retirement requires reconciliation');
 return {unit,boot_id:bootId,retired:true};
}
module.exports={inspectObserverUnit,retireObserverUnit};
