# Shared native platform core

`platform-core.h` supports the WebView host and remains shared with the archived
pure-native experiment. It owns the
boot/Home predicates, vconf/sd-bus reads, saved-source rearm (including probe),
app_launcher spawn, consumer filtering and close-on-exec channel creation.
`platform-matrix.h` supplies one test matrix to both launcher host suites.

The normal-mode path is now shared, as requested: both launchers wait within the
120-second boot window, require the Hub ISP owner and saved source, wait for the
screen to turn on, request the signed Hub to retire the TV viewer, then admit
only over the signed Hub. Another app/source cancels. The early background path
keeps its 46-second guard. The bounded wait and app-launch behavior still require
hardware acceptance for native-hub.

WebView and the signed web Hub permit the explicit TV Plus exception.

Linux channels use pipe2(O_CLOEXEC) / SOCK_CLOEXEC atomically. macOS host tests
use a checked fcntl fallback because those Linux APIs are unavailable there.
The source-rearm probe only rewrites an already-correct value. No persistent
service, additional polling loop or recovery state machine was introduced.

The native-launcher-builds CI job cross-compiles the WebView host in the collector
image and checks GLIBC <= 2.17 and startup libpthread dependencies. Host tests
also cover signal masking, malformed /proc stat input under AddressSanitizer,
and refusal of truncated discovery records. No hardware deployment is implied.
