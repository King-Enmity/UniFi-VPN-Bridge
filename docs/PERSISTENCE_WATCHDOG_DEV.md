# Experimental persistence: WireGuard server → UniFi-managed VPN client

> **Development only.** This watchdog is newly authored and has passed shell syntax checks, **not live UDM Pro reboot, firewall-reload, NordVPN reconnect, or privacy tests**. The previous *manual* `UVB_NORD` + `UVB_KILLSWITCH` fwmark/NAT/guard workflow has been packet-capture verified on one device. **Do not claim leak protection from this script without hardware testing.** Maintain console/LAN access and a rollback plan.

## What it does

- Leaves UniFi-owned policy rules, default routes, VLANs, firewall chains and VPN-client configuration untouched.
- Installs and reconciles **only scoped** IPv4 forwarding hooks for the selected incoming WireGuard interface/source subnet. Reuses the manually tested `UVB_NORD` and `UVB_KILLSWITCH` chains if their structures match; refuses to rewrite unfamiliar contents.
- Discovers exactly one unscoped UniFi IPv4 `from all fwmark VALUE/MASK lookup TABLE` rule whose table default route exits the configured outbound VPN interface. A changed mark/mask is refreshed in the project-owned chain.
- Uses the existing five local-exemption destination ranges, source-scoped NAT to the outbound VPN, a forward guard allowing VPN or bridge egress to proceed to UniFi ACLs, and a WireGuard-only IPv6 forward reject.
- Runs every 15 seconds by default. Restores missing hooks following some UniFi rule reloads. If no unique UniFi VPN mark is found, **leaves installed guards** and does not choose another exit.

**What it does not guarantee:** zero leaks during firmware boot or firewall replacement windows; preservation across every firmware update; DNS privacy when a remote client uses the router as its DNS forwarder; encrypted DNS control; non-WireGuard ingress; dynamic renaming of the outbound VPN interface; or that additional local VPN interfaces work as LAN exemptions. Interface-name wildcards `br+` are not the same as explicit destination/subnet authorization. Existing UniFi firewall ACLs still decide whether LAN access is allowed.

## Install on your own gateway

Do not publish your real interface/subnet/WAN information. Keep the configuration in `/data/unifi-vpn-bridge/bridge.env` **only on your gateway**, owned by root with permission `0600`.

**Preparation:** With a working manual bridge and a separate local LAN or console session, confirm the gateway has `bash`, `ip`, `iptables`, `ip6tables` and systemd, and that `/data` is writable and retained across a normal reboot. Document the existing rules and maintain a recent UniFi backup. The service unit uses native systemd and might have to be reinstalled after firmware updates.

1. Download **reviewed/pinned** copies of [the watchdog](../scripts/bridge-watch.sh), [unit](../systemd/uvb-bridge.service), and [environment template](../examples/bridge.env.example) into a local staging location; inspect before installing. Do **not** use `curl | bash`. Inspect the script in the repo, compare checksums, and test in a controlled environment.
2. Create `/data/unifi-vpn-bridge/`, place the watchdog at `/data/unifi-vpn-bridge/bridge-watch.sh`, and run `bash -n` on it.
3. Copy `examples/bridge.env.example` to `/data/unifi-vpn-bridge/bridge.env`; **replace** each placeholder with the interfaces and network **on your gateway**. The source CIDR must be the **canonical network** (not the gateway host address). Review local destination exemptions. Do not enter secrets.
4. `chmod 600 /data/unifi-vpn-bridge/bridge.env && chmod 700 /data/unifi-vpn-bridge/bridge-watch.sh`. Make both files root-owned.
5. Place the unit at `/etc/systemd/system/uvb-bridge.service` and review its `EnvironmentFile` and `ExecStart` paths. Run `systemctl daemon-reload`, `systemctl enable --now uvb-bridge.service`.
6. Run `systemctl status uvb-bridge.service --no-pager`, `journalctl -u uvb-bridge.service -n 40 --no-pager` and inspect `iptables -t mangle -S UVB_NORD`, `iptables -S UVB_KILLSWITCH`, `iptables -t nat -S POSTROUTING`, `ip6tables -S FORWARD`.
7. On an **external client** verify fresh HTTPS traffic actually enters the WireGuard server and exits the outbound VPN, source NAT and return path, public IPv4 exit, private LAN reachability, and absence of equivalent HTTPS flow exiting ordinary WAN. Check DNS separately. With LAN admin access, simulate outbound VPN disconnect/reconnect and verify fail-closed internet behavior, local resources, and rule recovery. Also test the actual service after a reboot. Do **not** assume success from `systemctl active` alone.

### Example installation commands (run on UDM Pro, paths need existing staged files)

```bash
install -d -m 700 /data/unifi-vpn-bridge
install -m 700 ./bridge-watch.sh /data/unifi-vpn-bridge/bridge-watch.sh
install -m 600 ./bridge.env.example /data/unifi-vpn-bridge/bridge.env
# Edit /data/unifi-vpn-bridge/bridge.env locally before starting.
install -m 644 ./uvb-bridge.service /etc/systemd/system/uvb-bridge.service
bash -n /data/unifi-vpn-bridge/bridge-watch.sh
systemctl daemon-reload
systemctl enable --now uvb-bridge.service
journalctl -u uvb-bridge.service -n 40 --no-pager
```

**Important:** The template contains placeholders and **will not run** until properly edited. Avoid exposing the true contents of `bridge.env` in public issue reports.

### Test routine after a normal reboot

```bash
systemctl is-enabled uvb-bridge.service
systemctl is-active uvb-bridge.service
journalctl -u uvb-bridge.service -n 40 --no-pager
iptables -t mangle -S UVB_NORD
iptables -S UVB_KILLSWITCH
iptables -t nat -S POSTROUTING
ip6tables -S FORWARD
```

Recheck a real remote test connection and the public IPv4 exit. During boot, before custom services come up, **there may be a WAN exposure window**. Disconnect remote full-tunnel clients during the first reboot test and do not describe this as an always-on, boot-time privacy guarantee.

### Stop and rollback safely

`systemctl disable --now uvb-bridge.service` **stops reconciliation but intentionally leaves the last installed rules in place**, including the IPv4 guard. This prevents an automatic drop of the firewall protection during service maintenance. It is **not** a full uninstall.

Before clearing firewall rules, disconnect remote clients. Inspect the rules and remove only project-owned exact jump rules, chains, and NAT additions, never UniFi-managed chains. Where a manual rule was already present before installing this watchdog, it is not possible to infer ownership from a counter alone; document the baseline before cleanup. If uncertain, restore the system to a known-good configuration through normal UniFi maintenance rather than blindly flushing any firewall table.

### Firmware updates and startup helpers

The systemd unit lives under `/etc/systemd/system`, whereas project script/config live under `/data`. A normal reboot generally preserves an enabled systemd unit on UniFi OS 4.x/5.x, but UniFi firmware upgrades may replace or disable custom units. Verify after **every firmware update**. An optional third-party on-boot helper such as `unifi-utilities/unifi-common` can restore units from `/data/on_boot.d`, but that requires separately reviewing and installing trusted third-party code. This project does **not** silently download or install such a helper.

This implementation remains **development**, not `coming-soon` or `main`, until all of the disconnect/reconnect, DNS, IPv6, failover, firewall-reprovision and upgrade checks are recorded.

## 2026-11-16 field test: duplicate hook regression and fix

The first `once` test on a UDM Pro completed, and confirmed the existing scoped NAT and IPv6 forward reject. However, it also revealed **duplicate** `mangle/PREROUTING → UVB_NORD` and `filter/FORWARD → UVB_KILLSWITCH` jump rules. The watchdog's `ensure_hook_first` compared argument strings in `-i IFACE -s CIDR` order while `iptables -S` prints `-s CIDR -i IFACE`. It therefore added a new rule without recognizing the existing first rule.

The watchdog now supplies its hook matcher with the canonical printed order. **Do not enable the looping service with earlier revisions.** Test `doctor`, then `once` twice and verify that the matching hook count remains exactly **one** for each chain. Existing duplicate exact hooks should be removed in a guarded first reconciliation. Verify no unrelated UniFi chains have been modified. The revised watchdog still requires real reboot, reconnect and privacy tests.
