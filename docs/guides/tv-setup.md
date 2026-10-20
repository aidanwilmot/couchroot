# TV setup and reapplication (unreleased)

For a separately reviewed S90D helper/cache boot trial, see
[S90D boot checkpoints and recovery](s90d-boot-recovery.md). Its checkpoints use
the shared device lock and journal, preserving the prior composite helper and
patched cache rather than restoring the historical splash-only build.

For launcher-focused setup, start with the [unified installer](universal-installer.md).
It adds offline web/native preparation and a scoped web installation path on this
shared engine. The [native boot-hook backend](native-installation.md) uses the
same engine and locks with explicit baseline enrollment; it is offline-tested only.

For a routine Hub interface update on a configured TV, use the shorter
[UI deployment workflow](ui-deployment.md). It shares this engine’s locks,
journals and signing checks while preserving full-setup choices.


`tv-setup` is unofficial, firmware-specific tooling for TVs you own or administer.
It offers five commands: `plan`, `apply`, `status`, `verify`, and `rollback`.
**This release candidate has not completed the full hardware setup/recovery
acceptance matrix.** See [release blockers](../project/release-readiness.md). The
2026-09-21 [shared telemetry rollout](telemetry.md#service-unification-validation--2026-09-21)
validated Hub/service updates and full reboot startup on both TVs, plus recovery
from an initial failed S90D install. That narrow result does not establish all
full-setup or recovery paths.

## Supported boundaries

| Model | Exact firmware | Historical integration | Current CLI apply/recovery |
| --- | --- | --- | --- |
| QN85QN90AAFXZA (QN90A) | `T-NKM2AKUC-2301.1` | Verified on one owner's TV | Hub/service verified; full setup acceptance pending |
| QN55S90DAFXZA (S90D) | `T-PTMDAKUC-0090-2130.0` | Verified on one owner's TV | Hub/service verified; full setup acceptance pending |
| Other sizes, regions, models or firmware | Any other combination | Unverified | Unsupported; preflight refuses |

QN90A retains its signed welcome-process relay → Hub → telemetry UI relay →
service chain, exact Home/AirPlay routes, Samsung splash, and **Hub-owned
five-minute** Asteroids saver. No S90D writable-cache assumptions, memory offsets,
system-wide saver timeout or copied native module are used on QN90A.
S90D retains its separate AT-HUB startup, splash acknowledgement and native saver
integration. Both TVs start the same signed telemetry service from Hub; S90D
telemetry migration retires only the old collector marker. See
[telemetry operations](telemetry.md).
Model, platform, firmware, runtime/launcher hashes, signing identity,
resource hashes and protected-package checks cannot be disabled by choices.

Host validation targets macOS and Linux. CI uses Python 3.12: the full offline
suite runs on Linux x86-64; macOS 14 ARM64 runs the setup, installer and UI-deploy
Python tests. Newer Python versions can be checked locally. Other host
architectures are experimental; native Windows and WSL are unsupported. CI
results are host tests, not proof of TV behavior.

## Install from source

Keep the checkout; the CLI reads source and model profiles beside its entry point.
Use a virtual environment and run the entry point from that environment:

```sh
cd /path/to/samsung-tv-hub
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tvsetup/requirements.txt
python scripts/check-dependencies.py
./tv-setup --version
./tv-setup --help
```

Install the .NET SDK selected by `global.json` (10.0.301), OpenSSL, Git and OpenSSH.
.NET restores the TV's `netcoreapp3.1`/`net6.0` reference packs; do not change the TV
runtime or retarget the payloads to the host runtime. These old target runtimes
are a maintenance constraint. The dependency checker is offline and never contacts
a device. Node 22 and Playwright are only needed for web tests.

Obtain Samsung SDB and the Tizen CLI/certificate tools from their official
installation channels, under their vendor terms. They are **not redistributed**
here. Supply their paths explicitly (or put `tizen` on PATH):

```sh
export SAMSUNG_TV_TOOLKIT="$HOME/.local/share/samsung-tv-research"
export TIZEN=/path/to/tizen-studio/tools/ide/bin/tizen
SDB=/path/to/tizen-studio/tools/sdb sh tools/setup-toolkit.sh
```

The toolkit script fetches the pinned public transport commit, installs its
optional analysis dependencies and builds disposable diagnostic payloads. It has
no TV/NAS operations. It refuses to replace generated keys without explicit
`FORCE_REBUILD=1`; use a new toolkit directory for a clean install. Do not force
replacement during an unfinished run. No private research installation,
`gather-dumps.py`, old signing build or historical deployment backup is required
by `tv-setup`. Legacy top-level/research deployment scripts are historical and
are **not** the public installation path.

## Configure your installation

```sh
mkdir -p "$HOME/.config/samsung-tv-hub"
chmod 700 "$HOME/.config/samsung-tv-hub"
cp examples/site.json "$HOME/.config/samsung-tv-hub/site.json"
chmod 600 "$HOME/.config/samsung-tv-hub/site.json"
```

Edit the copied file with your TV IPv4 addresses and exact `device_id` values
(the `device.id` UUID from a read-only GET of `http://TV_ADDRESS:8001/api/v2/`).
Keep that response private. The CLI compares physical identity before SDB commands. Example addresses are reserved
for documentation and will not find a TV. Delete devices you do not own and the
`nas` section if you are doing TV-only setup. NAS support currently requires an
already provisioned TrueNAS `s90d-telemetry` app with receiver/dashboard services
and the reviewed two-device registry. New NAS provisioning is a release blocker;
this CLI refuses absent or structurally different infrastructure.

`nas.ssh_target` is your SSH config alias (or `user@host`). Configure the identity
file in `~/.ssh/config`, and verify the host key separately. The CLI uses batch
SSH and strict host-key checking. `nas.base` names the existing telemetry code
directory; URL fields are credential-free origins. Receiver URLs require HTTPS.
HTTP dashboard inspection should stay on a trusted management network. The
collector separately pins the receiver certificate; no credential goes in Hub.

Enable TV Developer Mode with this computer's routed address. Identity inspection
checks the exact physical identity, model/platform and the Developer Mode host before SDB commands.
It does not change firmware, Developer Mode, security policy or firewall rules.

The toolkit reuses ready SDB connections and serializes connection attempts to
avoid repeated-connect socket leaks observed in the macOS vendor daemon. See
[SDB connection reliability](sdb-connection-reliability.md) for the diagnosis,
bounded validation, and recovery details.

For package installation, create your own Samsung developer signing profile and
independently inspect its author/distributor certificates. Add `"trust_file":
"trust.json"` to site.json. The adjacent private trust file has this shape (replace
both placeholders with SHA256 of the DER certificates, lowercase hex):

```json
{
  "qn90a": {
    "signing_profile": "MyQN90A",
    "author_cert_sha256": "REPLACE_WITH_REVIEWED_AUTHOR_DER_SHA256",
    "distributor_cert_sha256": "REPLACE_WITH_REVIEWED_DISTRIBUTOR_DER_SHA256"
  }
}
```

Enroll each TV separately. The CLI never learns trust from a package it is asked
to install. Signatures and all member digests are verified against these pins;
Samsung still checks device authorization at installation. Renewed certificates
require deliberate re-enrollment. Updates must retain the installed author
identity and move versions forward; copying another owner's profile does not
supply their private key or authorize your TV. Certificate enrollment/renewal on
a fresh user's device still needs hardware validation.

Connection configuration is `--site PATH` → `TV_SETUP_SITE` →
`~/.config/samsung-tv-hub/site.json`. Choices are separate:
**recommended defaults → saved choices → `--config` JSON → CLI overrides**.
Lists replace earlier lists; keep/remove displace contradictory earlier choices.
`examples/choices.json` starts with TV integration only, no cleanup or telemetry.
Default recommendations select all components, including reviewed optional-app
cleanup. Use the example choices for a narrower first plan:

```sh
./tv-setup plan --device qn90a --config examples/choices.json
./tv-setup apply --device qn90a --config examples/choices.json
./tv-setup status --device qn90a
./tv-setup verify --device qn90a
./tv-setup rollback --device qn90a --run RUN_ID --yes
```

The proposal gives one change summary and a short reason per component. Unknown
firmware/resources/protection metadata or incomplete uninstalls block apply.
Cleanup is limited to the reviewed package/app/version allowlist, registration,
dependency and protection checks. A removable flag alone never permits removal.

```sh
./tv-setup apply --device qn90a --keep GHI3a0zMSx
./tv-setup plan --device s90d --components hub,screensaver
./tv-setup apply --device qn90a --remove '' --exclude dashboard,telemetry --yes
./tv-setup apply --device s90d --non-interactive --yes
./tv-setup plan --device qn90a --json
```

`null` telemetry choices preserve current preferences. First telemetry pairing
requires an explicit receiver endpoint; missing preferences default to monitoring
**disabled**. Enable it deliberately with `--telemetry-enabled true`. Extra TV
preferences, favorites, ordering, sound, layout and clock settings are preserved.

```sh
./tv-setup plan --device qn90a --components telemetry \
  --endpoint https://nas.example.invalid:20490/v1/devices/qn90a
./tv-setup apply --device qn90a --components dashboard --shared-nas --yes
```

Shared NAS changes require `--shared-nas`. They preserve live compose, both
credential records, the device registry, history volumes and snapshot paths.
Receiver/dashboard restarts briefly interrupt both devices' collection. Use one
management host/state directory: local locks do not coordinate independent hosts.
Do not edit the NAS or TV concurrently with setup/recovery.

## Build artifacts

```sh
python scripts/build-native.py
python scripts/package.py
# After all source files are tracked, compare a second source-only checkout:
python scripts/check-reproducible.py
# With Emscripten 3.1.64 on PATH:
python scripts/check-web-reproducible.py
```

Native builds use the pinned host SDK and deterministic path mapping, producing
`dist/native-manifest.json`. `scripts/package.py` makes a deterministic **unsigned** Hub
WGT. It is a source artifact, not an installable signed package. The setup Builder
prepares model-specific Hub, saver, relay and service packages and signs them
locally. Signing outputs, certificate stores and diagnostic keys remain private.

The saver check builds from two source paths and writes
`dist/saver-reproducibility.json`. It reports comparison with the historical
reviewed hashes separately from reproducibility; a repeatable build does not
establish hardware acceptance. The pinned clean build currently reproduces
`shaders.js` but differs for `core.js`; profile hashes are not updated automatically.
For an isolated Linux build, run the check in `emscripten/emsdk:3.1.64` with only
a disposable source checkout mounted, without site settings, keys or TV access.

QN90A saver compilation requires Emscripten (CI uses 3.1.64). S90D renderer builds
require Linux, `gcc-arm-linux-gnueabi`, `libc6-dev-armel-cross`, GLES headers and an
owner-provided compatible `libGLESv2.so.2` directory:

```sh
GLES_LIBRARY_DIR=/private/vendor-library sh native/system-screensaver/build.sh
./tv-setup plan --device s90d --artifact renderer=/private/libgl-demo-app.so
```

The renderer's reviewed digest remains mandatory. A compiler-dependent mismatch
requires review; **do not remove the hash guard**. Its compiler/sysroot recipe is
not yet proven to reproduce the reviewed binary from a clean machine. No Samsung
binary, signing material, firmware or extracted resource belongs in a source or
public artifact bundle. See [redistribution decisions](../../LICENSE-STATUS.md).

## Apply, interruption and recovery

Apply builds/signs before its proposal, then verifies fresh per-action backups,
rechecks state, records intent, submits each mutation once and verifies readback.
Private journals use atomic replacement/fsync and 0600 files. They live under
`$TV_SETUP_STATE`, defaulting to `$SAMSUNG_TV_TOOLKIT/setup`. TV backup directories
are `/opt/minimal-tv-setup/RUN_ID/`; NAS backups stay in its telemetry-backups
folder. Keep the original checkout, site/trust configuration and backups for
unfinished runs. Destination/trust changes and source changes block recovery.
Journal schema 2 includes saved-choice/ledger recovery. Use the original checkout
for schema 1 or unbound journals; do not edit their schema number or upgrade an
unfinished run in place.

```sh
./tv-setup status --device qn90a
./tv-setup apply --device qn90a --resume RUN_ID --yes
./tv-setup rollback --device qn90a --run RUN_ID --yes
```

An unfinished run blocks a new apply. Resume reconciles first: an acknowledged
before-state is different from an uncertain outcome. If readback proves a lost
reply completed, the operation is not resubmitted. If it proves no state change,
inspect the private log and ensure the installer is idle before using
`--resume RUN_ID --retry-unchanged --yes`. Mixed/foreign state stops recovery.
A rolling-back run cannot be resumed as apply; continue rollback. Shared resume
also needs `--shared-nas`. Do not blindly retry when the TV is unreachable.

After device readback succeeds, the run remains pending as
`configuration-applied` or `finalizing` until both saved choices and the ownership
ledger are durable. If storage fills or the host stops during those writes, free
space and resume the same run. This finalization does not contact the TV or submit
device changes again. It refuses to overwrite later local edits. Rollback restores
the previous local records after configuration restoration, including their
absence on a first run. Keep the same site/trust configuration for local recovery.

Interrupted file replacement can leave a run-specific temporary file. A retry
recreates it only when its bytes match the expected complete payload. Unknown,
partial or symlinked staging files stop recovery and remain for private inspection;
they are not automatically deleted. Restored routing/cache state is reloaded even
when a previous inverse completed but its reply was lost.

Rollback checks current state and backup hashes, restoring exact inverse settings
and rows in reverse order. It refuses to overwrite subsequent user changes.
Database copies are recovery evidence, never blindly restored over live databases.
**Configuration restoration is distinct from application recovery.** Optional-app
removals require Samsung Store or an independently verified signed package.
Installed-file archives are forensic only. For managed updates, optionally set
`TV_SETUP_RECOVERY_DIR` to a private directory of old signed packages before apply;
matching packages are checked and copied into the run. Missing reinstall packages
are reported as manual recovery while reversible configuration rollback continues.
Newly installed managed apps are retained for manual review/removal so rollback
cannot delete user data acquired after installation. This also returns exit 3.

There is no general uninstall command: use a run's rollback, then manually review
remaining packages/data/backups. Do not delete journals or backup folders until
you have accepted recovery. Runtime processes may hold old code until restart.

## Activation and verification

`plan`, `status` and ordinary `verify` use read-only SDK/NAS inspection. Private
files may be inaccessible; this is unsupported inspection, not an absent file.
`--privileged-inspection` stages a bounded diagnostic operation in a temporary
private namespace and checks cleanup. Apply uses it for preparation. These are
privileged staging operations even when the inspected state is read-only.

Setup uploads into its own SDK-owned stage, not the agent-owned `on-demand`
directory. The namespace probe temporarily binds the setup archives at the
launcher's expected path; the agent's directory remains unchanged outside that
namespace. Results and read scratch files are created by SDK with mode `0600`
inside a `0700` subdirectory **before** any credentials are written. They are
retrieved through the SDK callback, never uploaded or made owner/world-readable.

Cleanup attempts each known setup file independently. On a later invocation,
known stale stage files are discarded and all new uploads are hash-checked;
unknown files and substituted directories cause refusal. Once root is established,
only the model-specific legacy setup archive and signature in the original
`on-demand` directory are removed. Agent archives are never enumerated or deleted.
A lost connection can still leave cleanup unconfirmed: consult the private
inspection evidence, and do not replay an uncertain operation automatically.

Hardware acceptance for this staging change remains pending: the owner should
repeat step 6 (`./tv-setup plan --device qn90a --privileged-inspection`), confirm the
two leftover setup files are cleared and the agent's files remain intact, then
repeat on S90D. Check the effective stage/result modes, complete privileged reads,
original resource hashes and absence of setup leftovers on both models.

Apply never implicitly reboots. `--activate` explicitly refreshes QN90A Hub or
S90D's AT-HUB helper and records a manual launch. It is not autonomous boot proof.

```sh
./tv-setup verify --device qn90a --privileged-inspection
./tv-setup verify --device qn90a --reboot --wait-seconds 180
```

Reboot verification requests one reboot, then observes a new boot ID, independent
startup evidence, collector freshness and both-device dashboard/history health.
It **never launches Hub or starts the collector** to make verification pass. A
timeout is unverified; the reboot request is not retried. Physical Home/AirPlay,
saver animation, playback, standby/wake and original Samsung Home recovery need
owner hardware acceptance on each model.

`--wait-seconds` bounds the observation period after the single reboot request
returns; the preceding snapshot and reboot request have separate transport
timeouts. All nested observation tools share the remaining budget through a host
process supervisor. Deadline expiry stops those host processes and records
unverified startup. TV-side diagnostic cleanup may be unconfirmed after a lost
connection or forced cutoff: inspect the private evidence before further changes.
Host process tests do not prove TV-side cleanup or firmware scheduling behavior.

## Temporary root sessions and private evidence

One setup transport invocation reuses its locally compiled managed probe and
operation runner, plus its signed acquisition archive. Each operation still checks
the pinned identity, stages and verifies the files, acquires bounded temporary
root access, and removes staging. No privileged daemon or connection is retained.
Resume starts a new local session; a partial or altered cache is refused. The
specialized QN90A app-cleanup runner and opt-in native-acquisition pilot keep their
existing preparation paths.

Privileged output is downloaded from a private result file, with a 16 MiB host
acceptance limit, instead of the toolkit's shortened console preview. Snapshot
reads use a JSON map of hex-encoded values so newlines and quotes cannot confuse
framing. Pairing `token` becomes `token_sha256` before the worker writes its result,
snapshot, journal or diagnostic output. Credential changes still trigger pairing
repair. Malformed pairing records are marked unsupported during planning without
blocking recovery snapshots. Actual install payloads and recovery copies remain private and may contain
credentials; hashes are diagnostics, not replacement credentials.

If a reply is lost, the operation is not retried. The device-side exit trap removes
executables while preserving the result for a serial-scoped download, even on
non-zero exit. Failure output is saved in private evidence; incomplete snapshot
frames are omitted to protect credentials. The host then attempts remote cleanup
and always unlinks the downloaded raw result.
A lost connection can leave cleanup unconfirmed. Preserve the journal and inspect
staging before another operation. Host tests do not establish cleanup on firmware.

### Evidence retention

Keep unfinished runs, journals, verified backups, signing/trust pins and the site
configuration until recovery is resolved. After a successful run, retain the
recovery set until a subsequent release has been accepted on hardware and its
rollback window has closed. Do not delete files referenced by a retained journal.

Local `root-session-*` build caches are removed when the transport closes,
including after Ctrl-C. A forced process kill can leave a cache behind; it may be
removed once that process is gone. These caches are not recovery backups.

For completed runs whose recovery window has closed, delete diagnostic `evidence/`
logs and toolkit `sessions/` after 30 days.
Delete unneeded pairing payloads and backups at the same time; rotate a receiver
credential if its private copies may have been exposed. Cleanup is manual: setup
never ages out recovery data automatically. Keep these directories private and
outside Git, and redact them before sharing. Existing logs are not retroactively
scrubbed by this change.

## Errors and automation

| Exit | Meaning |
| --- | --- |
| 0 | Successful command; plan may propose changes |
| 1 | Configuration, dependency, connection or operation failure |
| 2 | Unresolved inspection/verification, or argparse usage error |
| 3 | Configuration rollback finished; manual application recovery remains |

`--non-interactive` never prompts; mutations require `--yes`. Use `plan --json`
for review and `apply --json --yes` for automation. Successful JSON commands emit
one JSON document on stdout; progress/errors go to stderr. Failed commands may
have no JSON document, or a proposal emitted before failure: always check exit
status. Raw tool output and unexpected exception details stay in private logs.
Never attach journals, pairing files, root scripts, SDK logs or signing logs to
public issues without manual redaction.

Connection failure: check the site address, Developer Mode host route and SDB.
Missing local tool: run `scripts/check-dependencies.py` and rebuild the toolkit.
Unsupported resource/signature: stop and review the exact model/firmware or trust
entry; there is no force flag. Dirty upstream transport: use a clean pinned
checkout. Partial operation: preserve logs, inspect state, then resume/rollback.
Unfinished root staging: inspect cleanup evidence; never rerun a mutation merely
to clear staging. See [security guidance](../../SECURITY.md).

### Private Netdata origin

When Netdata uses a NAS address or port instead of the container hostname,
set optional `nas.netdata_url` in private `site.json` to its credential-free
HTTP(S) origin. Setup renders that origin into the dashboard server default and
Netdata link, and hashes the rendered files for drift detection and recovery.
Omitting it retains the generic container default. Keep the site file used for
each recovery run: changing NAS settings changes the recovery binding.

### Root staging and reboot contract

The setup engine and autonomous agent share the firmware launcher's fixed
`/home/owner/share/tmp/sdk_tools/on-demand` archive directory. It is a persistent
container: neither removes it. Each owns only its named archive and signature;
setup refuses occupied archive slots, symlinks and non-directory parents. Agent
archives are left untouched. Model-specific setup prefixes remain exclusive and
are removed on failure as well as success, including partial staging failures.

Upload directories use ordinary `mkdir`, as on the working pre-Phase-2 path,
without forcing a mode or umask. The stage capture records `stat -c '%U:%G:%a'`
for the prefix in its private `sessions/*/output.txt` evidence log, so the next
hardware session can confirm the actual owner, group and mode. Directory mode
is not the credential boundary: root applies `0600` to `result.txt` and `read.tmp`
after upload and before any secret is written; known payloads and credentials are removed by the remote
trap and final cleanup. Downloaded results are unlinked in a local `finally`.
These changes address the QN90A firmware 2301.1 session findings but require
a fresh acceptance run on **both TVs** before deployment.

Reboot verification submits one 10-second systemd timer with one-second accuracy that calls deviced's
`Reboot` method through `/usr/bin/busctl`. The service explicitly uses UID/GID 0,
the `System` SMACK label and the system kdbus address via `--setenv`. It does not use `systemctl reboot` or a shell
background child, which the native worker correctly kills at EXEC completion.
A lost submission reply remains uncertain and is never automatically retried.
