"""Build the reviewed delayed deviced reboot; never submit it implicitly."""

import re
import shlex


def reboot_command(unit, reason):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", unit):
        raise ValueError("Invalid reboot unit")
    return (
        f"systemd-run --unit={unit} --on-active=10s --timer-property=AccuracySec=1s "
        "-p Type=oneshot -p User=0 -p Group=0 -p SmackProcessLabel=System "
        "--setenv=DBUS_SYSTEM_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/0-system/bus "
        "/usr/bin/busctl --timeout=5 --system call org.tizen.system.deviced "
        "/Org/Tizen/System/DeviceD/Power org.tizen.system.deviced.power Reboot s "
        + shlex.quote(reason)
        + "\n"
    )
