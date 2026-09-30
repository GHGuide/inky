"""What a bot notices, with no AI: a recap of what happened, price trends, near-misses that become one-tap
suggestions, and the morning paper. Plus the manners: at most one unprompted note a day, never at night."""
import math
import re
from datetime import datetime
from statistics import median

from inky.skills import keep, parse_num

DAY = 86400


def quiet(hm, a, b):
    if not a or not b:
        return False
    return (a <= hm < b) if a < b else (hm >= a or hm < b)


def in_quiet(bot, now):
    s = bot.get("schedule") or {}
    return quiet(datetime.fromtimestamp(now).strftime("%H:%M"), s.get("quiet_from"), s.get("quiet_to"))


def recap(store, since, bot_id=None):
    out = []
    for b in store.find("bots", desc=False):
        if bot_id is not None and b["id"] != bot_id:
            continue
        runs = [r for r in store.find("runs", bot_id=b["id"], limit=500) if r["ts"] >= since and r.get("kind") == "replay"]
        fixed = [e for e in store.find("events", bot_id=b["id"], status="fixed", limit=100) if e["ts"] >= since]
        out.append({"bot": b["id"], "name": b["name"], "runs": len(runs), "results": sum(r.get("items") or 0 for r in runs),
                    "new": sum(r.get("new") or 0 for r in runs), "needs": len(store.find("needs", bot_id=b["id"], status="open")),
                    "fixed": len(fixed)})
    return out


def trend(results, field, now):
    """Week-over-week change of the median, when each week has at least 10 values."""
    def vals(lo, hi):
        return [v for r in results if lo <= r.get("ts", 0) < hi and (v := parse_num(r.get(field))) is not None]
    this, last = vals(now - 7 * DAY, now + 1), vals(now - 14 * DAY, now - 7 * DAY)
    if len(this) < 10 or len(last) < 10:
        return None
    a, b = median(last), median(this)
    return {"field": field, "from": a, "to": b, "pct": round((b - a) / a * 100, 1)} if a else None


def nice_up(v, limit):
    step = 5000 if limit >= 50000 else 500 if limit >= 5000 else 5
    return int(math.ceil(v / step) * step)


def near_misses(items, filters, margin=0.05):
    """Items that fail exactly one numeric limit, by at most `margin`: a new limit is worth suggesting."""
    for f in filters or []:
        lim = parse_num(f.get("value"))
        if f.get("op") not in ("<", "<=", ">", ">=") or lim is None:
            continue
        others = [g for g in filters if g is not f]
        up = f["op"] in ("<", "<=")
        miss = []
        for it in items:
            v = parse_num(it.get(f.get("field")))
            if v is None or keep(it, f) or not all(keep(it, g) for g in others):
                continue
            if (up and lim < v <= lim * (1 + margin)) or (not up and lim * (1 - margin) <= v < lim):
                miss.append(it)
        if miss:
            vs = [parse_num(it[f["field"]]) for it in miss]
            new = nice_up(max(vs), lim) if up else int(min(vs))
            return {"filter": f, "items": miss, "suggest": new}
    return None


def may_post(store, bot, now):
    """At most one unprompted note per bot per ~day, never in quiet hours, never while it waits on you."""
    if in_quiet(bot, now) or store.find("needs", bot_id=bot["id"], status="open", limit=1):
        return False
    recent = [m for m in store.find("messages", bot_id=bot["id"], limit=50) if m.get("unprompted")]
    return not any(now - m["ts"] < 20 * 3600 for m in recent)


def fmt(v):
    return f"{int(v):,}".replace(",", ".") if v >= 1000 else str(int(v))


def suggestion(bot, nm):
    f = nm["filter"]
    new_filters = [dict(g, value=nm["suggest"], text=f"{g['field']} {g['op']} {fmt(nm['suggest'])}") if g is f else g
                   for g in bot.get("filters") or []]
    n = len(nm["items"])
    raw = str(nm["items"][0].get(f["field"], ""))
    cur = re.match(r"^[^\d-]*", raw).group(0).strip()  # "£36.94" → "£", so the button says "£40"
    word = "Raise" if f["op"] in ("<", "<=") else "Lower"
    text = f"{n} {'result was' if n == 1 else 'results were'} just outside your {f.get('text') or f['field']} rule."
    return text, [{"label": f"{word} it to {cur}{fmt(nm['suggest'])}", "apply": {"filters": new_filters}}]


def morning_paper(store, bot, now):
    r = recap(store, now - DAY, bot["id"])[0]
    lines = [f"Good morning! Since yesterday: {r['runs']} runs, {r['results']} results checked, {r['new']} new."]
    results = [x for x in store.find("results", bot_id=bot["id"], limit=2000) if x["ts"] >= now - 7 * DAY]
    t = trend(store.find("results", bot_id=bot["id"], limit=2000), "price", now)
    if t and abs(t["pct"]) >= 2:
        lines.append(f"Prices {'fell' if t['pct'] < 0 else 'rose'} {abs(t['pct'])}% this week (median {fmt(t['to'])}).")
    chips = []
    nm = near_misses([x for x in results if x.get("passed") is False], bot.get("filters"))
    if nm:
        text, chips = suggestion(bot, nm)
        lines.append(text)
    if r["needs"]:
        lines.append(f"{r['needs']} thing{'s' if r['needs'] > 1 else ''} waiting for you.")
    return {"text": " ".join(lines), "chips": chips}
