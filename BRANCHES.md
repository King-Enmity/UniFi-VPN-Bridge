# Release channels

We keep three branches to separate what has actually been tested from experiments.

| Branch | Purpose | What to expect |
|---|---|---|
| **main** | Smallest tested working path | Incoming UniFi WireGuard Server → UniFi outbound OpenVPN VPN Client using its existing mark, scoped NAT and forwarding guard, plus watchdog/reboot recovery tested on one UDM Pro |
| **coming-soon** | Preview | Features that may work but need additional verification; do not depend on them for privacy |
| **development** | Active experiments | Incomplete engines, exploratory integrations, prototyping, and potentially disruptive changes |

A **working example on one router is not a guarantee** across all UniFi OS versions, firmware reloads, VPN types, DNS setups, or failure scenarios. Read [SECURITY.md](SECURITY.md) before treating main as suitable for your environment.

## Release process

1. Propose code and documentation in `development`.
2. Review and test in `coming-soon` where appropriate.
3. Promote to `main` only the smallest feature set supported by real testing, with explicit known limitations.
4. Preserve the simple manual command-line walkthrough and a reversible method.
5. Keep private router IPs, hostnames, WAN endpoints, provider credentials, SSH keys and unredacted logs **out of all branches**.

## Main's actual scope

- Tested: remote WireGuard IPv4 clients forwarded through an already connected UniFi OpenVPN client on one UDM Pro.
- Observed: scoped NAT, LAN access, IPv4 forwarding kill switch behavior, IPv6 ingress-forward guard, automatic firewall mark discovery, idempotent watchdog, normal reboot service recovery.
- **Not proven:** complete router-originated DNS protection, leak-free early boot, every VPN outage, WAN failover, all hardware offload paths, all firmware, Teleport/OpenVPN incoming servers, outgoing WireGuard clients.

See [ROADMAP.md](ROADMAP.md) for ideas that are **not** currently shipped.

## Suggested branch protections

Configure GitHub Rulesets to require reviews and CI checks before merging into `main`, disallow force pushes, and review changes touching privileged firewall scripts.
