#!/bin/sh
# Inky on a server (Linux) or a spare Mac, in one line:
#   curl -fsSL https://raw.githubusercontent.com/GHGuide/inky/main/install.sh | sh
# It keeps running after you log out and starts again after a reboot. At the end it prints a pair link
# (inky://pair?...) and a code: open the link on your computer, or type the address and code in Computers.
# Options:
#   --docker | --python   how to run it (default: Docker if it's there, else Python)
#   --port 8800           the port it listens on
#   --json                print only {"url","code"} (the app's "Set up over SSH" uses this)
#   --no-service          run it in the background without a service (for tests)
set -eu

MODE=auto PORT=8800 JSON=0 SERVICE=1
REPO="${INKY_REPO:-https://github.com/GHGuide/inky}"
SRC="${INKY_SRC:-$HOME/.inky-src}"
DATA="${INKY_HOME:-$HOME/.inky}"
while [ $# -gt 0 ]; do
  case "$1" in
    --docker) MODE=docker ;;
    --python) MODE=python ;;
    --port) PORT="$2"; shift ;;
    --json) JSON=1 ;;
    --no-service) SERVICE=0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

say() { if [ "$JSON" = 1 ]; then echo "$*" >&2; else echo "$*"; fi; }  # with --json, progress goes to stderr
fail() {  # $1 what went wrong, $2 how to fix it
  if [ "$JSON" = 1 ]; then printf '{"error":"%s","fix":"%s"}\n' "$1" "$2"; else printf 'Inky: %s.\n%s\n' "$1" "$2" >&2; fi
  exit 1
}
have() { command -v "$1" >/dev/null 2>&1; }
root() { if [ "$(id -u)" = 0 ]; then "$@"; elif have sudo && sudo -n true 2>/dev/null; then sudo -n "$@"; else return 1; fi; }

OS=$(uname -s)
case "$OS" in Linux|Darwin) ;; *) fail "this computer runs $OS" "The installer is for Linux or macOS. On Windows, use the Inky app." ;; esac
case "$PORT" in *[!0-9]*|'') fail "the port must be a number" "Use --port 8800" ;; esac

# ---- the code
if [ ! -f "$SRC/inky/__main__.py" ]; then
  say "Getting Inky…"
  if have git; then
    git clone --quiet --depth 1 "$REPO" "$SRC" >&2 || fail "couldn't download Inky" "Check this server can reach github.com"
  elif have curl; then
    mkdir -p "$SRC" && curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" | tar xz -C "$SRC" --strip-components 1 \
      || fail "couldn't download Inky" "Check this server can reach github.com"
  else
    fail "neither git nor curl is installed" "Install one of them (for example: sudo apt install -y git)"
  fi
elif [ -d "$SRC/.git" ] && have git; then
  git -C "$SRC" pull --quiet --ff-only >&2 || true
fi

if [ "$MODE" = auto ]; then
  if have docker && docker info >/dev/null 2>&1; then MODE=docker; else MODE=python; fi
fi

ip_addr() {
  if [ "$OS" = Darwin ]; then ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1
  else hostname -I 2>/dev/null | awk '{print $1}' | grep . || ip route get 1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") print $(i+1)}' || echo 127.0.0.1
  fi
}

# ---- run it
if [ "$MODE" = docker ]; then
  have docker || fail "Docker isn't installed" "Run again with --python, or install Docker"
  say "Building Inky (a few minutes the first time)…"
  docker build -q -t inky "$SRC" >&2 || fail "the Docker build failed" "Run: docker build -t inky $SRC to see why"
  docker rm -f inky >/dev/null 2>&1 || true
  docker run -d --name inky --restart unless-stopped -p "$PORT:8800" -v inky-data:/data inky >/dev/null \
    || fail "Docker couldn't start Inky" "Is port $PORT free? Try --port 8801"
  CODE=""
  for _ in $(seq 60); do
    CODE=$(docker logs inky 2>&1 | sed -n 's/.*Pairing code for other computers: //p' | tail -1)
    [ -n "$CODE" ] && break
    sleep 1
  done
else
  have python3 || fail "Python 3 isn't installed" "Install python3 (3.11 or newer), or Docker"
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail "Python is older than 3.11" "Install python3.11 or newer, or Docker"
  if [ ! -x "$SRC/.venv/bin/python" ]; then
    say "Setting up Python…"
    python3 -m venv "$SRC/.venv" >&2 || fail "Python can't make a venv" "Install it: sudo apt install -y python3-venv"
  fi
  PY="$SRC/.venv/bin/python"
  "$PY" -m pip install -q --disable-pip-version-check "playwright==1.63.0" "httpx==0.28.1" >&2 || fail "couldn't install Inky's two libraries" "Check this server can reach pypi.org"
  if [ "${INKY_SKIP_BROWSER:-0}" != 1 ]; then
    say "Getting the bots' browser (about 170 MB)…"
    if [ "$OS" = Linux ]; then
      root env PATH="$PATH" "$PY" -m playwright install-deps chromium >&2 || say "Couldn't install the browser's system libraries (needs sudo). If bots can't start, run: sudo $PY -m playwright install-deps chromium"
    fi
    PLAYWRIGHT_BROWSERS_PATH="$DATA/browsers" "$PY" -m playwright install chromium >&2 || fail "couldn't download the browser" "Check this server can reach playwright.azureedge.net"
  fi
  mkdir -p "$DATA"
  rm -f "$DATA/engine.json"  # an engine.json left from an earlier run would end the wait below before this one listens
  ARGS="-m inky --host 0.0.0.0 --port $PORT --home $DATA --no-open --name $(hostname -s 2>/dev/null || echo server)"
  if [ "$SERVICE" = 0 ]; then
    (cd "$SRC" && PLAYWRIGHT_BROWSERS_PATH="$DATA/browsers" INKY_HEADLESS=1 nohup "$PY" $ARGS >"$DATA/engine.log" 2>&1 &)
  elif [ "$OS" = Darwin ]; then
    PL="$HOME/Library/LaunchAgents/com.github.ghguide.inky.plist"
    mkdir -p "$(dirname "$PL")"
    cat >"$PL" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.github.ghguide.inky</string>
  <key>ProgramArguments</key><array><string>$PY</string>$(for a in $ARGS; do printf '<string>%s</string>' "$a"; done)</array>
  <key>WorkingDirectory</key><string>$SRC</string>
  <key>EnvironmentVariables</key><dict><key>PLAYWRIGHT_BROWSERS_PATH</key><string>$DATA/browsers</string><key>INKY_HEADLESS</key><string>1</string></dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DATA/engine.log</string><key>StandardErrorPath</key><string>$DATA/engine.log</string>
</dict></plist>
EOF
    launchctl unload "$PL" 2>/dev/null || true
    launchctl load -w "$PL"
  else
    have systemctl || fail "this server has no systemd" "Run again with --docker, or --no-service to start it by hand"
    UNIT="$HOME/.config/systemd/user/inky.service"
    mkdir -p "$(dirname "$UNIT")"
    cat >"$UNIT" <<EOF
[Unit]
Description=Inky: bots with their own browsers
After=network-online.target

[Service]
WorkingDirectory=$SRC
Environment=PLAYWRIGHT_BROWSERS_PATH=$DATA/browsers INKY_HEADLESS=1 PYTHONUNBUFFERED=1
ExecStart=$PY $ARGS
Restart=always

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload && systemctl --user enable inky >&2 && systemctl --user restart inky >&2 \
      || fail "systemd couldn't start Inky" "Run: systemctl --user status inky"
    loginctl enable-linger "$(id -un)" 2>/dev/null || root loginctl enable-linger "$(id -un)" 2>/dev/null \
      || say "Note: Inky stops when you log out until an admin runs: sudo loginctl enable-linger $(id -un)"
  fi
  CODE=""
  for _ in $(seq 60); do  # the engine writes engine.json once it listens; the code is made from its token
    if [ -f "$DATA/engine.json" ] && [ -f "$DATA/api_token" ]; then
      CODE=$(cd "$SRC" && "$PY" -c 'import sys; from inky.transfer import pair_code; print(pair_code(open(sys.argv[1]).read().strip()))' "$DATA/api_token")
      break
    fi
    sleep 1
  done
fi

[ -n "$CODE" ] || fail "Inky didn't start" "See $DATA/engine.log (or docker logs inky)"
URL="http://$(ip_addr):$PORT"
if [ "$JSON" = 1 ]; then
  printf '{"url":"%s","code":"%s"}\n' "$URL" "$CODE"
  exit 0
fi
ENC=$(printf %s "$URL" | sed 's/:/%3A/g; s#/#%2F#g')
LINK="inky://pair?url=$ENC&code=$CODE"
echo ""
echo "Inky is running on this server, and starts again after a reboot."
echo ""
echo "  Pair it from your computer: open this link, or in Inky go to Computers and paste it."
echo "  $LINK"
echo ""
echo "  Or type:  $URL   code $CODE"
if have tailscale && TS=$(tailscale ip -4 2>/dev/null | head -1) && [ -n "$TS" ]; then
  echo "  Away from home (Tailscale):  http://$TS:$PORT"
fi
if have qrencode; then echo ""; qrencode -t ANSIUTF8 "$LINK"; fi
