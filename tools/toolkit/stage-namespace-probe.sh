set -eu
test ! -e /home/owner/share/tmp/sdk_tools/codex-namespace-proof
test ! -e /home/owner/share/tmp/sdk_tools/on-demand
mkdir /home/owner/share/tmp/sdk_tools/codex-namespace-proof
mkdir /home/owner/share/tmp/sdk_tools/on-demand
sha256sum /etc/passwd /usr/share/sdbd/public.pem
