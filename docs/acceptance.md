# Inky · acceptance criteria

Every release is checked against this page. It turns [vision.md](vision.md) into pass/fail checks.
A check passes only when it works **first time, in the real app, on real sites, with a capable model** (gemma3:12b or a cloud key), and every message the app shows is true.

How each check is run: **J** = `python -m tests.journeys <name>` (automatic), **U** = unit tests (`python -m unittest`), **M** = by hand in the built app (a person or an agent driving the real window).

---

## A. The five-bot test (release gate)

A release ships only when one person can create these five bots from plain sentences, leave them alone, and come back to correct results. Each starts from the New bot screen with only the sentence below.

| # | Bot | Sentence typed on New bot | Kind |
|---|---|---|---|
| 1 | Book Bargains | "Every morning, find books under £20 on books.toscrape.com" | Watch, one site, several pages |
| 2 | E-bike Hunter | "Find second-hand e-bikes under €1500 in the Netherlands" | Watch, sites found for you, batch learning |
| 3 | Python Jobs | "Tell me about new remote Python jobs on python.org" | Watch, list without prices |
| 4 | HN Watch | "Every hour, tell me new Hacker News front page stories about AI" | Watch, title rule, hourly |
| 5 | Contact Form | "Send the message 'Is the flat still free?' through the contact form on http://127.0.0.1:8766/contact" | Do, local test site only |

For **each** of the five, all of these hold:

1. **Draft** — the name, job, schedule and rules match the sentence; no made-up rules; numbers only from the sentence (£20, €1500). *(J)*
2. **Sites** — a site named in the sentence is used as-is; otherwise at least 3 real, reachable sites are suggested and "Check all" learns them one after another with one progress line. *(J)*
3. **Learn** — learning finishes without asking you, in at most 12 AI calls per site, and the saved skill reads the right list (titles, and prices when the site shows them). An empty or nameless read is never saved. *(J)*
4. **Repeat for free** — the first check after learning uses 0 AI calls and returns the same items. *(J)*
5. **Correct results** — every item on Found is a real item from that site, with a working link; rules are applied (nothing over £20 / €1500, only AI stories). Spot-check 5 items by opening them. *(M)*
6. **Autonomous** — with the app left alone, the schedule fires on time ("tomorrow at 08:00", "in 52 min") and a later run marks **only truly new** items as new. *(J for timing, M for overnight)*
7. **Tells you** — new items arrive as one chat message, one notification (and Telegram when connected); "what did you find?" matches the Found tab exactly. *(J)*
8. **Handles its own problems** — a timeout, an offline network or a changed page is retried quietly; you are only asked after 3 failures in a row, and the card says what happened in one plain sentence. *(J)*
9. **Do bot only (5)** — it asks before sending; Approve sends **exactly once**; Deny sends nothing; "Always for this step" is never asked again; a renamed button is fixed by itself or by "Show me once". *(J `do`)*
10. **Stop** — Pause, Stop and "stop the model" each take effect within 2 seconds, and the bot says what it stopped. *(J `stop`)*

The test report records, per bot: sites, AI calls to learn, items found, items spot-checked, next run time, and any message that wasn't true.

---

## B. Setup and models

1. A fresh install reaches a working, **tested** model in 3 steps (Welcome, Model, Ready) with no terminal. *(J `newuser`)*
2. The recommended choice is the best that fits this computer (a cloud key, or the biggest local model that fits in memory). A model too small to learn sites shows a clear warning before it's picked. *(U)*
3. If Ollama or a model is missing, the app says exactly what to do and offers to get it (download only after you say yes). *(M)*
4. The model that is working right now is always visible while it works, with a Stop button. *(J `stop`)*
5. Keys go into the system keychain, are never shown again in full, never logged, never sent anywhere but their own service. *(U)*

## C. Chat with a bot

1. Plain commands work without the model: run, pause, resume, every morning / hourly / at 9, only keep under X, forget that rule, what did you find, how is it going. *(J `chat`)*
2. Every reply is true: if it says it changed a rule, the rule changed; if it says it ran, a run exists. *(J `chat`)*
3. Questions it can't answer from its own data say so, rather than guessing. *(M)*
4. Long jobs show live progress in one message that updates, not a stream of messages. *(J `batch`)*

## D. Connectors

Connectors are secondary (vision.md). Each one shown in the app must pass all of these; anything that can't is hidden, not shown half-working.

**Every connector card**

1. Shows one plain status: *Not set up*, *Connected*, or *Problem: <one sentence>* with one button that fixes it or one link that explains it. *(U, M)*
2. Uses the real brand logo, never a generic or AI-looking picture. *(U `test_logos`)*
3. Has **Test**, which does a real round trip and reports the true result within 10 seconds. *(M)*
4. Connecting takes at most 3 steps, and secrets are pasted once into a password field, never echoed. *(M)*
5. **Disconnect** removes it fully, including its stored secret. *(U)*
6. A connector failing never stops a bot; the bot carries on and the card shows the problem. *(U)*

**Per connector**

| Connector | Passes when |
|---|---|
| Telegram | Test sends you a message; a bot's new items arrive there within a minute of the run; a question a bot asks you can be answered from Telegram. |
| n8n | Test lists your workflows; "Send to n8n" creates a workflow that runs the bot and returns its results. |
| Apify | Test shows your account; a bot can run an Apify actor and use the items it returns. |
| Claude Code / Codex (Inky uses them) | Shows installed and signed in; a bot can hand a step to them and gets the answer back; nothing writes files unless you allowed it. |
| Inky as an MCP server (they use Inky) | From Claude Code or Codex: list bots, run one, read its results, read Needs you. Approving is never a tool. Adding Inky to their config happens only when you click the button. |
| Other MCP servers | Adding by command shows its tools; a broken command shows the error in one sentence. |
| Other computers | Add by pair link, SSH or "found on your network" in at most 3 steps; move a bot there; it runs and its results show here; an offline computer is shown as offline, never as working. |
| Phone | Alerts reach the phone (Telegram or notification); the page fits a 375 px screen with no sideways scroll. |

## E. Screen control (bots using your screen)

1. Off by default. Turning it on asks once, in plain words, what the bot will be able to do. *(M)*
2. A bot set to "Works in a window on your screen" opens **one** browser window, with a pill showing the bot's name and its current step. *(M)*
3. **Esc** stops it within 2 seconds; moving your mouse in the window takes over and pauses it ("Paused · you have the screen"); Resume carries on from the same step. *(M)*
4. ⌥C (Alt C) opens chat while it drives. *(M)*
5. The window closes by itself when the run ends, unless you took over. *(U)*
6. The Watch tab never opens a window on your screen just to show it; for bots on their own computer it shows the live picture. *(U)*
7. It never types passwords, never solves a robot check, and asks before anything that can't be undone, the same as on its own computer. *(U, J `do`)*

## F. Clean, simple UI

1. **One main action per screen**, in the brand colour; everything else is secondary or folded under More. *(M)*
2. **Plain words** on the main path. None of these words appear outside Settings → Advanced: skill, selector, MCP, headless, engine, token, LLM, API, JSON, regex. *(U: a word scan over views.js)*
3. Sidebar: New bot, your bots, Needs you, More. A bot opens on Found; tabs are Found, Watch, Settings, More. *(U `test_ui_wizard`)*
4. Every empty screen says what will appear there and offers one next step. No dead ends: every screen has a way back. *(M)*
5. Every error is one sentence saying what happened and what to do, with a button when there's a fix. No stack traces, no codes. *(M)*
6. Layout: one spacing scale, one radius, one type scale; nothing overlaps or overflows at 375 px, 1024 px and 1440 px, in light and dark. *(J `newuser` phone width, M)*
7. Contrast meets WCAG AA; every control is reachable by keyboard with a visible focus ring; motion is calm and respects "reduce motion". *(M)*
8. No page errors in the console on any screen. *(J `newuser`)*
9. Loading states show within 200 ms; nothing jumps when data arrives. *(M)*
10. Needs you only holds things that truly need you (a yes, a "show me once", a password you must type yourself). Anything the bot handled itself is one quiet line in "Handled by your bots". *(J `handled`)*

## G. Safety and honesty (always)

1. Asks before sending, buying, deleting, signing up or accepting terms; never types passwords or card numbers; never solves CAPTCHAs or robot checks. *(U, J `do`)*
2. What the app says always matches what happened (runs, counts, sends, rules). *(J)*
3. No Inky server, no account; everything runs on your computer with your keys. *(M)*
4. Searching for sites is gentle (cached, paused when a search engine pushes back), and falls back to the model's suggestions, each checked for reachability. *(U)*

## H. Share

1. Copy a share link → paste it on another Inky → see a preview (what it does, which sites, what it will ask) → Get → it runs there. *(J `share`)*
2. The shared bot carries no secrets, no results and no personal data. *(U)*
3. A bot from the public library that hasn't been checked says so before you get it. *(U)*

---

## Release checklist

1. `python -m unittest` passes; CI is green on `build`.
2. `python -m tests.journeys` passes in full (with `python -m tests.site_server 8766` for `do`).
3. Section A passes for all five bots, including one overnight run.
4. Sections D and E pass by hand on the built app.
5. The test report in `docs/superpowers/` lists what was run, what passed, and anything not checked.
