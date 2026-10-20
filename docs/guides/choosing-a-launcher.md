# Choosing a launcher

Use the signed web Hub by default. The experimental native option is the
[WebView host](../../native/webview/README.md), which renders that same interface
on the QN90A native boot path.

| | Signed web Hub | Native WebView host |
| --- | --- | --- |
| Targets | QN90A and S90D | QN90A firmware 2301.1 only |
| Installation | `couchroot-install --launcher web`, `tv-setup` or `deploy-ui` | Separate private, journaled WebView procedure |
| Interface | Full shipped UI and Tizen integrations | Shared UI; limited native bridge |
| Features | Favorites, settings, sound, telemetry and screensaver | Favorites, settings, discovery, launch, Home routing and source re-arm |
| Fallback | Samsung Home | Signed web Hub and Samsung Home |
| Status | Default | Experimental; fresh hardware acceptance required |

WebView keeps one interface rather than a separate native drawing implementation.
Its bridge does not provide all Tizen APIs: telemetry, monitoring, screensaver and
platform sound do not automatically carry over. Keep the signed Hub installed as
fallback and as the QN90A ISP source owner. WebView has its own boot admission,
normal-mode handoff, bounded restart and recovery procedure; it is not a public
`couchroot-install` installation option yet.

Recorded QN90A WebView software boots generally showed content at 17–19.7 seconds.
Those measurements do not establish physical-panel, remote-power, standby or
current-release acceptance. S90D native graphics remain unsupported. See the
[WebView evidence and recovery notes](../../native/webview/README.md) and the
[acceptance checklist](../project/release-readiness.md).

Opening Live TV or TV Plus changes QN90A's saved boot source. Source re-arm narrows
the window but cannot guarantee a quiet next boot if power is removed first.

The former pure-native drawing implementation is retired. New installation and
preparation are disabled. Existing `--launcher native` status, verification,
resume and rollback commands remain available **only for old journals**, so
retirement does not strand an installed experiment or its recovery evidence.
