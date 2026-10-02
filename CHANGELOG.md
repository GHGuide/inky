# Changelog

All notable changes to Inky. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [semantic versioning](https://semver.org/) (while on 0.x, a minor version may change the bot file format).

## [Unreleased]

### Added
- "Ask Codex to …" or "have Claude Code …" in a bot's chat hands that job, with what the bot found, to the agent you named, after you say yes. If Claude Code isn't signed in, the bot says so and offers Codex.
- Inky as an MCP server: `create_bot` answers within a minute and keeps making the bot in the background (`create_bot_status`); bots are found by loose names ("books", "the ebike bot"); short, readable answers; tool hints so clients know which tools only read. [docs/mcp.md](docs/mcp.md) explains it, including `codex exec`.

### Changed
- The chat is tidier:
  - What a bot found is a small card of results you can open, with “See all in Found”, instead of a run-on sentence.
  - Run and learning updates are one quiet line each, with their time.
  - A bot's messages in a row share one avatar. Repeated settings notes show only the latest, and long answers fold.
  - Older messages show the same way.
- Bots say less that you didn't ask for. “What did you do?” is two short sentences. “No AI needed” is only said when AI was used, and replies have no small talk about the bot itself. Replies come in the language you write in.
- Slow, Normal and Turbo really differ: a slow bot points longer, types letter by letter and rests between steps; Turbo goes straight through.
- Less on screen:
  - The Watch tab shows Stop only while something runs and drops empty sections.
  - Cards have no empty boxes.
  - Results without pictures have no grey squares.
  - A site's details are one line.
  - Needs you lists each handled problem once.
  - Settings shows desktop shortcuts only in the app.
  - The chat's examples go away once you've talked to a bot.
- Found can be ordered by cheapest or newest. Its rule tags open the bot's Settings.
- Unpairing a computer signs this one out over there too, and Needs you flags a server that signed you out.
- Handing back after a robot check while learning carries on learning that site.
- Messages no longer start with “Something went wrong (str)” in front of a perfectly readable reason. The Library marks starters even when the public library is reachable. The unused first-run tour is gone.
- Each device you pair gets its own key. Computers lists them with Sign out, and “Sign out older pairings” cuts off pairings made with 0.1.0.
- `run_skill` is now `run_bot`. The old name still works.
- Daily and weekly checks run at a time of day (07:30 unless you say “every evening” or “at 9”), so Run now in between never moves tomorrow's check. Settings offers the same choices as New bot (6 hours and weekly too).

### Learning
- Tested on 42 kinds of pages and 7 practice sites; 24 of those page kinds were handled wrongly before ([report](docs/learning-report.md)). Now:
  - Results keep their own names (no “View” titles, no quotes merged by their tags).
  - Prices: the price you'd pay on a sale, “Free”, and prices in tables are read right.
  - Pages: page numbers, a lone “›” and “Load more” lists are read past the first page, and lists that appear a moment late aren't missed.
  - Sites learned right: ASP.NET search pages, link-less tables, category pages named only by an aria-label, and Hacker News.
  - Fewer AI calls wasted: a 404 start page costs no AI calls, and a sign-in wall stops before anything is typed.
  - Learning ends after the same mistake three times instead of going round.

### Security
- A bot file you open gets the same preview, checks and fresh start as a shared agent. It arrives without sign-ins, memory, results, chat or approvals, stays on the sites it lists, and can't allow paying. Only a move between your own paired computers keeps those.
- Bots open web pages only: never a file on your computer, and never Inky's own page, even if a site redirects there. Shared bots that try fail the check before you get them.
- A shared bot's colour can only be a colour, so it can't hide the warnings in the preview.
- A form with a password box always stops for you to sign in, whatever its button says. Pressing Enter or a button in a contact, sign-up or order form asks first, even when the button only says “Continue”.
- A “never” rule also checks the page a step is on (“never contact the agency” stops the Send on the agency's contact page). Pausing while a bot waits for your yes holds after the yes.
- Learning treats text on a page as what the site says, never as instructions. If a finding bot still wants to send something, its question says that isn't part of its job.
- Requests to the engine have a size limit and a time limit; a broken request gets a clear error instead of an open connection.
- Inky reads a `.env` file only from its own folder (`~/.inky/.env`), not from whatever folder it was started in.

### Fixed
- Inky's MCP server answers with a protocol version it speaks, a clear message for a missing argument or an unknown tool, and one plain sentence when Inky isn't running.
- Chat answers “what's the cheapest?”, “the most expensive?” and “how many did you find?” from what the bot kept, never a guess. “Work on my screen” is done or honestly refused, never just claimed.
- “Skip senior roles” no longer becomes a rule that keeps only senior roles.
- The New bot rules editor reads “1,000” as one number and leaves out a rule with no value, instead of saving rules that hide everything.
- “I’ll try again on my own soon” says when, and why it stopped.
- Needs you moves to the next question after you answer, not onto its Approve button.
- Calls to a bot on another computer keep their options (like how many results to show).
- Every count and answer uses your rules as they are now, not as they were at the last run (Found, chat, the sidebar, hand-offs).
- A draft keeps the address you typed (http for your own machines) and limits written like “€150.000”. Answering “It wonders” searches for sites again, and it asks two rounds of questions at most.
- A site counts as “the site you named” only when you named it (“nintendo.com”, “on Amazon”), not when it's in a product's name.
- Results are titled by their heading, not by a “Details” link. Learning a new site with an empty address says so instead of learning the old one again.
- Chat: “only when I ask”, “forget that rule”, questions that end in an emoji, a hand-off to a bot rather than a connector, plain errors in “what did you do?”, a long plain-text answer kept as it is.
- Pause all bots pauses every bot, not only the ones running. The command bar opens a bot you typed the name of instead of sending it its own name.
- A moved bot whose computer is off says so, never shows results from before the move, and keeps its name on the other computer.
- Team shows milestones and good nights.
- Paired computers:
  - their names follow when they're renamed there, and you can rename them here;
  - addresses like `root@[::1]` work for SSH;
  - a move's check counts what passes the bot's rules.
- Models: a role can't be set to a model Ollama doesn't have, or to a provider with no key, so a job can't fail on it later. The picker suggests the model your other jobs use.
- A draft keeps “under £20” as you wrote it.
- Other fixes:
  - the publish preview says which GitHub account it posts as;
  - a moved bot's automations list its server's connectors;
  - Esc closes the key box in setup;
  - a quick click before the app has loaded no longer opens setup;
  - errors never show Playwright's call log.
- Setup's first page appears at once; Docker's state is checked in the background. A key that couldn't be checked isn't kept; “Is it running?” is only said of servers on this computer.
- Dark mode: code blocks, separators and “idle” are readable; the phone status bar follows the theme. Wording and small fixes across Settings, Models and the wizard.

## [0.1.0] - 2026-10-02

The first public release.

### Added
- Bots from a sentence: Inky drafts the bot (name, sites, schedule, rules), finds sites for the job, learns each site once with AI while you watch, then repeats it on a schedule with no AI.
- Ready-made jobs on Home and in setup: price drop, back in stock, new rentals, new jobs, second-hand deals, news on a topic, and a practice site that works in about half a minute.
- Found, Watch and Settings tabs for every bot; chat in plain words ("only under €500", "every hour", "what did you find?"), with simple commands that work without a model.
- Models: local through Ollama (picks the biggest that fits your computer) or a key for OpenRouter, Anthropic, OpenAI, Gemini, Groq, xAI or Mistral. Stop a model mid-answer.
- Learning that checks itself: results must be the kind of thing the job is about; home-page feeds, category menus and unsent searches are never saved as results; a site that refuses bots is skipped; what it learned is only kept if checking it again finds something.
- Problems handled quietly: retries after timeouts, offline spells and changed pages; you're asked only after three failures in a row.
- The approval gate: asks before sending, posting, deleting, submitting or signing up; never pays, never types passwords, never solves robot checks. "Always for this step" is remembered.
- Alerts in the app, as notifications, and on Telegram, where you can tap an answer to a bot's question.
- Your own screen (off until you allow it), other computers and servers (pair link, code, SSH, `install.sh`, Docker), connectors (Claude Code, Codex, n8n, Apify, any MCP server), Inky as an MCP server, sharing bots by link and the public library.
- Desktop app for macOS (Apple Silicon and Intel), Windows and Linux, built in public with provenance and SHA256SUMS.
- Updates inside the app: signed, checked a few seconds after it opens and every six hours, one click to restart into the new version.
- Light and dark, following your system or your choice in Settings → About.

### Security
- Strict Content-Security-Policy on the app's page; fonts bundled, so opening the app makes no outside request.
- Token checks are constant-time; the pairing code is made from a hash of the token.

### Fixed
- A first launch no longer waits about 30 seconds on macOS: starting the engine doesn't look up the computer's own name any more.

[Unreleased]: https://github.com/GHGuide/inky/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/GHGuide/inky/releases/tag/v0.1.0
