# Architecture: minimal VPN-to-VPN forwarding

This is **not** a new VPN daemon. UniFi continues managing the remote WireGuard server and outbound commercial VPN client.

```text
Remote WireGuard peer
   └── incoming UniFi WireGuard server (WG_IF / WG_CIDR)
        ├── specified LAN destinations → native UniFi LAN routing and firewall rules
        └── internet IPv4 destinations
             ├── scoped mangle MARK / CONNMARK
             ├── existing UniFi outgoing VPN client's routing mark + table
             ├── scoped MASQUERADE (VPN_IF)
             └── commercial VPN provider
```

**Kill switch:** a project-owned filter/FORWARD chain restricts the selected incoming WireGuard clients' IPv4 egress to the chosen VPN client or local bridge interfaces. Its RETURN rules preserve UniFi's normal ACL checks, not unconditional permission. A project-owned IPv6 FORWARD reject blocks that WireGuard ingress interface's forwarded IPv6 packets.

**Watchdog:** the same Bash script repeatedly discovers UniFi's existing VPN client fwmark and reconciles project-owned hooks. If the provider policy is not yet available during boot, it leaves the forwarding guard in place and retries. A local systemd unit starts it automatically after ordinary reboot on the tested gateway.

**Scope:** single incoming WireGuard server client subnet, single already connected outgoing UniFi VPN client; verified on UDM Pro with outbound OpenVPN. It does not edit UniFi's `ip rule` priorities, add alternative default routes, create VPN credentials, or automatically identify your interface names.

**Risk:** filter/FORWARD doesn't cover router-originated upstream DNS or necessarily early boot/firewall reload gaps. See [SECURITY.md](SECURITY.md), [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md), [docs/SETUP.md](docs/SETUP.md), and [ROADMAP.md](ROADMAP.md).
