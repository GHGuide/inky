"""MCP over stdio: newline-delimited JSON-RPC 2.0.
MCPClient talks to any MCP server (Claude Code: `claude mcp serve`; Codex: `python -m inky.codex_mcp`).
serve_stdio() turns a dict of tools into an MCP server (used by inky.mcp_server and inky.codex_mcp)."""
import concurrent.futures
import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
import time

PROTOCOL = "2025-06-18"

PRESETS = {
    "claude-code": {"label": "Claude Code", "command": ["claude", "mcp", "serve"],
                    "about": "Hand a job to Claude Code: its Agent, Bash, Read, Write, WebFetch and more."},
    "codex": {"label": "Codex", "command": [sys.executable, "-m", "inky.codex_mcp"],
              "about": "Hand a job to Codex (runs `codex exec`, read-only unless you allow writes)."},
}


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, command, env=None, cwd=None, log=None):
        self.command, self.env, self.cwd, self.log = command, env or {}, cwd, log
        self.proc = None
        self.pending = {}
        self.ids = itertools.count(1)
        self.lock = threading.Lock()
        self.server_info = None

    def start(self, timeout=30):
        exe = self.command[0]
        if not (os.path.isabs(exe) or shutil.which(exe)):
            raise MCPError(f"“{exe}” is not installed on this computer")
        errf = open(self.log, "ab") if self.log else subprocess.DEVNULL
        cmd = [shutil.which(exe) or exe, *self.command[1:]]  # Windows: npm installs `claude` as claude.cmd
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errf,
                                     env={**os.environ, **self.env}, cwd=self.cwd)
        threading.Thread(target=self._reader, daemon=True).start()
        r = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                        "clientInfo": {"name": "inky", "version": "0.1"}}, timeout=timeout)
        self.server_info = r.get("serverInfo")
        self.notify("notifications/initialized")
        return r

    def _reader(self):
        for raw in self.proc.stdout:
            try:
                m = json.loads(raw)
            except Exception:
                continue
            if "id" in m and ("result" in m or "error" in m):
                fut = self.pending.pop(m["id"], None)
                if fut:
                    if "error" in m:
                        fut.set_exception(MCPError(m["error"].get("message", "error")))
                    else:
                        fut.set_result(m["result"])
            elif "id" in m and "method" in m:  # server -> client request (roots, sampling…): we offer none
                result = {"roots": []} if m["method"] == "roots/list" else None
                reply = {"jsonrpc": "2.0", "id": m["id"]}
                reply.update({"result": result} if result is not None else {"error": {"code": -32601, "message": "not supported"}})
                self._write(reply)
        for fut in list(self.pending.values()):
            fut.set_exception(MCPError("the server stopped"))
        self.pending.clear()

    def _write(self, msg):
        with self.lock:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            self.proc.stdin.flush()

    def request(self, method, params=None, timeout=60):
        if not self.alive():
            raise MCPError("not connected")
        i = next(self.ids)
        fut = concurrent.futures.Future()
        self.pending[i] = fut
        self._write({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}})
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            self.pending.pop(i, None)
            raise MCPError(f"{method} took longer than {timeout} s")

    def notify(self, method, params=None):
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def tools(self):
        return self.request("tools/list").get("tools", [])

    def call(self, name, arguments=None, timeout=900):
        r = self.request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
        text = "\n".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        return {"text": text, "error": bool(r.get("isError")), "raw": r}

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def close(self):
        if self.proc and self.alive():
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class MCPManager:
    """Connected servers, configured in the store's `mcp` table (key = server name)."""

    def __init__(self, store, home):
        self.store, self.home = store, home
        self.clients, self.tools_cache = {}, {}
        self.lock = threading.Lock()

    def servers(self):
        saved = {r["key"]: r for r in self.store.find("mcp")}
        out = []
        for name, p in PRESETS.items():
            r = saved.pop(name, None) or {}
            out.append(self._view(name, r.get("command") or p["command"], p["label"], p["about"], r.get("enabled", False), True, r.get("env")))
        for name, r in saved.items():
            out.append(self._view(name, r["command"], r.get("label") or name, r.get("about", ""), r.get("enabled", True), False, r.get("env")))
        return out

    def _view(self, name, command, label, about, enabled, preset, env):
        c = self.clients.get(name)
        return {"name": name, "label": label, "about": about, "command": command, "enabled": enabled, "preset": preset,
                "installed": bool(shutil.which(command[0]) or os.path.isabs(command[0])),
                "connected": bool(c and c.alive()), "tools": [t["name"] for t in self.tools_cache.get(name, [])],
                "env_keys": sorted((env or {}).keys())}

    def save(self, name, command=None, enabled=True, label=None, env=None):
        rows = self.store.find("mcp", key=name)
        data = {"enabled": enabled}
        if command:
            data["command"] = command
        if label:
            data["label"] = label
        if env is not None:
            data["env"] = env
        if rows:
            self.store.update("mcp", rows[0]["id"], **data)
        else:
            self.store.insert("mcp", data, key=name)
        if not enabled:
            self.disconnect(name)

    def remove(self, name):
        for r in self.store.find("mcp", key=name):
            self.store.delete("mcp", r["id"])
        self.disconnect(name)

    def _config(self, name):
        s = next((s for s in self.servers() if s["name"] == name), None)
        if not s:
            raise MCPError(f"no connector called {name}")
        rows = self.store.find("mcp", key=name)
        return s, (rows[0].get("env") if rows else None) or {}

    def connect(self, name):
        with self.lock:
            c = self.clients.get(name)
            if c and c.alive():
                return c
            s, env = self._config(name)
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # so `python -m inky.…` works from any folder
            env = {"PYTHONPATH": os.pathsep.join(filter(None, [root, os.environ.get("PYTHONPATH")])), **env}
            c = MCPClient(s["command"], env=env, cwd=os.path.expanduser("~"), log=os.path.join(self.home, f"mcp-{name}.log"))
            c.start()
            self.clients[name] = c
            self.tools_cache[name] = c.tools()
            return c

    def disconnect(self, name):
        c = self.clients.pop(name, None)
        if c:
            c.close()

    def tools(self, name):
        self.connect(name)
        return self.tools_cache.get(name, [])

    def call(self, name, tool, args, timeout=900):
        return self.connect(name).call(tool, args, timeout=timeout)

    def catalog(self):
        """Short tool list of enabled, connected servers, for the chat model."""
        out = []
        for s in self.servers():
            if s["enabled"]:
                for t in self.tools_cache.get(s["name"], []):
                    props = list((t.get("inputSchema") or {}).get("properties", {}).keys())
                    out.append(f"{s['name']}.{t['name']}({', '.join(props)}): {(t.get('description') or '')[:140]}")
        return out

    def close(self):
        for n in list(self.clients):
            self.disconnect(n)


# ---------------------------------------------------------------- a minimal stdio MCP server


def serve_stdio(name, version, tools):
    """tools: {tool_name: (description, input_schema, fn(args) -> str[, annotations])}"""
    out = sys.stdout
    sys.stdout = sys.stderr  # nothing but protocol on the real stdout

    def send(m):
        out.write(json.dumps(m) + "\n")
        out.flush()

    for raw in sys.stdin:
        try:
            m = json.loads(raw)
        except Exception:
            continue
        method, mid = m.get("method"), m.get("id")
        if mid is None:
            continue  # notification
        try:
            if method == "initialize":
                res = {"protocolVersion": (m.get("params") or {}).get("protocolVersion", PROTOCOL),
                       "capabilities": {"tools": {}}, "serverInfo": {"name": name, "version": version}}
            elif method == "ping":
                res = {}
            elif method == "tools/list":
                res = {"tools": [dict({"name": k, "description": v[0], "inputSchema": v[1]}, **({"annotations": v[3]} if len(v) > 3 else {}))
                                 for k, v in tools.items()]}
            elif method == "tools/call":
                p = m.get("params") or {}
                if p.get("name") not in tools:
                    raise KeyError(f"unknown tool {p.get('name')}")
                t0 = time.time()
                try:
                    text, err = tools[p["name"]][2](p.get("arguments") or {}), False  # (desc, schema, fn[, annotations])
                except Exception as e:
                    text, err = f"Error: {e}", True
                res = {"content": [{"type": "text", "text": text if isinstance(text, str) else json.dumps(text)}],
                       "isError": err, "_meta": {"seconds": round(time.time() - t0, 2)}}
            else:
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"{method} not supported"}})
                continue
            send({"jsonrpc": "2.0", "id": mid, "result": res})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})
