# Changelog

All notable changes to Inky. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [semantic versioning](https://semver.org/) (while on 0.x, a minor version may change the bot file format).

## [Unreleased]

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

### Security
- Strict Content-Security-Policy on the app's page; fonts bundled, so opening the app makes no outside request.
- Token checks are constant-time; the pairing code is made from a hash of the token.

[Unreleased]: https://github.com/GHGuide/inky/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/GHGuide/inky/releases/tag/v0.1.0
