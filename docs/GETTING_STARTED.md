# Getting started: guided walkthrough or optional wizard

> **Development preview: READ-ONLY.** This setup helps identify UniFi VPN interfaces and inspect existing routing. It **does not** enable VPN-to-VPN bridging, install a kill switch, or change firewall rules. Do not rely on it for privacy.

## Goal

Connect remotely using **UniFi Teleport, WireGuard Server, or OpenVPN Server** to access internal resources (NAS, cameras, servers) while directing your web browsing through an outbound commercial VPN such as NordVPN, Proton VPN, or Mullvad.

The remote client's internet traffic must first travel **into** the gateway through its remote-access VPN. Split-tunneled web traffic that bypasses the gateway cannot be redirected. DNS and IPv6 leak protection are not yet implemented.

## Prerequisites

- A UniFi gateway with administrator-controlled SSH access.
- At least one UniFi incoming VPN (Teleport, WireGuard Server or OpenVPN Server) already configured.
- An outbound UniFi WireGuard or OpenVPN **client** connected to your chosen provider.
- Bash and OpenSSH on your laptop or desktop.
- A backup access path to the router. Do not experiment on a production gateway with no recovery path.

The project does not create VPN accounts or profiles. Use UniFi Network settings for those.

## Option A: manual walkthrough

**1. Download the source locally and inspect it:**

```bash
git clone https://github.com/King-Enmity/UniFi-VPN-Bridge.git
cd UniFi-VPN-Bridge
git switch development
less scripts/setup-wizard.sh
less bin/unifi-vpn-bridge
```

**2. Confirm your incoming and outbound VPN profiles are configured in UniFi Network.** Ensure the outbound commercial VPN is connected.

**3. Identify actual gateway interfaces (read-only):**

```bash
ssh root@192.168.1.1 'ip -o link show'
```

Replace the gateway address. Interface names vary by model and firmware; `tlprt0`, `wgsrv1`, `tun0`, `tunovpnc1`, and `wgclt4` are examples, not guaranteed matches. Map each interface to its actual VPN before continuing.

**4. Run the read-only doctor with verified interface names:**

```bash
ssh root@192.168.1.1 \
  'bash -s -- doctor --route teleport:tlprt0:tunovpnc1 --route wireguard:wgsrv1:wgclt4 --route openvpn:tun0:wgclt4' \
  < bin/unifi-vpn-bridge
```

Only include the incoming VPN types you have set up. A discovered **candidate IPv4 policy mark** is **not proof** that forwarded traffic exits through that VPN, or that DNS and IPv6 are safe. If the script reports `AMBIGUOUS` or `NOT READY`, do not guess.

## Option B: optional guided wizard

The wizard automates *diagnostics only*. It lists interfaces, asks for mappings, and streams the local read-only doctor to the gateway over SSH. It does not download dependencies onto the gateway, persist software, or alter firewall rules.

Interactive:

```bash
bash scripts/setup-wizard.sh
```

Or supply the SSH destination:

```bash
bash scripts/setup-wizard.sh --host root@192.168.1.1
```

Unattended, repeatable diagnostics with explicit mappings:

```bash
bash scripts/setup-wizard.sh --host root@192.168.1.1 \
  --route teleport:tlprt0:tunovpnc1 \
  --route wireguard:wgsrv1:wgclt4 \
  --route openvpn:tun0:wgclt4
```

Interface list only:

```bash
bash scripts/setup-wizard.sh --host root@192.168.1.1 --list-only
```

The wizard requires you to select VPN interfaces. It never silently guesses an outgoing VPN, installs a service, or asks for/stores VPN credentials. SSH may prompt for normal authentication.

## Future automatic configuration

A fully automatic bridge installer is **not available**. Before we introduce one, we'll need firmware-specific route validation, a staged fail-closed guard, explicit DNS and IPv6 policies, packet-level verification on real UniFi gateways, and safe rollback. The eventual setup should preview every planned change and require confirmation before modifying the router.

## Reporting results

When filing a GitHub issue, share your gateway model, UniFi OS and Network versions, and **redacted** interface/doctor output. Do not share VPN private keys, authentication tokens, SSH keys, passwords, or complete router configuration.

This is an independent community project, not affiliated with or endorsed by Ubiquiti.
