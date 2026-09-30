#!/bin/sh
# Builds InkyBar.app (menu bar, system-wide shortcuts, floating command bar). Needs Xcode or the Command Line Tools.
set -e
cd "$(dirname "$0")"
APP=build/InkyBar.app
rm -rf "$APP" && mkdir -p "$APP/Contents/MacOS"
swiftc -O -swift-version 5 -framework AppKit -framework WebKit -framework Carbon InkyBar.swift -o "$APP/Contents/MacOS/InkyBar"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>InkyBar</string>
  <key>CFBundleDisplayName</key><string>Inky</string>
  <key>CFBundleIdentifier</key><string>org.inky.bar</string>
  <key>CFBundleExecutable</key><string>InkyBar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
codesign --force --sign - "$APP" >/dev/null 2>&1 || true
echo "built $APP"
