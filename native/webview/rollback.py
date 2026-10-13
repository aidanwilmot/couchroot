"""Render first-boot recovery commands for a private, journaled installer.

No device access or installation occurs here. The caller provisions a root-owned
state directory and immutable payloads, keeps their hashes in its setup journal,
and inserts dispatch() into the existing boot hook. See README.md.
"""
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from shlex import quote as q


@dataclass(frozen=True)
class Recovery:
    target: str
    backup: str
    state: str
    expected: str
    original: str
    unit: str
    delay: int = 150

    def __post_init__(self):
        for path in (self.target, self.backup, self.state):
            if not path.startswith('/') or '..' in PurePosixPath(path).parts or any(c in path for c in '\n\r\0'):
                raise ValueError('Recovery paths must be absolute and contain no parent traversal/control characters')
        for digest in (self.expected, self.original):
            if not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('Expected a SHA-256 digest')
        if not re.fullmatch('[a-zA-Z0-9_-]+', self.unit) or not 0 <= self.delay <= 600:
            raise ValueError('Invalid unit or recovery deadline')
        if len({self.target, self.backup, self.state}) != 3:
            raise ValueError('Recovery paths must be distinct')

    def guard(self, path, digest):
        return f'test ! -L {q(path)}\ntest "$(sha256sum {q(path)} | cut -d " " -f 1)" = {digest}\n'

    def decision_lock(self):
        lock = q(self.state + '/decision.lock')
        return f'mkdir {lock}\ntrap {q("rmdir " + lock)} EXIT\n'

    def watch(self):
        """Rollback only the exact candidate; serialize the decision with accept()."""
        state = self.state
        return (
            'set -eu\numask 077\n'
            f'exec > {q(state + "/rollback.log")} 2>&1\n'
            'echo watcher-started\n'
            f'test ! -e {q(state + "/accepted")} || {{ echo already-accepted; exit 0; }}\n'
            f'sleep {self.delay}\n' + self.decision_lock() +
            f'test ! -e {q(state + "/accepted")} || {{ echo accepted; exit 0; }}\n' +
            self.guard(self.target, self.expected) + self.guard(self.backup, self.original) +
            f'tmp=$(mktemp {q(str(PurePosixPath(self.target).parent) + "/.webview-rollback.XXXXXX")})\n'
            f'cp -p {q(self.backup)} "$tmp"\n'
            f'mv "$tmp" {q(self.target)}\n' + self.guard(self.target, self.original) +
            f'printf restored > {q(state + "/rolled-back")}\n'
            'echo restored-hook\n'
            'systemctl stop couchroot-native-hub-boot.service\n'
            f'systemd-run --unit={self.unit}-home -p User=5001 -p Group=100 -p SmackProcessLabel=User '
            '--setenv=XDG_RUNTIME_DIR=/run/user/5001 '
            '--setenv=DBUS_SESSION_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/5001-user/bus '
            '/usr/bin/app_launcher -s MiniHub001.Hub -u 5001 __NO_LOADING_LAUNCH enable\n'
        )

    def dispatch(self):
        """Use sh -c: QN90A rejects sh /unsigned/script before executing its body.

        The script is trusted installer data in the root-owned state directory.
        Reading it as one command argument also avoids parsing its contents in
        the outer boot shell. The installer must verify its hash before reboot.
        """
        return (
            f'if test ! -e {q(self.state + "/accepted")}; then\n'
            f'systemd-run --no-block --unit={self.unit} -p DefaultDependencies=no '
            f'-p CPUSchedulingPolicy=other -p RuntimeMaxSec={self.delay + 60} '
            f'/bin/sh -c "$(cat {q(self.state + "/rollback-command")})"\n'
            'fi\n'
        )

    def accept(self):
        """Caller must validate boot/UI and every installed payload first."""
        return ('set -eu\numask 077\n' + self.decision_lock() +
                self.guard(self.target, self.expected) +
                f'test ! -e {q(self.state + "/rolled-back")}\n'
                f'printf verified > {q(self.state + "/accepted")}\n')
