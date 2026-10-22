# Couchroot

**Your couch. Your TV. Your launcher.**

A quiet home screen for Samsung Tizen TVs, plus optional monitoring and the tools
to set it up, administer it and recover it. The project is **Couchroot**; the app
it installs on your TV is called **Minimal Hub**.

Couchroot is a personal passion project, built for my own TVs: a **QN90A** and an
**S90D**. It's shared in case it's useful to you too. Everything here is free to
use, and contributions are welcome.

[Try it locally](#try-it-locally) · [Put it on a TV](#put-it-on-a-tv) ·
[Documentation](docs/README.md) · [Release status](docs/project/release-readiness.md)

![Minimal Hub in compact mode, with a clock, app favorites and remote controls](docs/images/compact.png)

*Actual launcher UI in the local browser workbench. All screenshots use simulated
apps and contain no live device or account data.*

## What it does

- **A home screen you control.** Choose and reorder favorites, switch layouts,
  show a clock and adjust navigation sounds. Use arrows, OK and Back; Samsung
  Home remains one shortcut away.
- **Optional TV monitoring.** Basic health counters on QN90A; app, process and
  startup inspection on S90D. The launcher works without telemetry or a NAS.
- **Administration with recovery.** A separate root agent provides
  authenticated commands, file transfers and jobs. Setup tools verify device
  identity and keep backups and journals for interrupted operations.

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

Open **<http://127.0.0.1:8766>**, choose a scenario and click the preview. Use the
arrow keys, **Enter** for OK and **Escape** for Back. The workbench runs the
shipped web UI against simulated TV APIs; it never contacts a TV or NAS.

## Put it on a TV

Couchroot installs the **signed web Hub** on the reviewed QN90A and S90D firmware
profiles. Other Samsung models are not automatically supported; check the
[compatibility notes](docs/guides/device-compatibility.md) first. This is a source
installation signed with your own Samsung certificates, not a downloadable WGT.

Got a different model? [Porting to a new TV or firmware](docs/guides/porting-to-a-new-tv.md)
walks through building your own device profile, debugging a port and the
decompilation flows behind the existing profiles.

### Check your TV first

Before installing the toolkit, SDKs or signing tools, run the read-only survey
against the TV's address on your local network:

```sh
bin/couchroot-install survey TV_ADDRESS
```

It reads the public identity endpoint once and compares non-identifying model
and platform fields with the reviewed profile registry. An exact model and
platform match is only a preliminary match: firmware, architecture, runtime,
hashes and signing trust are still checked before any operation. A platform
family match is informational and does not enable installation. The survey never
contacts SDB or changes the TV. See the [survey guide](docs/guides/universal-installer.md#survey-a-tv-before-installing-tools).

1. **Prepare your computer.** Install Python 3.12+, Samsung SDB, the Tizen
   CLI/certificate tools, OpenSSL and the .NET SDK pinned in `global.json`
   ([host setup](docs/guides/tv-setup.md#install-from-source)), then:

   ```sh
   python3 -m venv .venv && . .venv/bin/activate
   python -m pip install -r tvsetup/requirements.txt
   bin/couchroot-install plan --device qn90a --launcher web     # offline
   bin/couchroot-install doctor --device qn90a --launcher web   # checks prerequisites
   ```

2. **Enroll your TV and signing identity.** Enable Developer Mode, copy
   [`docs/examples/site.json`](docs/examples/site.json) to
   `~/.config/samsung-tv-hub/site.json` and fill in your TV and certificates. See
   [private configuration and signing trust](docs/guides/tv-setup.md#configure-your-installation).
   Keep keys, signed packages and recovery journals outside Git.

3. **Inspect, install and verify.** These commands contact the TV:

   ```sh
   bin/couchroot-install inspect --device qn90a --launcher web
   bin/couchroot-install apply --device qn90a --launcher web --yes
   bin/couchroot-install verify --device qn90a --launcher web
   ```

   This installs Hub with its Home, AirPlay and startup integration. It does not
   reboot or touch app cleanup, telemetry or a NAS. Keep the reported run ID: an
   interrupted install is finished with
   [journaled resume or rollback](docs/guides/universal-installer.md#web-installation-and-recovery),
   not by starting over.

Use `s90d` in place of `qn90a` for that model. After that:

| Task | Guide |
| --- | --- |
| Update Hub on a configured TV | [UI deployment](docs/guides/ui-deployment.md) (`bin/deploy-ui`) |
| Add telemetry or other components | [Full setup](docs/guides/tv-setup.md) (`bin/tv-setup`) and [telemetry](docs/guides/telemetry.md) |
| Install or administer the root agent | [Agent enrollment and recovery](agent/README.md) |
| Activate a newer native worker | [Native worker upgrades](docs/guides/native-worker-upgrades.md) |
| Try the experimental QN90A WebView launcher | [WebView procedure](native/webview/README.md) |

## Status

The signed web Hub and telemetry service are in use on my QN90A and S90D and have
been reboot-verified on both. The root agent's native worker passed hardware
acceptance on the S90D (agent 0.7.54, 2026-10-21); the latest QN90A agent upgrade
still needs acceptance. The WebView launcher is experimental, pure-native drawing
is retired, and other models, regions and firmware are unverified.

Before enabling agent loopback acquisition, read its
[recovery procedure](agent/README.md#recovery): a failed start may require
restoring Developer Mode access with the TV remote. Details are in
[release readiness](docs/project/release-readiness.md).

## Repository layout

| Path | What's there |
| --- | --- |
| [`web/`](web) | The Minimal Hub UI that ships to the TV |
| [`preview/`](preview) | Local workbench that runs `web/` with simulated TV APIs |
| [`tvsetup/`](tvsetup) | Shared setup engine: signing, identity checks, backups and journals |
| [`bin/`](bin) | Command-line entry points: `couchroot-install`, `deploy-ui`, `tv-setup` |
| [`agent/`](agent) | Root agent service, native worker and recovery |
| [`native/`](native) | Native on-TV components: WebView launcher, boot relay, screensavers, Home routing |
| [`telemetry/`](telemetry) | Monitoring service and collectors |
| [`tools/`](tools) | Per-model device operation scripts and toolkit |
| [`scripts/`](scripts) | Packaging, signing, reproducibility and offline checks |
| [`tests/`](tests) | Unit, browser and integration tests |
| [`docs/`](docs/README.md) | Guides, lab notes, project records, examples and sanitized evidence |
| [`research/`](research) | Experiments and retired code, kept for reference |

## Contributing

Issues, ideas and pull requests are welcome. This is a hobby project, so there is
no support promise or fixed roadmap, but I'm happy to review changes, especially
reports from other Samsung models.

```sh
npx playwright install chromium
npm test                                              # UI and preview
python3 -m unittest discover -s tests -p '*_test.py'  # setup and deployment
```

Read the [contributing guide](.github/CONTRIBUTING.md) and
[UI development](docs/guides/ui-development.md) before opening a PR. Never test
on a TV you don't own, and keep device identifiers, credentials and raw logs out
of issues. Report vulnerabilities privately; see [security](.github/SECURITY.md).

## Built with AI

AI coding assistants, mainly Anthropic's Claude and OpenAI's Codex, are a major
tool in this project. They help write and review code, tests and documentation.
I decide what gets built, review the changes and test them on my own TVs before
relying on them. That said, this is hobby software that runs with root on a TV:
read what a command does before running it.

AI-assisted contributions are welcome on the same terms as any other: understand
your change and say how you tested it.

## License: free to use

All of Couchroot's original code and documentation is released under
**[0BSD](LICENSE)**. You can use, copy, modify and share it for any purpose,
commercial or not, without asking and without attribution.

A few bundled third-party pieces keep their own permissive licenses (MIT and
Unlicense), so keep their notices if you copy them. See
[licensing](docs/project/licensing.md) for the list.

Thanks to [Vetro](https://github.com/andrearicci93/vetro) and
[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) for the transport,
root payloads and research behind this work. [Sources & credits](docs/project/credits.md)
records the full provenance.

*Unofficial. Not endorsed or supported by Samsung. Product names and marks belong
to their respective owners.*
