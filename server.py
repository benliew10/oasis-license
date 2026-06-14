#!/usr/bin/env python3
"""
Oasis / anubis license server.

Endpoints:
  POST /tapm          — license verify (AUTH=<key>_iOS4.4.0)
  GET/POST /cloudctrl/cloud_ctrl_v2 — mock MGPA cloud (securityTokenUrl)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent
LICENSES_PATH = ROOT / "licenses.json"
PUBLIC_URL_FILE = ROOT / "public_url.txt"
ACCESS_LOG = Path("/tmp/oasis_access.log")
IOS_SUFFIX_RE = re.compile(r"_iOS[\d.]+$")


def load_licenses() -> dict:
    if not LICENSES_PATH.exists():
        return {}
    return json.loads(LICENSES_PATH.read_text(encoding="utf-8"))


def save_licenses(data: dict) -> None:
    LICENSES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def public_base() -> str:
    if PUBLIC_URL_FILE.exists():
        file_url = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().rstrip("/")
        if file_url:
            return file_url
    for key in ("OASIS_PUBLIC_URL", "RENDER_EXTERNAL_URL"):
        env = os.environ.get(key, "").strip().rstrip("/")
        if env:
            return env
    return ""


def security_token_url() -> str:
    """URL anubis POSTs after MGPA/TTransceiverCloudControl sets securityTokenUrl."""
    override = os.environ.get("OASIS_SECURITY_TOKEN_URL", "").strip().rstrip("/")
    if override:
        return override if override.endswith("/tapm") else f"{override}/tapm"
    base = public_base()
    if base:
        return f"{base}/tapm"
    lan = os.environ.get("OASIS_LAN_MODE", "").strip().lower() in {"1", "true", "yes"}
    if lan:
        # start_lan.sh: hosts map k.gjacky.com → Mac; token URL keeps vendor hostname.
        return os.environ.get("OASIS_LAN_TOKEN_URL", "https://k.gjacky.com/tapm")
    return "/tapm"


def parse_auth_body(raw: str) -> str:
    params = parse_qs(raw, keep_blank_values=True)
    auth = params.get("AUTH", [""])[0].strip()
    if not auth:
        return ""
    return IOS_SUFFIX_RE.sub("", auth)


def check_license(key: str) -> tuple[bool, dict]:
    db = load_licenses()
    entry = db.get(key)
    if not entry:
        return False, {"retcode": 1, "retCode": 1, "message": "Invalid license key", "msg": "license does not exist"}

    expire = entry.get("expire", "")
    if expire:
        try:
            exp_dt = datetime.strptime(expire, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                return False, {
                    "retcode": 2,
                    "retCode": 2,
                    "message": "License expired",
                    "msg": "license expired",
                    "expire": expire,
                }
        except ValueError:
            pass

    return True, {
        "retcode": 0,
        "retCode": 0,
        "code": 0,
        "status": 0,
        "result": 0,
        "expire": expire,
        "expiration": expire,
        "businessCategory": entry.get("businessCategory", "default"),
        "message": "ok",
        "msg": "success",
    }


def cfgpush_payload() -> dict:
    """GCloud RemoteConfig /cfgpush/getConfig — include MGPA token URL for fresh clients."""
    token_url = security_token_url()
    return {
        "ret": 0,
        "retcode": 0,
        "retCode": 0,
        "code": 0,
        "status": 0,
        "msg": "success",
        "message": "ok",
        "securityTokenUrl": token_url,
        "mgpaCloud": {
            "retcode": 0,
            "retCode": 0,
            "securityTokenUrl": token_url,
        },
        "data": {
            "update_interval": 3600,
            "securityTokenUrl": token_url,
            "mgpaCloud": {
                "retcode": 0,
                "securityTokenUrl": token_url,
            },
            "rules": [],
            "config": {"securityTokenUrl": token_url},
        },
    }


def cloudctrl_payload() -> dict:
    """MGPA / .mgpacloud cloud config — replaces Tencent cloudctrl.igamecj.com response."""
    token_url = security_token_url()
    base = public_base()
    return {
        "retcode": 0,
        "retCode": 0,
        "code": 0,
        "status": 0,
        "cloudCtrlVersion": "1.3.3.0",
        "securityTokenUrl": token_url,
        "security_token_url": token_url,
        "mgpaCloud": {
            "retcode": 0,
            "retCode": 0,
            "securityTokenUrl": token_url,
            "security_token_url": token_url,
        },
        "data": {
            "securityTokenUrl": token_url,
            "mgpaCloud": {"securityTokenUrl": token_url, "retcode": 0},
        },
        "config": {
            "securityTokenUrl": token_url,
            "remoteConfigUrl": base,
        },
    }


def is_cloudctrl_path(path: str) -> bool:
    p = path.rstrip("/") or "/"
    if p in ("/cloudctrl", "/.mgpacloud", "/cloudctrl/cloud_ctrl_v2"):
        return True
    return p.endswith("/cloud_ctrl_v2") or p.endswith("/cloudctrl/cloud_ctrl_v2")


def is_cfgpush_path(path: str) -> bool:
    p = path.rstrip("/") or "/"
    return p == "/cfgpush/getConfig" or p.endswith("/cfgpush/getConfig")


class OasisHandler(BaseHTTPRequestHandler):
    server_version = "OasisLicense/2.0"

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_request_line(self) -> None:
        ua = self.headers.get("User-Agent", "")
        host = self.headers.get("Host", "")
        self.log_message("%s %s host=%r ua=%r", self.command, self.path, host, ua)

    def log_message(self, fmt: str, *args) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {self.address_string()} {fmt % args}\n"
        sys.stderr.write(line)
        try:
            with ACCESS_LOG.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return ""
        return self.rfile.read(length).decode("utf-8", errors="replace")

    def _handle_tapm(self, raw: str) -> None:
        key = parse_auth_body(raw)
        self.log_message(
            "TAPM %s key=%r raw=%r ua=%r",
            self.command,
            key,
            raw[:200],
            self.headers.get("User-Agent", ""),
        )
        if not key:
            self._send_json(200, {"retcode": 1, "message": "Missing AUTH field"})
            return
        _ok, payload = check_license(key)
        self._send_json(200, payload)

    def _handle_cloudctrl(self) -> None:
        self.log_message("MGPA/CLOUDCTRL %s %s token=%s", self.command, self.path, security_token_url())
        self._send_json(200, cloudctrl_payload())

    def _handle_cfgpush(self) -> None:
        self.log_message("GCLOUD/CFGPUSH %s %s ua=%r", self.command, self.path, self.headers.get("User-Agent", ""))
        self._send_json(200, cfgpush_payload())

    def do_GET(self) -> None:
        self.log_request_line()
        path = self._path()
        if path in ("/", "/health"):
            self._send_json(200, {"ok": True, "service": "oasis-license", "public": public_base()})
            return
        if path == "/tapm":
            self._handle_tapm(self.headers.get("AUTH", "") or "")
            return
        if is_cfgpush_path(path):
            self._handle_cfgpush()
            return
        if is_cloudctrl_path(path) or path == "/.mgpacloud":
            self._handle_cloudctrl()
            return
        self.log_message("GET 404 %s ua=%r", self.path, self.headers.get("User-Agent", ""))
        self.send_error(404)

    def do_POST(self) -> None:
        self.log_request_line()
        path = self._path()
        raw = self._read_body()
        # anubis may POST to http://host:8080/ (no /tapm path) when URL is 24-char padded
        if path in ("/tapm", "/"):
            self._handle_tapm(raw)
            return
        if is_cfgpush_path(path):
            self._handle_cfgpush()
            return
        if is_cloudctrl_path(path) or path == "/.mgpacloud":
            self._handle_cloudctrl()
            return
        self.log_message("POST 404 %s body=%r ua=%r", self.path, raw[:120], self.headers.get("User-Agent", ""))
        self.send_error(404)


def main() -> None:
    parser = argparse.ArgumentParser(description="Oasis anubis license server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--public-url", default="", help="HTTPS base URL (no trailing slash)")
    parser.add_argument("--cert", default="", help="TLS certificate PEM (for HTTPS / port 443)")
    parser.add_argument("--key", default="", help="TLS private key PEM")
    args = parser.parse_args()

    port_env = os.environ.get("PORT", "").strip()
    if port_env.isdigit():
        args.port = int(port_env)

    if not args.public_url:
        args.public_url = (
            os.environ.get("OASIS_PUBLIC_URL", "").strip()
            or os.environ.get("RENDER_EXTERNAL_URL", "").strip()
        )

    if args.public_url:
        PUBLIC_URL_FILE.write_text(args.public_url.rstrip("/") + "\n", encoding="utf-8")

    if not LICENSES_PATH.exists():
        save_licenses({})
        print(f"Created empty {LICENSES_PATH}")

    httpd = ThreadingHTTPServer((args.host, args.port), OasisHandler)
    scheme = "http"
    if args.cert and args.key:
        import ssl

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(args.cert, args.key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    lan = os.environ.get("OASIS_LAN_MODE", "").strip().lower() in {"1", "true", "yes"}
    print(f"Listening {scheme}://{args.host}:{args.port}")
    print(f"LAN mode: {lan}")
    print(f"securityTokenUrl: {security_token_url()}")
    print(f"Public URL: {public_base() or '(set OASIS_PUBLIC_URL or --public-url)'}")
    print("Endpoints: POST /tapm, GET/POST /cloudctrl/cloud_ctrl_v2, GET/POST /cfgpush/getConfig")
    print(f"Access log: {ACCESS_LOG}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
