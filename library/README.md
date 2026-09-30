# The Inky agent library

Agents anyone can get, in one click, from the **Library** tab in Inky. Each one is a single file in
[`agents/`](agents/): a bot's skills, rules, look and personality. Never sign-ins, memory, results or chat.

## Get an agent

Open Inky → **Library** → **Get**. Before anything is installed you see which sites it visits and what it may do
that can't be undone (it always asks you first). An agent from the library only works on the sites it lists:
if a step leads anywhere else, it stops.

## Post an agent

In Inky, open your bot → **Share** → **Post to the library**. Inky checks the file first (below), shows you exactly
what will be public, and then:

- with GitHub's [`gh`](https://cli.github.com) signed in: forks this repo, adds the file on a branch and opens a pull request;
- without it: opens GitHub's new-file page with the file filled in. Click **Propose new file**.

**Share link:** with `gh`, Inky can also put the file in a public Gist and give you an `inky://install?url=…`
link that anyone with Inky can open.

## What every pull request is checked for

`python -m inky.library check library/agents/<slug>.inky` runs in CI and locally:

- it's a valid Inky bot file under 500 KB;
- no sign-ins (cookies), memory, results or chat messages;
- nothing that looks like a secret: API keys (`sk-…`), GitHub tokens (`ghp_…`), Slack, AWS, Google or Telegram tokens,
  private keys, login tokens, a typed password, or any `password` / `token` / `api_key` value;
- the domains its skills visit and the steps it can't undo are listed in a comment on the pull request.

When a pull request is merged, CI rebuilds [`index.json`](index.json), and everyone's app sees the new agent
within 10 minutes. The two starters here (Book Bargains, Quote of the Day) use
[toscrape.com](https://toscrape.com), sandbox sites made for practice.
