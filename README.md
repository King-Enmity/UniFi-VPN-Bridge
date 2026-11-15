# UniFi VPN Bridge

> **Access your home network remotely. Browse through your commercial VPN.**
>
> Fixing a VPN-routing limitation that UniFi users still need addressed: remote Teleport, WireGuard, and OpenVPN users should be able to access local resources while their internet traffic exits through a commercial VPN such as NordVPN, Proton VPN, or Mullvad.
>
> **Current release scope:** read-only routing diagnostics only. No live VPN bridging or kill switch is implemented yet.

### Release channels

| Branch | Meaning |
|---|---|
| [main](../../tree/main) | Stable, reviewed functionality (currently diagnostics only) |
| [coming-soon](../../tree/coming-soon) | Working changes that still need more testing |
| [development](../../tree/development) | Active builds and experiments; may break |

Promote changes **development → coming-soon → main** after appropriate testing. See [BRANCHES.md](BRANCHES.md).


**v0.2.0: read-only three-protocol discovery. Not yet a VPN router, leak guard, or installer.**

An independent, security-first UniFi routing project. It is designed to eventually steer traffic from **Teleport**, **WireGuard VPN Server**, and **OpenVPN VPN Server** through one or more UniFi-managed outbound **WireGuard VPN Clients** or **OpenVPN VPN Clients**.

v0.2 has a CLI for *declaring* one or several ingress profiles and discovering existing UniFi-managed IPv4 fwmark policy rules for the selected outbound VPN interface(s). It cannot yet steer, NAT, forward, protect or block any packets. Nothing it prints is proof of leak protection. **No untrusted original-project code is bundled.**

## What is supported now

- Incoming VPN types: `teleport`, `wireguard`, `openvpn` (explicit type + existing network interface).
- Outgoing VPN: any explicitly chosen existing UniFi-managed WireGuard or OpenVPN **client** interface with a uniquely matching unscoped IPv4 fwmark rule and a single default route to that interface.
- Multiple incoming VPN profiles may share one outgoing VPN or use independent outgoing VPNs.
- Validates inputs, confirms interface existence, identifies ambiguous candidate marks and refuses to guess.
- `doctor` and `plan` are **read only**. The latter prints the proposed engineering stages, not shell mutation commands.
- Does **not** read VPN keys, credentials or VPN config files, talk to remote hosts, download software, write firewall rules, or install a service.

**Not yet implemented:** actually routing VPN clients, source NAT, kill switch, DNS control, IPv6 policy, live tunnel verification, boot persistence, interface auto-discovery, hardware compatibility testing.


## Guided setup (development preview)

**Start here:** [Step-by-step getting started guide](docs/GETTING_STARTED.md).

There are two supported workflows for the current **read-only diagnostics**:

- Manual: inspect VPN interfaces on the gateway and run the `doctor` CLI yourself.
- Optional wizard: run `bash scripts/setup-wizard.sh` from your own computer. It connects over SSH, lists interface names, asks which incoming VPN server should use which outbound VPN client, and runs the existing read-only diagnostic. Use `--help` for non-interactive mode.

**Important:** The wizard does *not* configure VPN-to-VPN forwarding, install firewall rules, provide a kill switch, or protect internet traffic. Automatic live setup is a future feature that requires real hardware validation before release. This wizard is on `development` only, not the stable `main` branch.

## Examples

Run from the repository directory on a laptop. SSH authenticates to your gateway; the script itself has no outbound network calls and is streamed to Bash without being installed. Replace `192.168.1.1` and ALL interface names with those verified on your device.

First inspect available interfaces on the gateway:

```sh
ssh root@192.168.1.1 'ip -o link show'
```

### All three incoming VPNs, one outbound OpenVPN client

```sh
ssh root@192.168.1.1 \
 'bash -s -- doctor --ingress teleport:tlprt0 --ingress wireguard:wgsrv1 --ingress openvpn:tun0 --egress tunovpnc1' \
 < bin/unifi-vpn-bridge
```

### Three incoming VPNs, different outgoing clients

```sh
ssh root@192.168.1.1 \
 'bash -s -- doctor --route teleport:tlprt0:tunovpnc1 --route wireguard:wgsrv1:wgclt4 --route openvpn:tun0:wgclt4' \
 < bin/unifi-vpn-bridge
```

Here `tun0`, `tlprt0`, `wgsrv1`, `tunovpnc1`, and `wgclt4` are **illustrative**, not guaranteed interface names. Actual names, especially for incoming OpenVPN, depend on gateway and firmware; the scanner will reject missing interfaces. `--route` accepts one incoming server profile and one outbound client interface per option. For a proposed (non-executed) engineering plan, replace `doctor` with `plan`.

Backward-compatible v0.1 syntax:

```sh
ssh root@192.168.1.1 'bash -s -- doctor --source tlprt0 --egress wgclt4' < bin/unifi-vpn-bridge
```

## How to test offline

```sh
bash -n bin/unifi-vpn-bridge
python3 -m unittest discover -s tests -v
```

All test gateway calls use stubbed `ip` commands in a temporary folder. The test suite itself makes no firewall changes. None of these tests demonstrates real packet routing or prevents leaks.

## Security

This is strictly an inspection tool. The only runtime external executable needed is `ip` (plus `awk` and standard shell utilities). Inputs and route-table identifiers are validated; there is no `source`, `eval`, `curl | bash`, telemetry, external dependency installer, persistence, or automatic update. See [SECURITY.md](SECURITY.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

A safe future mutation engine will need validated firmware-specific firewall precedence, ingress source mapping, A/B staged rule swaps, an already-installed fail-closed guard, constrained SNAT, explicit IPv6 and DNS decisions, packet-level disconnect tests and rollback before any production release.

## Official UniFi references

- [Teleport VPN](https://help.ui.com/hc/en-us/articles/5246403561495-UniFi-Gateway-Teleport-VPN)
- [WireGuard VPN Server](https://help.ui.com/hc/en-us/articles/115005445768-UniFi-Gateway-WireGuard-VPN-Server)
- [OpenVPN Server](https://help.ui.com/hc/en-us/articles/12600064355991-UniFi-Gateway-OpenVPN-Server)
- [WireGuard VPN Client](https://help.ui.com/hc/en-us/articles/16357883221015-UniFi-Gateway-WireGuard-VPN-Client)
- [OpenVPN Client](https://help.ui.com/hc/en-us/articles/12648654915863-UniFi-Gateway-OpenVPN-Client)

## License

MIT. Independent community project, not endorsed by or affiliated with Ubiquiti.