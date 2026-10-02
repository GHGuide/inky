# Inky: test report, 2026-10-02

Branch `build`. Checked against [docs/acceptance.md](../acceptance.md), written this round together with [docs/agent-prompt.md](../agent-prompt.md).
Model: gemma3:12b in Ollama, on this Mac. Every engine used a scratch home; your `~/.inky` was only read, never written. Do bots sent only to the local test site.

Unit tests: `.venv/bin/python -m unittest`: **103 tests, OK** (the 2 install.sh tests skip without Docker). Test runs now leave no temporary folders behind.

## A. The five-bot test (release gate): passed, with one honest caveat

`python -m tests.journeys five` creates the five bots from their sentences only, the way the New bot screen does: draft, find sites (unless one is named), check all, create, learn, then check again with no AI. It also asks "what did you find?" and makes one bot run on a 1-minute schedule by itself.

Final run (commit c8fbf30), 266 s in total:

| Bot | Sites | AI calls to learn | Found | Checked |
|---|---|---|---|---|
| Book Bargains | books.toscrape.com | 1 | 14 under £20, 3 pages | repeat 0 AI calls, "what did you find?" matches Found |
| E-bike Hunter | netherlands-secondhandbikes.com, marktplaats.nl, ebikexl.nl (bikefair.org skipped: it blocks bots) | at most 1 per site | 23 under €1500, every one with a price | 5 random results opened on the live sites: all load, show the same title, are e-bikes |
| Python Jobs | python.org/jobs | 3 | 16 remote jobs, each with its real title | "remote" rule checked on the whole result |
| HN Watch | news.ycombinator.com | 4 | 3 AI stories | hourly schedule set |
| Contact Form | local test site | 4 | asked before sending, sent once; the next run sent once more without asking ("Always") | |
| Runs on its own | | | a 1-minute schedule ran by itself, 0 AI calls | |

The gate also passed earlier in the night with different sites for E-bike Hunter (marktplaats, 2dehands, a bike shop), but that run had a flaw the test didn't catch yet: one site's "results" were a category menu with no prices. The test now fails on any found item without a price, and the final run above passed with that check.

Last run of the night (commit 6bc6b2a, with every fix): Book Bargains, Python Jobs, HN Watch, Contact Form and "runs on its own" passed. E-bike Hunter found only correct things (e-bikes under €1500, such as a Gazelle HeavyDuty for €1,499.99) but learned 1 site instead of 2. DuckDuckGo had paused the searches again, so its sites came from the model's backup list: marktplaats.nl (learned), funda.nl (a housing site), fietsenopfietsen.nl (no e-bikes) and 2dehands.be. Inky gave up on those three by itself, each within its budget, instead of keeping wrong results. When the search works, E-bike Hunter learns 3 sites in about a minute (the run above).

What still varies: when DuckDuckGo pauses Inky's searches (it did, often, after hours of test runs), the sites come from the model's own list instead. That list can include a site that doesn't fit (funda.nl, a housing site): learning gives up on it within its budget (15 AI calls), says so in one line, and the other sites carry on.

### What the five-bot test found, and what was fixed

| Found | Fix |
|---|---|
| bikefair.org shows Cloudflare's "Sorry, you have been blocked", and learning spent 18 AI calls on that page | A site that turns bots away is recognised at once and skipped (0 AI calls) |
| tweedehandsfietsen.nl prints prices with no € sign ("1.450,00", cents in their own element) | Money-shaped numbers count as prices, also when split over two elements; "old price" class checks use whole words |
| marktplaats: the first result was a dealer ad with no price, so the whole site was read without prices | The price field comes from the first result that shows one |
| python.org: the job title was read from the "More jobs in Worldwide" link | A result's title is its own link: the one that goes somewhere different in every result |
| "remote" and "about AI" became no rule | Word rules check everything a result shows, as whole words ("ai" doesn't match "rain") |
| The model invented "description must mention £" | A rule made only of symbols is never treated as yours |
| "Hacker News" became a guess, so the bot learned openai.com and arxiv.org | Sites named by a well-known name keep their address |
| marktplaats: typed "e-bike" without pressing Enter, then read the home page feed (a skirt, a toy kitchen) | Inky presses Enter itself when a search was typed but not sent |
| Home pages: featured items or a mixed feed were saved as results; ebikexl's home, which *is* its shop, was then blocked | Before results are saved, the model takes one look: are these the kind of thing the job is about? A mixed feed or boys' bikes for an e-bike job is turned down; a shop's real catalogue passes |
| 2dehands: the sidebar's category menu ("Elektrische fietsen 743") was read as 45 results | A list of names with counts is a menu, not results; with a price limit, only lists with prices are offered |
| 2dehands and speurders: gemma clicked "Plaats zoekertje" / "Maak advertentie" (*place an ad*) and tried to type a made-up email and password | A bot that finds things never clicks sell, post an ad, log in or register while learning (the password gate had already stopped it) |
| A learned route that didn't work the next time (3 repairs, 0 results) was kept | What it learned is only kept if checking it right after learning finds something |
| gemma said "goto Books" (a link's name), or invented an address next to a link's number | A goto with a link's number clicks the real link; a goto to the page it's on isn't a step |
| Learning answered differently each run | Temperature 0 and a fixed seed for learning and repairs |
| Suggested sites included a domain-for-sale page | Domains for sale or parked are never suggested; the model's backup list starts on the listing page when it exists |
| "What did you find?" described only the last site | It leads with the total over every site, then each site's last check |
| The sidebar showed "learning · Click to reveal"; the chat named the wrong site during a batch | Both say which site it's on: "learning 2dehands.be · 2 more after" |

## B–H. The rest of the criteria

Journeys run on the final code: `newuser` (3-step setup on the real screens, opens on Found, 14 found → 3 after "under £15" in chat, no page errors, fits a phone), `chat` (10/10), `do` (Approve sends once, Deny sends nothing, "Always" sends without asking next time, a moved button is fixed by itself), `batch` (2 of 3 sites, one progress line), `handled` (no card, one quiet line), `stop` (0.3 s), `share` (the other Inky ran it: 60 items, 14 pass) and `books` (14, 1 AI call): **all pass**.

`do` failed once during the night: with temperature 0, gemma kept retyping the message after it was sent. Fixed: a Do job's learning ends once its sending step went through.


| Area | Result |
|---|---|
| D Connectors | Telegram: **new**, a bot's question arrives with answer buttons and a tap answers it; only taps from your own chat count; answered buttons are removed (unit-tested with a fake Telegram server; not tried with a real bot because none is set up here). n8n and Apify: unit-tested with fakes; not set up here. Claude Code: the `claude` command line on this Mac is signed out, and the card says so with the fix. Codex: signed in, connected. Inky's own MCP server, started from the installed app the way Claude Code or Codex start it: 7 tools, `list_bots` returned your 3 bots (read-only). Connector texts are plain words (a unit test checks them) |
| E Screen control | **New guard:** the engine refuses "work on my screen" until you allow it in Settings (before, only the button was greyed out). Seen on screen: one window with the coral frame, the bot's named cursor, the target label and the pill (Chat ⌥C, Pause, Take over, Stop Esc). Stop took 0.57 s. The window closed by itself after the run. Esc and "mouse move takes over" are unit-tested |
| F Clean UI | "Skills" is "Sites" on screen; a unit test fails if words like skill, selector or headless appear in text you read. Phone width checked on Home and Connectors. **Not built:** a dark theme (about 150 fixed colours need to become tokens first) |
| G Safety | The Do bot asks before sending and sends exactly once. Screen permission is enforced by the engine. Finding bots never click sell, post an ad or log in |

## Tools added for whoever works on this next

- `INKY_FIVE="E-bike Hunter" INKY_JOURNEY_KEEP=1 python -m tests.journeys five`: one of the five bots, keeping its folder to look at.
- `INKY_TRACE=1`: every learning reply, the page it was on and what it was last told, written to engine.log.

## Not checked this round

- An overnight run (the 1-minute schedule check passed; a real morning run wasn't waited for).
- Telegram, n8n and Apify with real accounts (no tokens on this Mac; Inky never types keys).
- Claude Code handing work over (its command line is signed out).
- A dark theme (not built).
