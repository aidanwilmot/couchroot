#!/bin/sh
set -eu
umask 077

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
toolkit=${SAMSUNG_TV_TOOLKIT:-"$HOME/.local/share/samsung-tv-research"}
sdb_source=${SDB:-}
research="$repo/research"
toolkit_source="$research/toolkit"
upstream_url=https://github.com/chris-ritsen/samsung-tv-root.git
upstream_commit=380dcc23a2f4b1a21b22380e98e6559036acebf7

if [ -z "$sdb_source" ]; then
    sdb_source=$(command -v sdb || true)
fi
if [ -z "$sdb_source" ] || [ ! -x "$sdb_source" ]; then
    echo 'Set SDB to Samsung Tizen Studio sdb executable.' >&2
    exit 2
fi
for command in python3 dotnet openssl git tar; do
    command -v "$command" >/dev/null || {
        echo "Missing required command: $command" >&2
        exit 2
    }
done

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Python 3.12+ is required")'

mkdir -p "$toolkit" "$toolkit/bin" "$toolkit/sessions" \
    "$toolkit/namespace-root-probe" "$toolkit/root-identity-probe" "$HOME/.local/bin"
chmod 700 "$toolkit" "$toolkit/sessions"

cp "$sdb_source" "$toolkit/bin/sdb"
cp "$toolkit_source/"*.py "$toolkit_source/"*.sh "$toolkit/"
if [ ! -f "$toolkit/config.json" ]; then
    cp "$research/config.example.json" "$toolkit/config.json"
fi
cp "$research/namespace-root-probe/"* "$toolkit/namespace-root-probe/"
cp "$research/root-identity-probe/"* "$toolkit/root-identity-probe/"
cp "$toolkit_source/samsung-tv" "$HOME/.local/bin/samsung-tv"
chmod 700 "$HOME/.local/bin/samsung-tv" "$toolkit/"*.sh

if [ ! -d "$toolkit/upstream/.git" ]; then
    git clone "$upstream_url" "$toolkit/upstream"
fi
git -C "$toolkit/upstream" fetch --quiet origin "$upstream_commit"
git -C "$toolkit/upstream" checkout --detach "$upstream_commit"

python3 -m venv "$toolkit/.venv"
"$toolkit/.venv/bin/pip" install --quiet -r "$toolkit_source/requirements.lock"

dotnet build "$toolkit/namespace-root-probe/NamespaceRootProbe.csproj" \
    -c Release --nologo -v quiet
dotnet build "$toolkit/root-identity-probe/RootIdentity.csproj" \
    -c Release --nologo -v quiet

archive="$toolkit/namespace-root-probe/codex-namespace-proof.tar.gz"
signature="$archive.signature"
private_key="$toolkit/namespace-root-probe/test-private.pem"
public_key="$toolkit/namespace-root-probe/public.pem"
if [ "${FORCE_REBUILD:-0}" != 1 ]; then
    for generated in "$archive" "$signature" "$private_key" "$public_key"; do
        if [ -e "$generated" ]; then
            echo "Refusing to overwrite generated probe artifact: $generated" >&2
            echo 'Move the existing private toolkit aside or rerun with FORCE_REBUILD=1.' >&2
            exit 3
        fi
    done
fi
payload_dir=$(mktemp -d "${TMPDIR:-/tmp}/samsung-tv-probe.XXXXXX")
trap 'rm -f "$payload_dir/codex-identity-probe.txt"; rmdir "$payload_dir" 2>/dev/null || true' EXIT HUP INT TERM
printf '%s\n' 'Authorized local TV identity probe.' > "$payload_dir/codex-identity-probe.txt"
chmod 644 "$payload_dir/codex-identity-probe.txt"
tar -C "$payload_dir" -czf "$archive" codex-identity-probe.txt
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$private_key"
openssl pkey -in "$private_key" -pubout -out "$public_key"
openssl dgst -sha256 -sign "$private_key" -out "$signature" "$archive"
openssl dgst -sha256 -verify "$public_key" -signature "$signature" "$archive"

printf '%s\n' "Toolkit installed at $toolkit"
printf '%s\n' 'Review config.json, then run: samsung-tv doctor; samsung-tv status; samsung-tv root-check'
