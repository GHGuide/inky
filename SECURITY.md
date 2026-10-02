# Security

Inky drives a browser on your computer, keeps API keys, and runs a local API. We take reports seriously.

## Reporting a problem

Please **don't open a public issue.** Use GitHub's private reporting: the repository's **Security** tab → **Report a vulnerability**.

Include what you found, how to reproduce it, which version and OS, and what an attacker could do with it. We aim to:

- acknowledge your report within **72 hours**,
- tell you what we'll do within **7 days**,
- fix confirmed problems within **30 days** (90 for hard ones), and credit you in the release notes if you'd like.

## Supported versions

Only the latest release gets security fixes.

## In scope

- The engine's HTTP API and its token, pairing between computers, and the server mode (`install.sh`, Docker).
- How keys are stored and whether they can leak (logs, shared bot files, exports, crash output).
- The approval gate: anything that lets a bot send, buy, delete, submit or sign up without your yes, type a password, or get past a robot check.
- Shared bots and the library: a `.inky` file or `inky://` link that runs something you didn't agree to.
- The desktop app: deep links, file associations, the bundled engine, and the release workflow.
- Prompt injection from a web page that makes a bot act outside its job.

## Out of scope

Bugs in third-party sites, AI providers, Ollama or Playwright themselves (report those upstream), and findings that need someone who already controls your user account.

## How Inky protects you

- The local API listens on `127.0.0.1` by default, and every call needs a random token. The page that receives the token checks the `Host` header, which blocks DNS-rebinding pages.
- The app's page sends a strict Content-Security-Policy: its own scripts only, no frames.
- The pairing code is made from a hash of the token, so it shows nothing of the token itself, and wrong codes are rate-limited (5 a minute per address).
- Keys are in the macOS Keychain, or in a file only your user can read (Windows, Linux). They never go into shared bots.
- Irreversible steps, passwords, payments and robot checks are stopped by rules in code, not by a model's judgement.

## Safe harbour

We won't take legal action against research done in good faith that avoids privacy violations, data destruction and service disruption, and that gives us reasonable time to fix the problem before it's made public.
