# Couchroot telemetry sources

- `native-collector/`: QN90A basic C collector and its offline build/test inputs.
- `s90d-collector/`: shared managed collector, built for both firmware runtimes.
- `qn90a-startup/`: existing signed settings/service adapter.

The shared setup engine owns packaging, installation and recovery. App/package
IDs, settings keys and on-TV paths are unchanged. The receiver and historical
experiments remain in `research/`; see the [telemetry guide](../docs/guides/telemetry.md)
and [native integration guide](../docs/guides/native-telemetry.md).

Compiler path maps retain the former source paths in debug metadata so the moved
collectors and adapter keep byte-identical shipped binaries. These are build-time
identities, not runtime filesystem dependencies. Recover unfinished setup journals
with their original checkout; a source-layout change does not migrate a journal.

[Byte-identity evidence](byte-identity.json) records the baseline, SDK, collector
build image and every compared output hash. Both before/after trees also passed
`python3 scripts/check-reproducible.py --component all`. The Hub hashes are the
shared signed-path inputs; no signing credentials or hardware were used.
