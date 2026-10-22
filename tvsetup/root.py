"""Build a bounded operation using the tracked model-specific namespace probes.

No private dump collector, deployed artifacts or historical backup is imported.
The baseline invocation reports identity only; the script runs only at uid 0.
This orchestration requires physical validation on each supported firmware.
"""

import base64
import io
import re
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from .common import PRIVATE, REPO, Refused, lock, run, sha
from .transport import managed_guard, hash_guard, Q
from .toolkit import load

BASE = "/home/owner/share/tmp/sdk_tools/"
LAUNCHER = {
    "qn90a": "3580e6dcf5d9c6d5d0a606d43a3d878641f35eeac07317a405fb45bbed69a653",
    "s90d": "607e2991160449c0e5fb3acbdef1e47ac761086e5ad8942fff8a9725633ae20e",
}
OPERATION = """using System;using System.IO;using System.Diagnostics;using System.Runtime.InteropServices;
class RootIdentity {
[DllImport("libc.so.6")]static extern uint getuid();
static int Main(){foreach(string l in File.ReadLines("/proc/self/status"))if(l.StartsWith("Uid:"))Console.WriteLine(l);if(getuid()!=0)return 0;
var p=new ProcessStartInfo("/bin/sh"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};p.ArgumentList.Add("-c");p.ArgumentList.Add(System.Text.Encoding.UTF8.GetString(Convert.FromBase64String("PAYLOAD")));
using(var c=Process.Start(p)){var o=c.StandardOutput.ReadToEndAsync();var e=c.StandardError.ReadToEndAsync();if(!c.WaitForExit(25000)){c.Kill(true);return 9;}Console.Write(o.Result);Console.Write(e.Result);return c.ExitCode;}}
}"""


def operation_source(script):
    if script is None:
        return OPERATION.replace(
            'System.Text.Encoding.UTF8.GetString(Convert.FromBase64String("PAYLOAD"))',
            'File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"operation.sh"))',
        )
    return OPERATION.replace("PAYLOAD", base64.b64encode(script.encode()).decode())


def build(profile, folder, script, cleanup_index=None):
    folder = folder.resolve()
    framework = profile["framework"]
    defines = "QN90A" if profile["id"] == "qn90a" else ""
    outputs = {}
    for name in ("NamespaceRootProbe", "RootIdentity"):
        project = folder / name
        project.mkdir()
        if name == "NamespaceRootProbe":
            source = (REPO / "agent/namespace-root-probe/Program.cs").read_text()
        elif cleanup_index is None:
            source = operation_source(script)
        else:
            if (
                profile["id"] != "qn90a"
                or type(cleanup_index) is not int
                or not 0 <= cleanup_index < 10
            ):
                raise Refused("Invalid reviewed QN90A cleanup target")
            source = (REPO / "native/qn90a-app-cleanup/Program.cs").read_text()
            defines = "HOME_CLEANUP_" + str(cleanup_index)
        (project / "Program.cs").write_text(source)
        csproj = project / (name + ".csproj")
        csproj.write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<TargetFramework>"
            + framework
            + "</TargetFramework><OutputType>Exe</OutputType>"
            "<UseAppHost>false</UseAppHost><CheckEolTargetFramework>false</CheckEolTargetFramework>"
            "<DefineConstants>"
            + defines
            + "</DefineConstants></PropertyGroup></Project>"
        )
        run(
            [
                "dotnet",
                "build",
                csproj,
                "-c",
                "Release",
                "--nologo",
                "-v",
                "quiet",
                "-p:Deterministic=true",
                "-p:PathMap=" + str(project) + "=/src/" + name,
            ],
            timeout=120,
        )
        outputs[project / "bin/Release" / framework / (name + ".dll")] = name + ".dll"
    return outputs


def prepare_artifacts(
    profile, folder, script, probe, cleanup_index=None, native_bundle=None
):
    """Compile/sign locally before creating any device staging directories."""
    from . import native_root

    outputs = (
        build(profile, folder, script, cleanup_index)
        if native_bundle is None
        else native_root.prepare(profile, native_bundle, folder, script, cleanup_index)
    )
    artifacts = {p: probe + "/" + name for p, name in outputs.items()}
    archive = folder / (probe + ".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        payload = b"Authorized bounded setup operation.\n"
        entry = tarfile.TarInfo("identity-proof.txt")
        entry.size = len(payload)
        entry.mode = 0o644
        tar.addfile(entry, io.BytesIO(payload))
    private = folder / "test-private.pem"
    public = folder / "public.pem"
    signature = folder / (archive.name + ".signature")
    try:
        run(
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                private,
            ]
        )
        run(["openssl", "pkey", "-in", private, "-pubout", "-out", public])
        run(
            ["openssl", "dgst", "-sha256", "-sign", private, "-out", signature, archive]
        )
        run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-verify",
                public,
                "-signature",
                signature,
                archive,
            ]
        )
    finally:
        private.unlink(missing_ok=True)
    artifacts.update(
        {
            public: probe + "/public.pem",
            archive: probe + "/archives/" + archive.name,
            signature: probe + "/archives/" + signature.name,
        }
    )
    return artifacts


# Only setup-owned names; never enumerate/delete the agent's shared directory.
STAGE_FILES = (
    "NamespaceRootProbe.dll",
    "RootIdentity.dll",
    "NativeEntry.dll",
    "NativeEntry.deps.json",
    "NativeEntry.runtimeconfig.json",
    "public.pem",
    "operation.sh",
    "passwd-view",
    "result.txt",
    "read.tmp",
    "code/libacquire.so",
    "private/result.txt",
    "private/read.tmp",
)


def cleanup_script(prefix, probe, keep_result=False):
    # Each removal is independent: a failure must not skip later cleanup.
    files = (
        *STAGE_FILES,
        "archives/" + probe + ".tar.gz",
        "archives/" + probe + ".tar.gz.signature",
    )
    if keep_result:
        files = tuple(name for name in files if not name.startswith("private/"))
    removals = ""
    for name in files:
        parent = name.rsplit("/", 1)[0] if "/" in name else ""
        if parent:
            removals += (
                f"if test -L {Q(prefix + '/' + parent)}; then cleanup_failed=1; else\n"
            )
        removals += f"rm -f {Q(prefix + '/' + name)} || cleanup_failed=1\n"
        if parent:
            removals += "fi\n"
    return (
        "(\n"
        + f"if test -L {Q(prefix)}; then exit 1; fi\n"
        + f'if test -e {Q(prefix)} && test "$(stat -c %u {Q(prefix)})" != "$(id -u)"; then exit 1; fi\n'
        + "cleanup_failed=0\n"
        + removals
        + "".join(
            f"if test -d {Q(prefix + suffix)}; then rmdir {Q(prefix + suffix)} || cleanup_failed=1; fi\n"
            for suffix in (
                ("/code", "/archives", "/shared-on-demand")
                if keep_result
                else ("/private", "/code", "/archives", "/shared-on-demand", "")
            )
        )
        + 'test "$cleanup_failed" = 0\n)\n'
    )


def staging_script(prefix, native=False):
    """SDK owns disposable directories; uploads never enter shared on-demand."""
    probe = prefix.rsplit("/", 1)[1]
    on_demand = BASE + "on-demand"
    # Refuse substituted directories, but discard our known stale files. No old
    # executable or archive is reused: every upload is freshly hash-checked.
    safe = "".join(
        f"test ! -L {Q(prefix + suffix)}\n"
        for suffix in ("", "/private", "/code", "/archives", "/shared-on-demand")
    )
    return (
        safe
        + f'if test -e {Q(prefix)}; then test "$(stat -c %u {Q(prefix)})" = "$(id -u)";\n'
        + cleanup_script(prefix, probe)
        + "fi\n"
        + "made_prefix=0\n"
        + "stage_rollback() {\n"
        + 'if test "$made_prefix" = 1; then\n'
        + cleanup_script(prefix, probe)
        + "fi\n}\n"
        + "trap 'status=$?; stage_rollback || :; exit \"$status\"' EXIT\n"
        + f"mkdir {Q(prefix)}\nmade_prefix=1\n"
        + f"if mkdir {Q(on_demand)} 2>/dev/null; then :; else test -d {Q(on_demand)}; test ! -L {Q(on_demand)}; fi\n"
        + f"mkdir {Q(prefix + '/archives')} {Q(prefix + '/shared-on-demand')}\n"
        + (f"mkdir {Q(prefix + '/code')}\n" if native else "")
        # Never upload/chmod a result file. Exclusive creation in an SDK-private
        # directory protects it before the first credential byte is written.
        + f"(umask 077; mkdir {Q(prefix + '/private')}; set -C; : >{Q(prefix + '/private/result.txt')}; : >{Q(prefix + '/private/read.tmp')})\n"
        + f"stat -c '%U:%G:%a' {Q(prefix)}\n"
        + "trap - EXIT\n"
    )


def read_result(client, prefix, callback):
    # SDB pull runs as owner; the SDK-created 0600 result intentionally denies
    # that account. Use the existing serial-scoped SDK callback, without a raw
    # result preview or a second credential-bearing download on the host.
    path = Q(prefix + "/private/result.txt")
    result = client.capture(
        f'(set -eu; test ! -L {path}; test "$(wc -c <{path})" -le 16777216; cat {path})',
        callback_host=callback,
        bind_host=callback,
        timeout=20,
    )
    match = re.search(r"\n\[exit:0\]\s*\Z", result.output)
    if result.transport_returncode not in (0, 1) or not match:
        raise Refused("Private root result retrieval failed")
    output = result.output[: match.start()]
    if len(output.encode()) > 16 * 1024 * 1024:
        raise Refused("Oversized root result")
    return output


def execute(
    profile,
    script,
    cleanup_index=None,
    *,
    native_bundle=None,
    session=None,
    capture_result=False,
):
    toolkit = load()
    cfg = dict(
        tv_host=profile["host"],
        expected_model=profile["model"],
        expected_platform=profile["platform"],
        expected_device_id=profile["device_id"],
    )
    probe = (
        "codex-qn90a-root-proof"
        if profile["id"] == "qn90a"
        else "codex-namespace-proof"
    )
    if native_bundle is not None:
        from . import native_root

        probe = native_root.probe_name(profile)
    prefix = BASE + probe
    guards = managed_guard(profile) + hash_guard(
        "/usr/sbin/sdbd-tarlauncher", LAUNCHER[profile["id"]]
    )
    with (
        lock(PRIVATE / (profile["id"] + "-root-check.lock")),
        tempfile.TemporaryDirectory(prefix="setup-root-", dir=PRIVATE) as tmp,
    ):
        folder = Path(tmp)
        # Every operation still stages, verifies and removes its own remote files.
        if capture_result:
            script = (
                "export TV_SETUP_READ_TMP="
                + Q(prefix + "/private/read.tmp")
                + "\n(\n"
                + script
                + "\n) >"
                + Q(prefix + "/private/result.txt")
                + " 2>&1\n"
            )
        legacy = "\n".join(
            "rm -f "
            + Q(prefix + "/shared-on-demand/" + probe + suffix)
            + " || legacy_cleanup_failed=1"
            for suffix in (".tar.gz", ".tar.gz.signature")
        )
        script = (
            "legacy_cleanup_failed=0\n"
            + legacy
            + '\ntest "$legacy_cleanup_failed" = 0\n'
            + script
        )
        if session is not None and cleanup_index is None and native_bundle is None:
            from .root_session import prepared

            artifacts = prepared(profile, Path(session), probe)
            operation = folder / "operation.sh"
            operation.write_text(guards + script)
            artifacts[operation] = probe + "/operation.sh"
        else:
            artifacts = prepare_artifacts(
                profile, folder, guards + script, probe, cleanup_index, native_bundle
            )
        callback = toolkit.device(cfg)
        client = toolkit.SdbClient(PRIVATE / "bin/sdb", profile["host"])
        client.connect()
        client.require_device()
        # Originals are captured afresh; no dependency on another TV's passwd hash.
        original = client.capture(
            "(\n" + guards + "sha256sum /etc/passwd /usr/share/sdbd/public.pem\n)",
            callback_host=callback,
            bind_host=callback,
            timeout=15,
        )
        hashes = {
            m[2]: m[1]
            for m in re.finditer(r"(?m)^([a-f0-9]{64})  (/\S+)$", original.output)
        }
        if (
            original.transport_returncode not in (0, 1)
            or not re.search(r"\n\[exit:0\]\s*\Z", original.output)
            or set(hashes) != {"/etc/passwd", "/usr/share/sdbd/public.pem"}
        ):
            raise Refused("Cannot verify original root-transport resources")
        originals = "".join(hash_guard(p, h) for p, h in hashes.items())
        stage = (
            guards
            + originals
            + staging_script(prefix, native=native_bundle is not None)
        )
        cleanup = cleanup_script(prefix, probe)
        captured = None
        try:
            toolkit.capture(cfg, callback, stage, 20, "setup-root-stage")
            for source, target in artifacts.items():
                client.push(source, PurePosixPath(BASE + target))
            check = "".join(
                hash_guard(BASE + target, sha(source.read_bytes()))
                for source, target in artifacts.items()
            )
            completed = cleanup_script(prefix, probe, keep_result=True)
            command = guards + originals + "completed() {\n" + completed + "}\n"
            command += (
                "trap 'status=$?; completed || :; exit \"$status\"' EXIT\n" + check
            )
            if native_bundle is None:
                command += f"/usr/bin/dotnet {prefix}/NamespaceRootProbe.dll {prefix} --setup-archives\n"
            else:
                command += f"env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin DBUS_SYSTEM_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/0-system/bus /usr/bin/dotnet {prefix}/NativeEntry.dll probe\n"
            failure = None
            try:
                toolkit.capture(cfg, callback, command, 45, "setup-root-operation")
            except Exception as error:
                failure = error
            if capture_result:
                try:
                    captured = read_result(client, prefix, callback)
                except Exception:
                    if failure is None:
                        raise
                    captured = "Operation output could not be retrieved; completion remains unconfirmed."
            if failure is not None:
                failure.output = captured or ""
                raise failure
            return captured
        finally:
            # Only known temporary files; never retry an uncertain operation.
            try:
                toolkit.capture(
                    cfg,
                    callback,
                    "set -u\n"
                    + cleanup
                    + "cleanup_status=$?\n"
                    + "".join(
                        line + " || cleanup_status=1\n"
                        for line in originals.splitlines()
                    )
                    + f"test ! -e {prefix} || cleanup_status=1\n"
                    'if ps -eo args | grep -E "[N]amespaceRootProbe.dll|[R]ootIdentity.dll|[N]ativeEntry.dll"; then cleanup_status=1; fi\nexit "$cleanup_status"\n',
                    20,
                    "setup-root-cleanup",
                )
            except Exception as error:
                if captured is not None:
                    error.output = captured
                raise
