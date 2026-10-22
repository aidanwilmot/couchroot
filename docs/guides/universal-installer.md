> New pure-native installation and preparation are retired. `--launcher native`
> remains only for status, verification and recovery of existing journals. Use
> [the launcher guide](choosing-a-launcher.md) for current choices; historical
> native preparation examples below do not run on this release.

# Couchroot command-line installer

`bin/couchroot-install` provides one entry point for choosing, preparing, installing
and recovering the signed web or pure-native C launcher. The WebView experiment
uses its [separate tools](../../native/webview/README.md). Web uses the existing setup engine. Native uses
that same journal engine with an explicitly enrolled QN90A baseline and pinned
root-agent transport. **Native installation has offline validation only; it has
not been deployed or tested on a TV.** See [native installation](native-installation.md).

## Survey a TV before installing tools

`survey HOST` needs no private site configuration, toolkit, signing material or
SDB. It makes one bounded read-only request to `http://HOST:8001/api/v2/` and
compares only non-identifying model and platform fields against the reviewed
profiles:

```sh
bin/couchroot-install survey 192.0.2.20
bin/couchroot-install survey 192.0.2.20 --json
```

The verdict is `exact_model` when both model code and full platform code match a
profile. This is preliminary: the TV's exact firmware is confirmed later through
SDB, and all existing identity, runtime, hash, signature and package safety
checks still apply before operations. `same_platform_family` means only that a
syntactically valid platform code shares its first two underscore-delimited
tokens with a profile (for example, `24_PTM_`); it is informational and never
indicates support. Other results are `unknown`. The survey names observed field
mismatches, does not expose physical identifiers, and does not contact SDB. It
reuses the toolkit's existing `developerMode` and `developerIP` field handling
to report Developer Mode as enabled, disabled or unknown, and whether a
developer host is configured; it never prints the TV's configured host or any
IP address in survey output.

An unsupported result is a successful survey, not an install error. Use
`survey HOST --report DIR` to create a redacted report and follow
[the porting guide](porting-to-a-new-tv.md) before considering a profile change.
The survey does not infer model support from a family match and does not guess
additional identity API fields.

### Save a redacted report

Use a new output directory outside the checkout. The command creates it with
mode `0700` and writes a JSON inventory plus Markdown ready to paste into an
issue; each file has mode `0600`. Both files omit the TV address, device ID,
Developer Mode host address, serials, tokens and all other IP addresses,
including this computer's. Review the files before sharing or adding notes.

```sh
bin/couchroot-install survey TV_ADDRESS --report /private/tv-report
bin/couchroot-install survey TV_ADDRESS --report /private/tv-report --profile-skeleton
```

The optional profile skeleton marks itself `UNVERIFIED`, leaves all unverified
identity, capability, layout and hash fields null, and shows the observed model
and platform differences from the nearest profile. If no reviewed profile is
close enough to compare, it still writes the report and skeleton with no
comparison. The profile registry rejects that marked file if it is copied into
`tvsetup/profiles/`; it is a research template and grants no support.

### Check the TV and create private configuration

`doctor --tv HOST` is an optional read-only check of the public identity
endpoint on port 8001, Developer Mode state and host, and TCP reachability of
SDB on port 26101. It does not need `site.json` and does not change the TV. It
reports a one-line fix hint for each failed check and, when route lookup works,
shows this computer's routed IPv4 address in text and JSON so you can enter it
in the TV's Developer Mode settings. It never displays the TV's configured
Developer Mode host. Survey and report output still contain no IP addresses.
The existing
`doctor --device ...` form continues to check host prerequisites only.

After an `exact_model` survey, `init HOST` can create the default private
`~/.config/samsung-tv-hub/site.json` with the discovered device identity. It
supports IPv4 input, refuses nonmatching models and refuses to overwrite an
existing file. It writes local configuration only; no TV setting changes.

The `trust` helper calculates SHA-256 pins from supplied certificate files. It
does not inspect signed packages or enroll the result automatically; inspect
the author and distributor certificates independently, then add the generated
entry to private `trust.json`:

```sh
bin/couchroot-install trust --device qn90a --signing-profile MyQN90A \
  --author-cert /private/author.cer \
  --distributor-cert /private/distributor.cer
```

This helper reads local files only. Certificate enrollment and package signing
still use the normal setup process and its existing trust checks.

| Target | Web | Native |
| --- | --- | --- |
| QN85QN90AAFXZA, T-NKM2AKUC-2301.1 | Prepare, inspect, apply, verify, resume, rollback | Existing-journal status, verify, resume, rollback only; new installation and preparation are retired |
| QN55S90DAFXZA, T-PTMDAKUC-0090-2130.0 | Prepare, inspect, apply, verify, resume, rollback | Unsupported; rejected before any operation |
| Other models/firmware | Unsupported | Unsupported |

“Universal” describes a shared interface, not support for arbitrary Samsung TVs.
This implementation has offline tests, not new hardware acceptance. The existing
[setup acceptance limits](tv-setup.md) still apply.

## Start offline

Use Python 3.12+ on macOS or Linux from the source checkout. No private site file,
certificate, toolkit, root agent, TV or NAS is needed for a plan:

```sh
bin/couchroot-install plan --device qn90a --launcher native
bin/couchroot-install plan --device s90d --launcher web --json
bin/couchroot-install doctor --device qn90a --launcher native
bin/couchroot-install doctor --device s90d --launcher web --stage prepare
bin/couchroot-install apply --device qn90a --launcher web --dry-run
```

`doctor` defaults to installation prerequisites. `--stage prepare` checks the
Python-only offline bundle path without requiring .NET or signing tools. Native
installation consumes an existing bundle and enrolled root agent, so its doctor
also does not require a local .NET SDK; provisioning the web fallback and agent
still requires managed setup. Docker (`prepare --build-native`) and Node
(`prepare --web-state`) are reported as conditional tools and do not fail the
basic check. Web installation still checks the pinned .NET SDK for its helpers.
The host-prerequisite doctor does not contact a TV. `doctor --tv` makes only the
read-only identity request and SDB TCP reachability check described above; no
doctor command validates enrollment or a Docker image.

Launcher choice is always explicit. `plan` prints the installation recipe and its
blockers; it does **not** inspect current device state. `doctor` checks host/tool
presence and the pinned .NET SDK version when required, without reading private
configuration. It does not certify an available native build image, signing trust or TV ABI.
`inspect` is the separate, explicitly connected preflight command.

The separate `bin/tv-setup` full-setup flow starts with launcher integration
only. Cleanup and telemetry changes need an explicit component or configuration
choice. Broader defaults and saved choices take effect only after a matching,
completed schema-2 full-setup journal with `scope: setup`, matching device and
destination/signing trust, and every recorded action applied; UI, launcher-only,
recovery and trial runs do not qualify. A completed no-op full setup counts.
See [first-run setup defaults](tv-setup.md#configure-your-installation).

## Prepare review artifacts

Always use a **new directory outside the checkout**. Existing directories and
symlink destinations are refused. Failed builds/conversions do not publish a
bundle. Output directories are private (mode 0700); keep preference candidates
and native binaries out of Git.

```sh
bin/couchroot-install prepare --device s90d --launcher web \
  --output /private/couchroot-web-review

bin/couchroot-install prepare --device qn90a --launcher native \
  --native-binary /private/build/native-hub \
  --output /private/couchroot-native-review

# Alternative: use the existing local Docker image/build recipe, with no network.
bin/couchroot-install prepare --device qn90a --launcher native \
  --build-native --output /private/couchroot-native-build
```

Every bundle contains a deterministic, model-specific **unsigned** web WGT,
`web-choices.json`, and a manifest with payload sizes/hashes, target profile,
readiness and outstanding blockers. The web WGT includes the same service adapter
and QN90A idle adapter selected by the setup planner. It is not installable until
signed for the target TV.

A native bundle additionally contains the supplied/built ARM executable. Header,
EABI, load-segment bounds and executable entry-point checks reject obviously wrong
or malformed inputs. These checks do not establish firmware ABI compatibility or
binary provenance. An owner-supplied binary is explicitly marked as having unknown
correspondence to the current checkout. The local build uses
[native-hub/build.sh](../../research/archive/native-hub/build.sh), its existing Docker image and
GLIBC baseline check; the installer does not pull images or fetch dependencies.

For a one-time native preference candidate, add:

```sh
--web-state /private/exported-localstorage.json
```

This invokes the existing bounded offline converter (Node required). It accepts an
explicit JSON export, not a browser database or TV address. It does not copy the
original export into the bundle, change web preferences, or overwrite native
preferences. Native installation stages the candidate only when preferences are
absent; existing preference bytes are retained, including edits made by the Hub.
Recovery retains staged preferences and payloads while restoring the boot hook.

**Web bundles are review artifacts.** Web `apply` rebuilds and signs from the
current checkout. Native `apply` consumes and verifies the native ELF/preference
inputs from its bundle; the unsigned web WGT is never installed by the native backend.
No bundle command signs, installs, starts an app, changes a hook or reboots a TV.

## Web installation and recovery

Configure private site identity, signing trust and the vendor toolkit using the
[setup guide](tv-setup.md). These commands **contact the selected TV**:

```sh
bin/couchroot-install inspect --device s90d --launcher web
bin/couchroot-install apply --device s90d --launcher web --yes
bin/couchroot-install status --device s90d --launcher web
bin/couchroot-install verify --device s90d --launcher web
bin/couchroot-install resume --device s90d --launcher web --run RUN_ID --yes
bin/couchroot-install rollback --device s90d --launcher web --run RUN_ID --yes
```

`--site PATH` selects private connection/trust configuration. `--json` provides
machine-readable output. Add `--activate` to `apply` only when explicitly opening
Hub is desired. There is no implicit reboot. Physical Home, panel/audio, standby
and reboot behavior require separate owner acceptance.

The installer selects Hub, Home, AirPlay and startup only. It ignores saved
artifact overrides, cleanup and NAS selections. S90D startup still uses its
existing combined startup helper; its dormant saver/splash integration is
preserved by the shared planner. Full setup choices remain unchanged; the shared
ownership ledger records the installed artifacts. Use `tv-setup` explicitly for
optional cleanup, telemetry, screensaver or NAS work.

Web runs use scope `launcher-web` in the shared setup journal and the same device
locks, pending-run checks, identity/trust pins, backups, readback and recovery.
Resume uses journaled choices without rerunning builds. This entry point refuses
to recover unrelated UI/full-setup/private-native runs. Use their original entry
point and checkout. Missing signed recovery packages retain the existing manual
application recovery result (exit 3).

This is **not a native-to-web migration command**. Existing private native trials
must be recovered using their original retained driver/journal before installing
a different startup arrangement. Do not use web installation as a substitute for
rolling back native boot hooks.

## Native installation and recovery

An optional `prepare --native-telemetry-binary PATH` creates a
[local telemetry integration candidate](native-telemetry.md). It supports only QN90A/native
and includes journaled handoff/recovery, requiring an already installed current signed
adapter. It has local tests only; launcher-only bundles
retain their existing behavior.

The native transaction now captures immutable inputs, backs up the enrolled hook,
stages/verifies payloads, switches the hook last and supports journaled resume and
rollback. It requires an already configured signed web fallback and an explicit
baseline/dependency enrollment. Native-to-native private trial adoption is refused.

See [native installation and recovery](native-installation.md) for enrollment,
commands, interruption handling, retained files and the hardware acceptance limits.
Native `status --run RUN_ID` is local-only. Native apply never launches or reboots;
source re-arm requires an explicit opt-in and only runs on a later native boot.

## Exit codes

- **0:** offline recipe/preparation completed, or the selected web/native operation succeeded.
- **1:** invalid selection/input, build/storage failure, or shared engine failure.
- **2:** missing doctor prerequisites, unresolved
  web preflight/verification, or command-line usage error.
- **3:** shared configuration rollback completed with manual app recovery remaining.

For onboarding commands, an unsupported survey is still a completed survey and
returns **0**. A survey network/response failure or an `init` refusal returns
**1**; usage errors return **2**. `doctor --tv` returns **0** when all checks
pass and **2** when one or more reachability or Developer Mode checks fail.

A successful offline `plan`, `prepare` or `--dry-run` does not mean deployment is
ready for your TV. Check target enrollment, `hardware_checked`, `requirements` and
`blockers` in JSON; device preflight still applies.
