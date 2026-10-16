"""Bounded rolling observation scheduler; device operations belong to its adapter.

Adapters must journal each mutation before submission, never retry uncertain
outcomes, check the installed identity/selection, and validate/clean only owned
completed collectors. A failure deliberately leaves recovery armed and receipts
for reconciliation. This module does not authenticate devices or launch binaries.
"""
from dataclasses import dataclass
import math
import time


class ObservationStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class Plan:
    seconds: int
    window_seconds: int = 220
    stride_seconds: int = 160
    renew_seconds: int = 120
    health_seconds: int = 10

    def validate(self):
        values = (self.seconds, self.window_seconds, self.stride_seconds,
                  self.renew_seconds, self.health_seconds)
        if any(type(v) is not int for v in values):
            raise ValueError('plan values must be integers')
        if not (2 <= self.seconds <= 90000 and 40 <= self.window_seconds <= 240
                and self.window_seconds / 2 < self.stride_seconds <= self.window_seconds - 20
                and 10 <= self.renew_seconds <= 120 and 1 <= self.health_seconds <= 10):
            raise ValueError('invalid duration, overlap or recovery budget')
        return 1 + max(0, math.ceil((self.seconds - self.window_seconds) / self.stride_seconds))


def require_storage(free_bytes, plan, concurrent_runs=1, initial=False):
    """Check a caller-read free-space snapshot; this does not reserve disk blocks.

    Initial allowance covers maximum capture sizes plus 1 GiB of private receipts
    per concurrent run and a shared 2 GiB floor. Ongoing checks retain the floor.
    Other writers can still consume space after the check; I/O errors must abort.
    """
    if type(free_bytes) is not int or free_bytes < 0 or type(concurrent_runs) is not int or not 1 <= concurrent_runs <= 2:
        raise ValueError('invalid free-space snapshot or concurrent run count')
    count = plan.validate()
    capture_bytes = 10 * 1024**2 + 2 * 65536 + 4096
    required = 2 * 1024**3
    if initial:
        required += concurrent_runs * (count * capture_bytes + 1024**3)
    if free_bytes < required:
        raise ObservationStopped('host storage budget exhausted; preserve evidence and recovery')
    return required


def require_device_storage(output, minimum_free_bytes=256 * 1024**2):
    """Validate `LC_ALL=C df -Pk` for the two adapter-guarded device paths.

    Call synchronously from health(), never from a competing API client. The
    adapter binds the command/device; this parser cannot authenticate its output.
    """
    if type(minimum_free_bytes) is not int or minimum_free_bytes < 0:
        raise ValueError('invalid device storage floor')
    if not isinstance(output, str) or len(output) > 16384:
        raise ObservationStopped('invalid device storage response')
    lines = output.splitlines()
    if len(lines) != 3 or lines[0].split() != ['Filesystem', '1024-blocks', 'Used', 'Available', 'Capacity', 'Mounted', 'on']:
        raise ObservationStopped('incomplete device storage response')
    available = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 6 or not all(value.isascii() and value.isdecimal() for value in fields[1:4]):
            raise ObservationStopped('invalid device storage counters')
        total, used, free = map(int, fields[1:4])
        if total <= 0 or used > total or free > total or used + free > total:
            raise ObservationStopped('inconsistent device storage counters')
        available.append(free * 1024)
    if min(available) < minimum_free_bytes:
        raise ObservationStopped('device storage floor exhausted; preserve evidence and recovery')
    return min(available)


def run(adapter, plan, clock=time.monotonic, sleep=time.sleep):
    """Return captures and the still-armed rescue after all windows are collected.

    Adapter interface: health(), arm_rescue(delay_seconds), retire_rescue(handle),
    launch(index, seconds), collect(handle). arm_rescue must confirm an active
    independent timer before returning. retire_rescue checks it never fired before
    stopping it and then confirms inactivity. collect requires successful exit,
    hash-verified durable download, native identity coverage and owned cleanup.
    Every method must have bounded calls; an exception stops the run without replay.
    Device-space checks belong inside health(), serialized with all other calls.
    Host deadlines are conservative scheduling guards, not capture evidence.
    Offline verification of TV clocks/records remains mandatory after this returns.
    """
    count = plan.validate()
    adapter.health()
    armed_at = clock()
    rescue = adapter.arm_rescue(300)
    windows = []
    live = []
    launched = 0
    next_launch = clock()
    next_health = next_launch

    def check_budget():
        if clock() >= armed_at + 270:
            raise ObservationStopped('recovery renewal margin exhausted; inspect receipts, do not replay')

    check_budget()
    while live or launched < count:
        check_budget()
        now = clock()
        if now >= next_health:
            adapter.health()
            check_budget()
            next_health = clock() + plan.health_seconds
        if clock() >= armed_at + plan.renew_seconds:
            # Keep the previous independent rescue live until the new one is
            # confirmed active. Never retire it after a failed/uncertain arm.
            adapter.health()
            check_budget()
            replacement_at = clock()
            replacement = adapter.arm_rescue(300)
            check_budget()
            adapter.retire_rescue(rescue)
            check_budget()
            rescue, armed_at = replacement, replacement_at
        if live and clock() >= live[0][1] + plan.window_seconds:
            handle, _ = live[0]
            windows.append(adapter.collect(handle))
            check_budget()
            live.pop(0)
        if launched < count and clock() >= next_launch:
            if len(live) >= 2:
                raise ObservationStopped('two collectors still owned; refuse unbounded launch')
            if live and clock() >= live[-1][1] + plan.window_seconds:
                raise ObservationStopped('collector overlap lost; do not fill the gap retrospectively')
            adapter.health()
            check_budget()
            handle = adapter.launch(launched, plan.window_seconds)
            check_budget()
            began = clock()  # Later than actual launch: safe for completion wait.
            live.append((handle, began))
            launched += 1
            next_launch = began + plan.stride_seconds
        if live or launched < count:
            sleep(1)
    adapter.health()
    check_budget()
    return dict(captures=windows, rescue=rescue, planned_windows=count)
