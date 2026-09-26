# Inky voice

Hold **⌥ Space** in any app, say what to change ("only places with the euro"), let go. Inky applies it while it keeps running.

Speech never leaves the Mac: ffmpeg records the default mic (16 kHz mono), [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT) transcribes it with `ggml-base.bin`, and the text goes to the Inky app at `POST http://127.0.0.1:8765/api/command {"text": ...}`.

The command is applied live, so nothing is sent when no one spoke: whisper.cpp runs with Silero VAD (room noise gives no text instead of "Thank you."), and text made only of the spelling hints (`Porto, Bari, Łódź, euro, ...`, which whisper echoes on noise) is dropped as "Didn't catch that".

| File | What it does |
|---|---|
| `listen.py` | Record → transcribe → POST → print one JSON line (`{"heard", "change", "rule", "removed", "applied", "matches_before", "matches_after"}` or `{"heard", "error"}`). Stdlib only. |
| `init.lua` | Hammerspoon: ⌥ Space hold-to-talk and the pill near the bottom of the screen (Listening… → Thinking… → the change, 4 s). |
| `critter.png` | The octopus from `Critter.dc.html` (64 px) for the pill. |
| `check.py` | Self-check, no mic, no network, no keys. Also runs `init.lua` under a fake Hammerspoon. |
| `models/` | `ggml-base.bin` (148 MB) and `ggml-silero-v5.1.2.bin` (0.9 MB VAD), git-ignored. |

## Setup (already done on this Mac)

```bash
brew install whisper-cpp ffmpeg
curl -L -o voice/models/ggml-base.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
curl -L -o voice/models/ggml-silero-v5.1.2.bin https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin
.venv/bin/python voice/check.py          # prints "all checks passed"
```

## What you need to do

1. `brew install --cask hammerspoon`, open it once.
2. Add these two lines to `~/.hammerspoon/init.lua`, then *Reload Config* from the Hammerspoon menu bar icon:
   ```lua
   package.path = "/Users/leonardo/Downloads/Youngcreators/?/init.lua;" .. package.path
   require("voice")
   ```
3. System Settings → Privacy & Security:
   - **Files and Folders → Downloads**: allow Hammerspoon. The repo is in `~/Downloads`, which macOS guards; macOS asks on *Reload Config*. If you said no, `require("voice")` fails with "module 'voice' not found": turn it on here and reload.
   - **Accessibility**: turn on Hammerspoon (it needs this to see ⌥ Space).
   - **Microphone**: macOS asks the first time you hold ⌥ Space; allow Hammerspoon. If the pill says "The mic gave only silence", turn Hammerspoon on here and hold again.
4. **ChatGPT.app is installed on this Mac and its launcher uses ⌥ Space by default**, and a global shortcut wins over Hammerspoon. Before recording: ChatGPT → Settings → Keyboard shortcuts, change or clear the launcher shortcut. Do the same for Raycast or Alfred if you use them on ⌥ Space.
5. Optional, to match the design fonts: `brew install --cask font-geist`, then *Reload Config*. Without it the pill uses the system font.
6. Start the Inky app (port 8765), hold ⌥ Space, speak, release. Holding ⌥ Space while Inky is still on the last request shows "Still thinking…"; try again when the answer shows.

## Try it without Hammerspoon

```bash
.venv/bin/python voice/listen.py --text "only places with the euro" --dry-run   # no mic
.venv/bin/python voice/listen.py --seconds 4                                    # speak for 4 s (Terminal needs Microphone)
```

Options: `--dry-run` asks the app what would change without applying it; `--url` (or `INKY_URL`) for another app address; `--lang auto` for Dutch or other languages (default `en`); `--mic none:2` for another input (list them with `ffmpeg -f avfoundation -list_devices true -i ""`).
