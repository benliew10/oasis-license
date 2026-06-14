#!/bin/bash
# Repack stock Oasis IPA for a PUBLIC HTTPS server (like original k.gjacky.com flow).
# No LAN IP, no dylib, no Mac must stay on.
#
# Usage:
#   ./repack_public_ipa.sh https://license.yourdomain.com/tapm
#
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

CC_URL="${1:-}"
OUT="${2:-/Users/Apple/Desktop/oasis_public_license.ipa}"
ORIG="${ORIG_IPA:-/Users/Apple/Downloads/0asis.io_com.tencent.ig_4.4.0_15052026.ipa}"

if [[ -z "$CC_URL" ]]; then
  echo "Usage: $0 <https://your-domain.com/tapm> [output.ipa]"
  echo ""
  echo "Example:"
  echo "  $0 https://license.example.com/tapm"
  exit 1
fi

[[ "$CC_URL" == https://* ]] || { echo "Must be HTTPS (anubis rejects self-signed; use Let's Encrypt on VPS)"; exit 1; }

BASE="${CC_URL%/tapm}"
BASE="${BASE%/}"

echo "Testing remote server..."
curl -sS -m 20 "${BASE}/health" | grep -q '"ok"' || { echo "FAIL: ${BASE}/health unreachable"; exit 1; }
TOKEN=$(curl -sS -m 20 "${BASE}/cloudctrl/cloud_ctrl_v2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('securityTokenUrl',''))")
if [[ "$TOKEN" != *"${BASE#https://}"* && "$TOKEN" != "${CC_URL}" ]]; then
  echo "WARN: cloudctrl securityTokenUrl=$TOKEN (expected ${CC_URL})"
else
  echo "OK: cloudctrl securityTokenUrl=$TOKEN"
fi

"$DIR/repack_cc_url.sh" "$ORIG" "$CC_URL" "$OUT"

echo ""
echo "Wrote $OUT"
echo ""
echo "Plist patched:"
echo "  GCloudCore.RemoteConfigUrl = $BASE"
echo "  TAPM.CC_URL              = $CC_URL"
echo ""
echo "iPhone:"
echo "  1. Delete PUBG (Delete App)"
echo "  2. Install $OUT"
echo "  3. Enter key from licenses.json"
echo "  (No Mac needed. No Local Network. No reboot if app was deleted.)"
