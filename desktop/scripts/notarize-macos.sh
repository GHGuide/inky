#!/bin/sh
# Notarizes and staples a macOS build made on this Mac, so it opens without "can't verify" on any Mac.
#
# Once per Mac (you, not a script: it asks for an app-specific password from appleid.apple.com):
#   xcrun notarytool store-credentials inky-notary --apple-id <your Apple ID> --team-id YMCFJBC2DG
# Then:
#   APPLE_SIGNING_IDENTITY="Developer ID Application: <name> (<team>)" npm run tauri build   (in desktop/)
#   desktop/scripts/notarize-macos.sh
set -eu
cd "$(dirname "$0")/.."
BUNDLE=src-tauri/target/release/bundle
APP="$BUNDLE/macos/Inky.app"
DMG=$(ls -t "$BUNDLE"/dmg/*.dmg 2>/dev/null | head -1)
PROFILE="${INKY_NOTARY_PROFILE:-inky-notary}"
[ -n "$DMG" ] || { echo "No .dmg in $BUNDLE/dmg: build first."; exit 1; }
codesign --verify --deep --strict "$APP"
codesign -dv "$APP" 2>&1 | grep -q "Authority=Developer ID Application" || { echo "Inky.app isn't signed with a Developer ID: build with APPLE_SIGNING_IDENTITY set."; exit 1; }
echo "Sending $DMG to Apple's notary service (a few minutes)…"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
xcrun stapler staple "$DMG"
spctl --assess --type execute -vv "$APP"
echo "Notarized and stapled: $DMG"
