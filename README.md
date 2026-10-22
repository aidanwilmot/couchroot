# Couchroot

**Your couch. Your TV. Your launcher.**

A quiet home screen for Samsung Tizen TVs, with optional telemetry and tools for
setup, administration and recovery. Built around the **QN90A** and **S90D**.
The project is **Couchroot**; the app installed on your TV is named **Minimal Hub**.

[Try it locally](#try-it-locally) · [TV setup](#put-it-on-a-tv) · [Documentation](docs/README.md) · [Release status](docs/project/release-readiness.md)

![Minimal Hub in compact mode, with a clock, app favorites and remote controls](docs/images/compact.png)

*Actual launcher UI in the local browser workbench. All screenshots use simulated
apps and contain no live device or account data.*

## Make yourself at home

- **A home screen you control.** Choose and reorder favorites, switch layouts,
  show a clock and adjust navigation sounds. Use arrows, OK and Back; Samsung
  Home remains one shortcut away.
- **Optional TV monitoring.** Basic health counters on QN90A; app, process and
  startup inspection on S90D. The launcher works without telemetry or a NAS.
- **Administration with recovery.** A separate root agent provides
  authenticated commands, file transfers and jobs. Setup tools verify device
  identity and preserve backups and journals for interrupted operations.

<table>
  <tr>
    <td width="50%"><a href="docs/images/launcher.png"><img src="docs/images/launcher.png" alt="Comfortable layout with large app tiles and a visible remote focus ring"></a></td>
    <td width="50%"><a href="docs/images/settings.png"><img src="docs/images/settings.png" alt="Settings for navigation sounds, tile layout, clock and startup selection"></a></td>
  </tr>
  <tr>
    <td align="center"><strong>Room to browse</strong><br>Large tiles and clear remote focus.</td>
    <td align="center"><strong>Keep it yours</strong><br>Simple settings, directly on the TV.</td>
  </tr>
</table>

## Try it locally

You need **Node.js 22+ and npm**. No TV, signing certificate or root access is
required.

```sh
git clone https://github.com/splitcipher/couchroot.git
cd couchroot
npm ci
npm run dev
```

Open **<http://127.0.0.1:8766>**, choose a scenario and click the preview. Navigate
with the arrow keys, **Enter** for OK and **Escape** for Back. The workbench runs
the shipped web UI with simulated TV APIs; it does not contact a TV or NAS.

## Put it on a TV

Use the **signed web Hub** on the reviewed QN90A or S90D firmware profiles.
Check your exact model and firmware in the [compatibility notes](docs/guides/device-compatibility.md)
first; other Samsung TVs are not automatically supported. This is a source
installation using your own Samsung certificates, not a downloadable universal WGT.

### 1. Prepare your computer

Clone the repository as above, then install the Python dependencies on macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r tvsetup/requirements.txt
```

Use **Python 3.12+**, Samsung SDB and the Tizen CLI/certificate tools, OpenSSL,
Git/OpenSSH, and the **.NET SDK pinned in `global.json`** for the signed helpers.
Follow [host and toolkit setup](docs/guides/tv-setup.md#install-from-source) to
install the vendor tools and set their paths. The preview itself needs only Node.js.

You can inspect the installation recipe before configuring or contacting a TV:

```sh
./couchroot-install plan --device qn90a --launcher web
./couchroot-install doctor --device qn90a --launcher web
```

Replace `qn90a` with `s90d` for that model. `plan` is offline; `doctor` checks
local prerequisites and reports anything missing.

### 2. Enroll your TV and signing identity

Follow [private configuration and signing trust](docs/guides/tv-setup.md#configure-your-installation):

- Enable TV Developer Mode with your computer's address and establish SDB access.
- Copy `examples/site.json` to `~/.config/samsung-tv-hub/site.json` with private
  permissions. Enter your TV's address, exact device identity and signing profile;
  remove unused devices and the NAS section for a TV-only installation.
- Create Samsung certificates authorized for your TV and enroll their reviewed
  author/distributor fingerprints. Example values and another owner's certificates
  cannot be used for your installation.
- Keep the private toolkit, keys, prior signed packages and recovery journals
  outside Git. For an update, retain the installed author's signing identity.

### 3. Inspect, install and verify

These commands **contact the selected TV**. Inspect the proposal before applying it:

```sh
./couchroot-install inspect --device qn90a --launcher web
./couchroot-install apply --device qn90a --launcher web --yes
./couchroot-install verify --device qn90a --launcher web
```

This installs Hub and its Home, AirPlay and startup integration. It does not select
app cleanup, telemetry or NAS changes. It does not reboot; add `--activate` to
`apply` only when you want to open Hub immediately. Confirm arrows/OK/Back,
favorites, app launch and the Samsung Home fallback on the TV.

Keep the reported run ID and original checkout. If installation is interrupted,
use [journaled resume or rollback](docs/guides/universal-installer.md#web-installation-and-recovery)
from that checkout instead of starting over. An installed-file backup alone is
not a signed reinstall package; read the recovery requirements before applying.

### Updating and optional features

| Task | Workflow |
| --- | --- |
| Update Hub on a configured TV | [UI-only deployment](docs/guides/ui-deployment.md): `./deploy-ui plan --device qn90a`, then reviewed apply and verify |
| Add telemetry or other setup components | [Full setup](docs/guides/tv-setup.md) and [telemetry](docs/guides/telemetry.md) |
| Install or administer the root agent | [Agent enrollment and recovery](agent/README.md); a separate, reviewed operation |
| Activate a newer native worker | [Native worker upgrades](docs/guides/native-worker-upgrades.md); package installation alone keeps the committed worker |
| Try the QN90A native WebView launcher | [Experimental WebView procedure](native/webview/README.md); retain the signed web Hub as fallback |

Pure-native drawing is retired. `--launcher native` is retained for existing
journal status and recovery, not new installations.

## Validation status

The signed web Hub and shared telemetry service have been used and reboot-verified
on the reviewed QN90A and S90D profiles. The root agent uses a native worker;
a small .NET acquisition bridge remains, but new packages contain no managed
worker fallback.

**S90D agent 0.7.54 passed hardware acceptance on 2026-10-21:** native upgrades
in both directions, a root command and job, retained-job preservation, and
unattended native startup after reboot. Hub/telemetry files and registrations
were preserved and telemetry resumed on the new boot. Recovery material is retained.

That result does not qualify every installation or recovery path. The latest
QN90A agent upgrade still needs acceptance; interrupted-upgrade fault injection
is locally tested, and physical UI/standby checks remain separate. The S90D
installer reset service startup flags despite the manifest; a reviewed correction
was needed. Verify on-boot/auto-restart registration after agent updates before
relying on unattended startup. See [current acceptance and remaining checks](docs/project/release-readiness.md).

The WebView launcher remains experimental. Other models, regions and firmware
versions are unverified. Before enabling agent loopback acquisition, read its
[recovery procedure](agent/README.md#recovery): a failed start may require restoring
Developer Mode computer access with the TV remote.

## Develop and contribute

The UI lives in `web/`; `preview/` runs it locally. `tvsetup/` contains the shared
setup engine; `agent/` and `telemetry/` contain the shipped services.
`research/` holds experiments and retired code.

```sh
npx playwright install chromium
npm test
npm run screenshots
```

[UI development](docs/guides/ui-development.md) covers preview scenarios and
remote-navigation checks. [Release validation](docs/project/release-readiness.md#validation-and-reproducibility)
covers setup, native and managed checks. .NET is needed for managed components
and full setup, not the browser preview. Follow [Contributing](CONTRIBUTING.md)
and [Security](SECURITY.md); keep device identifiers, credentials and raw logs
out of issues.

## License and credits

Original work is **[0BSD](LICENSE)**. Bundled third-party code retains its own
licenses; see [licensing details](LICENSE-STATUS.md).

Thanks to [Vetro](https://github.com/andrearicci93/vetro) and
[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) for the transport,
root payloads and research behind this work. [Sources & credits](CREDITS.md)
records the full provenance.

*Unofficial. Not endorsed or supported by Samsung. Product names and marks belong
to their respective owners.*
