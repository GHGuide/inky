"""Websites for a job, so you don't have to find them: a web search (DuckDuckGo's plain page, no account)
for each query, merged to one row per site. Social networks, video and encyclopedias are left out."""
import html
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from inky.skills import site_of

SEARCH = "https://html.duckduckgo.com/html/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
SKIP = {"youtube.com", "facebook.com", "instagram.com", "pinterest.com", "wikipedia.org", "reddit.com", "linkedin.com", "tiktok.com",
        "twitter.com", "x.com", "duckduckgo.com", "google.com", "bing.com", "quora.com", "medium.com", "wiktionary.org"}
LINK = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
SNIP = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
text = lambda s: re.sub(r"\s+", " ", re.sub(r"<.*?>", "", html.unescape(s or ""))).strip()


def search(q, timeout=12):
    """One search: [{url, host, site, title, snippet}] in the order the search engine ranks them."""
    r = httpx.post(SEARCH, data={"q": q}, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    rows = []
    for (href, title), snip in zip(LINK.findall(r.text), SNIP.findall(r.text) + [""] * 50):
        u = unquote(parse_qs(urlparse(html.unescape(href)).query).get("uddg", [html.unescape(href)])[0])
        host = urlparse(u).hostname
        if not host or not u.startswith(("http://", "https://")) or "duckduckgo.com/y.js" in u:  # ads go through y.js
            continue
        rows.append({"url": u, "host": host.removeprefix("www."), "site": site_of(host), "title": text(title)[:120], "snippet": text(snip)[:220]})
    return rows


def suggest(queries, guess=None, limit=24):
    """Sites for these searches, best first, one per site. guess: the model's own idea, kept only if the web knows it too
    or listed last. Raises RuntimeError when no search worked."""
    queries = [q.strip() for q in dict.fromkeys(queries) if q and q.strip()][:4]
    got, errors = [], 0
    with ThreadPoolExecutor(max(1, len(queries))) as ex:
        for res in ex.map(_try, queries):
            if res is None:
                errors += 1
            else:
                got.append(res)
    if queries and errors == len(queries):
        raise RuntimeError("Couldn’t search the web right now. Type the site’s address instead, or try again in a minute.")
    seen, rows = set(), []
    for i in range(max((len(g) for g in got), default=0)):  # interleave: each query's best results first
        for g in got:
            if i < len(g) and g[i]["site"] not in seen and g[i]["site"] not in SKIP:
                seen.add(g[i]["site"])
                rows.append(g[i])
    if guess:
        h = urlparse(guess).hostname
        if h and site_of(h) not in seen and site_of(h) not in SKIP:
            rows.append({"url": guess, "host": h.removeprefix("www."), "site": site_of(h), "title": "", "snippet": "", "guess": True})
    return rows[:limit]


def _try(q):
    try:
        return search(q)
    except Exception:
        return None


if __name__ == "__main__":  # python -m inky.sites "wholesale bricks Moldova"
    import sys
    for row in suggest(sys.argv[1:] or ["cheap books"]):
        print(f"{row['host']:32} {row['title'][:60]}")
