# QN90A package-image startup investigation

2026-09-21, firmware `T-NKM2AKUC-2301.1`. **Read-only ext4 and SquashFS images
do not by themselves admit our unsigned native executable.** Both mounted
successfully in a bounded QN90A trial; the kernel rejected execution as unsigned.
The previously successful read-only VDFS view remains a distinct result.
Production still uses the managed collector. Native boot persistence is unresolved.

## Package lifecycle findings

Offline analysis used the exact QN90A app2sd capture and eight additional
hash-verified installer files obtained through guarded, read-only SDK access.

| Path | Finding | Consequence |
| --- | --- | --- |
| app2sd on-demand startup | `OndemandSetupInit` reaches `app2sd_usr_on_demand_setup_init` at `0x13fbc`, which calls `_app2sd_mount_app_content` with mode 0 at `0x1438c`. Mode 0 mounts ext4 with `MS_RDONLY\|MS_NOSUID`. | Launch-time read-only mounting is established statically; it is no longer merely a string-based hypothesis. |
| app2sd installation | Pre-install prepares the encrypted image and uses writable mount mode 1. Post-install finalizes/unmounts it and records external storage on success. | Image preparation and launch use different mount modes. |
| Image discovery | `_app2sd_find_loopback_device_path` at `0x25bbc` enumerates USB devices and checks the package image under their `app2usb` directories. | A database row or internal file alone does not satisfy this lookup. No USB volume was mounted during inspection. |
| Vendor TPK backend | `StepVdAdjustInstallLocation` checks the app2usb reservation, retrieves its USB path, and sets `installed_external`; `StepVdAcquireExternalStorage` delegates image preparation. | The vendor installer contains the external-storage integration. Its complete acceptance for our signed package has not been tested. |
| Extended storage | `MoveExtended` moves directories and creates a symlink. Platform paths resolve under `/opt/extendedsd`, separately from app2sd image mounting. | This branch supplies no read-only mount of executable content. |
| Internal mounted package | The vendor installer recognizes `.tmk`, mounts it to read `tizen-manifest.xml`, and has a mount-install workflow. Root `MountSystem` uses a loop mount with `nosuid`; the non-root branch delegates through `PS_Mount`. The TPK mount-install sequence includes a signature step. | This is a real internal image-install path, but neither developer signing acceptance nor reboot restoration was established. The filesystem test below rejects the proposed mount-only execution benefit. |

The app2sd D-Bus privilege and caller checks remain in force. No direct D-Bus
request, registry injection, package installation, vendor-container operation or
boot change was used to obtain these findings. All 362 package records observed
during inspection used `installed_internal`.

## Filesystem admission trial

Trial `20260921T212800Z-bf9b491d` used the same original ARM execution probe that
returned 42 through the read-only VDFS view. Its SHA-256 is
`08f6c365f0767c635acf9cfb40083d808203f11e6a15139608a708fd76104ffa`.
The host built a small gzip-compressed SquashFS image and an 8 MiB ext4 image
with older-kernel-compatible features. Independent extraction from each image
matched the probe bytes before transfer.

Each temporary system unit had `PrivateMounts=yes`, no restart, a 12-second
runtime limit, `NoNewPrivileges=yes`, and only the capabilities needed for mount
setup and dropping identity. A managed diagnostic mounted its image read-only,
then dropped supplementary groups, GID to 100 and UID to 5001 before attempting
the native process. At that point inheritable, permitted and effective capability
sets were zero; the bounding set retained the setup subset. No `BindReadOnlyPaths`
property supplied an additional VDFS execution view.

| Filesystem | Mount result | Native execution | Kernel evidence |
| --- | --- | --- | --- |
| ext4 | Success; `ro,nosuid,nodev` | `EPERM`, diagnostic exit 77 | UEP says the probe is unsigned; filesystem `ext4` |
| SquashFS | Success; `ro,nosuid,nodev` | `EPERM`, diagnostic exit 77 | UEP says the probe is unsigned; filesystem `squa` |

Neither probe reached `main`. These are filesystem-admission tests, not tests of
normal `.tmk` installation, signed external-package registration, cold boot or
standby. They establish that ordinary read-only image mounting does not reproduce
the successful VDFS behavior. Adding USB storage alone is therefore insufficient.
Other package trust mechanisms, if found, would require separate evidence.

## Cleanup and production continuity

The initial cleanup removed both units, staging files, code and output directories,
but its explicit leak check found two remaining loop-device associations. This
firmware's mount helper did not automatically detach them when the private mounts
exited. The run remained pending until recovery completed.

Recovery first verified absent units/paths and matched each loop's backing-file
identity to this run, then explicitly detached only those two devices. An initial
guard rejected the filesystem-relative, deleted-file spelling of `backing_file`
before submitting a detach; a fresh observation resolved that spelling. Final
cleanup passed and the journal is terminal `rolled-back`. Future image trials
must record and explicitly clean their loop associations rather than assuming
autoclear.

QN90A's SDK and zone-manager retained their PIDs and zero restart counts. Both
managed receiver sessions and boot identities were unchanged and each advanced
13 samples. Final sample ages were 3.82 seconds for QN90A and 3.24 seconds for
S90D. No collector restoration or foreground launch was necessary.

## Remaining decision

Prefer internal storage. The owner accepts an attached USB drive only as a
fallback, but these results do not justify requesting one for a mount-only fix.
The proven common design still needs an authorized privileged bootstrap to
prepare the VDFS execution view and system unit. QN90A's reviewed persistent
boot paths have not supplied one; the management-host pilot also still lacks
reliable postboot SDK acceptance. Keep the managed production path until one
passes autonomous startup and lifecycle tests.

Private reproduction evidence is under
`native-service-probe/app2sd-continuation-20260921/`, with the live journal and
full output in the setup run above. It includes both capture manifests,
Ghidra exports, ELF-backed literal resolution, independent ARM disassembly of
the on-demand/mount calls, image readback, the diagnostic source and recovery
observations. Firmware binaries and raw device evidence remain outside Git.
