"""A local shop with one page for each kind of site a bot meets while learning (tests/test_learning.py).
Run it to look around: python -m tests.learn_site 8770"""
import html
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

STATE = {"layout": 1}
BRANDS = ["Gazelle", "Batavus", "Sparta", "Cortina", "Stella", "Qwic", "Cube", "Trek", "Giant", "Riese"]
BIKES = [{"id": f"eb{i}", "name": f"{BRANDS[i % 10]} {['Ultimate', 'Grenoble', 'Arroyo', 'Ami', 'Vicenza'][i % 5]} C{300 + i * 7} e-bike",
          "price": 650 + (i * 137) % 1700, "where": ["Utrecht", "Leiden", "Delft", "Gouda"][i % 4]} for i in range(25)]
KIDS = [{"id": f"k{i}", "name": f"Boys' bike {16 + i % 3 * 2} inch {['red', 'blue', 'green'][i % 3]} #{i}", "price": 60 + i * 9, "where": "Utrecht"} for i in range(12)]
FEED = [{"id": f"f{i}", "name": n, "price": p, "where": "Amsterdam"} for i, (n, p) in enumerate(
    [("Grey corner sofa", 250), ("iPhone 13 128GB", 420), ("Fiat Panda 2012", 3900), ("Floor lamp, brass", 35),
     ("Stella Vicenza e-bike", 990), ("Oak dining table", 180), ("PlayStation 5", 380), ("Winter tyres 16 inch", 120)])]
TAGS = ["love", "life", "inspirational", "humor", "books", "truth"]
AUTHORS = ["Albert Einstein", "Jane Austen", "Mark Twain", "Marilyn Monroe"]
QUOTES = [{"text": f"“Quote number {i}: the {['world', 'mind', 'book', 'heart', 'truth'][i % 5]} is what we make of it, again and again.”",
           "author": AUTHORS[i % 4], "tags": [f"topic{i % 10}", TAGS[i % 6]]} for i in range(29)]  # like the real site: on one page the first tags all differ

LAPTOPS = [{"id": f"lt{i}", "name": f"{['Asus', 'Lenovo', 'Acer', 'Dell', 'HP'][i % 5]} VivoBook {14 + i} laptop", "price": 299 + i * 61} for i in range(15)]
TOP = [{"id": "t0", "name": "Galaxy Tab 3", "price": 97}, {"id": "t1", "name": "Nokia 123", "price": 24}, {"id": "t2", "name": "Asus VivoBook 14 laptop", "price": 299}]
TEAMS = [{"name": f"{['Boston', 'Chicago', 'Detroit', 'Toronto', 'Montreal', 'New York'][i % 6]} {['Bruins', 'Hawks', 'Wings', 'Leafs'][i // 6]}",
          "year": 1990 + i % 5, "wins": 30 + (i * 7) % 25, "losses": 20 + i % 9} for i in range(24)]

CSS = """body{font-family:system-ui,sans-serif;margin:0;color:#222}header{background:#234;color:#fff;padding:12px 20px}
header a{color:#fff;margin-right:14px}main{max-width:900px;margin:20px auto;padding:0 16px}
.product,.listing,.tile,.quote{border:1px solid #ddd;border-radius:8px;padding:12px;margin:8px 0}
input{padding:6px;width:240px}button{padding:6px 14px}td,th{padding:4px 10px;text-align:left}"""


def esc(s):
    return html.escape(str(s))


def eur(n):
    return f"€ {n:,}".replace(",", ".")


def shell(title, body, extra=""):
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><title>{esc(title)}</title><style>{CSS}</style></head><body>"
            "<header><a href='/'>BikeBarn</a><a href='/cats/'>Categories</a><a href='/sell'>Sell your bike</a><a href='/login'>Log in</a></header>"
            f"<main>{body}</main><footer><small>© BikeBarn · <a href='/about'>About</a></small></footer>{extra}</body></html>")


def card(p):
    return (f'<article class="product"><h2 class="name"><a href="/p/{p["id"]}">{esc(p["name"])}</a></h2>'
            f'<p class="meta">{esc(p["where"])}</p><span class="price">{eur(p["price"])}</span></article>')


def search_form(action="/search", button=True):
    return (f'<form action="{action}"><label for="q">Search</label><input id="q" name="q" placeholder="What are you looking for?">'
            + ('<button type="submit">Search</button>' if button else "") + "</form>")


def paged(items, n, per, link):
    """One page of cards and a “Next ›” link while there are more."""
    chunk = items[(n - 1) * per:n * per]
    nxt = f'<nav class="pages"><a href="{link(n + 1)}">Next ›</a></nav>' if n * per < len(items) else ""
    return "".join(card(p) for p in chunk) + nxt


PRICES = [  # (markup inside the card, what it means)
    ('<span class="price"><span class="amount">€ 1.234,56</span></span>', 1234.56),
    ('<span class="price"><span class="amount">$1,234.56</span></span>', 1234.56),
    ('<span class="price"><span class="amount">£12</span></span>', 12),
    ('<span class="price"><span class="amount">Free</span></span>', 0),
    ('<span class="price"><span class="amount">from €99</span></span>', 99),
    ('<span class="price"><span class="amount">€100 – €200</span></span>', 100),
    ('<span class="price"><del><span class="amount">€ 1.500,00</span></del> <ins><span class="amount">€ 1.199,00</span></ins></span>', 1199),
    ('<span class="badge">-20%</span><span class="price"><span class="amount">€ 80,00</span></span>', 80),
]


def quote(q):
    tags = "".join(f'<a class="tag" href="/quotes/tag/{t}/">{t}</a> ' for t in q["tags"])
    return (f'<div class="quote"><span class="text">{esc(q["text"])}</span>'
            f'<span>by <small class="author">{esc(q["author"])}</small> <a href="/quotes/author/{q["author"].replace(" ", "-")}">(about)</a></span>'
            f'<div class="tags">Tags: {tags}</div></div>')


def finder():
    """/find: a search page whose button changes with /__layout (2: renamed, 3: the box is renamed too, 4: the button is gone)."""
    box = ('<label for="q">Search</label><input id="q" name="q">' if STATE["layout"] != 3 else
           '<label for="where">Where to?</label><input id="where" name="where">')
    btn = {1: '<button type="submit">Search</button>', 2: '<button type="submit">Go</button>', 3: '<button type="submit">Go</button>',
           4: '<button type="button" onclick="this.textContent=\'Saved\'">Save search</button>'}[STATE["layout"]]
    return f'<form action="/search" onsubmit="return {str(STATE["layout"] != 4).lower()}">{box}{btn}</form>'


def thumb(p):
    """webscraper.io's product card: the price heading comes first, the name is a link with the full name in its title."""
    return (f'<div class="col-md-4"><div class="thumbnail"><div class="caption"><h4 class="price">${p["price"]:.2f}</h4>'
            f'<h4><a class="title" href="/shop/product/{p["id"]}" title="{esc(p["name"])}">{esc(p["name"][:16])}...</a></h4>'
            f'<p class="description">{esc(p["name"])}, 8GB, 256GB SSD</p></div></div></div>')


def shop(title, body):
    side = ('<div class="sidebar"><a href="/shop/">Home</a> <a href="/shop/computers" aria-label="Navigation category">Computers</a> '  # as on webscraper.io
            '<a href="/shop/computers/laptops" aria-label="Navigation subcategory">Laptops</a> '
            '<a href="/shop/computers/tablets" aria-label="Navigation subcategory">Tablets</a> <a href="/shop/cart" aria-label="Cart"><b>×</b></a></div>')
    return shell(title, f"{side}<div class='page'>{body}</div>")


class Site(BaseHTTPRequestHandler):
    def send(self, body, status=200, ctype="text/html; charset=utf-8", headers=()):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        if urlparse(self.path).path == "/aspx/":
            return self.send(aspx(form.get("ctl00$q", "")))
        return self.send(shell("Sent", "<h1>Thanks</h1>"))

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p, n = u.path, int(q.get("page", "1") or 1)
        if p == "/":  # a marketplace home: a mixed feed of featured things, a search box, sell and log in links
            return self.send(shell("BikeBarn marketplace", "<h1>Welcome to BikeBarn</h1>" + search_form() +
                                   "<a href='/post'>Post an ad</a><h2>Featured</h2>" + "".join(card(x) for x in FEED)))
        if p == "/search":
            hits = [b for b in BIKES if not q.get("q") or any(w in b["name"].lower() for w in q["q"].lower().replace("-", " ").split())] or BIKES
            return self.send(shell(f"{len(hits)} results", f"<h1>{len(hits)} results for {esc(q.get('q', ''))}</h1>" +
                                   paged(hits, n, 10, lambda k: "/search?" + urlencode({**q, "page": k}))))
        if p == "/enter/":
            return self.send(shell("Find a bike", "<h1>Find a bike</h1>" + search_form(button=False)))
        if p == "/find":
            return self.send(shell("Find", "<h1>Find</h1>" + finder()))
        if p == "/aspx/":
            return self.send(aspx(None))
        if p == "/cats/":
            tiles = "".join(f'<div class="tile"><a href="/cat/{k}"><h3>{t}</h3></a><p>Browse all {t.lower()} near you</p></div>'
                            for k, t in (("city", "City bikes"), ("e-bikes", "E-bikes"), ("kids", "Kids' bikes")))
            return self.send(shell("Categories", f"<h1>Categories</h1>{tiles}"))
        if p == "/cat/e-bikes":
            return self.send(shell("E-bikes", "<h1>E-bikes</h1>" + paged(BIKES, n, 10, lambda k: f"/cat/e-bikes?page={k}")))
        if p == "/cat/kids":
            return self.send(shell("Kids' bikes", "<h1>Kids' bikes</h1>" + paged(KIDS, n, 10, lambda k: f"/cat/kids?page={k}")))
        if p == "/cat/city":
            return self.send(shell("City bikes", "<h1>City bikes</h1><p>Nothing here yet.</p>"))
        if p == "/numbered":
            chunk = "".join(card(b) for b in BIKES[(n - 1) * 8:n * 8])
            pages = " ".join(f'<span class="current">{k}</span>' if k == n else f'<a href="/numbered?page={k}">{k}</a>' for k in (1, 2, 3, 4))
            return self.send(shell("E-bikes", f"<h1>E-bikes</h1>{chunk}<div class='pagination'>{pages}</div>"))
        if p in ("/more", "/scroll"):  # 10 shown, the rest fetched by a button or by scrolling to the bottom
            data = json.dumps([{"id": b["id"], "name": b["name"], "price": eur(b["price"]), "where": b["where"]} for b in BIKES[10:30]])
            js = ("const rest=" + data + ";function more(){const l=document.getElementById('list');"
                  "rest.splice(0,10).forEach(b=>l.insertAdjacentHTML('beforeend',`<article class=\"product\"><h2 class=\"name\"><a href=\"/p/${b.id}\">${b.name}</a></h2>"
                  "<p class=\"meta\">${b.where}</p><span class=\"price\">${b.price}</span></article>`));if(!rest.length){const m=document.getElementById('more');m&&m.remove()}}")
            js += ("addEventListener('scroll',()=>{if(innerHeight+scrollY>=document.body.offsetHeight-40)more()});" if p == "/scroll" else "")
            btn = '<button id="more" onclick="more()">Load more</button>' if p == "/more" else ""
            return self.send(shell("E-bikes", f"<h1>E-bikes</h1><div id='list'>{''.join(card(b) for b in BIKES[:10])}</div>{btn}<script>{js}</script>"))
        if p == "/prices":
            cards = "".join(f'<article class="product"><h2 class="name"><a href="/p/x{i}">Bike deal number {i}</a></h2>{m}</article>' for i, (m, _) in enumerate(PRICES))
            return self.send(shell("Deals", f"<h1>Deals</h1>{cards}"))
        if p == "/articles":
            items = "".join(f'<li class="story"><a class="headline" href="/a/{i}">Cycling story {i}: how the city changed its bike lanes</a>'
                            f' <span class="by">by Reporter {i % 3} · {i + 1} hours ago</span></li>' for i in range(15))
            return self.send(shell("News", f"<h1>Latest news</h1><ul class='stories'>{items}</ul>"))
        if p == "/sponsored":  # one result shown twice, once marked as an ad: the others keep their own links
            cards = card({**BIKES[0], "name": "Ad: " + BIKES[0]["name"]}) + "".join(card(b) for b in BIKES[:12])
            return self.send(shell("E-bikes", f"<h1>E-bikes</h1>{cards}"))
        if p == "/table":
            rows = "".join(f'<tr><td><a href="/p/{b["id"]}">{esc(b["name"])}</a></td><td>{b["where"]}</td><td>{eur(b["price"])}</td></tr>' for b in BIKES[:12])
            return self.send(shell("E-bikes", f"<h1>E-bikes</h1><table><thead><tr><th>Name</th><th>Where</th><th>Price</th></tr></thead><tbody>{rows}</tbody></table>"))
        if p == "/details":  # cards whose only link says Details / View: the name is in the heading
            cards = "".join(f'<div class="listing"><h3>Flat on Via Roma {i}, {40 + i} m²</h3><div class="info">2 rooms · floor {i % 4}</div>'
                            f'<div class="cost">{eur(90000 + i * 5000)}</div><a href="/l/{i}">{["Details", "Dettagli", "View"][i % 3]}</a></div>' for i in range(9))
            return self.send(shell("Flats", f"<h1>Flats</h1>{cards}"))
        if p == "/details2":  # the same, with no heading at all: the name is a plain paragraph
            cards = "".join(f'<div class="tile"><p class="desc">Red city bike, {24 + i % 3} inch, number {i}</p><b>{eur(100 + i * 10)}</b>'
                            f'<a href="/b/{i}">View</a></div>' for i in range(9))
            return self.send(shell("Bikes", f"<h1>Bikes</h1>{cards}"))
        if p == "/quotes":  # quotes.toscrape: a quote's links (its author, its tags) are shared with other quotes
            chunk = QUOTES[(n - 1) * 10:n * 10]
            nxt = f'<ul class="pager"><li class="next"><a href="/quotes?page={n + 1}">Next <span aria-hidden="true">→</span></a></li></ul>' if n * 10 < len(QUOTES) else ""
            side = "".join(f'<span class="tag-item"><a class="tag" href="/quotes/tag/{t}/">{t}</a></span>' for t in TAGS)
            return self.send(shell("Quotes", f"<h1>Quotes to Scrape</h1><div class='row'><div class='col-md-8'>{''.join(quote(x) for x in chunk)}{nxt}</div>"
                                             f"<div class='col-md-4 tags-box'><h2>Top Ten tags</h2>{side}</div></div>"))
        if p in ("/shop/", "/shop/computers"):  # a few featured items, and the category the job wants is a link away
            return self.send(shop("Web Scraper Test Sites", "<h1>Top items being scraped right now</h1><div class='row'>" + "".join(thumb(t) for t in TOP) + "</div>"))
        if p == "/shop/computers/laptops":
            chunk = "".join(thumb(x) for x in LAPTOPS[(n - 1) * 6:n * 6])
            nxt = f'<ul class="pagination"><li><a class="page-link" href="/shop/computers/laptops?page={n + 1}">›</a></li></ul>' if n * 6 < len(LAPTOPS) else ""
            return self.send(shop("Laptops", f"<h1>Computers / Laptops</h1><div class='row'>{chunk}</div>{nxt}"))
        if p == "/teams":  # scrapethissite's hockey teams: a table whose rows have no links, a search box, pages
            n = int(q.get("page_num", "1"))
            hits = [t for t in TEAMS if q.get("q", "").lower() in t["name"].lower()]
            rows = "".join(f'<tr class="team"><td class="name">{t["name"]}</td><td class="year">{t["year"]}</td><td class="wins">{t["wins"]}</td>'
                           f'<td class="losses">{t["losses"]}</td><td class="pct">{t["wins"] / (t["wins"] + t["losses"]):.2f}</td></tr>' for t in hits[(n - 1) * 10:n * 10])
            nxt = f'<a href="/teams?{urlencode({**q, "page_num": n + 1})}" aria-label="Next">»</a>' if n * 10 < len(hits) else ""
            return self.send(shell("Hockey Teams", '<h1>Hockey Teams: Forms, Searching and Pagination</h1><form action="/teams">'
                                                   '<input name="q" placeholder="Search for Teams..." aria-label="Search for Teams"><button>Search</button></form>'
                                                   f'<table><tr><th>Team Name</th><th>Year</th><th>Wins</th><th>Losses</th><th>Win %</th></tr>{rows}</table>{nxt}'))
        if p == "/hn/news":  # Hacker News: each story is two table rows, the second with its vote, user and comment links
            stories = "".join(
                f'<tr class="athing submission" id="{i}"><td class="title"><span class="rank">{i}.</span></td><td class="votelinks"><a href="/hn/vote?id={i}">'
                f'<div class="votearrow"></div></a></td><td class="title"><span class="titleline"><a href="/hn/story{i}">Story {i}: what changed in '
                f'{["AI", "Rust", "space", "chips", "maps"][i % 5]} this week</a> <span class="sitebit">(<a href="/hn/from?site=example.org">example.org</a>)</span></span></td></tr>'
                f'<tr><td colspan="2"></td><td class="subtext"><span class="subline">{i * 7} points by <a class="hnuser" href="/hn/user?id=u{i % 4}">u{i % 4}</a> '
                f'<a href="/hn/item?id={i}">{i} hours ago</a> | <a href="/hn/hide?id={i}">hide</a> | <a href="/hn/item?id={i}">{i * 3} comments</a></span></td></tr>'
                '<tr class="spacer" style="height:5px"></tr>' for i in range(1, 31))
            return self.send('<!doctype html><html><head><meta charset=utf-8><title>Hacker News</title></head><body><center><table id="hnmain">'
                             '<tr><td><table><tr><td><span class="pagetop"><b class="hnname"><a href="/hn/news">Hacker News</a></b> '
                             '<a href="/hn/newest">new</a> | <a href="/hn/past">past</a> | <a href="/hn/ask">ask</a></span></td></tr></table></td></tr>'
                             f'<tr id="bigbox"><td><table>{stories}<tr><td colspan="2"></td><td class="title"><a href="/hn/news?p=2" class="morelink" rel="next">More</a></td></tr>'
                             '</table></td></tr></table></center></body></html>')
        if p == "/cookie":
            wall = ('<div id="consent" style="position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9;display:flex;align-items:center;justify-content:center">'
                    '<div style="background:#fff;padding:30px">We use cookies to make this site work. '
                    '<button onclick="document.cookie=\'consent=1;path=/cookie\';document.getElementById(\'consent\').remove()">Accept all</button></div></div>'
                    "<script>if(document.cookie.includes('consent=1'))document.getElementById('consent').remove()</script>")
            return self.send(shell("Find a bike", "<h1>Find a bike</h1>" + search_form(), extra=wall))
        if p == "/late":  # the list comes a moment after the page
            data = json.dumps([card(b) for b in BIKES[:12]])
            return self.send(shell("E-bikes", f"<h1>E-bikes</h1><div id='list'>Loading…</div><script>setTimeout(()=>{{document.getElementById('list').innerHTML={data}.join('')}},1500)</script>"))
        if p == "/old":
            return self.send("", 302, headers=[("Location", "/search?q=e-bike")])
        if p == "/jsredirect":
            return self.send("<!doctype html><title>Moving</title><script>location.replace('/search?q=e-bike')</script>")
        if p == "/slow":
            time.sleep(3)
            return self.send(shell("E-bikes", "<h1>E-bikes</h1>" + paged(BIKES, n, 10, lambda k: f"/slow?page={k}")))
        if p == "/menu":  # a category menu with counts, and no results on the page
            items = "".join(f'<li><a href="/cat/{k}">{t} ({c})</a></li>' for k, t, c in
                            (("e-bikes", "E-bikes", 743), ("city", "City bikes", 1210), ("kids", "Kids' bikes", 86), ("racing", "Racing bikes", 312),
                             ("cargo", "Cargo bikes", 97), ("folding", "Folding bikes", 54)))
            return self.send(shell("All bikes", f"<h1>All bikes</h1><ul class='cats'>{items}</ul>"))
        if p == "/contact":  # a contact form with its own header, and a box to tick beside its button
            return self.send(shell("Contact", '<form method="post" action="/sent"><header><h2>Write to the seller</h2></header>'
                                              '<label for="msg">Message</label><textarea id="msg" name="msg"></textarea>'
                                              '<div class="actions"><label><input type="checkbox" name="ok"> I agree</label><button type="submit">Continue</button></div></form>'))
        if p == "/members":
            return self.send("", 302, headers=[("Location", "/login")])
        if p == "/login":
            return self.send(shell("Sign in", '<h1>Sign in to see members’ deals</h1><form method="post" action="/login">'
                                              '<label for="em">Email</label><input id="em" type="email" name="em">'
                                              '<label for="pw">Password</label><input id="pw" type="password" name="pw"><button type="submit">Sign in</button></form>'))
        if p == "/robot":
            return self.send(shell("Just a moment", '<h1>Are you a robot?</h1><div class="g-recaptcha" data-sitekey="x"><iframe title="reCAPTCHA" src="about:blank"></iframe></div>'))
        if p == "/blocked":
            return self.send("<!doctype html><title>Access denied</title><h1>Access denied</h1><p>You don't have permission to access this server.</p>", 403)
        if p == "/__layout":
            STATE["layout"] = int(q.get("v", "1"))
            return self.send(json.dumps(STATE), ctype="application/json")
        if p in ("/sell", "/post", "/about") or p.startswith(("/p/", "/l/", "/b/", "/a/", "/quotes/", "/hn/", "/shop/")):
            return self.send(shell("BikeBarn", f"<h1>{esc(p)}</h1>"))
        links = "".join(f"<li><a href='/cat/c{i}'>Category {i}</a></li>" for i in range(45))  # a shop's 404: its whole menu, and “not found”
        return self.send(shell("Page not found", f"<h1>Sorry, we couldn’t find that page</h1><ul>{links}</ul>"), 404)


def aspx(query):
    """An ASP.NET page: one POST form around everything, with a sign-in box in the header and a newsletter box in the footer."""
    hits = [b for b in BIKES if query is not None and any(w in b["name"].lower() for w in query.lower().replace("-", " ").split())]
    res = "".join(card(b) for b in hits) if query is not None else "<p>Type what you look for.</p>"
    return ("<!doctype html><html><head><meta charset=utf-8><title>Bike Search</title></head><body>"
            '<form method="post" action="/aspx/" id="aspnetForm"><input type="hidden" name="__VIEWSTATE" value="dDwtMTA4MzE0MjEwNTs7Pg==">'
            "<header><a href='/'>Home</a> <a href='/cats/'>Categories</a> <span><input name='ctl00$user' aria-label='User name'>"
            "<input type='password' name='ctl00$pw' aria-label='Password'><input type='submit' name='ctl00$in' value='Log in'></span></header>"
            "<main><h1>Bike Search</h1>"
            '<label for="ctl00_q">Search bikes</label><input id="ctl00_q" name="ctl00$q" value=""><input type="submit" name="ctl00$go" value="Search">'
            f"<div id='results'>{res}</div></main>"
            '<footer><label for="ctl00_nl">Newsletter</label><input type="email" id="ctl00_nl" name="ctl00$nl"><input type="submit" name="ctl00$sub" value="Subscribe"></footer>'
            "</form></body></html>")


def start(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8770), Site)
    print(f"learning test site on http://127.0.0.1:{srv.server_port}")
    srv.serve_forever()
