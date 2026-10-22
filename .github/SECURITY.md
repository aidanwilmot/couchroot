# Security

This unofficial project uses a firmware-specific privilege chain on TVs you own
or administer. This is an experimental source release; the full hardware acceptance matrix
in [release readiness](../docs/project/release-readiness.md) remains incomplete. It is not
Samsung-supported software.

The setup runner can execute privileged configuration changes through a bounded
temporary mount namespace. It stages diagnostic assemblies and a disposable key,
checks firmware/runtime/launcher hashes and verifies cleanup. It is not merely an
identity probe. Developer Mode and SDB access expose a powerful management path;
keep the TV, NAS and management host on trusted networks. Do not expose SDK or
receiver administration ports to the Internet. Telemetry is opt-in for missing
preferences, authenticated and certificate-pinned; dashboard HTTP is intended
for a trusted management network.

Model/firmware guards, independent signing pins, full archive signature/digest
verification, reviewed cleanup allowlists and backup checks are mandatory.
There is no override to disable them. Root privileges do not bypass every SMACK,
DRM or firmware policy. The optional autonomous root prototype is a separate, explicitly enrolled service;
its authenticated API can execute owner-supplied shell commands within the root
worker context. Treat its client certificate and key as administrative credentials.

Keep site/trust files, certificate stores, signed packages, private keys, tokens,
journals, evidence, raw databases, dumps and vendor libraries outside Git. Use
private 0700 directories/0600 files. Backups can contain credentials and app data.
Do not paste command output, identifiers or journals into public bug reports.
The included privacy scanner reports locations/categories, never matching values;
it is a heuristic review aid, not proof that disclosure is safe.

## Reporting

Use [GitHub private vulnerability reporting](https://github.com/splitcipher/couchroot/security/advisories/new).
Do not submit exploit details or private device evidence in public issues.
Provide the affected commit, exact model/firmware, impact and a redacted minimal
reproduction. Do not send signing keys, credentials or complete private logs.
No response-time or support-lifetime commitment has yet been made.

If sensitive material entered Git, stop publication, assess exposure, and rotate
any affected credential. Editing the latest file does not remove old Git objects.
History rewriting and publication require separate explicit owner authorization.
