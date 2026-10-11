# S90D telemetry to TrueNAS Netdata

> The deployed implementation now supports both TVs. See
> [shared monitoring and current operations](samsung-tv-telemetry.md).
> The remainder records the original S90D rollout and its recovery artifacts.

The TV runs a small managed collector through Samsung's existing signed
`/usr/bin/dotnet` host. The managed assembly is our code, not a Samsung-signed
binary. It does not install a native Netdata agent on Tizen.

## Dashboard controls

Minimal Hub 0.3.11 adds **Settings → TV monitoring**:

- Monitoring On/Off pauses or resumes sampling and transmission.
- Receiver URL defaults to `https://192.0.2.20:20490/v1/s90d`.
- Save applies on the next ten-second collection cycle; no reboot is required.
- Cancel leaves the saved preferences alone.

The app atomically replaces `wgt-private/telemetry.json` using the public Tizen
filesystem API. On this TV it resolves to
`/opt/usr/home/owner/apps_rw/MiniHub001/data/telemetry.json`. The schema is:

```json
{"schema":1,"enabled":true,"endpoint":"https://192.0.2.20:20490/v1/s90d"}
```

Only HTTPS, a credential-free URL, and the `/v1/s90d` path are accepted. The
receiver must present the certificate paired during installation. Changing the
address of the same receiver is supported; a different server/certificate needs
administrative pairing and a matching network rule. The UI never receives the
authentication token or certificate private key. The dashboard still has
`connect-src 'none'` and no Internet privilege; its two new privileges are
filesystem read and write.

## Collection and startup

`research/s90d-telemetry/collector/Program.cs` reads bounded snapshots of
`/proc/stat`, `/proc/meminfo`, `/proc/net/dev`, `/proc/diskstats`, uptime and its
own CPU/RSS. It does not inspect app content, URLs, viewing history or credentials.
Sampling is every ten seconds, at nice +10, with a three-second network deadline.
HTTPS connections are reused. A failed send backs off to at most five minutes;
there is no accumulating queue. Preferences continue to be checked every ten
seconds during an outage or while monitoring is paused.

The build combines the existing screensaver helper and unmodified splash fix
with an optional resident telemetry thread. AT-HUB remains `Type=simple` and
adds no service-ordering dependency. Collection starts only after uptime reaches
60 seconds and Samsung has requested dashboard resume. A RAM-backed file lock
prevents duplicate collectors. The opt-in file `/opt/minimal-telemetry/enabled`
controls installation-level enablement; deleting it ends the collector. Dashboard
Off keeps the small service available so it can react to On later.

Credentials, collector and backup live in root-only `/opt/minimal-telemetry`.
Runtime status and PID live under `/run/minimal-telemetry`; telemetry adds no
periodic flash logging or on-TV metric database. Native executable policy,
firmware binaries, and the existing service cache are unchanged by this feature.

## TrueNAS

TrueNAS app **s90d-telemetry** is a bounded Python HTTPS receiver in a container,
using the already-installed Netdata image pinned by digest. It runs as UID 65534,
with a read-only root filesystem, no capabilities, 96 MiB memory limit,
0.25 CPU limit, 16-PID limit and automatic restart. Its own TCP health check
replaces the base image's Netdata health check. It listens on
`192.0.2.20:20490`, accepts only the TV's source IP and bearer token, caps requests
at 64 KiB, limits concurrent connections to four and keeps one latest snapshot.
The private certificate pin authenticates the server even before TV clock sync.

The existing Netdata v2.11.1 agent discovers `custom-plugins.d/s90d.plugin`
without a restart. Nine `s90d.*` charts appear under the **NAS's existing node**,
not as a separate native Netdata child: CPU, memory, network, eMMC, uptime,
collector CPU/RSS, availability and sample age. Open <http://192.0.2.20:20489/> and
search for S90D. Normal NAS retention settings apply.

Rates use actual TV uptime deltas; a reboot, counter reset or gap over 45 seconds
breaks the baseline. Missing/stale snapshots are not repeated as fresh CPU/I/O
measurements. Availability becomes zero after 35 seconds without a snapshot.
Disk rates include whole eMMC devices, never those devices plus their partitions.

Files reside within the existing persistent Netdata config mount:

- `s90d-receiver/`: receiver code, pinned certificate, protected credentials and app spec.
- `custom-plugins.d/s90d.plugin`: executable Netdata plugin.
- `custom-plugins.d/s90d-code/metrics.py`: parser and rate calculation.
- `custom-plugins.d/s90d-data/latest.json`: latest received snapshot.

Receiver credentials are not committed. Local protected deployment state is at
`~/.local/share/samsung-tv-research/telemetry/`.

## Network exception

The NAS guardrail initially blocked both its existing Netdata port and the new
receiver. After a binary backup and sanitized export, one disabled rule was
staged, enabled, verified and committed in RouterOS safe mode:

```routeros
/ip firewall filter add chain=forward action=accept connection-state=new protocol=tcp src-address=192.0.2.12 dst-address=192.0.2.20 dst-port=20490 in-interface=wifi out-interface=data comment="s90d-telemetry-20260920 receiver" place-before=[find where comment="codex truenas guardrail drop other new to truenas"]
```

Existing established-connection rules handle replies. No NAS administration,
Netdata UI, WAN exposure or subnet-wide allowance was added. Router backup:
`pre-s90d-telemetry-20260920`; before/after exports are stored privately.

## Build, deploy and rollback

Build with `python3 research/s90d-telemetry/build.py`. First installs use
`deploy-nas.py` and `deploy-tv.py`; they refuse to overwrite an existing
installation. `update-tv.py` checks the recorded deployed hashes before changing
either assembly. Deployment uses the pre-existing private root transport and
verifies its cleanup. There is no root command listener on the TV.

`python3 research/s90d-telemetry/rollback-tv.py` stops telemetry and restores
`/opt/minimal-telemetry/Boot.before.dll`, preserving the splash fix and screensaver.
The prior signed dashboard package is saved privately under `telemetry/rollback/`;
an in-place install restores the UI without uninstalling the app or deleting
shortcuts. Disable/remove the TrueNAS `s90d-telemetry` app and remove only the
three `s90d` plugin paths to stop NAS collection. Remove the router rule by its
unique comment:

```routeros
/ip firewall filter remove [find where comment="s90d-telemetry-20260920 receiver"]
```

## Validation

- .NET collector and composite helper build with warnings treated as errors.
- 42 dashboard tests pass, including endpoint validation, failed writes, Save,
  Cancel and text-field remote navigation.
- Six Python tests cover authentication, source filtering, request throttling,
  malformed payloads, atomic ingestion, actual elapsed-time rates, reboots,
  counter resets and outage gaps.
- Real TV dashboard Save/readback passed; favorites, sound, clock and layout
  preferences remained present. Final dashboard runs with debug disabled.
- TV HTTPS reaches the receiver; unauthenticated TV requests receive 401 and
  requests from another host receive 403. Netdata API returns live S90D charts.
- Initial keep-alive samples measured 0.16–0.20% of one core and roughly 20 MiB
  resident memory after warmup; these are short measurements, not a long-term
  performance guarantee. Startup/TLS reconnection temporarily costs more.

### Reboot verification, 2026-09-20

Boot ID changed from `00000000-0000-4000-8000-000000000018` to
`00000000-0000-4000-8000-000000000019`. The native splash completed with
acknowledgement and resume true at 22.16 seconds. The first telemetry sample was
at approximately 62.48 seconds; by 122.49 seconds, seven sends succeeded with
zero failures. The dashboard was foreground, the Asteroids renderer overlay
matched its expected hash, and `DN_spotlight-ss` was running. Endpoint and enabled
preferences survived the reboot. Resident memory settled to about 22 MiB by
142 seconds after a startup peak of about 30 MiB in the sampled data.

Final collector SHA-256:
`0ce858ae952e6ec9a8e6ce9485919ee85f73a91dab00f5a263c77fb4ed967ae1`.
Composite helper SHA-256:
`879e602d64887b3d706efeff916b2ecfd6c9a7d431bfe6078feb6613c377ef1d`.
Previous helper SHA-256:
`4a6fdb3d979ab13ed8d38b2bc6e1b9b94e5a04294312d0f9b50cc7f1f0a6c987`.

Private evidence: `dumps/20260920T182253Z` (installation),
`dumps/20260920T182828Z` (final helper), `dumps/20260920T183227Z` (reboot request),
`dumps/20260920T183449Z` (post-boot verification), and `telemetry/` (pairing,
rollback package and router exports). The reboot interrupted the transport's
last cleanup verification; a subsequent SDK cleanup and full root-transport
verification passed with original passwd/public-key hashes unchanged.

The rollback artifact hash has been verified; the complete rollback has not been
executed. Extended standby and signed-in playback performance have not been
measured. The live tests establish collection, dashboard preference writes,
Netdata ingestion and restart persistence on this firmware.

Sources: [Samsung filesystem API guide](https://developer.samsung.com/smarttv/develop/guides/data-handling/managing-file-operations.html),
[Netdata external plugin protocol](https://learn.netdata.cloud/docs/developer-and-contributor-corner/external-plugins).

## Dedicated metrics dashboard

Open **http://192.0.2.20:20491/** from an existing trusted NAS administration client.
The new `dashboard` service in the existing TrueNAS `s90d-telemetry` app provides
six interactive history charts, live CPU/memory/network/uptime cards and collector
CPU/RSS/sample-age readings. Choose 15 minutes, 1 hour, 6 hours or 24 hours.
Graphs support pointer inspection and keyboard arrows. Pause updates freezes only
the browser view; collection continues. A URL such as `/?range=3600` bookmarks a
history range. It works at desktop and mobile viewport sizes.

It uses Netdata history and the receiver's latest snapshot, without changing or
adding work to the TV collector. This is a local read-only page, with no cloud
account, CDN or third-party JavaScript. Readings refresh every ten seconds while
the page is visible. When telemetry becomes older than 35 seconds, current-value
cards are cleared and history remains visible. A NAS/API outage is distinguished
from a TV with no recent telemetry. CPU activity excludes idle and I/O wait;
collector CPU uses one-core percentage. Memory use is total minus available.

Code: `research/s90d-telemetry/dashboard/`. The Python service exposes only its
three static assets, a health endpoint and a bounded snapshot API with four
allowed ranges and nine fixed chart IDs. It cannot proxy arbitrary Netdata paths.
Its volume mounts contain dashboard source and read-only latest-snapshot data,
not receiver credentials. It runs as UID 65534 with no capabilities, read-only
root, 96 MiB / 0.25 CPU / 32 PID limits and automatic restart. Port 20491 binds
only to the NAS data address. Existing trusted-client firewall rules apply; no
new router exception or TV change was made for the dashboard.

`dashboard/deploy.py` backs up the live custom-app compose configuration before
adding this service. Private backup: `telemetry/dashboard/app-before-*.json`.
To roll back, use TrueNAS `app.update` with that backed-up compose configuration;
this removes only the dashboard service and retains the receiver. Remove the
`s90d-dashboard` code directory afterward if desired. Do not replay the older
receiver-only app spec for routine receiver updates, as that would remove the
dashboard service; always preserve the current live custom-app configuration.

Live verification (`node research/s90d-telemetry/dashboard/verify.cjs`) passed:
all six charts contain real readings; all four history ranges load; pause/resume,
keyboard inspection and 390px mobile layout work; simulated stale and failed
responses clear live cards while retaining history; unsupported ranges and source
or credential file requests are rejected. Browser page/console errors were absent
except the deliberately simulated 503 response. Both TrueNAS services report
healthy. Screenshots remain in the private `telemetry/dashboard/` directory.
