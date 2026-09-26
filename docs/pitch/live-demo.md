# Live final, 16:15: the 2-minute walkthrough

One person talks, one drives. Every number below is real (Saturday's runs); fill in the two overnight ones at 15:30.

## At 15:45: set up

- Laptop on power, Do Not Disturb on, ChatGPT/Raycast/Alfred quit (they take ⌥ Space). Phone on Wi-Fi, Focus letting only Telegram through, brightness up.
- The app on the film copy, so nothing done on stage can change Saturday's numbers or the live workflow:
  ```bash
  INKY_DATA=data-film .venv/bin/python app/serve.py
  ```
- Chrome, the "Inky film" profile, one window at 1440×900, these tabs in this order:
  1. `http://127.0.0.1:8765/?rec=1#results`
  2. `http://127.0.0.1:8765/?rec=1#research`
  3. `https://YOUR-N8N.app.n8n.cloud/workflow/8PuVKxiSlGuJO4CU/executions` (a green run from the night already open)
  4. `https://YOUR-N8N.app.n8n.cloud/workflow/s1PH8DN9pBhQ7pky/executions` (the 23:30 repair run already open on "Patch the step")
  5. Gmail → Drafts
- The recorded video open in QuickTime, paused on the first frame, on the second desktop.
- Test the hotspot on the phone once. Test ⌥ Space once.

## The two minutes

| Time | Screen | Say |
|---|---|---|
| 0:00–0:15 | the phone, held up: this morning's Inky message | "Good flats go in days. You'd have to check three portals in three languages, every day, and do the maths on every listing. I told Inky once what I want. This morning it sent me these." |
| 0:15–0:35 | tab 2, Research: click v1, v2, v3 | "It read 17,836 real listings through Apify, in Porto, Bari and Łódź. An open model, GLM-5.3, wrote rules and the data tested them, three rounds: 15, 70, 46 homes. Łódź wins, 6.5% after costs. Porto's prices rose 17.8% last year, but the rents don't pay. Most of the winners are on Otodom, which is OLX, which is Prosus." |
| 0:35–0:55 | tab 3, n8n: the green run, point at each node | "Inky built this n8n workflow itself, through the API. Every 15 minutes: five Apify scrapers, then scoring compiled into this Code node. No AI in the loop. Overnight it ran [N] times and checked [N] listings." |
| 0:55–1:15 | tab 4, the repair run | "Last night at 23:30 we broke a step on purpose. n8n caught the error, the model read it, changed one field of the input, published the fix and reran: 7.3 seconds. It messaged me after. At most one fix an hour; after that a human decides." |
| 1:15–1:45 | tab 1, Results → **Send me the best 3 now**; phone: tap **Save as draft**; tab 5, Gmail Drafts | "Now live. I ask for the best three… here they are on my phone. I tap Save as draft… and the email to the agent is waiting in Gmail. It never sends anything for me." |
| 1:45–2:00 | the end card, or the QR on the phone | "Inky. Tell it once. It's open source, the model is open, and it's all on GitHub." |

If there's time left, the extra: hold ⌥ Space, "only places with the euro": 46 → 14 homes (the film copy, so the live workflow keeps Łódź).

## Fallback plan

| If this fails | Do this |
|---|---|
| Venue Wi-Fi | Phone hotspot. The app and its Research, Results and Turbo screens run from local files and need no network. |
| n8n Cloud slow or down | Skip tabs 3 and 4 and play the video from 0:56 to 1:25 (beats 5 and 6). Say the same lines. |
| The best-3 message doesn't arrive in 10 s | Scroll up in Inky's Telegram chat to an earlier question and tap Save as draft on that one. |
| Gmail slow | Move on, and open Drafts again at the end. |
| GLM/OpenRouter down | Nothing on the main path needs it. Skip the ⌥ Space extra. |
| The app won't start | `.venv/bin/python app/serve.py --demo` (bundled snapshot, no keys, no network), if it is in the repo by then. Otherwise play the video. |
| The laptop | Play the video from the phone (AirDrop it there at 15:30) and walk through it with the same lines. |
| Everything | Play the 1:52 video, then take questions. |

Things not to do on stage: press Execute, Save or the Active switch in n8n; click Send in Gmail; run `learn.py` or `race.py` (they take the whole screen and need the network).
