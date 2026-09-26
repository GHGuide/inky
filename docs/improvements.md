# Inky: everything that could be better

Written Sun 27 Sep, 00:10. Video due 15:00, live final 16:15.
P0 = the video depends on it · P1 = clearly better · P2 = nice if time allows.
**me** = Claude overnight · **you** = only you can do it.

Overnight rules I follow:
- Never break the live workflow that is collecting proof tonight: n8n changes are tested on a staging copy first, and deployed once, keeping the workflow's saved state.
- No Telegram messages between 23:00 and 07:00.
- At most $5 extra on Apify.
- Nothing is ever sent to anyone.
- Commits go to the `build` branch only.

## A. The video (Presentation 15%)
- [x] A1 P0 me: Recut the storyboard from 12 to 7 beats: wake-up → describe, it asks → Apify research → learns a site → runs with no AI in n8n → fixes itself → talk and approve → end card. Marketplace and sharing become a 3 s flash.
- [x] A2 P0 me: Final voice-over script with real numbers, one line per beat, timed at about 2.2 words per second (docs/video/script.md).
- [x] A3 P0 me: Shot list: for each beat, the exact screen, command, window size and click path, plus plan B (docs/video/shots.md).
- [x] A4 P1 me: Recording mode in the app (`?rec=1`): 1920×1080-friendly scale, no scrollbars, slower and bigger animations, cursor-safe margins.
- [x] A5 P1 me: Replay mode for the interview: plays a real, saved interview session at a readable pace, so the take is clean. Labelled as a replay.
- [x] A6 P1 me: Captions file (SRT) generated from the script.
- [x] A7 P0 me: A real QR code for the repo on the end card (SVG, no image service).
- [x] A8 P1 me: End card as an app screen (`#end`), so the last shot is recorded live with the real totals from last night.
- [x] A9 P2 me: Submission thumbnail.
- [ ] A10 you: Record (Screen Studio or QuickTime), voice-over in your cloned voice, edit, submit by 15:00.

## B. Proof of real use (25%)
- [x] B1 P0 me: "Send me the best ones now" (app command and a webhook branch in n8n): the top 3 real matches go to your Telegram with buttons, and your tap creates a real Gmail draft. You'll have the approval shot even if the night finds nothing new.
- [ ] B2 P0 you: 1–2 real people (friend, family) describe a goal in Inky in the morning. Film their reaction and get one quote.
- [x] B3 P0 me: "Last night" summary from the real n8n and Apify data: runs, listings checked, new listings, matches, fixes, Apify cost, AI calls. Feeds Activity, the end card and the voice-over.
- [x] B4 P1 me: Cost per run from the Apify API. Headline: "$0.20 a run, 0 AI calls".
- [x] B5 P1 me: Better 08:00 digest: new listings checked, matches, any fix, and the best current home when there's nothing new.
- [x] B6 P1 me: Quiet hours. Matches found at night wait for the 07:00 message instead of waking you.
- [x] B7 P1 me: More fresh listings per run (60 newest per site) and Inky's own Tecnocasa actor as a 5th source (D2).
- [ ] B8 P2 me: "Almost" tier: homes that miss one rule by a little, marked as such, only in the digest.

## C. Autonomy (25%)
- [x] C1 P0 me: "Yes, start research" in the app really runs the research. GLM derives the rules from the plan you just gave, on the scraped data, and streams each step into the chat live (like Claude Code). Results then follow your answers.
- [x] C2 P0 me: "Yes, watch them" really builds and publishes the n8n workflow and streams the steps (credentials, nodes, published) with links. Tested on staging.
- [x] C3 P0 me: The finished interview saves the plan (plan.json, with a backup), so research uses what you said.
- [x] C4 P1 me: More failures it can repair: a site returns items Inky can't read (schema drift), as well as bad requests and empty results.
- [x] C5 P1 me: Repair audit trail: before/after of every fix, shown as a diff in the app.
- [x] C6 P1 me: Visible guardrails: a daily Apify spend cap in the workflow, at most one fix per hour (exists), asks before any draft (exists).
- [ ] C7 P2 me: Re-learn path: when the Tecnocasa program breaks, the repair re-runs learn.py headless.

## D. Apify & n8n (20%)
- [ ] D1 P0 you: Install the Apify node (Inky workflow → N → "Apify" → Install). The next deploy switches to it automatically.
- [x] D2 P1 me: Inky's own published actor (`inky-tecnocasa-homes`) as a live source, with its neighbourhoods matched to the rent data by nearest coordinates.
- [x] D3 P1 me: Sticky notes on the n8n canvas that explain each part (read, score, ask, draft, repair). Judges opening n8n understand it in 10 s.
- [x] D4 P1 me: Tidy canvas layout, and an "inky" tag on both workflows.
- [x] D5 P1 me: Both workflows exported to the repo (credentials stripped) so anyone can import them.
- [x] D6 P1 me: Lower Apify cost per run (memory and timeouts per actor).
- [ ] D7 P2 you: Decide whether to publish the Tecnocasa actor in the Apify Store.

## E. Problem fit and trust in the numbers (15%)
- [x] E1 P1 me: "Why 6.8%?" on every home: rent estimate (from N rentals nearby at €X/m²) minus agency 9%, vacancy 8%, upkeep, rent tax, buying costs.
- [x] E2 P1 me: Honest labels: price trend is per country (Eurostat 2026-Q1), Łódź districts are approximate, yields are estimates.
- [x] E3 P1 me: Best per city, even where nothing passes. "Porto: prices +17.8% a year, but the best yield after costs is only X%."
- [ ] E4 P2 me: Neighbourhood map per city (plain SVG from the coordinates), coloured by yield.
- [ ] E5 P2 me: Ten-year view per home: rent income plus price growth, clearly marked as an estimate.
- [ ] E6 P2 me: Evidence that speed matters: how fast listings disappear or get replaced, from the listing dates.
- [ ] E7 P1 me: One sharp problem line on the home screen and in the README: "Good listings go in days. Inky watches every 15 minutes, you only decide."

## F. App: UX and UI
- [x] F1 P1 me: Workflow stages show totals since the start and the last match, not a dead "0 · 0 · 0".
- [x] F2 P1 me: Results: what's new since you last looked, city and yield filters, "best now" pinned on top.
- [x] F3 P1 me: "Preview" labels on mock parts (marketplace, sample agents), so they don't cast doubt on the real parts.
- [x] F4 P1 me: Race wording: "all 96 Bari flats under €200k in 19.7 s". Explain or hide empty windows.
- [ ] F5 P1 me: Interview: show the defaults that "Skip" picks. Voice button works. Editable plan before research.
- [x] F6 P1 me: Loading skeletons (shimmer) instead of empty flashes on first load.
- [x] F7 P1 me: Toasts for things that happen ("Saved to n8n ✓", "Sent to Telegram ✓").
- [x] F8 P1 me: Activity: expand a run to see listings per site, matches, time and cost (replay idea, as in Manus).
- [ ] F9 P2 me: "Last night" time-lapse on Activity.
- [x] F10 P1 me: Home suggestion chips lead somewhere real, or are removed.
- [x] F11 P1 me: Layout check at 1280, 1440 and 1920 wide.
- [x] F12 P1 me: Accessibility: focus rings, aria-live chat, contrast.
- [x] F13 P2 me: Keyboard: `/` focuses the chat, 1–5 switch tabs.
- [x] F14 P1 me: Favicon and page titles.

## G. Computer control
- [x] G1 P1 me: learn.py for filming: `--slow` pace, every step scrolled into view before its coral mark (the next-page mark was off-screen), a clear step caption.
- [x] G2 P1 me: race.py for filming: a 1920×1080 layout, a summary window at the end, a big live counter.
- [x] G3 P2 me: "Inky has the screen" coral frame around the whole screen while learn or race runs (Hammerspoon).

## H. Voice
- [ ] H1 P0 you: Hammerspoon permissions (Accessibility, Downloads, Microphone) and clear ChatGPT's ⌥ Space.
- [x] H2 P1 me: The voice pill shows the effect ("46 → 14 homes").
- [x] H3 P1 me: Voice troubleshooting steps in voice/README.md, for the morning.

## I. Sharing
- [ ] I1 P1 me: Real sharing. "Share" creates a bundle: plan, rules, both workflows without credentials, and a README. `share/import.py` sets it up in another n8n through the API. Tested with a copy in your n8n.
- [ ] I2 P2 me: The marketplace lists real bundles from a folder instead of hard-coded cards.

## J. Reliability, safety and cost
- [x] J1 P0 me: A staging copy of both workflows for every test. The live one is deployed once, keeping its saved state (seen listings, counters).
- [x] J2 P1 me: Telegram questions expire after 24 h, so waiting runs don't pile up.
- [x] J3 P1 me: The same flat on two sites counts once (city, price, size).
- [ ] J4 P2 me: The repair checks that the fixed step works before it publishes.

## K. Repo and open source
- [ ] K1 P0 you: Decide on the MIT license (the end card says MIT). Then me: add LICENSE.
- [ ] K2 P0 you: OK to merge `build` into `main`. Then me: merge.
- [x] K3 P1 me: README rewrite: one-line pitch, a 60-second quickstart without keys, a diagram, real results, screenshots, honest licensing.
- [x] K4 P1 me: Demo mode without keys: `app/serve.py --demo` with a bundled data snapshot, so anyone who clones it sees the app working.
- [x] K5 P1 me: GitHub Actions CI running the offline tests.
- [x] K6 P1 me: docs/architecture.md (diagram, data flow, what runs where, what's AI and what isn't).
- [x] K7 P1 me: Secret scan of the whole git history before any merge.

## L. Live final at 16:15
- [x] L1 P1 me: A 2-minute live walkthrough script, and a fallback plan if Wi-Fi or n8n fails (the recorded video plus local demo mode).
- [x] L2 P1 me: Judge Q&A sheet with short answers:
  - Isn't this n8n's AI builder?
  - How accurate are the yields?
  - What if a site blocks you?
  - What does it cost?
  - Privacy?
  - Business model?
  - Why Prosus/OLX?
- [x] L3 P2 me: A 3-slide backup deck.

## M. Security
- [ ] M1 you: Rotate every key after the weekend (they were pasted in chat).
- [x] M2 P1 me: Scan every commit for secrets (same as K7).
