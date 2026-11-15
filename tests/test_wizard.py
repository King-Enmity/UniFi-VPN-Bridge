"""Offline tests for optional read-only setup wizard."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WIZARD = Path(__file__).resolve().parents[1] / "scripts" / "setup-wizard.sh"
STUB = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SSH_LOG"
case "$*" in
  *'ip -o link show') printf '7: tlprt0: <POINTOPOINT>\\n8: wgclt4: <POINTOPOINT>\\n' ;;
  *'bash -s -- doctor'*)
    cat >/dev/null
    printf 'RESULT: DISCOVERY ONLY (no changes made)\\n' ;;
  *) exit 90 ;;
esac
'''

class WizardTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        root = Path(self.work.name)
        ssh = root / "ssh"
        ssh.write_text(STUB)
        ssh.chmod(0o755)
        self.log = root / "ssh.log"
        self.env = dict(os.environ,
                        PATH=str(root) + os.pathsep + os.environ.get("PATH", ""),
                        SSH_LOG=str(self.log))

    def run_wizard(self, *args):
        return subprocess.run(["bash", str(WIZARD), *args],
                              capture_output=True, text=True,
                              env=self.env, timeout=10)

    def test_help_never_calls_ssh(self):
        result = self.run_wizard("--help")
        self.assertEqual(0, result.returncode)
        self.assertIn("READ ONLY", result.stdout)
        self.assertFalse(self.log.exists())

    def test_list_only(self):
        result = self.run_wizard("--host", "root@192.168.1.1", "--list-only")
        self.assertEqual(0, result.returncode, result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(1, len(calls))
        self.assertIn("ip -o link show", calls[0])

    def test_three_vpn_types(self):
        result = self.run_wizard("--host", "root@gateway.local",
                                 "--route", "teleport:tlprt0:tunovpnc1",
                                 "--route", "wireguard:wgsrv1:wgclt4",
                                 "--route", "openvpn:tun0:wgclt4")
        self.assertEqual(0, result.returncode, result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(2, len(calls))
        self.assertIn("bash -s -- doctor", calls[1])
        for route in ("teleport:tlprt0:tunovpnc1", "wireguard:wgsrv1:wgclt4", "openvpn:tun0:wgclt4"):
            self.assertIn("--route " + route, calls[1])

    def test_rejects_injection(self):
        result = self.run_wizard("--host", "root@192.168.1.1",
                                 "--route", "teleport:tlprt0:wgclt4;id")
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.log.exists())

    def test_rejects_ssh_option(self):
        result = self.run_wizard("--host", "-oProxyCommand=evil", "--list-only")
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.log.exists())

    def test_rejects_duplicate_source(self):
        result = self.run_wizard("--host", "root@gateway.local",
                                 "--route", "teleport:tlprt0:tunovpnc1",
                                 "--route", "wireguard:tlprt0:wgclt4")
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.log.exists())

    def test_requires_route_for_unattended_mode(self):
        result = self.run_wizard("--host", "root@192.168.1.1")
        self.assertEqual(2, result.returncode)
        self.assertIn("--route", result.stderr)
        self.assertEqual(1, len(self.log.read_text().splitlines()))

if __name__ == "__main__":
    unittest.main()
