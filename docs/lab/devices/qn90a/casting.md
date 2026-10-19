# QN90A return after AirPlay mirroring

Target: QN85QN90AAFXZA, 192.0.2.11, firmware T-NKM2AKUC-2301.1.

**Current status:** receiver-pause rule installed and owner-confirmed: stopping
iPad mirroring returns to Minimal Hub, with a brief Samsung overlay beforehand. Both earlier trials were reverted.
Samsung Home fallback and live database rollback have been verified. The owner
accepted the earlier handoff as good enough and requested merging the changes.
Complete elimination of the overlay flash was not specifically confirmed.

The Home-button key override works independently of the return path after casting.
The owner reproduced iPad Screen Mirroring ending on live TV with Samsung's
partial menu. A bounded native Vconf trace captured this disconnect sequence:

1. AirPlay changes from `running` to `ready` while `com.samsung.tv.airplay-app`
   is still fullscreen.
2. `NRi6kdBYJ0.AirPlayWebApp` briefly becomes fullscreen.
3. `org.tizen.tv-viewer` becomes fullscreen about 0.6 seconds after disconnect.
4. `com.samsung.tv.csfs` appears as the partial app about 0.9 seconds after disconnect.

The firmware context manager reads `db/appfw/overlay_home_appid` in its native
base-home fallback path. This remained `com.samsung.tv.csfs`, independently of
our `XF86Home` key map. A bounded preference trial assigned `MiniHub001.Hub`:

```sh
python3 tools/qn90a/home-integration.py overlay
```

Exact single-setting rollback:

```sh
python3 tools/qn90a/home-integration.py restore-overlay
```

The typed original value is preserved in the private QN90A settings snapshot.
Both operations use native Vconf setters and readback, preserving access labels.
Model, firmware and existing values are guarded. First-screen/startup preferences,
TV viewer, Home key map, signed launcher, and AirPlay receiver remain unchanged.
The dashboard's explicit Samsung Home action continues to target Samsung's app.
No root service, background watcher, process killer, or network server is installed.

## Verification

The rollback command compiled and read back Samsung's original value; applying
then read back `MiniHub001.Hub`. The owner repeated real mirroring and still
returned to Samsung's menu. The trial was reverted with `restore-overlay`;
readback confirmed `com.samsung.tv.csfs`. This is not a working casting fix.

A read-only native caller check identifies `tvctx-manager` (PID 814) as the
launcher of Samsung Home. AirPlayWebApp remains running after disconnect, so
a stop-event rule on that web receiver would not match the observed lifecycle.
Firmware inspection also found Samsung Home hardcoded as an attached app in
the Exit route. Whether AirPlay invokes that route remains under investigation.

The bounded trace watches only three app/status keys and exits after 60 seconds;
its DLL is removed afterward. It is a diagnostic, not part of the deployed fix.
Do not run another SDB operation while a trace is active: this TV serializes
those requests. An earlier long shell sampler exceeded its transport deadline
and is not counted as a complete trace.

An initial task-filter rule aimed at the AirPlay UI stop event failed the owner's
real mirroring test. It was removed and zero task-filter rows were verified,
with the existing Home key mapping intact. No such rule remains installed.
Its private pre-trial DB backup is `qn90a/before-cast-route.db`, SHA-256
`1bce2f3edb8cccb525849bf25ed61b85a206121e62a6d5c40c83406a0396861c`.
Research source is preserved privately under `qn90a/failed-cast-task-rule/`.

Private evidence: `sessions/20260920T151930.970130Z-qn90a-cast-native-trace`,
`20260920T151921.932053Z-qn90a-cast-rollback-verify`,
`20260920T152050.909631Z-qn90a-restore-overlay`, and
`20260920T152057.070698Z-qn90a-overlay`,
`20260920T152356.680790Z-qn90a-restore-overlay`, and
`20260920T152549.506217Z-qn90a-caller-read` (all under the sessions directory).

## Receiver-pause trial

The installed trial rule observes `pause` on `NRi6kdBYJ0.AirPlayWebApp`, requires
`memory/menu/network/airplay_status=ready`, and excludes standby. Its only
request is to launch `MiniHub001.Hub`. This targets the receiver returning to
the background after mirroring rather than waiting for the receiver to exit.
It does not intercept Samsung Home, stop applications, or watch from a service.

```sh
python3 tools/qn90a/cast.py apply
# Exact rollback; run this before restoring the Home route or removing the hub:
python3 tools/qn90a/cast.py restore
```

The signed launcher is unchanged. The firmware-guarded temporary-root helper
adds exactly one row to the existing native task-filter database and notifies
its existing context manager to reload. Allow six seconds for its debounce.
The apply guard requires the hub's normal managed-app registration and refuses
an existing hub rule. Restore checks all installed fields before deleting only
that rule. Private backup verification is required before applying. A failed
reload notification attempts the reverse transaction and reports any failure.

Nine focused Home/casting SQLite tests pass; the casting tests cover isolation,
exact rollback, missing dependency, repeated apply, and conflicting restore.
The actual pre-trial TV database also round-trips with every row and rowid
preserved across all three tables. These are configuration tests, not proof of
physical mirroring behavior.

A bounded native probe can put the idle receiver in front of Plex and pause it
through `aul_pause_app`, the same API used by AirPlay's platform adapter.
The baseline returns to Plex (private session
`20260920T153634.030816Z-qn90a-cast-repro`). Merely launching an idle receiver
without pausing it follows a different path and already returns to the hub;
that is not evidence that real casting is fixed.

With the pause rule installed, the native pause test returned to Plex briefly
and then Minimal Hub within about 0.8 seconds of the pause request (session
`20260920T153802.190199Z-qn90a-cast-repro`). The pause request and final foreground
were verified on the TV. An intervening attempt could not foreground the warm
receiver using generic AUL launch; it submitted no pause and is not a passing
case. The successful test used Samsung's normal web-app launcher to resume it.
The owner subsequently confirmed that real iPad Screen Mirroring returns to
Minimal Hub, but Samsung's overlay is briefly visible during the handoff.

The pause rule's rollback was also executed on the TV. A consistent restored DB
matched every pre-casting row and rowid in `managed_app`, `key_filter`, and
`task_filter`; integrity check returned `ok` and the task-filter count was zero
(`20260920T153827.918053Z-qn90a-root-home-cast-restore`,
`20260920T153847.923907Z-qn90a-cast-pause-rollback-check`). A subsequent baseline
probe failed to foreground the receiver and submitted no pause. Warm idle
receiver launches are not a reliable stand-in for an iPad session. This does
not invalidate the earlier positive pause test, but repeated automated
end-to-end behavior has not been established.

The rule was reapplied at `20260920T153925.407403Z-qn90a-root-home-cast-apply`.
Samsung Home opened explicitly as the partial app, then Minimal Hub returned
with no partial app (`20260920T153942.019292Z-qn90a-cast-fallback-check`).
Final readback showed exactly the intended pause rule, unchanged Home row 82,
original overlay preference, integrity `ok`, root:root 0644 / SMACK `_`, and
the same context-manager PID 814 (`20260920T153955.169154Z-qn90a-cast-rule-status`).

## Accepted earlier handoff

Owner feedback confirmed that the pause rule returns after real mirroring, but
Samsung's partial menu is briefly visible while the hub comes forward. An
optional additional rule requests the hub on `deactivate` of the native
`com.samsung.tv.airplay-app`, only when AirPlay is `ready` and outside standby.
This targets the earlier native-to-web transition in the recorded disconnect.
The confirmed web-receiver pause rule stays installed as a fallback.

```sh
python3 tools/qn90a/cast.py early-apply
# Remove only the earlier trigger, retaining the confirmed return behavior:
python3 tools/qn90a/cast.py early-restore
```

For full rollback, remove the early rule first, then the pause rule, then the
Home rule if desired. Each transaction rejects unexpected or missing rules.
Twelve local tests pass, including exact early-rule rollback, preservation of
the confirmed rule, dependencies, and conflicting changes. The actual current
working DB also round-trips exactly. Its private snapshot is
`qn90a/before-early-route.db`; no firmware file is modified.

A potential scoped `attach.above` blocker was investigated but not deployed:
this firmware separates static JSON blockers from ordinary filters, while its
SQLite task-filter loader only populates the ordinary list. A database `block`
row would not provide the intended interception. The earlier-trigger trial
therefore does not claim to suppress the Samsung overlay directly.

Bounded synthetic Exit/native-AirPlay probes could not foreground the idle
receiver and submitted no Exit/pause input. These are not passing behavior
tests. Real mirroring and visual confirmation are required to determine whether
the earlier trigger reduces or eliminates the flash and preserves cast startup.

The earlier trigger's rollback was exercised on the TV and its consistent
snapshot exactly matched the working pause-only DB across every row and rowid.
Evidence: `20260920T155032.235627Z-qn90a-cast-early-restored`.

Reapplied at `20260920T155045.362290Z-qn90a-root-home-cast-early-apply`.
Samsung Home fallback again opened explicitly and returned to the hub
(`20260920T155107.090904Z-qn90a-cast-fallback-check`). Final readback confirmed
exactly the two intended casting rows, unchanged Home row 82, integrity `ok`,
context-manager PID 814, and no temporary probe/root helper files
(`20260920T155126.733073Z-qn90a-cast-early-final`). The dashboard is foreground;
the owner subsequently accepted the result as “good enough” and requested merging.
This is acceptance of the installed behavior, not a claim that the overlay flash
is completely eliminated or that reboot/standby verification has been completed.
