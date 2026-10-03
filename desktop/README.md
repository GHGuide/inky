# Inky desktop app

A real app for Mac, Windows and Linux (Tauri 2). It runs Inky's engine inside itself, so there is no browser tab and no localhost address.

- **Tray and badge:** a critter in the tray (it animates while bots work) and a Needs-you badge on the dock or taskbar.
- **Shortcuts anywhere:**
  - ⌥Space or ⌃⌥Space opens the command bar over any app;
  - ⌃⌥P pauses all bots;
  - ⌃⌥Esc stops every bot on your screen.
- **Notifications** when a bot needs you or finds something. Clicking one brings you to it.
- **Desktop buddy:** a critter peeks in from the screen edge when a bot needs you (Settings → Desktop buddy).
- **Open Inky when you log in** (Settings).
- **Files:** double-click an `.inky` bot file to import it.
- **Links:** `inky://pair?url=…&code=…` (printed by `install.sh`) pairs a server after one confirm, and `inky://install?url=…` gets a shared agent after a permission preview.
- **Finds your tools:** opened from the Dock, the app adds your login shell's PATH, so Claude Code, Codex, Ollama, Docker and gh are found.
- **Outside links** (get a key, install Ollama, a pull request) open in your own browser.

## Add a server

Pick one in Computers (or setup step 2):

- **Over SSH:** type `you@server`. Inky installs itself there and pairs. Nothing to type on the server.
- **One line on the server:** `curl -fsSL https://raw.githubusercontent.com/GHGuide/inky/main/install.sh | sh` (Docker if it's there, otherwise Python with a systemd or launchd service). It prints a pair link.
- **Found on your network:** engines started with `--host 0.0.0.0` announce themselves on UDP 48800 (no code or token in it). Pairing still needs the code.
- **On your tailnet:** with Tailscale, other Inkys on your tailnet are listed with their Tailscale address, which works away from home.

## Build

You need Python 3.12 with `uv`, Node 22 and Rust. Releases are built by [.github/workflows/release.yml](../.github/workflows/release.yml) when a version tag is pushed.

```bash
uv sync                      # from the repo root: engine deps + PyInstaller (build only)
cd desktop && npm install
npm run build                # engine binary, then the app: src-tauri/target/release/bundle/
```

For a quick local build use `npx tauri build --debug --bundles app`.

`INKY_HOME=/some/folder` points the app at another data folder; the default is `~/.inky`.

## How it fits together

- **Starting:** the app looks for `~/.inky/engine.json`. If an engine already runs there (for example `python -m inky`), it uses that one. Otherwise it starts its own: `binaries/inky-engine` with `--port 8800 --or-any-port --stop-with-stdin` (a stable port keeps links, pairings and n8n working).
- **First launch:** the bots' browser (Chromium) downloads into `~/.inky/browsers`.
- **Windows:** the app's windows show the engine's own web UI. `?bar=1` is the floating command bar and `?buddy=1` is the desktop buddy.
- **Native side:** the web UI tells the native side what changed (`tray`, `notify`, `bar`, `open_needs`, `autostart`, `app_info`, `open_url`). Only the local engine page may call these (`capabilities/default.json`).

Builds are ad-hoc signed on macOS and unsigned on Windows, so both warn the first time. [The main README](../README.md#download) says what to click.

## Signing and notarizing

The app and its engine always run with the hardened runtime and [entitlements.plist](src-tauri/entitlements.plist): `allow-jit`, `allow-unsigned-executable-memory` and `disable-library-validation`. The engine is a PyInstaller program that unpacks Python, its libraries and Playwright's driver when it starts, and the hardened runtime refuses to load them otherwise. Without a certificate the signature is ad-hoc, so macOS offers **Open Anyway**. With a Developer ID it is signed, and with notary credentials it is also notarized, so it opens like any app.

**The quick way:** run `desktop/scripts/setup-apple-signing.sh` (and again with your exported .p12 for releases). It does both steps below and asks for each password itself.

**On your Mac**, once (only you can do this: it needs an app-specific password from [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords):

```bash
xcrun notarytool store-credentials inky-notary --apple-id <your Apple ID> --team-id <your team id>
```

Then build signed and notarize:

```bash
cd desktop && APPLE_SIGNING_IDENTITY="Developer ID Application: <name> (<team id>)" npx tauri build
desktop/scripts/notarize-macos.sh
```

**In releases** ([release.yml](../.github/workflows/release.yml)), macOS builds are signed and notarized when these repository secrets exist, and ad-hoc signed otherwise:

| Secret | What |
|---|---|
| `APPLE_CERTIFICATE` | the Developer ID Application certificate with its private key, exported from Keychain Access as .p12, base64 (`base64 -i cert.p12 \| gh secret set APPLE_CERTIFICATE -R GHGuide/inky`) |
| `APPLE_CERTIFICATE_PASSWORD` | the password you gave the .p12 (`gh secret set APPLE_CERTIFICATE_PASSWORD -R GHGuide/inky`, then paste) |
| `APPLE_SIGNING_IDENTITY` | `Developer ID Application: <name> (<team id>)` |
| `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` | your Apple ID, an app-specific password and your team id, for notarizing |

If the engine starts slowly inside a signed app (`Contents/MacOS/inky-engine --port 0 --home "$(mktemp -d)" --no-open` should take a few seconds), sample it (`/usr/bin/sample <pid> 2`) before anything else: a 30-second start once turned out to be a name lookup that macOS holds for new apps.
