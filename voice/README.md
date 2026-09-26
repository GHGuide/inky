# Inky voice

Hold **⌥ Space** in any app, say what to change ("only places with the euro"), let go. Inky applies it while it keeps running.

Speech never leaves the Mac: ffmpeg records the default mic (16 kHz mono), [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT) transcribes it with `ggml-base.bin`, and the text goes to the Inky app at `POST http://127.0.0.1:8765/api/command {"text": ...}`.

The command is applied live, so nothing is sent when no one spoke: whisper.cpp runs with Silero VAD (room noise gives no text instead of "Thank you."), and text made only of the spelling hints (`Porto, Bari, Łódź, euro, ...`, which whisper echoes on noise) is dropped as "Didn't catch that".

| File | What it does |
|---|---|
| `listen.py` | Record → transcribe → POST → print one JSON line (`{"heard", "change", "rule", "removed", "applied", "matches_before", "matches_after"}` or `{"heard", "error"}`). Stdlib only. |
| `init.lua` | Hammerspoon: ⌥ Space hold-to-talk and the pill near the bottom of the screen (Listening… → Thinking… → the effect, 5 s: **"46 → 14 homes"** with the change sentence under it, or just the change sentence when the app sends no counts). Also the "Inky has the screen" frame, below. |
| `screen.py` | `has_screen(text)`: `teach/learn.py` and `race/race.py` (headed runs) write `$TMPDIR/inky-screen.flag` while they drive Chrome. |
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
   package.path = "/path/to/inky/?/init.lua;" .. package.path
   require("voice")
   ```
3. System Settings → Privacy & Security:
   - **Files and Folders → Downloads**: allow Hammerspoon. The repo is in `~/Downloads`, which macOS guards; macOS asks on *Reload Config*. If you said no, `require("voice")` fails with "module 'voice' not found": turn it on here and reload.
   - **Accessibility**: turn on Hammerspoon (it needs this to see ⌥ Space).
   - **Microphone**: macOS asks the first time you hold ⌥ Space; allow Hammerspoon. If the pill says "The mic gave only silence", turn Hammerspoon on here and hold again.
4. **ChatGPT.app is installed on this Mac and its launcher uses ⌥ Space by default**, and a global shortcut wins over Hammerspoon. Before recording: ChatGPT → Settings → Keyboard shortcuts, change or clear the launcher shortcut. Do the same for Raycast or Alfred if you use them on ⌥ Space.
5. Optional, to match the design fonts: `brew install --cask font-geist`, then *Reload Config*. Without it the pill uses the system font.
6. Start the Inky app (port 8765), hold ⌥ Space, speak, release. Holding ⌥ Space while Inky is still on the last request shows "Still thinking…"; try again when the answer shows.

## "Inky has the screen" frame

While a headed `teach/learn.py` or `race/race.py` runs, `init.lua` draws a coral frame round the whole display with a
tag at the bottom ("Inky has the screen · racing: 8 windows vs 1 clicking agent"). It checks for
`$TMPDIR/inky-screen.flag` twice a second and takes the frame down when the run ends (also on Ctrl-C). Drawing needs
no permission beyond loading the config (Downloads). Clicks go through it. If a run was killed hard and the frame
stays: `rm "$TMPDIR/inky-screen.flag"`. To see it without a run: `echo test > "$TMPDIR/inky-screen.flag"`, then `rm` it.

## Try it without Hammerspoon

```bash
.venv/bin/python voice/listen.py --text "only places with the euro" --dry-run   # no mic
.venv/bin/python voice/listen.py --seconds 4                                    # speak for 4 s (Terminal needs Microphone)
```

Options: `--dry-run` asks the app what would change without applying it; `--url` (or `INKY_URL`) for another app address; `--lang auto` for Dutch or other languages (default `en`); `--mic none:2` for another input (list them with `ffmpeg -f avfoundation -list_devices true -i ""`).

## Troubleshooting (morning checklist)

After any change to `voice/init.lua`: Hammerspoon menu bar icon → **Reload Config**. Hammerspoon still runs the
version from before Sunday 00:30, so reload once for the new pill ("46 → 14 homes") and the screen frame.

1. **Test without the mic first.** Start the app (`.venv/bin/python app/serve.py`), then:
   ```bash
   .venv/bin/python voice/listen.py --text "only places with the euro" --dry-run
   ```
   You should get one JSON line with `change`, `matches_before` and `matches_after` (`--dry-run` changes nothing; it
   costs one small GLM call). `"error": "Inky app is not running at http://127.0.0.1:8765"` means the app is not up.
   `No rules yet` means `data/rules.json` has no `final` rules yet.
2. **Permissions** (System Settings → Privacy & Security), all for **Hammerspoon**:
   - *Files and Folders → Downloads*: without it *Reload Config* shows "module 'voice' not found".
   - *Accessibility*: without it ⌥ Space does nothing (no pill at all). After turning it on, quit Hammerspoon and open
     it again if the pill still does not show.
   - *Microphone*: asked the first time you hold ⌥ Space. If the pill says "The mic gave only silence", turn it on here
     and hold again.
3. **⌥ Space opens ChatGPT instead of the pill**: ChatGPT.app → Settings → Keyboard shortcuts → change or clear the
   launcher shortcut (it uses ⌥ Space by default and a global shortcut wins). Same for Raycast or Alfred on ⌥ Space.
4. **Read the Hammerspoon console** (menu bar icon → Console…). A load error of `init.lua` shows there with its line.
   Type `InkyVoice` and Enter: a table means the module is loaded; `nil` means it is not (see 2, Downloads).
   `InkyVoice.tap:isEnabled()` should say `true`; `false` most likely means Accessibility is off.
5. **Pill says "Didn't catch that"**: whisper heard nothing (or only its spelling hints). Hold ⌥ Space a moment before
   you speak and let go after. Check the input with `.venv/bin/python voice/listen.py --seconds 4` in Terminal
   (Terminal then needs Microphone too).
6. **Pill says "Still thinking…"**: the last request is still at the app (GLM can take 10-20 s). Wait for its answer.
7. `.venv/bin/python voice/check.py` checks everything that does not need your voice (no mic, no network, no keys).
