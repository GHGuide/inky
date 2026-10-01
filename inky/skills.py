"""Skills: learned once with a model, replayed as plain steps with no model.
A step targets an element by a descriptor (role, name, text, attrs, css). Replay finds it again by that
descriptor; only if that fails does it ask a model once (repair), and it only acts when the model is sure."""
import re
import time
from urllib.parse import urljoin, urlparse


def short(s, n):
    """At most n characters, cut at a word with … rather than mid-word."""
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


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
CONSENT = re.compile(r"\b(accept\w*|accepta|acceptă|accetta\w*|acept\w*|aceit\w*|akzept\w*|zustimmen|einverstanden|agree|de acord|allow( all)?|alle(s)? toestaan|toestaan|"
                     r"ok|okay|got it|zgadzam|akceptuj\w*|akkoord|ik ga akkoord|godta|godkänn\w*|close|chiudi|cerrar|fermer|sluiten|schließen|"
                     r"принять|принимаю|согласен|cookies?|consent\w*|tout accepter)\b", re.I)
FILTER_FIELD = re.compile(r"\b(price|prices|prijs|prijzen|preis|prix|prezzo|precio|preço|cena|cen[ay]|pre[tț]|цена|min|max|minimum|maximum|from|to|van|tot|von|bis|"
                          r"budget|size|grootte|größe|m²|m2|year|jaar|km|mileage)\b", re.I)

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


def table(page, limit=140, typed=None):
    """The page's elements for a model. typed: {(role, name): value} already typed while learning, so it isn't typed twice."""
    rows = []
    for e in page["elements"][:limit]:
        done = (typed or {}).get((e["role"], e["name"]))
        extra = ", ".join(x for x in (e["tag"], e["type"], e["placeholder"] and f"placeholder “{e['placeholder']}”",
                                        e["value"] and f"options {e['value'][:80]}", not e["inview"] and "off-screen",
                                        done is not None and f"ALREADY TYPED “{str(done)[:60]}”") if x)
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
Never type into a box marked ALREADY TYPED. To open a category or page, click its link; use "goto" only for an address you
saw on the page or the user gave, never one you guess. After filling a search form, click its search button. After typing a message or
filling a form the job wants sent, click the button that sends or submits it (Inky asks the user before it really sends).
Don't set the site's own filters for price, size or the like: Inky filters the results itself. As soon as the page lists
results for the job (after a search, or in the right category; not the categories or featured items on a home page), use "extract". After extracting, if there is a next-page link use
"next_page" with its index, otherwise "done". Never type passwords. Never click buy/pay. Prefer the user's corrections."""

EXTRACT_SYSTEM = """You write CSS selectors to extract a list of results from a page outline.
Reply with ONE JSON object: {"item": "<css for one result>", "fields": {"<field>": "<css inside the item, or css@attr>"}}
Always include a "title" field and, when there is one, a "link" field like "a@href". Include price/size/date-like fields
that the goal cares about. Use class names from the outline."""

REPAIR_SYSTEM = """A recorded browser step no longer matches the page. Pick the element that does the same thing now.
Reply with ONE JSON object: {"index": <element number or null>, "confidence": <0-1>, "why": "<short>"}.
Use null and low confidence when no element clearly does the same thing. A different action with a similar word is NOT a match."""


NEXT = re.compile(r"^\s*(next|next page|›|»|→|>|more results|show more|load more|older|siguiente|suivant|weiter|nächste|avanti|successiva|următor|urmatoarea|înainte|далее|следующая|вперед|następna|dalej|próxima|seguinte|volgende|nästa)\b", re.I)


def said_number(v, text):
    """Is this number one you stated (150000 for “under 150k”, 20 for “£20”)?"""
    n = parse_num(v)
    if n is None or n == 0:
        return False
    t = re.sub(r"(?<=\d)[ ,.\u00a0'’](?=\d{3}\b)", "", (text or "").lower())  # 150.000 / 150,000 / 150 000 → 150000
    whole = str(int(n)) if float(n).is_integer() else str(n)
    return bool(re.search(rf"(?<![\d.]){re.escape(whole)}(?!\d)", t) or (n >= 1000 and n % 1000 == 0 and re.search(rf"(?<![\d.]){int(n // 1000)}k\b", t)))


def is_optional(step):
    """A step that may be missing on a later run: a cookie banner (even one learned before this check existed), or a next page."""
    t = step.get("target") or {}
    where = f"{t.get('name') or ''} {t.get('placeholder') or ''}"
    return bool(step.get("optional") or step.get("next_page") or (step.get("action") == "click" and
                (CONSENT.search(t.get("name") or "") or re.search(r"cookie|consent|banner", step.get("text") or "", re.I)))
                or (step.get("action") in ("fill", "select") and FILTER_FIELD.search(f"{where} {step.get('text') or ''}")  # a site's price filter: Inky filters anyway
                    and not re.search(r"search|zoek|such|cerca|busca|recherch|szukaj|caut|поиск", where, re.I)))


def next_link(page):
    """The page's “next page” link (or button, off the home page: there a “Next” is usually a slideshow arrow)."""
    home = not urlparse(page.get("url") or "").path.strip("/") and not urlparse(page.get("url") or "").query
    for e in page.get("elements") or []:
        name = (e.get("name") or "").strip()
        if name and len(name) < 40 and NEXT.match(name) and (e.get("role") == "link" and e.get("href") or e.get("role") == "button" and not home):
            return e
    return None


def error_page(page):
    """A “not found” or server error page: what a made-up address leads to."""
    head = f"{page.get('title') or ''} {' '.join(page.get('heads') or [])} {(page.get('text') or '')[:160]}"
    return bool(re.search(r"\b(404|410|500|502|503)\b|not found|page (doesn.t|does not) exist|niet gevonden|nicht gefunden|introuvable|no encontrad|non trovat|nu a fost găsit", head, re.I)) \
        and len(page.get("elements") or []) < 40


def home_page(url):
    u = urlparse(url or "")
    return not u.path.strip("/") and not u.query


SUBMIT = re.compile(r"\b(search|find|go|submit|cerca|trova|buscar|rechercher|suchen|szukaj|caută|cauta|найти|поиск|zoeken|sök|ok)\b", re.I)
DOING = re.compile(r"\b(send|submit|contact|book|apply|post|order|reserve|sign up|register|message|reply|enquire|inquire|request)\b", re.I)
FINDING = re.compile(r"\b(find|finds|watch|check|monitor|list|search|look for|track|new|cheap|cheapest|price|prices|under|below|compare|results?|offers?|deals?|listings?)\b", re.I)
PICK_LIST_SYSTEM = """Pick the list of results on this page that fits the goal. Reply with ONE JSON object: {"pick": <list number, or 0 if none fits>}"""


def read_results(ctx, goal, page):
    """The results on this page: Inky finds the lists itself (repeated items with links), the model only picks one.
    Falls back to the model writing selectors from an outline. -> (spec, rows); rows is [] when nothing was found."""
    comp = ctx.computer
    lists = comp.call("lists")
    if home_page(page.get("url")):  # a home page's few tiles are its categories or featured items, not results
        lists = [c for c in lists if c["count"] >= 6]
    if lists:
        pick = 1
        if len(lists) > 1:
            menu = "\n".join(f"{i + 1}) {c['count']} items, e.g. " + " | ".join(
                "; ".join(f"{k}: {str(v)[:60]}" for k, v in r.items() if v and k != "image") for r in c["rows"][:2]) for i, c in enumerate(lists))
            try:
                d, _ = ctx.llm.ask_json("learn", PICK_LIST_SYSTEM, f"GOAL: {goal}\nPAGE: {page['title']}\nLISTS:\n{menu}", bot_id=ctx.bot["id"])
                pick = int(d.get("pick") or 0)
            except Exception as e:
                if type(e).__name__ == "ModelStopped":
                    raise
                pick = 1  # any reply that isn't a number: the likeliest list (they're ranked)
            if not 1 <= pick <= len(lists):
                pick = 1 if any(c.get("priced") for c in lists[:1]) else 0
        if pick:
            c = lists[pick - 1]
            spec = {"item": c["item"], "fields": c["fields"]}
            rows = [r for r in comp.call("extract", spec) if any(r.values())]
            if named(rows):
                return spec, rows
    if home_page(page.get("url")):
        return None, []  # on a home page, only a real list counts; the outline would find its tiles again
    outline = comp.call("sample")
    for note in ("", "Your selectors found nothing. Use class names that are in the outline. "):
        try:
            spec, _ = ctx.llm.ask_json("learn", EXTRACT_SYSTEM, f"{note}GOAL: {goal}\nURL: {page['url']}\nOUTLINE:\n{outline[:7000]}", bot_id=ctx.bot["id"])
        except ValueError:
            continue
        if isinstance(spec, dict) and isinstance(spec.get("item"), str) and not re.fullmatch(r"\s*(html|body)(\s*>\s*[\w.#-]+)?\s*", spec["item"]):
            try:
                rows = [r for r in comp.call("extract", spec) if any(r.values())]
            except Exception:
                rows = []
            if len(rows) >= 3 and named(rows):  # the model's own selectors: a real list, not one stray element
                return spec, rows
    return None, []


def named(rows):
    """Real results have names: most rows need a title (or at least a price). Rows of only links are a wrong list."""
    if len(rows) < 3:
        return bool(rows) and all(r.get("title") for r in rows)
    return sum(1 for r in rows if r.get("title") or r.get("price")) >= 0.6 * len(rows)


def learn(ctx, goal, start_url, max_steps=24):
    """Drive the page with the model, recording each step. ctx: computer, llm, bot, emit, gate, check, corrections."""
    comp = ctx.computer
    page = comp.call("open", start_url)
    steps, history = [], []
    extract, empty, typed, finished = None, 0, {}, False
    watch, looked, idle = bool(FINDING.search(goal or "")), set(), 0
    ctx.emit("learn", f"Opened {urlparse(page['url']).netloc}", step=0)
    for _ in range(max_steps * 2):  # strikes don't use up the steps; the steps themselves are capped below
        if len(steps) >= max_steps:
            break
        ctx.check()
        if page.get("robot"):
            raise NeedsHelp("robot", f"{urlparse(page['url']).netloc} shows a robot check",
                            "Bots don’t solve these. Solve it once on its computer and it carries on, or skip it for now.", ["Open its computer", "Skip for now"])
        u = urlparse(page["url"])
        if watch and not extract and page["url"] not in looked and (steps or u.path.strip("/") or u.query):
            looked.add(page["url"])  # a page that already lists priced results: read them now, no need to go on clicking
            lists = comp.call("lists")
            if lists and lists[0]["count"] >= 6 and lists[0].get("priced"):
                spec, rows = read_results(ctx, goal, page)
                if rows:
                    extract = spec
                    steps.append({"action": "extract", "spec": spec, "text": f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}"})
                    ctx.emit("learn", f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}", step=len(steps), fields=list(spec.get("fields", {})))
                    page = comp.call("elements")
                    nxt = next_link(page)
                    if nxt:
                        steps.append({"action": "click", "target": descriptor(nxt), "value": None, "text": f"Next page ({nxt['name'][:30]})", "next_page": True, "optional": True})
                        ctx.emit("learn", "Next page", step=len(steps), target=nxt["name"])
                    finished = True
                    break
        idle += 1
        if idle > 10 and watch and not extract:  # going round in circles: if the page already lists real results, those are the job
            spec, rows = read_results(ctx, goal, page)
            if rows and len(rows) >= 6:
                extract = spec
                steps.append({"action": "extract", "spec": spec, "text": f"Read {len(rows)} results"})
                ctx.emit("learn", f"Read {len(rows)} results", step=len(steps), fields=list(spec.get("fields", {})))
                page = comp.call("elements")
                nxt = next_link(page)
                if nxt:
                    steps.append({"action": "click", "target": descriptor(nxt), "value": None, "text": f"Next page ({nxt['name'][:30]})", "next_page": True, "optional": True})
                finished = True
                break
        if idle > 10:  # ten replies without a new step: it's going round in circles
            raise NeedsHelp("learn_failed", "Learning got stuck on this site",
                            f"The model tried for a while on {u.netloc} without getting further. Show it once, or try a smarter model.",
                            ["Show me once", "Try a smarter model", "Try again"])
        fixes = ctx.corrections()
        user = (f"GOAL: {goal}\nBOT RULES: {'; '.join(r['text'] for r in ctx.bot.get('rules', []))}\n"
                f"CORRECTIONS FROM THE USER: {'; '.join(fixes) or 'none'}\n"
                f"STEPS SO FAR:\n" + ("\n".join(f"{i + 1}. {s['text']}" for i, s in enumerate(steps)) or "none") +
                f"\nEXTRACTED: {'yes' if extract else 'no'}\n\nPAGE: {page['title']} — {page['url']}\n"
                f"HEADINGS: {' | '.join(page['heads'])}\nTEXT: {page['text'][:500]}\n\nELEMENTS:\n{table(page, typed=typed)}" +
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
        if act in ("done", "next_page") or (act == "extract" and extract):
            finished = True
        if act == "done" and not extract and FINDING.search(goal or ""):  # a watch job that never read anything: read the results here, if there are any
            spec, rows = read_results(ctx, goal, page)
            if rows:
                extract = spec
                steps.append({"action": "extract", "spec": spec, "text": f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}"})
                ctx.emit("learn", f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}", step=len(steps), fields=list(spec.get("fields", {})))
            break
        if act == "done":
            break
        if act == "extract":
            if extract:
                break
            spec, rows = read_results(ctx, goal, page)
            if rows and home_page(page["url"]) and len(rows) < 6:  # a home page's few tiles are its categories or featured items
                rows = []
                history.append("these are the shop's categories or featured items, not results: open the right category or search first")
            if not rows:  # reading nothing is never a learned step: say so to the model and go on looking
                empty += 1
                history.append("there are no results to read on this page yet; search or open the list first")
                if empty >= 3:
                    raise NeedsHelp("learn_failed", "Couldn’t find the results to read",
                                    f"On {urlparse(page['url']).netloc} it found no list of results. Tell it where the list is, or show it once.",
                                    ["Show me once", "Try a smarter model", "Try again"])
                continue
            extract = spec
            steps.append({"action": "extract", "spec": spec, "text": f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}"})
            ctx.emit("learn", f"Read {len(rows)} result{'' if len(rows) == 1 else 's'}", step=len(steps), fields=list(spec.get("fields", {})))
            page = comp.call("elements")
            nxt = next_link(page)
            if nxt:  # a next page: it reads that too, every run (the model rarely thinks of it)
                steps.append({"action": "click", "target": descriptor(nxt), "value": None, "text": f"Next page ({nxt['name'][:30]})", "next_page": True, "optional": True})
                ctx.emit("learn", "Next page", step=len(steps), target=nxt["name"])
                finished = True
                break
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
        if watch and act in ("fill", "select") and el and FILTER_FIELD.search(f"{el.get('name')} {el.get('placeholder')} {d.get('step') or ''}") \
                and not re.search(r"search|zoek|such|cerca|busca|recherch|szukaj|caut|поиск", f"{el.get('name')} {el.get('placeholder')}", re.I) \
                and not said_number(d.get("value"), f"{goal} {' '.join(r['text'] for r in ctx.bot.get('rules', []))}"):
            # a site filter only with a limit you stated (“under 150k”); a made-up one breaks on the next run
            history.append("don’t set the site’s price or size filters with your own numbers: Inky filters the results itself; search or read the results")
            continue
        label = d.get("step") or f"{act} {el['name'] if el else d.get('value')}"
        step = {"action": "click" if act == "next_page" else act, "target": descriptor(el) if el else None,
                "value": d.get("value"), "text": label, "next_page": act == "next_page",
                "optional": bool(act == "click" and el and (CONSENT.search(el["name"] or "") or re.search(r"cookie|consent|banner", label, re.I)))}
        from inky.safety import classify
        if el and classify(step["action"], el, page)[0] == "irreversible":
            step["sends"] = True  # this is the step that sends or submits: a job that never has one never does anything
        ctx.gate(step, el, page)
        try:
            page_after = _do(comp, step, idx, el, len(steps) + 1)
            if act == "goto" and error_page(page_after):  # an address the model made up: back, and click links instead
                history.append(f"{d.get('value')} doesn’t exist (an error page); click a link on the page instead of guessing addresses")
                page = comp.call("open", page["url"])
                continue
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
        if step["action"] in ("fill", "select") and el:
            prev = next((st for st in steps if st["action"] == step["action"] and (st.get("target") or {}).get("role") == el["role"]
                         and (st.get("target") or {}).get("name") == el["name"]), None)
            typed[(el["role"], el["name"])] = step.get("value")
            if prev:  # the same box again: its step gets the new value, no second step
                prev.update(value=step.get("value"), text=label)
                page = page_after
                continue
        same = lambda st: st["action"] == step["action"] and st.get("value") == step.get("value") and (step["action"] == "goto" or st.get("target") == step.get("target"))
        if sum(same(st) for st in steps) >= (1 if step["action"] in ("fill", "select", "goto") else 2):  # a small model loops: the same step again isn't progress
            history.append(f"“{label}” is already a step; do the next thing")
            page = page_after
            continue
        if step.get("optional") and any(st.get("optional") and not st.get("next_page") for st in steps):
            page = page_after  # a cookie banner is answered once; a second click on one isn't a new step
            continue
        steps.append(step)
        idle = 0
        ctx.emit("learn", label, step=len(steps), target=el and el["name"])
        page = page_after
        if act == "next_page":
            break  # one next-page is enough to learn the loop
    if not finished and not extract:  # it ran out of steps or kept failing: that isn't a learned job
        raise NeedsHelp("learn_failed", "Learning didn’t finish",
                        f"After {len(steps)} steps on {urlparse(page['url']).netloc} it still wasn’t done. Show it once, or try a smarter model.",
                        ["Show me once", "Try a smarter model", "Try again"])
    if DOING.search(goal or "") and not extract and not any(st.get("sends") for st in steps):
        raise NeedsHelp("learn_failed", "It didn’t find the button that sends it",
                        "It typed what it should, but never pressed send or submit, so nothing would ever be sent. Show it once which button to press.",
                        ["Show me once", "Try a smarter model", "Try again"])
    if not extract and (not steps or all(st["action"] == "goto" for st in steps)):  # only ever opened pages: nothing learned
        raise NeedsHelp("learn_failed", "Couldn’t find the results to read",
                        "It learned the steps but never reached a list of results. Tell it where to look, or show it once.",
                        ["Show me once", "Try a smarter model"])
    host = urlparse(start_url).netloc
    name = f"Check {host}" if extract else (short(goal.strip().rstrip("."), 48) or f"Job on {host}")
    return {"name": name, "site": host, "goal": goal, "start_url": start_url, "steps": steps,
            "version": 1, "learned_at": time.time(), "max_pages": 3 if any(st.get("next_page") for st in steps) else 1}


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
                            "Bots don’t solve these. Solve it once on its computer and it carries on, or skip this run.",
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
        if idx is None and is_optional(step):
            ctx.emit("replay", f"Skipped “{step['text']}”: not shown this time", step=i + 1)
            i += 1
            continue
        if idx is None:
            ctx.emit("repair", f"Couldn’t find “{step['target'].get('name')}” by its name", step=i + 1)
            el, conf, why = repair(ctx, step, page, role=repair_role)
            if (el is None or conf < CONFIDENT) and step["action"] == "click" and i and steps[i - 1]["action"] == "fill" and \
                    (SUBMIT.search(step["target"].get("name") or "") or step["target"].get("type") == "submit"):
                prev, _ = locate(steps[i - 1]["target"], page["elements"])  # a search button that's hidden now: Enter in its box still searches
                if prev is not None:
                    before = page.get("url")
                    comp.call("act", "press", prev, "Enter", step_text=f"{i + 1} · Enter instead of “{step['target'].get('name')}”")
                    page = comp.call("elements")
                    if page.get("url") != before:
                        ctx.emit("replay", f"Pressed Enter instead of “{step['target'].get('name')}”", step=i + 1)
                        i += 1
                        continue
            if el is None or conf < CONFIDENT:
                guess = f"“{el['name']}”, only {round(conf * 100)}% sure" if el else "nothing"
                raise NeedsHelp("fix_failed", f"Couldn’t fix step {i + 1} ({step['text']})",
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
            ctx.emit("repair", f"Trying “{el['name']}” for step {i + 1} ({round(conf * 100)}% sure)", step=i + 1)
        ctx.gate(step, el, page)
        try:
            page = _do(comp, step, idx, el, i + 1)
        except (NeedsHelp, Stopped, CheckedUpTo):
            raise
        except Exception:  # it's on the page but can't be used now (hidden behind a menu, covered, gone while loading)
            if is_optional(step):
                ctx.emit("replay", f"Skipped “{step['text']}”: it couldn’t be used this time", step=i + 1)
                page = comp.call("elements")
                i += 1
                continue
            raise NeedsHelp("fix_failed", f"Couldn’t do step {i + 1} ({step['text']})",
                            "The page has it, but it couldn’t be used this time (it may be hidden behind a menu now). Show it once, or try again later.",
                            ["Show me once", "Try again", "Skip this run"], step=i, url=page.get("url"))
        fence(ctx, page.get("url"))  # a click can lead off the site too
        ctx.emit("replay", step["text"], step=i + 1, how=how)
        i += 1
    if extract_at is None:
        pass
    if items and not named(items):  # it read something, but nothing with a name or price: the page changed under the reading step
        raise NeedsHelp("fix_failed", "Reading the results stopped working",
                        f"It found {len(items)} items, but none had a name or price. The site’s page has probably changed.",
                        ["Show me once", "Try again", "Skip this run"], url=start_url_of(skill))
    items = [r for r in items if r.get("title") or r.get("price") or r.get("name")]  # nameless rows are never results
    return {"items": items, "repairs": repairs, "pages": pages}


def start_url_of(skill):
    return skill.get("start_url") or next((st.get("value") for st in skill.get("steps") or [] if st.get("action") == "goto"), None)
