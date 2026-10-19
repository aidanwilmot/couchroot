# QN90A optional-app cleanup

Target: QN85QN90AAFXZA, 192.0.2.11, T-NKM2AKUC-2301.1.
The owner authorized removing less-used apps and keeping streaming/music apps.

**Completed on 2026-09-20:** all ten optional packages below were removed.

The fixed removal list is TikTok, Instagram, QVC+ and HSN+, Samsung
GameBreaks, Samsung Promotion, Glance, Xbox, Google Meet, Explore Google
Assistant, and Amazon Alexa (the web frontends, not their native services).
Streaming/music apps, Minimal Hub, AirPlay and mirroring, Samsung Home,
account/security/privacy components, browser, e-Manual, and core TV services
are excluded. Installed metadata reports these ten packages as non-system,
non-preloaded, non-readonly, removable web apps. None has a declared incoming
package dependency. That check does not establish that all dynamic dependencies
are represented in the package database.

## Private backup and recovery limits

Before changes, the ten installed package directories and manifests were
archived and copied to the Mac, with matching SHA-256 hashes:

- `qn90a/app-cleanup-backup/optional-apps.tar`:
  `c435b31914baae308fd43e9a7a853fcbd1fd1f77278d0a3544f992b3e91c8f2e`
- `qn90a/app-cleanup-backup/package-db.sqlite`:
  `1e2abb22b6254149434b414ad118dc412c9a8cbd4724f8cb1918548b9cc0314d`
- `qn90a/app-cleanup-backup/was-db.sqlite`:
  `b30b100464515e95d5389a6a57c329e01cbe2e564983cceac5579fc19709ece0`

Paths are relative to `~/.local/share/samsung-tv-research/`. Keep these private:
they include installed vendor package material. The archive preserves installed
files, not a tested reinstallable widget or a complete backup of app login data.
It is not an exact, validated uninstall rollback. Do not overwrite the live
package database to restore an app. Store availability/reinstallation must be
checked if an app is wanted again.

## Guarded native uninstall

`tools/qn90a/cleanup.py inspect` checks the fixed list and current metadata.
`tools/qn90a/cleanup.py remove --package PACKAGE_ID` removes one allowlisted package;
without `--package`, it proceeds through all ten. Each operation verifies the
TV model, firmware, idle AirPlay and foreground Minimal Hub. It requires all three
verified private backups. It refuses changed versions/protection flags,
missing app registrations, or declared incoming dependencies. Packages already
absent are reported as such, not counted as removals in that invocation.

Removal uses Samsung's native WAS uninstall API under the existing temporary
root runner. The helper resolves the **store/catalog ID** from
`.webappservice.db`; WAS ID type 0 does not accept the Tizen launch ID here.
Normal uninstall mode (`force=0`) works. The native helper independently checks
package identity/protection flags and dependencies, then verifies that the WAS
record is installed, available, non-system, removable, and unlocked. It accepts
no runtime target or command; each build selects one of ten fixed apps.

For each app, the host verifies unchanged package version/flags and catalog
identity against the private original snapshots. It checks the completion
callback, removal from both package/app registrations and Samsung's catalog,
absence of the installed directory/manifest, and both database integrity checks.
It also compares registrations to detect unrelated removals. The batch stops on
any failure or uncertain result. Requests are never automatically retried.
SQLite snapshot reads allow a three-second busy timeout for normal installer
activity. All command outputs and DB snapshots stay private.

The native helper has an 11-second verification deadline inside the existing
15-second child-process limit. It performs no action in the UID-5001 baseline;
only the temporary UID-0 invocation requests uninstall. Each invocation removes
its staged helper/key/archive files and verifies the real password and Samsung
public-key files are unchanged. There is no daemon, scheduled task, firmware
change, security-policy edit, or background process killer.

Twelve cleanup guard tests cover streaming-app exclusion, changed system flags,
versions, dependencies, app IDs, catalog identity/lock status, isolated removal,
collateral removal, and packages remaining installed. With the existing routing
checks, 24 tests pass. These are local synthetic-database tests; native helper
compilation and actual uninstall results are separately verified on the TV.

## Developer-service stall

The generic `pkgcmd -D -t wgt -n 9FhM0cODbY --uid 5001` disable trial stalled
inside the SDB shell-capture path. Its callback timed out, subsequent reads
could not stage, and reconnect failed. No uninstall had been submitted. The
owner power-cycled the TV. Do not repeat that command through shell capture;
inspect the package state after reconnecting. This trial is not proof that
package disabling works or that TikTok was disabled.

Evidence: `20260920T161537.129337Z-qn90a-app-cleanup-preflight`,
`20260920T161611.699769Z-qn90a-app-cleanup-backup`, and
`20260920T161644.462676Z-qn90a-app-disable-trial` under private `sessions/`.

After the owner's power cycle, boot ID changed to
`00000000-0000-4000-8000-000000000004`. TikTok's package and app disable flags
were both still `false`; no per-user override row existed and no `pkgcmd`
process remained (`20260920T162047.195479Z-qn90a-app-disable-readback`).
The Home key override and both casting rows survived the power cycle; routing
integrity was `ok` (`20260920T162132.200861Z-qn90a-app-cleanup-ready`).

The dedicated SDK command `0 vd_appuninstall` refused the retail TikTok app;
neither the package-ID nor launch-ID attempt removed it. Initial direct WAS
calls using the Tizen launch ID returned callback error 132 and left the app
intact, including an administrative-mode diagnostic. Local firmware inspection
and the live catalog exposed the store-ID mismatch. Using store ID
`3202008021577` in normal mode removed TikTok successfully; no forced removal
was needed or retained.

During the later batch, Google Meet completed its uninstall, but the immediate
snapshot hit a transient database lock. The batch stopped. A separate readback
compared against the prior Xbox snapshot confirmed only Google Meet's removal
from both catalogs before work resumed. No uninstall was repeated for that app.

## Completed result and validation

All ten packages were removed. Package count changed from 368 to 358. A complete
row comparison against the original package and app-registration tables found
only rows belonging to these ten packages removed; every other row matched.
Samsung's app catalog lost only the ten corresponding identities. All ten app
directories and manifests are absent, and both database integrity checks pass.
Disney+, Plex, Prime Video, Amazon Music, Hulu, Netflix, YouTube, Crunchyroll,
Spotify, and the other streaming apps remain installed.

Their installed directories occupied 10916 KiB before removal. This is
an app-file footprint, not a measured increase in free RAM or a controlled
filesystem-free-space measurement. No responsiveness improvement is claimed.
Firmware-protected Samsung components, native assistant services, and core TV
services remain; this was not a firmware debloat or a process-killing pass.

Post-cleanup native checks launched Plex with debug 0 and verified it fullscreen.
A native Home-key event returned to Minimal Hub. Explicit Samsung Home launch
showed `com.samsung.tv.csfs` as the partial app; relaunching the hub restored it
fullscreen with an empty partial-app ID. The AirPlay receiver reported `ready`,
the Home mapping and both existing casting-return rules remained intact, and
the routing DB integrity check passed. These are automated/native state checks,
not physical-remote, playback, or a new iPad mirroring test. No post-removal
reboot was performed. Persistence against future Samsung automatic app delivery
or firmware updates has not been established; no background blocker was added.

Final inspection found all ten packages absent. Temporary backup copies and
readback databases/journals from this pass were removed from the TV after the
Mac copies were hash-verified again. No root helper, `pkgcmd`, or staging
directory remained. The TV was left in Minimal Hub with AirPlay ready.

Sanitized results: [inventory](../../../../inventory/qn90a-app-cleanup-20260920.json).
Private per-app snapshots are under `qn90a/app-cleanup-backup/20260920T163508Z`,
`20260920T163624Z`, `20260920T163732Z`, and `20260920T163755Z`.
