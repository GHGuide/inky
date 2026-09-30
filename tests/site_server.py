"""Local listings portal for tests. Mimics a real site: cookie banner, search form, pagination,
a layout switch (/__layout?v=2 moves "Cerca" inside a "Filtri" panel), a send form, a login and a robot check.
Run: python -m tests.site_server 8765"""
import html
import json
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STATE = {"layout": 1, "sent": []}
CITIES = {"bari": ("Bari", ["Libertà", "Madonnella", "Carrassi", "Poggiofranco", "Japigia"]),
          "valencia": ("Valencia", ["Ruzafa", "Benimaclet", "Cabanyal", "Campanar", "Patraix"]),
          "lodz": ("Łódź", ["Śródmieście", "Bałuty", "Widzew", "Polesie", "Górna"])}

CSS = """body{font-family:system-ui,sans-serif;margin:0;background:#fafafa;color:#222}
header{background:#1f6f78;color:#fff;padding:14px 24px;font-weight:700}
main{max-width:860px;margin:24px auto;padding:0 20px}
label{display:block;font-size:13px;color:#555;margin:10px 0 4px}
input,select,textarea{font:inherit;padding:8px 10px;border:1px solid #bbb;border-radius:6px;width:260px}
button,.btn{font:inherit;background:#1f6f78;color:#fff;border:0;border-radius:6px;padding:9px 18px;margin-top:14px;cursor:pointer;text-decoration:none;display:inline-block}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:10px;padding:14px 16px;margin:10px 0;display:flex;justify-content:space-between}
.price{font-weight:700;font-size:18px}.muted{color:#777;font-size:13px}
#cookies{position:fixed;inset:auto 0 0 0;background:#222;color:#fff;padding:18px 24px;display:flex;gap:16px;align-items:center;justify-content:space-between}
details{border:1px solid #ddd;border-radius:8px;padding:10px 14px;margin-top:14px;background:#fff}"""


def page(title, body, cookies=True):
    banner = ('<div id="cookies"><span>Usiamo i cookie per migliorare il sito.</span>'
              '<button onclick="document.cookie=\'ok=1;path=/\';this.parentNode.remove()">Accetta</button></div>') if cookies else ""
    return (f"<!doctype html><html lang=it><head><meta charset=utf-8><title>{title}</title><style>{CSS}</style></head>"
            f"<body><header>CasaFacile</header><main>{body}</main>{banner}"
            "<script>if(document.cookie.includes('ok=1')){const c=document.getElementById('cookies');c&&c.remove()}</script></body></html>")


def listings(city_key, max_price):
    name, areas = CITIES.get(city_key, (city_key.title(), ["Centro"]))
    rnd = random.Random(city_key)
    out = []
    for i in range(27):
        area = areas[i % len(areas)]
        size = rnd.randint(38, 95)
        price = rnd.randint(55, 230) * 1000 + (915 if i == 3 else 0)
        rooms = rnd.randint(1, 4)
        out.append({"id": f"{city_key}-{i}", "title": f"Appartamento {rooms} locali · {area}, {name}",
                    "price": price, "size": size, "rooms": rooms, "floor": rnd.randint(0, 7)})
    return [x for x in out if not max_price or x["price"] <= max_price]


def fmt(n):
    return f"€ {n:,}".replace(",", ".")


def search_form():
    fields = ('<label for="comune">Comune</label><input id="comune" name="comune" placeholder="Città">'
              '<label for="tipologia">Tipologia</label><select id="tipologia" name="tipologia">'
              '<option>Appartamenti</option><option>Ville</option><option>Uffici</option></select>'
              '<label for="prezzo_max">Prezzo max</label><input id="prezzo_max" name="prezzo_max" placeholder="Nessun limite">')
    if STATE["layout"] in (1, 3):
        label = "Cerca" if STATE["layout"] == 1 else "Trova"
        return f'<form action="/results">{fields}<br><button type="submit">{label}</button></form>'
    return (f'<form action="/results"><label for="comune">Dove</label><input id="comune" name="comune" placeholder="Città">'
            '<details><summary>Filtri</summary>'
            '<label for="tipologia">Tipologia</label><select id="tipologia" name="tipologia"><option>Appartamenti</option><option>Ville</option></select>'
            '<label for="prezzo_max">Prezzo massimo</label><input id="prezzo_max" name="prezzo_max">'
            '<br><button type="submit">Cerca</button></details>'
            '<button type="button" onclick="alert(\'Ricerca salvata\')">Salva ricerca</button></form>')


class Site(BaseHTTPRequestHandler):
    def send(self, body, status=200, ctype="text/html; charset=utf-8"):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if p == "/":
            return self.send(page("Case in vendita", "<h1>Case in vendita</h1>" + search_form()))
        if p == "/results":
            city = (q.get("comune") or "").strip().lower().replace("ł", "l").replace("ó", "o").replace("ź", "z")
            digits = "".join(c for c in q.get("prezzo_max", "") if c.isdigit())
            items = listings(city, int(digits) if digits else None)
            n = int(q.get("page", "1"))
            chunk = items[(n - 1) * 10:n * 10]
            cards = "".join(
                f'<div class="card"><div><h3 class="title">{html.escape(x["title"])}</h3>'
                f'<span class="size">{x["size"]} m²</span> · <span class="rooms">{x["rooms"]} locali</span> · '
                f'<span class="floor">piano {x["floor"]}</span></div><div><div class="price">{fmt(x["price"])}</div>'
                f'<a class="details" href="/listing/{x["id"]}">Dettagli</a></div></div>' for x in chunk)
            nxt = ""
            if n * 10 < len(items):
                qs = "&".join(f"{k}={v}" for k, v in q.items() if k != "page")
                nxt = f'<a class="next" href="/results?{qs}&page={n + 1}">Avanti</a>'
            return self.send(page("Risultati", f"<h1>{len(items)} case trovate</h1>{cards}<nav>{nxt}</nav>"))
        if p.startswith("/listing/"):
            lid = p.split("/")[-1]
            return self.send(page("Dettagli", f'<h1>Annuncio {lid}</h1><a class="btn" href="/contact?id={lid}">Contatta</a>'))
        if p == "/contact":
            lid = html.escape(q.get("id", ""))
            return self.send(page("Contatta", f'<h1>Contatta l’agenzia</h1><form method="post" action="/sent">'
                                              f'<input type="hidden" name="id" value="{lid}">'
                                              '<label for="msg">Messaggio</label><textarea id="msg" name="msg"></textarea>'
                                              '<br><button type="submit">Invia</button></form>'))
        if p == "/login":
            return self.send(page("Accedi", '<h1>Accedi</h1><form method="post" action="/sent">'
                                            '<label for="user">Email</label><input id="user" name="user">'
                                            '<label for="pw">Password</label><input id="pw" type="password" name="pw">'
                                            '<br><button type="submit">Accedi</button></form>'))
        if p == "/captcha":
            return self.send(page("Verifica", '<h1>Are you a robot?</h1><div class="g-recaptcha" data-sitekey="x">'
                                              '<iframe title="reCAPTCHA" src="about:blank"></iframe></div>'))
        if p == "/__layout":
            STATE["layout"] = int(q.get("v", "1"))
            return self.send(json.dumps(STATE), ctype="application/json")
        if p == "/__sent":
            return self.send(json.dumps(STATE["sent"]), ctype="application/json")
        return self.send("not found", 404, "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        STATE["sent"].append(form)
        return self.send(page("Inviato", "<h1>Messaggio inviato</h1>", cookies=False))


def start(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), Site)
    print(f"test site on http://127.0.0.1:{srv.server_port}")
    srv.serve_forever()
