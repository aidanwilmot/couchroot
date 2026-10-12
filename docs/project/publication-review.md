# Source publication review — 2026-10-11

Couchroot starts with a new Git repository and the `splitcipher` public noreply
identity. Previous development history, private remotes and work-account metadata
were not imported. The original development checkout remains separate.

## Publication boundary

- Included tracked and non-ignored source, reviewed documentation, synthetic
  fixtures, existing sanitized inventory and retained third-party notices.
- Excluded old Git objects, external skill symlinks, dependencies, build outputs,
  private site/trust configuration, credentials, signed packages, vendor binaries,
  deployment journals and raw device captures.
- Replaced remaining personal filesystem references. The historical D2TV package
  builder now requires explicit snapshot and package arguments instead of private
  default paths. Synthetic test UUIDs use the reserved zero-prefix convention.
- README images are screenshots of the local simulated browser workbench, not
  photographs or captures of a live television or management dashboard.

## Checks

The value-redacted privacy heuristic passes against the staged source. Reserved
`.invalid` email-like fixtures are ignored explicitly; other email matches remain
reported. Gitleaks identified two generic-key matches in existing inventory:
`/etc/passwd` and `host-passwd.original` file hashes. Both are 64-character SHA-256
hex digests, not passwords or API credentials. No other matches were reported.
No scanner can guarantee the absence of secrets; findings were reviewed rather
than silently suppressed.

Local validation: 200 Python setup tests, 20 telemetry/inspector Python tests,
85 JavaScript tests, and three root-protocol checks passed. The targeted tests
for the explicit-path builder also passed. Screenshots were generated and the
three README images visually inspected. Documentation entry links and staged
whitespace were checked. Hosted CI and its native reproducibility matrix are
separate checks; publication is not a claim that all hardware acceptance is done.

## Release scope and attribution

This is experimental source, not a stable signed binary release. Full setup,
recovery and toolchain portability limits remain in the project guides.
Original work uses 0BSD; bundled upstream licenses remain beside their sources.
See [Sources & Credits](../../CREDITS.md) and [licensing](../../LICENSE-STATUS.md).
GitHub private vulnerability reporting is enabled; see [Security](../../SECURITY.md).
