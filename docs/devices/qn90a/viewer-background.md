# QN90A TV-viewer background startup investigation

Date: 2026-09-22. Target: QN85QN90AAFXZA, T-NKM2AKUC-2301.1.
Follow-up to the [direct-boot investigation](direct-boot.md).

**TV-viewer contains a real background initialization path, but it is an early
boot mode, not an ordinary launch preference.** It keeps TV control running and
avoids the normal top-level window-show call. Selecting that path for a normal
cold boot would require an earlier integration point than the current Hub relay
and validation of deferred readiness. No usable persistent override or tested
direct-to-Hub configuration was established.

This investigation used read-only SDK retrieval and offline Ghidra analysis.
No app was launched, stopped or restarted; no boot marker, setting, package,
service or firmware was changed. No reboot or physical-panel test was performed.

## What was examined

The exact installed executable was copied from
`/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` and its checksum verified:

- Package version: `0.2.6` in the live firmware manifest.
- ELF: ARM, 32-bit, 11,083,320 bytes.
- SHA-256: `30e3cd18147227806d3dcce4811affed7426504cfb3c8db5d35fd3347fb7efce`.
- Build ID: `a8e87cec5a9a677d28cbea658d9be91696bed87c`.

Although stripped, the executable retains dynamic C++ symbols. The functions
below are named firmware methods, not names inferred from string proximity.
Ghidra completed analysis successfully. No code was patched.

## The selection happens before ordinary app-control handling

`CAppViewer::m_Create` (`0x6a4e74`) creates the window structures, calls
`m_GetInitType` (`0x6a8f70`), then dispatches one initialization path:

| Internal type | Method | Significant behavior |
| --- | --- | --- |
| 0 | `m_ProcessInitTypeNormal`, `0x6aab3c` | Shows the main window, schedules banner/control work, signals viewer-ready events and schedules show-complete. |
| 1 | `m_ProcessInitTypeBackground`, `0x6ab3a8` | Creates the compositor, loads TV control, initializes TV events, updates the window ID, sets the TVS hint to 1, iconifies the graphics window on non-LFD products and submits `EventPause`. Does not make the normal top-level `evas_object_show` call. |
| 2 | `m_ProcessInitTypeRecovery`, `0x6ab480` | Recovery path that shows the main window; not a hidden cold start. |
| 3 | `m_ProcessInitTypeBackgroundRecovery`, `0x6ab60c` | Separate recovery path; despite its name, it calls `evas_object_show`. |
| 4 | `m_ProcessInitTypeSub`, `0x6ab68c` | Secondary viewer instance, not the main TV/source viewer. |

The background path's `ChangeState(6)` was followed into
`CViewerStateManager::ChangeState` (`0x648304`): 6 dispatches **EventPause**;
7 dispatches EventBackground. Do not conflate the initialization-type enum with
the state-transition enum.

The main instance normally obtains its mode from
`m_GetInitModeFile` (`0x6a9b58`):

```text
repeat:
    if /tmp/init_mode_normal exists:
        return normal
    if /tmp/init_mode_background exists:
        return background
    sleep 10 milliseconds
```

Normal has priority when both exist. The choice is stored in the viewer object
and its internal `CSharedStorage` key `init_type`. That key is not a discovered
writable Vconf switch. Creating a background marker after initialization does
not re-run this selection.

There are additional recovery and model-condition overrides. In particular, an
already-completed `/tmp/tv-viewer_show_done` makes a main viewer restart choose
recovery. Merely restarting the process later would not reproduce the initial
background path. This is one reason a post-boot restart is not an adequate cold-
boot experiment.

## Why a launch argument or manifest tweak is insufficient

The startup script's `cmd=init` is distinct from the bundle key `init`.
`CAppControlHandleProcessor::m_ProcessCmd` (`0x6870e0`) handles the former as an
initial-launch notification; it does not select the background initialization
type. `m_GetInitType` recognizes `init=recovery`, then otherwise uses the early
mode files, subject to its other overrides.

The later `m_ProcessInit` handler (`0x67bf24`) accepts `activate`, `recovery` and
`reset`; other values reach its invalid-value diagnostic. `init=background` is
not an implemented background-mode selector in that handler. The boot manager
contains an `init=background` bundle in a different source/ontimer path, but that
does not override the viewer's already-completed creation-time decision.

The live manifest already has Samsung's `noautoraise` metadata. The normal
initialization method explicitly shows its own window, so adding that metadata
cannot solve this startup behavior.

## Readiness cannot be assumed from a hidden window

The native background path performs meaningful initialization:

- It calls `m_CreateCbShow` (`0x6ad884`), signaling `/tmp/cb_show` without requiring
  the normal visible startup. Despite its name, that event alone is not proof of
  visible pixels.
- `CTvControl::LoadTVControl` (`0x6edb6c`) creates TV/PIP controls. Its full reload
  shows a **child TV control**, distinct from showing the top-level viewer window.
  The presence of `evas_object_show` somewhere in this call tree is therefore
  insufficient to conclude that the viewer becomes foreground.
- It does not execute the normal path's immediate viewer-ready calls or its
  show-complete timer setup.

The identified deferred completion route is:

```mermaid
flowchart LR
    V[Main viewer becomes visible] --> C[Video-window visibility callback]
    C --> B[Background-init completion]
    B --> E[Viewer-ready event 0x19]
    E --> R[Viewer-ready and show-complete signals]
```

`m_VideoWindowVisibleChangedCB` (`0x6c6720`) calls
`m_ProcessBackgroundInitOnVisibleChanged` (`0x6c737c`) on visible state 1. For
initialization type 1 with TVS hint 1, that method loads deferred UI and submits
event `0x19`. `CBannerControl::t_OnEvent` routes it to
`m_HandleViewerReadyEvent` (`0x62945c`), which signals any outstanding:

- `/tmp/tv-viewer_ready`
- `/tmp/tv-viewer_show_done`
- `tv-viewer_ready`

This proves that readiness and initial visibility have coupled paths. It does
not prove that every possible event producer has been exhausted, or that a
modified hidden cold boot must deadlock. A test must record actual signals and
dependent services; it must not manufacture readiness events to make the trial
appear successful.

There is also a separate fast-video path. `m_GetFastBootMode` (`0x6a6c64`) reads
`/tmp/fb_bootmode` and recognizes `BOOT_DTV`, `BOOT_ATV` and `BOOT_HDMI`; fastboot
starts `fastvideo` independently. Avoiding the viewer's top-level window-show
call is not yet proof that no live video appears on the panel.

## Timing and integration consequence

The previously collected `control-one` boot provides a same-run cross-check:

| Event | Kernel uptime |
| --- | ---: |
| Boot manager signals `/tmp/init_mode_normal` | 2.360 s |
| Viewer signals `/tmp/tv-viewer_ready` | 4.004 s |
| Viewer signals `/tmp/cb_show` | 4.015 s |
| Viewer signals `/tmp/tv-viewer_show_done` | 4.547 s |
| Current Mini Hub relay enters | 17.980 s |

These are historical event timestamps, not a new measurement of panel display.
The current relay is much too late to select background initialization. `/tmp`
is recreated during full boot; pre-creating a marker before reboot would not
persist. Leaving both markers present would still select normal.

The productive technical direction is therefore an **early, coordinated
background initialization and Hub handoff**, not a late `init=background`
request, deletion of TV-viewer, or another first-screen preference change. An
acceptable prototype still needs all of the following resolved:

1. A reversible integration point that runs before the viewer selects its mode,
   without creating conflicting boot-mode signals or changing unrelated device
   power/source semantics.
2. A real completion path for viewer/HDMI dependencies while Hub is foreground.
3. Observation of the independent fast-video output and a usable fallback if Hub
   fails to launch.

No supported persistent selector meeting those conditions was found in the
inspected paths. This result identifies a native capability and its integration
constraints; it is not a deployable bypass or evidence of a startup speedup.

## Evidence

Private directory:
`~/.local/share/samsung-tv-research/qn90a/viewer-startup-review/20260922/`.
It contains the firmware copy and hash record, live manifest capture, symbol
inventory, named-function decompilation, readiness-string cross-references and
the final readback. Firmware bytes and raw logs remain outside Git.

The viewer executable was rechecked against the live hash after analysis. Boot
ID, first-screen preferences and foreground application were read back without
altering them. Documentation checks are separate from hardware validation; no
background-mode or boot-time acceptance test was run.
