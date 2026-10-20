# Shared native preferences

`preferences.h` owns the bounded `COUCHROOT1` parser and writer used by native-hub
and the WebView import. JavaScript callers use `HubModel.nativeApps()` from
`web/model.js`; `tests/fixtures/preferences.json` pins the shared entry rules
through both C readers, the native shim and the offline importer.

App IDs must be 1–256 ASCII letters, digits, `_`, `.` or `-`. Samsung Home,
MiniHub itself and duplicate IDs are rejected. Names must contain non-whitespace
text. Web storage still normalizes entries and allows 256 favorites. Native
storage deliberately refuses the whole invalid import, allows 128 favorites,
and limits names to 120 UTF-8 bytes without ASCII control characters. It preserves
valid names as supplied instead of trimming them. Nothing rewrites existing web
preferences during conversion.

WebView imports now reject reserved IDs, duplicates and out-of-range selection;
the shim also rejects reserved IDs and duplicates. Empty favorite lists import
with the launcher’s empty selection instead of being discarded. Native readers and the offline
importer now reject whitespace-only names, matching the web reference. Invalid
native files are left intact for recovery. The shim loads after the model so it
uses the same JavaScript validator.
