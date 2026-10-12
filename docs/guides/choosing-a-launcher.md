# Choosing a launcher: web Hub or native Hub

Couchroot has two launchers. They share a purpose: a quiet, remote-first home screen
that opens your apps. They differ in how they reach the screen, what they need from
the TV, and how much of the feature set they carry.

| | Web Hub (`web/`) | Native Hub (`native-hub/`) |
| --- | --- | --- |
| Runs as | A signed Tizen web app (`MiniHub001.Hub`) | An unregistered EFL (Ecore/Evas) window, owner UID, read-only bind |
| Supported TVs | S90D (Tizen 9) and QN90A (Tizen 6) | **QN90A only** (firmware T-NKM2AKUC-2301.1) |
| Install path | Samsung developer signing + `./tv-setup` / `./deploy-ui` | Experimental boot-hook chain; requires the autonomous root agent |
| Becomes Home by | Samsung's own Home/startup assignment (S90D) or the ISP source role (QN90A) | Boot hook dispatch + an overridable Home key grab |
| Software time to Hub after a QN90A reboot | ~37–47 s (best web path) | **~9–10 s** (first rendered frame) |
| Time to Hub on S90D | Started by Samsung at ~2.3 s; no hook needed | Not available |
| Features | Full: favourites, edit/move/undo, settings, sound, hold-OK, fade, telemetry, screensaver, monitoring | Core: favourites, edit/move/undo, settings, app discovery, Home routing; advanced web-only features stay in the web Hub |
| Failure fallback | Samsung Home | Web Hub (installed alongside) and Samsung Home |
| Maturity | Supported source release | Experimental research launcher |

## Pick the web Hub when

- You have an S90D, or any TV other than a QN90A on firmware 2301.1.
- You want the supported, signed install that survives firmware-update review and
  uses only Samsung's normal app APIs.
- Your TV already starts its Home app quickly. The S90D does: Samsung's launch
  pool starts the assigned Home app about 2.3 seconds after boot, at real-time
  priority. That path is out of reach of the QN90A problems described below.
- You need the web-only features (sound, hold-OK, fade, telemetry relay, saver).

## Pick the native Hub when

- You have a QN90A on firmware 2301.1, and boot-to-Hub time matters. The web
  path on this model cannot start earlier than the firmware's app readiness, which
  arrives around 17–40 seconds into boot.
- You can run the autonomous root agent and accept an experimental boot hook,
  with the documented rollback.
- You want a strict no-Live-TV boot. Native admission requires the ISP/background
  boot mode, an empty foreground, the screen on, and a ready compositor. If any
  check fails, native does not draw at all.

Keep the web Hub installed on a native-Hub TV. It remains the manual fallback,
behind the Web Hub button, Back, or a Home press while the native worker is unhealthy.
It also holds the ISP source role that the quiet boot depends on.

## Why the QN90A web path is slow and the native path is fast

On the QN90A, the web Hub can only launch after the firmware's web application
service and its boot readiness chain complete; a long vendor startup sequence runs first.
The native Hub is started directly from the earliest writable boot hook. It renders
with the EFL and Mali libraries that Live TV's viewer has already loaded. That path
had two hidden costs, both fixed in 2026-10:

1. **Boot-time `SCHED_IDLE` demotion.** Samsung's systemd starts every service
   launched after `starter.target` loads (about 7.3 s) with idle CPU priority,
   unless the unit sets `CPUSchedulingPolicy`. The native unit now sets
   `CPUSchedulingPolicy=other`, the same opt-out Samsung's own sensord,
   mbr-daemon and Bluetooth units use. It gets normal nice-0 scheduling, not elevated.
2. **Hook layering.** Experiments had stacked several hash-checked wrapper layers in
   front of the native dispatch. The dispatch now runs first; the other layers still
   run afterwards, in the same order.

See [QN90A boot performance](../devices/qn90a/boot-performance.md) for the
measurements, the evidence, and the remaining limits.

## The QN90A Live TV trap (both launchers)

The QN90A boots quietly only while its saved boot source is `isp-service`. Opening
Live TV or TV Plus immediately changes that saved source, so the next power-on
starts on Live TV. The native Hub now re-arms the source every 15 s, and routes Home
from Live TV through the web Hub. Details are in the
[native Hub README](../../native-hub/README.md#saved-source-re-arm-no-live-tv-after-watching-tv-2026-10-12).
