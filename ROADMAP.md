# Roadmap — what's next for UniFi VPN Bridge

The goal is to make VPN-server → commercial-VPN-client routing easy while keeping normal LAN access. **Nothing here is a promise of availability or a claim of current support.** The main branch is intentionally small and limited to the observed WireGuard server → outbound UniFi OpenVPN client workflow.

## Current, observed functionality

- Remote WireGuard IPv4 client traffic forwarded through an already-connected UniFi outbound OpenVPN VPN client.
- Native LAN routing and existing UniFi LAN ACLs left intact for configured local destinations.
- Source-scoped NAT, IPv4 forwarding guard, and scoped IPv6 forwarding REJECT.
- Dynamic detection of the UniFi-managed VPN routing mark.
- Idempotent reconciliation and working watchdog startup after a normal UDM Pro reboot.

**Security limits remain**: no verified protection for router-originated DNS, early boot, all firewall reloads, alternate WAN interfaces, hardware offloading, every VPN disconnect scenario, or client-side IPv6.

## Possible additions

| Priority | Proposed feature | Why |
|---|---|---|
| Next | **DNS leak protection and split DNS** | Keep public DNS queries inside the commercial VPN while resolving internal hostnames locally |
| Next | **Stronger fail-closed boot and reload handling** | Minimize or eliminate unprotected windows before the watchdog reattaches |
| Next | **Outage/reconnect and WAN-failover validation** | Confirm behavior when UniFi regenerates VPN policy marks or changes interfaces |
| Next | **Safe uninstall and rollback** | Undo only project-owned changes with clear audits, without risking unrelated UniFi rules |
| Later | **Incoming Teleport support** | Apply the same concept to a different UniFi VPN server ingress path after packet tests |
| Later | **Incoming OpenVPN Server support** | Map OpenVPN server clients to outgoing commercial VPN paths |
| Later | **Outgoing WireGuard VPN clients** | Validate provider tunnels using WireGuard rather than OpenVPN |
| Later | **Multiple incoming profiles and exits** | Support multiple remote client groups and independent egress routing policies |
| Later | **Firmware-update resilience** | Safely reinstall custom startup services when UniFi OS upgrades |
| Later | **CLI setup wizard / optional installer** | Reduce manual setup while making actions reviewable and opt-in |
| Later | **Per-client/per-network exceptions** | Fine-grained LAN access and provider selection without bypassing UniFi ACLs |
| Later | **Hardware/firmware test matrix and automatic diagnostics** | Make compatibility explicit and easier to troubleshoot |

## Promotion rules

- New features start in `development` and can move through `coming-soon`.
- They only reach `main` when there is independent, reproducible verification for the declared capability.
- Security-sensitive claims require packet tests, tunnel loss/recovery tests, and honest documentation of remaining gaps.
- Never include IP addresses, interface values, hostnames, DNS logs, VPN configurations or credentials from a contributor's actual router in source files.

Contributions and test reports are welcome, provided personal network details are redacted.
