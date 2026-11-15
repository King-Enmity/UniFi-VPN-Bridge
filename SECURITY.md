# Security model

UniFi VPN Bridge targets highly privileged UniFi gateways. A routing bug can leak public IPs, DNS, IPv6 traffic or interrupt admin access. **This starter is not an independently audited or operational VPN privacy solution.**

## v0.2 (read-only) guarantees by design

- No firewall or routing mutations: no `iptables`, `ip6tables`, `nft`, `ip rule add`, `ip route replace`, NAT, systemd or boot-hook actions.
- No installation, telemetry, autoupdate, external software downloads, key/certificate reads or remote network connections from the diagnostic code.
- All supplied `TYPE` strings must be from a three-item allowlist. Interface names must use a strict <=15-character allowlist and route-table names/marks are checked before being given to a read-only `ip` command.
- No shell-based configuration, `eval`, Bash `source` of another file, or execution of text read from policy output.
- Reports ambiguity rather than guessing the mark; a matched policy mark does NOT establish a protected forwarded path.
- The provided tests use a stubbed `ip` program; test success is not an operational routing claim.

## Remaining risks

- Firmware-dependent forwarding paths may not follow the displayed gateway OUTPUT-path route.
- A VPN gateway may send DNS requests via its ordinary WAN when responding for incoming VPN clients.
- IPv6 is neither configured nor guarded by this diagnostic.
- Route table data and interface state can change while being read (time-of-check/time-of-use).
- OpenVPN server ingress may be represented differently across firmware versions or per-client sessions.
- Anyone with shell access on the gateway can modify environment `PATH` or executables; a compromised device lies outside this threat model.
- `ip -o link show` and routing diagnostic output may contain private addressing. Review and redact before sharing.

## Minimum gate for future `apply`

No production traffic mutation until verified inbound and outbound forwarding for each protocol on supported hardware; guard-first, atomic replacement, explicit IPv6 and DNS policies, failure-state packet tests, independent test environments and rollback. Privileged installation must require a human confirmation and an auditable diff. No `curl | bash` or unpinned dependencies.

Disclose security issues privately without posting tunnel credentials, SSH keys, client configurations or identifiable public IP addresses.