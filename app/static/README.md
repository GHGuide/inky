# Inky front-end (app/static)

Plain HTML, CSS and vanilla JS. No framework, no build step. `app/serve.py` serves this folder and the `/api/*` routes.

```bash
.venv/bin/python app/serve.py            # then open http://127.0.0.1:8765/
.venv/bin/python app/static/check_ui.py  # self-check: stub API, every route in headless Chrome, screenshots in /tmp/inky-ui/
```

| File | What it is |
|---|---|
| `index.html` | Shell: fonts (Geist, Geist Mono), `app.css`, `app.js` |
| `app.css` | Design tokens and components copied from the approved `*.dc.html` designs |
| `app.js` | Hash router, one function per screen, all data from `/api/*` (list below) |
| `check_ui.py` | The self-check. Five passes: full fixtures, empty state, 1280x720 with no runs yet, 1920x1080, and `?rec=1` at 1920x1080. The empty and 1280 passes answer 404 for the newer endpoints, so the fallbacks are tested. It fails on any console error, uncaught exception, missing element, a card squashed by its column, or content wider than its panel |
| `qr-repo.svg` | The repo QR on the end card (a dashed placeholder shows when it is missing) |

Routes: `#home #task #confirm #research #screen #fast #results #workflow #activity #share #market #end`.

API: `GET /api/state /api/executions /api/run_detail /api/summary?since= /api/end /api/bundles`, `POST /api/interview /api/command /api/share /api/plan /api/best_now`,
and two POSTs that answer with Server-Sent Events: `/api/research/run` and `/api/build/run`. Every screen works when the newer ones answer 404: summary totals and the end card's numbers are left out, research shows the last research, build says the workflow is already built, "send the best 3" shows a toast, the marketplace shows its sample cards marked Preview.

- **The plan on `#confirm` is a form**: budget, paying, years, cities (at least one) and the text fields can be changed inline. **Yes, start research** checks it in the browser first (the browser points at a bad field) and sends the edited plan, which `serve.py` checks again.
- **Yes, start research** (`#confirm`) saves the plan (`/api/plan`), streams `/api/research/run` into the chat line by line (versions as small bars), then opens `#research`. **Yes, watch them** (`#research`) streams `/api/build/run` and ends with the n8n links, then opens `#workflow`. A second click while one runs does nothing. Add `?staging=1` to build the staging copy.
- **Send me the best 3 now** (Results button, or any message like "send me the best ones") calls `/api/best_now` and shows a toast.
- **Why 6.8%?** on every Results row: the same sum as `inky.js` (rent from nearby rentals, minus empty months, agency, rent tax, upkeep, over price plus buying costs), labelled as an estimate. It needs `rent_m2` or `rent_month` on the match and `research.costs`. Under it, **ten years, roughly**: that rent after costs (kept flat) × 10, plus the price growing at the country's Eurostat trend capped at 3% a year, minus the buying costs, labelled "estimate, not advice".
- **Every saved home, by yield after costs** (`#research`): one strip per city, one dot per saved home on the same yield scale, darker = higher yield, hollow = the city's best home when it misses a rule, the yield rule as a dashed line; hover for zone, yield and price. It is a strip, not a map: the research keeps no coordinates per home.
- **Last night, run by run** (`#activity`): one tick per run from `/api/summary` `per_run`, height = listings read, colour = how it went. It rises in once per visit.
- **Marketplace** (`#market`) lists the bundles from `/api/bundles` (the built-in one tagged `example`); the sample sections below stay, marked Preview.
- Results: city and yield filters, the best home on top, and a green `new` on homes this browser hasn't shown before (`localStorage`).
- Keys: `/` focuses the message box, `1`–`5` switch tabs, `F` toggles full screen on `#end`.
- `?rec=1` recording mode: the 1440-wide design is zoomed to fill the window (1920x1080), no scrollbars, no hover jumps, motion 1.3x slower. `?replay=1#task` replays the last finished interview of this browser at a readable pace (`?replay=3` is 3x faster), labelled "Replay"; it calls no API.

- Every number on screen comes from the API. When data is missing, a screen shows "Runs after the first build". `#market` (and the three cards on `#home`) are the only static sample agents, marked Preview.
- The message box on every task screen posts to `/api/command` and shows the change and the matches before and after. On `#task` it answers the interview instead.
- `#task` runs the real interview: rounds collapse as they finish, and the right panel counts what is clear. When the interview is done, the app moves to `#confirm`. Interview progress is kept in `sessionStorage`, and the last finished one in `localStorage` (for the replay). Under each round, "Skip picks" shows the plan values Skip falls back to.
- `#screen` reads `teach/tecnocasa.program.json` (`steps[].do/label/target.css` and `item.fields`). `#fast` reads `data/race.json` (`compiled` and `llm`).
- The page polls `/api/state` and `/api/executions` every 20 s, so research and runs show up while the build finishes. It never re-renders over text you have typed and not sent.
- Match counts: every screen shows the same number. It is the count from the last command for the current rules, or else the research version with those rules. `derive.py` saves only the first 15 homes. After a command, the ones that fail a new rule are hidden, and the next research run lists the rest.
- Status: `/api/state` has no n8n "active" flag. The header says "Running · every 15 min" only when a scheduled run started in the last 30 minutes. Otherwise it says "Built in n8n · no runs yet" or shows the last run.
- Layout: designed at 1440 wide. Below 1400 px the thread gets narrower, and the n8n picture zooms down to fit.
- The mic button opens a small popover: talking to Inky is **hold ⌥ Space** anywhere (Hammerspoon + whisper.cpp on this Mac, `voice/README.md`). The page records nothing. Nothing leaves the page apart from `/api/*` calls and Google Fonts.

What it needs from you: nothing extra. Start `app/serve.py` with the repo's `.env`. The n8n links come from `N8N_BASE_URL`. Use the bare origin (`https://YOUR-N8N.app.n8n.cloud`); `serve.py` also strips a pasted path such as `/home/workflows`.
