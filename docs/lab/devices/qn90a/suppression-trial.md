# QN90A viewer suppression trial

Date: 2026-09-23 UTC. Target: QN85QN90AAFXZA / T-NKM2AKUC-2301.1.
The owner authorized suppression work and agreed to observe the panel.

## Live runtime result

A bounded app-control trial completed without killing or restarting the viewer:

| Kernel uptime | Operation / observation |
| --- | --- |
| 281.73 s | Requested viewer `init=activate`, then `tvs_hint=1` to establish normal presentation. |
| Before suppression | Native foreground readback was `org.tizen.tv-viewer`. |
| 285.20 s | Requested `tvs_hint=0`, then waited eight seconds. |
| During suppression | Viewer remained foreground with the same PID. This is not evidence of visible video or silence. |
| Restoration | Requested `tvs_hint=1`, then launched `MiniHub001.Hub`. |
| 297.06 s | Hub foreground confirmed; viewer PID still unchanged. |

Each app-control submission reported successful launch against the existing
viewer process. The script installed an EXIT trap to request the inverse and
return to Hub if it failed partway through. It did not change persistent
preferences, install a package, stop a service, alter boot markers or patch
firmware. Viewer input initialization was preserved in the sense that the
process was not restarted; functional HDMI/source acceptance is still separate.

The owner subsequently watched the repeated test and reported Samsung TV Plus
showing with audio. No successful picture/audio suppression was observed; this
control is not accepted as a working suppression policy. An accepted
app-control request and unchanged PID do not establish panel blanking or silence.

Private evidence:
`~/.local/share/samsung-tv-research/setup/inspections/viewer-suppression-20260923T014417Z-a741f2ab/`.
It contains the prepared inverse, exact hash/boot/PID guards, operation script,
submission journal and SDK result. The viewer binary was checked against SHA-256
`30e3cd18147227806d3dcce4811affed7426504cfb3c8db5d35fd3347fb7efce` before
submitting the commands.

## Power-cycle baseline

The owner was asked to use brief remote power presses with about 15 seconds in
standby. The subsequent readback had a different kernel boot ID, and Hub was
foreground. This does not validate a same-boot resume or the conditional native
first-screen resume branch. The panel sequence and exact button behavior have
not yet been confirmed by the owner.

The power transition left an SDB entry that appeared connected but rejected its
sync channel. One targeted QN90A disconnect/reconnect restored access. The shared
Mac server was not restarted and no S90D operation was submitted.

Private baseline evidence:
`~/.local/share/samsung-tv-research/setup/inspections/suppression-baseline-20260923T013829Z-15ac649c/`.
Its temporary foreground sampler stopped with the previous boot and did not
complete; do not treat it as a continuous wake trace. A subsequent guarded
read confirmed first-screen preferences remained Samsung CSFS and autostart 0.
The sampler output was collected locally and its temporary TV log removed
under a checksum guard. Final readback confirmed Hub foreground and no pending
setup operation.

## Why startup suppression remains uninstalled

`tvs_hint=0` targets the TV-control child, not the parent viewer window or the
independent early fastvideo output. Later viewer fullscreen-app callbacks can
change this hint according to TV Plus capability and application state.
Ordinary source selection and `init=activate` restore the hint, but also
activate the viewer. No reliable recovery operation that preserves Hub focus
has been demonstrated for an unattended relay-level suppression policy.

The current relay also enters after the early viewer/fastvideo launches. Adding
a hide request there cannot prevent the initial cold-boot frames even if it
reduces later exposure. The earlier persistent ordinary-boot hook is still
unresolved; none was installed or simulated with manufactured ready markers.

## Prepared first-screen trial tooling

`python3 -m tvsetup.qn90a_resume_trial` provides `prepare`, `apply`, `inspect`,
`rollback` and `accept`, plus `start` to prepare and apply. It uses the existing
setup engine, identity/firmware guards, target lock, pending-run checks,
backups and private journal. Its only permitted changes are:

```text
db/first_screen/type: com.samsung.tv.csfs -> MiniHub001.Hub
db/menu/smart_hub/ontvsetting/auto_start: 0 -> 1
```

Rollback restores those exact baseline values. A prepared but unapplied run can
be cancelled; accepting a fully applied run closes only its journal, preserving
saved deployment choices and the ownership ledger. No run was created or
applied for these settings during the live runtime trial. They remain a
conditional genuine-resume candidate, not a demonstrated cold-start fix.

Host validation passed 187 setup tests, including 10 trial lifecycle tests.
These host results do not establish native setter permissions, standby
behavior or physical-panel suppression on the TV.

## Repeat after leaving the screensaver

At the owner's request, a second bounded trial first launched Hub and confirmed
its foreground at 721.84 seconds uptime. It then activated the existing viewer
at 725.05 seconds, submitted suppression at 730.27 seconds, and submitted the
inverse at 738.51 seconds. Hub foreground was confirmed again at 741.62 seconds.
The same viewer PID remained alive throughout. The owner reported Samsung TV
Plus showing with audio, so the suppression attempt is recorded as failed.
No persistent settings changed.

Private evidence:
`~/.local/share/samsung-tv-research/setup/inspections/viewer-suppression-repeat-20260923T015137Z-d8abe271/`.

## TV Plus-specific follow-up

Read-only inspection after the owner's report found:

| State | Observed value |
| --- | --- |
| `db/menu/autorun_tv_plus_state` | `enable` (string) |
| `db/menu/autorun_tv_plus` | `False` (boolean; already off) |
| `db/boot/last_service` | `vc-service` |
| `db/mw/number_of_virtualservices` | 587 |
| Current native source | `tv-service`, `SOURCE_TYPE_TV` |
| Running relevant processes | `tv-viewer`, `tpp.tvpluspeppe`; no `fastvideo` in this post-boot sample |
| Native foreground | `MiniHub001.Hub` |

The installed TV Plus app is a newer, native, no-display service TPK version
8.2.008 under `/opt`, distinct from the vendor-decrypted firmware corpus. Its
manifest marks it built-in. A removable package flag alone is not a reason to
uninstall it. No package operation was performed.

`CSystemConfig::CanAutoRunTVPlus` at `0x505964` in the pinned viewer checks the
autorun boolean and returns false when it is off. Changing that already-off
option is therefore not a new suppression experiment. The saved `vc-service`
source makes last-source restoration a separate candidate to trace; it is not
proof of a complete causal path by itself.

Samsung's [Australian support guide](https://www.samsung.com/au/support/tv-audio-video/disable-samsung-tv-plus/)
documents a separate **Remove → Disable** UI action for 2020–2021 models and
an **Add to Home** inverse from Source. It removes the launcher entry and TV
Plus guide channels. The guide explicitly warns that regional steps vary, so
availability and equivalent native behavior on this US QN90A need checking.
This is distinct from turning off Autorun. Neither this action nor channel
deletion has been submitted.

Private follow-up evidence:
`~/.local/share/samsung-tv-research/setup/inspections/tvplus-startup-20260923T015328Z-a27d8fdb/`.


## Hub registered as an ISP viewing source

On 2026-09-23 UTC, the owner's request to register Hub as a viewing source was
applied through a normally signed package update. Hub 0.4.12 differs from the
installed 0.4.11 payload only in `config.xml`: the forward version and
`tizen:metadata` key `http://samsung.com/tv/metadata/D2TV`, value `ISPBound`.
All eleven other payload files are byte-identical to the installed baseline.
Both Samsung author and distributor signatures were checked against the
independently enrolled QN90A pins. The shared setup engine made fresh package
and database backups and recorded the installation before submitting it once.

Live readback confirmed `widgetinfo.is_ispbound=1`, `is_hybrid_tv=0`, with Hub's
app/package identity unchanged. This is installed source-role classification,
not an arbitrary WAS database write. Native `was_is_isp_app` subsequently
returned 0 (`WAS_TRUE` in this API).

An ordinary `app_launcher -s` launch did not change the saved viewing source.
A post-boot LiteWAS `SOURCE_LAUNCH` app-control request also did not activate it.
The successful activation was a **fresh regular WAS API launch**, after
terminating only the Hub app gracefully. A pinned temporary .NET helper called
`was_launch_app_ex` with an app-control containing Hub's app ID and a callback.
It returned 0 and emitted events 900 (launch start), 901 (launched), and 902
(showed). Readback then showed:

| State | Before | After |
| --- | --- | --- |
| `db/boot/last_service` | `vc-service` | `isp-service` |
| `db/was/isp_app_id` | empty string | `MiniHub001.Hub` |
| Hub ISP role flag | 0 | 1 |
| Foreground at final verification | — | `MiniHub001.Hub` |

The earlier API call while Hub was already running emitted event 906 (resume)
and did not update source bookkeeping. `app_launcher -r` only checks whether an
app is running; it is not a resume command.

At registration acceptance, no reboot, standby transition, or physical panel
suppression test had been performed. Registration and saved-source selection
were verified; faster startup and absence of TV Plus picture/audio were not.
The later failed reboot and owner-requested withdrawal are recorded below. A
source-app exit can reset the service to TV; ordinary pause does not, according
to the static lifecycle trace.

Private shared-engine run: `20260923T022422Z-9463fb27`, under
`~/.local/share/samsung-tv-research/setup/runs/`. Its package journal, activation
records, snapshots, helper source/hashes, launch callbacks, and private recovery
plan preserve the evidence. The registration journal was accepted without
changing saved full-setup choices or the ownership ledger.

The prepared signed inverse is 0.4.13 with the D2TV metadata absent and all other
payloads unchanged. Recovery must use the preserved source snapshot. Its source revision was
verified against the live journal, so later UI edits need not block recovery:

```sh
cd <private-run-directory>/recovery-source
python3 -m tvsetup.qn90a_source_trial rollback --run 20260923T022422Z-9463fb27
python3 <private-run-directory>/restore-source-state.py
```

The second command requires successful package/role withdrawal, checks exact
expected manifest and source state, restores the original typed source values,
and returns to ordinary Hub. Both inverses were subsequently executed as recorded
below; do not resubmit these historical recovery commands. Do not use an
app uninstall, a stale database-file restore, or an unguarded preference write.
Host validation: the 191-test setup suite passed, followed by five focused
source-trial tests; this is separate from the live results above.

## First reboot with Hub saved as the ISP source — 2026-09-23 UTC

The owner requested a power cycle. The shared `tv-setup verify --reboot`
workflow submitted one DeviceD full system reboot, not an AC power disconnect.
Before the request, the ISP role and saved source were still correct; the
foreground was `MiniSave01.Saver`. No key or Hub launch normalized that state
before this run, unlike the earlier web-startup measurements.

A new kernel boot ID was confirmed. The TV created `/tmp/init_mode_background`,
and `memory/system/boot_done=1` was observed. The saved source remained
`isp-service` with Hub's app ID. However, native foreground was empty, no Hub
process or relay status was observed, and Hub was still absent at 173.16 seconds
of kernel uptime. The bounded reboot verification ended unverified without
sending any Hub launch. This is a failed automatic-entry trial, not a faster
startup result; the reason the source restore and existing relay did not bring
Hub up remains unresolved.

The Mac retained a stale SDB entry after reboot. One target-only QN90A
disconnect/reconnect restored inspection; the shared SDB server was not
restarted. After the observation window, one explicit manual
`app_launcher -s MiniHub001.Hub` recovered Hub, with native foreground confirmed
at 218.18 seconds uptime. That recovery is separate from autonomous startup.
No package or persistent configuration was changed during this reboot test.

The owner was not in the room, so panel visibility and TV Plus/Live TV audio
suppression were not observed. Standby/wake remains untested with this source
registration. Private evidence, the single reboot journal, connection recovery,
and manual recovery record are under
`~/.local/share/samsung-tv-research/setup/inspections/20260923T025326Z-26a4f9f7/`.

## Owner-requested withdrawal and deferred investigation — 2026-09-23 UTC

The owner requested reverting only the ISP-source experiment and setting it
aside. From the preserved recovery source, the shared engine installed the
prepared signed 0.4.13 inverse. Installed content matched the exact inverse;
the WAS role row returned to `is_ispbound=0`, `is_hybrid_tv=0`, and the journal
reached `rolled-back`. All non-manifest Hub payloads retain their pre-trial
bytes. This forward-version rollback avoids an uninstall or loss of Hub data.

The hash-guarded source-state inverse then restored the original typed values:
`db/boot/last_service=vc-service`, an empty `db/was/isp_app_id`, and the unchanged
Hybrid slot. A fresh snapshot matched the baseline source settings, and ordinary
Hub foreground was verified. The private `source-state-rollback.json` records
`phase=restored`; the prepared package and source inverses have now been executed.

The preserved findings, unresolved launch-path questions, and requirements for
any future live trial are in the
parked ISP-source investigation (private research notes, not distributed).
No further ISP-source trial is scheduled.

A subsequent DeviceD full reboot verified restored autonomous startup: the
existing boot relay confirmed Hub foreground at **39.54 seconds of kernel
uptime**, after two bounded launch attempts. The host verification sent no Hub
launches. Telemetry and receiver ingestion were fresh on the new boot. Final
readback confirmed the inverse manifest hash, both source-role flags zero,
`vc-service`, an empty ISP slot, the unchanged Hybrid slot, Hub foreground, and
no pending QN90A setup runs. Private verification evidence is
`setup/inspections/20260923T030243Z-e3ef9cf2/`. A target-only SDB reconnect was
again needed after reboot; the shared Mac server was not restarted. The 39.54
seconds measures native foreground, not panel-render or remote-response timing.
