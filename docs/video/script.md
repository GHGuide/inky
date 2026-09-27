# Inky: Round 1 video, voice-over script

Target 1:52 (max 2:00), 7 beats, a 3 s flash and the end card. 224 words, 2.0 words a second on average (limit 2.2).
One block per clip. Generate each clip on its own in the cloned voice, so one can be redone without the rest.
The storyboard with thumbnails, camera notes and plan B: https://claude.ai/artifact/NQorqMxkSQ5WMvQt1BxW4d (page "Demo video").
Shots and click paths: [shots.md](shots.md). Captions: [captions.srt](captions.srt) (generated from this file, digits instead of words).

## Fill these in before recording

Filled in on Sunday at 08:30 from the 08:00 digest: 36 runs and 9,009 listings checked overnight, 332 new, 1 match, 1 fix. The digest listed no homes, so beat 1 uses the "Send me the best 3 now" line. The end card reads its totals live from the app.

If a placeholder can't be filled, use the fallback line in its block. Never round up.

## Pronunciation

Łódź: "Woodge". GLM is never spoken. n8n: "n-eight-n". Tecnocasa: "tek-no-KAH-sah". Libertà is not spoken. 

---

### 1 · Wake-up · 0:00–0:08 (8 s, 17 words, 2.1 w/s)

> Good flats go in days. Inky just sent me the three best that fit my plan.

On screen: the phone, Telegram: press "Send me the best 3 now" in the app's Results thread first, then film the three messages arriving; the thumb opens the top home and taps "Save as draft".
(Sunday's 08:00 digest had only counts, "36 runs · 9,009 listings checked · 332 new · 1 match · 1 fix", no home to show, so this is the line to use.)

### 2 · Describe it, it asks · 0:08–0:22 (14 s, 30 words, 2.1 w/s)

> I described it once: two hundred thousand euros, a flat to rent out, prices rising, easy for a Dutch buyer. Inky asked what it couldn't guess, then wrote the plan.

On screen: Home → one sentence typed at 2× → Plan (questions with "I assumed…" lines) → Your plan.

### 3 · It reads the market · 0:22–0:40 (18 s, 37 words, 2.1 w/s)

> Through Apify it read nearly eighteen thousand real listings in Porto, Bari and Łódź. An open model wrote rules, and the data tested them: fifteen, seventy, then forty-six homes. Porto's prices climb, but the rents don't pay.

On screen: Apify console Runs (idealista, immobiliare, otodom Store actors, $17.49 in total), then Research: 17,836 listings, 39 neighbourhoods, v1 → v2 → v3 = 15 → 70 → 46.
Lower third: "Łódź 32 · Bari 14 · Porto 0 (prices +17.8% a year, Eurostat 2026-Q1). Otodom belongs to OLX, a Prosus company."

### 4 · Learns a site, ships an actor · 0:40–0:56 (16 s, 33 words, 2.1 w/s)

> Tecnocasa, Italy's largest agency network, had no Apify scraper. Inky used it once, found its data feed, and published its own Apify actor. Eight windows, no model: ninety-six flats in under twenty seconds.

On screen: learn.py in Chrome (10 steps, 1 GLM call, chip "8 steps became 1 request"), the actor page `cavernous_stew/inky-tecnocasa-homes` (test run 20 of 20), then race.py: 96 flats in 19.7 s, 0 model calls. Caption on the grey agent window: "Click-by-click AI agent: 30 in 60 s, 5 model calls, $0.085".

### 5 · Runs in n8n, no AI · 0:56–1:10 (14 s, 26 words, 1.9 w/s)

> Inky built this n8n workflow itself, through the API. Every fifteen minutes, five Apify scrapers feed compiled scoring. No AI. Last night: thirty-six runs, nine thousand listings.

On screen: the n8n canvas (5 Apify steps → Merge → Score, a Code node running inky.js in about 1.8 s → Telegram approval → Gmail draft; 08:00 digest), then Executions.
Fallback (no overnight totals): "…five Apify scrapers feed compiled scoring. No AI, all night long."

### 6 · It fixes itself · 1:10–1:25 (15 s, 30 words, 2.0 w/s)

> I broke one step on purpose. n8n caught the error. The open model read it and fixed the input in seven seconds, then published and reran. It told me after.

On screen: Executions, Sat 23:30: the red run (otodom input), the repair run with "Changed searchType from 'sale' to the allowed enum value 'sprzedaz'" (7.3 s), the green rerun.
Caption: "Broken on purpose, as a test. At most one fix an hour."
Only if a real overnight failure was repaired and you show that one instead: "At [time] a step broke. n8n caught it, the open model fixed the input in [seconds] seconds, published and reran. It told me after."

### 7 · Tell it, approve · 1:25–1:41 (16 s, 32 words, 2.0 w/s)

> I type one line: "only places with the euro." Forty-six homes become fourteen. On Telegram I approve one; the email to the agent waits in Gmail, as a draft. Inky never sends.

On screen: the Results chat (the line typed → the change → "46 → 14 homes"), the phone tap on “Save as draft” in Telegram, the draft in Gmail. Caption: "Draft only. Inky never sends."
If the reply shows other counts (rules changed overnight), say those.

### Flash · Share it · 1:41–1:44 (3 s, 5 words)

> Share it in a sentence.

On screen: 2 s of Share (Inky's description, budget kept out), 1 s of the marketplace with its "Preview" label.

### End card · 1:44–1:52 (8 s, 12 words)

> Inky. Tell it once. It watches every fifteen minutes; you only decide.

On screen: the end card: "Tell it once.", "Good listings go in days. Inky watches every 15 minutes with Apify and n8n. You only decide.", Saturday's totals, the overnight [N]s, the QR to github.com/GHGuide/inky, "Open source (MIT) · open models (GLM-5.3)", "n8n is fair-code · Apify's platform is hosted". Hold 2 s after the last word.

---

## What the voice never says

- That a model picks the clicks. The compiled program replays them; the model is called once when learning, and again only to repair.
- "Fully open source". Say "open source" for Inky's code and "open model" for GLM-5.3.
- That the 23:30 failure happened by itself. It was broken on purpose.
- That anything is sent. Gmail gets drafts only.
