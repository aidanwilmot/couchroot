# HDMI shortcuts investigation

Status: researched on 2026-09-22. On 2026-10-22 an owner-supervised session on the
owner's QA50QN90AAKXXA (`T-NKM2UABC-2310.0`) verified native switching to a
Chromecast on HDMI 2, and Hub gained an Inputs panel (see below).

## QN90A HDMI switching (2026-10-22)

- `get_source_list` listed the Chromecast by CEC name on HDMI 2 (`sourceType 14`),
  plus a DLNA source and the tuner. HDMI1–4 are source types 13–16, as upstream.
- `connect_source(14)` from an SDK process, and again from a signed no-window app
  launched with an app-control extra, brought `org.tizen.tv-viewer` forward on
  HDMI 2. The owner confirmed picture, sound, remote control of the Chromecast and
  Home returning to Hub. Switching away from a different active input is not yet
  verified.
- The signed helper is `native/qn90a-input-switch` (`MiniHubInput.Switch`), installed
  by the opt-in `inputs` tv-setup component. It accepts only `source=HDMI1..4`,
  is firmware-guarded, replies with an `outcome` extra and exits.
- The remote's Source key routes to `com.samsung.tv.csfs` with
  `entry_point:source_key`. Hub's "All inputs…" uses that entry point; whether the
  extra opens the list (rather than Samsung Home) still needs on-TV confirmation.
- TVWindow was not used: native viewing, not an embedded window, was the goal.

Samsung's public [TVWindow API](https://developer.samsung.com/smarttv/develop/api-references/tizen-web-device-api-references/tvwindow-api.html)
provides `setSource`, `show` and `hide` for a TV window within the web app. It
requires `http://tizen.org/privilege/tv.window`. The
[SystemInfo API](https://developer.samsung.com/smarttv/develop/api-references/tizen-web-device-api-references/systeminfo-api.html)
exposes `VIDEOSOURCE` with connected/disconnected sources identified by type
and number. Signal availability is a separate concern; do not treat a listed
connector as proof of active video.

These APIs make an in-app input viewer plausible. They do not, by themselves,
establish a reliable native full-screen input handoff after Hub leaves the
foreground. That distinction matters for remote routing, audio, HDR/game mode,
standby, and returning Home. A successful callback is insufficient evidence.

## Initial inspection

- S90D: read-only inspection reached the TV while native YouTube was foreground.
  Installed Hub was 0.4.6 and did not request `tv.window`. Playback was left
  undisturbed; no source selection, privilege change or app launch was attempted.
- QN90A: the identity request timed out, so no current capability claim is made.
- The locally available upstream native source helper targets QN90F/QN90B.
  Neither target establishes compatibility with S90D or QN90A.

Private raw inspection evidence is under
`~/.local/share/samsung-tv-research/hub-refinements/20260922T134026Z/`.
It is intentionally outside Git.

## Follow-up hardware inspection

During the authorized UI validation session, both QN90A and S90D were reachable
and their exact model/firmware identities were checked. Both have
`/usr/lib/libsource-api.so`. A temporary, bounded SDK probe called only the
upstream helper's read-only `get_source_list` entry point, using each TV's own
.NET runtime. Both returned a single connected TV entry (`sourceType: 0`) and
no HDMI entries. This does not establish a connected HDMI target or prove that
native switching works on either model.

The S90D source service also exposes `source_service.message` through D-Bus,
but its generic message interface does not supply a verified switching contract.
No source-setting function, D-Bus source command, game-mode setter or HDMI
privilege change was used. Temporary probe files were removed. The first probe
attempt failed because the TV lacks the shell `timeout` command; the successful
probe used its own ten-second process deadline.

To advance the handoff check, identify a powered-on device and its actual HDMI
port on one TV, then verify the model's supported switching route before using
it. Private follow-up evidence is under
`~/.local/share/samsung-tv-research/hub-validation/20260922T140842Z/`.

## Before adding named input tiles

1. Inspect source inventory and supported operations separately on each target.
   Record connector type/number without assuming HDMI numbers are app IDs.
2. Test the selected handoff route during an authorized device session, retaining
   the previous source and a recovery path. Distinguish embedded TVWindow video
   from native viewing. Do not port firmware-specific source commands blindly.
3. Confirm visible video, audio, remote behavior, HDR/game mode, disconnected
   inputs, repeated selection, Home return and standby/restart on both models.
4. Only then add a separate input-shortcut model with friendly names, explicit
   availability and an honest fallback. Preserve existing app shortcut storage
   and keep Samsung Home reachable. Package/sign any necessary privilege change
   through the normal deployment workflow.

Until then, Samsung Home remains the supported route to inputs.
