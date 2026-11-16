# Setup: the simplest tested VPN-to-VPN bridge

**This is a command-line walkthrough, not a one-click installer.** It assumes you can operate a shell on your own UniFi gateway and have safe recovery access. It was confirmed on one UDM Pro with **incoming WireGuard Server → outgoing UniFi OpenVPN Client**, not on every firmware, gateway, or VPN protocol.

## 0 — What you need

- A UniFi **WireGuard VPN Server** already created for remote access.
- A UniFi **VPN Client** connected to your commercial provider (the hardware-tested exit used OpenVPN).
- Root SSH access from your **home LAN** (do not depend on remote WireGuard to manage the router during setup).
- `bash`, `ip`, `iptables`, `ip6tables`, `systemctl`, `curl` or a way to transfer files; no `nano` required.
- A router backup and an off-device way to recover if routing fails.

The remote client must route internet IPv4 through its incoming WireGuard connection (`AllowedIPs = 0.0.0.0/0`). If you route only local LAN ranges from your phone, normal internet traffic never reaches the gateway and the bridge cannot redirect it.

**Do not install unreviewed development-branch experiments.** Follow the `main` files linked from the README.

## 1 — Locate the two VPN interfaces and the client subnet

In your router's SSH session, run these **read-only** commands:

```bash
ip -br -4 addr
ip -o link show
ip -4 rule show
ip -4 route show table all
iptables -V
systemctl --version | head -1
```

Find and write down these values *locally*, not in a GitHub issue:

| Config name | What to enter | How to identify it |
|---|---|---|
| `WG_IF` | Actual incoming **WireGuard server** interface | Match it to UniFi server and `ip -4 addr` |
| `WG_CIDR` | The **whole VPN-client IPv4 network with prefix** | E.g. convert your gateway's assigned address to its canonical network. Don't use a host IP |
| `VPN_IF` | Connected outbound **UniFi VPN client** interface | Match it to UniFi client and routing table |
| `LAN_EXEMPTIONS` | Space-separated destination networks that should stay local | Examine LAN/VLAN connected routes; use exact network CIDRs |
| `UVB_INTERVAL` | 15 seconds by default | How frequently the service checks its own hooks |

Find UniFi's existing `from all fwmark VALUE/MASK lookup TABLE` policy rule and confirm **its table has one default route through your selected `VPN_IF`**. The watchdog discovers the value dynamically. **Do not paste any example mark** or edit UniFi's managed rules.

You must configure the matching WireGuard *server* and provider VPN *client* yourself in the UniFi GUI before this stage. This project does not handle VPN authentication.

## 2 — Copy files from the repository onto the gateway

For straightforward CLI setup, connect to your router via SSH and run:

```bash
install -d -m 700 /data/unifi-vpn-bridge
cd /data/unifi-vpn-bridge

BASE="https://raw.githubusercontent.com/King-Enmity/UniFi-VPN-Bridge/main"
curl -fLsS "$BASE/scripts/bridge-watch.sh" -o bridge-watch.sh
curl -fLsS "$BASE/examples/bridge.env.example" -o bridge.env
curl -fLsS "$BASE/systemd/uvb-bridge.service" -o uvb-bridge.service

chmod 700 bridge-watch.sh
chmod 600 bridge.env
bash -n bridge-watch.sh
```

**Review downloaded files first** (`less`, `cat`, or `vi`). This only saves files; it does not run the watchdog. For reproducible installs, prefer a reviewed fixed commit SHA in `BASE` instead of the moving `main` branch. Never use `curl | bash`.

If your router has no `curl`, download the reviewed files on your computer and copy them with `scp`; no extra router packages are required.

## 3 — Fill in the configuration file (required)

The copy at `/data/unifi-vpn-bridge/bridge.env` starts with **invalid placeholders on purpose**. You must replace them with values from your own device.

Edit using `vi bridge.env` if you have `vi`. If you have no editor, use the following **template**; substitute every ALL-CAPS placeholder in your terminal *before* pasting:

```bash
cat > /data/unifi-vpn-bridge/bridge.env <<'EOF'
# Incoming WireGuard VPN SERVER interface:
WG_IF=YOUR_WIREGUARD_SERVER_INTERFACE
# Connected outgoing UniFi VPN CLIENT interface:
VPN_IF=YOUR_OUTBOUND_VPN_CLIENT_INTERFACE
# Full canonical IPv4 subnet allocated to remote WireGuard clients:
WG_CIDR=YOUR_CLIENT_NETWORK/PREFIX
# EXACT destination networks to preserve on local routing:
LAN_EXEMPTIONS="YOUR_LAN_NETWORK/PREFIX YOUR_OTHER_LOCAL_NETWORK/PREFIX"
# Number of seconds between rule checks:
UVB_INTERVAL=15
EOF

chmod 600 /data/unifi-vpn-bridge/bridge.env
```

Replace placeholders with real, canonical IPv4 CIDRs (the examples in the `cat` block **cannot run unchanged**). Most users can start with their LAN/VLAN networks, then expand the list only for other *intentionally local* destinations. Avoid blanket exemptions that unintentionally route private internet destinations via the home WAN.

The private file is executed as shell environment assignments only on your router; **never copy untrusted text into it** and never upload it to GitHub.

## 4 — Run read-only doctor first

```bash
set -a
. /data/unifi-vpn-bridge/bridge.env
set +a

bash /data/unifi-vpn-bridge/bridge-watch.sh doctor
```

`doctor` verifies basic inputs and detects the unique UniFi outbound VPN mark. It **does not** modify any firewall rule. Stop if it reports a missing or ambiguous mark. If you already have manually installed `UVB_NORD` rules from an older bridge test, keep `LAN_EXEMPTIONS` in the same order to allow recognition; don't blindly overwrite a working chain.

## 5 — Install the temporary firewall rules once

Take a UniFi configuration backup and keep your LAN SSH session open. This step **does** modify the active kernel firewall. It installs:

1. Scoped IPv4 forwarding guard: only the selected incoming WireGuard interface/client CIDR; `RETURN` for outbound VPN and bridged LAN interfaces, `REJECT` for other egress.
2. IPv6 forwarding REJECT scoped to the selected incoming WireGuard interface.
3. Scoped `MASQUERADE` for the WireGuard client CIDR leaving via the chosen commercial VPN interface.
4. Local-destination `RETURN` exceptions and internet `MARK` + `CONNMARK` using UniFi's currently detected outbound client mark.

```bash
bash /data/unifi-vpn-bridge/bridge-watch.sh once
```

Check all hooks:

```bash
iptables -t mangle -S PREROUTING | grep UVB_NORD
iptables -S FORWARD | grep UVB_KILLSWITCH
iptables -t nat -S POSTROUTING | grep MASQUERADE
ip6tables -S FORWARD | grep -- '-j REJECT'
```

**Only one** matching incoming WireGuard `UVB_NORD` hook and **one** `UVB_KILLSWITCH` hook should be present. Run `once` a second time and verify the counts remain the same; duplicate-hook behavior in early versions was corrected after actual testing.

**Real test:** connect a remote WireGuard device from a separate outside connection; verify new web HTTPS sessions exit through the commercial VPN's public IPv4, **not** your home WAN, and access to local LAN resources still works. Use packet captures on the router if you need a precise path verdict. A successful `ip route get` result alone is insufficient.

If anything fails, **do not enable systemd**. Inspect the rules and the [rollback notes](#stop-and-rollback).

## 6 — Make the verified rules persistent with systemd

Only after `once` and a remote client test succeed:

```bash
install -m 644 /data/unifi-vpn-bridge/uvb-bridge.service /etc/systemd/system/uvb-bridge.service
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/uvb-bridge.service
systemctl enable --now uvb-bridge.service
systemctl status uvb-bridge.service --no-pager
journalctl -u uvb-bridge.service -b -n 30 --no-pager
```

Look for `active (running)`. A single startup message is normal; the service is usually quiet on successful unchanged checks. It retries every `UVB_INTERVAL` seconds and may initially log `No unique UniFi fwmark` while the commercial VPN is still connecting. That is expected *if* a later `doctor` finds the mark and real client traffic works.

## 7 — Test restart safely

Before the first reboot, disconnect any remote full-tunnel VPN clients and keep a local router access path: **there can be a leak window before the watchdog starts.**

```bash
reboot
```

After reconnecting over local SSH:

```bash
systemctl is-enabled uvb-bridge.service
systemctl is-active uvb-bridge.service
journalctl -u uvb-bridge.service -b -n 40 --no-pager

iptables -t mangle -S PREROUTING | grep UVB_NORD
iptables -S FORWARD | grep UVB_KILLSWITCH
iptables -t nat -S POSTROUTING | grep MASQUERADE
ip6tables -S FORWARD | grep -- '-j REJECT'
```

The previously tested gateway rebooted with `enabled`, `active`, and restored project hooks. **Your gateway and firmware may behave differently.** Verify real remote web access, DNS, local LAN resources and VPN loss again after every UniFi upgrade.

## Stop and rollback

To **stop automatic reconciliation without deleting the last installed guard**, run:

```bash
systemctl disable --now uvb-bridge.service
```

This stops the service but deliberately **leaves existing firewall/NAT rules in place**. It is the safest first step if an unexpected problem occurs.

If you want to *fully remove* the bridge, disconnect all remote WireGuard clients first: removing the kill switch could allow their internet traffic to fall back to the ordinary WAN. Inspect exact hooks with `iptables -S` and remove **only the project-owned hooks and chain rules**, not UniFi-managed firewall tables. Example for your verified variables loaded in the shell:

```bash
# Review before executing these; the following require the same WG_IF,
# WG_CIDR, and VPN_IF that were used when adding the original rules.
iptables -w -t mangle -D PREROUTING -s "$WG_CIDR" -i "$WG_IF" -j UVB_NORD
iptables -w -D FORWARD -s "$WG_CIDR" -i "$WG_IF" -j UVB_KILLSWITCH
iptables -w -t nat -D POSTROUTING -s "$WG_CIDR" -o "$VPN_IF" -j MASQUERADE
ip6tables -w -D FORWARD -i "$WG_IF" -j REJECT
# Only after confirming neither chain is referenced:
iptables -w -t mangle -F UVB_NORD
iptables -w -t mangle -X UVB_NORD
iptables -w -F UVB_KILLSWITCH
iptables -w -X UVB_KILLSWITCH
```

**Caution:** If someone else created a matching rule, do not delete it; if any removal fails, stop and inspect rather than repeatedly flushing. Uninstalling custom firewall rules is not the same as restoring a complete UniFi configuration. For the simplest recovery when unsure, disable the watchdog and use your normal UniFi administrative/reboot recovery process.

## Not yet fixed by this release

Router-originated upstream DNS can still go out through the home WAN when remote clients use the router as DNS. The IPv4 kill switch works on FORWARD, not OUTPUT. IPv6 clients may also bypass the IPv4-only remote tunnel through their own local network. Stronger DNS isolation, reliable early-boot blocking, firmware-update recovery and multi-protocol support belong to the [roadmap](../ROADMAP.md), not the working release.

If your DNS uses internal names, local resolver policy matters. Avoid blindly switching to a public resolver if it resolves your internal hostnames to your public WAN address.

**Privacy:** share only redacted command output. Do not publish local configuration, public IPs, endpoint addresses, keys or credentials.
