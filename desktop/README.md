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

## Build

You need Python 3.12 with `uv`, Node 22 and Rust.

```bash
uv sync                      # from the repo root: engine deps + PyInstaller (build only)
cd desktop && npm install
npm run build                # engine binary, then the app: src-tauri/target/release/bundle/
```

For a quick local build use `npx tauri build --debug --bundles app`.

`INKY_HOME=/some/folder` points the app at another data folder; the default is `~/.inky`.

## How it fits together

- **Starting:** the app looks for `~/.inky/engine.json`. If an engine already runs there (for example `python -m inky`), it uses that one. Otherwise it starts its own: `binaries/inky-engine` with `--port 0 --stop-with-stdin`.
- **First launch:** the bots' browser (Chromium) downloads into `~/.inky/browsers`.
- **Windows:** the app's windows show the engine's own web UI. `?bar=1` is the floating command bar and `?buddy=1` is the desktop buddy.
- **Native side:** the web UI tells the native side what changed (`tray`, `notify`, `bar`, `open_needs`, `autostart`, `app_info`). Only the local engine page may call these (`capabilities/default.json`).

Builds are unsigned. On macOS, right-click the app → Open the first time.
