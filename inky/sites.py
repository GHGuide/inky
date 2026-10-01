"""Websites for a job, so you don't have to find them. Two sources, merged to one row per site:
- a web search (DuckDuckGo's plain page, no account), gently: one page per query unless you ask for more, a pause between
  requests, results cached, and when the search engine asks for a break it gets one (Inky never answers its challenge);
- the model's own suggestions, each checked to be a real, reachable site before it's shown.
Social networks, video and encyclopedias are left out."""
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from inky.skills import site_of

SEARCH = "https://html.duckduckgo.com/html/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
SKIP = {"youtube.com", "facebook.com", "instagram.com", "pinterest.com", "wikipedia.org", "reddit.com", "linkedin.com", "tiktok.com",
        "twitter.com", "x.com", "duckduckgo.com", "google.com", "bing.com", "quora.com", "medium.com", "wiktionary.org"}
# a domain that's for sale or parked, not a shop: "ebikeshop.nl is te koop", sedo, dan.com…
PARKED = re.compile(r"\b(domain|domein(naam)?)\b.{0,40}\b(for sale|te koop|kopen|zu verkaufen|à vendre|in vendita|en venta)\b|"
                    r"\b(buy|koop|kaufen) (this|deze|diese) (domain|domein(naam)?|domain)\b|\bparked (free|domain)\b|"
                    r"(^|\.)(sedo|dan|afternic|hugedomains|undeveloped|mooiedomeinnaam|domeinnaamkopen|parkingcrew)\.", re.I)
LINK = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
SNIP = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
NEXT_FORM = re.compile(r'<form[^>]*action="/html/"[^>]*>(.*?)</form>', re.S)
HIDDEN = re.compile(r'<input type="hidden" name="([^"]+)" value="([^"]*)"')
text = lambda s: re.sub(r"\s+", " ", re.sub(r"<.*?>", "", html.unescape(s or ""))).strip()

_cache, _pause = {}, {"until": 0}
PAUSE = 600  # seconds, after the search engine asks for a break


class Busy(RuntimeError):
    """The search engine asked for a break (a challenge page)."""


def search(q, timeout=12, pages=1):
    """One search, up to `pages` pages of about 10: [{url, host, site, title, snippet}] in the engine's order."""
    key = (q.lower(), pages)
    if key in _cache and time.time() - _cache[key][0] < 3600:
        return _cache[key][1]
    if time.time() < _pause["until"]:
        raise Busy("the search engine asked for a break")
    rows, data = [], {"q": q}
    for n in range(pages):
        if n:
            time.sleep(0.8)  # gently: like a person pressing Next, never a burst
        try:
            r = httpx.post(SEARCH, data=data, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
        except httpx.HTTPError:
            if n == 0:
                raise
            break  # a later page failing still leaves the first ones
        if r.status_code == 202 or "anomaly" in r.text[:6000].lower():
            _pause["until"] = time.time() + PAUSE
            if n == 0:
                raise Busy("the search engine asked for a break")
            break
        r.raise_for_status()
        rows += _rows(r.text)
        nxt = next((f for f in NEXT_FORM.findall(r.text) if 'value="Next"' in f), None)
        if not nxt:
            break
        data = dict(HIDDEN.findall(nxt)) | {"q": q}
    _cache[key] = (time.time(), rows)
    return rows


def _rows(page):
    rows = []
    for (href, title), snip in zip(LINK.findall(page), SNIP.findall(page) + [""] * 50):
        u = unquote(parse_qs(urlparse(html.unescape(href)).query).get("uddg", [html.unescape(href)])[0])
        host = urlparse(u).hostname
        if not host or not u.startswith(("http://", "https://")) or "duckduckgo.com/y.js" in u:  # ads go through y.js
            continue
        rows.append({"url": u, "host": host.removeprefix("www."), "site": site_of(host), "title": text(title)[:120], "snippet": text(snip)[:220]})
    return rows


def suggest(queries, guess=None, limit=60, pages=1):
    """Sites for these searches, best first, one per site. guess: the model's own idea, listed last if the web didn't
    find it. Raises Busy when the search engine wants a break, RuntimeError when no search worked at all."""
    queries = [q.strip() for q in dict.fromkeys(queries) if q and q.strip()][:4]
    got, busy = [], False
    for i, q in enumerate(queries):  # one after another, with a pause: never a burst
        if i and (q.lower(), pages) not in _cache:
            time.sleep(0.6)
        try:
            got.append(search(q, pages=pages))
        except Busy:
            busy = True
            break
        except Exception:
            continue
    if not got and busy:
        raise Busy("The search engine asked for a break, so Inky waits a few minutes before searching again.")
    if queries and not got:
        raise RuntimeError("Couldn’t search the web right now. Type the site’s address instead, or try again in a minute.")
    seen, rows = set(), []
    for i in range(max((len(g) for g in got), default=0)):  # interleave: each query's best results first
        for g in got:
            if i < len(g) and g[i]["site"] not in seen and g[i]["site"] not in SKIP and \
                    not PARKED.search(f"{g[i]['host']} {g[i]['title']} {g[i]['snippet']}"):
                seen.add(g[i]["site"])
                rows.append(g[i])
    if guess:
        h = urlparse(guess).hostname
        if h and site_of(h) not in seen and site_of(h) not in SKIP:
            rows.append({"url": guess, "host": h.removeprefix("www."), "site": site_of(h), "title": "", "snippet": "", "guess": True})
    return rows[:limit]


SITES_SYSTEM = """List websites where this job can be done: shops, marketplaces, listing sites or suppliers that really exist.
Reply with ONE JSON object: {"sites": ["<domain, e.g. example.com>", ...]} with up to 15 domains, the most useful first."""


def from_model(llm, job, have=(), label="the model"):
    """The model's own list of sites for the job, keeping only domains that really answer. -> rows like suggest()'s."""
    try:
        d, _ = llm.ask_json("chat", SITES_SYSTEM, job)
    except Exception:
        return []
    raw = [str(x).strip().lower() for x in (d.get("sites") or []) if isinstance(x, str)]
    names = [re.sub(r"^https?://", "", n).split("/")[0].removeprefix("www.") for n in raw]
    have = set(have)
    names = [n for n in dict.fromkeys(names) if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", n) and site_of(n) not in SKIP | have][:15]

    def real(n):
        for url in (f"https://{n}/", f"https://www.{n}/"):
            try:
                r = httpx.get(url, headers={"User-Agent": UA}, timeout=5, follow_redirects=True)
            except Exception:
                continue
            if r.status_code < 500:
                title = text((re.search(r"<title[^>]*>(.*?)</title>", r.text[:20000], re.S | re.I) or [None, ""])[1])[:120]
                if PARKED.search(f"{urlparse(str(r.url)).hostname} {title} {text(r.text[:20000])[:2000]}"):
                    return None  # it answers, but it's a domain for sale
                if re.search(r"just a moment|attention required|access denied|forbidden|captcha|are you a robot", title, re.I):
                    title = ""  # its bot-check page, not its name
                return {"url": str(r.url), "host": n, "site": site_of(n), "title": title, "snippet": "", "source": f"suggested by {label}"}
        return None
    with ThreadPoolExecutor(8) as ex:
        return [r for r in ex.map(real, names) if r]


if __name__ == "__main__":  # python -m inky.sites "wholesale bricks Moldova"
    import sys
    for row in suggest(sys.argv[1:] or ["cheap books"]):
        print(f"{row['host']:32} {row['title'][:60]}")
