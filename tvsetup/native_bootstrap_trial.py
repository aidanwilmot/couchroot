"""Isolated host-bootstrap pilot. Production monitoring is never paused.

prepare --device DEVICE --binary FILE creates a private run and stages its payload.
serve --run RUN receives pilot samples locally; ensure/watch reconciles startup.
reboot is explicit and submitted once. cleanup removes only the isolated pilot.
This is bounded research tooling, not an installed management-host daemon.
"""

import argparse
import contextlib
import hashlib
import hmac
import http.server
import importlib.util
import ipaddress
import json
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import threading
import time
import traceback

from .common import (
    REPO,
    STATE,
    Refused,
    atomic_json,
    lock,
    read_json,
    run,
    sha,
    safe_id,
)
from .engine import pending, run_id
from .native_bootstrap import Bootstrap, SCOPE, layout, validate_doc
from .site import binding, configured_profile, load_site
from .transport import Transport, Q


@contextlib.contextmanager
def locked_run(identity, site):
    safe_id(identity)
    folder = STATE / "runs" / identity
    doc = read_json(folder / "journal.json")
    if not doc:
        raise Refused("Pilot journal not found")
    validate_doc(doc)
    device = doc["device"]
    with lock(STATE / (device + ".lock")):
        doc = read_json(folder / "journal.json")
        validate_doc(doc)
        if doc["device"] != device:
            raise Refused("Pilot target changed while acquiring its device lock")
        if doc["target_binding"] != binding(site, device):
            raise Refused("Pilot destination/trust binding changed")
        if any(name != identity for name, _ in pending(STATE, device)):
            raise Refused("Another pending setup operation must be reconciled first")
        if doc["phase"] == "rolled-back":
            raise Refused("This pilot has already been removed")
        yield folder, doc


def prepare(device, binary, seconds, site):
    if not 120 <= seconds <= 1800:
        raise Refused("Pilot lifetime must be 120–1800 seconds")
    binary = binary.resolve()
    body = binary.read_bytes()
    if body[:6] != b"\x7fELF\x01\x01" or body[18:20] != b"\x28\x00":
        raise Refused("Expected a little-endian ARM32 collector")
    with lock(STATE / (device + ".lock")):
        if pending(STATE, device):
            raise Refused("Resolve the pending device operation first")
        identity = run_id()
        folder = STATE / "runs" / identity
        folder.mkdir(parents=True, mode=0o700)
        profile = configured_profile(device, site)
        tv = Transport(profile, folder / "transport")
        address = str(ipaddress.IPv4Address(tv.callback))
        with socket.socket() as listener:
            listener.bind((address, 0))
            port = listener.getsockname()[1]
        cert, key = folder / "receiver-cert.pem", folder / "receiver-key.pem"
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                key,
                "-out",
                cert,
                "-days",
                "1",
                "-subj",
                "/CN=native-bootstrap-pilot",
            ]
        )
        key.chmod(0o600)
        cert.chmod(0o600)
        pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
        payload = folder / "payload"
        payload.mkdir(mode=0o700)
        shutil.copyfile(binary, payload / "collector")
        (payload / "collector").chmod(0o600)
        paths = layout(identity)
        endpoint = f"https://{address}:{port}/v1/devices/{device}"
        atomic_json(
            payload / "config.json",
            dict(
                device_id=device,
                endpoint=endpoint,
                token=secrets.token_urlsafe(32),
                certificate_sha256=pin,
                dashboard_config_path=paths["data"] + "/preferences.json",
                firmware=profile["firmware"],
            ),
        )
        atomic_json(
            payload / "preferences.json",
            dict(schema=1, enabled=True, endpoint=endpoint),
        )
        (payload / "enabled").write_bytes(b"isolated bootstrap pilot\n")
        (payload / "enabled").chmod(0o600)
        doc = dict(
            schema=1,
            scope=SCOPE,
            run=identity,
            device=device,
            target_binding=binding(site, device),
            phase="preparing",
            desired=True,
            expires=time.time() + seconds,
            receiver_host=address,
            receiver_port=port,
            files={p.name: sha(p.read_bytes()) for p in payload.iterdir()},
            **paths,
        )
        atomic_json(folder / "journal.json", doc)
        Bootstrap(tv, doc, folder).stage()
        return dict(run=identity, device=device, phase=doc["phase"])


def serve(identity):
    safe_id(identity)
    folder = STATE / "runs" / identity
    doc = read_json(folder / "journal.json")
    validate_doc(doc)
    if (
        not doc["desired"]
        or doc["phase"] == "rolled-back"
        or time.time() >= doc["expires"]
    ):
        raise Refused("Pilot is finished or expired")
    site = load_site()
    if doc["target_binding"] != binding(site, doc["device"]):
        raise Refused("Pilot binding changed")
    token = read_json(folder / "payload/config.json")["token"]
    peer = configured_profile(doc["device"], site)["host"]
    spec = importlib.util.spec_from_file_location(
        "pilot_metrics", REPO / "telemetry/s90d/nas/metrics.py"
    )
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    write_lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_POST(self):
            status = 400
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if self.client_address[0] != peer or not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                ):
                    status = 403
                elif (
                    self.path != "/v1/devices/" + doc["device"]
                    or not 0 < length <= 131072
                ):
                    status = 400
                else:
                    sample = metrics.validate(json.loads(self.rfile.read(length)))
                    if sample.get("device") != doc["device"]:
                        raise ValueError("device")
                    sample["received_at"] = time.time()
                    with write_lock:
                        with (folder / "pilot-samples.jsonl").open("a") as out:
                            out.write(json.dumps(sample, separators=(",", ":")) + "\n")
                        (folder / "pilot-samples.jsonl").chmod(0o600)
                    status = 204
            except (ValueError, KeyError, StopIteration, OSError):
                pass
            self.send_response(status)
            self.send_header("Content-Length", "0")
            if status != 204:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(folder / "receiver-cert.pem", folder / "receiver-key.pem")

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            try:
                if address[0] != peer:
                    raise OSError("Unexpected pilot peer")
                return context.wrap_socket(connection, server_side=True), address
            except BaseException:
                connection.close()
                raise

    with lock(folder / "receiver.lock"):
        server = Server((doc["receiver_host"], doc["receiver_port"]), Handler)
        server.timeout = 1
        try:
            while time.time() < doc["expires"]:
                current = read_json(folder / "journal.json")
                if not current["desired"] or current["phase"] == "rolled-back":
                    break
                server.handle_request()
        finally:
            server.server_close()


def operate(command, identity, site):
    with locked_run(identity, site) as (folder, doc):
        if command in ("stop", "cleanup"):
            # Cancellation must survive even when the SDK is currently offline.
            doc["desired"] = False
            doc["phase"] = "stopping"
            atomic_json(folder / "journal.json", doc)
        tv = Transport(configured_profile(doc["device"], site), folder / "transport")
        bootstrap = Bootstrap(tv, doc, folder)
        if command == "ensure":
            result = bootstrap.ensure()
        elif command == "observe":
            result = bootstrap.observe()
        elif command == "fail":
            result = bootstrap.fail_main()
        elif command == "inspect":
            result = bootstrap.inspect()
        elif command == "stop":
            bootstrap.stop()
            result = "stopped"
        elif command == "cleanup":
            bootstrap.cleanup()
            result = "rolled-back"
        elif command == "reboot":
            if doc.get("reboot_requested"):
                raise Refused("Reboot was already submitted; do not retry")
            current = bootstrap.observe()
            doc["reboot_requested"] = dict(boot=current["boot"], at=time.time())
            bootstrap.save()
            # Same reviewed deviced API as tv-setup reboot verification. The delay
            # permits the bounded administrative helper to finish its own cleanup.
            from .reboot import reboot_command

            tv.root(
                reboot_command(
                    "native-bootstrap-reboot", "Owner-authorized native bootstrap pilot"
                )
            )
            result = "one reboot submitted"
        return dict(run=identity, action=command, result=result)


def watch(identity, seconds):
    safe_id(identity)
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        # Errors before any write are safe to observe again; uncertain submissions
        # remain journaled and ensure never resubmits in the same boot.
        try:
            result = operate("ensure", identity, load_site())
        except (RuntimeError, OSError) as error:
            # The pinned SDK client raises its own RuntimeError subclass during
            # reconnect, independently of the setup engine's Refused exception.
            folder = STATE / "runs" / identity
            with (folder / "watch-errors.log").open("a") as out:
                out.write(traceback.format_exc() + "\n")
            (folder / "watch-errors.log").chmod(0o600)
            result = dict(
                run=identity,
                result="unavailable or refused",
                error=type(error).__name__,
            )
        if result != last:
            print(json.dumps(result), flush=True)
            last = result
        time.sleep(min(10, max(0, end - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("prepare")
    p.add_argument("--device", choices=("qn90a", "s90d"), required=True)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--seconds", type=int, default=900)
    for name in (
        "serve",
        "ensure",
        "observe",
        "inspect",
        "fail",
        "stop",
        "cleanup",
        "reboot",
        "watch",
    ):
        p = subs.add_parser(name)
        p.add_argument("--run", required=True)
        if name == "watch":
            p.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.run)
        return
    if args.command == "watch":
        if not 1 <= args.seconds <= 1800:
            parser.error("watch duration must be 1–1800 seconds")
        watch(args.run, args.seconds)
        return
    site = load_site()
    result = (
        prepare(args.device, args.binary, args.seconds, site)
        if args.command == "prepare"
        else operate(args.command, args.run, site)
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
