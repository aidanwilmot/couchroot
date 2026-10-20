"""Repeat the bounded, temporary S90D root identity proof; leave no root service."""
import fcntl
from pathlib import PurePosixPath

from samsung_tv import ROOT, SdbClient, capture


def run(config, callback):
    # A fixed diagnostic only: this deliberately does not accept a root command.
    with (ROOT / "root-check.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stage = (ROOT / "stage-namespace-probe.sh").read_text()
        guard = """set -eu
test "$(sha256sum /usr/sbin/sdbd-tarlauncher | cut -d ' ' -f 1)" = 607e2991160449c0e5fb3acbdef1e47ac761086e5ad8942fff8a9725633ae20e
test "$(uname -m)" = armv7l
"""
        files = {
            "namespace-root-probe/bin/Release/net6.0/NamespaceRootProbe.dll": "codex-namespace-proof/NamespaceRootProbe.dll",
            "root-identity-probe/bin/Release/net6.0/RootIdentity.dll": "codex-namespace-proof/RootIdentity.dll",
            "namespace-root-probe/public.pem": "codex-namespace-proof/public.pem",
            "namespace-root-probe/codex-namespace-proof.tar.gz": "on-demand/codex-namespace-proof.tar.gz",
            "namespace-root-probe/codex-namespace-proof.tar.gz.signature": "on-demand/codex-namespace-proof.tar.gz.signature",
        }
        for source in files:
            if not (ROOT / source).is_file():
                raise RuntimeError(f"Missing reviewed probe artifact: {source}")
        capture(config, callback, guard + stage, 20, "root-check-stage")
        try:
            client = SdbClient(ROOT / "bin/sdb", config["tv_host"])
            client.connect()
            client.require_device()
            for source, target in files.items():
                client.push(ROOT / source, PurePosixPath("/home/owner/share/tmp/sdk_tools") / target)
            capture(config, callback, (ROOT / "run-namespace-probe.sh").read_text(), 45, "root-check")
        finally:
            # Also covers an interrupted push. Only these known probe files are removed.
            cleanup = "\n".join(
                "rm -f /home/owner/share/tmp/sdk_tools/" + target for target in files.values()
            )
            cleanup += "\nrm -f /home/owner/share/tmp/sdk_tools/codex-namespace-proof/passwd-view\n"
            for name in ("codex-namespace-proof", "on-demand"):
                path = "/home/owner/share/tmp/sdk_tools/" + name
                cleanup += f"if test -d {path}; then rmdir {path}; fi\n"
            capture(config, callback, "set -eu\n" + cleanup, 20, "root-check-cleanup")
        capture(config, callback, (ROOT / "verify-root-probe-cleanup.sh").read_text(), 20, "root-check-verify")
