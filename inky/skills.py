"""Skills: learned once with a model, replayed as plain steps with no model.
A step targets an element by a descriptor (role, name, text, attrs, css). Replay finds it again by that
descriptor; only if that fails does it ask a model once (repair), and it only acts when the model is sure."""
import re
import time
from urllib.parse import urljoin, urlparse


class NeedsHelp(Exception):
    """Stop and put a Problem in Needs you."""

    def __init__(self, kind, title, body, options=None, **meta):
        super().__init__(title)
        self.kind, self.title, self.body, self.options, self.meta = kind, title, body, options or [], meta


class CheckedUpTo(Exception):
    """A check run (when a bot moves) reached a step that would ask you: that's far enough, nothing is done."""


class Stopped(Exception):
    pass


CONFIDENT = 0.7
CONSENT = re.compile(r"\b(accept|accetta|aceptar|akzeptieren|accepter|agree|allow all|ok|got it|zgadzam|akkoord|close|chiudi|cerrar)\b", re.I)

# ---------------------------------------------------------------- finding elements again


def descriptor(el):
    return {k: el.get(k, "") for k in ("role", "name", "text", "tag", "id", "attr_name", "placeholder", "css", "type")} | \
        {"href": urlparse(el.get("href") or "").path}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def locate(desc, elements):
    """-> (index, how) or (None, None). Order: css (if role+name agree) → role+name → text → attributes."""
    if not desc:
        return None, None
    name, role = norm(desc.get("name")), desc.get("role")
    tiers = [
        ("css", lambda e: desc.get("css") and e["css"] == desc["css"] and e["role"] == role and norm(e["name"]) == name),
        ("name", lambda e: name and e["role"] == role and norm(e["name"]) == name),
        ("name", lambda e: name and norm(e["name"]) == name and e["role"] in ("button", "link", role)),
        ("text", lambda e: desc.get("text") and norm(e["text"]) == norm(desc["text"]) and e["role"] == role),
        ("attr", lambda e: any(desc.get(k) and e.get(k) == desc[k] for k in ("id", "attr_name", "placeholder")) and e["role"] == role),
    ]
    for how, ok in tiers:
        hits = [e for e in elements if ok(e)]
        if hits:
            hits.sort(key=lambda e: (not e.get("inview"), e["i"]))
            return hits[0]["i"], how
    return None, None


def table(page, limit=140):
    rows = []
    for e in page["elements"][:limit]:
        extra = ", ".join(x for x in (e["tag"], e["type"], e["placeholder"] and f"placeholder “{e['placeholder']}”",
                                        e["value"] and f"options {e['value'][:80]}", not e["inview"] and "off-screen") if x)
        rows.append(f"[{e['i']}] {e['role']} “{e['name']}” ({extra})")
    return "\n".join(rows)


# ---------------------------------------------------------------- numbers and filters


def parse_num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "")
    m = re.search(r"-?\d[\d.,\s  ]*", s)
    if not m:
        return None
    t = re.sub(r"[\s  ]", "", m.group(0)).rstrip(".,")
    if re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", t):
        t = re.sub(r"[.,]", "", t)
    elif "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def keep(item, f):
    op, want = f.get("op"), f.get("value")
    if f.get("field") not in item:  # the site has no such field: can't judge, so keep (unchecked() reports it)
        return True
    v = item.get(f.get("field"))
    if op in ("<", "<=", ">", ">="):
        a, b = parse_num(v), parse_num(want)
        if a is None or b is None:
            return False
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    if op in ("==", "!=") and parse_num(v) is not None and parse_num(want) is not None:
        same = parse_num(v) == parse_num(want)
        return same if op == "==" else not same
    s = norm(str(v if v is not None else ""))
    if op == "==":
        return s == norm(str(want))
    if op == "!=":
        return s != norm(str(want))
    if op == "contains":
        return norm(str(want)) in s
    if op == "not_contains":
        return norm(str(want)) not in s
    if op in ("in", "not_in"):
        ws = [w.strip() for w in re.split(r"[,;]", want)] if isinstance(want, str) else (want or [])  # "Bari, Lecce" or a list
        hit = any(norm(str(w)) and norm(str(w)) in s for w in ws)
        return hit if op == "in" else not hit
    return True


def apply_filters(items, filters):
    fs = [f for f in filters or [] if f and f.get("field")]
    return [it for it in items if all(keep(it, f) for f in fs)]


def unchecked(items, filters):
    """Rules this site's results can't be checked against (their field isn't extracted)."""
    fields = {k for it in items[:20] for k in it}
    return [f.get("text") or f"{f['field']} {f['op']} {f['value']}" for f in filters or [] if items and f.get("field") not in fields]


def item_key(it):
    return it.get("link") or it.get("url") or "|".join(str(v) for v in it.values())[:200]


# ---------------------------------------------------------------- learning

LEARN_SYSTEM = """You operate a web browser for a bot, one step at a time, to learn a job that will later be replayed with no AI.
You see the page as a numbered list of interactive elements. Reply with ONE JSON object:
{"action": "click"|"fill"|"select"|"press"|"goto"|"extract"|"next_page"|"done", "index": <element number or null>,
 "value": <text to type, option label, key, or URL>, "step": "<short label, e.g. Type Bari>", "confidence": <0-1>}
Rules: close cookie banners first. Use "fill" for text boxes and "select" for dropdowns (value = option label).
When the page shows the list of results the job wants, use "extract". After extracting, if there is a next-page link use
"next_page" with its index, otherwise "done". Never type passwords. Never click buy/pay. Prefer the user's corrections."""

EXTRACT_SYSTEM = """You write CSS selectors to extract a list of results from a page outline.
Reply with ONE JSON object: {"item": "<css for one result>", "fields": {"<field>": "<css inside the item, or css@attr>"}}
Always include a "title" field and, when there is one, a "link" field like "a@href". Include price/size/date-like fields
that the goal cares about. Use class names from the outline."""

REPAIR_SYSTEM = """A recorded browser step no longer matches the page. Pick the element that does the same thing now.
Reply with ONE JSON object: {"index": <element number or null>, "confidence": <0-1>, "why": "<short>"}.
Use null and low confidence when no element clearly does the same thing. A different action with a similar word is NOT a match."""


def learn(ctx, goal, start_url, max_steps=24):
    """Drive the page with the model, recording each step. ctx: computer, llm, bot, emit, gate, check, corrections."""
    comp = ctx.computer
    page = comp.call("open", start_url)
    steps, history = [], []
    extract = None
    ctx.emit("learn", f"Opened {urlparse(page['url']).netloc}", step=0)
    for _ in range(max_steps):
        ctx.check()
        if page.get("robot"):
            raise NeedsHelp("robot", f"{urlparse(page['url']).netloc} shows a robot check",
                            "Bots don’t solve these. Solve it once on its computer and it carries on.", ["Open its computer", "Skip"])
        fixes = ctx.corrections()
        user = (f"GOAL: {goal}\nBOT RULES: {'; '.join(r['text'] for r in ctx.bot.get('rules', []))}\n"
                f"CORRECTIONS FROM THE USER: {'; '.join(fixes) or 'none'}\n"
                f"STEPS SO FAR:\n" + ("\n".join(f"{i + 1}. {s['text']}" for i, s in enumerate(steps)) or "none") +
                f"\nEXTRACTED: {'yes' if extract else 'no'}\n\nPAGE: {page['title']} — {page['url']}\n"
                f"HEADINGS: {' | '.join(page['heads'])}\nTEXT: {page['text'][:500]}\n\nELEMENTS:\n{table(page)}" +
                (f"\n\nYOUR LAST REPLIES DIDN’T WORK: {'; '.join(history[-3:])}. Pick an element by its number; goto needs a full URL." if history else ""))
        try:
            d, _ = ctx.llm.ask_json("learn", LEARN_SYSTEM, user, bot_id=ctx.bot["id"])
        except ValueError:  # a reply that isn't JSON is one more strike, not the end
            history.append("your reply wasn’t one JSON object")
            if len(history) >= 6:
                raise NeedsHelp("learn_failed", "The model’s answers didn’t make sense",
                                "It kept replying in a way Inky can’t use. Try again, show it once, or pick a smarter model in Models.",
                                ["Try again", "Show me once", "Open Models"])
            continue
        act = d.get("action")
        if act == "done":
            break
        if act == "extract":
            if extract:
                break
            outline = comp.call("sample")
            spec, _ = ctx.llm.ask_json("learn", EXTRACT_SYSTEM, f"GOAL: {goal}\nURL: {page['url']}\nOUTLINE:\n{outline[:6000]}",
                                       bot_id=ctx.bot["id"])
            rows = comp.call("extract", spec)
            if not rows or all(not r.get("title") for r in rows):
                spec, _ = ctx.llm.ask_json("learn", EXTRACT_SYSTEM, f"Your selectors found nothing ({spec}). Try again.\n"
                                           f"GOAL: {goal}\nOUTLINE:\n{outline[:6000]}", bot_id=ctx.bot["id"])
                rows = comp.call("extract", spec)
            extract = spec
            steps.append({"action": "extract", "spec": spec, "text": f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}"})
            ctx.emit("learn", f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}", step=len(steps), fields=list(spec.get("fields", {})))
            page = comp.call("elements")
            continue
        idx = d.get("index")
        el = next((e for e in page["elements"] if e["i"] == idx), None) if idx is not None else None
        if act == "goto":  # the model sometimes "goes to" a word it meant to type
            url = web_address(d.get("value"), page["url"])
            if not url:
                history.append(f"goto {d.get('value')!r} is not a web address")
                continue
            d["value"] = url
        elif act not in ACTIONS:
            history.append(f"{act!r} is not an action")
            continue
        elif el is None:
            history.append(f"element {idx} does not exist")
            continue
        label = d.get("step") or f"{act} {el['name'] if el else d.get('value')}"
        step = {"action": "click" if act == "next_page" else act, "target": descriptor(el) if el else None,
                "value": d.get("value"), "text": label, "next_page": act == "next_page",
                "optional": bool(act == "click" and el and CONSENT.search(el["name"] or ""))}
        ctx.gate(step, el, page)
        try:
            page_after = _do(comp, step, idx, el, len(steps) + 1)
        except (NeedsHelp, Stopped):
            raise
        except Exception as e:  # a step that fails is feedback for the model, not the end of learning
            history.append(f"“{label}” failed ({type(e).__name__})")
            if len(history) >= 6:
                raise NeedsHelp("learn_failed", "Learning got stuck on this site",
                                f"The model kept picking steps that didn’t work here (last: “{label}”). Show it once, or try a smarter model.",
                                ["Show me once", "Try a smarter model", "Try again"])
            page = comp.call("elements")
            continue
        same = lambda st: st["action"] == step["action"] and st.get("value") == step.get("value") and (step["action"] == "goto" or st.get("target") == step.get("target"))
        if len(steps) >= 2 and all(same(st) for st in steps[-2:]):
            history.append(f"“{label}” done 3 times already; do the next thing")
            page = page_after
            continue
        steps.append(step)
        ctx.emit("learn", label, step=len(steps), target=el and el["name"])
        page = page_after
        if act == "next_page":
            break  # one next-page is enough to learn the loop
    if not extract and (not steps or all(st["action"] == "goto" for st in steps)):  # only ever opened pages: nothing learned
        raise NeedsHelp("learn_failed", "Couldn’t find the results to read",
                        "It learned the steps but never reached a list of results. Tell it where to look, or show it once.",
                        ["Show me once", "Try a smarter model"])
    host = urlparse(start_url).netloc
    name = f"Check {host}" if extract else (goal.strip().rstrip(".")[:48] or f"Job on {host}")
    return {"name": name, "site": host, "goal": goal, "start_url": start_url, "steps": steps,
            "version": 1, "learned_at": time.time(), "max_pages": 3}


ACTIONS = {"click", "fill", "select", "press", "next_page"}


def web_address(v, base):
    """A full URL, a /path on this site, or a bare domain; None for anything else (like a word to type)."""
    v = str(v or "").strip()
    if v.startswith("/"):
        v = urljoin(base, v)
    elif "://" not in v and re.match(r"^[\w-]+(\.[\w-]+)+(:\d+)?(/\S*)?$|^localhost(:\d+)?(/\S*)?$", v):
        local = re.match(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\d+\.\d+\.\d+\.\d+|[\w-]+\.local\b)", v)
        v = ("http://" if local else "https://") + v  # your own machines rarely have https
    u = urlparse(v)
    return v if u.scheme in ("http", "https") and u.netloc and " " not in v else None


def _do(comp, step, idx, el, n):
    comp.call("act", step["action"], idx, step.get("value"), step_text=f"{n} · {step['text']}", el=el)
    return comp.call("elements")


# ---------------------------------------------------------------- replay and repair


def repair(ctx, step, page, role="repair"):
    user = (f"RECORDED STEP: {step['text']} — {step['action']} on {step['target'].get('role')} “{step['target'].get('name')}”\n"
            f"PAGE: {page['title']} — {page['url']}\nELEMENTS:\n{table(page)}")
    d, _ = ctx.llm.ask_json(role, REPAIR_SYSTEM, user, bot_id=ctx.bot["id"])
    idx = d.get("index")
    conf = float(d.get("confidence") or 0)
    el = next((e for e in page["elements"] if e["i"] == idx), None) if idx is not None else None
    if el:  # same kind of control, or a word in common: otherwise a small model's "90% sure" isn't sure
        t = step["target"] or {}
        words = lambda x: {w for w in re.findall(r"[^\W\d_]{3,}", (x or "").lower())}
        if t.get("role") != el.get("role") and not (words(t.get("name")) & words(el.get("name"))):
            conf = min(conf, CONFIDENT - 0.2)
    return el, conf, d.get("why", "")


SLD = {"co", "com", "org", "net", "ac", "gov", "edu", "ne", "or"}


def site_of(host):
    """example.com for shop.example.com; example.co.uk for www.example.co.uk."""
    parts = (host or "").lower().removeprefix("www.").split(".")
    n = 3 if len(parts) > 2 and len(parts[-1]) == 2 and parts[-2] in SLD else 2
    return ".".join(parts[-n:])


def fence(ctx, url):
    """Agents from the library keep to the sites they list (allowed_domains). Your own bots have no fence."""
    allowed = (getattr(ctx, "bot", None) or {}).get("allowed_domains")
    host = urlparse(url or "").hostname
    if not allowed or not host:
        return
    if site_of(host) not in {site_of(d) for d in allowed}:
        raise NeedsHelp("blocked", f"This agent only works on {', '.join(allowed)}",
                        f"A step went to {host}. Agents from the library stay on the sites they list, so it stopped there.",
                        ["OK"], url=url)


def replay(ctx, skill, repair_role="repair"):
    """Run a skill with no model. -> {items, repairs, pages}"""
    comp = ctx.computer
    fence(ctx, skill["start_url"])
    page = comp.call("open", skill["start_url"])
    fence(ctx, page.get("url"))
    items, repairs, pages = [], [], 0
    steps = skill["steps"]
    extract_at = next((i for i, s in enumerate(steps) if s["action"] == "extract"), None)
    i = 0
    while i < len(steps):
        ctx.check()
        step = steps[i]
        if page.get("robot"):
            raise NeedsHelp("robot", f"{urlparse(page['url']).netloc} shows a robot check",
                            "Bots don’t solve these. Solve it once on its computer and it carries on, or skip this site.",
                            ["Open its computer", "Skip this run"], step=i)
        if step["action"] == "extract":
            rows = comp.call("extract", step["spec"])
            items += rows
            pages += 1
            ctx.emit("replay", f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}", step=i + 1)
            nxt = steps[i + 1] if i + 1 < len(steps) and steps[i + 1].get("next_page") else None
            if nxt and pages < skill.get("max_pages", 3):
                idx, _ = locate(nxt["target"], comp.call("elements")["elements"])
                if idx is not None:
                    page = _do(comp, nxt, idx, None, i + 2)
                    continue  # read the next page with the same extract step
            i += 2 if nxt else 1
            continue
        if step["action"] == "goto" or not step.get("target"):
            if step["action"] == "goto":
                fence(ctx, step.get("value"))
            comp.call("act", step["action"], None, step.get("value"), step_text=f"{i + 1} · {step['text']}")
            page = comp.call("elements")
            fence(ctx, page.get("url"))
            i += 1
            continue
        idx, how = locate(step["target"], page["elements"])
        if idx is None:  # cheap fix first: the page may still be loading
            time.sleep(1.0)
            page = comp.call("elements")
            idx, how = locate(step["target"], page["elements"])
        el = next((e for e in page["elements"] if e["i"] == idx), None)
        if idx is None and step.get("optional"):
            ctx.emit("replay", f"Skipped “{step['text']}”: not shown this time", step=i + 1)
            i += 1
            continue
        if idx is None:
            ctx.emit("repair", f"Couldn’t find “{step['target'].get('name')}” by its name", step=i + 1)
            el, conf, why = repair(ctx, step, page, role=repair_role)
            if el is None or conf < CONFIDENT:
                guess = f"“{el['name']}”, only {round(conf * 100)}% sure" if el else "nothing"
                raise NeedsHelp("fix_failed", f"Couldn’t fix step {i + 1}: “{step['text']}”",
                                f"Looked for “{step['target'].get('name')}” by its name: not on the page. "
                                f"Asked the model once: it picked {guess}. Stopped instead of guessing.",
                                ["Show me once", "Try a smarter model", "Skip this run"], step=i, guess=el and el["name"],
                                confidence=conf, url=page["url"])
            repairs.append({"step": i + 1, "from": step["target"].get("name"), "to": el["name"], "confidence": conf, "why": why})
            old_name = step["target"].get("name") or ""
            step["target"] = descriptor(el)
            step["repaired"] = step.get("repaired", 0) + 1
            if old_name and old_name in step.get("text", ""):  # the label follows: "Click Cerca" becomes "Click Trova"
                step["text"] = step["text"].replace(old_name, el["name"] or old_name)
            idx = el["i"]
            ctx.emit("repair", f"Fixed step {i + 1}: now “{el['name']}” ({round(conf * 100)}% sure)", step=i + 1)
        ctx.gate(step, el, page)
        page = _do(comp, step, idx, el, i + 1)
        fence(ctx, page.get("url"))  # a click can lead off the site too
        ctx.emit("replay", step["text"], step=i + 1, how=how)
        i += 1
    if extract_at is None:
        pass
    return {"items": items, "repairs": repairs, "pages": pages}
