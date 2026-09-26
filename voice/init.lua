-- Inky voice for Hammerspoon: hold ⌥ Space in any app, speak, release.
-- Inky applies the change while it keeps running. Load it from ~/.hammerspoon/init.lua (see README.md).
-- Hammerspoon needs Accessibility (to see ⌥ Space) and Microphone (ffmpeg records as Hammerspoon).
-- Also: a coral "Inky has the screen" frame round the display while teach/learn.py or race/race.py drives Chrome
-- (they write $TMPDIR/inky-screen.flag, voice/screen.py). Drawing needs no permission.

local dir = debug.getinfo(1, "S").source:sub(2):match("(.*)/")
local venv = dir .. "/../.venv/bin/python"
local python = hs.fs.attributes(venv) and venv or "/usr/bin/python3" -- listen.py is stdlib only
local listen = dir .. "/listen.py"
local flag = (os.getenv("TMPDIR") or "/tmp/") .. "inky-voice.flag"
local screenFlag = (os.getenv("TMPDIR") or "/tmp/") .. "inky-screen.flag"
local critter = hs.image.imageFromPath(dir .. "/critter.png") -- the octopus from Critter.dc.html, 32 px

local CORAL, INK, GREY = "#E86F51", "#111110", "#A8A49C"
local function font(name, fallback)
  return hs.fnutils.contains(hs.styledtext.fontNames(), name) and name or fallback.name
end
local BOLD = font("Geist-SemiBold", hs.styledtext.defaultFonts.boldSystem)
local REGULAR = font("Geist-Regular", hs.styledtext.defaultFonts.system)

local M = { recording = false } -- global below: Hammerspoon garbage-collects eventtaps nobody holds

local function styled(s, face, size, color)
  return hs.styledtext.new(s, { font = { name = face, size = size }, color = { hex = color },
    paragraphStyle = { lineBreak = "truncateTail" } })
end

local function hide()
  if M.pulse then M.pulse:stop(); M.pulse = nil end
  if M.timer then M.timer:stop(); M.timer = nil end
  if M.pill then M.pill:delete(); M.pill = nil end
end

-- Dark pill near the bottom of the screen: octopus, title, grey line under it (Desktop.dc.html).
local function show(title, sub, seconds, pulse)
  hide()
  local t, s = styled(title, BOLD, 13.5, "#FFFFFF"), styled(sub or "", REGULAR, 12, GREY)
  local screen = hs.screen.mainScreen():frame()
  local textW = math.max(hs.drawing.getTextDrawingSize(t).w, hs.drawing.getTextDrawingSize(s).w)
  local w, h = math.min(math.ceil(textW) + 72, screen.w - 80), 48
  M.pill = hs.canvas.new({ x = screen.x + (screen.w - w) / 2, y = screen.y + screen.h - h - 40, w = w, h = h })
  M.pill:level(hs.canvas.windowLevels.overlay)
  M.pill:behavior({ "canJoinAllSpaces", "stationary" })
  M.pill:appendElements(
    { type = "rectangle", action = "fill", fillColor = { hex = INK },
      roundedRectangleRadii = { xRadius = h / 2, yRadius = h / 2 } },
    critter and { type = "image", image = critter, frame = { x = 12, y = 8, w = 32, h = 32 } }
      or { type = "circle", action = "fill", fillColor = { hex = CORAL }, center = { x = 28, y = h / 2 }, radius = 7 },
    { type = "text", text = t, frame = { x = 54, y = 6, w = w - 72, h = 19 } },
    { type = "text", text = s, frame = { x = 54, y = 25, w = w - 72, h = 17 } })
  M.pill:show()
  if pulse then
    local on = true
    M.pulse = hs.timer.doEvery(0.45, function()
      on = not on
      local a = on and 1 or 0.35
      if critter then M.pill[2].imageAlpha = a else M.pill[2].fillColor = { hex = CORAL, alpha = a } end
    end)
  end
  if seconds then M.timer = hs.timer.doAfter(seconds, hide) end
end

local function done(code, stdout, stderr)
  local last = (stdout or ""):match("([^\n]+)%s*$")
  local ok, r = pcall(hs.json.decode, last or "")
  if not ok or type(r) ~= "table" then
    r = { error = ((stderr or ""):match("([^\n]+)%s*$")) or ("listen.py exited " .. tostring(code)) }
  end
  if r.error then
    show("Inky didn't get that", r.error, 5)
    return
  end
  local heard = "“" .. tostring(r.heard) .. "”"
  local before, after = tonumber(r.matches_before), tonumber(r.matches_after)
  if before and after then -- the effect first: "46 → 14 homes", the change under it
    show(string.format("%d → %d homes", before, after), r.change or heard, 5)
  else
    show(r.change or "Done", heard, 5)
  end
end

local function pressed()
  io.open(flag, "w"):close()
  M.recording = true
  show("Listening…", "Release ⌥ Space to send · Inky keeps driving", nil, true)
  M.task = hs.task.new(python, done, { listen, "--flag", flag })
  M.task:start()
end

local function released()
  M.recording = false
  os.remove(flag)
  -- listen.py may be done already (30 s cap, no mic): then done() has shown its answer, keep it.
  if M.task:isRunning() then show("Thinking…", "Transcribing on this Mac", nil, true) end
end

-- An eventtap, not hs.hotkey: macOS 15+ refuses Option-only hotkeys, and we need the key-up.
local types = hs.eventtap.event.types
M.tap = hs.eventtap.new({ types.keyDown, types.keyUp }, function(e)
  if e:getKeyCode() ~= hs.keycodes.map.space then return false end
  local f = e:getFlags()
  if e:getType() == types.keyDown then
    if M.recording or M.busy then return true end -- swallow key repeat while held
    if not (f.alt and not f.cmd and not f.ctrl and not f.shift) then return false end
    if M.task and M.task:isRunning() then -- still on the last one: say so, done() replaces this pill
      M.busy = true
      show("Still thinking…", "Inky is on your last request · try again in a moment", nil, true)
      return true
    end
    pressed()
    return true
  end
  if M.recording then released(); return true end
  if M.busy then M.busy = false; return true end -- the key-up of a swallowed key-down
  return false
end)
M.tap:start()
-- macOS switches taps off after sleep or a slow callback; switch it back on.
M.watchdog = hs.timer.doEvery(5, function() if not M.tap:isEnabled() then M.tap:start() end end)

-- "Inky has the screen": a coral frame round the whole display while the flag file exists, and a tag at the bottom
-- with what the file says ("learning tecnocasa.it"). Clicks go through (a canvas with no mouse callback).
function M.frameCheck()
  local f = io.open(screenFlag)
  if not f then
    if M.frame then M.frame:delete(); M.frame = nil end
    return
  end
  local what = ((f:read("*a") or ""):gsub("%s+$", ""))
  f:close()
  if M.frame then return end
  local s = hs.screen.mainScreen():fullFrame()
  local t = styled("Inky has the screen" .. (what ~= "" and (" · " .. what) or ""), BOLD, 15, INK)
  local tw, th = math.ceil(hs.drawing.getTextDrawingSize(t).w) + 28, 30
  M.frame = hs.canvas.new(s)
  M.frame:level(hs.canvas.windowLevels.overlay)
  M.frame:behavior({ "canJoinAllSpaces", "stationary" })
  M.frame:appendElements(
    { type = "rectangle", action = "stroke", strokeColor = { hex = CORAL }, strokeWidth = 12,
      frame = { x = 0, y = 0, w = s.w, h = s.h } },
    { type = "rectangle", action = "fill", fillColor = { hex = CORAL },
      roundedRectangleRadii = { xRadius = 8, yRadius = 8 }, frame = { x = (s.w - tw) / 2, y = s.h - th - 6, w = tw, h = th } },
    { type = "text", text = t, frame = { x = (s.w - tw) / 2 + 14, y = s.h - th - 6 + 5, w = tw - 28, h = th - 8 } })
  M.frame:show()
end
M.frameTimer = hs.timer.doEvery(0.5, M.frameCheck)

InkyVoice = M
return M
