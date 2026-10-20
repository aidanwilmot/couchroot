# S90D optional-app cleanup

Target: QN55S90DAFXZA at 192.0.2.12, T-PTMDAKUC-0090-2130.0.
The owner requested removal of junk apps while retaining streaming/music apps,
explicitly including Plex, Disney+, Prime/Amazon Music and Crunchyroll.

The reviewed removal list is QVC+ and HSN+, Instagram, Glance, Samsung Promotion,
Samsung GameBreaks, Amazon Luna, Blacknut Cloud Gaming, Xbox and Copilot.
All nine packages reported removable, non-system, non-preloaded and non-readonly
metadata, and no declared incoming package dependencies. Metadata is not a proof
that all dynamic dependencies are recorded. Core services can also report
removable, so that flag alone was not used to choose candidates.

Streaming/music apps, Minimal Hub, the native screensaver, casting, voice control,
Samsung Home, settings, accounts, DRM, accessibility, panel care, app store and
shared advertising/content services are excluded. No raw package database writes,
firmware deletion, service disabling, or protection-flag changes are used.

## Backup and recovery

Private files under `~/.local/share/samsung-tv-research/`:

- `dumps/20260920T163459Z/package-db.tar.gz`: consistent initial package database.
- `dumps/20260920T163630Z/optional-apps-backup.tar.gz`: all nine installed package
  trees and their owner app-data directories. SHA256:
  `557a6f08dda048382a04f50e9b0f2f91b4602b445d158a3aa991e470c3607acf`.
- `dumps/20260920T163659Z/backup-xattrs.jsonl`: file extended attributes, collected
  separately because the TV's tar reports xattr support unavailable. SHA256:
  `17494665257c9d91d3237a1e1e371f6f9a854af5433ad9e2b48ed19d5f80bd9a`.
- `analysis/s90d-app-cleanup/`: extracted read-only database copies, inventory,
  exact operation requests, and logs for each subsequent removal.

These are private recovery/research archives, not tested reinstallable vendor
packages. Restoring directory trees and overwriting the live package database is
not a supported rollback. Reinstall wanted apps through Samsung's app store;
store availability and preservation of sign-in state are not guaranteed.

## Guarded removal

`research/s90d-app-cleanup/remove.py PACKAGE_ID` accepts only the fixed list. It
requires the exact verified backup and target address/firmware. It snapshots the
package database immediately before removal, checks original identity/version,
protection flags and incoming dependencies, then invokes root
`/usr/bin/pkgcmd -u -n PACKAGE_ID` through the existing temporary root collector.
The TV repeats metadata checks immediately before calling its package manager.

Each invocation snapshots the database afterward and requires integrity `ok`,
absence of the selected package, and an exact removal set for both package and
app registrations. Any failed or ambiguous operation stops the batch; there is
no automatic retry. The original accounts and SDK key are verified after every
root collector, and the temporary root staging files are removed.

QVC/HSN was the first native uninstall trial, verified separately against the
initial snapshot (`dumps/20260920T163718Z`). An earlier wrapper failed because
this TV lacks the `timeout` executable; it submitted no package operation. The
collector's existing subprocess deadline bounds subsequent requests.

## Validation

The scope guard was exercised with an accepted single-package removal, rejected
collateral deletion, rejected unchanged registration, and exclusions for the
owner's named streaming apps and Minimal Hub. Each actual uninstall also checks
its own before/after database state.

Completed on 2026-09-20 at 16:40 UTC: all nine selected packages were removed.
The final database contains 490 packages versus 499 initially; the exact package
and app-registration difference is limited to those nine. All remaining package
registrations, including streaming/music apps, are retained; integrity is `ok`.
Final evidence: `dumps/20260920T164043Z`.

Home and startup routing still target `MiniHub001.Hub`. Native screensaver
processes remain running. The renderer, Boot.dll, signed diagnostic, service
cache and offset-table hashes exactly match their pre-cleanup values. Root
collector cleanup verified the original account and SDK-key hashes. No additional
reboot was needed. Playback in every retained app was not tested.

Five scope/keep-list tests pass with `python3 tests/s90d_cleanup_test.py`.
