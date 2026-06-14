#!/usr/bin/env python3
"""Patch anubis: disable SSL verify paths in __TEXT (libcurl uses mov wN,#1 for verify)."""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# arm64: mov wN, #1  -> mov wN, #0
PATCHES = [
    (b"\x01\x00\x80\x52", b"\x00\x00\x80\x52"),  # mov w0,#1 -> #0
    (b"\x21\x00\x80\x52", b"\x20\x00\x80\x52"),  # mov w1,#1 -> #0
]

ANUBIS_REL = "Payload/ShadowTrackerExtra.app/Frameworks/anubis.framework/anubis"
MAX_PATCHES = 600


def text_file_range(data: bytes) -> tuple[int, int]:
    """Return (start, end) file offsets for __TEXT segment."""
    magic = struct.unpack("<I", data[:4])[0]
    if magic != 0xFEEDFACF:
        return 0, len(data)
    ncmds = struct.unpack("<I", data[16:20])[0]
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack("<II", data[off : off + 8])
        if cmd == 0x19:  # LC_SEGMENT_64
            segname = data[off + 8 : off + 24].split(b"\0")[0]
            if segname == b"__TEXT":
                fileoff, filesize = struct.unpack("<QQ", data[off + 40 : off + 56])
                return int(fileoff), int(fileoff + filesize)
        off += cmdsize
    return 0, len(data)


def patch_binary(data: bytearray) -> int:
    start, end = text_file_range(data)
    count = 0
    for old, new in PATCHES:
        idx = start
        while idx < end and count < MAX_PATCHES:
            i = data.find(old, idx, end)
            if i < 0:
                break
            data[i : i + 4] = new
            count += 1
            idx = i + 4
    return count


def main() -> None:
    ipa_in = Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/Apple/Downloads/0asis.io_com.tencent.ig_4.4.0_15052026.ipa")
    ipa_out = Path(sys.argv[2] if len(sys.argv) > 2 else "/Users/Apple/Desktop/oasis_patched_ssl.ipa")

    work = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(ipa_in) as zf:
            zf.extractall(work)
        anubis = work / ANUBIS_REL
        if not anubis.exists():
            raise SystemExit(f"missing {anubis}")
        raw = anubis.read_bytes()
        data = bytearray(raw)
        text_start, text_end = text_file_range(raw)
        n = patch_binary(data)
        anubis.write_bytes(data)
        print(f"Patched {n} instruction(s) in anubis __TEXT [{text_start:#x}..{text_end:#x})")

        if ipa_out.exists():
            ipa_out.unlink()
        subprocess.run(["zip", "-qr", str(ipa_out), "Payload"], cwd=work, check=True)
        print(f"Wrote {ipa_out}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
