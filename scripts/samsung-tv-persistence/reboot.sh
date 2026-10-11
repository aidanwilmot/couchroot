# Samsung's native reboot request, discovered by live D-Bus introspection.
# Normally requires temporary root; no force flags or direct reboot syscall.
set -eu
printf 'BOOT_BEFORE='; cat /proc/sys/kernel/random/boot_id
cat /proc/uptime
busctl --timeout=5 --system call org.tizen.system.deviced \
  /Org/Tizen/System/DeviceD/Power org.tizen.system.deviced.power \
  Reboot s 'Owner-authorized on-demand root reboot validation'
