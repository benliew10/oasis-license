#!/bin/bash
# Install Oasis license server on Ubuntu/Debian VPS with Caddy TLS (Let's Encrypt).
# Run ON THE VPS as root after DNS A record points to this machine.
#
# Usage:
#   sudo DOMAIN=license.yourdomain.com bash install_vps.sh
#
set -euo pipefail

DOMAIN="${DOMAIN:?Set DOMAIN=license.yourdomain.com}"
APP_DIR="/opt/oasis-license"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Oasis license server → https://${DOMAIN} ==="

apt-get update -qq
apt-get install -y -qq python3 caddy curl

mkdir -p "$APP_DIR"
cp "$SRC/server.py" "$SRC/licenses.json" "$APP_DIR/"
echo "https://${DOMAIN}" > "$APP_DIR/public_url.txt"

cat > /etc/systemd/system/oasis-license.service <<EOF
[Unit]
Description=Oasis license server
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
Environment=OASIS_PUBLIC_URL=https://${DOMAIN}
ExecStart=/usr/bin/python3 ${APP_DIR}/server.py --host 127.0.0.1 --port 8080 --public-url https://${DOMAIN}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    reverse_proxy 127.0.0.1:8080
}
EOF

systemctl daemon-reload
systemctl enable --now oasis-license
systemctl reload caddy || systemctl restart caddy

sleep 3
echo ""
echo "=== Health ==="
curl -sS "https://${DOMAIN}/health" | head -c 200
echo ""
echo ""
echo "=== cloudctrl (MGPA reads securityTokenUrl from here) ==="
curl -sS "https://${DOMAIN}/cloudctrl/cloud_ctrl_v2" | python3 -m json.tool 2>/dev/null | head -20
echo ""
echo "=== License test ==="
curl -sS -X POST "https://${DOMAIN}/tapm" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "AUTH=Oas01g7o1pOT6wYZ7U5GFuPUuVqnRaZd_iOS4.4.0"
echo ""
echo ""
echo "DONE. Repack IPA on Mac:"
echo "  cd ~/Downloads/hok-frida-capture/oasis-license-server"
echo "  ./repack_public_ipa.sh https://${DOMAIN}/tapm"
