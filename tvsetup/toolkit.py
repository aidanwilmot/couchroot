"""Load the checked-in wrapper only after verifying the external transport checkout."""

import sys
from .common import PRIVATE, REPO, Refused, run

UPSTREAM_COMMIT = "380dcc23a2f4b1a21b22380e98e6559036acebf7"


def load():
    upstream = PRIVATE / "upstream"
    if not (upstream / ".git").exists() or not (PRIVATE / "bin/sdb").is_file():
        raise Refused(
            "Install the source toolkit first: SDB=/path/to/sdb sh tools/setup-toolkit.sh"
        )
    if run(["git", "-C", upstream, "rev-parse", "HEAD"]).strip() != UPSTREAM_COMMIT:
        raise Refused(
            "Transport checkout differs from the reviewed commit; reinstall the toolkit"
        )
    if run(
        ["git", "-C", upstream, "status", "--porcelain", "--untracked-files=normal"]
    ).strip():
        raise Refused(
            "Transport checkout has local changes; use a clean reviewed toolkit"
        )
    sys.path.insert(0, str(REPO / "tools/toolkit"))
    import samsung_tv

    return samsung_tv
