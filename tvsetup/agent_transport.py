"""Explicit certificate-pinned root-agent transport for scoped setup trials.

Unlike SDB Transport, all commands run in the enrolled root worker. Package
installation is deliberately unsupported: Driver's ordinary signer/installer
path must still be used with a reachable SDK connection. No automatic retries.
"""

import base64
import importlib.util
import json
from pathlib import Path
import uuid
from .common import REPO, Refused, atomic_json, sha
from .transport import (
    Transport,
    compare_identity_probe,
    identity_probe_script,
    managed_guard,
    managed_guard_refusal,
    Q,
)


class AgentTransport(Transport):
    def __init__(self, profile, evidence, credentials):
        self.profile, self.evidence = profile, Path(evidence)
        self.identity_diagnostics = []
        self.evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.credentials = json.loads(Path(credentials).read_text())
        if (
            self.credentials.get("device") != profile["id"]
            or self.credentials.get("host") != profile["host"]
        ):
            raise Refused("Agent enrollment differs from selected device")
        spec = importlib.util.spec_from_file_location(
            "enrolled_agent_client", REPO / "agent/client.py"
        )
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        status = self.api.request(self.credentials, "GET", "/v1/status")
        if (
            status.get("device") != profile["id"]
            or not status.get("connected")
            or status.get("worker_ready") is False
            or status.get("identity", {}).get("uid") != 0
        ):
            raise Refused("Enrolled root worker is not ready")
        probe = identity_probe_script().replace(
            "PROFILE_RUNTIME", Q(profile["runtime"])
        )
        self.identity_diagnostics = compare_identity_probe(
            profile, self._execute(probe, 20)
        )
        if self.identity_diagnostics:
            atomic_json(
                self.evidence / "identity-diagnostics.json",
                {
                    "differences": [
                        {"field": field, "expected": expected, "found": found}
                        for field, expected, found in self.identity_diagnostics
                    ]
                },
            )
        self._execute(managed_guard(profile), 20)

    def execute_result(self, script, timeout=20):
        """Return a completed command result, including nonzero exits."""
        encoded = base64.b64encode(script.encode()).decode()
        command = "printf %s " + encoded + " | base64 -d | /bin/sh"
        if len(command.encode()) > 16384:
            raise Refused("Agent command exceeds bounded request size")
        request = dict(
            id=str(uuid.uuid4()),
            command=command,
            timeout_ms=min(25000, int(timeout * 1000)),
        )
        path = self.evidence / ("agent-" + request["id"] + ".json")
        atomic_json(path, dict(state="submitted", request=request))
        result = self.api.request(self.credentials, "POST", "/v1/exec", request)
        atomic_json(path, dict(state="completed", request=request, result=result))
        if result.get("id") != request["id"] or not isinstance(
            result.get("exit_code"), int
        ):
            raise Refused(
                "Invalid agent response; outcome unknown; inspect private evidence: "
                + str(path)
            )
        return result

    def _execute(self, script, timeout=20, check=True, *, guard_marker=None):
        if guard_marker is None and script.startswith(managed_guard(self.profile)):
            guard_marker = "TVSETUP_MANAGED_GUARD_OK_" + uuid.uuid4().hex
            guard = managed_guard(self.profile)
            script = (
                guard
                + "printf '%s\\n' "
                + Q(guard_marker)
                + "\n"
                + script[len(guard) :]
            )
        result = self.execute_result(script, timeout)
        stdout = result.get("stdout", "")
        if check and (result["exit_code"] != 0 or result.get("timed_out")):
            failure = Refused(
                "Agent command completed with exit code "
                + str(result["exit_code"])
                + (" (timed out)" if result.get("timed_out") else "")
                + "; inspect private evidence in "
                + str(self.evidence)
            )
            if (
                result["exit_code"] != 0
                and not result.get("timed_out")
                and guard_marker is not None
                and guard_marker not in stdout
            ):
                raise managed_guard_refusal(
                    failure, self.identity_diagnostics, prefix=str(failure)
                )
            raise failure
        if guard_marker is not None:
            stdout = stdout.replace("\n" + guard_marker + "\n", "\n", 1)
            if stdout.startswith(guard_marker + "\n"):
                stdout = stdout[len(guard_marker) + 1 :]
        return stdout

    def sdk(self, script, timeout=30):
        # Inherited snapshot parsing is reused, but this is explicitly root,
        # not evidence of SDK UID permissions. Never attach an SDB client.
        if len(script.encode()) <= 12000:
            return self._execute(script, timeout)
        guard_marker = None
        guard = managed_guard(self.profile)
        if script.startswith(guard):
            guard_marker = "TVSETUP_MANAGED_GUARD_OK_" + uuid.uuid4().hex
            script = (
                guard
                + "printf '%s\\n' "
                + Q(guard_marker)
                + "\n"
                + script[len(guard) :]
            )
        stage = "/home/owner/share/tmp/sdk_tools/couchroot-inspect-" + uuid.uuid4().hex
        self._execute("umask 077\nmkdir " + Q(stage) + "\n")
        self._upload(script.encode(), stage + "/command.sh")
        return self._execute(
            'sh -c "$(cat '
            + Q(stage + "/command.sh")
            + ')"; result=$?; rm -f '
            + Q(stage + "/command.sh")
            + "; rmdir "
            + Q(stage)
            + '; exit "$result"\n',
            timeout,
            guard_marker=guard_marker,
        )

    def root(self, script, namespace=False, cleanup_index=None):
        if namespace or cleanup_index is not None:
            raise Refused(
                "Namespace and cleanup operations are not supported by this trial transport"
            )
        return self.sdk(managed_guard(self.profile) + script, 25)

    def _upload(self, data, target):
        digest = sha(data)
        evidence = self.evidence / ("agent-upload-" + uuid.uuid4().hex + ".json")
        record = dict(
            state="begin-submitted", target=target, size=len(data), sha256=digest
        )
        atomic_json(evidence, record)
        session = self.api.operation(
            self.credentials,
            dict(
                op="file.begin",
                path=target,
                size=len(data),
                sha256=digest,
                expected_sha256="absent",
            ),
        )
        transfer = session["transfer_id"]
        record.update(state="uploading", transfer_id=transfer, offset=0)
        atomic_json(evidence, record)
        for offset in range(0, len(data), session["chunk_bytes"]):
            chunk = data[offset : offset + session["chunk_bytes"]]
            record.update(state="chunk-submitted", offset=offset)
            atomic_json(evidence, record)
            result = self.api.operation(
                self.credentials,
                dict(
                    op="file.write",
                    transfer_id=transfer,
                    offset=offset,
                    sha256=sha(chunk),
                ),
                binary=chunk,
            )
            if result.get("offset") != offset + len(chunk):
                raise Refused("Upload offset mismatch; inspect transfer " + transfer)
        record.update(state="commit-submitted", offset=len(data))
        atomic_json(evidence, record)
        result = self.api.operation(
            self.credentials, dict(op="file.commit", transfer_id=transfer)
        )
        record.update(state="completed", result=result)
        atomic_json(evidence, record)

    def push(self, source, target):
        if not str(target).startswith(
            "/home/owner/share/tmp/sdk_tools/tv-setup-"
        ) or not str(target).endswith("-control.dll"):
            raise Refused("Only a run-specific setup control helper may be staged")
        self._upload(Path(source).read_bytes(), str(target))
