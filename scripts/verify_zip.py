#!/usr/bin/env python3
"""Static integrity and target-safety checks for the onclite AnyKernel3 ZIP."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile
import zipfile
import zlib

REQUIRED = {
    "META-INF/com/google/android/update-binary",
    "META-INF/com/google/android/updater-script",
    "anykernel.sh",
    "banner",
    "tools/ak3-core.sh",
    "tools/busybox",
    "tools/magiskboot",
    "payload/Image.gz",
    "LICENSES/AnyKernel3-LICENSE.txt",
    "ZIP_CONTENTS.txt",
}
FORBIDDEN_PARTITIONS = {
    "boot.img",
    "recovery.img",
    "vendor_boot.img",
    "dtbo.img",
    "vbmeta.img",
}


def fail(message: str) -> None:
    raise SystemExit(f"VERIFY FAILED: {message}")


def canonical(name: str) -> str:
    while name.startswith("./"):
        name = name[2:]
    return name


def check_gzip_kernel(data: bytes, label: str) -> None:
    if not data.startswith(b"\x1f\x8b"):
        fail(f"{label} does not begin with gzip magic")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        decoded = decoder.decompress(data)
        decoded += decoder.flush()
    except zlib.error as exc:
        fail(f"{label} has a corrupt gzip stream: {exc}")
    if not decoder.eof:
        fail(f"{label} gzip stream did not terminate cleanly")
    if decoder.unused_data:
        fail(f"{label} has unexpected bytes after the gzip stream; the live DTB must remain separate")
    if len(decoded) < 1024 * 1024:
        fail(f"{label} decompresses to an implausibly small kernel image")
    if len(decoded) < 64 or decoded[56:60] != b"ARM\x64":
        fail(f"{label} does not decompress to an arm64 Linux Image")


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: verify_zip.py <flashable.zip>")
    archive = pathlib.Path(sys.argv[1]).resolve()
    if not archive.is_file():
        fail(f"ZIP does not exist: {archive}")

    with zipfile.ZipFile(archive) as zf:
        bad_entry = zf.testzip()
        if bad_entry:
            fail(f"ZIP CRC failure in {bad_entry}")
        names: dict[str, zipfile.ZipInfo] = {}
        for info in zf.infolist():
            name = canonical(info.filename)
            parts = pathlib.PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts:
                fail(f"unsafe archive path: {info.filename}")
            if name in names:
                fail(f"duplicate archive path: {name}")
            names[name] = info
        missing = sorted(REQUIRED - names.keys())
        if missing:
            fail("missing required archive entries: " + ", ".join(missing))
        unexpected_boots = sorted(name for name in names if pathlib.PurePosixPath(name).name in FORBIDDEN_PARTITIONS)
        if unexpected_boots:
            fail("archive must not carry partition images: " + ", ".join(unexpected_boots))
        payload_entries = sorted(name for name in names if name.startswith("payload/"))
        if payload_entries != ["payload/Image.gz"]:
            fail("archive must carry exactly the kernel-only payload/Image.gz; DTBs come from the live boot image")

        updater = zf.read("META-INF/com/google/android/update-binary")
        if not updater.startswith(b"#!/sbin/sh"):
            fail("update-binary has an unexpected interpreter header")
        updater_script = zf.read("META-INF/com/google/android/updater-script").decode("utf-8", "replace")
        if "#FLASHAFTERUPDATEV2" not in updater_script:
            fail("AnyKernel3 recovery updater marker is missing")

        magiskboot = zf.read("tools/magiskboot")
        for marker in (
            b"kernel_dtb",
            b"recovery_dtbo",
            b"Split image.*-dtb into kernel + kernel_dtb.",
            b"Repack boot image components",
        ):
            if marker not in magiskboot:
                fail(f"bundled MagiskBoot lacks expected DTB-preservation support: {marker!r}")

        installer = zf.read("anykernel.sh").decode("utf-8", "replace")
        required_tokens = (
            "do.devicecheck=1",
            "device.name1=onclite",
            "BLOCK=boot",
            "IS_SLOT_DEVICE=0",
            "PATCH_VBMETA_FLAG=0",
            ". tools/ak3-core.sh",
            "split_boot;",
            "flash_boot;",
            "header_ver",
            "payload/Image.gz",
            '"$SPLITIMG/kernel_dtb"',
            '"$SPLITIMG/dtb"',
        )
        for token in required_tokens:
            if token not in installer:
                fail(f"installer is missing required onclite guard/flow: {token}")
        if re.search(r"(?m)^\s*(?:write_boot|flash_generic|format|wipe_data)\s*(?:;|$)", installer):
            fail("installer contains a forbidden extra partition/wipe operation")
        if "device.name2=" in installer or "device.name3=" in installer:
            fail("installer must allow only the onclite codename")

        gz = zf.read("payload/Image.gz")
        check_gzip_kernel(gz, "payload/Image.gz")

        # Run host-side parser checks on the shipped installer and AnyKernel core.
        with tempfile.TemporaryDirectory(prefix="onclite-zip-check-") as tmp:
            tmp_path = pathlib.Path(tmp)
            files = {
                "update-binary": updater,
                "anykernel.sh": installer.encode(),
                "ak3-core.sh": zf.read("tools/ak3-core.sh"),
            }
            for filename, content in files.items():
                path = tmp_path / filename
                path.write_bytes(content)
                result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
                if result.returncode:
                    fail(f"shell syntax error in {filename}: {result.stderr.strip()}")

        print(f"ZIP OK: {archive.name}")
        print(f"Entries: {len(names)}; CRC: clean; device guard: onclite only")
        print("Installer: boot-only AnyKernel3 repack; no wipe/format or extra partition image")
        print("Kernel payload: gzip stream valid; installer requires and preserves the live DTB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
