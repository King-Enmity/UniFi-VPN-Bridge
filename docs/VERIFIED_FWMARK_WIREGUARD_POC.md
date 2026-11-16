# Field-tested WireGuard server → UniFi VPN client via fwmark

> **Development-only field notes — NOT a completed privacy/killswitch solution.** A UDM Pro test established that marking inbound WireGuard packets with the *existing UniFi-managed outbound VPN client's fwmark* can steer real HTTPS traffic into an outbound OpenVPN tunnel. DNS, IPv6, disconnect/failover behavior, reboot persistence, and broader firmware compatibility remain unverified. The procedure below modifies live firewall rules. Do not run without local administrative access and a recovery plan.

## What was actually verified

On one UDM Pro with a UniFi WireGuard **server** and an already-connected outbound commercial OpenVPN **client**:

1. The initial forwarded HTTPS connection arrived on the WireGuard interface but exited directly through the WAN. A plain `ip route get` simulation choosing an experimental separate table was **not sufficient**.
2. A scoped `mangle/PREROUTING` firewall mark using the outbound VPN's **existing UniFi policy mark and mask** changed the *actual forwarded path*.
3. A narrowly scoped `nat/POSTROUTING MASQUERADE` rule translated the remote WireGuard client source to the outbound tunnel's own IP.
4. Packet capture confirmed the same HTTPS flow entering the WireGuard server, leaving the outbound VPN tunnel, and returning through that tunnel and the WireGuard server.
5. A narrow `filter/FORWARD` WAN egress REJECT guard blocked a demonstrated direct-WAN path while diagnosing the issue.
6. A reboot cleared the previously added temporary kernel changes; the smaller fwmark + scoped NAT + guard procedure worked again after restart.

**No IP addresses, real LAN networks, public WAN addresses, VPN endpoints, credentials, packet-capture logs, or other private site details from the field test are stored here.** Interface examples and variables below are generic.

## Principle

UniFi creates a policy such as:

```text
<priority>: from all fwmark <MARK_VALUE>/<MARK_MASK> lookup <UNIFI_VPN_TABLE>
```

The chosen UniFi-managed table has a default route through the intended outbound VPN **client** interface.

For matching remote clients, add only a dedicated `mangle/PREROUTING` hook that sets that mark (using the exact value **and mask**) for internet-bound IPv4 packets. Let original LAN routing and UniFi LAN firewall policy continue to operate. Source NAT only that incoming subnet on that one VPN client interface. **Do not edit UniFi-managed policy tables, rules, or default routes.**

The VPN client must already be connected. The remote WireGuard peer must route internet traffic **into** the server, e.g. IPv4 full-tunnel `AllowedIPs = 0.0.0.0/0` in the *client* profile.

## Operator inputs — never publish real values

In a root SSH session opened from the **local LAN**, set these only in the terminal:

```sh
WG_IF='<incoming-WireGuard-server-interface>'
WG_NET='<remote-WireGuard-client-IPv4-CIDR>'
VPN_IF='<connected-UniFi-outbound-VPN-client-interface>'
WAN_IF='<current-physical-WAN-interface>'
LAN_CIDRS='<space-separated-actual-LAN-and-local-VPN-CIDRs>'
VPN_MARK='<UniFi-fwmark-value>/<UniFi-fwmark-mask>'
```

Do **not** execute the following steps with placeholder values. Determine the correct interfaces, source network and *all desired* LAN/local VPN destination ranges from your own device. Use precise destination CIDRs, not a blanket exemption for all RFC1918 space: a broad exemption could unintentionally leave nonlocal private-IP traffic eligible for ordinary routing.

Read-only discovery:

```sh
ip -br -4 addr
ip -4 rule show
ip -4 route show table all
iptables -V
```

Identify the unscoped `from all fwmark ... lookup ...` rule whose table contains a single default route via `$VPN_IF`. A table or mark merely containing `VPN` in its name does **not** establish a match. Check uniqueness and priority on the actual firmware. Do **not** hardcode a mark from somebody else's router: UniFi can regenerate it.

## Manual proof-of-concept (temporary)

**Preconditions:** all previous temporary test hooks have been removed or a reboot has returned the gateway to a clean UniFi-managed state; the outbound VPN is connected; the specific mark, interfaces and networks have been verified; access from the LAN remains available. The commands are intentionally not an automatic installer.

Confirm required interfaces and ensure the proof-of-concept chain does not already exist:

```sh
ip -o link show dev "$WG_IF"
ip -o link show dev "$VPN_IF"
ip -o link show dev "$WAN_IF"
iptables -t mangle -S UVB_FWPOC 2>/dev/null && echo 'STOP: chain already exists'
```

If the final command prints the STOP message, do not proceed. Check that `VPN_MARK` contains both hexadecimal components and that its corresponding UniFi routing policy still leads through `VPN_IF`.

**1. Stage the narrowly scoped WAN guard first (IPv4).**

```sh
iptables -I FORWARD 1 -i "$WG_IF" -s "$WG_NET" -o "$WAN_IF" \
  -m comment --comment UVB_FWPOC_WAN -j REJECT
```

This guard blocks only the named WAN device; it is **not** a complete kill switch if additional WAN egress routes, IPv6 or UniFi reload paths exist. It may temporarily interrupt remote internet access during setup.

**2. Install scoped source NAT for outbound VPN traffic.**

```sh
iptables -t nat -I POSTROUTING 1 -s "$WG_NET" -o "$VPN_IF" \
  -m comment --comment UVB_FWPOC_NAT -j MASQUERADE
```

**3. Create a dedicated marking chain with local exceptions.**

```sh
iptables -t mangle -N UVB_FWPOC
for LAN_NET in $LAN_CIDRS; do
  iptables -t mangle -A UVB_FWPOC -d "$LAN_NET" -j RETURN
done

# Preserve the exact UniFi mark *and* mask from the current policy.
MARK_MASK="${VPN_MARK#*/}"
iptables -t mangle -A UVB_FWPOC -j MARK --set-xmark "$VPN_MARK"
iptables -t mangle -A UVB_FWPOC -j CONNMARK --save-mark \
  --nfmask "$MARK_MASK" --ctmask "$MARK_MASK"

iptables -t mangle -I PREROUTING 1 -i "$WG_IF" -s "$WG_NET" \
  -m comment --comment UVB_FWPOC_HOOK -j UVB_FWPOC
```

The chain matches only ingress from `WG_IF` with source `WG_NET`. A RETURN allows existing UniFi routing and ACLs to decide how to handle LAN traffic; it does **not** grant LAN access by itself.

This proof-of-concept does not modify `ip rule`, create an additional routing table, or set a global default route. It relies on the mark already being recognized by **UniFi's** policy rules. Only one test profile per `UVB_FWPOC` chain is supported; do not run this recipe twice.

## Verification (real packets, not just route lookup)

Use a remote WireGuard client on an **independent outside network**, not a laptop sitting on the LAN. After activating its full-tunnel IPv4 profile:

```sh
iptables -t mangle -L UVB_FWPOC -n -v
iptables -t nat -L POSTROUTING -n -v --line-numbers
iptables -L FORWARD -n -v --line-numbers
```

For a fresh HTTPS destination the operator chooses and knows is safe to contact:

```sh
TEST_HOST='<public-IPv4-destination-for-a-new-HTTPS-test>'
tcpdump -ni any -e -c 30 "host $TEST_HOST and tcp port 443"
```

Start a new HTTPS session from the **remote WireGuard client** to `TEST_HOST`. For the **same TCP connection**, observe:

```text
WireGuard interface  In   : remote VPN source -> public HTTPS destination
Outbound VPN         Out  : outbound VPN tunnel source -> same HTTPS destination
Outbound VPN         In   : HTTPS reply -> outbound VPN tunnel source
WireGuard interface  Out  : HTTPS reply -> remote VPN source
```

No corresponding clear-text test connection should exit through ordinary WAN. The WAN may still carry the encrypted OpenVPN/WireGuard **transport** to the VPN provider; this is normal.

Verify separately: public IPv4 exit belongs to your commercial VPN, actual local LAN access and ACLs still work, DNS resolver path, IPv6 behavior, VPN disconnect/reconnect, WAN failover, and UniFi firewall reload. **Successful HTTPS packet capture alone proves none of the latter.**

### Remove only these test additions

Use only if **you** installed these exact proof-of-concept rules with these variables. Removing the WAN guard while remote clients are still using the tunnel may re-enable direct WAN leaks. Disconnect remote clients first unless you are intentionally testing that behavior.

```sh
iptables -t mangle -D PREROUTING -i "$WG_IF" -s "$WG_NET" \
  -m comment --comment UVB_FWPOC_HOOK -j UVB_FWPOC
iptables -t mangle -F UVB_FWPOC
iptables -t mangle -X UVB_FWPOC

iptables -t nat -D POSTROUTING -s "$WG_NET" -o "$VPN_IF" \
  -m comment --comment UVB_FWPOC_NAT -j MASQUERADE
iptables -D FORWARD -i "$WG_IF" -s "$WG_NET" -o "$WAN_IF" \
  -m comment --comment UVB_FWPOC_WAN -j REJECT
```

The commands intentionally target only `UVB_FWPOC` rules. Never flush UniFi-managed chains or indiscriminately clear connection tracking.

## Next work before a safe installer

- Auto-discover and unambiguously match each outbound VPN client's **current** mark and mask at runtime. Abort on mismatch or ambiguous policy.
- Install a comprehensive fail-closed egress guard **before** any steering, including multi-WAN, changing interfaces, firewall reloads and recovery.
- Implement strict per-profile ingress and LAN destination scopes without weakening UniFi ACLs.
- Define DNS behavior (including router-resolved DNS and encrypted DNS) and IPv6 handling.
- Stage, test, rollback and reconcile changes idempotently; validate packet paths during tunnel loss and recovery.
- Add safe uninstall, reboot persistence, disconnect handling, tests and independent review.
- Validate Teleport and incoming OpenVPN **separately**; the field test establishes only inbound WireGuard to outbound OpenVPN on one UDM Pro.

Existing `bin/bridge-engine.py` remains an **unvalidated experimental prototype**, not an implementation of this field-tested minimal recipe. In particular, its currently fixed early `prohibit` fallback priority may preempt UniFi's later fwmark policy rule on some firmware. Do **not** treat that engine as ready to run on a working gateway.

The `main` branch remains diagnostic-only. Promotion needs repeatable compatibility and failure-state evidence.


## Follow-up field observation: scoped IPv4 forwarding kill-switch

In the same UDM Pro test, an additional **dedicated filter/FORWARD guard** was installed for only the incoming WireGuard interface and remote client CIDR, before UniFi-managed forwarding rules. It was reported to block remote internet connectivity when the outbound VPN was unavailable. Packet counters after use showed matches for the outbound VPN and the final REJECT rule. This is a **limited IPv4 observation**, not a complete zero-leak certification.

A generalized form of the tested rule ordering is:

```sh
# Replace every variable with locally validated values; commands are live changes.
iptables -w -N UVB_KILLSWITCH
iptables -w -A UVB_KILLSWITCH -o "$VPN_IF" -j RETURN
iptables -w -A UVB_KILLSWITCH -o 'br+' -j RETURN
iptables -w -A UVB_KILLSWITCH -j REJECT
iptables -w -I FORWARD 1 -i "$WG_IF" -s "$WG_NET" -j UVB_KILLSWITCH
```

**Caution:** The `br+` wildcard represents a broad interface-name-based allowance, not an audited list of reachable local destination CIDRs; do **not** assume it preserves all network isolation goals. In this field run the `br+` rule had **zero packet matches** when the counters were shared, so LAN accessibility under VPN loss still needs explicit verification. `RETURN` continues to UniFi's other rules; it is not `ACCEPT`.

This guard does **not** cover IPv6, traffic terminating at the router (`INPUT`), router-originated DNS (`OUTPUT`), software/hardware offload, firewall reload gaps, alternate VPN paths, or boot/reconnect. It must not be called a complete privacy kill switch. External VPN tunnel traffic to its provider still needs to reach the WAN as *encrypted transport*.

The earlier single-WAN guard can remain installed during testing, but it is redundant for the normal IPv4 FORWARD path while this comprehensive-output-interface guard is correctly attached. Do not remove safeguards until packet-level checks—including tunnel-down and secondary WAN—confirm the replacement behavior.

### Manual rollback for this separate guard

Disconnect remote VPN clients first if removing protection may expose their internet traffic:

```sh
iptables -w -D FORWARD -i "$WG_IF" -s "$WG_NET" -j UVB_KILLSWITCH
iptables -w -F UVB_KILLSWITCH
iptables -w -X UVB_KILLSWITCH
```

Always inspect existing rules first and remove **only** rules this project installed. Do not flush UniFi-managed chains. This section is field documentation, not a reboot-persistent or fully tested installer.


## Follow-up field observation: DNS and IPv6 reconnaissance

The same UDM Pro test confirmed that remote WireGuard clients **continued to reach local LAN resources with the IPv4 forwarding guard active**.

Further read-only inspection found:
- The incoming WireGuard server interface had **no configured IPv6 address**, while global IPv6 forwarding was enabled.
- The IPv6 FORWARD policy was not independently locked down for the incoming VPN interface.
- The remote WireGuard client sent conventional DNS requests to the **router's own VPN-interface address** on port 53, and the router answered them.
- This capture alone **does not establish the route used for the router's upstream DNS lookups**. The forwarded IPv4 fwmark does not automatically govern the router's own DNS traffic.

**Unverified:** external IPv6 bypass from a remote phone/laptop; router-originated DNS egress; browser DNS-over-HTTPS; DNS behavior after VPN loss; local hostname resolution under alternate DNS. Never claim full DNS/IPv6 leak prevention from IPv4 route or packet counters alone.

Recommended next **manual** validation:
1. Set the *remote WireGuard client profile* to a trusted DNS resolver reachable through the intended outbound VPN, without globally changing UniFi's DNS for LAN users. Test external DNS over the intended VPN. Note that private DNS hostnames may require a separately designed split-DNS policy.
2. Apply an ingress-interface-specific **IPv6 FORWARD reject** as a temporary extra guard, but understand it cannot prevent IPv6 traffic that the remote device chooses to send **outside its WireGuard tunnel**. Test remote client IPv6 routing and leak websites separately.
3. Verify DNS paths with simultaneous interface captures and unique fresh DNS queries. Avoid publishing capture logs containing public/private IPs or identifying hostnames.
4. Keep IPv4 forwarding guard and mark/NAT rules unchanged while testing. Add reboot persistence only after independent disconnect, firewall-reload and rejoin tests.

Do not disable system-wide IPv6 forwarding or overwrite global DNS configuration just to protect one VPN profile. More complete leak guarantees require client-side full-tunnel IPv6 policy and explicit upstream/resolver design.


## Follow-up: DNS and IPv6 field observations (not yet leak-protected)

On the same test gateway, the operator reported continued access to local resources while the scoped IPv4 kill switch was active. The `filter/FORWARD` IPv4 guard recorded both outbound VPN matches and rejected packets. This does **not** yet establish behavior during every VPN reconfiguration or failure.

A read-only diagnostic showed:

- The incoming WireGuard server interface had **no IPv6 address** in the interface listing.
- The gateway's global IPv6 forwarding sysctl was **enabled**, while its displayed IPv6 routes had **no public default route**. The IPv6 filter FORWARD chain had no project-specific WireGuard guard.
- WireGuard clients sent ordinary UDP DNS requests to the **gateway's WireGuard DNS listener**; the gateway returned replies. The upstream resolver's actual egress path was **not captured**. Thus router-originated upstream DNS can potentially bypass an IPv4 FORWARD-only VPN mark and kill switch.

### Safer DNS experiment before implementing split DNS

Do not change global WAN, LAN, or UniFi DNS settings merely to fix one remote VPN client's DNS.

For **one remote WireGuard test client** only, temporarily change the client profile's `[Interface] DNS` to NordVPN's documented public IPv4 resolvers (`103.86.96.100`, `103.86.99.100`). Keep the client full-tunnel IPv4 destination policy, and verify real IPv4 packets to the chosen resolver arrive via WireGuard and leave via the assigned outbound VPN client interface. Check for any direct-WAN packets to that resolver and confirm DNS fails closed during an outbound VPN disconnect. Restore the original client DNS if the test fails.

This choice may break internal hostnames even if direct local IP access still works. A later **split-DNS** implementation should preserve internal domain lookups using explicitly scoped local resolvers, but keep *public* DNS exits confined to the outbound VPN. The gateway's own DNS behavior, content-filter DNS interception, browser DoH, and DNS over TLS/QUIC need individual checks.

**IPv6 caveat:** No IPv6 assigned to the server interface and no IPv6 default route on the gateway are not proof that remote devices cannot use their local IPv6 connectivity outside an IPv4-only WireGuard tunnel. Client-side routing policy must be checked separately. For defense in depth, the future implementation should explicitly reject IPv6 **forwarded from selected VPN ingress interfaces** until there is a verified IPv6-through-VPN design, and test the rule through reconnects and reloads. It must not disable IPv6 globally for other LANs.

**Status remains developmental:** DNS, IPv6, failover/reload behavior, kill-switch durability, persistence and automated recovery have not yet passed end-to-end privacy testing.
