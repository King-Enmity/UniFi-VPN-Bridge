# Security scope and limitations

**Privileged router modifications deserve caution.** UniFi VPN Bridge manages `iptables`, `ip6tables`, and a systemd watchdog on a UniFi gateway. A bad rule can interrupt remote access or reveal your ISP WAN address. The main branch contains the simplest hardware-observed IPv4 bridge method, **not an independently audited or fully leak-proof network privacy solution**.

## What was actually observed on a UDM Pro

- Incoming WireGuard server client traffic sent through a UniFi-managed outbound OpenVPN client after adding the exact outbound VPN's existing fwmark.
- Scoped NAT and a source/interface-scoped IPv4 forwarding guard worked in the test.
- LAN resources remained accessible.
- The watchdog's duplicate-hook bug was discovered and corrected; repeated one-time reconciliation preserved one hook per project chain.
- A normal router reboot restored an enabled/active systemd service and the corresponding project firewall hooks.

These observations do not establish compatibility with every UniFi hardware/firmware combination.

## Remaining risks

1. **Router DNS:** If WireGuard peers point to the UDM Pro as DNS, router-originated upstream DNS can leave via normal WAN. FORWARD-only marking/guarding does not automatically apply to router-generated OUTPUT packets. This remains a high-priority roadmap feature.
2. **Early boot and firewall reload gaps:** The systemd service may start after UniFi networking is already active. Even a 15-second watchdog cannot guarantee continuous fail-closed policy during early boot or rule replacement.
3. **IPv6 outside the tunnel:** The ingress interface's IPv6 forwarding rule does not control a remote phone's separate local IPv6 route.
4. **Multiple WANs, alternate egress, offloading:** The code and one UDM Pro field test do not establish complete safety for every alternate path or hardware acceleration behavior.
5. **VPN disconnect/reconnect:** An absent UniFi mark leaves the guard intact, but not every outage/rule-change scenario has been tested with independent WAN packet captures.
6. **Firewall order and firmware changes:** UniFi may reorder or replace rules; persistence across every firmware upgrade and daemon restart remains unverified.
7. **Local exceptions:** The `br+` bridge interface allowance is topology-dependent. Do not use uncontrolled local-destination exemptions.
8. **Unsupported ingress protocols:** Teleport and incoming OpenVPN server forwarding must be investigated separately.
9. **Service configuration:** `bridge.env` is sourced in operator shells and loaded by systemd. Keep it root-owned, restricted to `0600`, containing only assignments you wrote and reviewed. Never execute downloaded text without reviewing it first.

## Operator safeguards

- Have LAN/admin recovery access and a router backup before installing.
- Configure the remote WireGuard client for IPv4 full-tunnel access if its internet should traverse the bridge.
- Verify the exact UniFi policy mark, interface names, local CIDRs and source subnet on your own gateway.
- First run read-only `doctor`; then `once`; only start the systemd service after observing real packet routing and LAN access.
- Disconnect remote clients during reboot testing: there may be an unprotected boot interval.
- Disable the systemd service before rollback, retain the forwarding guard until remote clients are disconnected, and **never flush UniFi-managed chains**.
- Never post SSH keys, VPN profiles, public IPs, internal IP addresses, router hostnames, endpoint addresses, or unredacted packet traces to GitHub.

## Disclosure and development

Report security concerns privately when possible. The roadmap explicitly lists DNS, early-boot policy, failover, hardware-offload and firmware validation as unfinished. No telemetry, secret collection, downloaded execution or automatic software updates are required by the bridge.
