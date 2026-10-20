cleanup() {
  rm -f /home/owner/share/tmp/sdk_tools/codex-namespace-proof/RootIdentity.dll /home/owner/share/tmp/sdk_tools/codex-namespace-proof/NamespaceRootProbe.dll /home/owner/share/tmp/sdk_tools/codex-namespace-proof/public.pem /home/owner/share/tmp/sdk_tools/codex-namespace-proof/passwd-view
  rm -f /home/owner/share/tmp/sdk_tools/on-demand/codex-namespace-proof.tar.gz /home/owner/share/tmp/sdk_tools/on-demand/codex-namespace-proof.tar.gz.signature
  rmdir /home/owner/share/tmp/sdk_tools/codex-namespace-proof /home/owner/share/tmp/sdk_tools/on-demand
  sha256sum /etc/passwd /usr/share/sdbd/public.pem
}
trap cleanup EXIT
/usr/bin/dotnet /home/owner/share/tmp/sdk_tools/codex-namespace-proof/NamespaceRootProbe.dll /home/owner/share/tmp/sdk_tools/codex-namespace-proof
