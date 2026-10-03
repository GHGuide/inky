#!/bin/bash
# One-time Apple setup for notarized Inky builds. Run it yourself in Terminal: it asks for your passwords and never
# shows, saves or passes them on the command line.
#
#   desktop/scripts/setup-apple-signing.sh                   # notarize builds on this Mac
#   desktop/scripts/setup-apple-signing.sh ~/Desktop/devid.p12   # also every GitHub release
#
# Before you run it:
#   1. An app-specific password: https://account.apple.com → Sign-In and Security → App-Specific Passwords → "Inky notary".
#   2. Only for releases: export your "Developer ID Application" certificate from Keychain Access (the script deletes
#      that .p12 once it is uploaded)
#      (My Certificates → right-click it → Export… → .p12, and give it a password).
set -euo pipefail
TEAM="${APPLE_TEAM_ID:-YMCFJBC2DG}"
REPO="${INKY_REPO:-GHGuide/inky}"
IDENTITY=$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application: .*\)"/\1/p' | head -1)
[ -n "$IDENTITY" ] || { echo "No Developer ID Application certificate in your keychain. Make one at developer.apple.com → Certificates."; exit 1; }
echo "Signing identity: $IDENTITY"
read -rp "Your Apple ID (email): " APPLE_ID

echo
echo "1/2 · Saving notary credentials on this Mac as \"inky-notary\". Paste the app-specific password when asked."
xcrun notarytool store-credentials inky-notary --apple-id "$APPLE_ID" --team-id "$TEAM"

P12="${1:-}"
if [ -z "$P12" ]; then
  echo
  echo "Done for this Mac. To notarize GitHub releases too, export the certificate (see the top of this file) and run:"
  echo "  $0 /path/to/devid.p12"
  exit 0
fi
[ -f "$P12" ] || { echo "No file at $P12"; exit 1; }
command -v gh >/dev/null && gh auth status >/dev/null 2>&1 || { echo "Sign in to GitHub's gh tool first: gh auth login"; exit 1; }

echo
echo "2/2 · Adding the release secrets to $REPO."
base64 -i "$P12" | gh secret set APPLE_CERTIFICATE -R "$REPO"
echo "Paste the password you gave the .p12:"
gh secret set APPLE_CERTIFICATE_PASSWORD -R "$REPO"
printf %s "$IDENTITY" | gh secret set APPLE_SIGNING_IDENTITY -R "$REPO"
printf %s "$APPLE_ID" | gh secret set APPLE_ID -R "$REPO"
printf %s "$TEAM" | gh secret set APPLE_TEAM_ID -R "$REPO"
echo "Paste the app-specific password again (for notarizing in releases):"
gh secret set APPLE_PASSWORD -R "$REPO"
rm -P "$P12" 2>/dev/null || rm -f "$P12"  # the exported key isn't needed on disk any more
echo
echo "Done. From the next release on, macOS builds are signed with your Developer ID and notarized."
