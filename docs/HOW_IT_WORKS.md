# How UniFi VPN Bridge works

## The problem

UniFi can simultaneously operate a remote-access VPN **server** and an outbound commercial VPN **client**. On the tested UDM Pro, incoming WireGuard clients could reach local resources, but ordinary UniFi VPN-client policy routing did not automatically make their forwarded web traffic exit through the commercial VPN. Without extra rules, forwarded internet packets could use the WAN.

The bridge solves this using UniFi's own VPN client's **existing firewall mark**. It does **not** replace UniFi's default route or edit managed policy-routing tables.

## Traffic paths

```text
Remote WireGuard client (IPv4 full tunnel)
              |
       incoming WireGuard server (WG_IF)
              |
       project IPv4 forwarding guard
              |
     +--------+----------+
     |                   |
  LOCAL destination   OTHER IPv4 destination
     |                   |
  RETURN / main LAN   mangle MARK + CONNMARK
  routing / UniFi ACL    |
                        UniFi's native VPN policy
                         |
                     outgoing VPN_IF
                         |
                    scoped MASQUERADE
                         |
                    commercial VPN provider
```

1. **Source match:** only packets arriving on the named WireGuard server interface and from the configured VPN-client subnet get the IPv4 routing mark. Other LAN and router traffic is not targeted.
2. **Local exceptions:** packets heading to the operator's `LAN_EXEMPTIONS` return to normal UniFi routing. Existing UniFi firewall policies still apply. These exceptions should be specific to actual local destinations, not copied blindly.
3. **Internet mark:** remaining IPv4 packets receive the exact UniFi-managed `fwmark` mask that already directs packets to the chosen VPN client's routing table.
4. **NAT:** MASQUERADE on the selected outgoing VPN client interface allows the return packets to find their way back to the remote WireGuard client.
5. **Kill switch:** a dedicated `filter/FORWARD` chain permits only forwarded traffic exiting via the VPN client or LAN bridge interfaces, and rejects other forwarded IPv4 egress for the specified remote client subnet.
6. **IPv6:** a separate scoped `ip6tables/FORWARD` rule rejects forwarded IPv6 arriving via the selected WireGuard server, rather than globally disabling IPv6.
7. **Reconciliation:** the systemd service starts the same script in a 15-second loop. It checks for missing/reordered project hooks, discovers the current UniFi VPN mark, and retains the forwarding guards if the VPN policy is temporarily missing.

## Why a route lookup is not enough

During the hardware test, a custom source-route table appeared correct in `ip route get`, yet a real forwarded HTTPS flow was seen on the WAN. Actual packet capture established the working forwarded path only after applying UniFi's existing mark on the WireGuard ingress traffic.

## Why the kill switch isn't perfect

The forwarding guard is attached to the kernel's filter FORWARD path; a DNS lookup answered by the router itself can leave as a separate router-originated OUTPUT packet over the normal WAN. Early boot may precede the watchdog installation. UniFi policy/firewall reload and hardware acceleration can affect which rules are actually applied. These require separate testing and engineering before calling it a leak-proof solution.

The `RETURN` rules are **not** broad firewall ACCEPT rules. They let the rest of the UniFi firewall chain make normal access-control decisions.

## What we don't do

We do not generate VPN certificates, change the gateway's WAN route, collect secrets, upload network information, install third-party boot hooks, or modify other people's UniFi configurations. The operator must configure and verify their own interfaces and CIDRs.
