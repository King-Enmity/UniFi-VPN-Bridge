# Experimental routing engine v0.3

> **DANGER — NOT PRODUCTION READY.** This is a prototype under active development. It modifies kernel routing policy, firewall tables, and may lock users out or expose remote VPN traffic if UniFi reloads firewall rules. It has **not** passed real-device or packet-level leak tests. Do not activate it on a production gateway or rely on it for privacy.

This implementation is on `development` only. Stable `main` and preview `coming-soon` remain read-only.

## The intended traffic path

```text
Remote laptop / phone
    -> UniFi Teleport / WireGuard Server / OpenVPN Server
    -> UniFi gateway
         |-> Explicit local LAN networks: native LAN route (UniFi security rules still apply)
         \-> Internet: selected outbound UniFi VPN client (WireGuard/OpenVPN)
                  -> NordVPN / Proton VPN / Mullvad / other provider
```

Incoming traffic must actually traverse the gateway. A split-tunnel remote client that sends web traffic directly to its local ISP will bypass this project.

## Implemented experimentally

- Explicit per-source VPN profiles: protocol, validated ingress interface, incoming client IPv4 subnet, outbound UniFi VPN client interface, allowed LAN CIDRs, DNS resolver.
- Resolve unique existing UniFi client VPN firewall marks from `ip -4 rule` and route tables (never write UniFi-owned policy tables).
- IPv4 marking and source-specific NAT into the selected outbound VPN.
- IPv4 forwarding drop guard for ingress interfaces, with explicit LAN exceptions.
- Source-address policy rule with a `prohibit` fallback above ordinary main WAN routing, with explicit LAN destination exceptions.
- DNAT normal TCP/UDP port-53 DNS requests to a specified public resolver; marks outbound DNS for the same VPN tunnel.
- Block all forwarded IPv6 from ingress interfaces until IPv6 routing can be verified.
- Alternate A/B chains for replacements; do not intentionally flush a referenced chain.
- `plan`, `apply --experimental`, `status`, `watch --experimental`, and optional `install-service --experimental` with `systemd` recovery.
- Strict, non-executable JSON configuration; no external package installers or telemetry.

## Security limitations requiring work before real installation

1. **No hardware verification.** UDM/UDM SE/Pro/Pro Max and firmware variants may behave differently, especially OpenVPN and Teleport.
2. **Firewall reload risk.** UniFi may replace or reorder built-in chains between watchdog polls. A watchdog is not an instantaneous guard, and a software kill switch cannot guarantee zero exposure across all firmware reload scenarios.
3. **DNS scope.** Port-53 DNS is redirected, but encrypted DNS (DoH over HTTPS, DoT on 853, DoQ), device/browser-local DNS, IPv6 DNS, and gateway-managed DNS are not fully controlled. A public DNS address is **not** itself a privacy guarantee.
4. **IPv6.** Forwarded IPv6 traffic is blocked in the supported ingress interfaces. IPv6 to local router services and router-originated DNS require further validation.
5. **No transactional rollback yet.** Partially applied changes may require manual repair. A/B chains prevent deliberate flushes of live chains but do not provide full transactionality. No safe automatic teardown or rollback command is offered yet.
6. **Firewall rule precedence.** Kernel and UniFi firewall policy order must be checked on real gateways. The code refuses ambiguous VPN marks but does not prove existing higher-priority policy rules cannot bypass the fallback.
7. **Boot persistence.** A service unit and on-boot hook can be generated, but boot hook execution requires a *separately installed* udm-boot system service. This project does not install it. Firmware update behavior is unverified.
8. **No tests of actual WAN IP, LAN isolation, DNS, tunnel-down failure, WAN failover, VPN disconnect, or remote management connectivity.** CI checks only decision logic and syntax.

## Offline inspection

Read `bin/bridge-engine.py` and `examples/config.experimental.json` before doing anything else. The example CIDRs and interfaces are placeholders, NOT usable defaults.

Run the pure unit tests on your laptop or in an isolated CI runner:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/bridge-engine.py
```

The `plan` subcommand shows intended operations without changing firewall/kernel state. It reads live routing information, so it would need to run on a suitably permitted test gateway:

```bash
python3 bin/bridge-engine.py plan --config /path/to/test-config.json
```

**Do not invoke `apply`, `watch`, or `install-service` on your production router.** These are intentionally gated behind `--experimental`.

## Release criteria

Before promotion to `coming-soon` or `main`, verify on an isolated UniFi gateway with a recovery path:

- Teleport, WireGuard and OpenVPN source interface and CIDR discovery.
- Forwarded packet-path route marks and NAT for every selected outbound VPN.
- LAN devices remain accessible and original UniFi LAN ACLs still apply.
- Fail-closed behavior on VPN client loss, gateway restart, firewall rebuild, WAN failover, IPv6 enabled, and DNS changes.
- No packet ever reaches ordinary WAN during controlled failure/recovery tests.
- Full installer preflight, safe rollback, persistent boot behavior, idempotent convergence, and thorough error reporting.
- Independent code review and supported firmware matrix.

No tests can prove all possible future firmware behavior. Any release must state its verified model/firmware combinations and residual risks.
