# Inky: shot list

What to record for each beat of [script.md](script.md): the screen, the command, the window size, the clicks, and a plan B.
Storyboard with thumbnails: https://claude.ai/artifact/NQorqMxkSQ5WMvQt1BxW4d (page "Demo video").

Suggested order, so nothing waits on anything else: the phone at 08:00 (beat 1) → the read-only n8n and Apify console shots (beats 3A, 4B, 5, 6) → the app shots on the film copy (beats 2, 3B, flash, end) → learn.py and the race (beat 4, they call GLM) → voice and approve last (beat 7).

## Set up once

1. **Focus**: Do Not Disturb on the Mac. On the phone, a Focus that lets only Telegram through. Hide the Dock and desktop icons. Quit ChatGPT, Raycast and Alfred (they take ⌥ Space).
2. **Chrome**: a clean profile called "Inky film", with no extensions, no bookmarks bar and zoom at 100%. Sign in to n8n, the Apify console and Gmail in that profile only.
3. **Window size**: every Chrome shot is one window at 1440×900 (the size the app and learn.py are laid out for). On a screen wider than 1920 px you can use 1920×1080 instead.
   ```bash
   osascript -e 'tell application "Google Chrome" to set bounds of front window to {0, 38, 1440, 938}'
   ```
4. **A film copy of the data**, so no take can change Saturday's numbers or the live workflow. With `INKY_DATA` set, rule edits are not pushed to n8n.
   ```bash
   cp -R data data-film && cp plan.json data-film/plan.saturday.json
   INKY_DATA=data-film .venv/bin/python app/serve.py          # http://127.0.0.1:8765
   ```
   Add `?rec=1` to every app URL: it is the recording mode (the 1440-wide design scaled to the window, slower motion).
   Afterwards, `cp data-film/plan.saturday.json plan.json` (the interview saves plan.json in the repo root).
5. **Screen Studio**, for every Mac shot:
   - Recording: *Window* for Chrome shots, *Display* for the race and ⌥ Space (they cross windows). 60 fps. Microphone and system audio off (the voice-over goes on later).
   - Cursor: size 1.4, smoothing on, hide when idle on, click sound off.
   - Zoom: automatic zoom on clicks at 1.6×, follow cursor on. Off for the race and the n8n glide, which get manual zoom keyframes instead.
   - Background: solid `#F7F6F3`, padding 48, corner radius 12, soft shadow. Race: no background, full bleed.
   - Export: 1920×1080, 60 fps, MP4, high quality. One file per beat: `b1-wake.mp4`, `b2-ask.mp4` … `end.mp4`.
6. **Phone**: iPhone Screen Recording from Control Center. Put the other Telegram chats in an archive or a folder, so only Inky's chat shows.

---

## 1 · Wake-up (0:00–0:08)

- **Screen**: the phone, portrait.
- **Record**: start the screen recording at 07:59 with the phone locked. The 08:00 digest arrives → tap the notification → Inky's chat opens → hold on the message with the homes → tap the top home.
- **Edit**: centre the portrait video on a dark 1920×1080 frame. Then a 1 s card, "The day before", and a hard cut.
- **Plan B**: no new match overnight: in the app, Results → **Send me the best 3 now** sends the top 3 to Telegram with buttons. Record the phone receiving it and use the fallback line in script.md. No Telegram at all: open on the app's Results screen and drop the phone.

## 2 · Describe it, it asks (0:08–0:22)

- **Screen**: Chrome 1440×900, `http://127.0.0.1:8765/?rec=1#home`, on the film copy.
- **Clicks**: click the chat box → type (or paste; the edit plays it at 2×):
  `I live in the Netherlands and have €200,000 in cash. Where can I earn the most renting out a flat, somewhere prices are rising and buying is easy for me?`
  → Start → Plan: the questions and "I assumed…" lines arrive (cut the wait) → answer with the chips, or Skip → Your plan: hold 2 s on the one-sentence plan, move the cursor over "What I may do alone" → move to **Yes, start research** and stop there.
- **Careful**: clicking **Yes, start research** really runs the research again (GLM, on the film copy), so its numbers can differ from Saturday's. The S1 transition does the click in the edit. If you click it anyway, reset before beat 3: `rm -rf data-film && cp -R data data-film`, then restart the server.
- **Plan B**: GLM slow or down: `http://127.0.0.1:8765/?rec=1&replay=1#task` replays the last finished interview in this browser at a readable pace, with nothing sent (label it "replay" in the edit). Needs one full real take first. Or open `#confirm` straight away with the saved plan.

## 3 · It reads the market (0:22–0:40)

- **A. Apify console (6 s)**: `https://console.apify.com/actors/runs`. Scroll to Saturday's runs of `igolaizola/idealista-scraper`, `memo23/immobiliare-scraper` and `trev0n/otodom-scraper`, with their result counts and costs. Glide down slowly (manual zoom keyframe).
- **B. Inky (12 s)**: `http://127.0.0.1:8765/?rec=1#research` on the unchanged copy. Hold on "17,836 listings · 39 neighbourhoods", then click the versions v1 → v2 → v3 on the right, about 2 s each, so the count goes 15 → 70 → 46.
- **Edit**: lower third, "Łódź 32 · Bari 14 · Porto 0 (prices +17.8% a year, Eurostat 2026-Q1). Otodom belongs to OLX, a Prosus company."
- **Plan B**: Apify console slow: a screenshot of Saturday's Runs list, stamped "Saturday". The Research screen reads `data-film/research.json` locally and needs no network. Last resort: `.venv/bin/python app/serve.py --demo`.

## 4 · Learns a site, ships an actor (0:40–0:56)

- **A. learn.py (7 s)**, Terminal plus the Chrome window it opens (1440×900, headed). One GLM call, about $0.02. `--out` keeps the saved program as it is:
  ```bash
  .venv/bin/python teach/learn.py --slow --size 1440x900 --out data-film/tecnocasa.program.json
  ```
  Record the Chrome window. The clicks go through the page, not the mouse, so add manual zoom keyframes on each coral mark. End on the chip "8 steps became 1 request".
- **B. Actor page (3 s)**: `https://console.apify.com/actors/d3z9fAUDHkB8hOxmO` (cavernous_stew/inky-tecnocasa-homes), then the test run `https://console.apify.com/view/runs/CTQzApy35x6ktt7Uv` (20 results). For a fresh run: `.venv/bin/python teach/publish.py --run-only` (about $0.0001) and record its run page.
- **C. Race (6 s)**: Screen Studio on *Display*, nothing else on screen. About $0.05–0.15 of GLM for the agent window:
  ```bash
  .venv/bin/python race/race.py --seconds 60 --out data-film/race.json
  ```
  In the edit, play the first 20 s at 4× until all 8 windows are done, with a big counter: "96 flats · 19.7 s · 0 model calls". Caption the grey agent window: "click-by-click AI agent: 30 in 60 s, 5 model calls, $0.085". Use the numbers of your take if they differ, and say those.
- **Plan B**: Chrome flaky: `.venv/bin/python teach/run_program.py --pages 2 --browser --headed` replays the same steps with no model and no key. Race fails: the app's Turbo screen `?rec=1#fast` with Saturday's race.json. The actor page is static and always loads.

## 5 · Runs in n8n, no AI (0:56–1:10)

- **Screen**: Chrome 1440×900, `https://YOUR-N8N.app.n8n.cloud/workflow/YOUR-MAIN-WORKFLOW-ID/executions` (both workflow ids are in `data/n8n.json`, or open the links from the app's Workflow screen). Open a green run from last night: the canvas shows every node with a green check and its item count.
- **Clicks**: fit the view (the fit button at the bottom left) → manual zoom keyframes from left to right: the 15-minute trigger → the 5 Apify steps → Merge → **Score · rules** → click it to show that it's a Code node and how long it took (about 1.8 s) → Telegram → Gmail draft. Then back to the executions list and scroll through the night's runs.
- **Count for the voice-over**: the runs since Sat 23:00 in this list → `[forty]`. Listings checked → `[eight thousand]` (the app's Activity screen, or the "last night" summary).
- **Careful**: only look. Don't press Execute, Save or the Active switch on the live workflow.
- **Plan B**: n8n slow: the app's `?rec=1#workflow` screen (the same steps, from the n8n API) or a screenshot of the canvas. No overnight totals: use the fallback line.

## 6 · It fixes itself (1:10–1:25)

- **Screen**: Chrome 1440×900.
- **Clicks**: `https://YOUR-N8N.app.n8n.cloud/workflow/YOUR-MAIN-WORKFLOW-ID/executions` → the red run on Saturday around 23:30 → the red otodom step → zoom on the error. Then `https://YOUR-N8N.app.n8n.cloud/workflow/YOUR-REPAIR-WORKFLOW-ID/executions` → the repair run from the same minute → click **Patch the step** → zoom on its output, "Changed searchType from 'sale' to the allowed enum value 'sprzedaz'" → **Tell me it's fixed**. Back to the main executions: the green rerun right after.
- **Insert (optional, 2 s)**: a screenshot of the phone's Telegram at 23:30, "Fixed otodom · Łódź: … Running it again now."
- **Edit**: stamp "REAL · n8n · Sat 23:30". Caption: "Broken on purpose, as a test. At most one fix an hour."
- **Plan B**: n8n slow: the repair entry on the app's `?rec=1#activity` screen. Nothing works: break a staging copy of the workflow the same way at 12:00 (never the live one) and record that run.

## 7 · Talk to it, approve (1:25–1:41)

- **A. ⌥ Space (6 s)**, Screen Studio on *Display*: the film-copy server running, another app in front (Notes with an empty note works). Hold ⌥ Space → say "only places with the euro" → let go → the pill: Listening… → Thinking… → the change and "46 → 14 homes". Manual zoom keyframe on the pill (bottom centre). Optionally 2 s of `?rec=1#results` with 14 homes.
- **B. Phone (5 s)**: an Inky question in Telegram with **Save as draft** and **Skip** → tap **Save as draft**.
- **C. Gmail (4 s)**, Chrome 1440×900: Gmail → Drafts → open the new draft to the agent. Move the cursor next to Send and stop, then cut. **Don't click Send.**
- **Plan B**: ⌥ Space doesn't fire: in Terminal, `.venv/bin/python voice/listen.py --seconds 4` (the same local whisper.cpp path; Terminal needs the microphone). No mic: `.venv/bin/python voice/listen.py --text "only places with the euro" --dry-run` changes nothing and shows the effect (say "typed", not "said"). No question waiting in Telegram: Results → **Send me the best 3 now**.

## Flash · Share it (1:41–1:44)

- **Screen**: Chrome 1440×900, `http://127.0.0.1:8765/?rec=1#share` → who it's for: "my sister" → Inky writes what the agent does (one GLM call) → 2 s. Then `?rec=1#market` for 1 s, with its "Preview" label in view.
- **Plan B**: cut it and hold the end card 3 s longer.

## End card (1:44–1:52)

- **Screen**: the app's end screen (`?rec=1#end`, with the real totals). Or the EndCard artboard in the storyboard canvas, in Play, full screen, or exported as a 1920×1080 PNG.
- **Record**: still, 8 s, no cursor. The QR opens github.com/GHGuide/inky; check it with a phone before the final export.
- **Plan B**: the exported PNG as a still.

---

## Before you export

- Every number spoken is on screen in the same shot, or in a caption.
- Captions: burn in `captions.srt` (fill in the placeholders first).
- Length: at most 2:00. Target 1:52.
- Nothing personal in view: other Telegram chats, Gmail inbox rows, browser tabs, API keys (n8n credentials pages are never opened).
