# race: eight windows, zero AI

For the demo shot. The compiled program runs in 8 Chrome windows at once with no model. Next to them, one
click-by-click LLM agent (GLM-5.3 via `derive.glm`) has to ask the model before every action.

```
.venv/bin/python race/race.py                    # 60 s, 8 headed windows + 1 agent window, then the result card (6 s)
.venv/bin/python race/race.py --record           # for filming: windows within 1920x1080, the result card stays up 12 s
.venv/bin/python race/race.py --seconds 90
.venv/bin/python race/race.py --program race/sample.program.json
.venv/bin/python race/race.py --dry-run --out /tmp/race.json   # 2 headless windows for 15 s, agent for 2 steps
.venv/bin/python race/race.py --dry-run --out /tmp/race.json --shots /tmp/shots   # plus a PNG of every window and the card
.venv/bin/python race/check.py                   # self-check: helper asserts (pages, layout, agent link check) + a real --dry-run
```

Run the commands from the repo root. The run writes `data/race.json`:
`{at, seconds, compiled:{windows, listings, per_second, model_calls:0, pages, per_window, seconds_used}, llm:{listings, per_second, model_calls, cost_usd, seconds_used}, program}`
and prints one summary line.

How it works
- **Program**: `--program`, or by default `teach/tecnocasa.program.json` when it exists, else `race/sample.program.json`
  (Bari flats for sale on tecnocasa.it: 174 listings over 12 pages).
- **Compiled windows**: one Chrome, one separate context per window. Each window opens `start_url`, waits for the
  page to finish loading, and replays the steps (`open`/`click`/`fill`/`select`, as in `teach/run_program.py`).
  A failed step stops the steps. The window then starts over once. The steps pass when the results have cards and
  every typed value (`Bari`, `200000`) is in the URL, so a price filter that silently did not apply is caught too.
  The first window to pass sets the page plan (first page, page link pattern, last page) for all windows, so the
  slices line up. A window that fails twice still reads its slice from that plan. Each window then reads its own
  pages with `item.selector`/`item.fields`, at most about 8 pages a minute. The coral frame has a card in the top
  left, sized in screen pixels whatever the page scale: "window 3" / **"42 homes"** (36 px) / "0 AI calls", from the
  first page on, during the steps too. A window with no pages left says so.
  `listings` counts unique listing URLs. `per_second` is listings divided by the time the windows took, capped at
  `--seconds`.
- **Layout**: Chrome will not make a window smaller than 500x375 px. A screen at least 2500 px wide gets a 4x2 grid
  with the agent in a column on the right. A laptop or a 1920x1080 screen gets a 3x3 grid with the agent in the last
  cell (bottom right): 600x375 windows on the MacBook, 640x375 at 1920x1080, rows overlapping by about 30 px. When a cell is
  below 500x375, the windows overlap evenly and still end at the screen edge (1440x900: rows overlap by about half). Each window lays the page out 1280 px wide, the width the steps were taught at, and scales it to fit. So the
  filters the steps use are on the page, not hidden in the phone layout. Clicks go through the DOM, because mouse
  coordinates do not survive that scaling.
- **Result card**: when both sides are done, a small window (1040x440) opens in the middle of the screen with the
  run's real numbers, the same ones written to `data/race.json`:
  "Inky · 96 homes · 19.7 s · 0 AI calls" over "Clicking agent · 30 homes · 60 s · 5 AI calls · $0.085". It stays up
  6 s (12 s with `--record`), then every window closes. `--record` also keeps the windows within 1920x1080 on a bigger
  screen; on the MacBook (1800x1071 usable) and on a 1920x1080 screen the layout is the same 3x3 grid either way.
- **"Inky has the screen"**: a headed run writes `$TMPDIR/inky-screen.flag` while it runs; with Hammerspoon and
  `voice/init.lua` loaded, that draws a coral frame round the whole display (see `voice/README.md`).
- **Agent window** (grey frame, card "clicking AI agent / 12 homes / 3 AI calls · $0.021 · thinking…"): each turn the model gets the goal, the clickable elements and the visible text. It
  answers with the listings it read plus one action: click, goto, scroll, back or done. A listing counts only if its
  URL is a link on the page, and it is stored under that link. The agent is capped at 3 min and $0.50. It cannot
  type, and clicks on contact/login/accept-cookies buttons are refused. Clicks and `goto` must stay on the site's
  own host; if a script takes it elsewhere it goes straight back, and popup windows are closed. A model call counts
  only when the model answered, so a missing key shows 0 calls (and fails the check). Failed calls print only the
  error type and HTTP status.
- If the agent is still waiting on the model at the bell, the race waits for that answer so its cost is counted.
  Listings in that late answer do not count. The race can therefore finish up to a minute after `--seconds`.

Needs from you: Google Chrome, network, and `OPENROUTER_API_KEY` in `.env`. A 60 s race costs about $0.05–0.15
of GLM-5.3, and the dry run about $0.03. The headed run opens 9 windows over the whole screen, so start it with nothing
else you need on screen.

`--shots` PNGs from a headless run ignore the page scale, so the cards look bigger in them than they are on screen.

Not used: the program's JSON `shortcut`. The race shows the steps replayed in Chrome; the shortcut is faster still but
has nothing to show on camera.
