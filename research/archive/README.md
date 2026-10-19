# Archived experiments and manual checks

These files are retained for reference; ordinary builds and CI do not run them.
Moving them does not retire any shipped collector, launcher or recovery path.

| Location | Original purpose | Status |
| --- | --- | --- |
| `native-telemetry/probe/` | Native identity/lifetime probes, resident experiment, and managed owner/launch adapters | Historical capability experiments, not the production collector |
| `system-screensaver/verify-render-loop.c` | Instrument the native saver render loop | Manual diagnostic, outside the maintained CI suite |
| `system-screensaver/verify-shader.cjs` | Render actual C simulation batches and GLSL in a browser | Manual visual check; still points at the active source |
| `s90d-telemetry/dashboard/verify.cjs` | Live receiver dashboard smoke test with an outage mock | Requires an explicitly authorized receiver; never run as an offline test |
| `qn90a-screensaver/verify-web.cjs` | Browser checks of the built Asteroids package | Historical manual check; requires generated saver assets |

Production saver reproducibility and maintained collector/receiver tests remain
in CI. These archives were not run against any TV or NAS during the move.
