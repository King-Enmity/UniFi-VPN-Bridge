"""Offline unit checks for the EXPERIMENTAL routing engine.

These tests DO NOT establish router compatibility or packet-level leak prevention.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "bin" / "bridge-engine.py"
spec = importlib.util.spec_from_file_location("bridge_engine", MODULE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def config():
    return {
        "watch_interval": 30,
        "profiles": [
            {"type": "teleport", "ingress": "tlprt0", "source_cidr": "10.20.30.0/24",
             "egress": "wgclt4", "lan_cidrs": ["192.168.1.0/24", "192.168.5.0/24"],
             "dns_ipv4": "1.1.1.1"},
            {"type": "wireguard", "ingress": "wgsrv1", "source_cidr": "10.30.40.0/24",
             "egress": "tunovpnc1", "lan_cidrs": ["192.168.1.0/24"],
             "dns_ipv4": "9.9.9.9"},
            {"type": "openvpn", "ingress": "tun0", "source_cidr": "10.40.50.0/24",
             "egress": "wgclt4", "lan_cidrs": ["192.168.1.0/24"],
             "dns_ipv4": "1.1.1.1"},
        ]
    }


class ReadOnlyFake:
    def __init__(self, rules=None, routes=None):
        self.calls = []
        self.rules = rules or ("3000: from all fwmark 0x6a0000/0x7e0000 lookup 201.wgclt4\n"
                               "3001: from all fwmark 0x6c0000/0x7e0000 lookup 202.tunovpnc1\n")
        self.routes = routes or {"201.wgclt4": "default dev wgclt4\n",
                                 "202.tunovpnc1": "default dev tunovpnc1\n"}
        self.hooks = {}

    def read(self, *args, optional=False):
        self.calls.append(("read", args))
        if args == ("ip", "-4", "rule", "show"):
            return self.rules
        if args[:5] == ("ip", "-4", "route", "show", "table"):
            return self.routes.get(args[5], "")
        if args[0] in ("iptables", "ip6tables") and args[1] == "-t":
            table, op, chain = args[2:]
            if op == "-S" and chain in ("FORWARD", "INPUT", "POSTROUTING", "PREROUTING"):
                return "-P %s ACCEPT\n" % chain
            if op == "-S":
                return ""
        return ""

    def check(self, *args):
        self.calls.append(("check", args))
        return True

    def write(self, *args):
        self.calls.append(("write", args))


class EngineTests(unittest.TestCase):
    def save_config(self, value):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "config.json"
        path.write_text(json.dumps(value))
        return str(path)

    def test_three_protocols_validate(self):
        validated = bridge.load_config(self.save_config(config()))
        self.assertEqual(3, len(validated["profiles"]))

    def test_explicit_lan_bypass_and_guard(self):
        conf = bridge.load_config(self.save_config(config()))
        result = bridge.chain_rules(conf, {"wgclt4": "0x6a0000/0x7e0000",
                                           "tunovpnc1": "0x6c0000/0x7e0000"})
        fw = result[("iptables", "filter", "FORWARD", "UVB_FWD")]
        self.assertIn(["-i", "tlprt0", "-s", "10.20.30.0/24", "-d",
                       "192.168.1.0/24", "-j", "RETURN"], fw)
        self.assertIn(["-i", "tlprt0", "-j", "DROP"], fw)
        self.assertIn(["-i", "wgsrv1", "-j", "DROP"], fw)
        self.assertIn(["-i", "tun0", "-j", "DROP"], fw)

    def test_no_mark_still_guards_forwarded_traffic(self):
        conf = bridge.load_config(self.save_config(config()))
        rules = bridge.chain_rules(conf, {})
        fw = rules[("iptables", "filter", "FORWARD", "UVB_FWD")]
        self.assertIn(["-i", "tlprt0", "-j", "DROP"], fw)
        self.assertIn(["-i", "tun0", "-j", "DROP"], fw)
        mark = rules[("iptables", "mangle", "PREROUTING", "UVB_MARK")]
        self.assertFalse(any("MARK" in item for args in mark for item in args))

    def test_ipv6_forward_block_all_ingress(self):
        conf = bridge.load_config(self.save_config(config()))
        rules = bridge.chain_rules(conf, {})
        v6 = rules[("ip6tables", "filter", "FORWARD", "UVB_FWD6")]
        self.assertEqual([["-i", p["ingress"], "-j", "DROP"] for p in conf["profiles"]], v6)

    def test_dns_redirect_ordinary_port_53(self):
        conf = bridge.load_config(self.save_config(config()))
        rules = bridge.chain_rules(conf, {"wgclt4": "0x6a0000/0x7e0000",
                                           "tunovpnc1": "0x6c0000/0x7e0000"})
        dnat = rules[("iptables", "nat", "PREROUTING", "UVB_DNS")]
        self.assertIn(["-i", "tlprt0", "-s", "10.20.30.0/24", "-p", "udp",
                       "--dport", "53", "-j", "DNAT", "--to-destination", "1.1.1.1"], dnat)
        self.assertIn(["-i", "tlprt0", "-s", "10.20.30.0/24", "-p", "tcp",
                       "--dport", "53", "-j", "DNAT", "--to-destination", "1.1.1.1"], dnat)

    def test_policy_mark_uniqueness(self):
        fake = ReadOnlyFake()
        found = bridge.policy_marks(fake, config()["profiles"])
        self.assertEqual("0x6a0000/0x7e0000", found["wgclt4"])
        self.assertEqual("0x6c0000/0x7e0000", found["tunovpnc1"])

    def test_policy_mark_ambiguity_rejected(self):
        fake = ReadOnlyFake(rules=("3000: from all fwmark 0x6a0000/0x7e0000 lookup 201.wgclt4\n"
                                   "3002: from all fwmark 0x6b0000/0x7e0000 lookup 201.wgclt4\n"))
        with self.assertRaises(bridge.BridgeError):
            bridge.policy_marks(fake, [config()["profiles"][0]])

    def test_scoped_route_not_used(self):
        fake = ReadOnlyFake(rules="3000: from all iif wgsrv1 fwmark 0x6a0000/0x7e0000 lookup 201.wgclt4\n")
        with self.assertRaises(bridge.BridgeError):
            bridge.policy_marks(fake, [config()["profiles"][0]])

    def test_duplicate_fields_rejected(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        file = Path(tmp.name) / "config.json"
        file.write_text('{"profiles":[],"profiles":[],"watch_interval":30}')
        with self.assertRaises(bridge.BridgeError):
            bridge.load_config(str(file))

    def test_overlapping_source_networks_rejected(self):
        c = config()
        c["profiles"][1]["source_cidr"] = "10.20.30.0/24"
        with self.assertRaises(bridge.BridgeError):
            bridge.load_config(self.save_config(c))

    def test_source_overlaps_lan_rejected(self):
        c = config()
        c["profiles"][0]["lan_cidrs"] = ["10.20.30.0/24"]
        with self.assertRaises(bridge.BridgeError):
            bridge.load_config(self.save_config(c))

    def test_private_dns_rejected(self):
        c = config()
        c["profiles"][0]["dns_ipv4"] = "192.168.1.1"
        with self.assertRaises(bridge.BridgeError):
            bridge.load_config(self.save_config(c))

    def test_invalid_egress_rejected(self):
        c = config()
        c["profiles"][0]["egress"] = "eth8"
        with self.assertRaises(bridge.BridgeError):
            bridge.load_config(self.save_config(c))

    def test_mutation_requires_experimental_flag(self):
        with self.assertRaises(bridge.BridgeError):
            bridge.main(["apply", "--config", self.save_config(config())])

    def test_fallback_before_firewall_mutations(self):
        fake = ReadOnlyFake()
        with mock.patch.object(bridge, "sync_chain") as sync, \
             mock.patch.object(bridge, "verify_runtime"), \
             mock.patch.object(bridge, "policy_marks", return_value={
                "wgclt4": "0x6a0000/0x7e0000", "tunovpnc1": "0x6c0000/0x7e0000"
             }):
            bridge.reconcile(fake, bridge.load_config(self.save_config(config())))
        writes = [args for action, args in fake.calls if action == "write"]
        self.assertTrue(writes)
        self.assertTrue(all(args[:4] == ("ip", "-4", "rule", "add") for args in writes))
        self.assertTrue(sync.called)

    def test_all_mutations_use_argv_not_shell(self):
        import inspect
        source = inspect.getsource(bridge.Runner)
        self.assertNotIn("shell=True", source)
        self.assertIn("subprocess.run(argv", source)


if __name__ == "__main__":
    unittest.main()
