"""Bounded native collector trial, with a TV-side rollback timer and private journal.

This deliberately does not change deployment defaults or boot integration.
Run: python3 -m tvsetup.native_trial --device qn90a --binary /absolute/collector-arm
Recover an interrupted run: python3 -m tvsetup.native_trial --device qn90a --recover RUN
"""

import argparse
import json
from pathlib import Path
import re
import time

from .common import PRIVATE, STATE, Refused, atomic_json, lock, read_json, sha, safe_id
from .engine import pending, run_id
from .nas import NAS
from .site import binding, configured_profile, load_site
from .telemetry import DATA, drain
from .transport import Q, Transport, hash_guard


def properties(unit):
    return f"systemctl show {Q(unit)} -p MainPID -p ActiveState -p SubState -p Result -p ExecMainStatus\n"


def stop_units(*units):
    return "".join(
        f'if test "$(systemctl show {Q(u)} -p LoadState --value)" != not-found; then\n'
        f"  systemctl stop {Q(u)}\n"
        f'  if test "$(systemctl show {Q(u)} -p ActiveState --value)" = failed; then systemctl reset-failed {Q(u)}; fi\n'
        "fi\n"
        for u in units
    )


def restore_script(data):
    # Package context preserves credential isolation. App launching runs in a
    # separate User-labeled unit ordered after successful marker restoration.
    return f"""#!/bin/sh
set -eu
test -r {DATA}/config.json
if test "${{1:-}}" = --probe; then
    mv {data}/restore-test {data}/restore-tested
    exit 0
fi
if test -f {data}/managed-enabled; then
    test ! -e {DATA}/enabled
    mv {data}/managed-enabled {DATA}/enabled
fi
test -f {DATA}/enabled
echo restored > {data}/restored
"""


def receiver(nas, device):
    path = (
        nas.base
        + "/custom-plugins.d/s90d-data/"
        + ("latest.json" if device == "s90d" else device + ".json")
    )
    # No credential reads or NAS mutations. Keep full proc snapshots out of output.
    code = (
        "import json,time; d=json.load(open(" + repr(path) + ")); "
        'keys=("device","boot","session","seq","uptime","received_at",'
        '"collector_cpu_seconds","collector_rss_bytes","metrics"); '
        'print(json.dumps({**{k:d.get(k) for k in keys},"age":time.time()-d["received_at"]}))'
    )
    return json.loads(nas.remote("python3 -c " + Q(code)))


def stage(tv, doc, folder, binary):
    code, data, staging = (doc[k] for k in ("code", "data", "staging"))
    restore = folder / "restore.sh"
    restore.write_text(restore_script(data))
    doc["restore_sha256"] = sha(restore.read_bytes())
    atomic_json(folder / "journal.json", doc)
    tv.sdk(f"test ! -e {staging}\nmkdir {staging}")
    tv.push(binary, staging + "/collector")
    tv.push(restore, staging + "/restore.sh")
    script = hash_guard(staging + "/collector", doc["binary_sha256"]) + hash_guard(
        staging + "/restore.sh", doc["restore_sha256"]
    )
    script += f"""
test ! -e {code}
test ! -e {data}
test -f {DATA}/enabled
test ! -L {DATA}/enabled
test ! -L {DATA}/config.json
mkdir -m 755 {code}
mkdir -m 700 {data}
chown 5001:100 {data}
chsmack -a User::Pkg::MiniTelemetry {data}
cp {staging}/collector {code}/collector
cp {staging}/restore.sh {code}/restore.sh
chmod 555 {code}/collector {code}/restore.sh {code}
chsmack -a User::Pkg::MiniTelemetry {code}
chsmack -a User::Pkg::MiniTelemetry {code}/collector
chsmack -a User::Pkg::MiniTelemetry {code}/restore.sh
cp -p {DATA}/config.json {data}/config.json
cp -p {DATA}/enabled {data}/enabled
cp -p {DATA}/enabled {data}/restore-test
for f in config.json enabled restore-test; do chsmack -a User::Pkg::MiniTelemetry {data}/$f; done
systemd-run --unit={doc["unit"]}-check -p User=5001 -p Group=100 -p SmackProcessLabel=User::Pkg::MiniTelemetry -p BindReadOnlyPaths={code} -p RuntimeMaxSec=8s -p RemainAfterExit=yes {code}/collector --check-config --root {data}
systemd-run --unit={doc["unit"]}-probe --on-active=2s --timer-property=AccuracySec=1s -p User=5001 -p Group=100 -p SmackProcessLabel=User::Pkg::MiniTelemetry -p BindReadOnlyPaths={code} /bin/sh {code}/restore.sh --probe
sleep 4
test "$(systemctl show {doc["unit"]}-check.service -p ExecMainStatus --value)" = 0
test "$(systemctl show {doc["unit"]}-check.service -p SubState --value)" = exited
test -f {data}/restore-tested
systemctl stop {doc["unit"]}-check.service {doc["unit"]}-probe.timer
sha256sum {DATA}/enabled {DATA}/config.json
echo PREFLIGHT_PASSED
"""
    output = tv.root(script)
    if "PREFLIGHT_PASSED" not in output:
        raise Refused("Native trial preflight failed; inspect private evidence")
    hashes = dict(
        (path, digest)
        for digest, path in re.findall(r"(?m)^([a-f0-9]{64})  (/\S+)$", output)
    )
    if DATA + "/enabled" not in hashes or DATA + "/config.json" not in hashes:
        raise Refused("Missing pairing/marker readback")
    doc["before_hashes"] = hashes
    doc["phase"] = "prepared"
    atomic_json(folder / "journal.json", doc)


def start(tv, doc, folder):
    code, data, unit = (doc[k] for k in ("code", "data", "unit"))
    script = hash_guard(code + "/collector", doc["binary_sha256"]) + hash_guard(
        code + "/restore.sh", doc["restore_sha256"]
    )
    script += "".join(
        hash_guard(path, digest) for path, digest in doc["before_hashes"].items()
    )
    script += (
        f"""
systemd-run --unit={unit}-restore --on-active=179s --timer-property=AccuracySec=1s -p User=5001 -p Group=100 -p SmackProcessLabel=User::Pkg::MiniTelemetry -p BindReadOnlyPaths={code} -p Type=oneshot -p RemainAfterExit=yes -p TimeoutStartSec=20s /bin/sh {code}/restore.sh
systemd-run --unit={unit}-relaunch --on-active=180s --timer-property=AccuracySec=1s -p User=5001 -p Group=100 -p SmackProcessLabel=User -p Type=oneshot -p RemainAfterExit=yes -p TimeoutStartSec=20s -p Requires={unit}-restore.service -p After={unit}-restore.service -p 'Environment=DBUS_SESSION_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/5001-user/bus XDG_RUNTIME_DIR=/run/user/5001' /bin/sh -c '/usr/bin/app_launcher -k MiniHub001.Hub || true; /usr/bin/app_launcher -s MiniHub001.Hub'
test "$(systemctl show {unit}-relaunch.timer -p ActiveState --value)" = active
mv {DATA}/enabled {data}/managed-enabled
"""
        + drain(doc["runtime"])
        + f"""
systemd-run --unit={unit} -p User=5001 -p Group=100 -p SmackProcessLabel=User::Pkg::MiniTelemetry -p BindReadOnlyPaths={code} -p RuntimeMaxSec=120s -p TimeoutStopSec=4s {code}/collector --root {data} --runtime {doc["runtime"]} --run-for 110
sleep 1
{properties(unit + ".service")}
"""
    )
    doc["phase"] = "starting"
    atomic_json(folder / "journal.json", doc)
    out = tv.root(script)
    match = re.search(r"(?m)^MainPID=(\d+)$", out)
    if not match or int(match[1]) <= 0 or "ActiveState=active" not in out:
        raise Refused("Native collector did not remain active; recover this trial")
    doc["native_pid"] = int(match[1])
    doc["phase"] = "running"
    atomic_json(folder / "journal.json", doc)


def restore(tv, doc, folder):
    unit, code, data = (doc[k] for k in ("unit", "code", "data"))
    doc["phase"] = "restoring"
    atomic_json(folder / "journal.json", doc)
    # Run restoration through its existing system unit, not the host process lifetime.
    # Keep the watchdog armed until readback succeeds.
    out = tv.root(
        hash_guard(code + "/restore.sh", doc["restore_sha256"])
        + stop_units(unit + ".service")
        + f"""
systemctl start {unit}-relaunch.service
test -f {DATA}/enabled
test ! -e {data}/managed-enabled
test -f {data}/restored
echo RESTORED
"""
    )
    if "RESTORED" not in out:
        raise Refused("Restoration incomplete; watchdog remains armed")


def cleanup(tv, doc, folder):
    unit, code, data, staging = (doc[k] for k in ("unit", "code", "data", "staging"))
    script = "".join(
        hash_guard(path, digest) for path, digest in doc["before_hashes"].items()
    )
    for name, digest in [
        ("collector", doc["binary_sha256"]),
        ("restore.sh", doc["restore_sha256"]),
    ]:
        script += (
            f"if test -e {code}/{name}; then\n"
            + hash_guard(code + "/" + name, digest)
            + "fi\n"
        )
    script += stop_units(
        *(
            unit + suffix
            for suffix in (
                "-restore.timer",
                "-relaunch.timer",
                "-restore.service",
                "-relaunch.service",
                ".service",
            )
        )
    )
    script += f"""
test ! -e {data}/managed-enabled
rm -f {code}/collector {code}/restore.sh
if test -d {code}; then rmdir {code}; fi
rm -f {data}/config.json {data}/enabled {data}/restore-tested {data}/restored
if test -d {data}; then rmdir {data}; fi
rm -f {staging}/collector {staging}/restore.sh
if test -d {staging}; then rmdir {staging}; fi
echo CLEANUP_PASSED
"""
    doc["phase"] = "cleaning"
    atomic_json(folder / "journal.json", doc)
    if "CLEANUP_PASSED" not in tv.root(script):
        raise Refused("Cleanup incomplete")
    doc["phase"] = "rolled-back"
    atomic_json(folder / "journal.json", doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("qn90a", "s90d"), required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--binary", type=Path)
    group.add_argument("--recover")
    group.add_argument("--resume")
    parser.add_argument(
        "--watchdog",
        action="store_true",
        help="Let the TV-side timers restore the managed worker instead of restoring from the host",
    )
    args = parser.parse_args()
    site = load_site()
    device = args.device
    with lock(STATE / (device + ".lock")):
        if args.recover or args.resume:
            identity = args.recover or args.resume
            safe_id(identity)
            folder = STATE / "runs" / identity
            doc = read_json(folder / "journal.json")
            if (
                not doc
                or doc.get("scope") != "native-collector-trial"
                or doc["device"] != device
                or doc["target_binding"] != binding(site, device)
            ):
                raise Refused("Trial recovery identity mismatch")
            allowed = (
                ("prepared",)
                if args.resume
                else (
                    "starting",
                    "running",
                    "awaiting-restore",
                    "restoring",
                    "cleaning",
                )
            )
            if doc["phase"] not in allowed:
                raise Refused(
                    "Inspect this preparation/cleanup state before recovery; do not replay trial mutations"
                )
        else:
            if pending(STATE, device):
                raise Refused("Resolve the pending setup/trial before starting another")
            binary = args.binary.resolve()
            header = binary.read_bytes()[:20] if binary.is_file() else b""
            if (
                len(header) < 20
                or header[:6] != b"\x7fELF\x01\x01"
                or header[18:20] != b"\x28\x00"
            ):
                raise Refused("Expected a little-endian ARM 32-bit ELF build")
            identity = run_id()
            folder = STATE / "runs" / identity
            suffix = identity.replace("T", "t").replace("Z", "z")
            doc = dict(
                schema=1,
                scope="native-collector-trial",
                device=device,
                run=identity,
                target_binding=binding(site, device),
                phase="preparing",
                binary_sha256=sha(binary.read_bytes()),
                code="/opt/minimal-native-trial-" + suffix,
                data=DATA + "/native-trial-" + suffix,
                staging="/home/owner/share/tmp/sdk_tools/native-trial-" + suffix,
                unit="minimal-native-trial-" + suffix,
                runtime="/tmp/minimal-telemetry-" + device,
                watchdog_test=args.watchdog,
            )
            atomic_json(folder / "journal.json", doc)
        print(
            json.dumps(dict(run=doc["run"], device=device, phase=doc["phase"])),
            flush=True,
        )
        tv = Transport(configured_profile(device, site), folder / "transport")
        nas = NAS(folder / "nas", site["nas"])
        if args.recover and doc["phase"] == "cleaning":
            cleanup(tv, doc, folder)
            print("Trial cleanup complete", flush=True)
            return
        if not args.recover:
            doc["receiver_before"] = receiver(nas, device)
            atomic_json(folder / "journal.json", doc)
            if not args.resume:
                stage(tv, doc, folder, binary)
            print("Preflight passed; starting timed native handoff", flush=True)
            start(tv, doc, folder)
            samples = []
            for _ in range(8):
                time.sleep(10)
                value = receiver(nas, device)
                if (
                    value["session"] != doc["receiver_before"]["session"]
                    and value["age"] < 20
                ):
                    samples.append(value)
                if len(samples) == 1:
                    print("Receiver accepted the native session", flush=True)
            doc["native_samples"] = samples
            atomic_json(folder / "journal.json", doc)
            if len({s["seq"] for s in samples}) < 3:
                raise Refused("Native ingestion did not advance; recover the trial")
            pid = doc["native_pid"]
            output = tv.root(f"""
test "$(systemctl show {doc["unit"]}.service -p MainPID --value)" = {pid}
printf 'NATIVE_PROCESS_BEGIN\\n'
readlink /proc/{pid}/exe
awk '/^(Name|PPid|Uid|Gid|VmRSS|VmSize):/ {{print}}' /proc/{pid}/status
cat /proc/{pid}/attr/current
grep {Q(doc["code"])} /proc/{pid}/mountinfo
if grep -E 'libcoreclr|libhostfxr|libhostpolicy|/dotnet/' /proc/{pid}/maps; then exit 7; fi
echo NO_MANAGED_RUNTIME
cat {doc["runtime"]}/status.json
printf '\\nNATIVE_PROCESS_END\\n'
""")
            match = re.search(
                r"NATIVE_PROCESS_BEGIN\n(.*?)\nNATIVE_PROCESS_END", output, re.S
            )
            if not match:
                raise Refused("Native process readback incomplete")
            status = json.loads(match[1].splitlines()[-1])
            if (
                status.get("implementation") != "native"
                or status["pid"] != pid
                or status["failures"] != 0
                or any(s["session"] != status["session"] for s in samples)
            ):
                raise Refused("Receiver samples do not match a healthy native process")
            doc["native_process"] = match[1]
            doc["native_status"] = status
            atomic_json(folder / "journal.json", doc)
        watchdog = bool(doc.get("watchdog_test")) and not args.recover
        if watchdog:
            doc["phase"] = "awaiting-restore"
            atomic_json(folder / "journal.json", doc)
            print("Waiting for TV-side watchdog restoration", flush=True)
        else:
            restore(tv, doc, folder)
        native_sessions = {s["session"] for s in doc.get("native_samples", [])}
        for _ in range(12 if watchdog else 6):
            time.sleep(10)
            value = receiver(nas, device)
            if (
                value["session"] not in native_sessions
                and value["age"] < 20
                and value["uptime"] > doc["receiver_before"]["uptime"]
            ):
                doc["receiver_restored"] = value
                atomic_json(folder / "journal.json", doc)
                break
        else:
            raise Refused(
                "Managed ingestion has not resumed; retain rollback evidence and investigate"
            )
        if watchdog:
            out = tv.root(
                f"test -f {doc['data']}/restored\n"
                + properties(doc["unit"] + "-relaunch.service")
            )
            if "Result=success" not in out or "ExecMainStatus=0" not in out:
                raise Refused("Watchdog launch unit did not complete successfully")
            doc["watchdog_verified"] = True
            atomic_json(folder / "journal.json", doc)
        cleanup(tv, doc, folder)
        samples = doc.get("native_samples", [])
        print(
            json.dumps(
                dict(
                    device=device,
                    run=doc["run"],
                    phase=doc["phase"],
                    accepted_samples=len(samples),
                    native_rss_bytes=[
                        min(s["collector_rss_bytes"] for s in samples),
                        max(s["collector_rss_bytes"] for s in samples),
                    ]
                    if samples
                    else [],
                    managed_restored=True,
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
