import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("server", ROOT / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

KEY = "Oas01g7o1pOT6wYZ7U5GFuPUuVqnRaZd"
AUTH = f"{KEY}_iOS4.4.0"


def test_parse_auth_body_form():
    assert server.parse_auth_body(f"AUTH={AUTH}") == KEY


def test_parse_auth_body_bare_token():
    assert server.parse_auth_body(AUTH) == KEY


def test_parse_auth_body_empty():
    assert server.parse_auth_body("") == ""


def test_cloudctrl_has_switch_and_config():
    payload = server.cloudctrl_payload()
    assert "switch" in payload["data"]
    assert "config" in payload["data"]
    assert payload["data"]["config"]["securityTokenUrl"].endswith("/tapm")


def test_check_license_valid():
    ok, body = server.check_license(KEY)
    assert ok is True
    assert body["retcode"] == 0


def test_check_license_invalid():
    ok, body = server.check_license("badkey")
    assert ok is False
    assert body["retcode"] == 1
