"""Application-only tests; no TV, network, repository setup, or vendor binaries."""
import json
import os
import shutil
import socket
import urllib.parse
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class HostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="webview-test-")
        cls.out = Path(cls.temp.name)
        cls.host = cls.out / "host"
        cls.maps = cls.out / "maps"
        flags = ["-std=c99", "-Wall", "-Wextra", "-Werror"]
        shared = ["-dynamiclib"] if sys.platform == "darwin" else ["-shared", "-fPIC"]
        appmanager = cls.out / "libfake-appmanager.so"
        subprocess.run(["cc", *flags, *shared, str(SOURCE / "tests/fake_appmanager.c"), "-o", str(appmanager)], check=True)
        cls.launches = cls.out / "launches"
        launcher = cls.out / "app_launcher"
        # Like the firmware tool, it prints to stdout/stderr; that must not reach the result pipe.
        launcher.write_text('#!/bin/sh\necho "$@" >> "$FAKE_LAUNCH_LOG"\necho "... successfully launched pid = 42"\n'
                            'echo noise >&2\n'
                            'if [ -n "$FAKE_LAUNCH_FG" ]; then printf %s "$FAKE_LAUNCH_FG" > "$FAKE_STATE/fg"; fi\n'
                            'exit "${FAKE_LAUNCH_EXIT:-0}"\n')
        launcher.chmod(0o755)
        # Launcher-role fixtures: guard paths in a short directory (AF_UNIX path limit),
        # fake vconf/systemd, the Hub bundle beside the executable.
        cls.boot = Path(tempfile.mkdtemp(prefix="wv-", dir="/tmp"))
        cls.uptime, cls.marker, cls.ready = cls.boot / "uptime", cls.boot / "marker", cls.boot / "ready"
        cls.normal = cls.boot / "normal"
        cls.socket_path = cls.boot / "wl"
        cls.listener = socket.socket(socket.AF_UNIX); cls.listener.bind(str(cls.socket_path))
        platform = cls.out / "libvconf.so.0"
        subprocess.run(["cc", *flags, *shared, str(SOURCE / "tests/fake_platform.c"), "-o", str(platform)], check=True)
        (cls.out / "libsystemd.so.0").symlink_to(platform)
        (cls.out / "hub").mkdir()
        (cls.out / "hub/index.html").write_text("<!doctype html><title>Hub</title>")
        subprocess.run(["cc", *flags, f'-DMAPS_PATH="{cls.maps}"', f'-DSELF_EXE="{cls.host}"',
                        f'-DAPP_MANAGER_LIBRARY="{appmanager}"', f'-DAPP_LAUNCHER="{launcher}"',
                        f'-DUPTIME_PATH="{cls.uptime}"', f'-DMARKER_PATH="{cls.marker}"',
                        f'-DWM_READY_PATH="{cls.ready}"', f'-DWAYLAND_SOCKET_PATH="{cls.socket_path}"',
                        f'-DNORMAL_MODE_PATH="{cls.normal}"', '-DNORMAL_BOOT_WAIT_LIMIT=12',
                        "-DRESTART_DELAY=0", str(SOURCE / "host.c"), "-ldl", "-o", str(cls.host)], check=True)
        library = cls.out / "libecore_evas.so.1"
        subprocess.run(["cc", *flags, *shared, str(SOURCE / "tests/fake_runtime.c"), "-o", str(library)], check=True)
        (cls.out / "libchromium-ewk.so").symlink_to(library)
        (cls.out / "libelementary.so.1").symlink_to(library)
        # Same fake runtime without the undocumented engine-selection export.
        cls.legacy = cls.out / "legacy"
        cls.legacy.mkdir()
        subprocess.run(["cc", *flags, *shared, "-DOMIT_VERSION_POLICY", str(SOURCE / "tests/fake_runtime.c"),
                        "-o", str(cls.legacy / "libecore_evas.so.1")], check=True)
        (cls.legacy / "libchromium-ewk.so").symlink_to(cls.legacy / "libecore_evas.so.1")
        (cls.legacy / "libelementary.so.1").symlink_to(cls.legacy / "libecore_evas.so.1")
        cls.page = cls.out / "page #?%.html"
        cls.page.write_text("<!doctype html><title>Test</title>")

    @classmethod
    def tearDownClass(cls):
        cls.listener.close()
        shutil.rmtree(cls.boot)
        cls.temp.cleanup()

    DEFAULT = "/usr/share/chromium-efl/lib/libchromium-impl.so"
    UPGRADE = "/usr/share/chromium-efl/upgrade/lib/libchromium-impl.so"

    def run_host(self, mode="success", args=None, mapped=DEFAULT, libraries=None, **extra):
        self.maps.write_text(f"b6000000-b6100000 r-xp 00000000 b3:15 42 {mapped}\n" if mapped else "")
        env = dict(os.environ, FAKE_MODE=mode, FAKE_LAUNCH_LOG=str(self.launches), **extra)
        env["DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"] = str(libraries or self.out)
        return subprocess.run([str(self.host), *(args or [str(self.page)])], env=env,
                              capture_output=True, text=True, timeout=5)

    def test_render_precedes_chromium_and_cleanup_is_ordered(self):
        result = self.run_host()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout
        self.assertLess(output.index("mock elm-init"), output.index("native-first-render"))
        self.assertLess(output.index("native-first-render"), output.index("mock ewk-init"))
        self.assertLess(output.index("mock view-delete"), output.index("mock ewk-shutdown"))
        self.assertLess(output.index("mock ewk-shutdown"), output.index("mock window-free"))
        self.assertLess(output.index("mock window-free"), output.index("mock elm-shutdown"))
        self.assertIn("page%20%23%3F%25.html", output)
        self.assertIn("event=load-finished", output)
        self.assertIn("engine requested=default observed=default", output)
        self.assertNotIn("version-policy", output)
        self.assertIn("page-title=diag ready?ok", output)  # Control byte sanitized.

    def test_deferred_window_requires_loaded_page_and_rendered_frame(self):
        result = self.run_host(args=["--defer-show", str(self.page)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for earlier, later in [("mock ewk-init", "load-finished"),
                               ("load-finished", "page-frame"),
                               ("page-frame", "mock window-show"),
                               ("mock window-show", "native-first-render")]:
            self.assertLess(result.stdout.index(earlier), result.stdout.index(later))
        self.assertEqual(result.stdout.count("mock window-show"), 1)

    def test_deferred_window_does_not_show_on_load_without_frame(self):
        result = self.run_host("no-page-frame", args=["--defer-show", str(self.page)])
        self.assertNotIn("mock window-show", result.stdout)
        self.assertNotIn("page-present", result.stdout)

    def test_deferred_window_does_not_show_failed_page(self):
        result = self.run_host("load-error", args=["--defer-show", str(self.page)])
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertNotIn("mock window-show", result.stdout)

    def test_window_focus_before_load_is_applied_at_load(self):
        result = self.run_host("focus-before-load")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_upgrade_policy_precedes_init_and_is_verified_by_mapping(self):
        result = self.run_host(args=["--engine=upgrade", str(self.page)], mapped=self.UPGRADE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout
        self.assertLess(output.index("mock version-policy=1"), output.index("mock ewk-init"))
        self.assertIn("engine requested=upgrade observed=upgrade", output)

    def test_upgrade_never_reported_when_default_engine_loaded(self):
        for mapped in [self.DEFAULT, None]:
            with self.subTest(mapped=mapped):
                result = self.run_host("engine-mismatch", ["--engine=upgrade", str(self.page)], mapped=mapped)
                self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
                self.assertIn("failure=engine-upgrade-not-loaded", result.stderr)
                self.assertNotIn("mock url=", result.stdout)
                self.assertNotIn("observed=upgrade", result.stdout)

    def test_upgrade_requires_selection_export(self):
        result = self.run_host(args=["--engine=upgrade", str(self.page)], libraries=self.legacy)
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("failure=engine-upgrade-api-unavailable", result.stderr)
        self.assertNotIn("mock ewk-init", result.stdout)

    def test_default_engine_works_without_selection_export(self):
        result = self.run_host(libraries=self.legacy)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_partial_initialization_navigation_and_crash_recover(self):
        for mode in ["init-fail", "view-fail", "url-fail", "load-error", "crash"]:
            with self.subTest(mode=mode):
                result = self.run_host(mode)
                self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
                self.assertIn("event=fallback", result.stdout)
                self.assertIn("mock window-free", result.stdout)

    def test_stop_before_load_is_not_reported_as_webview_failure(self):
        for mode in ["close-early", "sigterm-in-init"]:
            with self.subTest(mode=mode):
                result = self.run_host(mode)
                self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
                self.assertNotIn("mock url=", result.stdout)
                self.assertNotIn("event=fallback", result.stdout)
                self.assertIn("mock window-free", result.stdout)

    def test_elementary_failure_never_creates_window(self):
        result = self.run_host("elm-fail")
        self.assertEqual(result.returncode, 3)
        self.assertNotIn("mock window-free", result.stdout)
        self.assertNotIn("mock ewk-init", result.stdout)

    def bridge(self, title, args=None, **extra):
        self.launches.write_text("")
        result = self.run_host(args=args or ["--native-bridge", str(self.page)], FAKE_TITLE=title, **extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        scripts = [line[len("mock script="):] for line in result.stdout.splitlines() if line.startswith("mock script=")]
        replies = []
        for script in scripts:
            prefix = "window.HubNativePlatform&&HubNativePlatform.receive("
            self.assertTrue(script.startswith(prefix) and script.endswith(");"), script)
            replies.append(json.loads(script[len(prefix):-2]))
        return result, replies

    def test_bridge_discovery_lists_consumer_apps_with_escaped_fields(self):
        result, replies = self.bridge("hubbridge:1:r1:discover")
        self.assertIn("?host=native-webview", result.stdout)
        self.assertEqual(len(replies), 1)
        reply = replies[0]
        self.assertEqual((reply["v"], reply["id"], reply["ok"]), (1, "r1", True))
        apps = {app["id"]: app for app in reply["apps"]}
        self.assertEqual(set(apps), {"kIciSQlYEM.plex", "9Ur5IzDKqV.TizenYouTube", "org.tizen.netflix-app"})
        self.assertEqual(apps["9Ur5IzDKqV.TizenYouTube"]["name"], 'YouTube "TV" \u2028line')
        self.assertEqual(apps["9Ur5IzDKqV.TizenYouTube"]["iconPath"], "")  # Remote icons dropped.
        self.assertEqual(apps["kIciSQlYEM.plex"]["packageId"], "kIciSQlYEM")
        self.assertTrue(all(app["show"] is True for app in apps.values()))
        script = next(l for l in result.stdout.splitlines() if l.startswith("mock script="))
        self.assertNotIn("\u2028", script)  # Raw line separator never reaches the script.

    def test_bridge_discovery_failure_is_reported(self):
        _, replies = self.bridge("hubbridge:1:r9:discover", FAKE_DISCOVERY_FAIL="1")
        self.assertEqual(replies, [{"v": 1, "id": "r9", "ok": False,
                                    "error": {"name": "UnknownError", "message": "Installed apps could not be listed."}}])

    def test_bridge_launch_uses_quiet_hint_except_samsung_home(self):
        _, replies = self.bridge("hubbridge:1:r2:launch:kIciSQlYEM.plex")
        self.assertEqual(replies, [{"v": 1, "id": "r2", "ok": True}])
        self.assertEqual(self.launches.read_text().split(), ["-s", "kIciSQlYEM.plex", "-u", str(os.getuid()),
                                                               "__NO_LOADING_LAUNCH", "enable"])
        _, replies = self.bridge("hubbridge:1:r3:launch:com.samsung.tv.csfs")
        self.assertTrue(replies[0]["ok"])
        self.assertEqual(self.launches.read_text().split(), ["-s", "com.samsung.tv.csfs", "-u", str(os.getuid())])

    def test_bridge_launch_failure_is_not_reported_as_success(self):
        _, replies = self.bridge("hubbridge:1:r4:launch:kIciSQlYEM.plex", FAKE_LAUNCH_EXIT="1")
        self.assertEqual(replies[0]["ok"], False)
        self.assertEqual(replies[0]["error"]["name"], "NotFoundError")

    def test_bridge_rejects_untrusted_or_malformed_requests(self):
        cases = [
            ("hubbridge:1:r5:launch:kIciSQlYEM.plex", None, {"FAKE_CURRENT_URL": "file:///tmp/other.html"}, "origin"),
            ("hubbridge:1:r5:launch:kIciSQlYEM.plex", [str(self.page)], {}, "disabled"),
            ("hubbridge:2:r5:discover", None, {}, "format"),
            ("hubbridge:1:bad-id:discover", None, {}, "format"),
            ("hubbridge:1:r5:launch:a:b", None, {}, "format"),
        ]
        for title, args, extra, reason in cases:
            with self.subTest(title=title, reason=reason):
                result, replies = self.bridge(title, args=args, FAKE_WAIT_MS="200", **extra)
                self.assertEqual(replies, [])
                self.assertIn("bridge-rejected reason=" + reason, result.stderr)
                self.assertEqual(self.launches.read_text(), "")
        for title in ["hubbridge:1:r6:launch:bad id!", "hubbridge:1:r6:uninstall", "hubbridge:1:r6:launch"]:
            with self.subTest(title=title):
                _, replies = self.bridge(title)
                self.assertEqual(replies[0]["error"]["name"], "InvalidValuesError")
                self.assertEqual(self.launches.read_text(), "")

    def test_bridge_follows_window_focus_for_page_visibility(self):
        result, _ = self.bridge("diag ready", FAKE_WAIT_MS="0")
        visibility = [line for line in result.stdout.splitlines() if line.startswith("mock visibility=")]
        # Focus lost before load is not forwarded; afterwards visibility follows focus.
        self.assertEqual(visibility, ["mock visibility=1", "mock visibility=0", "mock visibility=1"])
        plain = self.run_host()
        self.assertNotIn("mock visibility", plain.stdout)  # Diagnostic runs leave visibility alone.

    # ---- Boot launcher role (drop-in for couchroot native-hub) ----
    def launcher(self, args=("--native-guard", "--stay"), mode="success", admitted=True, state=None, timeout=20, normal=False, **extra):
        for path in (self.uptime, self.marker, self.ready, self.normal):
            path.unlink(missing_ok=True)
        if normal: self.normal.touch()
        if admitted:
            self.uptime.write_text("12.50 40.00\n"); self.marker.write_text("enabled"); self.ready.write_text("")
        self.state = Path(tempfile.mkdtemp(dir=self.out))
        values = {"source": "isp-service", "isp": "MiniHub001.Hub", "fg": "", "power": "lcdon"}
        values.update(state or {})
        for name, value in values.items():
            (self.state / name).write_text(value)
        self.launches.write_text("")
        self.maps.write_text(f"b6000000-b6100000 r-xp 00000000 b3:15 42 {self.UPGRADE}\n")
        env = dict(os.environ, FAKE_MODE=mode, FAKE_STATE=str(self.state), FAKE_LAUNCH_LOG=str(self.launches), **extra)
        env["DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"] = str(self.out)
        return subprocess.run([str(self.host), *args], env=env, capture_output=True, text=True, timeout=timeout)

    def test_hidden_launcher_rechecks_source_before_presenting(self):
        result = self.launcher(COUCHROOT_WEBVIEW_DEFER_SHOW="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("page-present", result.stdout)
        self.assertLess(result.stdout.index("hub-ui-ready"), result.stdout.index("page-frame"))
        self.assertLess(result.stdout.index("page-frame"), result.stdout.index("page-present"))

    def test_hidden_launcher_does_not_present_background_without_ui_ready(self):
        result = self.launcher(mode="no-ui-ready", COUCHROOT_WEBVIEW_DEFER_SHOW="1", FAKE_WAIT_MS="100")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("page-present", result.stdout)
        self.assertNotIn("mock window-show", result.stdout)

    def test_hidden_launcher_cancels_for_app_or_source_takeover(self):
        for change in [{"FAKE_FG_AFTER_START": "example.other"}, {"FAKE_SOURCE_AFTER_START": "vc-service"}]:
            with self.subTest(change=change):
                result = self.launcher(COUCHROOT_WEBVIEW_DEFER_SHOW="1", **change)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("presentation-cancelled", result.stdout)
                self.assertNotIn("mock window-show", result.stdout)
                self.assertNotIn("launcher-restart", result.stdout)

    def test_frame_before_load_does_not_present_blank_document(self):
        result = self.run_host("frame-before-load", args=["--defer-show", str(self.page)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(result.stdout.index("load-finished"), result.stdout.index("page-frame"))

    def test_launcher_guard_refuses_without_boot_marker(self):
        result = self.launcher(admitted=False)
        self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
        self.assertIn("admission-denied", result.stdout)
        self.assertNotIn("mock elm-init", result.stdout)

    def test_launcher_guard_refuses_live_tv_boot(self):
        result = self.launcher(state={"source": "vc-service"})
        self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
        self.assertIn("native-values source=vc-service", result.stdout)

    def test_normal_boot_waits_for_display_then_hands_viewer_to_web_hub(self):
        result = self.launcher(normal=True, state={"power": "standby", "fg": "org.tizen.tv-viewer"},
                               FAKE_STANDBY_ONCE="1", FAKE_LAUNCH_FG="MiniHub001.Hub")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for event in ("normal-boot-wait", "power=standby", "normal-boot-web-submitted",
                      "normal-boot-handoff-ready", "admission-passed", "mock elm-init"):
            self.assertIn(event, result.stdout)
        self.assertLess(result.stdout.index("power=standby"), result.stdout.index("normal-boot-web-submitted"))
        self.assertLess(result.stdout.index("normal-boot-handoff-ready"), result.stdout.index("mock elm-init"))
        self.assertEqual(self.launches.read_text().count("-s MiniHub001.Hub"), 1)

    def test_normal_boot_cancels_for_another_app_source_or_isp_owner(self):
        for state in ({"fg":"kIciSQlYEM.plex"}, {"source":"vc-service"}, {"isp":"Another.Hub"}):
            with self.subTest(state=state):
                result = self.launcher(normal=True, state=state)
                self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
                self.assertIn("normal-boot-cancelled", result.stdout)
                self.assertNotIn("mock elm-init", result.stdout)
                self.assertEqual(self.launches.read_text(), "")

    def test_normal_boot_cancels_if_another_app_takes_over_during_handoff(self):
        result = self.launcher(normal=True, state={"fg":"org.tizen.tv-viewer"},
                               FAKE_LAUNCH_FG="kIciSQlYEM.plex")
        self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
        self.assertIn("normal-boot-web-submitted", result.stdout)
        self.assertIn("normal-boot-cancelled", result.stdout)
        self.assertNotIn("mock elm-init", result.stdout)

    def test_normal_boot_never_draws_or_launches_while_standby_persists(self):
        result = self.launcher(normal=True, state={"power":"standby"})
        self.assertEqual(result.returncode, 8, result.stdout + result.stderr)
        self.assertNotIn("mock elm-init", result.stdout)
        self.assertEqual(self.launches.read_text(), "")

    def test_normal_boot_admits_existing_web_hub_without_relaunch(self):
        result = self.launcher(normal=True, state={"fg":"MiniHub001.Hub"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("normal-boot-handoff-ready", result.stdout)
        self.assertEqual(self.launches.read_text(), "")

    def test_launcher_runs_bundle_with_upgrade_engine_and_offers_import(self):
        prefs = self.out / "preferences"
        prefs.write_text("COUCHROOT1 1 2 0 1\nkIciSQlYEM.plex\tPlex\n9Ur5IzDKqV.TizenYouTube\tYou\"Tube\n")
        result = self.launcher(COUCHROOT_NATIVE_STATE=str(prefs), COUCHROOT_NATIVE_HOME="1", FAKE_DRIVE="1", FAKE_WAIT_MS="100")
        output = result.stdout
        self.assertEqual(result.returncode, 0, output + result.stderr)
        for event in ["admission-passed", "launcher engine=upgrade home=1 rearm=0", "first-render-complete",
                      "mock version-policy=1", "mock keygrab XF86Home", "launcher-exited"]:
            self.assertIn(event, output)
        self.assertLess(output.index("admission-passed"), output.index("mock elm-init"))
        url = next(line[len("mock url="):] for line in output.splitlines() if line.startswith("mock url="))
        page, fragment = url.split("#", 1)
        self.assertEqual(page, "file://" + str((self.out / "hub/index.html").resolve()).replace(" ", "%20") + "?host=native-webview")
        self.assertTrue(fragment.startswith("import="))
        self.assertEqual(json.loads(urllib.parse.unquote(fragment[len("import="):])), {
            "shortcuts": {"version": 1, "apps": [{"id": "kIciSQlYEM.plex", "name": "Plex"},
                                                 {"id": "9Ur5IzDKqV.TizenYouTube", "name": 'You"Tube'}]},
            "layout": "compact", "clock": "24h", "start": "last", "selection": "9Ur5IzDKqV.TizenYouTube"})

    def test_launcher_skips_invalid_preferences(self):
        prefs = self.out / "bad-preferences"
        prefs.write_text("COUCHROOT1 1 2 0 0\nbad id!\tBad\n")
        result = self.launcher(COUCHROOT_NATIVE_STATE=str(prefs))
        self.assertIn("preferences-import skipped=entry", result.stdout)
        url = next(line for line in result.stdout.splitlines() if line.startswith("mock url="))
        self.assertNotIn("#import=", url)

    def test_launcher_restarts_failed_hub_then_stops(self):
        result = self.launcher(mode="crash")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("launcher-restart "), 5)
        self.assertIn("launcher-restart-limit", result.stdout)
        self.assertEqual(result.stdout.count("admission-passed"), 1)  # Admission only at boot.

    def test_home_press_raises_hub_over_an_app(self):
        result = self.launcher(COUCHROOT_NATIVE_HOME="1", FAKE_HOME_PRESS="1", FAKE_FG_AFTER_START="kIciSQlYEM.plex")
        self.assertIn("native-home-request", result.stdout)
        self.assertIn("native-home-activate", result.stdout)
        self.assertIn("mock raise", result.stdout)
        self.assertEqual(self.launches.read_text(), "")

    def test_home_press_over_live_tv_leaves_through_web_hub_then_raises(self):
        # Admitted in a quiet boot; Live TV is in front by the time Home is pressed.
        result = self.launcher(COUCHROOT_NATIVE_HOME="1", COUCHROOT_NATIVE_SOURCE_REARM="1", FAKE_HOME_PRESS="1",
                               FAKE_FG_AFTER_START="org.tizen.tv-viewer", FAKE_LAUNCH_FG="MiniHub001.Hub")
        output = result.stdout
        for event in ["native-home-source-fallback", "native-home-fallback-launched", "native-home-resume", "native-home-activate"]:
            self.assertIn(event, output)
        self.assertEqual(self.launches.read_text().split(), ["-s", "MiniHub001.Hub", "-u", str(os.getuid()),
                                                               "__NO_LOADING_LAUNCH", "enable"])

    def test_home_press_denied_when_hub_does_not_own_isp(self):
        result = self.launcher(COUCHROOT_NATIVE_HOME="1", FAKE_HOME_PRESS="1", FAKE_WAIT_MS="800",
                               FAKE_ISP_AFTER_START="other.app")
        self.assertIn("native-home-denied", result.stdout)
        self.assertNotIn("mock raise", result.stdout)

    def test_running_launcher_rearms_saved_source(self):
        result = self.launcher(COUCHROOT_NATIVE_SOURCE_REARM="1", FAKE_DRIVE="1", FAKE_WAIT_MS="2600",
                               FAKE_SOURCE_AFTER_START="vc-service")
        self.assertIn("source-rearm rearmed previous=vc-service", result.stdout)
        self.assertIn("set db/boot/last_service isp-service", (self.state / "log").read_text())

    def test_source_rearm_wait_mode(self):
        result = self.launcher(args=("--source-rearm-wait",), admitted=False, state={"source": "vc-service"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("source-rearm rearmed previous=vc-service", result.stdout)
        result = self.launcher(args=("--source-rearm-wait",), admitted=False, state={"source": "vc-service", "isp": "other"})
        self.assertIn("source-rearm not-isp", result.stdout)
        self.assertFalse((self.state / "log").exists())

    def test_app_launch_then_exit_returns_to_hub(self):
        result = self.launcher(FAKE_TITLE="hubbridge:1:r1:launch:kIciSQlYEM.plex", FAKE_RETURN="1",
                               FAKE_LAUNCH_FG="kIciSQlYEM.plex")
        output = result.stdout
        for event in ["launch=accepted", "app-foreground-observed", "native-return-safe"]:
            self.assertIn(event, output)
        self.assertLess(output.index("app-foreground-observed"), output.index("native-return-safe"))

    def test_window_failure(self):
        for mode in ["window-fail", "fake-fail"]:
            with self.subTest(mode=mode):
                result = self.run_host(mode)
                self.assertEqual(result.returncode, 4)
                self.assertNotIn("mock ewk-init", result.stdout)
                self.assertIn("mock elm-shutdown", result.stdout)

    def test_missing_webview_library_preserves_native_fallback(self):
        library = self.out / "libchromium-ewk.so"
        library.unlink()
        try:
            result = self.run_host()
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn("event=native-first-render", result.stdout)
            self.assertIn("failure=ewk-api-unavailable", result.stderr)
            self.assertIn("event=fallback", result.stdout)
            self.assertNotIn("mock ewk-init", result.stdout)
        finally:
            library.symlink_to(self.out / "libecore_evas.so.1")

    def test_invalid_inputs_never_initialize_graphics(self):
        for args in [["https://example.com"], [str(self.out)], ["/nonexistent/page"],
                     [str(self.page), "-1"], [str(self.page), "0"],
                     [str(self.page), "3601"], [str(self.page), "1oops"],
                     [str(self.page), "9999999999999999999999999"],
                     ["--engine=m120", str(self.page)], ["--engine=upgrade"],
                     ["--engine=upgrade", str(self.page), "5", "extra"]]:
            with self.subTest(args=args):
                result = self.run_host(args=args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("mock", result.stdout)


if __name__ == "__main__":
    unittest.main()
