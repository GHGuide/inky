# teach: Inky learns a site once

Tecnocasa (tecnocasa.it) has no Apify actor. Inky uses the site once in a visible Chrome, writes what it did down as a typed program, and from then on runs that program with no model: first locally, then as an Apify actor.

| File | What it does |
|---|---|
| `learn.py` | Opens Chrome (1280x800, headed) and uses the site like a person: close the cookie banner (technical cookies only), Vendita, type Bari, pick "Bari (tutto il comune)", Appartamenti, max price 200000, read the cards, next page. Each step becomes a typed step and gets a coral border and chip on the page. It watches the network: the cards come from `GET /api/estates/search`, so that request becomes the **shortcut** (8 clicks become 1 request). GLM-5.3 is called **once**, at the end, to label the steps and to name and type the card fields. Its answer is checked against every card and JSON item seen, with one retry. Writes `tecnocasa.program.json`. |
| `run_program.py` | Runs the program with no model. It uses the shortcut (httpx, one request per page) when there is one, or `--browser` to replay the recorded clicks in Chrome. Writes `out.json` and prints listings/second. |
| `actor/` | The same program as the Apify actor `inky-tecnocasa-homes` (Node, plain fetch; input `maxItems`, `maxPrice`, `city`). Other Italian cities go through the site's own autocomplete. |
| `publish.py` | Uploads `actor/` plus the program, builds it, runs it once with `maxItems: 20` and checks the 20 items. Writes `published.json` (actor URL and test run URL). |
| `check.py` | The self-check. It validates the program shape, runs 1 page through the shortcut (no browser), and asserts at least 10 listings with a price and a size that `inky.js normalize()` accepts. |

`inky.js` has a `tecnocasa` branch in `normalize()`, so these items join the idealista, immobiliare and otodom listings.

## Run

```bash
.venv/bin/python teach/check.py                              # no keys, no spend
.venv/bin/python teach/run_program.py --pages 10             # ~96 listings in ~2 s (shortcut)
.venv/bin/python teach/run_program.py --pages 2 --browser --headed   # the same 30 rows in ~13 s, clicking
.venv/bin/python teach/learn.py                              # re-learn: opens Chrome, 1 GLM call (~$0.02)
.venv/bin/python teach/publish.py                            # re-publish and test the actor (~$0.0001 Apify)
.venv/bin/python teach/publish.py --run-only                 # just test the published actor
```

Last results: 96 of 96 Bari flats up to €200k. The browser replay and the shortcut give identical rows. The actor `cavernous_stew/inky-tecnocasa-homes` returned 20 of 20 sensible items (see `published.json`).

## What it needs from you

- Google Chrome, for `learn.py` and `run_program.py --browser` only.
- `OPENROUTER_API_KEY` in `.env`, for `learn.py` only.
- `APIFY_TOKEN` in `.env`, for `publish.py` only.
- `check.py` and `run_program.py` need no keys.

`publish.py` talks to the Apify API directly, the same way `apify push` does (source files, then a build). apify-cli 1.10 ignores `APIFY_TOKEN` for `push` and would first run `apify login`, which stores the token in the keychain or in `~/.apify`. To use the CLI anyway, run `cd teach/actor && npx apify-cli login && npx apify-cli push` yourself. Copy `tecnocasa.program.json` to `actor/program.json` first.
