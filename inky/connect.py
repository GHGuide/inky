"""Easy connect: pair links (inky://pair?url=…&code=…), setting a server up over SSH, and finding Inky on your
network (a UDP beacon with no secrets in it) and on your tailnet (Tailscale). Pairing always needs the code."""
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import httpx

from inky import transfer

INSTALL_URL = os.environ.get("INKY_INSTALL_URL", "https://raw.githubusercontent.com/GHGuide/inky/main/install.sh")
BEACON_PORT = 48800
CODE = re.compile(r"^[A-Z0-9]{4,12}$")
TARGET = re.compile(r"^(?:([A-Za-z0-9._][A-Za-z0-9._-]*)@)?([A-Za-z0-9][A-Za-z0-9.-]*|\[[0-9A-Fa-f:]+\])(?::(\d{1,5}))?$")  # [::1] for IPv6


class SetupError(Exception):
    def __init__(self, msg, fix=""):
        super().__init__(msg)
        self.fix = fix


# ---------------------------------------------------------------- pair links
def parse_pair_link(link):
    u = urlsplit((link or "").strip())
    if u.scheme != "inky" or u.netloc != "pair":
        raise ValueError("That isn’t an Inky pair link (inky://pair?…).")
    q = parse_qs(u.query)
    url, code = (q.get("url") or [""])[0].strip(), (q.get("code") or [""])[0].strip().upper()
    t = urlsplit(url)
    if t.scheme not in ("http", "https") or not t.hostname:
        raise ValueError("The link has no server address.")
    if not CODE.match(code):
        raise ValueError("The link has no pairing code.")
    return url.rstrip("/"), code


def pair_and_save(E, url, code):
    try:
        eid = httpx.get(url.rstrip("/") + "/api/ping", timeout=8).json().get("id")
    except (httpx.HTTPError, ValueError):
        eid = None
    if eid and eid == transfer.engine_id(E):
        raise ValueError("That’s this computer. Pair another one.")
    token, name = transfer.pair(url, code, me=E.store.setting("engine_name", None) or __import__("platform").node())
    for c in E.store.find("computers"):
        if (eid and c.get("engine_id") == eid) or c.get("token") == token:  # the same server again (maybe by another address): refresh it
            E.store.update("computers", c["id"], url=url.rstrip("/"), name=name, engine_id=eid, token=token)
            return c["id"]
    return E.store.insert("computers", {"name": name, "url": url.rstrip("/"), "token": token, "engine_id": eid})


# ---------------------------------------------------------------- SSH setup
def split_target(target):
    m = TARGET.match((target or "").strip())
    if not m:
        raise ValueError("Use user@host, or user@host:port.")
    user, host, port = m.groups()
    host = host.strip("[]")  # ssh takes an IPv6 address as it is, with the port given apart
    if port and not 0 < int(port) < 65536:
        raise ValueError("That port isn’t valid.")
    return user, host, port


def ssh_command(target, install_url=INSTALL_URL):
    """argv only, no local shell. The host is validated, the URL too, so nothing can be injected on either side."""
    user, host, port = split_target(target)
    if not re.match(r"^https?://[A-Za-z0-9._~:/-]+$", install_url):
        raise ValueError("bad install address")
    # accept-new: a server you've never connected to is trusted on first use; a changed key is still refused
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"] + (["-p", port] if port else [])
    return cmd + [f"{user}@{host}" if user else host, f"curl -fsSL '{install_url}' | sh -s -- --json"]


def parse_install_output(out):
    line = next((ln for ln in reversed((out or "").strip().splitlines()) if ln.strip().startswith("{")), None)
    if not line:
        raise SetupError("The installer didn’t say where Inky runs", (out or "").strip()[-300:])
    d = json.loads(line)
    if d.get("error"):
        raise SetupError(d["error"][:1].upper() + d["error"][1:], d.get("fix", ""))
    if not d.get("url") or not d.get("code"):
        raise SetupError("The installer didn’t give an address and code")
    return d


def explain(target, host, err):
    e = err or ""
    if "Permission denied" in e:
        return SetupError("The server didn’t accept your SSH key", f"Add your key to it once, in a terminal: ssh-copy-id {target}")
    if "Host key verification failed" in e:
        return SetupError("This computer hasn’t met the server yet", f"Connect once in a terminal to confirm it: ssh {target}")
    if "Could not resolve hostname" in e:
        return SetupError(f"Couldn’t find {host}", "Check the name, or use its IP address.")
    if re.search(r"timed out|Connection refused|No route to host|Network is unreachable", e):
        return SetupError(f"Couldn’t reach {host} over SSH", "Check the address and that SSH is on (port 22, or add :port).")
    if re.search(r"curl: (command )?not found|curl: not found", e):
        return SetupError("The server has no curl", "Install it there: sudo apt install -y curl")
    return SetupError("Setting up over SSH failed", e.strip()[-300:])


def _run(cmd, on_line):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
    err = []

    def pump():
        for ln in p.stderr:
            err.append(ln)
            on_line(ln.strip())
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    out = p.stdout.read()
    p.wait(timeout=1800)
    t.join(2)
    return p.returncode, out, "".join(err)


def ssh_setup(E, target, progress, run=None, install_url=INSTALL_URL):
    """Install Inky on a server you can ssh into, then pair with it. progress(step, text=…) for each step."""
    cmd = ssh_command(target, install_url)
    _, host, _ = split_target(target)
    if run is None and not shutil.which("ssh"):
        raise SetupError("This computer has no ssh", "Install OpenSSH, or run the one-line install on the server yourself.")
    progress("connecting", text=f"Connecting to {host}…")
    begun = []

    def line(text):
        if re.match(r"ssh:|.*(Permission denied|Host key verification|Could not resolve)", text):
            return  # ssh's own complaints: explain() turns them into a message and a fix
        if not begun:
            begun.append(1)
            progress("installing", text="Installing Inky on the server. The first time takes a few minutes.")
        if text.startswith("Warning: Permanently added"):
            text = "First time connecting to this server: its key is remembered from now on."
        if text:
            progress("installing", text=text)
    code, out, err = (run or _run)(cmd, line)
    if code != 0 and not (out or "").strip().startswith("{"):
        raise explain(target, host, err)
    info = parse_install_output(out)
    port = urlsplit(info["url"]).port or 8800
    url = f"http://{host}:{port}"  # the address you ssh'd to; the one it printed may be a private IP you can't reach
    progress("pairing", text=f"Pairing with {url}…")
    try:
        cid = pair_and_save(E, url, info["code"])
    except httpx.RequestError:
        raise SetupError(f"Inky runs on {host}, but this computer can’t reach port {port}",
                         f"Open port {port} on the server’s firewall (for example: sudo ufw allow {port}/tcp), or use Tailscale.")
    progress("done", text=f"Paired with {E.store.get('computers', cid)['name']}. Its bots show up in Computers.", id=cid)
    return cid


# ---------------------------------------------------------------- LAN discovery
def beacon_packet(name, port, version, eid=None):
    import platform
    d = {"inky": 1, "name": str(name)[:60], "port": int(port), "version": version, "os": platform.system()}
    if eid:
        d["id"] = eid  # who it is (a hash, no secret), so a server you paired by another address isn't offered again
    return json.dumps(d, ensure_ascii=False).encode()


def parse_beacon(data):
    try:
        d = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(d, dict) or d.get("inky") != 1 or not isinstance(d.get("port"), int) or not 0 < d["port"] < 65536:
        return None
    eid = d.get("id") if isinstance(d.get("id"), str) and re.match(r"^[0-9a-f]{16}$", d.get("id")) else None
    os_ = d.get("os") if d.get("os") in ("Darwin", "Linux", "Windows") else None
    return {"name": str(d.get("name") or "Inky")[:60], "port": d["port"], "version": str(d.get("version") or "")[:20], "id": eid, "os": os_}


def local_ips():
    """This computer's address on the network. (Not by looking up its own name: on macOS that's a multicast-DNS
    lookup that can hang for 30 s the first time an app touches the local network.)"""
    ips = {"127.0.0.1"}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet is sent; this only picks the outgoing interface
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return ips


class Listener:
    """Hears beacons from Inky engines on your network. Entries go stale after 30 s of silence."""
    TTL = 30

    def __init__(self, own_port=None, own_ips=()):
        self.own_port, self.own_ips = own_port, set(own_ips) | {"127.0.0.1"}
        self.peers = {}

    def seen(self, data, addr, now=None):
        info = parse_beacon(data)
        if not info or (addr[0] in self.own_ips and info["port"] == self.own_port):
            return
        url = f"http://{addr[0]}:{info['port']}"  # where it came from, not what it says
        self.peers[url] = {**info, "url": url, "via": "lan", "at": now or time.time()}

    def found(self, now=None):
        now = now or time.time()
        return [{k: v for k, v in p.items() if k != "at"} for p in list(self.peers.values()) if now - p["at"] <= self.TTL]

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(("", BEACON_PORT))

        def loop():
            while True:
                try:
                    data, addr = s.recvfrom(2048)
                    self.seen(data, addr)
                except OSError:
                    time.sleep(1)
        threading.Thread(target=loop, daemon=True, name="lan-listener").start()


def start_beacon(name_fn, port, version, eid=None):
    """An engine that listens on your network says so every 5 s. No code, no token: pairing still needs the code.
    Returns an Event: set it to stop. ponytail: a Docker install's beacon stays inside Docker's network;
    the SSH setup and pair link cover those."""
    stop = threading.Event()

    def loop():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not stop.is_set():
            try:
                s.sendto(beacon_packet(name_fn(), port, version, eid), ("255.255.255.255", BEACON_PORT))
            except OSError:
                pass
            stop.wait(5)
    threading.Thread(target=loop, daemon=True, name="lan-beacon").start()
    return stop


def lan_ip():
    return next((ip for ip in local_ips() if not ip.startswith("127.")), None)


# ---------------------------------------------------------------- Tailscale
def _ping(url):
    try:
        r = httpx.get(url, timeout=1)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def tailscale_status():
    exe = shutil.which("tailscale") or next((p for p in ("/Applications/Tailscale.app/Contents/MacOS/Tailscale",) if os.path.exists(p)), None)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
        return json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def tailnet_peers(status, probe=_ping, port=8800):
    """Online peers on your tailnet that answer Inky's ping. Their Tailscale address works away from home too."""
    mine = set((status.get("Self") or {}).get("TailscaleIPs") or [])
    cands = [(p, ip) for p in (status.get("Peer") or {}).values() if p.get("Online")
             for ip in [next((i for i in p.get("TailscaleIPs") or [] if "." in i), None)] if ip and ip not in mine]

    def check(c):
        p, ip = c
        r = probe(f"http://{ip}:{port}/api/ping")
        if r and r.get("ok"):
            return {"name": r.get("name") or p.get("HostName"), "url": f"http://{ip}:{port}", "via": "tailscale",
                    "host": (p.get("DNSName") or "").rstrip("."), "os": r.get("os"), "id": r.get("id")}
    with ThreadPoolExecutor(8) as ex:
        return [x for x in ex.map(check, cands) if x]


# ---------------------------------------------------------------- what the Computers page lists
_state = {"listener": None, "ts_at": 0, "ts": [], "ts_busy": False}


def found(E):
    """Inky engines on your network and tailnet that you haven't paired yet. Listening starts the first time you look."""
    if _state["listener"] is None:
        L = Listener(own_port=getattr(E, "port", None), own_ips=local_ips())
        try:
            L.start()
        except OSError:
            pass  # another engine on this computer holds the port without sharing it; LAN discovery stays off here
        _state["listener"] = L
    if time.time() - _state["ts_at"] > 30 and not _state["ts_busy"]:
        _state["ts_busy"] = True

        def refresh():
            try:
                st = tailscale_status()
                _state["ts"] = tailnet_peers(st) if st else []
            finally:
                _state["ts_at"], _state["ts_busy"] = time.time(), False
        threading.Thread(target=refresh, daemon=True).start()
    comps = E.store.find("computers")
    paired, ids = {c["url"].rstrip("/") for c in comps}, {c.get("engine_id") for c in comps if c.get("engine_id")}
    seen, out = set(), []
    for f in _state["listener"].found() + _state["ts"]:
        if f["url"] not in paired and f["url"] not in seen and not (f.get("id") and f["id"] in ids):
            seen.add(f["url"])
            out.append(f)
    return out
