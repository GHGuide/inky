# Inky · product vision

Agreed with the user on 2026-10-01. Every fix and feature is checked against this page.

## In one sentence

**Bots that watch and work the web for you.** You describe a job in plain words; a bot learns the site once with AI, then repeats it for free on your own computer, and only bothers you with what's new or what needs your yes.

## Who it's for

Both everyday people and power users, **everyday people first**: simple by default, with advanced options folded away. Plain words, no terminal, no jargon on the main path.

## What a bot does

Finding and doing count **equally**:
- **Watch:** find and monitor things on websites (new flats, price drops, suppliers, jobs) and report what's new.
- **Do:** carry out tasks on websites (fill a form, send a message, book something), always with your yes before anything that can't be undone.

## The core loop

1. **Describe** the job in plain words.
2. **It sets itself up:** drafts the bot and finds the websites for you.
3. **It learns once,** while you can watch. This is the only step that needs AI.
4. **It repeats for free** on its schedule, with no AI.
5. **It tells you what's new** (chat, notification, Telegram), and "what did you find?" gets a straight answer.
6. **It stays safe and honest:** asks before sending, buying, deleting or signing up; never types passwords; fixes itself when a site changes, or asks you to show it once; never claims something it didn't do.

## Principles

- **Best results first:** a new user is steered to a model that can really learn sites (a cloud key, or a capable local model such as gemma3:12b). Tiny models are allowed but come with a clear warning.
- **Learn once, repeat with no AI:** the reason Inky is cheap, fast and private.
- **Yours:** runs on your computer with your keys. There is no Inky server or account.
- **Honest:** what the app says always matches what happened.

## Around the core (secondary)

Share (one link, the public library), connectors (Claude Code, Codex, n8n, Telegram), personality (critters, voice, diary) and more computers. These must never get in the way of the core loop; anything not solid is hidden rather than shown half-working.

## Done means

A new person installs the app, makes a useful bot for a real site, and gets correct results the next morning: no errors, no dead ends, no confusing text, no docs needed.

## Core journeys (the acceptance tests)

Each is run in the real app, on real websites, with a capable model. A journey passes only when every step works first time and every message is true.

| # | Journey | Passes when |
|---|---|---|
| 1 | **Setup** on a fresh install | It ends with a model that works and was tested; a tiny model comes with a warning; no terminal, no dead end |
| 2 | **Watch bot** for a real site (e.g. books under £20, flats, brick suppliers) | Draft is sensible, sites are found, learning finishes with a skill that reads the right items, first results are correct |
| 3 | **Results and alerts** | A later run marks only truly new items as new, says so in chat (and a notification), and "what did you find?" matches the Results tab |
| 4 | **Do bot** (a form or message, on the local test site only) | It asks before sending; Approve sends exactly once; Deny sends nothing; "Always" is remembered |
| 5 | **Chat** | Rules, schedule, run, pause, remember and questions each do exactly what was asked, and replies are true |
| 6 | **Site changes** | A renamed button is fixed by itself, or it asks; "Show me once" fixes it; a fix that finds nothing is never kept |
| 7 | **Share** | Copy a share link → paste on another Inky → preview → Get → it runs |
