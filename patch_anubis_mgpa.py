#!/usr/bin/env python3
"""
Patch embedded GCloud/MGPA URLs inside anubis.framework/anubis (XOR 0xAA plist fragment).

Offsets (stock 4.4.0 Oasis IPA):
  RemoteConfigUrl @ 0x196da28  — max 29 bytes (e.g. https://cloudctrl.igamecj.com)
  TAPM.CC_URL     @ 0x196d773  — max 25 bytes (e.g. https://k.gjacky.com/tapm)

MGPA cloudctrl uses the embedded RemoteConfigUrl copy, NOT the app Info.plist alone.
cfgpush reads app plist — that is why plist-only repacks show cfgpush hits but no license POST.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ANUBIS_REL = Path("Payload/ShadowTrackerExtra.app/Frameworks/anubis.framework/anubis")
XOR_KEY = 0xAA

OLD_REMOTE = b"https://cloudctrl.igamecj.com"
OLD_CC = b"https://k.gjacky.com/tapm"
OFF_REMOTE = 0x196DA28
OFF_CC = 0x196D773

DISABLED_CC = "http://127.0.0.1:9/disab"  # last resort


def cc_embed_url(base: str, tapm_url: str | None) -> str:
    """Pick anubis CC_URL embed (25 bytes max). Server accepts POST /, /t, and /tapm."""
    cc_url = tapm_url or f"{base}/tapm"
    if len(cc_url) <= len(OLD_CC):
        return cc_url
    short = f"{base}/t"
    if len(short) <= len(OLD_CC):
        print(f"NOTE: CC embed -> {short!r} (25-byte slot; server alias /t -> /tapm)")
        return short
    root = f"{base}/"
    if len(root) <= len(OLD_CC):
        print(f"NOTE: CC embed -> {root!r} (POST / on server)")
        return root
    print(f"NOTE: CC embed -> {DISABLED_CC!r}")
    return DISABLED_CC


def xor_encode(url: str, slot: int, label: str) -> bytes:
    raw = bytearray(url.encode("ascii"))
    if len(raw) > slot:
        raise ValueError(f"{label} max {slot} bytes, got {len(raw)}: {url!r}")
    while len(raw) < slot:
        raw.append(0)
    return bytes(b ^ XOR_KEY for b in raw)


def xor_decode(data: bytes, offset: int, length: int) -> str:
    enc = data[offset : offset + length]
    raw = bytes(b ^ XOR_KEY for b in enc)
    return raw.split(b"\x00")[0].decode("ascii", errors="replace")


def find_or_fail(data: bytearray, enc_old: bytes, expected: int, name: str) -> int:
    if data[expected : expected + len(enc_old)] == enc_old:
        return expected
    found = data.find(enc_old)
    if found < 0:
        raise SystemExit(f"{name}: expected bytes not found (checked {hex(expected)})")
    return found


def patch_slot(
    data: bytearray,
    offset: int,
    old_plain: bytes,
    new_url: str,
    label: str,
) -> int:
    slot = len(old_plain)
    enc_old = bytes(b ^ XOR_KEY for b in old_plain)
    offset = find_or_fail(data, enc_old, offset, label)
    before = xor_decode(data, offset, slot)
    enc_new = xor_encode(new_url, slot, label)
    data[offset : offset + slot] = enc_new
    print(f"Patched {label} @ {hex(offset)}")
    print(f"  was: {before!r}")
    print(f"  now: {new_url!r}")
    return offset


def verify_clean(data: bytes) -> None:
    dec = bytes(b ^ XOR_KEY for b in data)
    bad = []
    for needle in (b"cloudctrl.igamecj.com", b"k.gjacky.com"):
        if needle in dec:
            bad.append(needle.decode())
    if bad:
        raise SystemExit(f"VERIFY FAIL: still contains {bad}")


def patch_ipa(ipa_in: Path, ipa_out: Path, base_url: str, tapm_url: str | None) -> None:
    base = base_url.rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("base_url must be https://…")
    if len(base) > len(OLD_REMOTE):
        raise ValueError(
            f"base_url must be ≤{len(OLD_REMOTE)} chars for anubis embed, got {len(base)}: {base!r}\n"
            f"Use a short Render name (e.g. https://oasis.onrender.com) or a short custom domain."
        )

    cc_url = tapm_url or f"{base}/tapm"
    cc_embed = cc_embed_url(base, tapm_url)
    if cc_embed != cc_url and cc_embed != f"{base}/":
        pass  # message printed in cc_embed_url

    work = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(ipa_in) as zf:
            zf.extractall(work)
        anubis = work / ANUBIS_REL
        if not anubis.exists():
            raise SystemExit(f"missing {anubis}")

        data = bytearray(anubis.read_bytes())
        print(f"Before RemoteConfigUrl: {xor_decode(data, OFF_REMOTE, len(OLD_REMOTE))!r}")
        print(f"Before CC_URL:          {xor_decode(data, OFF_CC, len(OLD_CC))!r}")

        patch_slot(data, OFF_REMOTE, OLD_REMOTE, base, "RemoteConfigUrl")
        patch_slot(data, OFF_CC, OLD_CC, cc_embed, "CC_URL")
        verify_clean(data)
        anubis.write_bytes(data)

        if ipa_out.exists():
            ipa_out.unlink()
        subprocess.run(["zip", "-qr", str(ipa_out), "Payload"], cwd=work, check=True)
        print(f"Wrote {ipa_out}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Patch anubis embedded MGPA/GCloud URLs")
    p.add_argument("ipa_in")
    p.add_argument("ipa_out")
    p.add_argument("--base", required=True, help=f"RemoteConfigUrl base, max {len(OLD_REMOTE)} chars")
    p.add_argument("--tapm", help="full tapm URL for CC embed if ≤25 chars (else neutered)")
    args = p.parse_args()
    patch_ipa(Path(args.ipa_in), Path(args.ipa_out), args.base, args.tapm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
