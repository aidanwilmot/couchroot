# QN90A Home key routing

Target only: QN85QN90AAFXZA at 192.0.2.11, T-NKM2AKUC-2301.1.

The stock short-press `XF86Home` route is row 82 in
`/opt/dbspace/.app-context.db`, owned by `com.samsung.tv.csfs` and targeting
`package:com.samsung.tv.csfs` with `entry_point:smarthub_key`.
The separate 5300 ms support shortcut and Source/MultiView routes are untouched.

A consistent SQLite backup was saved privately before deployment:
`~/.local/share/samsung-tv-research/qn90a/app-context-original.db`, SHA-256
`44f5aebf3f476c31a42751a14dc4da77518873b2cb34e59613c1f22910f456b8`.
The original database is root:root 0644, SMACK `_`, journal mode `persist`.
Never commit the backup or replace the whole live DB as a routine rollback.

## Exact change and rollback

`python3 tools/qn90a/home-route.py apply` changes only this key's target to
`package:MiniHub001.Hub`, clears its Samsung-specific arguments, and adds one
normal managed-app registration for the hub. It preserves the registering
Samsung app identity and all other rows, preferences, firmware and boot scripts.
The SQL checks the exact expected original fields in one transaction and refuses
conflicts. The private original backup is required before applying.

**Rollback before uninstalling the hub:**

If the [AirPlay return trial](casting.md) is installed, run
`python3 tools/qn90a/cast.py early-restore` first if the optional earlier trigger is
installed, then `python3 tools/qn90a/cast.py restore`; the casting rule depends on the managed hub registration.
Home restore refuses to unregister the hub while a hub task rule remains.

```sh
python3 tools/qn90a/home-route.py restore
```

Restore checks the exact installed mapping, restores Samsung's target and original
arguments, and deletes only our added managed-app row. A local round trip using
the actual TV backup reproduced every row and rowid in all three tables.
Both operations use Samsung's native
`memory/appfw/app_context_db_change` notification. The context manager debounces
it for five seconds before reloading the routing DB; allow at least six seconds
before testing. No process is killed to reload it.

`python3 tools/qn90a/home-route.py key` submits exactly one native Home key for a bounded test.
It is not a physical-remote test. The shared temporary-root runner checks the
model, platform, firmware and stock binary hashes, enters a private mount
namespace, performs only the selected fixed operation, and removes its staged
files. No root daemon or key interception loop remains. Original password and
Samsung verification-key files are checked unchanged afterward.

If execution is interrupted or lacks its final exit marker, inspect the route and
notification before retrying. Apply and restore intentionally reject an already
changed or unexpected state. A notification failure attempts to undo the DB
transaction; any secondary failure is reported and requires readback.

## Validation

Five local SQLite tests cover short-Home isolation, exact restore, conflicting
Home fields, existing hub registration, and rollback conflicts. Run them with
`python3 tests/qn90a_home_test.py`.

Live tests on 2026-09-20:

- Apply and native reload succeeded. The context manager retained PID 814;
  no service restart or TV reboot was used.
- Launched Plex, verified it was fullscreen, submitted one native Home event,
  and read back `MiniHub001.Hub` as the foreground app.
- Exercised the actual restore on the TV. A consistent post-restore backup
  matched every original row and rowid in `key_filter`, `managed_app`, and
  `task_filter`. Home then opened `com.samsung.tv.csfs` as the partial app.
- Reapplied the change, launched native YouTube, verified its foreground state,
  and submitted Home. The full dashboard returned with an empty partial-app ID.
- A final enabled snapshot matched the exact intended two-row change; all other
  database rows and rowids were preserved. Integrity check returned `ok` and
  root:root 0644 / SMACK `_` were retained. Startup/overlay preferences remain
  their original values. The signed launcher package remains 0.3.9, debug 0.
- All temporary root invocations cleaned up successfully; no helper remained.

Physical-remote/panel confirmation and a subsequent cold-boot/standby check are
still pending. This is persistent local SQLite configuration, but persistence
through a future firmware update is not guaranteed: Samsung could regenerate
its app registration. Startup-to-dashboard is implemented separately by the
[QN90A boot relay](../../../research/qn90a-hub-boot/); the key route remains unchanged.
The dashboard's Samsung Home action still launches the stock app directly;
its physical button check was requested separately from native-key tests.

Private evidence includes `sessions/20260920T144903.224610Z-qn90a-root-home-apply`,
`20260920T144941.679897Z-qn90a-home-route-status`,
`20260920T144952.889008Z-qn90a-root-home-restore`,
`20260920T145042.524419Z-qn90a-home-route-status`,
`20260920T145120.981960Z-qn90a-home-route-status`, and
`20260920T145203.926286Z-qn90a-home-final-check` under the same sessions directory.
