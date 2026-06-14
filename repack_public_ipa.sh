#!/bin/bash
# Full public HTTPS repack: anubis URLs + SSL patch + curl redirect dylib in anubis.
#
# Usage:
#   ./repack_public_ipa.sh https://oasismod.qzz.io/tapm
#
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
INSERT_DYLIB="${INSERT_DYLIB:-/Users/Apple/Downloads/vphone-cli/.tools/bin/insert_dylib}"

CC_URL="${1:-}"
OUT="${2:-/Users/Apple/Desktop/oasis_public_license.ipa}"
ORIG="${ORIG_IPA:-/Users/Apple/Downloads/0asis.io_com.tencent.ig_4.4.0_15052026.ipa}"

if [[ -z "$CC_URL" ]]; then
  echo "Usage: $0 <https://your-domain/tapm> [output.ipa]"
  exit 1
fi
[[ "$CC_URL" == https://* ]] || { echo "Must be HTTPS"; exit 1; }

BASE="${CC_URL%/tapm}"
BASE="${BASE%/}"
(( ${#BASE} <= 29 )) || { echo "FAIL: base URL > 29 chars: $BASE"; exit 1; }

echo "Testing $BASE ..."
curl -sS -m 25 "${BASE}/health" | grep -q '"ok"' || { echo "FAIL: ${BASE}/health"; exit 1; }

WORK="$(mktemp -d)"
TMP1="$WORK/step1.ipa"
TMP2="$WORK/step2.ipa"
STAGE="$WORK/stage"
trap 'rm -rf "$WORK"' EXIT

echo "=== 1) anubis embedded URL patch ==="
python3 "$DIR/patch_anubis_mgpa.py" "$ORIG" "$TMP1" --base "$BASE" --tapm "$CC_URL"

echo "=== 2) Info.plist ==="
"$DIR/repack_cc_url.sh" "$TMP1" "$CC_URL" "$TMP2"

echo "=== 3) anubis SSL patch + curl redirect dylib ==="
[[ -x "$INSERT_DYLIB" ]] || { echo "Missing insert_dylib: $INSERT_DYLIB"; exit 1; }
"$ROOT/logger-dylib/build_redirect_dylib.sh"
rm -rf "$STAGE" && mkdir -p "$STAGE"
unzip -q "$TMP2" -d "$STAGE"

APP="$(ls -d "$STAGE"/Payload/*.app | head -n 1)"
ANUBIS_FW="$APP/Frameworks/anubis.framework"
ANUBIS_BIN="$ANUBIS_FW/anubis"

python3 <<PY
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location("ssl", "$DIR/patch_anubis_ssl.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
p = Path("$ANUBIS_BIN")
data = bytearray(p.read_bytes())
n = mod.patch_binary(data)
p.write_bytes(data)
print(f"SSL patch: {n} instruction(s)")
PY

DYLIB_NAME="anubis_redirect.dylib"
cp "$ROOT/logger-dylib/$DYLIB_NAME" "$ANUBIS_FW/$DYLIB_NAME"
chmod 755 "$ANUBIS_FW/$DYLIB_NAME"
LOAD="@loader_path/$DYLIB_NAME"
if ! otool -l "$ANUBIS_BIN" | awk '/LC_LOAD_DYLIB/{show=1} show && /name/{print; show=0}' | grep -q "$DYLIB_NAME"; then
  "$INSERT_DYLIB" --all-yes --strip-codesig "$LOAD" "$ANUBIS_BIN" "$ANUBIS_BIN.patched"
  mv "$ANUBIS_BIN.patched" "$ANUBIS_BIN"
  chmod 755 "$ANUBIS_BIN"
fi

# token redirect in main binary (MGPA setSecurityTokenUrl)
"$ROOT/logger-dylib/build_token_redirect_dylib.sh"
MAIN="$APP/ShadowTrackerExtra"
cp "$ROOT/logger-dylib/oasis_token_redirect.dylib" "$APP/Frameworks/oasis_token_redirect.dylib"
chmod 755 "$APP/Frameworks/oasis_token_redirect.dylib"
TLOAD="@executable_path/Frameworks/oasis_token_redirect.dylib"
if ! otool -l "$MAIN" | awk '/LC_LOAD_DYLIB/{show=1} show && /name/{print; show=0}' | grep -q oasis_token_redirect; then
  "$INSERT_DYLIB" --all-yes --strip-codesig "$TLOAD" "$MAIN" "$MAIN.patched"
  mv "$MAIN.patched" "$MAIN"
  chmod 755 "$MAIN"
fi

rm -f "$OUT"
( cd "$STAGE" && COPYFILE_DISABLE=1 zip -qr "$OUT" Payload )

echo "=== 4) verify ==="
python3 <<PY
import zipfile, subprocess, tempfile, shutil, plistlib
ipa = "$OUT"
work = tempfile.mkdtemp()
with zipfile.ZipFile(ipa) as z:
    z.extractall(work)
app = work + "/Payload/ShadowTrackerExtra.app"
dec = bytes(b^0xAA for b in open(app+"/Frameworks/anubis.framework/anubis",'rb').read())
assert b"k.gjacky.com" not in dec
host = "${BASE#https://}".encode()
assert host in dec
otool = subprocess.check_output(["otool","-L",app+"/ShadowTrackerExtra"], text=True)
assert "oasis_token_redirect" in otool
assert "anubis_redirect" in subprocess.check_output(["otool","-L",app+"/Frameworks/anubis.framework/anubis"], text=True)
p = plistlib.loads(open(app+"/Info.plist",'rb').read())
assert p["TAPM"]["CC_URL"] == "$CC_URL"
print("OK:", "$CC_URL")
shutil.rmtree(work)
PY

echo "Wrote $OUT"
