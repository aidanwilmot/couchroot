# QN90A port and rollback

Target: the owner’s QN85QN90AAFXZA, `192.0.2.11`, firmware
`T-NKM2AKUC-2301.1`, build `TIZEN-TRUNK2021-NikeM2-RELEASE_20251112.1`.
Live inspection reports Tizen 6.0 ARMv7 and Chromium 76. The S90D remains on its
separately signed 0.3.8 build; QN90A work must not use its integration or trim commands.

**Current Home status:** a later root-assisted [key-routing change](home.md)
successfully returns from Plex and YouTube to the full dashboard in native-key
tests. Its exact rollback was tested on the TV. The preference trials below are
historical failures. The later [boot relay](../../../../research/qn90a-hub-boot) adds
full-reboot startup without using those preferences.

## Signing and application

The existing author identity is retained. A new Samsung-issued public distributor
certificate covers this TV under the separate `MinimalHubQN90A` profile. It does
not replace `MinimalHub` or its device certificate. Private artifacts live under
`~/.local/share/samsung-tv-research/qn90a/`; never commit them.

The initial 0.3.8 installation succeeded normally. Live discovery inside the signed
app yielded 33 filtered apps. The on-TV editor added Crunchyroll, moved it ahead of
Plex/YouTube, saved the order, and launched the actual installed Crunchyroll app.
Plex and YouTube also launched (YouTube resolves to `com.samsung.tv.cobalt-yt`).
Removing Crunchyroll through the editor restored Plex/YouTube while
`getAppInfo` still returned the installed Crunchyroll app. The explicit Samsung
Home button opened `com.samsung.tv.csfs` as the current partial app.
Those checks used the TV's debugger and SDK foreground reads;
they are not physical-remote or playback verification.

Version 0.3.9 adds compatibility for the older browser: explicit edge positioning,
font sizes before `clamp()` declarations, and measured flex-gap fallback spacing.
The live TV confirmed `clamp` and `inset` unsupported and flex gap absent. After the
style trial, Plex text measured 115.2 px, YouTube 74.88 px, and both utility pages
covered 1920×1080. The 37 automated checks include an older-CSS layout regression.

The signed 0.3.9 update installed successfully and launched with debug 0. All nine
source files match the signed artifact, stored privately at
`qn90a/build-0.3.9/MinimalHub.wgt`, SHA-256
`54b23ff808d44e1b3cf27c60c72e84310784f3840ce4885c3f3fb0ce5ff875a4`.
For subsequent builds, use the TV-specific profile:

```sh
python3 scripts/sign.py --profile MinimalHubQN90A
```

Use the printed private build directory with the Tizen CLI's `install` command,
always selecting serial `192.0.2.11:26101`. The default signing profile remains
the S90D profile. The original QN90A 0.3.8 package is preserved privately; the
pre-port rollback is to restore Samsung routing and uninstall this new package.

## Original configuration

| Key | Original value |
| --- | --- |
| `db/appfw/home_appid` | string `org.tizen.tv-viewer` |
| `db/appfw/overlay_home_appid` | string `com.samsung.tv.csfs` |
| `db/first_screen/type` | string `com.samsung.tv.csfs` |
| `db/menu/smart_hub/ontvsetting/auto_start` | integer `0` |
| `db/appfw/booting_appid_backup` | string `org.tizen.tv-viewer` |
| `db/appfw/startup_appid` | absent |

The owner's app-service DB has no main-operation override. An integrity-checked,
read-only copy and typed original settings are saved privately. The preference
helper never writes that app-service database. The later Home fix changes two
rows in the separate app-context database, with an exact row-level restore.
The QN90A helper targets .NET Core 3.1; the
S90D's .NET 6 helper is incompatible, and `aul_get_default_app` is absent here.

Before any Home preference trial, the native restore/readback path was exercised
against the original values successfully. `tools/qn90a/home-integration.py` checks the exact model,
platform, developer host and firmware, then stages and removes its bounded helper.
It uses native Vconf setters to preserve access labels.

Restore the three selected preferences:

```sh
python3 tools/qn90a/home-integration.py restore
```

If the later Home fix is enabled, first run `python3 tools/qn90a/home-route.py restore` and
allow six seconds for its native reload. Restore the preferences above too if
they were changed. Restart after restoring cached preference trials. Restore
before uninstalling:

```sh
~/.local/share/samsung-tv-research/tizen-sdk/cli/tools/ide/bin/tizen \
  uninstall -s 192.0.2.11:26101 -p MiniHub001.Hub
```

## Home routing trial and startup limitations

An overlay-only assignment was tested first. the owner pressed Home from Plex and
confirmed Samsung's normal partial bottom menu appeared. This does not count as
successful Home routing. The overlay key was returned to Samsung Home.

The next trial set `db/first_screen/type=MiniHub001.Hub` and integer `auto_start=1`,
while retaining the stock TV viewer and stock Samsung overlay. The context manager
caches the firstscreen identity, so it was evaluated after a real restart.
Boot ID changed from `00000000-0000-4000-8000-000000000006` to
`00000000-0000-4000-8000-000000000005`. The settings persisted, but native readback
and the owner’s panel observation both showed live TV. the owner then confirmed Home
still opened Samsung's bottom menu. **Neither startup nor Home routing is working
through these preferences on this firmware.** All three trial preferences were
restored to their original values and read back successfully.

`python3 tools/qn90a/home-integration.py enable` reproduces this unsuccessful research trial; do not
treat it as a supported installation step. `restore` reverses it.
If a setter/readback fails, the helper attempts to restore the values read at the
start of that invocation. It reports failures rather than assuming success.

This firmware's `/usr/bin/firstscreen.sh` explicitly launches Samsung Home during
cold boot. Its context manager also caches `db/first_screen/type`. Consequently,
the S90D's boot integration and three-process memory trim cannot be copied here.
The QN90A has no equivalent HomeMedia/HomeSidebar pair in the inspected layout.
No firmware file, boot script, security policy, or resident process killer has
been installed or changed.

Samsung network-remote pairing timed out without a visible owner approval prompt.
Native input/screenshot tools are not executable by the SDK identity. The later
bounded root Home helper successfully submitted native `XF86Home` events. Chromium's
debug screenshot request timed out; it is not counted as visual confirmation.
Standby/wake, physical sound and spinner behavior on this older TV still need
verification. The SDK identity could not read Chromium's Local Storage directory;
that failed access is not counted as a persistence test. A later signed-app debug
read did confirm that the saved Plex/YouTube configuration survived the real
restart and in-place updates. A later [one-time memory cleanup](overhead.md)
unloaded idle Prime Video, YouTube and Samsung Home, with recovery verified.

## Verified temporary root

At the owner’s request, the QN90A's root path was investigated separately. The live
SDK identity is UID/GID 901, SMACK `System`, inherited capabilities
`00000000002000e2`, with no effective capabilities. Samsung's `/usr/bin/dotnet`
has `cap_setgid,cap_sys_admin+ei`; `sdbd-tarlauncher` has
`cap_setgid,cap_setuid+eip`.

The QN90A tar launcher was copied privately and inspected before testing. Its
SHA-256 is `3580e6dcf5d9c6d5d0a606d43a3d878641f35eeac07317a405fb45bbed69a653`.
It verifies the named archive with `/usr/share/sdbd/public.pem`, resolves `owner`
through `getpwnam_r`, applies that record's GID/UID, and forwards arguments to
`/usr/bin/tar`. The .NET runtime hash is
`d2a35114d788c22d22d329acdb2f379c17b75b7099997fb8252cbd6dd940702e`.
Both hashes, model/platform, architecture and exact firmware are guarded.

The same private-namespace approach as the S90D works with assemblies built for
**.NET Core 3.1**. A newly generated disposable public key and owner UID/GID view
are bind-mounted only inside a private mount namespace. Neither original file is
written. The private test key stays on the Mac and is deleted with the temporary
build directory; no signing material enters Git.

The bounded proof completed on 2026-09-20:

| Check | Result |
| --- | --- |
| Unmodified owner baseline | All four UID fields 5001, GID fields 100, SMACK `User` |
| Temporary owner record view | All four UID/GID fields 0, SMACK `User` |
| Root capabilities | Permitted/effective/bounding `0000003fffffffff`, seccomp 0 |
| Read-only access test | `/dev/mmcblk0p19` and `/proc/1/ns/mnt` opened successfully; zero bytes read |
| Namespace isolation | Recursive private propagation verified before either bind mount |
| Unmount | Both returned 0 |
| Original files | `/etc/passwd` and Samsung public-key SHA-256 unchanged |
| Final state | SDK UID/GID 901, zero effective capabilities, original host propagation, no probe processes or staging directories |

Repeat the fixed identity diagnostic from the repository:

```sh
python3 tools/qn90a/root-check.py
```

It accepts no arbitrary root command. It builds in a private temporary directory,
generates and locally verifies its disposable archive signature, runs owner/root
checks, and removes the staged files. It refuses an unexpected target or existing
staging directories and does not retry an uncertain root run. Root retains SMACK
`User`; this is not proof of unrestricted access to every Samsung policy layer.
No firmware, boot slot, persistent root service or security policy was changed.
Repeatability across a subsequent reboot has not yet been tested on the QN90A.

Private evidence:
`sessions/20260920T142053.596711Z-qn90a-root-identity` and
`sessions/20260920T142054.595016Z-qn90a-root-cleanup-verify`.

## Asteroids screensaver port

The [QN90A screensaver port](../../../../native/qn90a-screensaver/README.md) diagnosed
native resets to two hours and a renderer too dim on this LCD. Asteroids 1.0.1
uses brighter/wider QN90A-only strokes, confirmed visible by the owner. After two
successful native five-minute trials, the owner selected **dashboard-owned idle**:
Minimal Hub 0.4.0 launches Asteroids after five minutes while visible and cancels
its timer while hidden. Plex keeps its own native timeout/playback policy. This
timer is packaged only for MinimalHubQN90A and requires no root service.

The optional system-wide selector remains a memory patch cleared by full reboot;
its automatic boot integration is unresolved. The broader global timeout patch
was superseded and removed. The rejected native-file override was not retried.
See the port's acceptance evidence and [exact rollback](../../../../native/qn90a-screensaver/ROLLBACK.md).
