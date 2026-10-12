# Couchroot

**Your couch. Your TV. Your launcher.**

A minimal Samsung Tizen launcher, a read-only TV inspector, and an experimental
on-TV root agent. Built through hands-on work with a QN90A and an S90D.

[Get started](#try-the-launcher-on-your-computer) · [TV setup](docs/guides/tv-setup.md) ·
[Root agent](research/autonomous-root/README.md) · [Sources & credits](CREDITS.md) ·
[0BSD license](LICENSE)

![Minimal Hub with a full app catalog and remote focus](docs/images/launcher.png)

*Actual launcher source running in the local browser workbench with simulated
apps. Screenshots contain no live device data.*

## What's here

- **Minimal Hub:** an offline, remote-first launcher with editable favorites,
  move/remove controls, compact layout, clock, settings and a Samsung Home fallback.
- **TV inspector:** read-only app, process and startup inspection alongside the
  telemetry dashboard. See [telemetry and inspection](docs/guides/telemetry.md).
- **Autonomous root agent:** a separate signed service that reacquires a temporary
  root context through TV-local SDB. It uses certificate-pinned HTTPS, authenticated
  loopback messages, bounded retries and a durable request journal.
- **Setup and recovery tools:** explicit device profiles, firmware/hash checks,
  signature verification, private configuration, backups and recovery journals.
- **Research:** documented experiments, including failures and model differences.

## A quieter home screen

![Minimal Hub settings](docs/images/settings.png)

Use the remote's arrows to choose, OK to open, and Back to return. Favorites are
editable from the TV. The Samsung Home shortcut remains available.

![Compact launcher with clock](docs/images/compact.png)

## Try the launcher on your computer

No TV, signing certificate or root access is needed for the browser preview.
Requires Node.js 20+ and npm.

```sh
git clone https://github.com/splitcipher/couchroot.git
cd couchroot
npm ci
npm run dev
```

Open <http://127.0.0.1:8766>. Select a scenario, click the preview, then use arrow
keys, Enter and Escape. The workbench serves the same `web/` source as the TV
package, with simulated platform APIs. It does not contact a TV or NAS.

For screenshots and browser tests:

```sh
npx playwright install chromium
npm test
npm run screenshots
```

See [UI development](docs/guides/ui-development.md) for scenarios and remote-navigation
checks. Python 3 is also required to build an unsigned package with `npm run package`.

## Putting it on a TV

Start with the [setup guide](docs/guides/tv-setup.md), [compatibility notes](docs/guides/device-compatibility.md)
and [recovery guidance](docs/guides/tv-setup.md#apply-interruption-and-recovery). If you already have an installation,
use the separate [UI deployment guide](docs/guides/ui-deployment.md).

You supply your own device addresses, Developer Mode setup, SDK tools and signing
credentials. Examples use reserved addresses. Site/trust files, keys, certificates,
signed packages and deployment journals stay outside Git. Native helpers use the
.NET SDK pinned in `global.json` and Python dependencies in `tvsetup/requirements.txt`.

**Experimental source release, not a universal installer or firmware jailbreak.**
Only exact reviewed profiles are intended for device operations. Samsung signing
privileges, SDK admission and startup behavior can vary by firmware. Root does
not bypass every SMACK, DRM or firmware restriction.

| Hardware | Recorded root-agent firmware | Observed behavior |
| --- | --- | --- |
| QN90A | `T-NKM2AKUC-2301.1` | Reboot startup, root acquisition, worker and registered-service recovery |
| S90D | `T-PTMDAKUC-0090-2130.0` | Reboot startup, root acquisition, worker and registered-service recovery |

These observations are not a promise for every size, region or firmware.
The [agent notes](research/autonomous-root/README.md) record exact tests and limits,
including remaining cold-power and recovery cases. Comprehensive installation
acceptance remains work in progress; see [release readiness](docs/project/release-readiness.md).

## How the pieces fit

```mermaid
flowchart LR
    PC[Management computer] -->|Signed setup and recovery| TV[Samsung TV]
    HUB[Minimal Hub] -->|Optional telemetry| NAS[Receiver and read-only dashboard]
    TV --- HUB
    SERVICE[On-TV administration service] -->|Loopback SDB| ROOT[Temporary root worker]
    PC -->|Certificate-pinned HTTPS| SERVICE
```

The root agent is separate from the launcher and dashboard. A boot service
reacquires privileges; it does not permanently patch the firmware. If the service
cannot start while Developer Mode points to loopback, recovery can require the
remote: restore Host PC IP to your management computer and restart. Read the
[agent recovery instructions](research/autonomous-root/README.md) before enabling it.

## Repository map

| Path | Purpose |
| --- | --- |
| `web/` | Shipped launcher UI and platform adapters |
| `preview/` | Local browser workbench, fixtures and screenshot capture |
| `tvsetup/`, `tv-setup`, `deploy-ui` | Setup, signing integration, deployment and recovery |
| `research/autonomous-root/` | Agent, client, payload sources and upstream provenance |
| `research/s90d-telemetry/` | Shared collector, inspector, receiver and dashboard |
| `docs/` | Setup guides, compatibility and investigation records |
| `tests/` | Offline UI, protocol, setup and recovery tests |
| `examples/` | Public configuration templates |

Historical research scripts are not the supported setup entry point. The telemetry
folder's original model name is retained even though the integration serves both TVs.

## Security and contributions

Use only with devices you own or administer. Keep management endpoints on a trusted
network. Never post raw logs, device identifiers, keys or signing material in issues.
See [Security](SECURITY.md) and [Contributing](CONTRIBUTING.md).

This repo starts from a reviewed source snapshot rather than the development Git
history. See the [publication review](docs/project/publication-review.md) for what was checked
and the limits of those checks.

## License and thanks

Original Couchroot work is **[0BSD](LICENSE)**: use it with or without attribution.
Bundled third-party code retains its own licenses, including Vetro's MIT notices.
See [licensing details](LICENSE-STATUS.md).

Thanks especially to [Vetro](https://github.com/andrearicci93/vetro) and
[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) for the transport,
root payloads and research that helped make this possible. [Sources & Credits](CREDITS.md)
records included code, development references and tools.

Unofficial; not endorsed or supported by Samsung. Product names and marks belong
to their respective owners.
