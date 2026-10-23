"""First-run defaults remain narrow until a same-target run is verified complete."""

import json
from pathlib import Path
import tempfile
import unittest

from tvsetup import cli
from tvsetup.common import atomic_json
from tvsetup.config import COMPONENTS, DEFAULTS, FIRST_RUN_COMPONENTS, profile, resolve, selected


class FirstRunTests(unittest.TestCase):
    def test_first_run_matches_example_without_cleanup_or_telemetry(self):
        example = json.loads(
            (
                Path(__file__).resolve().parents[1] / "docs/examples/choices.json"
            ).read_text()
        )
        for device in ("qn90a", "s90d"):
            value = resolve(device, first_run=True)
            self.assertEqual(value, {**example, "exclude": []})
            self.assertEqual(selected(value), list(FIRST_RUN_COMPONENTS))
            # Old choices without a verified journal cannot silently opt in.
            value = resolve(
                device,
                saved={
                    "components": list(COMPONENTS),
                    "remove": list(profile(device)["cleanup"]),
                    "telemetry_enabled": True,
                },
                first_run=True,
            )
            self.assertEqual(value, {**example, "exclude": []})

    def test_explicit_components_and_config_still_enable_reviewed_features(self):
        for layer in ("file", "overrides"):
            for device in ("qn90a", "s90d"):
                value = resolve(
                    device,
                    first_run=True,
                    **{layer: {"components": ["cleanup", "telemetry"]}},
                )
                self.assertEqual(selected(value), ["telemetry", "cleanup"])
                self.assertEqual(set(value["remove"]), set(profile(device)["cleanup"]))
                value = resolve(
                    device,
                    first_run=True,
                    **{layer: {"components": ["cleanup"], "remove": []}},
                )
                self.assertEqual(value["remove"], [])

    def test_existing_completed_run_retains_prior_recommendations_and_saved_choices(
        self,
    ):
        for device in ("qn90a", "s90d"):
            self.assertEqual(resolve(device)["components"], DEFAULTS["components"])
            self.assertEqual(
                resolve(device)["remove"], list(profile(device)["cleanup"])
            )
            saved = {
                "components": ["telemetry"],
                "telemetry_enabled": False,
                "remove": [],
            }
            value = resolve(device, saved=saved, first_run=False)
            for key, expected in saved.items():
                self.assertEqual(value[key], expected)

    def test_only_complete_verified_same_target_full_setup_enables_previous_defaults(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "runs/example/journal.json"
            good = {
                "schema": 2,
                "device": "qn90a",
                "target_binding": "synthetic-binding",
                "scope": "setup",
                "phase": "complete",
                "actions": [{"phase": "applied"}],
            }
            self.assertFalse(
                cli.has_completed_verified_run(root, "qn90a", "synthetic-binding")
            )
            non_setup_scopes = (
                "ui",
                "launcher-web",
                "launcher-native",
                "autonomous-root-pilot",
                "native-bootstrap-pilot",
                "native-collector-trial",
                "netdata-native-trial",
                "qn90a-firstscreen-resume-trial",
                "qn90a-source-role-trial",
                "s90d-boot-recovery",
            )
            invalid_journals = [
                {"phase": "configuration-applied"},
                {"phase": "rolled-back"},
                {"phase": "partial"},
                {"device": "s90d"},
                {"target_binding": "different"},
                {"schema": 1},
                {"actions": [{"phase": "uncertain"}]},
                {"actions": None},
                {"scope": None},
            ]
            invalid_journals.extend({"scope": scope} for scope in non_setup_scopes)
            invalid_journals.append({"scope": "missing"})
            for changes in invalid_journals:
                atomic_json(journal, {**good, **changes})
                self.assertFalse(
                    cli.has_completed_verified_run(root, "qn90a", "synthetic-binding")
                )
            missing_scope = dict(good)
            missing_scope.pop("scope")
            atomic_json(journal, missing_scope)
            self.assertFalse(
                cli.has_completed_verified_run(root, "qn90a", "synthetic-binding")
            )
            atomic_json(journal, good)
            self.assertTrue(
                cli.has_completed_verified_run(root, "qn90a", "synthetic-binding")
            )
            # Engine no-op apply also produces a verified complete run.
            atomic_json(journal, {**good, "actions": []})
            self.assertTrue(
                cli.has_completed_verified_run(root, "qn90a", "synthetic-binding")
            )
            value = resolve(
                "qn90a",
                first_run=not cli.has_completed_verified_run(
                    root, "qn90a", "synthetic-binding"
                ),
            )
            self.assertEqual(value["components"], DEFAULTS["components"])


if __name__ == "__main__":
    unittest.main()
