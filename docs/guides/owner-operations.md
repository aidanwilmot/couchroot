# Minimal TV Hub

For current UI updates, use [UI deployment](ui-deployment.md). Full installation
and recovery use [tv-setup](tv-setup.md). The signing and rollback records below
describe historical procedures and evidence.

A local Tizen TV launcher for the owner’s QN55S90DAFXZA.
Remote-editable shortcuts start with Plex and YouTube. Samsung Home remains
available as a fallback. See [Edit apps](edit-apps.md) for controls, discovery
limitations, persistence evidence, and the exact pre-feature rollback. All assets are local; no server, root daemon, feed,
telemetry, external font, or network request is required by the hub.

**Status:** signed and installed on the TV. the owner confirmed the hub displays and
the remote's Plex tile opens Plex. Uninstall and reinstall of the same package
passed. Reboot startup, standby/wake, both app tiles, Home-key routing, and
Samsung Home fallback have passed automated on-TV checks. Details are tracked in
[integration findings](../devices/s90d/README.md).

## Visual design

Version 0.3.8 centers logo-only app cards horizontally and wraps larger lists into
rows, scrolling with focus. The bottom menu remains anchored at the screen edge.
The Home logo, clock, hero heading, slogans, section labels, tile callouts,
descriptions and decorative launch arrows have been removed. Plex/YouTube retain
their geometric artwork; the other discovered consumer apps have bundled brand
colors, typography and geometry. Unknown apps get a readable generated card.
No remote fonts or artwork are fetched. Edit apps uses explicit focus, a scrolling
picker and move/remove controls. Focus feedback is immediate, without animated
travel. The footer gear contains sound, comfortable/compact layout, confirmed
shortcut reset and remote help. Back always stays inside the hub; use the
Samsung Home button to leave.

The current gear also includes menu auto-dimming and an optional 12/24-hour
clock. Navigation uses soft local tones and selection briefly expands the tile.
Rollback of these 0.3.7 additions to 0.3.6 is prepared at
`~/.local/share/samsung-tv-research/signing/quiet-home-rollback/rollback.sh`.

For just the 0.3.6 page redesign, use the prepared rollback to the working 0.3.5
UI: `~/.local/share/samsung-tv-research/signing/pages-polish-rollback/rollback.sh`.
See the feature record for version and validation details.

The exact pre-feature 0.2.2 UI has a signed forward-version rollback prepared at
`~/.local/share/samsung-tv-research/signing/edit-apps-rollback/rollback.sh`.
Use that for this feature's UI rollback. The older original-UI rollback below is
historical and has version 0.2.3, below the new installed version.

The original six app files are preserved privately in
`~/.local/share/samsung-tv-research/signing/ui-before-0.2.0/`.
Restore the original UI with:

```sh
~/.local/share/samsung-tv-research/signing/rollback-ui-0.2.0.sh
```

This installs the original UI under version 0.2.3, avoiding a version downgrade,
and leaves Home/startup configuration intact. Its signed package was prepared
before the final update; this particular visual rollback has not been installed
on the TV. Full startup rollback remains `python3 tools/s90d/restore.py`.

## Preview and checks

For local UI work, follow [UI development](ui-development.md). The browser
workbench uses simulated TV APIs and does not control a device.

```sh
npm ci
npx playwright install chromium
npm run dev
```

Before preparing a release, run `npm test`, inspect `npm run screenshots`, and
build the unsigned WGT with `npm run package`. Signing and installation follow
below. This document's commands target the S90D; use the
[QN90A record](../devices/qn90a/README.md) for that TV's profile and device procedures.

The app IDs are from this TV's package registry, and each target was separately
launched through app_launcher during the previous investigation:

| Tile | Tizen application ID |
| --- | --- |
| Plex | `kIciSQlYEM.plex` |
| YouTube | `9Ur5IzDKqV.TizenYouTube` |
| Samsung Home | `com.samsung.tv.csfs` |

`bridge.js` requests the verified native no-loading hint through app control for
app shortcuts, with ordinary launch fallback if unsupported. Samsung Home uses
the original launch path. See [spinner verification and rollback](../research/launch-spinner.md).
It fails visibly when the runtime or permission is missing.
The manifest requests `application.launch` plus filesystem read/write for
monitoring preferences. The launch privilege and remote input worked for Plex. Other hardware checks are recorded in the integration notes.
The Home key is not intercepted by this app. Power and volume remain system keys.
The hub does not request a wake lock or disable the TV's screen saver.

## Signing and installation

The private toolkit now contains Tizen CLI, a `MinimalHub` signing profile,
and Samsung-issued author/distributor certificates for this TV. the owner completed
the Samsung account login himself. Keys, passwords, certificates, and signed
packages remain outside git under `~/.local/share/samsung-tv-research/`.
Signature enforcement remains enabled.

Run `python3 scripts/sign.py` to sign a private staged copy of the source. It prints the
new package path. Staging keeps generated signatures and certificate subjects
out of the source tree. The output filename is `MinimalHub.wgt`: a filename with
a space failed on this TV, while identical package bytes installed after renaming.

The current 0.3.8 artifact is in the private toolkit's `signing/builds/hub-mxho5h6j/` directory. The original 0.1.0 artifact remains in `signing/package/`:

```sh
cli="$HOME/.local/share/samsung-tv-research/tizen-sdk/cli/tools/ide/bin/tizen"
"$cli" install -s 192.0.2.12:26101 -n MinimalHub.wgt -- \
  "$HOME/.local/share/samsung-tv-research/signing/builds/hub-mxho5h6j"
"$cli" run -s 192.0.2.12:26101 -p MiniHub001.Hub
```

The verified standalone uninstall command is:

```sh
"$HOME/.local/share/samsung-tv-research/tizen-sdk/cli/tools/ide/bin/tizen" \
  uninstall -s 192.0.2.12:26101 -p MiniHub001.Hub
```

Restore any Home/startup assignment **before** uninstalling a configured hub;
see the integration notes for the current rollback command.

## Startup integration

On the S90D firmware 2130.0, the custom Home app needs Samsung's native splash
handoff. Build and install the compatibility variant of the existing screensaver
boot helper after assigning the custom Home app:

```sh
python3 research/s90d-splash/build-helper.py
python3 tools/s90d/splash.py apply
python3 tools/s90d/splash.py status
```

The installer requires the reviewed original helper or this exact variant. It
backs up the original, checks firmware/native/resource/build hashes, and enables
a bounded launch of Samsung's unmodified splash with its existing resource path.
The launch uses the existing AT-HUB startup entry; no new boot service, widget
rebuild or filesystem overlay is added. This integration is S90D-specific.

`python3 tools/s90d/splash.py rollback` disables the addition and restores the exact
original screensaver helper. The renderer, widget and favorites remain intact.
Use this before replacing the screensaver helper with another variant: boot
tracing and splash compatibility currently use separate helper builds. For full
startup rollback, use `python3 tools/s90d/restore.py` to select Samsung Home. The compatible
helper also skips its splash when the custom Home app is not selected. See the
[boot-splash record](../devices/s90d/splash-acknowledgement.md) for details.

The native Home-operation assignment points to `MiniHub001.Hub`,
`db/appfw/home_appid` names the hub, and Smart Hub `auto_start` is integer `1`.
This configuration survived a controlled real reboot with the hub running in the
foreground. Samsung Home remains installed and `db/first_screen/type` remains
unchanged. Writing the derived startup-app string alone was insufficient.

After installing the signed package, run `python3 tools/s90d/enable.py` to select the hub
and enable autostart. Both configuration and rollback use native setters that
preserve the settings' access privileges. The original settings and owner
assignment have private backups. The complete restore command was exercised
successfully:

```sh
python3 tools/s90d/restore.py
```

It requires the existing Mac toolkit and developer-mode connection. It uploads
its own temporary helper and removes it afterward, so recovery does not depend
on a helper being left on the TV. Restore settings before uninstalling the hub.
See [verification and rollback details](../devices/s90d/README.md).

## Verification

Current Edit apps verification is in [the feature record](edit-apps.md). The
following checks describe the original two-tile implementation:

- Six Node tests: desktop simulation, exact target IDs, independent app-control
  launch, unsupported runtime, permission error, rejection of unknown target.
- Browser: Right/Enter selected YouTube; Escape displayed return confirmation;
  Right/Enter selected Samsung Home; visible messages clearly identified previews.
- Visual layout inspected in the in-app browser at its default size and at
  1920×1080. the owner also confirmed the real TV display and Plex tile.
- Native API assignment to the hub and immediate restoration to Samsung Home
  passed; the startup-app string also passed a change/restore test.

## Optional runtime memory cleanup

With the hub open, `python3 tools/s90d/trim-home.py` temporarily stops Samsung's HomeMedia
and HomeSidebar helpers. The main Samsung Home app stays running. The measured
initial gain was about 73–91 MiB of available RAM; Plex/YouTube navigation and
Samsung Home recovery passed. Samsung Home recreates the helpers when opened.
This uses the existing SDK route, requires no root, and changes no boot settings.
For the owner-selected deeper trim, run `python3 tools/s90d/trim-home.py --include-home`.
This also unloads main Samsung Home; reopening it took about nine seconds.
App launches, Home-key routing, cold Samsung Home, Quick Settings and source
overlays passed focused TV checks. Run `python3 tools/s90d/trim-home.py --restore` to
relaunch the full Home family and return to Minimal Hub.
See [measurements and limitations](../devices/s90d/overhead.md).

The background-startup investigation found main Samsung Home already absent in
two post-reboot samples with the existing hub configuration. Its sidebar helper
was present and was trimmed explicitly. No permanent startup block was added;
Samsung Home, Quick Settings or source selection can reload these components.

## Primary references

- [Samsung Application API](https://developer.samsung.com/smarttv/develop/api-references/tizen-web-device-api-references/application-api.html)
- [Tizen application groups and launch privilege](https://github.com/Samsung/tizen-docs/blob/master/docs/application/web/guides/app-management/app-group.md)
- [Samsung remote input](https://developer.samsung.com/smarttv/develop/guides/user-interaction/remote-control.html)
- [Samsung certificate creation](https://developer.samsung.com/smarttv/develop/getting-started/setting-up-sdk/creating-certificates.html)
- [Samsung TV CLI](https://developer.samsung.com/smarttv/develop/getting-started/using-sdk/command-line-interface.html)
