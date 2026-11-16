# Find your UniFi VPN server, VPN client, source subnet, and firewall mark

**Read this before editing the bridge configuration.** The purpose of these commands is to discover values on **your own gateway**, without changing routing or firewall rules. Everything in this guide is read-only unless explicitly labeled otherwise.

## First: which "name" do we need?

UniFi shows a **friendly VPN name** in the Network application (the label you gave it). Linux uses a different **interface name** to move packets. **UniFi VPN Bridge needs the Linux interface name**, not the friendly name, provider name, or WireGuard peer name.

| What you are looking for | Saved as | Example format (not your real interface) |
|---|---|---|
| Incoming UniFi WireGuard **VPN Server** interface | `WG_IF` | `wgsrvN` |
| Whole IPv4 subnet used by that server's remote clients | `WG_CIDR` | A canonical network with `/prefix` |
| Outgoing UniFi commercial **VPN Client** interface | `VPN_IF` | `tunovpncN` for some OpenVPN clients |
| Local destinations that stay on normal LAN routes | `LAN_EXEMPTIONS` | Your actual LAN/VLAN CIDRs |
| Outgoing VPN policy **firewall mark** | **Not a config field** | Automatically discovered at runtime |

The letters `N` above mean an interface number, **not** something to enter literally. Actual interface names vary by model, firmware and VPN configuration.

## Step 1 — Find the incoming WireGuard VPN Server

1. In UniFi Network, locate your **VPN Server** configuration and note which server is **WireGuard** and what **subnet/network** is assigned to remote clients. Depending on UniFi Network version, the page may be under *Settings → VPN* or a VPN Server section.
2. Connect to the gateway from your **local LAN** with SSH as root. Run:

```bash
# List existing interfaces, including their actual Linux names.
ip -o link show

# Summarize IPv4 addresses currently assigned to those interfaces.
ip -br -4 addr

# If the 'wg' tool is available, list WireGuard interfaces only.
# This prints interface names, not private keys.
if command -v wg >/dev/null 2>&1; then wg show interfaces; fi
```

3. Look for the interface that is associated with the **server** you configured in UniFi; do **not** assume every `wg*` device is an incoming server (some may be outbound VPN clients). Compare its assigned address/prefix with the **VPN Server subnet** shown in UniFi.
4. Once you've identified a **candidate**, substitute its actual name in these **read-only** commands:

```bash
WG_IF='REPLACE_WITH_SERVER_INTERFACE'

# Confirm the device exists; examine the gateway address/prefix.
ip -o link show dev "$WG_IF"
ip -4 addr show dev "$WG_IF"

# Look for connected IPv4 routes for this interface.
ip -4 route show dev "$WG_IF"
```

The gateway may display a host IP with a prefix, but **`WG_CIDR` must be the complete canonical client network** associated with that server. For example, a host address followed by `/29` is not necessarily the network's first address. Cross-check with UniFi's configured server network and the connected route.

**Don't guess:** If you cannot confidently map a Linux device to the UniFi **VPN Server**, stop rather than setting `WG_IF` to a similarly named outgoing VPN.

## Step 2 — Find the outgoing commercial VPN Client

1. In UniFi Network, locate **VPN Client**, not VPN Server. Note which provider/client connection is currently **connected** and whether it is **OpenVPN** or **WireGuard**.
2. On the gateway, run:

```bash
# List all current IPv4 interfaces and their addresses.
ip -br -4 addr

# Display VPN-related policy routing rules, without changing them.
ip -4 rule show | grep -E 'fwmark|lookup'
```

3. Look for candidate outbound interfaces such as `tunovpncN` (OpenVPN) or `wgcltN` (WireGuard). These are possible patterns, **not guaranteed names** or evidence of an active commercial VPN by themselves.
4. Identify the interface by matching the **routing table that UniFi created for the connected VPN client**:

```bash
# From 'ip -4 rule show', copy one lookup TABLE associated with a
# candidate 'from all fwmark ... lookup TABLE' rule.
# Example assignment is a placeholder: replace it with the REAL table name.
VPN_TABLE='REPLACE_WITH_TABLE_FROM_RULE'

# A matching table should have a single 'default ... dev VPN_INTERFACE'
# route pointing through the selected outbound VPN CLIENT.
ip -4 route show table "$VPN_TABLE"
```

5. Set `VPN_IF` to the actual **`dev` name** on that default route **only after** confirming it belongs to your selected UniFi VPN **Client**:

```bash
VPN_IF='REPLACE_WITH_CONNECTED_OUTBOUND_CLIENT_INTERFACE'
ip -o link show dev "$VPN_IF"
ip -4 route show table "$VPN_TABLE"
```

**Important:** If you have multiple VPN clients or ambiguous policy rules, inspect each table and match it to UniFi's connection settings. A tunnel being listed as `UP` alone doesn't prove that it is your commercial VPN, or that its policy route is active.

## Step 3 — Understand and verify the UniFi `fwmark`

A UniFi VPN-client policy rule may look like this (illustrative format; **no live values**):

```text
PRIORITY: from all fwmark VALUE/MASK lookup TABLE_NAME
```

- **`VALUE`**: firewall mark bits applied to packets assigned to the VPN policy.
- **`MASK`**: specifies which mark bits UniFi checks.
- **`TABLE_NAME`**: a UniFi-owned routing table; its default route should exit through your chosen `VPN_IF`.
- **`PRIORITY`**: controls rule evaluation order. Do not modify priorities or overwrite UniFi's rules.

Check the policy and then its corresponding routing table:

```bash
ip -4 rule show

# Replace this with the selected real TABLE_NAME.
ip -4 route show table "$VPN_TABLE"
```

The bridge script **does not require you to type the mark into a file**. It scans the system for a unique, unrestricted `from all fwmark VALUE/MASK lookup TABLE` policy and confirms that its table has one default route via `VPN_IF`. The mark can change after UniFi regenerates a VPN connection; hardcoding it would be fragile.

After you complete `bridge.env`, use the built-in **read-only** discovery command:

```bash
set -a
. /data/unifi-vpn-bridge/bridge.env
set +a

bash /data/unifi-vpn-bridge/bridge-watch.sh doctor
```

Expected format:

```text
UniFi outbound VPN fwmark: VALUE/MASK
```

The reported mark must match the current UniFi-owned route for your chosen outbound client. If the command reports **no unique policy mark**, check VPN Client connectivity, the `VPN_IF` selection and the relevant routing table. **Do not guess a mark or modify the script's `MARK` command.**

`doctor` is **not proof that internet traffic is leaving through the VPN**. Verify actual forwarded packets and return traffic using the tests in [SETUP.md](SETUP.md).

## Step 4 — Find the local CIDRs for `LAN_EXEMPTIONS`

```bash
# Lists all normal IPv4 routes, including directly connected LAN/VLAN routes.
ip -4 route show table main

# You can narrow your review to the bridge (br*) interfaces:
ip -4 route show table main | grep -E ' dev br[[:alnum:]_.-]+'
```

Choose the exact LAN/VLAN networks that remote clients should access without going through the commercial VPN. A local VPN subnet may need special consideration if it uses a non-bridge interface. Avoid pasting large blanket private ranges simply because they are private IP space; an exemption is a routing decision, not an ACL.

If you already had `UVB_NORD` from a manual test, keep the existing exception order until you intentionally migrate that chain; the watchdog refuses unrecognized rule layouts.

## Step 5 — What to edit (and what NOT to edit)

Create or edit **only this local file on your gateway**:

```text
/data/unifi-vpn-bridge/bridge.env
```

Populate:

```bash
# Fill in your actual interface names and network ranges ON YOUR ROUTER.
WG_IF=REPLACE_WITH_WIREGUARD_SERVER_INTERFACE
VPN_IF=REPLACE_WITH_OUTBOUND_VPN_CLIENT_INTERFACE
WG_CIDR=REPLACE_WITH_WIREGUARD_CLIENT_NETWORK_AND_PREFIX
LAN_EXEMPTIONS="REPLACE_WITH_ACTUAL_LOCAL_NETWORK_CIDR"
UVB_INTERVAL=15
```

Do **not** edit `scripts/bridge-watch.sh` to insert an interface name, subnet, provider, mark, or routing table. The script reads the first four values from `bridge.env` and finds the current `fwmark` automatically.

Do **not** set `WG_IF` to the outbound interface, `VPN_IF` to the incoming server, or `WG_CIDR` to the gateway's host address. Do not edit UniFi-managed `ip rule` or `ip route` entries.

**Privacy:** `ip -4 addr`, `ip -4 route` and `ip -4 rule` output can contain your real private or public addresses; review and redact before posting. Never share VPN keys, configuration exports or unredacted router logs. All examples in this guide are deliberately placeholders.

## If you still cannot identify an interface

- **No `wg` command?** The first two `ip` commands still work; match interface address/subnet to the UniFi VPN Server.
- **No WireGuard server interface?** Make sure the server exists and is enabled; don't use a client interface in its place.
- **No outbound VPN route/table?** Confirm the UniFi VPN **Client** is connected, then rerun `ip -4 rule show` and table inspection.
- **Multiple possible fwmarks?** Stop; identify the correct outbound VPN and resolve the ambiguity rather than applying an unknown mark.
- **Need a human-readable UniFi display name?** Use the UniFi Network settings screen. Linux interface listings do not reliably show the friendly name.

Then continue with [the step-by-step manual setup](SETUP.md).
