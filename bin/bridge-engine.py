#!/usr/bin/env python3
"""Experimental IPv4 VPN-to-VPN forwarding with fail-closed guards for UniFi.

NOT production-validated. This requires root on a compatible gateway and
existing UniFi-managed VPN client routing rules. No third-party dependencies.
"""
from __future__ import annotations

import argparse
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

VERSION = "0.3.0-experimental"
IFACE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,14}$")
MARK_RULE = re.compile(
    r"^\s*(\d+):\s+from all fwmark "
    r"(0x[0-9a-fA-F]+(?:/0x[0-9a-fA-F]+)?) lookup ([a-zA-Z0-9_.-]+)\s*$"
)
EGRESS = re.compile(r"^(wgclt[0-9]+|tunovpnc[0-9]+|ovpnc[0-9]+)$")
ALLOW_TYPES = {"teleport", "wireguard", "openvpn"}
TABLES = ("filter", "mangle", "nat")
PREFIX = "UVB"
FALLBACK_PREF = 29000
DEFAULT_CONFIG = "/data/unifi-vpn-bridge/config.json"
DEFAULT_RUNTIME = "/data/unifi-vpn-bridge/bin/bridge-engine.py"
DEFAULT_HOOK = "/data/on_boot.d/50-unifi-vpn-bridge.sh"
DEFAULT_SERVICE = "/etc/systemd/system/unifi-vpn-bridge.service"


class BridgeError(Exception):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise BridgeError(message)


def duplicate_key_reject(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, f"duplicate JSON field: {key}")
        obj[key] = value
    return obj


def ipv4_network(value: str) -> str:
    require(isinstance(value, str), "IPv4 CIDR must be a string")
    net = ipaddress.ip_network(value, strict=True)
    require(isinstance(net, ipaddress.IPv4Network), "IPv6 CIDR is not supported here")
    require(net.prefixlen >= 8 and not (net.is_multicast or net.is_loopback or
                                      net.is_link_local or net.is_unspecified),
            f"unsafe network: {value}")
    return str(net)


def load_config(filename: str) -> dict:
    path = Path(filename)
    require(path.is_file(), f"missing config: {path}")
    require(path.stat().st_size <= 65536, "config is too large")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=duplicate_key_reject)
    except (OSError, UnicodeError, ValueError) as error:
        raise BridgeError(f"invalid config: {error}") from error
    require(type(obj) is dict and set(obj) == {"profiles", "watch_interval"},
            "config must contain only profiles and watch_interval")
    interval = obj["watch_interval"]
    require(type(interval) is int and 10 <= interval <= 300,
            "watch_interval must be an integer from 10 to 300")
    raw = obj["profiles"]
    require(type(raw) is list and 1 <= len(raw) <= 12, "expected 1 to 12 profiles")
    profiles = []
    seen_ifaces, seen_nets = set(), []
    for i, entry in enumerate(raw):
        require(type(entry) is dict and set(entry) == {
            "type", "ingress", "source_cidr", "egress", "lan_cidrs", "dns_ipv4"
        }, f"profile {i}: unexpected or missing field")
        kind, ingress, egress = entry["type"], entry["ingress"], entry["egress"]
        require(type(kind) is str and kind in ALLOW_TYPES, f"profile {i}: bad VPN type")
        require(type(ingress) is str and IFACE.fullmatch(ingress) is not None,
                f"profile {i}: invalid incoming interface")
        require(type(egress) is str and EGRESS.fullmatch(egress) is not None,
                f"profile {i}: egress must be a UniFi VPN client (wgcltN/tunovpncN/ovpncN)")
        require(ingress != egress and ingress not in seen_ifaces,
                f"profile {i}: duplicate ingress or same ingress/egress")
        seen_ifaces.add(ingress)
        source = ipv4_network(entry["source_cidr"])
        network = ipaddress.IPv4Network(source)
        require(not any(network.overlaps(n) for n in seen_nets),
                f"profile {i}: overlapping remote VPN address ranges")
        seen_nets.append(network)
        lans = entry["lan_cidrs"]
        require(type(lans) is list and 1 <= len(lans) <= 16,
                f"profile {i}: specify 1 to 16 explicit LAN ranges")
        lan_cidrs = [ipv4_network(n) for n in lans]
        require(len(set(lan_cidrs)) == len(lan_cidrs), f"profile {i}: duplicate LAN range")
        require(all(not network.overlaps(ipaddress.IPv4Network(n)) for n in lan_cidrs),
                f"profile {i}: remote VPN subnet overlaps allowed LAN")
        dns = entry["dns_ipv4"]
        require(type(dns) is str, f"profile {i}: dns_ipv4 must be a string")
        try:
            address = ipaddress.IPv4Address(dns)
        except ipaddress.AddressValueError as error:
            raise BridgeError(f"profile {i}: invalid DNS address") from error
        require(address.is_global, f"profile {i}: DNS resolver must be a public IPv4 address")
        require(not any(address in ipaddress.IPv4Network(n) for n in lan_cidrs),
                f"profile {i}: DNS resolver must not be on the LAN")
        profiles.append({
            "type": kind, "ingress": ingress, "source_cidr": source, "egress": egress,
            "lan_cidrs": lan_cidrs, "dns_ipv4": dns,
        })
    return {"watch_interval": interval, "profiles": profiles}


class Runner:
    """All command execution goes through argument vectors; never shell=True."""

    def __init__(self, preview=False):
        self.preview = preview

    def read(self, *argv, optional=False) -> str:
        p = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=15)
        if p.returncode and not optional:
            raise BridgeError(f"{shlex.join(argv)} failed: {p.stderr.strip()}")
        return p.stdout if p.returncode == 0 else ""

    def check(self, *argv) -> bool:
        p = subprocess.run(argv, check=False, capture_output=True, timeout=15)
        return p.returncode == 0

    def write(self, *argv) -> None:
        if self.preview:
            print("WOULD:", shlex.join(argv))
            return
        p = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=15)
        if p.returncode:
            raise BridgeError(f"mutation failed: {shlex.join(argv)}: {p.stderr.strip()}")


def policy_marks(runner: Runner, profiles: list) -> dict:
    """Resolve only unscoped UniFi fwmark rules with an exact VPN default route."""
    text = runner.read("ip", "-4", "rule", "show")
    candidates = []
    for line in text.splitlines():
        match = MARK_RULE.fullmatch(line.strip())
        if not match:
            continue
        priority, mark, table = match.groups()
        require(int(priority) < FALLBACK_PREF, "UniFi VPN policy has unsafe precedence relative to fallback")
        route = runner.read("ip", "-4", "route", "show", "table", table, optional=True)
        defaults = [line.split() for line in route.splitlines() if line.startswith("default ")]
        if len(defaults) != 1:
            continue
        parts = defaults[0]
        if "dev" not in parts or parts.index("dev") + 1 >= len(parts):
            continue
        dev = parts[parts.index("dev") + 1]
        value, _, mask = mark.partition("/")
        mask = mask or "0xffffffff"
        # A zero mask would route arbitrary traffic; the mark must be nonzero.
        require(int(value, 16) != 0 and int(mask, 16) != 0,
                "invalid firewall mark/mask")
        candidates.append((dev, f"{value}/{mask}"))
    result = {}
    for p in profiles:
        dev = p["egress"]
        if dev in result:
            continue
        options = {mark for candidate_dev, mark in candidates if candidate_dev == dev}
        require(len(options) == 1,
                f"egress {dev}: expected exactly one unscoped fwmark route, found {len(options)}")
        result[dev] = options.pop()
    return result


def chain_rules(conf: dict, marks: dict) -> dict:
    """Generate ordered firewall chains. Each array item is an argv fragment."""
    profiles = conf["profiles"]
    fw, dns_input, fw6, dns_input6, prerouting, dns_nat, snat = [], [], [], [], [], [], []
    for p in profiles:
        iface, source, egress, dns = (
            p["ingress"], p["source_cidr"], p["egress"], p["dns_ipv4"]
        )
        # DNS is marked BEFORE LAN exemptions, so DNATing gateway DNS to
        # an external resolver cannot accidentally select the home WAN.
        for proto in ("udp", "tcp"):
            if egress in marks:
                prerouting.append(["-i", iface, "-s", source, "-p", proto,
                                   "--dport", "53", "-j", "MARK",
                                   "--set-xmark", marks[egress]])
            dns_nat.append(["-i", iface, "-s", source, "-p", proto,
                            "--dport", "53", "-j", "DNAT", "--to-destination", dns])
            dns_input.append(["-i", iface, "-p", proto, "--dport", "53", "-j", "DROP"])
            dns_input6.append(["-i", iface, "-p", proto, "--dport", "53", "-j", "DROP"])
        for lan in p["lan_cidrs"]:
            if egress in marks:
                prerouting.append(["-i", iface, "-s", source, "-d", lan, "-j", "RETURN"])
            fw.append(["-i", iface, "-s", source, "-d", lan, "-j", "RETURN"])
        if egress in marks:
            prerouting.append(["-i", iface, "-s", source, "-j", "MARK",
                               "--set-xmark", marks[egress]])
        fw.append(["-i", iface, "-s", source, "-o", egress, "-j", "RETURN"])
        # The final rule catches invalid source addresses on the VPN interface too.
        fw.append(["-i", iface, "-j", "DROP"])
        fw6.append(["-i", iface, "-j", "DROP"])
        snat.append(["-s", source, "-o", egress, "-j", "MASQUERADE"])
    return {
        ("iptables", "filter", "FORWARD", "UVB_FWD"): fw,
        ("iptables", "filter", "INPUT", "UVB_DNSIN"): dns_input,
        ("ip6tables", "filter", "FORWARD", "UVB_FWD6"): fw6,
        ("ip6tables", "filter", "INPUT", "UVB_DNSIN6"): dns_input6,
        ("iptables", "nat", "PREROUTING", "UVB_DNS"): dns_nat,
        ("iptables", "nat", "POSTROUTING", "UVB_SNAT"): snat,
        ("iptables", "mangle", "PREROUTING", "UVB_MARK"): prerouting,
    }


def _rules(runner: Runner, binary: str, table: str, chain: str):
    text = runner.read(binary, "-t", table, "-S", chain, optional=True)
    if not text:
        return None
    try:
        return [shlex.split(line)[2:] for line in text.splitlines()
                if line.startswith("-A " + chain + " ")]
    except ValueError as error:
        raise BridgeError(f"unparseable {chain} rules: {error}") from error


def _hooks(runner: Runner, binary: str, table: str, builtin: str, base: str):
    lines = runner.read(binary, "-t", table, "-S", builtin)
    refs = []
    expected_tag = "unifivpnbridge"
    rule_position = 0
    for line in lines.splitlines():
        try:
            tokens = shlex.split(line)
        except ValueError as error:
            raise BridgeError("unable to parse firewall listing") from error
        if not tokens or tokens[:2] != ["-A", builtin]:
            continue
        position = rule_position
        rule_position += 1
        if "--comment" not in tokens or "-j" not in tokens:
            continue
        if tokens[tokens.index("--comment") + 1] != expected_tag:
            continue
        jump = tokens[tokens.index("-j") + 1]
        if jump not in (base + "_A", base + "_B"):
            continue
        refs.append((jump, tokens[2:], position))
    return refs


def sync_chain(runner: Runner, binary: str, table: str, builtin: str,
               base: str, expected: list):
    """Build inactive A/B chain in full, hook it at #1, then retire old hooks."""
    hooks = _hooks(runner, binary, table, builtin, base)
    current = hooks[0][0] if hooks else None
    if len(hooks) == 1 and hooks[0][2] == 0 and _rules(runner, binary, table, current) == expected:
        return
    target = base + ("_B" if current == base + "_A" else "_A")
    # Do not flush any currently referenced chain, even when a hook was displaced.
    require(all(h[0] != target for h in hooks),
            f"refusing to flush a live chain {target}")
    if _rules(runner, binary, table, target) is None:
        runner.write(binary, "-t", table, "-N", target)
    else:
        runner.write(binary, "-t", table, "-F", target)
    for args in expected:
        runner.write(binary, "-t", table, "-A", target, *args)
    runner.write(binary, "-t", table, "-I", builtin, "1", "-m", "comment",
                 "--comment", "unifivpnbridge", "-j", target)
    # Retire old hooks only after the complete new chain is installed.
    for _, args, _ in hooks:
        runner.write(binary, "-t", table, "-D", builtin, *args)


def ensure_source_fallback(runner: Runner, profiles: list):
    """Persistent in-kernel block below VPN fwmark policy, above main WAN route."""
    rules = runner.read("ip", "-4", "rule", "show")
    for idx, p in enumerate(profiles):
        allow_pref, block_pref = FALLBACK_PREF + idx * 2, FALLBACK_PREF + idx * 2 + 1
        source = p["source_cidr"]
        # Prohibit before allowing LAN: brief LAN interruption is safer than WAN leaks.
        block = f"{block_pref}: from {source} prohibit"
        if block not in rules:
            runner.write("ip", "-4", "rule", "add", "pref", str(block_pref),
                         "from", source, "prohibit")
        for lan in p["lan_cidrs"]:
            allow = f"{allow_pref}: from {source} to {lan} lookup main"
            if allow not in rules:
                runner.write("ip", "-4", "rule", "add", "pref", str(allow_pref),
                             "from", source, "to", lan, "lookup", "main")


def verify_runtime(runner: Runner, profiles: list):
    """Check prerequisites before a single mutation (including IPv6 filtering)."""
    for binary in ("iptables", "ip6tables"):
        require(runner.check(binary, "-t", "filter", "-S", "FORWARD"),
                f"{binary} filter/FORWARD unavailable; refusing to run")
    require(runner.check("iptables", "-t", "nat", "-S", "PREROUTING"),
            "IPv4 NAT table unavailable")
    require(runner.check("iptables", "-t", "mangle", "-S", "PREROUTING"),
            "IPv4 mangle table unavailable")
    for p in profiles:
        for dev in (p["ingress"], p["egress"]):
            require(runner.check("ip", "-o", "link", "show", "dev", dev),
                    f"interface {dev} not present")


def reconcile(runner: Runner, config: dict):
    """Repeatedly converge guarded rules. Never deliberately remove a live guard."""
    profiles = config["profiles"]
    verify_runtime(runner, profiles)
    ensure_source_fallback(runner, profiles)
    # Install protection first, even if no outbound VPN policy exists.
    chain = chain_rules(config, {})
    for key in list(chain)[:4]:
        sync_chain(runner, *key, chain[key])
    # If UniFi withdraws its VPN fwmark rule, these guards and kernel source
    # prohibition remain; do not remove them or fall back to ordinary WAN.
    marks = policy_marks(runner, profiles)
    chain = chain_rules(config, marks)
    for key in list(chain)[4:]:
        sync_chain(runner, *key, chain[key])
    return marks


def write_service(runner: Runner, config_path: str, engine_path: str):
    """Optional boot recovery using an already-installed udm-boot mechanism."""
    require(config_path.startswith("/data/") and engine_path.startswith("/data/"),
            "service paths must be under /data")
    for path in (config_path, engine_path):
        require(re.fullmatch(r"/[A-Za-z0-9_./-]+", path) is not None and ".." not in path,
                "unsafe service path")
    require(Path(engine_path).exists(), f"engine script absent: {engine_path}")
    unit = f"""[Unit]
Description=UniFi VPN Bridge (EXPERIMENTAL, fail-closed recovery)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {engine_path} watch --config {config_path} --experimental
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    boot = f"""#!/bin/sh
# Requires the separately installed udm-boot.service; no downloads performed.
exec /usr/bin/python3 {engine_path} install-service --config {config_path} --experimental --engine-path {engine_path}
"""
    if runner.preview:
        print(f"WOULD WRITE {DEFAULT_SERVICE}:\n{unit}")
        print(f"WOULD WRITE {DEFAULT_HOOK}:\n{boot}")
    else:
        Path(DEFAULT_SERVICE).write_text(unit, encoding="utf-8")
        Path(DEFAULT_HOOK).write_text(boot, encoding="utf-8")
        Path(DEFAULT_HOOK).chmod(0o755)
    runner.write("systemctl", "daemon-reload")
    runner.write("systemctl", "enable", "unifi-vpn-bridge.service")
    runner.write("systemctl", "restart", "unifi-vpn-bridge.service")
    if not runner.check("systemctl", "is-enabled", "udm-boot.service"):
        print("WARNING: udm-boot.service is absent. Service may NOT survive a UniFi reboot;",
              file=sys.stderr)


def main(argv=None, runner=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply", "watch", "status", "install-service"))
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--experimental", action="store_true",
                        help="acknowledge unverified router behavior; required for all mutations")
    parser.add_argument("--engine-path", default=DEFAULT_RUNTIME)
    args = parser.parse_args(argv)
    changing = args.command in ("apply", "watch", "install-service")
    require(not changing or args.experimental,
            "changes require --experimental; this feature has not been hardware-validated")
    require(not changing or os.geteuid() == 0, "root required for router changes")
    config = load_config(args.config)
    io = runner or Runner(preview=args.command == "plan")
    if args.command == "status":
        print("EXPERIMENTAL: status is read-only, NOT proof of end-to-end leak protection")
        for p in config["profiles"]:
            print(f"{p['type']}: {p['ingress']} ({p['source_cidr']}) -> {p['egress']}")
        for table, base in (("filter", "UVB_FWD"), ("filter", "UVB_DNSIN"),
                            ("mangle", "UVB_MARK"), ("nat", "UVB_DNS")):
            print(f"{table}/{base}: "
                  f"{io.read('iptables', '-t', table, '-S', base+'_A', optional=True)[:80].strip() or 'not found'}")
        return 0
    if args.command == "install-service":
        write_service(io, str(Path(args.config).resolve()), str(Path(args.engine_path).resolve()))
        return 0
    if args.command == "plan":
        print("EXPERIMENTAL PREVIEW ONLY; no changes will be made")
        reconcile(io, config)
        return 0
    with open("/run/unifi-vpn-bridge.lock", "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == "apply":
            marks = reconcile(io, config)
            print("Rules installed experimentally; hardware leak testing STILL REQUIRED.")
            print("Resolved outbound fwmarks:", marks)
        else:
            while True:
                try:
                    reconcile(io, load_config(args.config))
                except (BridgeError, OSError) as error:
                    print(f"watchdog: {error}; keeping existing guards/fallback", file=sys.stderr)
                time.sleep(config["watch_interval"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BridgeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"UniFi VPN Bridge: {exc}", file=sys.stderr)
        sys.exit(2)
