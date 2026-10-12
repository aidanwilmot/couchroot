# SDB connection reuse

On 2026-09-22, a Mac SDB 4.2.36 server had 803 TCP sockets in `CLOSE_WAIT` and
failed to connect to QN90A despite the correct Developer Mode address and an open
SDK port. Restarting the host server restored both TV connections. A bounded
follow-up reproduced one leaked socket for each `sdb connect` against an already
connected QN90A; three `sdb devices` queries caused no growth. This establishes a
specific contributor, not the cause of every historical connection failure.

The [official macOS package catalog](https://download.tizen.org/sdk/tizenstudio/official/pkg_list_macos-64)
still listed SDB 4.2.36 when checked. The installed binary exactly matched
`data/tools/sdb` from its official package:

- Package SHA-256: `0bd307ac8382c857be5c2106dd5b8587b10c1c91ac1e504de8432c8276bc28c5`
- Binary SHA-256: `05db410d2e36e85147f95b20bae6296a71c54dab0e1ec79f9e11b89c4b6bd2cd`

The toolkit's `SdbClient.connect()` now checks for the exact ready serial and
reuses it. When a connection is needed, it issues one connect and then verifies
that the serial became ready. A per-target process lock serializes the check and
connect, with a ten-second acquisition timeout. Listing and connection failures
remain visible. This wrapper never restarts the shared server, disconnects
another target, or repeats a submitted TV command.

Use the toolkit client for repeated operations. Direct vendor `sdb connect`
commands still have the observed leak. The `samsung-tv reconnect` command now
ensures its target is ready while retaining an already healthy connection.
The setup script includes the sibling `sdb_connection.py` helper automatically.

Validation passed on the two configured owner TVs: 100 checked-in-wrapper calls
plus 20 installed-wrapper calls added no stale sockets (six before and after).
An intentional QN90A disconnect/reconnect left S90D available, and model/firmware
guards plus SDK uptime reads passed on both. The host suite passed 177 tests,
including a real two-process connection race, bounded lock timeout, and the
actual subclass's raw-connector path. These are bounded observations rather
than a long-term guarantee about the vendor daemon.

A later read-only socket check found the same server still running after 37
minutes 53 seconds, with both TV connections established and the same six
`CLOSE_WAIT` sockets. Follow-up checks after 1 hour 15 minutes and 1 hour 30
minutes found the same PID and socket counts again. A further check after more
than two hours still found both established connections and the same six stale
sockets. No additional restart was performed.

The installed private wrapper was patched narrowly, with its historical commands
preserved and a timestamped backup under the toolkit's `backups/` directory.
The SDB binary and pinned upstream transport checkout were unchanged. Restoring
that backed-up wrapper reverses the private installation change; the unused
helper may remain. Live evidence and the deployment manifest are kept outside
this repository's tracked source.
