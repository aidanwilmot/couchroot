# Refusal codes

The SDK transport refuses a connection when firmware or architecture differs from the
profile, matching the existing identity guard. The read-only probe records
runtime and executable-hash differences in private evidence without refusing
the connection. Where an operation already runs the managed guard, a failed
guard uses those diagnostics to explain the refusal. The guards remain
authoritative and run at the same operation boundaries as before, including
the enrolled root-agent transport's initial managed check.

| Code | Fields | Meaning |
| --- | --- | --- |
| `CR-ID-FIRMWARE` | `firmware` | The reported `Version=` value differs from the profile. |
| `CR-ID-ARCH` | `architecture` | `uname -m` differs from the profile. |
| `CR-ID-RUNTIME` | `runtime` | The pinned .NET runtime directory is absent. |
| `CR-ID-HASH` | `dotnet_sha256`, `dotnet_launcher_sha256` | A pinned .NET host executable hash differs or the file is absent. |
| `CR-ID-DEVICE` | model, platform, or `id` | Physical TV identity does not match the site configuration. Device IDs are never shown. |

### CR-ID-FIRMWARE

The TV firmware does not match the exact pinned version. Firmware outside the
profile remains unsupported.

### CR-ID-ARCH

The TV architecture differs from the profile.

### CR-ID-RUNTIME

The profile's pinned .NET runtime directory is missing.

### CR-ID-HASH

The .NET host or launcher does not match its pinned SHA-256 hash.

### CR-ID-DEVICE

The model, platform, or configured device identity differs. Device ID values
are redacted in text and JSON output.

JSON refusals include `code`, `fields`, and `next_steps`. Each field reports
expected and observed values when they are non-identifying. Device identifiers
are represented by redacted placeholders. Firmware, architecture, runtime and
executable hashes may appear in diagnostics.

The explanatory probe runs before the current SDK and root shell guards. Those
guards are still required and unchanged. If the device changes after the probe,
the guard can still stop the operation.

See [device compatibility](device-compatibility.md) for supported profiles and
[TV setup](tv-setup.md#supported-boundaries) for the limits of each profile.
