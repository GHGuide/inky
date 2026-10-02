# Inky and other agents (MCP)

Inky works with AI agents both ways: Claude Code, Codex or any MCP client can use your bots, and your bots can hand a job to Claude Code or Codex.

## Use your bots from Claude Code or Codex

In the app: **Connectors → Let Claude Code and Codex use your bots → Add Inky to Claude Code** (or Codex). It shows the exact command first. Or by hand:

```bash
claude mcp add --scope user inky -- python -m inky.mcp_server
```

```toml
# ~/.codex/config.toml
[mcp_servers.inky]
command = "python"
args = ["-m", "inky.mcp_server"]
```

That's for Inky run from source, with the Python that runs it. With the desktop app, use the button: the command is the app's own engine with `mcp-server` (for example `/Applications/Inky.app/Contents/MacOS/inky-engine mcp-server`). If your Inky folder isn't `~/.inky`, add `INKY_HOME` to the server's environment. Inky has to be running; the tool finds it on its own, even when the app picked a new port.

Then ask in plain words: "what did my Inky bots find today?", "check Book Bargains now", "make an Inky bot that tells me when the Sony WH-1000XM5 drops below €250".

| Tool | What it does | Changes anything |
|---|---|---|
| `list_bots` | Every bot: its job, how much it found and how much is new, its next check, whether it's waiting for you | No |
| `get_bot` | One bot: rules, sites, what it remembers, its last runs and chat, what it's waiting for | No |
| `bot_results` | What a bot found (name, price, link, new or not), with its rules applied | No |
| `list_needs` | What your bots are waiting for you on | No |
| `run_bot` | Check a bot's sites now, with no AI, and say what's new | Starts a check |
| `message_bot` | Talk to a bot as in its chat: "only keep under €500", "every hour", "pause" | Can change the bot |
| `create_bot` | Make a bot from a sentence; it drafts, finds sites and starts learning | Makes a bot |
| `create_bot_status` | How a bot `create_bot` is still making is getting on | No |

Bots are found by loose names: "books", "the ebike bot", "python jobs". `run_skill`, the 0.1.0 name of `run_bot`, still works.

Every call answers in under a minute, which is about as long as clients wait. A long check or a slow model keeps going in Inky, and the answer says how to pick it up.

**Approving is not a tool, on purpose.** When a bot wants to send, post or submit something, only you can say yes, in the app or on Telegram. `list_needs` shows what's waiting.

### Codex without asking: `codex exec`

`codex exec` never asks, so Codex turns down any tool that isn't read-only (`run_bot`, `message_bot`, `create_bot`). To let it use those, approve Inky's tools for that run:

```bash
codex exec -c 'mcp_servers.inky.default_tools_approval_mode="approve"' "check my Inky bots and tell me what's new"
```

or add `default_tools_approval_mode = "approve"` under `[mcp_servers.inky]`. Interactive Codex asks you instead.

## Hand a job from a bot to Claude Code or Codex

In a bot's chat, name the agent:

- "Ask Codex which of these is the best deal"
- "Have Claude Code write a short report on these"

The bot asks you first ("Book Bargains wants to hand a job to Codex"), sends what it found with the job, and the answer comes back in the chat. Codex runs read-only. Claude Code needs to be signed in on this computer (open a terminal, run `claude` and sign in); until then the bot says so and offers Codex.

## Check it yourself

```bash
claude mcp list              # inky: … ✔ Connected
python -m unittest tests.test_mcp
```
