"""Isolated, time-limited S90D Netdata benchmark; production telemetry stays active."""

import argparse
import json
from pathlib import Path
import re
import time
import ipaddress
import ssl
import urllib.request
import uuid

from .common import REPO, STATE, Refused, atomic_json, lock, read_json, sha, safe_id
from .engine import pending, run_id
from .native_trial import receiver, stop_units
from .nas import NAS
from .site import binding, configured_profile, load_site
from .transport import Transport, hash_guard

SOURCE = REPO / "tools/netdata-trial"


def configuration(code, ram):
    text = (
        (SOURCE / "netdata.conf.in")
        .read_text()
        .replace("@CODE@", code)
        .replace("@RAM@", ram)
    )
    enabled = {"/proc/stat", "/proc/meminfo", "/proc/diskstats", "/proc/uptime"}
    text += "\n[plugin:proc]\n    /proc/net/dev = yes\n"
    for name in read_json(SOURCE / "proc-modules.json"):
        text += "    " + name + " = " + ("yes" if name in enabled else "no") + "\n"
    return text


def validate_trial_paths(doc, folder):
    identity = folder.name
    safe_id(identity)
    expected = dict(
        run=identity,
        device="s90d",
        scope="netdata-native-trial",
        code="/opt/minimal-netdata-" + identity.lower(),
        ram="/tmp/minimal-netdata-" + identity.lower(),
        staging="/home/owner/share/tmp/sdk_tools/netdata-" + identity.lower(),
        unit="minimal-netdata-" + identity.lower(),
    )
    if any(doc.get(k) != v for k, v in expected.items()):
        raise Refused("Trial path/identity mismatch")
    required = {
        "netdata",
        "netdata.conf",
        "stream.conf",
        "exporting.conf",
        ".opt-out-from-anonymous-statistics",
    }
    if not required <= set(doc.get("files", {})) <= required | {"parent.crt"}:
        raise Refused("Unexpected trial files")
    if any(not re.fullmatch("[a-f0-9]{64}", v) for v in doc["files"].values()):
        raise Refused("Invalid trial file hash")


def cleanup(tv, doc, folder):
    validate_trial_paths(doc, folder)
    doc["phase"] = "cleaning"
    atomic_json(folder / "journal.json", doc)
    script = "".join("test ! -L " + doc[k] + "\n" for k in ("code", "staging", "ram"))
    script += stop_units(doc["unit"] + ".service", doc["unit"] + "-version.service")
    for name, digest in doc["files"].items():
        for prefix in (doc["code"], doc["staging"]):
            path = prefix + "/" + name
            script += (
                f"if test -e {path}; then\n"
                + hash_guard(path, digest)
                + f"rm {path}\nfi\n"
            )
    for path in (doc["code"], doc["staging"]):
        script += f"if test -d {path}; then rmdir {path}; fi\n"
    # Runtime is a uniquely named trial-owned directory on tmpfs; contains no pairing.
    ram = doc["ram"]
    script += f"test ! -L {ram}\nif test -d {ram}; then rm -rf -- {ram}; fi\n"
    script += "echo CLEANUP_PASSED\n"
    if "CLEANUP_PASSED" not in tv.root(script):
        raise Refused("Netdata trial cleanup incomplete")
    doc["phase"] = "rolled-back"
    atomic_json(folder / "journal.json", doc)


def sample(tv, doc):
    unit = doc["unit"] + ".service"
    # /proc stat fields follow the final ')', so process names cannot shift indexes.
    out = tv.root(f"""p=$(systemctl show {unit} -p MainPID --value)
test "$p" -gt 1
printf 'SAMPLE_TIME '; cat /proc/uptime
for n in "$p" $(pgrep -P "$p" || true); do
 echo "PID_BEGIN=$n"
 cat /proc/$n/stat
 sed -n '/^Uid:/p;/^VmRSS:/p;/^VmSwap:/p;/^Threads:/p;/^Cap/p' /proc/$n/status
awk '/^(Rss|Pss|Swap|SwapPss):/ {{a[$1]+=$2}} END {{for(k in a) print \"SMAPS_\"k,a[k]}}' /proc/$n/smaps
cat /proc/$n/limits
 if test -r /proc/$n/io; then cat /proc/$n/io; fi
 cat /proc/$n/attr/current; echo
 echo PID_END
done
echo MAPS_BEGIN
if grep -Ei 'coreclr|hostfxr|hostpolicy' /proc/$p/maps; then exit 4; fi
cat /proc/$p/cgroup
systemctl show {unit} -p MemoryCurrent -p MemoryMax -p CPUUsageNSec -p CPUQuotaPerSecUSec -p ActiveState -p Result
""")
    match = re.search(r"SAMPLE_TIME (\d+(?:\.\d+)?)", out)
    if not match:
        raise Refused("Missing process sample")
    procs = []
    for pid, block in re.findall(r"PID_BEGIN=(\d+)\n(.*?)PID_END", out, re.S):
        stat = block.splitlines()[0].rsplit(")", 1)[1].split()
        procs.append(
            dict(
                pid=int(pid),
                ticks=int(stat[11]) + int(stat[12]),
                rss_kib=int(re.search(r"VmRSS:\s+(\d+)", block)[1]),
                threads=int(re.search(r"Threads:\s+(\d+)", block)[1]),
                memory_kib={
                    k: int(v)
                    for k, v in re.findall(
                        r"SMAPS_(Rss|Pss|Swap|SwapPss): (\d+)", block
                    )
                },
                write_bytes=(
                    int(re.search(r"(?m)^write_bytes: (\d+)", block)[1])
                    if re.search(r"(?m)^write_bytes:", block)
                    else None
                ),
            )
        )
    return dict(uptime=float(match[1]), processes=procs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--binary", type=Path)
    group.add_argument("--recover")
    parser.add_argument(
        "--parent-config",
        type=Path,
        help="Private JSON with host, port, api_key and CA PEM path for an isolated TLS parent",
    )
    args = parser.parse_args()
    site = load_site()
    device = "s90d"
    with lock(STATE / (device + ".lock")):
        if args.recover:
            safe_id(args.recover)
            folder = STATE / "runs" / args.recover
            doc = read_json(folder / "journal.json")
            if (
                not doc
                or doc.get("scope") != "netdata-native-trial"
                or doc["target_binding"] != binding(site, device)
            ):
                raise Refused("Recovery identity mismatch")
            tv = Transport(configured_profile(device, site), folder / "transport")
            cleanup(tv, doc, folder)
            return
        if pending(STATE, device):
            raise Refused("Resolve the pending setup/trial before starting another")
        binary = args.binary.resolve()
        pin = read_json(SOURCE / "upstream.json")
        if sha(binary.read_bytes()) != pin["stripped_elf_sha256"]:
            raise Refused("Expected the reviewed Netdata ARM build")
        identity = run_id()
        suffix = identity.lower()
        folder = STATE / "runs" / identity
        doc = dict(
            scope="netdata-native-trial",
            device=device,
            run=identity,
            target_binding=binding(site, device),
            phase="preparing",
            code="/opt/minimal-netdata-" + suffix,
            ram="/tmp/minimal-netdata-" + suffix,
            staging="/home/owner/share/tmp/sdk_tools/netdata-" + suffix,
            unit="minimal-netdata-" + suffix,
        )
        code, ram, stage, unit = (doc[k] for k in ("code", "ram", "staging", "unit"))
        folder.mkdir(parents=True, exist_ok=False, mode=0o700)
        config = folder / "netdata.conf"
        config.write_text(configuration(code, ram))
        stream = folder / "stream.conf"
        stream.write_text("[stream]\n    enabled = no\n")
        parent = None
        if args.parent_config:
            parent = read_json(args.parent_config)
            host = str(ipaddress.IPv4Address(parent["host"]))
            port = int(parent["port"])
            if not 1 <= port <= 65535:
                raise Refused("Invalid trial parent port")
            key = str(uuid.UUID(parent["api_key"]))
            ca = Path(parent["ca"]).read_bytes()
            if (
                b"BEGIN PRIVATE KEY" in ca
                or b"BEGIN RSA PRIVATE KEY" in ca
                or not ca.startswith(b"-----BEGIN CERTIFICATE-----")
            ):
                raise Refused("Expected a public CA certificate")
            (folder / "parent.crt").write_bytes(ca)
            stream.write_text(
                "[stream]\n    enabled = yes\n    destination = "
                + host
                + ":"
                + str(port)
                + ":SSL\n    api key = "
                + key
                + "\n    CAfile = "
                + code
                + "/parent.crt\n    ssl skip certificate verification = no\n    buffer size = 1MiB\n"
            )
            stream.chmod(0o600)
        exporting = folder / "exporting.conf"
        exporting.write_text("[exporting:global]\n    enabled = no\n")
        optout = folder / ".opt-out-from-anonymous-statistics"
        optout.write_bytes(b"")
        files = {
            "netdata": binary,
            "netdata.conf": config,
            "stream.conf": stream,
            "exporting.conf": exporting,
            ".opt-out-from-anonymous-statistics": optout,
        }
        if parent:
            files["parent.crt"] = folder / "parent.crt"
        doc["files"] = {n: sha(p.read_bytes()) for n, p in files.items()}
        atomic_json(folder / "journal.json", doc)
        print(json.dumps(dict(run=identity, phase=doc["phase"])), flush=True)
        tv = Transport(configured_profile(device, site), folder / "transport")
        nas = NAS(folder / "nas", site["nas"])
        atomic_json(folder / "production-before.json", receiver(nas, device))
        tv.sdk(f"test ! -e {stage}\nmkdir {stage}\ndf -k /opt /tmp\n")
        for n, p in files.items():
            tv.push(p, stage + "/" + n)
        script = f"test ! -e {code}\ntest ! -e {ram}\nmkdir -m 755 {code}\nmkdir -m 700 {ram}\nchown 5001:100 {ram}\nchsmack -a User {code} {ram}\n"
        for n in files:
            script += (
                hash_guard(stage + "/" + n, doc["files"][n])
                + f"cp {stage}/{n} {code}/{n}\nchmod 555 {code}/{n}\nchsmack -a User {code}/{n}\n"
            )
        for n in ("empty", "cache", "lib", "log", "run", "tmp"):
            script += f"mkdir -m 700 {ram}/{n}\nchown 5001:100 {ram}/{n}\nchsmack -a User {ram}/{n}\n"
        props = f'-p User=5001 -p Group=100 -p SmackProcessLabel=User -p BindReadOnlyPaths={code} -p ProtectSystem=strict -p ReadWritePaths={ram} -p InaccessiblePaths=/opt/usr/home -p Nice=10 -p MemoryMax=128M -p CPUQuota=20% -p TasksMax=128 -p LimitCORE=0 -p LimitAS=256M -p LimitCPU=20 -p TimeoutStopSec=8s -p "Environment=DISABLE_TELEMETRY=1 NETDATA_RUN_DIR={ram}/run TMPDIR={ram}/tmp"'
        script += f"""systemd-run --unit={unit}-version {props} -p RuntimeMaxSec=10s -p RemainAfterExit=yes -p StandardOutput=file:{ram}/version.txt -p StandardError=file:{ram}/version-error.txt {code}/netdata -v
sleep 2
systemctl show {unit}-version.service -p ExecMainStatus -p Result
cat {ram}/version.txt {ram}/version-error.txt
echo VERSION_CHECK_DONE
"""
        out = tv.root(script)
        (folder / "version.txt").write_text(out)
        if "ExecMainStatus=0" not in out or "netdata v2.11.1" not in out:
            raise Refused("Netdata version check failed; recover staged trial")
        doc["phase"] = "starting"
        atomic_json(folder / "journal.json", doc)
        out = tv.root(f"""systemd-run --unit={unit} {props} -p RuntimeMaxSec=180s -p StandardOutput=file:{ram}/stdout.txt -p StandardError=file:{ram}/stderr.txt {code}/netdata -D -c {code}/netdata.conf -P {ram}/netdata.pid
sleep 4
systemctl show {unit}.service -p MainPID -p ActiveState -p Result
head -c 6000 {ram}/stderr.txt
""")
        (folder / "start.txt").write_text(out)
        if "ActiveState=active" not in out:
            raise Refused("Netdata startup failed; inspect and recover staged trial")
        doc["phase"] = "running"
        atomic_json(folder / "journal.json", doc)
        observations = []
        atomic_json(
            folder / "clock.json",
            dict(ticks_per_second=int(tv.sdk("getconf CLK_TCK").strip())),
        )
        for i in range(7):
            time.sleep(10)
            value = sample(tv, doc)
            observations.append(value)
            atomic_json(folder / "samples.json", observations)
            print(
                json.dumps(
                    dict(
                        sample=i + 1,
                        uptime=value["uptime"],
                        rss_kib=sum(p["rss_kib"] for p in value["processes"]),
                    )
                ),
                flush=True,
            )
            if i in (0, 6):
                charts = json.loads(
                    tv.sdk(
                        "curl -fsS --max-time 5 http://127.0.0.1:21999/api/v1/charts"
                    )
                )
                if charts.get("update_every") != 10 or not charts.get("charts"):
                    raise Refused("Netdata chart collection did not initialize")
                atomic_json(folder / ("charts-" + str(i) + ".json"), charts)
                atomic_json(
                    folder / ("production-" + str(i) + ".json"), receiver(nas, device)
                )
                if parent:
                    context = ssl.create_default_context(cafile=parent["ca"])
                    base = (
                        "https://"
                        + host
                        + ":"
                        + str(port)
                        + "/host/s90d-native-trial/api/v1/"
                    )
                    with urllib.request.urlopen(
                        base + "charts", context=context, timeout=5
                    ) as response:
                        remote = json.load(response)
                    if not remote.get("charts"):
                        raise Refused("Parent received no charts")
                    atomic_json(folder / ("parent-charts-" + str(i) + ".json"), remote)
                    with urllib.request.urlopen(
                        base + "data?chart=system.cpu&after=-30&points=3",
                        context=context,
                        timeout=5,
                    ) as response:
                        data = json.load(response)
                    atomic_json(folder / ("parent-cpu-" + str(i) + ".json"), data)
                    if i == 6 and not any(
                        any(v is not None for v in row[1:])
                        for row in data.get("data", [])
                    ):
                        raise Refused("Parent CPU chart has no values")
                    print(
                        json.dumps(
                            dict(
                                parent_charts=len(remote["charts"]),
                                parent_data_points=len(data.get("data", [])),
                            )
                        ),
                        flush=True,
                    )
        out = tv.root(f"""p=$(systemctl show {unit}.service -p MainPID --value)
echo MOUNTINFO_BEGIN
grep -E ' /opt | /opt/usr/home | /opt/minimal-netdata-| /tmp/minimal-netdata-' /proc/$p/mountinfo
echo OPEN_FILES_BEGIN
ls -l /proc/$p/fd
find {ram} -type f -printf '%s %p\\n'
head -c 1000 {ram}/stderr.txt
tail -c 1000 {ram}/log/daemon.log || true
""")
        (folder / "runtime-evidence.txt").write_text(out)
        doc["phase"] = "verified"
        atomic_json(folder / "journal.json", doc)
        cleanup(tv, doc, folder)
        atomic_json(folder / "production-after.json", receiver(nas, device))
        print(json.dumps(dict(run=identity, phase=doc["phase"])), flush=True)


if __name__ == "__main__":
    main()
