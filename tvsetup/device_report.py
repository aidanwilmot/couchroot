"""Create private, redacted reports from the public survey result only."""

from datetime import date
import json
import os
from pathlib import Path
import re
import shutil

from .common import REPO, Refused
from .registry import CAPABILITIES, profiles

REPORT_SCHEMA = 1
MILESTONES = (
    "root_transport",
    "launcher_install",
    "physical_home",
    "cold_boot",
    "standby_wake",
    "playback",
    "hdmi_game_bar",
)
STATUSES = ("read-only observation", "owner-authorized change", "not tested")
MODEL_RE = re.compile(r"[A-Z]{2}[0-9]{2,3}[A-Z0-9]{5,20}\Z")
PLATFORM_RE = re.compile(r"[0-9]{2}_[A-Z0-9]+_[A-Z0-9_]+\Z")


def _survey_fields(result):
    """Read a narrow allowlist; never copy arbitrary survey input into output."""
    if not isinstance(result, dict):
        raise Refused("Invalid survey result; no report written")
    rows = result.get("comparison")
    if not isinstance(rows, list):
        raise Refused("Invalid survey comparison; no report written")
    observed = {}
    for row in rows:
        if isinstance(row, dict) and row.get("field") in ("modelName", "model"):
            value = row.get("found")
            pattern = MODEL_RE if row["field"] == "modelName" else PLATFORM_RE
            observed[row["field"]] = (
                value if isinstance(value, str) and pattern.fullmatch(value) else None
            )
    verdict = result.get("verdict")
    if verdict not in ("exact_model", "same_platform_family", "unknown"):
        raise Refused("Invalid survey verdict; no report written")
    nearest = result.get("nearest_profile")
    known_profiles = profiles()
    if not isinstance(nearest, str) or nearest not in known_profiles:
        nearest = None
    capabilities = result.get("capabilities")
    safe_capabilities = {}
    if isinstance(capabilities, dict):
        for key in sorted(CAPABILITIES):
            value = capabilities.get(key)
            safe_capabilities[key] = (
                value
                if value
                in ("verified", "verified_other_firmware", "untested", "refused")
                else "unknown"
            )
    developer = result.get("developer_mode")
    if not isinstance(developer, dict):
        developer = {}
    mode = developer.get("mode")
    host = developer.get("host")
    return {
        "model": observed.get("modelName"),
        "platform": observed.get("model"),
        "verdict": verdict,
        "nearest_profile": nearest,
        "nearest_basis": result.get("nearest_basis")
        if result.get("nearest_basis")
        in ("exact_model", "platform_family", "model_only")
        else None,
        "capabilities": safe_capabilities,
        "developer_mode": mode
        if mode in ("enabled", "disabled", "unknown")
        else "unknown",
        "developer_host": host
        if host in ("configured (redacted)", "unknown")
        else "unknown",
    }


def _report_document(survey_result, collected_on):
    fields = _survey_fields(survey_result)
    milestones = {
        name: {"result": "not tested", "evidence": None} for name in MILESTONES
    }
    return {
        "schema": REPORT_SCHEMA,
        "date": collected_on,
        "target": {
            "model": fields["model"],
            "platform": fields["platform"],
            "firmware": None,
            "tizen_version": None,
        },
        "method": {
            "operation": "one bounded read-only GET to the public TV identity endpoint",
            "sdb_contacted": False,
            "developer_mode": fields["developer_mode"],
            "developer_host": fields["developer_host"],
        },
        "survey": {
            "verdict": fields["verdict"],
            "nearest_profile": fields["nearest_profile"],
            "nearest_basis": fields["nearest_basis"],
            "capabilities": fields["capabilities"],
        },
        "milestones": milestones,
        "limitations": [
            "Firmware and Tizen version were not read by the public identity survey.",
            "No SDB, install, physical Home, cold-boot, standby, playback or HDMI/Game Bar test was performed by this survey.",
            "A model/platform or platform-family match does not grant device or firmware support.",
        ],
    }


def _markdown(document):
    target = document["target"]
    survey = document["survey"]
    method = document["method"]
    lines = [
        "## TV device report",
        "",
        f"- Collected: {document['date']}",
        f"- Survey verdict: `{survey['verdict']}`",
        f"- Nearest profile: `{survey['nearest_profile'] or 'none'}` ({survey['nearest_basis'] or 'no match'})",
        f"- Model code: `{target['model'] or 'not observed'}`",
        f"- Platform code: `{target['platform'] or 'not observed'}`",
        "- Firmware: not observed by survey",
        "- Tizen version: not observed by survey",
        f"- Developer Mode: `{method['developer_mode']}`",
        f"- Developer host: `{method['developer_host']}`",
        "- SDB contacted: no",
        "",
        "### Profile capability evidence",
        "",
    ]
    if survey["capabilities"]:
        lines.extend(
            f"- `{key}`: `{value}`" for key, value in survey["capabilities"].items()
        )
    else:
        lines.append("No nearest profile capability table is available.")
    lines.extend(
        (
            "",
            "### Milestone results",
            "",
            "The default is `not tested`. For any result you report, use exactly one label: `read-only observation`, `owner-authorized change`, or `not tested`.",
            "",
        )
    )
    names = {
        "root_transport": "Root / transport",
        "launcher_install": "Launcher install",
        "physical_home": "Physical Home behavior",
        "cold_boot": "Cold boot",
        "standby_wake": "Standby / wake",
        "playback": "Playback",
        "hdmi_game_bar": "HDMI / Game Bar",
    }
    for key, value in document["milestones"].items():
        lines.extend(
            (
                f"#### {names[key]}",
                "",
                f"Result: `{value['result']}` (read-only observation / owner-authorized change / not tested)",
                "",
                "Evidence: not provided",
                "",
            )
        )
    lines.extend(("### Limitations", ""))
    lines.extend(f"- {item}" for item in document["limitations"])
    lines.extend(
        (
            "",
            "### Redaction check",
            "",
            "This report contains no device ID/UUID, DUID, MAC address, IP address, serial number, token or credential. Review any added evidence before posting.",
            "",
        )
    )
    return "\n".join(lines)


def _profile_skeleton(survey_result):
    fields = _survey_fields(survey_result)
    reference = fields["nearest_profile"]
    if reference is None:
        raise Refused("A profile skeleton requires a deterministic nearest profile")
    base = profiles()[reference]
    diff = []
    for key, observed, field in (
        ("model", fields["model"], "modelName"),
        ("platform", fields["platform"], "model"),
    ):
        diff.append(
            {
                "field": key,
                "profile_value": base[key],
                "observed_value": observed,
                "status": "match" if base[key] == observed else "different",
                "survey_field": field,
            }
        )
    # This is deliberately profile-shaped enough to guide research, but all
    # unverified identity/layout/runtime/hash data are null and the registry
    # must reject the marker if a user copies it into the accepted profile set.
    return {
        "_marker": "UNVERIFIED",
        "_diff_against": reference,
        "id": None,
        "name": None,
        "model": fields["model"],
        "platform": fields["platform"],
        "firmware": None,
        "architecture": None,
        "framework": None,
        "runtime": None,
        "host_sha256": None,
        "startup": None,
        "chart_prefix": None,
        "snapshot": None,
        "launcher_sha256": None,
        "helper_sha256": None,
        "collector_sha256": None,
        "dashboard_config_path": None,
        "capabilities": {key: None for key in sorted(CAPABILITIES)},
        "cleanup": None,
        "reasons": None,
        "source_hashes": None,
        "boot_artifacts": None,
        "service_artifacts": None,
        "saver_generated": None,
        "diff": diff,
    }


def _write_private(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_report(survey_result, destination, *, profile_skeleton=False):
    """Write redacted JSON/Markdown to a new private directory; return its path."""
    requested = Path(destination).expanduser().absolute()
    if requested.exists() or requested.is_symlink():
        raise Refused("Report output already exists; choose a new private directory")
    # Reject symlinked parents resolving into the checkout as well as direct paths.
    resolved = requested.resolve(strict=False)
    repo = REPO.resolve()
    if resolved == repo or repo in resolved.parents:
        raise Refused("Keep device reports outside the source checkout")
    document = _report_document(survey_result, date.today().isoformat())
    markdown = _markdown(document).encode("utf-8")
    files = {
        "device-report.json": (
            json.dumps(document, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        "device-report.md": markdown,
    }
    if profile_skeleton:
        files["profile-skeleton.json"] = (
            json.dumps(_profile_skeleton(survey_result), indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    requested.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    created = False
    try:
        requested.mkdir(mode=0o700)
        created = True
        requested.chmod(0o700)
        for filename, data in files.items():
            _write_private(requested / filename, data)
        return requested
    except BaseException:
        if created:
            shutil.rmtree(requested, ignore_errors=True)
        raise
