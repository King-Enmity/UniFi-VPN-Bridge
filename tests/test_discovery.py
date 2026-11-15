"""Offline tests for the read-only UniFi VPN Bridge discovery CLI."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "bin" / "unifi-vpn-bridge"
IP_STUB = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$IP_CALLS"
case "$*" in
  '-o link show dev '*)
    case "${5:-}" in
      tlprt0|wgsrv1|tun0|tunovpnc1|wgclt4) exit 0 ;;
      *) exit 1 ;;
    esac ;;
  '-4 rule show')
    case "$SCENARIO" in
      missing) printf '0: from all lookup local\n' ;;
      ambiguous)
        printf '3000: from all fwmark 0x6a0000/0x7e0000 lookup 178.tunovpnc1\n'
        printf '3001: from all fwmark 0x6b0000/0x7e0000 lookup 179.tunovpnc1\n' ;;
      scoped) printf '3000: from all iif tlprt0 fwmark 0x6a0000/0x7e0000 lookup 178.tunovpnc1\n' ;;
      *)
        printf '3000: from all fwmark 0x6a0000/0x7e0000 lookup 178.tunovpnc1\n'
        printf '3001: from all fwmark 0x6c0000/0x7e0000 lookup 180.wgclt4\n' ;;
    esac
    exit 0 ;;
  '-4 route show table '*)
    case "${5:-}" in
      178.tunovpnc1|179.tunovpnc1) printf 'default dev tunovpnc1 scope link\n' ;;
      180.wgclt4) printf 'default dev wgclt4 scope link\n' ;;
      *) exit 1 ;;
    esac
    exit 0 ;;
  '-4 route get '*)
    printf '1.1.1.1 dev tunovpnc1 table 178.tunovpnc1 src 10.0.0.2\n'
    exit 0 ;;
esac
exit 1
'''

class OfflineDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        stub = root / "ip"
        stub.write_text(IP_STUB)
        stub.chmod(0o755)
        self.calls = root / "calls"
        self.env = dict(os.environ, PATH=self.tmp.name + os.pathsep + os.environ.get("PATH", ""),
                        SCENARIO="good", IP_CALLS=str(self.calls))

    def run_cli(self, *args, scenario="good"):
        env = dict(self.env, SCENARIO=scenario)
        return subprocess.run(["bash", str(TOOL), *args], env=env, text=True,
                              capture_output=True, timeout=8)

    def test_version(self):
        self.assertEqual("0.2.0", self.run_cli("--version").stdout.strip())

    def test_multi_protocol_shared_exit(self):
        result = self.run_cli("doctor", "--ingress", "teleport:tlprt0",
                              "--ingress", "wireguard:wgsrv1",
                              "--ingress", "openvpn:tun0", "--egress", "tunovpnc1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, result.stdout.count("Candidate IPv4 mark"))
        self.assertIn("SECURITY STATUS: NOT PROTECTED", result.stdout)

    def test_multi_protocol_separate_exits(self):
        result = self.run_cli("doctor", "--route", "teleport:tlprt0:tunovpnc1",
                              "--route", "wireguard:wgsrv1:wgclt4",
                              "--route", "openvpn:tun0:wgclt4")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("table 180.wgclt4", result.stdout)

    def test_missing_interface_fails(self):
        result = self.run_cli("doctor", "--ingress", "openvpn:missing0",
                              "--egress", "wgclt4")
        self.assertEqual(2, result.returncode)
        self.assertIn("not found", result.stderr)

    def test_ambiguous_route_fails(self):
        result = self.run_cli("doctor", "--route", "teleport:tlprt0:tunovpnc1",
                              scenario="ambiguous")
        self.assertEqual(3, result.returncode)
        self.assertIn("AMBIGUOUS", result.stdout)

    def test_missing_route_fails(self):
        result = self.run_cli("doctor", "--route", "teleport:tlprt0:tunovpnc1",
                              scenario="missing")
        self.assertEqual(3, result.returncode)

    def test_scoped_route_fails(self):
        result = self.run_cli("doctor", "--route", "teleport:tlprt0:tunovpnc1",
                              scenario="scoped")
        self.assertEqual(3, result.returncode)

    def test_shell_input_rejected_without_commands(self):
        result = self.run_cli("doctor", "--route",
                              "teleport:tlprt0:tunovpnc1;id")
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.calls.exists())

    def test_duplicate_ingress_rejected(self):
        result = self.run_cli("doctor", "--ingress", "teleport:tlprt0",
                              "--ingress", "wireguard:tlprt0",
                              "--egress", "wgclt4")
        self.assertEqual(2, result.returncode)

    def test_plan_never_mutates_firewall(self):
        result = self.run_cli("plan", "--route", "teleport:tlprt0:tunovpnc1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("NOT EXECUTED", result.stdout)
        calls = self.calls.read_text().splitlines()
        self.assertTrue(calls)
        self.assertTrue(all(c.startswith(("-o link show dev", "-4 rule show",
                                           "-4 route show table", "-4 route get"))
                            for c in calls))

if __name__ == "__main__":
    unittest.main()
