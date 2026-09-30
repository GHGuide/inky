"""The shared agent library on GitHub: anyone can post a bot, and everyone can get it.
Each agent is one file, library/agents/<slug>.inky: a shared bundle (no sign-ins, memory, results or chat) with a
"listing". CI checks every pull request with check() and rebuilds library/index.json on main; the app reads that index.
Posting goes through gh (a pull request) or GitHub's new-file page. Nothing leaves this computer before check()
passes, and you see exactly what becomes public.
    python -m inky.library check <file.inky>...     python -m inky.library index <library dir>"""
import base64
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from inky import transfer
from inky.safety import IRREVERSIBLE, PAY, _has

REPO = "GHGuide/inky"
INDEX_URL = os.environ.get("INKY_LIBRARY_URL", f"https://raw.githubusercontent.com/{REPO}/main/library/index.json")
BUNDLED = Path(__file__).resolve().parents[1] / "library"  # starters that ship with the app
MAX_BYTES = 512_000
SECRETS = [
    (r"sk-(?:or-v1-|ant-|proj-)?[A-Za-z0-9_-]{20,}", "an API key"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", "a GitHub token"),
    (r"xox[abprs]-[A-Za-z0-9-]{10,}", "a Slack token"),
    (r"AKIA[0-9A-Z]{16}", "an AWS key"),
    (r"AIza[0-9A-Za-z_-]{35}", "a Google API key"),
    (r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}", "a Telegram bot token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "a private key"),
    (r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "a login token"),
]
SECRET_KEYS = re.compile(r"^(password|passwd|pass|secret|api_?key|token|access_token|auth)$", re.I)
PASSWORD_FIELD = re.compile(r"password|passwort|contrase|mot de passe|hasło|wachtwoord", re.I)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:48] or "agent"


def host_of(url):
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _strings(x, key=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _strings(v, k)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v, key)
    elif isinstance(x, str):
        yield key, x


def check(b):
    """-> {ok, problems, domains, irreversible}. The same rules run here before posting and in CI on every pull request."""
    problems = []
    if not isinstance(b, dict) or b.get("bundle") != transfer.BUNDLE or not isinstance(b.get("bot"), dict):
        return {"ok": False, "problems": ["This isn’t an Inky bot file."], "domains": [], "irreversible": []}
    if len(json.dumps(b)) > MAX_BYTES:
        problems.append("The file is too big for the library (over 500 KB).")
    bot = b["bot"]
    for what, has in (("sign-ins (cookies)", b.get("cookies") or bot.get("pending_cookies")), ("memory", bot.get("memory")),
                      ("results", b.get("results")), ("chat messages", b.get("messages"))):
        if has:
            problems.append(f"It carries your {what}. Shared agents never do.")
    for key, s in _strings(b):
        for rx, name in SECRETS:
            if re.search(rx, s):
                problems.append(f"It contains what looks like {name}.")
        if SECRET_KEYS.match(key) and s.strip():
            problems.append(f"It has a “{key}” value.")
    domains, irreversible = set(), []
    if bot.get("start_url"):
        domains.add(host_of(bot["start_url"]))
    for sk in b.get("skills") or []:
        for u in (sk.get("start_url"), "https://" + sk["site"] if sk.get("site") else None):
            if u:
                domains.add(host_of(u))
        for st in sk.get("steps") or []:
            t = st.get("target") or {}
            if st.get("action") == "goto" and st.get("value"):
                domains.add(host_of(st["value"]))
            if st.get("action") in ("fill", "type") and st.get("value") and (t.get("type") == "password" or PASSWORD_FIELD.search(t.get("name") or "")):
                problems.append(f"It types a password into “{t.get('name') or 'a password field'}”.")
            label = f"{st.get('text') or ''} {t.get('name') or ''}"
            if st.get("approved_always") or (st.get("action") in ("click", "press") and _has(IRREVERSIBLE + PAY, label)):
                irreversible.append(f"{sk.get('name') or 'Skill'}: {st.get('text') or t.get('name')}")
    for a in bot.get("automations") or []:
        irreversible.append(f"Hands work to {a.get('server')}: {a.get('label') or a.get('tool')}")
    return {"ok": not problems, "problems": list(dict.fromkeys(problems)), "domains": sorted(d for d in domains if d), "irreversible": irreversible}


def listing(b, meta=None):
    meta, bot = meta or {}, b["bot"]
    c = check(b)
    title = (meta.get("title") or bot.get("name") or "Agent").strip()[:60]
    return {"slug": slugify(meta.get("slug") or title), "title": title,
            "summary": (meta.get("summary") or bot.get("summary") or bot.get("goal") or "").strip()[:200],
            "tags": [slugify(t) for t in meta.get("tags") or []][:6], "author": (meta.get("author") or "").strip()[:39],
            "look": bot.get("look") or {}, "sites": c["domains"], "may": [x.split(": ", 1)[-1] for x in c["irreversible"]][:6],
            "version": int(meta.get("version") or 1), "skills": len(b.get("skills") or [])}


def build_index(root):
    agents = []
    for p in sorted(Path(root, "agents").glob("*.inky")):
        b = json.loads(p.read_text(encoding="utf-8"))
        c = check(b)
        if not c["ok"]:
            continue
        agents.append({**(b.get("listing") or listing(b)), "sites": c["domains"], "may": [x.split(": ", 1)[-1] for x in c["irreversible"]][:6],
                       "file": f"agents/{p.name}", "reviewed": True})
    agents.sort(key=lambda a: a["title"].lower())
    return {"agents": agents, "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}


# ---------------------------------------------------------------- getting an agent
_cache = {"at": 0, "data": None}


def index():
    """The public index (cached 10 min), plus the starters that ship with the app. url is where each file is."""
    if time.time() - _cache["at"] > 600 or _cache["data"] is None:
        remote, err = [], None
        try:
            r = httpx.get(INDEX_URL, timeout=10, follow_redirects=True)
            r.raise_for_status()
            base = INDEX_URL.rsplit("/", 1)[0] + "/"
            remote = [{**a, "url": base + a["file"]} for a in r.json().get("agents", [])]
        except Exception as e:
            err = "The public library isn’t reachable right now." if not isinstance(e, httpx.HTTPStatusError) else "The public library isn’t published yet."
        local = []
        if (BUNDLED / "index.json").exists():
            local = [{**a, "url": "bundled:" + a["file"], "starter": True} for a in json.loads((BUNDLED / "index.json").read_text(encoding="utf-8"))["agents"]]
        seen = {a["slug"] for a in remote}
        _cache.update(at=time.time(), data={"agents": remote + [a for a in local if a["slug"] not in seen], "error": err if not remote else None})
    return _cache["data"]


def fetch(url):
    """A bundle from the library, a share link or the starters. https only (http for this computer, in tests)."""
    if url.startswith("bundled:"):
        p = (BUNDLED / url[8:]).resolve()
        if BUNDLED.resolve() not in p.parents:
            raise ValueError("bad starter path")
        return json.loads(p.read_text(encoding="utf-8"))
    u = urlsplit(url)
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost")):
        raise ValueError("Agents only come from https links.")
    r = httpx.get(url, timeout=20, follow_redirects=True)
    r.raise_for_status()
    if len(r.content) > MAX_BYTES:
        raise ValueError("That file is too big to be an agent.")
    return r.json()


def install(E, b, source=None):
    """Import a library agent. It keeps to the sites it lists, starts in its own browser, and asks before
    anything it can't undo: approvals that came with the file are dropped."""
    c = check(b)
    if not c["ok"]:
        raise ValueError("This agent can’t be installed: " + " ".join(c["problems"]))
    b = json.loads(json.dumps(b))
    for sk in b.get("skills") or []:
        for st in sk.get("steps") or []:
            st.pop("approved_always", None)
    bot = b["bot"]
    for a in bot.get("automations") or []:
        a.pop("approved_always", None)
    bot["mode"] = "own"
    bid = transfer.import_bot(E, b)
    lst = b.get("listing") or listing(b)
    E.store.update("bots", bid, allowed_domains=c["domains"],
                   library={"slug": lst["slug"], "version": lst.get("version", 1), "author": lst.get("author"), "source": source})
    return bid


# ---------------------------------------------------------------- posting an agent
def _gh(*args, stdin=None):
    return subprocess.run([shutil.which("gh") or "gh", *args], capture_output=True, text=True, timeout=90, input=stdin)


def prepare(E, bid, meta):
    """The exact file that would become public, and what the checker says about it."""
    b = transfer.export_bot(E, bid)
    b.pop("exported", None)
    for k in ("last_run", "created", "warned_unchecked", "allowed_domains", "library"):  # this computer's bookkeeping
        b["bot"].pop(k, None)
    b["listing"] = listing(b, meta)
    return b, check(b), json.dumps(b, ensure_ascii=False, indent=1)


def publish(E, bid, meta):
    b, c, text = prepare(E, bid, meta)
    if not c["ok"]:
        return {"mode": "blocked", "problems": c["problems"]}
    slug = b["listing"]["slug"]
    if shutil.which("gh") and _gh("auth", "status").returncode == 0:
        try:
            return _pull_request(slug, text, b["listing"], c)
        except RuntimeError as e:
            note = str(e)
        return {**_web(slug, text, c), "note": f"gh couldn’t open the pull request ({note}), so here’s GitHub’s page instead."}
    return _web(slug, text, c)


def _web(slug, text, c):
    url = f"https://github.com/{REPO}/new/main/library/agents?filename={slug}.inky&value={quote(text)}"
    if len(url) < 8000:  # GitHub's new-file page takes the file in its link; it forks for you and you click Propose
        return {"mode": "web", "url": url, "public": text, "check": c}
    return {"mode": "manual", "url": f"https://github.com/{REPO}/upload/main/library/agents", "filename": f"{slug}.inky", "file": text, "public": text, "check": c}


def _pull_request(slug, text, lst, c):
    def ok(r):
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[:200])
        return r.stdout.strip()
    ok(_gh("repo", "fork", REPO, "--clone=false"))
    me = ok(_gh("api", "user", "-q", ".login"))
    sha = ok(_gh("api", f"repos/{REPO}/git/ref/heads/main", "-q", ".object.sha"))
    _gh("repo", "sync", f"{me}/inky", "--branch", "main")  # an older fork may not have main's latest commit yet
    branch = f"agent-{slug}-{int(time.time())}"
    ok(_gh("api", "-X", "POST", f"repos/{me}/inky/git/refs", "-f", f"ref=refs/heads/{branch}", "-f", f"sha={sha}"))
    body = json.dumps({"message": f"Library: add {lst['title']}", "branch": branch, "content": base64.b64encode(text.encode()).decode()})
    ok(_gh("api", "-X", "PUT", f"repos/{me}/inky/contents/library/agents/{slug}.inky", "--input", "-", stdin=body))
    report = "\n".join([f"**{lst['title']}**: {lst['summary']}", "", f"Visits: {', '.join(c['domains']) or 'none'}",
                        f"May do (asks first): {'; '.join(c['irreversible']) or 'nothing irreversible'}", "", "Posted from the Inky app."])
    url = ok(_gh("pr", "create", "--repo", REPO, "--head", f"{me}:{branch}", "--title", f"Library: {lst['title']}", "--body", report))
    return {"mode": "pr", "url": url.splitlines()[-1], "check": c}


def share_link(E, bid, meta):
    """A public Gist and an inky://install link anyone can open. Needs gh signed in."""
    b, c, text = prepare(E, bid, meta)
    if not c["ok"]:
        return {"mode": "blocked", "problems": c["problems"]}
    if not (shutil.which("gh") and _gh("auth", "status").returncode == 0):
        return {"mode": "none", "text": "Share links need GitHub’s gh tool, signed in (gh auth login). You can still send the file."}
    slug = b["listing"]["slug"]
    r = _gh("gist", "create", "--public", "--filename", f"{slug}.inky", "--desc", f"Inky agent: {b['listing']['title']}", "-", stdin=text)
    if r.returncode != 0:
        return {"mode": "none", "text": (r.stderr or "gh couldn’t make the gist").strip()[:200]}
    gist = r.stdout.strip().splitlines()[-1]
    raw = _gh("api", f"gists/{gist.rstrip('/').rsplit('/', 1)[-1]}", "-q", ".files[].raw_url").stdout.strip().splitlines()
    raw = raw[0] if raw else gist
    return {"mode": "gist", "gist": gist, "link": f"inky://install?url={quote(raw, safe='')}", "check": c}


def main(argv):
    if len(argv) >= 2 and argv[0] == "check":
        bad = 0
        for f in argv[1:]:
            b = json.loads(Path(f).read_text(encoding="utf-8"))
            c = check(b)
            lst = b.get("listing") or {}
            print(f"### {lst.get('title') or Path(f).name} {'✅' if c['ok'] else '❌'}")
            print(f"- Visits: {', '.join(c['domains']) or 'none'}")
            print(f"- May do (asks first): {'; '.join(c['irreversible']) or 'nothing irreversible'}")
            for p in c["problems"]:
                print(f"- ❌ {p}")
            bad += not c["ok"]
        return 1 if bad else 0
    if len(argv) == 2 and argv[0] == "index":
        out = Path(argv[1], "index.json")
        out.write_text(json.dumps(build_index(argv[1]), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {out}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
