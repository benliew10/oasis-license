#!/bin/bash
# Point Oasis IPA at your license server + redirect MGPA cloudctrl to same host.
# See patch_mgpacloud.sh for MGPA-specific repack with before/after output.
set -euo pipefail

IPA_IN="${1:-/Users/Apple/Downloads/0asis.io_com.tencent.ig_4.4.0_15052026.ipa}"
CC_URL="${2:-}"
OUT="${3:-}"

if [[ -z "$CC_URL" ]]; then
  echo "Usage: $0 <input.ipa> <https://your-server.com/tapm> [output.ipa]"
  exit 1
fi

# Base URL without /tapm path
BASE="${CC_URL%/tapm}"
BASE="${BASE%/}"

if [[ -z "$OUT" ]]; then
  base="$(basename "$IPA_IN" .ipa)"
  OUT="$(dirname "$IPA_IN")/${base}_custom_license.ipa"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Unpacking $IPA_IN ..."
unzip -q "$IPA_IN" -d "$WORK"
PLIST="$WORK/Payload/ShadowTrackerExtra.app/Info.plist"
[[ -f "$PLIST" ]] || { echo "Info.plist missing"; exit 1; }

echo "Setting TAPM.CC_URL -> ${BASE}/tapm"
/usr/libexec/PlistBuddy -c "Delete :TAPM:CC_URL" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :TAPM:CC_URL string ${BASE}/tapm" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :TAPM:CC_URL ${BASE}/tapm" "$PLIST"

echo "Setting GCloudCore.RemoteConfigUrl -> $BASE"
/usr/libexec/PlistBuddy -c "Delete :GCloudCore:RemoteConfigUrl" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :GCloudCore:RemoteConfigUrl string $BASE" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :GCloudCore:RemoteConfigUrl $BASE" "$PLIST"

echo "Verify:"
/usr/libexec/PlistBuddy -c "Print :TAPM" "$PLIST"
/usr/libexec/PlistBuddy -c "Print :GCloudCore:RemoteConfigUrl" "$PLIST"

( cd "$WORK" && zip -qr "$OUT" Payload )
echo "Wrote $OUT"
echo "IMPORTANT: Delete old PUBG from iPhone before install (clears .mgpacloud cache)."
