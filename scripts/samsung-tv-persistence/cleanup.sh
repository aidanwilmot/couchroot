# Remove only known temporary root-probe artifacts; preserve Developer Mode.
set -eu
base=/home/owner/share/tmp/sdk_tools
if ps -eo args | grep -E '^/usr/bin/dotnet /home/owner/share/tmp/sdk_tools/codex-namespace-proof/(NamespaceRootProbe|RootIdentity|DumpLauncher|DumpCollector)\.dll' >/dev/null; then
  echo 'ABORT: a root probe is running; wait for it to finish.' >&2
  exit 3
fi
for name in codex-namespace-proof on-demand; do
  test ! -L "$base/$name"
done
for name in NamespaceRootProbe.dll RootIdentity.dll DumpLauncher.dll DumpCollector.dll public.pem passwd-view dump-config.json; do
  rm -f "$base/codex-namespace-proof/$name"
done
for name in codex-namespace-proof.tar.gz codex-namespace-proof.tar.gz.signature; do
  rm -f "$base/on-demand/$name"
done
for name in codex-namespace-proof on-demand; do
  if test -d "$base/$name"; then rmdir "$base/$name"; fi
done
test "$(sha256sum /etc/passwd | cut -d ' ' -f 1)" = 154b98168c7c6e7d2ab358fa69c6ac6fca6a13b3931fbbb8fb106655f3547a0d
test "$(sha256sum /usr/share/sdbd/public.pem | cut -d ' ' -f 1)" = c83cab64331f092ba99f666b8bb20a49dd1fff04030336c2ea34f6b55ca09d09
test "$(id -u)" = 901
echo 'Temporary root files absent; host originals unchanged; SDK route preserved.'
