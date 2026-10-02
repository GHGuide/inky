# Changelog

All notable changes to Inky. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [semantic versioning](https://semver.org/) (while on 0.x, a minor version may change the bot file format).

## [Unreleased]

### Added
- "Ask Codex to …" or "have Claude Code …" in a bot's chat hands that job, with what the bot found, to the agent you named, after you say yes. If Claude Code isn't signed in, the bot says so and offers Codex.
- Inky as an MCP server: `create_bot` answers within a minute and keeps making the bot in the background (`create_bot_status`); bots are found by loose names ("books", "the ebike bot"); short, readable answers; tool hints so clients know which tools only read. [docs/mcp.md](docs/mcp.md) explains it, including `codex exec`.

### Changed
- `run_skill` is now `run_bot`. The old name still works.

### Fixed
- Inky's MCP server answers with a protocol version it speaks, a clear message for a missing argument or an unknown tool, and one plain sentence when Inky isn't running.

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
