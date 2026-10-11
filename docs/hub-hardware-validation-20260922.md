# Minimal Hub hardware validation — 2026-09-22

This session follows the local UI refinements and uses the UI-only deployment
workflow with matching signed rollback packages. Raw logs, device identities,
screenshots and signed packages remain outside Git.

## QN90A

Hub was updated from 0.4.5 to 0.4.6, then to 0.4.7 after the Samsung Home check
revealed an overlay-specific launch-feedback bug. Final installed content
readback matches the current source. The immediate deployment foreground checks
ran before Hub became foreground; follow-up native state and screenshots
confirmed it without repeating the submitted launches. Both journals are
complete and retain their historical uncertain activation note.

Native arrows, OK and Back exercised grid-move cancellation, saved movement,
removal and Undo. The original six favorites and order were restored: Plex,
YouTube, Disney+, Amazon Music, Crunchyroll and Prime Video. Native launch checks
confirmed Plex and YouTube foreground, followed by Home returning to Hub.

Samsung Home opens as a partial overlay while Hub remains the fullscreen app.
The initial UI treated that visibility as failure after ten seconds. The fix
clears pending feedback on Samsung Home's accepted callback; reported failures
and missing callbacks still retain recovery. A browser regression reproduced
the failure before the fix. The corrected on-TV check waited twelve seconds,
confirmed the Samsung overlay and inspected a clean return to Hub.

The [performance record](samsung-qn90a-performance.md) contains before/after
saver-return observations. They do not establish a speed improvement. A standby
trial lost developer access and needed the owner's physical power-on. The new
boot session showed TV viewer, with no Hub startup-helper status, despite correct
persisted routing and startup configuration. Automatic cold-start and dependable
standby return remain unresolved. Interrupted diagnostic files were removed,
and original protected system-file hashes were verified unchanged.

Runs:

- UI refinements: `20260922T141925Z-e6e1e31e`.
- Samsung Home overlay fix: `20260922T144025Z-b34bbe28`.

## S90D

Hub was updated in place from 0.4.6 to 0.4.7 through run
`20260922T144436Z-106bab15`. Installation, explicit activation and installed-file
readback passed. The journal is complete and a matching signed rollback package
is retained. The three saved shortcuts (Plex, YouTube and Crunchyroll), their
order and the 12-hour clock were preserved.

Native arrows/OK opened the move grid, moved Plex into a draft second position,
and Back discarded the draft. Screenshots confirmed the original order on Home.
Native launch checks confirmed Plex and YouTube foreground and Home return from
both. Samsung Home opened its native fullscreen interface; a subsequent Home
returned to Hub without a recovery dialog. The combined diagnostic reached its
deadline after capturing Samsung Home. Follow-up readback and a separate short
capture confirmed the completed return, without repeating a launch. Diagnostic
cleanup and removal of all session-owned screenshots/probes were verified.
No standby or reboot was requested on S90D during this session.

## Verification boundaries

All 72 automated UI/preview tests pass, including the new Samsung Home overlay
regression. Native injected keys and screenshots confirm the behaviors above;
they do not establish physical-remote hold/repeat behavior or app playback.
No successful standby or reboot acceptance is claimed. HDMI handoff remains
separate research, with Samsung Home as the supported route to inputs.

Private evidence root:
`~/.local/share/samsung-tv-research/hub-validation/20260922T140842Z/`.
