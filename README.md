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


## Hardware-observed fwmark bridge (development field notes)

A UDM Pro field test confirmed that a remote WireGuard server client can reach the internet through an existing UniFi-managed outbound OpenVPN VPN client by marking inbound IPv4 packets with **UniFi's own outbound VPN fwmark**, with narrowly scoped source NAT. A same-connection packet capture verified return traffic through both tunnels. An unmarked connection previously exited the normal WAN even though a separate-table route lookup appeared correct.

Read the **[sanitized manual proof-of-concept and rollback guide](docs/VERIFIED_FWMARK_WIREGUARD_POC.md)**. This records the method as a **manual, temporary, development-only experiment**; it includes no personal WAN, LAN, peer, or VPN endpoint addresses or credentials. It does **not** establish a complete kill switch, DNS/IPv6 protection, automatic recovery, or reboot persistence.

**Do not confuse this field-tested method with the older unvalidated `bin/bridge-engine.py` prototype**: the prototype's existing early source-policy fallback may take precedence over UniFi's VPN mark policy on some devices. Do not run it on a working production gateway.

## Experimental persistence watchdog (development ONLY)

A **new, not yet hardware-tested** [fwmark watchdog](scripts/bridge-watch.sh), [local configuration template](examples/bridge.env.example), and [systemd unit](systemd/uvb-bridge.service) are available with the [installation, validation and rollback guide](docs/PERSISTENCE_WATCHDOG_DEV.md). The service is designed to reconcile the previously tested WireGuard→UniFi VPN-client firewall mark, scoped source NAT, IPv4 forwarding guard and IPv6 forwarded-traffic block after startup or configuration reload, without editing UniFi's own routing tables.

**Do not treat this as a verified leak-proof or reboot-tested installation.** Router-originated upstream DNS, brief exposure windows during boot/firewall rebuilds, firmware-upgrade persistence, and VPN-failure behavior remain to be validated. Keep live gateway-specific values only in the root-owned local config under `/data`, never in public GitHub files. Existing experimental `bin/bridge-engine.py` is a distinct, unvalidated prototype and is not used by this watchdog.

## Experimental routing implementation (development ONLY)

**NEW v0.3 proof-of-concept:** `bin/bridge-engine.py` provides an experimental IPv4 VPN-to-VPN routing and DNS policy engine, with explicit LAN exceptions, a forwarding drop guard, a kernel source-route fallback, staged A/B firewall chains, and optional watchdog/systemd boot recovery.

- **Read the [experimental engine safety notes](docs/EXPERIMENTAL_ENGINE.md) first.** This code has not been validated on physical UniFi hardware and may interrupt routing or cause traffic leaks during firewall reloads.
- **Review [example JSON configuration](examples/config.experimental.json)**: sample subnets, devices and DNS servers are illustrative, not install-ready.
- Only an explicitly marked `--experimental` invocation can change firewall or service state. Do **not** run `apply`, `watch` or `install-service` on a production router.
- `main` and `coming-soon` do **not** contain this experimental implementation. They remain read-only.

**Not yet solved:** device/firmware compatibility, independent packet-level verification, encrypted DNS behavior, genuinely atomic UniFi firewall reload handling, guaranteed reboot persistence, automatic rollback and safe production installation.

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