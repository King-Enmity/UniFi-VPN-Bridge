# Architecture — multi-protocol ingress, UniFi-managed egress

```text
Remote Teleport clients -- [UniFi Teleport server interface] ---+
Remote WireGuard peers - [UniFi WireGuard server interface] -+-- (future per-profile forwarding policy)
Remote OpenVPN clients - [UniFi OpenVPN server interface] ---+               |
                                                                  v
                                        UniFi-native PBR mark -> routing table
                                                                  |
                                               UniFi WireGuard/OpenVPN client
                                                                  |
                                                     External VPN provider
```

The system does not implement any VPN tunneling protocol; UniFi terminates incoming VPN connections and establishes outbound VPN clients. This project will be a *policy engine*, matching explicitly selected ingress traffic to explicitly selected outbound client tunnels.

## v0.2 behavior

- Accept 1–12 profiles: `--ingress TYPE:IFACE --egress OUT` for shared exit or `--route TYPE:IN:OUT` repeated for independent exits.
- Verify that each named source and destination interface exists in the gateway's local `ip -o link` listing. Never infer VPN type from `tun`, `tlprt`, or `wg` prefixes.
- Discover a possible unscoped IPv4 `from all fwmark MARK lookup TABLE` rule and require exactly one default route in that table, exiting via the selected outbound VPN interface.
- Ambiguous and absent mark candidates fail. A gateway-originated `ip route get` is output-path evidence only, never forwarded-path proof.
- Repeated egress targets are independently validated, and no policy is installed or stored.
- OpenVPN may use different/ephemeral server interfaces; inspect real hardware before specifying the source. Unsupported active-interface layouts must fail, not be guessed.

## Required before implementing apply

1. Collect sanitized real UniFi OS + Network version and network-state fixtures for Teleport, WireGuard server, OpenVPN server, and both client types.
2. Validate actual ingress device, source-address scope, conntrack and routing precedence separately for every server type.
3. Implement a *staged fail-closed guard first*; if the outbound tunnel/rule disappears, selected traffic must drop and must never fall back to WAN. Rule replacement must not create a forwarding gap.
4. Explicitly scope forwarding and any SNAT to configured ingress/egress pairs, with local-access exemptions that cannot accidentally bypass privacy intent.
5. Address IPv6 intentionally (route through a verified IPv6 VPN or block selected inbound IPv6) and gateway-originated DNS separately. Teleport clients often use the gateway as DNS.
6. Prove properties with packet capture on real hardware: normal path, tunnel loss, rule reload, VPN peer reconnect, service restart, and system reboot, with recoverability and rollback.
7. Ship mutation features opt-in, dry-run by default, with no downloaded executable dependencies and with exact change reports.

## Scope

This software should never be in the path of UniFi control-plane login, VPN handshake termination, router management SSH or ordinary LAN routing. Source identification is protocol-specific; the policy and verified guard can be shared. The current scanner is not an enforcement engine.