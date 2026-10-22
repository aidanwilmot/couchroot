# Shared Hub telemetry service

This historical directory now contains the service and no-window relay for **both
S90D and QN90A**. Build for `net6.0` on S90D and `netcoreapp3.1` on QN90A. The
collector source remains in `telemetry/s90d-collector`.

Hub sends public enabled/receiver URL preferences after initialization and when it
returns to the foreground. `MiniTelemetry.Start` accepts only `MiniHub001.Hub`,
forwards those preferences to `MiniTelemetry.Service`, and exits. The service
accepts only its relay and keeps one collector running independently of Hub.
A later Hub launch can restart a collector that exited. Early preference/API
failures use bounded startup retries; foreground entry starts a new retry budget.

The relay is needed because Samsung forbids direct cross-package service launches.
`ui_app_main` comes from `libcapi-appfw-application.so.0`; `service_app_main` comes
from `libappcore-agent.so.1`. Both calls need argv[0]. App-control extras may arrive
as scalars or single-element arrays; both are handled.

Pairing and mirrored preferences live in `MiniTelemetry/data`, mode 0600, UID 5001,
SMACK `User::Pkg::MiniTelemetry`. Credentials never enter Hub or its package.
Status is `/tmp/minimal-telemetry-DEVICE/status.json`; the collector holds a lock
in the same directory. Native single-instance enforcement also remains enabled.

Use the shared setup engine with private site/signing configuration:

```sh
bin/tv-setup plan --device s90d --components hub,telemetry --privileged-inspection
bin/tv-setup apply --device s90d --components hub,telemetry --yes --activate
bin/tv-setup verify --device s90d --components hub,telemetry --privileged-inspection
bin/tv-setup rollback --device s90d --run RUN_ID --yes
```

Substitute `qn90a` for the other TV. Historical `manage.py` commands are retired.
See [telemetry operations](../../docs/guides/telemetry.md) for migration,
recovery, verification limits and model-specific startup behavior.
