# Inky: test report, 2026-10-02

Branch `build`. Checked against [docs/acceptance.md](../acceptance.md), written this round together with [docs/agent-prompt.md](../agent-prompt.md).
Model: gemma3:12b in Ollama, on this Mac. Every engine used a scratch home; your `~/.inky` was only read, never written. Do bots sent only to the local test site.

Unit tests: `.venv/bin/python -m unittest`: **96 tests, OK** (the 2 install.sh tests skip without Docker).

## A. The five-bot test (release gate)

`python -m tests.journeys five` creates the five bots from their sentences only, the way the New bot screen does: draft, find sites (unless one is named), check all, create, learn, then check again with no AI. It also asks "what did you find?" and makes one bot run on a 1-minute schedule by itself.

FINAL_RESULTS

Spot check (A5), E-bike Hunter: 5 random results opened on the live sites. 5 of 5 pages load, show the same title, and cost under €1500.

### What the five-bot test found, and what was fixed

| Found | Fix |
|---|---|
| bikefair.org shows Cloudflare's "Sorry, you have been blocked", and learning spent 18 AI calls on that page | A site that turns bots away is recognised at once and skipped (0 AI calls), with one quiet line |
| tweedehandsfietsen.nl prints prices with no € sign ("1.450,00", cents in their own element), so every bike "passed" €1500 | Money-shaped numbers count as prices, also when split over two elements; "old price" class checks use whole words, so a random class like `kOLdPq` no longer hides a price |
| python.org: the job title was read from the "More jobs in Worldwide" link, so 29 jobs collapsed into 23 | A result's title is its own link: the one that goes somewhere different in every result |
| "remote" and "about AI" became no rule at all | Word rules check everything a result shows (its new `text` field), as whole words: "ai" doesn't match "rain" |
| The model invented "description must mention £", and every book failed it | A rule made only of symbols is never treated as yours; prices and currencies are never a word rule |
| "Hacker News" became a guess, so the bot learned openai.com, huggingface.co and arxiv.org | Sites named by a well-known name keep their address (Hacker News → news.ycombinator.com); "Stack Overflow" matches stackoverflow.com |
| marktplaats: it typed "e-bike" without pressing Enter, then read the home page feed (a skirt, a toy kitchen) | Nothing is read from a home page while a typed search hasn't been sent; the model is told to press Enter first |
| netherlands-secondhandbikes: the home page's featured items (regular bikes) were read as e-bike results | On a shop's home page the model is asked once to open the right category or search first; a "front page" job (HN) reads it straight away |
| Suggested sites included mooiedomeinnaam.nl, a domain-for-sale page | Domains for sale or parked are never suggested |
| "What did you find?" described only the last site (18) while Found had 38 | It leads with the total over every site, then each site's last check |
| The sidebar showed "learning · Click to reveal" (the model's step, reading like an order), and the chat card named the first site during a batch | Both say which site it's on: "learning 2dehands.be · 2 more after" |

## B–H. The rest of the criteria

| Area | Result |
|---|---|
| B Setup | `newuser` journey passed on 1 Oct on the 3-step setup; not rerun this round |
| C Chat | `chat` journey 10/10 on 1 Oct; this round "what did you find?" now counts every site |
| D Connectors | Telegram: **new**, a bot's question arrives with answer buttons and a tap answers it; only taps from your own chat count; answered buttons are removed (unit-tested with a fake Telegram server; not tried with a real bot because no token is set up). n8n and Apify: unit-tested with fakes; not set up on this Mac. Claude Code: really signed out on this Mac (the `claude` command line), and the card says so with the fix. Codex: signed in, connected. Inky's own MCP server, started from the installed app exactly as Claude Code or Codex would: 7 tools, `list_bots` returned your 3 bots (read-only). Cards use plain words (a unit test now checks them) |
| E Screen control | **New guard:** the engine refuses "work on my screen" until you allow it in Settings (before, only the button was greyed out). Seen on screen: one window with the coral frame, the bot's named cursor, the target label and the pill (Chat ⌥C, Pause, Take over, Stop Esc). Stop took 0.57 s. The window closed by itself after the run. Esc and "mouse move takes over" are covered by unit tests |
| F Clean UI | "Skills" is now "Sites" on screen, and a unit test fails if words like skill, selector or headless appear in text you read. Phone width checked on Home and Connectors. **Not built:** a dark theme (about 150 fixed colours need to become tokens first) |
| G Safety | Do bot: asked before sending, Approve sent once, "Always" not asked again (five-bot test). Screen permission now enforced by the engine |
| H Share | `share` journey passed on 1 Oct; the privacy checks are unit-tested |

## Not checked this round

- An overnight run (A6 "overnight"): the 1-minute schedule check passed, but a real morning run wasn't waited for.
- Telegram, n8n and Apify with real accounts (no tokens on this Mac; Inky never types keys).
- Claude Code handing work over (its command line is signed out).
- A dark theme (not built).
