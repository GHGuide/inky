# teach: Inky learns a site once

Tecnocasa (tecnocasa.it) has no Apify actor. Inky uses the site once in a visible Chrome, writes what it did down as a typed program, and from then on runs that program with no model: first locally, then as an Apify actor.

| File | What it does |
|---|---|
| `learn.py` | Opens Chrome (page 1440x900, centred, headed) and uses the site like a person: close the cookie banner (technical cookies only), Vendita, type Bari, pick "Bari (tutto il comune)", Appartamenti, max price 200000, read the cards, next page. Each step becomes a typed step and gets a coral border and chip on the page, scrolled into view first, under a caption bar ("Step 5 of 10 · Pick Bari (tutto il comune)" · "learning once · 1 AI call"). The end shows "Became a program: 10 steps · shortcut found · 8 clicks → 1 request" with the real call count and cost for 3 s. It watches the network: the cards come from `GET /api/estates/search`, so that request becomes the **shortcut** (8 clicks become 1 request). GLM-5.3 is called **once**, at the end (the page stays up meanwhile), to label the steps and to name and type the card fields. Its answer is checked against every card and JSON item seen, with one retry. Writes `tecnocasa.program.json`. |
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
.venv/bin/python teach/learn.py                              # re-learn: opens Chrome, 1 GLM call (~$0.02-0.05)
.venv/bin/python teach/learn.py --slow                       # for filming: each mark held 1.2 s longer (~50 s of steps, then the AI call)
.venv/bin/python teach/learn.py --slow --size 1600x900       # another page size (default 1440x900)
.venv/bin/python teach/learn.py --headless --out /tmp/p.json --shots /tmp/shots   # test run: keeps the real program, a PNG per step
.venv/bin/python teach/publish.py                            # re-publish and test the actor (~$0.0001 Apify)
.venv/bin/python teach/publish.py --run-only                 # just test the published actor
```

Last results: 96 of 96 Bari flats up to €200k. The browser replay and the shortcut give identical rows. The actor `cavernous_stew/inky-tecnocasa-homes` returned 20 of 20 sensible items (see `published.json`).

While a headed `learn.py` runs, it writes `$TMPDIR/inky-screen.flag`; with Hammerspoon and `voice/init.lua` loaded, that draws the coral "Inky has the screen" frame round the display (see `voice/README.md`).

The step captions in the bar are written in `learn.py` (`DEMO`); the labels saved in the program still come from GLM-5.3, so the program file has the same format as before.

## What it needs from you

- Google Chrome, for `learn.py` and `run_program.py --browser` only.
- `OPENROUTER_API_KEY` in `.env`, for `learn.py` only.
- `APIFY_TOKEN` in `.env`, for `publish.py` only.
- `check.py` and `run_program.py` need no keys.

`publish.py` talks to the Apify API directly, the same way `apify push` does (source files, then a build). apify-cli 1.10 ignores `APIFY_TOKEN` for `push` and would first run `apify login`, which stores the token in the keychain or in `~/.apify`. To use the CLI anyway, run `cd teach/actor && npx apify-cli login && npx apify-cli push` yourself. Copy `tecnocasa.program.json` to `actor/program.json` first.
