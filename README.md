# UniFi VPN Bridge

**Remote access to your LAN, internet browsing through your commercial VPN.**

UniFi can host a WireGuard VPN server and connect to a commercial VPN, but routing **remote VPN server clients into an outbound VPN client** does not automatically work through ordinary VPN-client policy routing on the tested UDM Pro. **UniFi VPN Bridge fills that forwarding gap** using UniFi's existing `fwmark` route instead of replacing UniFi's default routes.

```text
Remote phone/laptop
       │ full-tunnel IPv4 WireGuard connection
       ▼
UniFi WireGuard SERVER on your gateway
       ├── local LAN destinations ──► your normal local routes and UniFi ACLs
       └── internet destinations ───► UniFi VPN CLIENT ──► commercial VPN provider
                                         (tested with outbound OpenVPN)
```

## Start here

**[Manual command-line setup guide →](docs/SETUP.md)**

The guide explains what you must fill in, how to install from SSH (including on gateways without `nano`), how to test before starting a service, how to verify after reboot, and how to back out safely.

- [Explained watchdog script](scripts/bridge-watch.sh): uses the current UniFi-owned outgoing VPN policy mark; sets scoped IPv4 forwarding, NAT, an IPv4 forwarding kill switch, and an incoming-WireGuard IPv6 forwarding guard.
- [Configuration template](examples/bridge.env.example): contains **only placeholders**, never IPs, hostnames, or keys from a real installation.
- [Systemd service](systemd/uvb-bridge.service): runs the watchdog on boot and periodically checks for missing/reordered project rules.
- [How the routing works](docs/HOW_IT_WORKS.md) and [known limitations](SECURITY.md).
- [Future roadmap](ROADMAP.md).
- Existing [read-only diagnostic CLI](bin/unifi-vpn-bridge) is optional; it is **not** an installer.

## Tested today — scope matters

On **one UDM Pro** with incoming UniFi **WireGuard Server** and outgoing UniFi **OpenVPN Client** to a commercial VPN, field testing confirmed:

| Feature | Result |
|---|---|
| Forwarding a remote WireGuard client's IPv4 HTTPS traffic through the outbound VPN | Confirmed with real packet captures and replies |
| Scoped outbound VPN MASQUERADE | Confirmed |
| LAN resource access while the forwarding guard is on | Confirmed |
| Rejecting non-approved forwarded IPv4 paths using a source/interface-scoped guard | Confirmed in the observed test |
| Discovering the current UniFi outbound `fwmark` without hardcoding it | Confirmed |
| Repeated reconciliation without accumulating duplicate hooks | Confirmed (the original duplicate-hook bug was fixed) |
| Service starting after an ordinary router reboot and restoring firewall hooks | Confirmed |
| Full end-to-end leak-free operation during *all* failures | **Not established** |

**Important:** This is the simplest **tested** workflow for this particular combination, **not** a general-purpose or zero-leak-guaranteed VPN router. The restored service is only as reliable as the local UniFi OS environment; firmware updates may affect custom services.

## Before you install

You need a UniFi gateway with root SSH access and `bash`, `ip`, `iptables`, `ip6tables`, and `systemd`; an already configured UniFi incoming WireGuard server; an already connected UniFi outbound VPN client with an identifiable `fwmark` route; and local/admin access to recover your router if something goes wrong.

Configure your remote WireGuard device as a **full-tunnel IPv4** client for web browsing (`AllowedIPs = 0.0.0.0/0`). Local split-tunnel browser traffic never reaches this bridge.

The script supports operator-supplied interfaces, not auto-detection of your VPN server, and targets **one WireGuard server subnet and one outbound VPN client** per installation. The code does not create VPN accounts, modify UniFi-managed policy tables, or ask for VPN credentials.

## Privacy and safety limitations

- **Router DNS:** If a remote WireGuard client uses the router for DNS, the router's own upstream queries might still exit via the WAN. The forwarding kill switch does **not** cover router-originated DNS. DNS leak protection and split DNS are roadmap items.
- **Boot gap:** Before systemd starts the watchdog or during UniFi firewall reprovisioning there can be an interval without custom protections. Do not claim uninterrupted or zero-leak enforcement.
- **IPv6:** The script rejects forwarded IPv6 arriving on the selected WireGuard interface. It cannot prevent a remote client from using its separate local IPv6 connection.
- **Allow rules:** `RETURN` to the outbound VPN or local bridge means continue processing UniFi firewall rules; the script does not grant blanket LAN access. `br+` matches bridge interface names, so administrators must review their actual topology.
- **Other traffic:** WAN failover, hardware offload, tunnel-down conditions, changed UniFi versions, multiple VPNs, incoming Teleport/OpenVPN, and outbound WireGuard clients **have not received the same complete field validation**.

Keep local configuration under `/data/unifi-vpn-bridge/bridge.env` with permissions `0600`. **Never commit actual local addresses, endpoints, secrets or diagnostic dumps to GitHub.**

## Release channels

| Branch | Meaning |
|---|---|
| [main](../../tree/main) | Minimal, documented hardware-observed WireGuard-to-OpenVPN-client method; explicit safety limits |
| [coming-soon](../../tree/coming-soon) | Preview work, not automatically promoted |
| [development](../../tree/development) | Experimental implementations and unverified features; not part of this release |

See [BRANCHES.md](BRANCHES.md). **Future features are plans, not advertised as working.**

## License

MIT. Independent community project; not affiliated with or endorsed by Ubiquiti or VPN providers.
