# QN90A screensaver rollback

Target only: QN85QN90AAFXZA, 192.0.2.11, T-NKM2AKUC-2301.1.
The owner later requested a five-minute timeout; rollback restores the original
Samsung timeout, not that new preference.

Original native state in Minimal Hub: Enabled, timeout 7200 seconds, default
renderer `org.tizen.default-screensaver`. Apps may change native eligibility.
No firmware file, boot script or service was modified.

## Dashboard-owned timer rollback

The owner selected a dashboard-owned timer instead of globally overriding other
apps' timeout requests. Before updating Minimal Hub, its existing web source was
staged and signed as forward rollback version 0.4.1 under
`qn90a/hub-rollback-20260920/MinimalHub.wgt` (MinimalHubQN90A profile).
To remove the dashboard idle timer while preserving saved favorites and routing:

```sh
~/.local/share/samsung-tv-research/tizen-sdk/cli/tools/ide/bin/tizen \
  install -s 192.0.2.11:26101 -n MinimalHub.wgt -- \
  ~/.local/share/samsung-tv-research/qn90a/hub-rollback-20260920
```

The new QN90A-only dashboard is version 0.4.0. The ordinary shared web package
remains 0.3.9; sign.py adds the idle script/version only for MinimalHubQN90A.
No Hub data is reset. `apply` now removes the earlier global timeout policy,
retains the Asteroids selector, and restores the native 7200-second default.
No supported operation installs the global timeout normalization again.
The dashboard's independent visible-only timer requests an ordinary saver app
launch after five minutes; Plex and other apps retain their native timeout policy.
To undo everything, restore the dashboard package, then run native `restore`.
If `inspect` reports no mapped native module after a restart, run `module-restore`
first to recover the original stock module.

## September 20 follow-up rollback (prepared before deployment)

The superseded runtime timeout policy redirected the stock module's timeout-set GOT
entry at relative offset `0x1716c` from `0x000bbf71` to a 32-byte Thumb thunk
at module offset `0x6940`. It maps **only exact 7200 seconds to 300**, then
tail-calls the original function. Original padding is 32 zero bytes. Both the
module and compositor executable hashes are guarded; unknown bytes are refused.
`restore` and `memory-restore` now remove this policy before restoring the selector.
`timeout-restore` removes only this policy and sets Samsung's 7200 seconds.
The same `restore` command below reverses both generations of runtime integration.
Full reboot removes both memory patches.

Before changing the renderer, the previous signed 1.0.0 WGT and a signed forward
rollback version 1.0.2 were prepared privately. To return to the previous dim
renderer after restoring the native route:

```sh
~/.local/share/samsung-tv-research/tizen-sdk/cli/tools/ide/bin/tizen \
  install -s 192.0.2.11:26101 -n AsteroidsSaver.wgt -- \
  ~/.local/share/samsung-tv-research/qn90a/saver-rollback-20260920
```

This initial runtime/renderer phase did not change the launcher package or
Home/casting database. The later dashboard package rollback is described below.

## Current memory-only redirect

From `/path/to/samsung-tv-hub`:

```sh
~/.local/share/samsung-tv-research/.venv/bin/python qn90a-screensaver.py wake
~/.local/share/samsung-tv-research/.venv/bin/python qn90a-screensaver.py restore
~/.local/share/samsung-tv-research/.venv/bin/python qn90a-screensaver.py inspect
```

`restore` restores the exact original pointer and 17 padding bytes, selects the
explicit stock ID and restores timeout 7200. It verifies known memory before
writing, reads back the result and resumes the compositor in `finally`. It
refuses unexpected state. `inspect` should report the stock module under
`/usr/lib`, stock app ID and timeout 7200, with no rejected user override.
Do not force-enable a saver that the foreground application has disabled.

A full TV reboot also clears the memory redirect and runtime timeout change.
No automatic reapplication is installed. If the guarded restore refuses unknown
memory or a root operation cannot be completed, use a normal full power-cycle;
do not retry an uncertain write or force-reset the kernel.

After rolling back the dashboard timer and restoring the native route, optionally
uninstall only the standalone saver:

```sh
~/.local/share/samsung-tv-research/tizen-sdk/cli/tools/ide/bin/tizen \
  uninstall -s 192.0.2.11:26101 -p MiniSave01.Saver
```

Minimal Hub, its saved configuration, Home routing, AirPlay return and streaming
apps are separate and remain unchanged. Never uninstall the saver first while
the default route points to it.

To end a 15-second trial while keeping Asteroids selected, use
`qn90a-screensaver.py timeout-restore` with the private Python, then press a key.
`memory-restore` reverses both runtime patches; `restore` also restores the
7200-second timeout.

## Removed native-file experiment

The rejected override was removed from:

`/var/lib/enlightenment/.e/e/modules/e-mod-tizen-screensaver/linux-gnueabi-armv7l-ver-autocannoli-0.20/module.so`

Its staging and trial commands are no longer available. `module-restore` is
retained only as emergency cleanup for the exact known rejected file: it refuses
unknown content, removes the file, unloads that module name and loads the stock
module. It first reverses any known runtime patches in an already mapped stock module,
then selects the stock app ID and timeout. Follow with `inspect`. A full restart is the
cleanest way to discard old module mappings after an earlier failed trial.
The recovery operation now also removes the exact empty module/architecture
directories; it refuses other contents.

Original firmware module SHA-256:
`1dffd1d7d24b3827d0263e43e26d8149ba4d20fdcae3ba4fa75b4d6b9ac55728`
Rejected copy SHA-256 (only for exact cleanup):
`2456c5a3c12f52118080f324cd942000d7b77dafdf359bfc555d663e112907ba`


The attempted native standby test suspended its own recovery helper and dropped
SDB. Its supported CLI operation has been removed. Use the physical remote for
standby acceptance; automatic in-TV Power On from a suspended helper is not a
reliable recovery path. The one LAN wake packet restored network API access but
left the reported state as standby. The owner subsequently powered it on; a new
boot ID was observed. The interrupted temporary SDK files were inspected and
removed after hash checks, with no active probe process and unchanged global
passwd/verifier hashes (session `20260920T183910.840228Z-qn90a-standby-recovery-cleanup`). Do not repeat the root
operation. The exact interrupted cleanup script is saved privately at
`sessions/20260920T182955.530118Z-qn90a-root-cleanup-verify/command.sh`.
Inspect active probe processes before running that fixed file cleanup.

The `script-probe` diagnostic creates only
`/opt/data/DeviceTracker/.qn90a-script-probe`, refuses a pre-existing file, and
removes its own file in `finally`. It never edits or runs Samsung's diagnostic
script. Its execution was rejected by the firmware signature check.

Post-restart inspection found the native module disabled, plus empty directories
left by the rejected override. Before stock-module recovery their exact listing
was saved in `20260920T184028.197829Z-qn90a-reboot-loader-paths`.
`module-restore` now removes only the exact known override (if present), then
removes the two exact empty module/architecture directories with non-recursive
deletes that refuse any other contents. It unloads the canonical native module name and loads the absolute firmware
path. Canonical-name loading alone failed in the actual recovery trial. No firmware file
or other module configuration is edited. The obsolete empty directories are deliberately not restored; their removal is
reversible with `mkdir -p` at the exact override parent path if diagnosing it.
