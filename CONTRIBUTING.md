# Contributing to Inky

Thanks for helping. Inky is a small codebase on purpose: a Python engine (stdlib + Playwright + httpx), a vanilla-JS UI with no build step, and a thin Tauri shell. Please keep it that way.

## Ways to help

- **Report a bug.** Use the bug form, and include your OS, Inky version, the model you use, and what the bot's chat said. The engine log is in your Inky folder (`~/.inky/engine.log` when you run from source).
- **Tell us about a site Inky learns badly.** Use the "A site doesn't work" form, with the job sentence you typed. These reports make learning better for everyone.
- **Share a bot** in the [library](library/README.md).
- **Code:** fixes, connectors, translations, better learning on hard sites. For anything bigger than a fix, open an issue first so we can agree on the approach.

## Set up

```bash
git clone https://github.com/GHGuide/inky && cd inky
uv sync                                   # or: python -m venv .venv && .venv/bin/pip install "playwright==1.63.0" "httpx==0.28.1"
uv run playwright install chromium
uv run python -m inky --home "$(mktemp -d)" --port 8899   # a scratch engine, so your real ~/.inky stays untouched
```

The UI is in `inky/ui`: edit and reload, no build. The desktop app is in `desktop/` (see [desktop/README.md](desktop/README.md)).

## Test

```bash
uv run python -m unittest                      # unit tests: about two minutes, no keys, no network beyond a local test site
uv run python -m tests.site_server 8766        # the local test site that Do bots send to
uv run python -m tests.journeys                # end-to-end journeys on real sites with a local model (gemma3:12b in Ollama)
uv run python -m tests.journeys five           # the release gate: five bots from five sentences
```

Journeys take minutes and use a real model. Run the ones your change touches. If learning goes wrong, `INKY_FIVE="E-bike Hunter" INKY_JOURNEY_KEEP=1 INKY_TRACE=1` keeps the folder and writes every model reply to its `engine.log`.

## What a good change looks like

[docs/agent-prompt.md](docs/agent-prompt.md) is written for AI coding agents, but it's the best description of how we work. The short version:

1. **Find the real cause.** Reproduce it, read the whole flow, fix it once where every caller passes through.
2. **Make the smallest change that fixes it.** Reuse what's there. No new dependency unless nothing installed can do it.
3. **Leave one test behind** that fails if the fix breaks.
4. **Keep the hard rules.** Bots ask before anything irreversible, never type passwords, never solve robot checks, and never call a model on the replay path. A change that weakens these won't be merged.
5. **Plain words on screen.** "Sites", not "skills". One sentence for an error, with a button when there's a fix. `tests/test_plain_words.py` catches jargon.
6. **Honest messages.** Every count and "done" the app shows must come from real data.

Write commit messages that say what changed for the person using the app.

## Releases

Maintainers bump the version in the five places `scripts/check_versions.py` checks, add a section to [CHANGELOG.md](CHANGELOG.md), and push a tag (`git tag v0.2.0 && git push origin v0.2.0`). [The release workflow](.github/workflows/release.yml) builds every installer into a draft release, which a maintainer checks and publishes.

## Code of conduct

Be kind and assume good intent. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
