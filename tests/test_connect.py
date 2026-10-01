"""Easy connect: pair links, SSH setup (no shell injection), LAN discovery and Tailscale peers."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from inky import connect
from inky.store import Store

URL = "https://raw.githubusercontent.com/GHGuide/inky/main/install.sh"


class PairLinkTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(connect.parse_pair_link("inky://pair?url=http%3A%2F%2F10.0.0.5%3A8800&code=AB12CD"), ("http://10.0.0.5:8800", "AB12CD"))
        self.assertEqual(connect.parse_pair_link(" inky://pair?url=http://srv.tail1.ts.net:8800&code=ab12cd "), ("http://srv.tail1.ts.net:8800", "AB12CD"))
        for bad in ("https://pair?url=http://x:8800&code=AB12CD", "inky://pair?url=file:///etc/passwd&code=AB12CD",
                    "inky://pair?url=http://x:8800", "inky://pair?url=http://x:8800&code=../../", "inky://install?url=http://x"):
            with self.assertRaises(ValueError, msg=bad):
                connect.parse_pair_link(bad)


class SSHTest(unittest.TestCase):
    def test_command(self):
        self.assertEqual(connect.ssh_command("leo@my-vps.example:2222", URL),
                         ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new", "-p", "2222", "leo@my-vps.example",
                          f"curl -fsSL '{URL}' | sh -s -- --json"])
        self.assertEqual(connect.ssh_command("10.0.0.5", URL)[-2], "10.0.0.5")
        for bad in ("leo@host name", "host;rm -rf ~", "$(whoami)@h", "`id`", "-oProxyCommand=evil", "h:99999", "h:22x", ""):
            with self.assertRaises(ValueError, msg=bad):
                connect.ssh_command(bad, URL)
        with self.assertRaises(ValueError):
            connect.ssh_command("h", "https://x/install.sh'; rm -rf ~; '")

    def test_output_parser(self):
        self.assertEqual(connect.parse_install_output('Getting Inky…\n{"url":"http://10.1.2.3:8800","code":"AB12CD"}\n'),
                         {"url": "http://10.1.2.3:8800", "code": "AB12CD"})
        with self.assertRaises(connect.SetupError) as e:
            connect.parse_install_output('{"error":"Python is older than 3.11","fix":"Install python3.11 or newer, or Docker"}')
        self.assertIn("3.11", e.exception.fix)

    def run_setup(self, result):
        home = tempfile.mkdtemp()
        E = SimpleNamespace(store=Store(os.path.join(home, "t.db")))
        steps = []
        fake = lambda cmd, on_line: (on_line("Getting Inky…"), result)[1]
        with mock.patch.object(connect.transfer, "pair", return_value=("remote-token", "vps")) as pair:
            try:
                cid = connect.ssh_setup(E, "leo@my-vps.example", lambda step, **kw: steps.append((step, kw)), run=fake, install_url=URL)
            except connect.SetupError as err:
                return E, steps, None, err, pair
        return E, steps, cid, None, pair

    def test_setup_pairs_using_the_ssh_host(self):
        E, steps, cid, err, pair = self.run_setup((0, '{"url":"http://10.1.2.3:8800","code":"AB12CD"}', ""))
        self.assertIsNone(err)
        pair.assert_called_once_with("http://my-vps.example:8800", "AB12CD")  # the private IP it printed may not be reachable
        self.assertEqual(E.store.get("computers", cid)["url"], "http://my-vps.example:8800")
        self.assertEqual([s for s, _ in steps][:2], ["connecting", "installing"])
        self.assertEqual(steps[-1][0], "done")

    def test_setup_explains_failures(self):
        cases = [((255, "", "leo@my-vps.example: Permission denied (publickey)."), "ssh-copy-id"),
                 ((255, "", "ssh: connect to host my-vps.example port 22: Operation timed out"), "reach"),
                 ((127, "", "sh: 1: curl: not found"), "curl"),
                 ((1, '{"error":"this computer runs FreeBSD","fix":"The installer is for Linux or macOS."}', ""), "Linux or macOS")]
        for result, hint in cases:
            _, _, _, err, _ = self.run_setup(result)
            self.assertIsNotNone(err, result)
            self.assertIn(hint, err.fix + err.args[0], result)


class LanTest(unittest.TestCase):
    def test_beacon_round_trip_and_no_secrets(self):
        pkt = connect.beacon_packet("Leo’s server", 8800, "0.1.0")
        self.assertNotIn(b"code", pkt)
        self.assertNotIn(b"token", pkt)
        info = connect.parse_beacon(pkt)
        self.assertEqual((info["name"], info["port"], info["version"]), ("Leo’s server", 8800, "0.1.0"))
        self.assertIsNone(connect.parse_beacon(b"hello"))
        self.assertIsNone(connect.parse_beacon(json.dumps({"inky": 1, "name": "x", "port": "80; rm"}).encode()))

    def test_listener_dedups_expires_and_ignores_itself(self):
        L = connect.Listener(own_port=8800, own_ips={"192.168.1.9"})
        pkt = connect.beacon_packet("vps", 8800, "0.1.0")
        L.seen(pkt, ("192.168.1.20", 48800), now=100)
        L.seen(pkt, ("192.168.1.20", 48800), now=103)
        L.seen(pkt, ("192.168.1.9", 48800), now=103)  # this computer's own beacon
        L.seen(connect.beacon_packet("pi", 8801, "0.1.0"), ("192.168.1.30", 48800), now=90)
        found = L.found(now=125)
        self.assertEqual([f["url"] for f in found], ["http://192.168.1.20:8800"])  # the pi went quiet 35 s ago
        self.assertEqual(found[0]["via"], "lan")


class TailscaleTest(unittest.TestCase):
    def test_peers_that_answer(self):
        status = {"Self": {"TailscaleIPs": ["100.64.0.1"]}, "Peer": {
            "a": {"HostName": "vps", "DNSName": "vps.tail1.ts.net.", "TailscaleIPs": ["100.64.0.2", "fd7a::2"], "Online": True},
            "b": {"HostName": "phone", "DNSName": "phone.tail1.ts.net.", "TailscaleIPs": ["100.64.0.3"], "Online": True},
            "c": {"HostName": "old", "DNSName": "old.tail1.ts.net.", "TailscaleIPs": ["100.64.0.4"], "Online": False}}}
        probed = []
        probe = lambda url: (probed.append(url), {"ok": True, "name": "VPS"} if "100.64.0.2" in url else None)[1]
        peers = connect.tailnet_peers(status, probe=probe)
        self.assertEqual(peers, [{"name": "VPS", "url": "http://100.64.0.2:8800", "via": "tailscale", "host": "vps.tail1.ts.net", "os": None, "id": None}])
        self.assertNotIn("http://100.64.0.4:8800/api/ping", probed)  # offline peers aren't probed


if __name__ == "__main__":
    unittest.main()
