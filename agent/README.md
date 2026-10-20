# Couchroot administration agent

## Support

The agent provides enrolled, authenticated administration for the pinned QN90A
and S90D firmware profiles. It reacquires a temporary namespace root context;
it does not patch firmware or bypass SMACK. The native worker keeps its small
.NET entry bridge and managed fallback. Phase 2 is merged but has not yet been
accepted on either TV; earlier device results do not qualify the current build.
See [release gates](../docs/project/release-readiness.md).

## Enrolment

Use `python3 -m tvsetup.autonomous_root --help` and the shared setup engine to
prepare per-device artifacts with the private site configuration and enrolled
signing trust. Preparation is local; it does not install or change SDK admission.
Keep the generated keys, pinned certificates and client configuration private.
Install disabled only during an owner-approved, journaled acceptance session.
Verify mutual TLS, rejection of foreign certificates and independent SDK recovery
before enabling loopback acquisition. Certificates expire; renew through explicit
enrolment, never by disabling verification.

After device acceptance, query the enrolled agent with:

```sh
python3 agent/client.py --config PRIVATE_RUN/client.json status
```

## Recovery

Keep the original checkout, immutable journal, signed recovery packages and exact
former Developer Mode Host PC IP available. Use the shared engine's pending-run
checks and device lock; restore the journal's captured state rather than installing
a newer tree over an unfinished run. See [setup recovery](../docs/guides/tv-setup.md).

If the authenticated endpoint works, `client.py --config PRIVATE_RUN/client.json
disable` stops reacquisition. It does not restore SDK admission or undo previous
administrative commands. If loopback admission prevents computer access and the
agent cannot acquire root, use Samsung Apps → Developer Mode to restore the
computer's former Host PC IP and restart. Verify ordinary SDK access before
canceling a timed rescue. Do not assume a disabled or restarted service has restored
settings. The [maintenance procedure](../docs/lab/autonomous-root/README.md#service-restart-during-maintenance)
and the full [required device acceptance, in order](../docs/lab/autonomous-root/README.md#required-device-acceptance-in-order)
require an independent rescue and, on S90D, confirmation that the original host
has exited before relaunching.

## Trust boundary

The HTTPS API requires a pinned client certificate; the client verifies and pins
the server. The loopback worker uses authenticated frames and bounded requests.
An enrolled administrator can execute privileged commands, so possession of the
private credentials is administrative access. Request IDs and durable intent
journals prevent automatic replay; a lost reply remains uncertain until reconciled.
Namespace root is still subject to firmware and SMACK policy. Never expose the
endpoint as an unauthenticated LAN service or treat successful signing as proof of
boot entitlement, recovery or hardware acceptance.

See the [protocol](PROTOCOL.md), [source provenance](UPSTREAM.json), and
[historical capabilities](../docs/lab/autonomous-root/CAPABILITIES.md).
Vendor MIT and payload licenses remain beside their sources.
