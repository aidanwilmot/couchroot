# Contributing to Couchroot

Original contributions are made under the project's [0BSD license](LICENSE).
Preserve existing third-party notices and document the origin of copied code.

Use an isolated branch. Keep changes focused, document behavior and add tests for
meaningful failures. Run the offline checks in docs/project/release-readiness.md. Do not
contact or modify someone else's TV or NAS, and do not treat mocked device state
as hardware validation. Live mutations require the device owner's authorization.

CI runs web/setup checks on Node 22/24 and Python 3.12/3.14 on Linux, alongside
managed fallback, native worker, ARM launcher builds and QN90A saver checks.
A focused macOS 14/Python 3.12 job covers setup, installer and UI deployment.
ARM64 parity runs the real managed/native workers and process observer in an
isolated container. Actions and pulled images are pinned; Dependabot proposes
weekly updates. CI runs on pull requests and `main`; use the manual workflow
trigger for a branch without a PR. See the [remaining opt-in suites](tests/worker-parity/README.md#ci-coverage)
and [validation details](docs/project/release-readiness.md#validation-and-reproducibility).

New firmware/model support needs a separate reviewed profile, original resource
hashes, model-specific transport evidence and a documented recovery path. Never
weaken firmware, signature, package protection or cleanup allowlist checks to make
a test pass. Never copy S90D writable-cache assumptions or offsets into QN90A.
NAS changes must preserve all device identities, credentials and history.

Submit only redacted reproduction steps. Fixtures use reserved example addresses
and synthetic identities/tokens. Never commit real journals, signing material,
raw backups, vendor binaries or device/account identifiers. Follow SECURITY.md
for vulnerability reporting. A change description must distinguish local tests,
read-only observations and owner-authorized hardware mutations.
