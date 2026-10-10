#!/usr/bin/env python3
"""Exercise the real experimental writer against temporary regular files.

This validates byte-copy, backup, and read-back behavior only. It does not
open a block device, run in Android recovery, or test device acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
STOCK_SHA256 = "cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30"
CANDIDATE_SHA256 = "684d5f2f29ee0dfeb9519a007be99594a8ba9af7c57c1734dec3b0fc06a0495c"
PARTITION_SIZE = 67_108_864
LIB = ROOT / "installer" / "prebuilt_boot_lib.sh"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=pathlib.Path, default=ROOT / "google_drive" / "boot.img")
    parser.add_argument("--candidate", type=pathlib.Path, default=ROOT / "build-artifacts" / "onclite-experimental-boot.img")
    args = parser.parse_args()

    stock = args.stock.resolve()
    candidate = args.candidate.resolve()
    for label, path, expected in (
        ("stock", stock, STOCK_SHA256),
        ("candidate", candidate, CANDIDATE_SHA256),
    ):
        if not path.is_file():
            parser.error(f"{label} input does not exist: {path}")
        if path.stat().st_size != PARTITION_SIZE:
            parser.error(f"{label} input must be exactly {PARTITION_SIZE} bytes")
        actual = sha256_file(path)
        if actual != expected:
            parser.error(f"{label} SHA-256 mismatch: {actual}")

    with tempfile.TemporaryDirectory(prefix="onclite-prebuilt-integration-") as temp:
        work = pathlib.Path(temp)
        block_file = work / "boot-partition-file-backed"
        backup_dir = work / "persistent-backup"
        backup_dir.mkdir()
        shutil.copyfile(stock, block_file)
        command = ". {} && onclite_flash_prebuilt {} {} {} {} {} {}".format(
            shlex.quote(str(LIB)),
            shlex.quote(str(candidate)),
            shlex.quote(str(block_file)),
            shlex.quote(str(backup_dir)),
            PARTITION_SIZE,
            STOCK_SHA256,
            CANDIDATE_SHA256,
        )
        shell = os.environ.get("ONCLITE_TEST_SHELL", "bash")
        result = subprocess.run([shell, "-c", command], text=True, capture_output=True, check=False)
        backup = backup_dir / "onclite-kernel-experimental-original-boot.img"
        if result.returncode != 0:
            raise SystemExit(f"file-backed install path failed ({result.returncode}):\n{result.stderr}")
        values = {
            "shell": shell,
            "result": "FILE_BACKED_HOST_TEST_PASS_NOT_RECOVERY_OR_DEVICE_TEST",
            "partition_fixture_size": block_file.stat().st_size,
            "candidate_expected_sha256": CANDIDATE_SHA256,
            "partition_readback_sha256": sha256_file(block_file),
            "backup_sha256": sha256_file(backup),
            "recovery_or_device_tested": False,
            "installer_output": result.stderr.strip().splitlines(),
        }
        if values["partition_readback_sha256"] != CANDIDATE_SHA256:
            raise SystemExit("file-backed target read-back did not match the candidate")
        if values["backup_sha256"] != STOCK_SHA256:
            raise SystemExit("file-backed original backup did not match the stock input")
        print(json.dumps(values, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
