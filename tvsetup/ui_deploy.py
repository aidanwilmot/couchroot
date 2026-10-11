"""Small UI-only entry point; signing and recovery remain in the setup engine."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from .common import REPO
from .cli import main as setup_main


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    for name in ('plan', 'apply', 'verify', 'resume', 'rollback'):
        command = commands.add_parser(name)
        command.add_argument('--device', required=True, choices=('s90d', 'qn90a'))
        command.add_argument('--site', type=Path, help='Private site config; otherwise TV_SETUP_SITE or the standard location')
        command.add_argument('--json', action='store_true')
        command.add_argument('--dry-run', action='store_true', help='Print workflow only; no tests, signing, or device connections')
        if name in ('apply', 'resume', 'rollback'):
            command.add_argument('--yes', action='store_true', help='Accept the deployment summary; required without an interactive terminal')
        if name == 'apply':
            command.add_argument('--launch', action='store_true', help='Close/reopen Hub after updating; interrupts the current screen')
        if name in ('resume', 'rollback'):
            command.add_argument('--run', required=True, help='UI deployment run ID')
        if name == 'resume':
            command.add_argument('--retry-unchanged', action='store_true', help='Retry only after inspecting an uncertain unchanged install')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    command = 'apply' if args.command == 'resume' else args.command
    forwarded = [command, '--device', args.device]
    if args.site is not None: forwarded += ['--site', str(args.site.expanduser().resolve())]
    if args.json: forwarded += ['--json']
    if getattr(args, 'yes', False): forwarded += ['--yes', '--non-interactive']
    if getattr(args, 'launch', False): forwarded += ['--activate']
    if args.command == 'resume': forwarded += ['--resume', args.run]
    if args.command == 'rollback': forwarded += ['--run', args.run]
    if getattr(args, 'retry_unchanged', False): forwarded += ['--retry-unchanged']
    if args.dry_run:
        print(json.dumps({'scope': 'ui', 'checks': [['npm', 'test']] if args.command == 'apply' else [],
                          'setup_arguments': forwarded, 'preserve_setup_choices': True}, indent=2))
        return 0
    # Fail before device inspection when the local UI is broken. Recovery never
    # depends on a working browser install; it uses the saved journal instead.
    if args.command == 'apply':
        if args.json and not args.yes:
            print('deploy-ui: --json apply requires --yes; use plan --json to review first', file=sys.stderr)
            return 1
        try:
            result = subprocess.run(['npm', 'test'], cwd=REPO, stdout=sys.stderr,
                                    stderr=subprocess.STDOUT, timeout=300)
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
            print('deploy-ui: UI checks unavailable, interrupted, or timed out; no deployment started', file=sys.stderr)
            return 1
        if result.returncode: return 1
    return setup_main(forwarded, ui_only=True)
