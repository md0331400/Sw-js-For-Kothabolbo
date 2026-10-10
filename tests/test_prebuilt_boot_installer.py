#!/usr/bin/env python3
"""Host tests for the experimental prebuilt-boot writer, using regular files."""
from __future__ import annotations

import hashlib
import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / "installer" / "prebuilt_boot_lib.sh"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PrebuiltBootInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="onclite-prebuilt-flash-test-")
        self.root = pathlib.Path(self.temp.name)
        self.stock = self.root / "stock.img"
        self.candidate = self.root / "candidate.img"
        self.block = self.root / "boot-block"
        self.backup_dir = self.root / "persistent"
        self.backup_dir.mkdir()
        self.stock_bytes = bytes((i % 251 for i in range(256 * 1024)))
        self.candidate_bytes = bytes((255 - (i % 251) for i in range(256 * 1024)))
        self.stock.write_bytes(self.stock_bytes)
        self.candidate.write_bytes(self.candidate_bytes)
        self.block.write_bytes(self.stock_bytes)
        self.stock_hash = digest(self.stock_bytes)
        self.candidate_hash = digest(self.candidate_bytes)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_helper(self, *, stock_hash: str | None = None, candidate_hash: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        args = [
            str(self.candidate),
            str(self.block),
            str(self.backup_dir),
            str(len(self.candidate_bytes)),
            stock_hash or self.stock_hash,
            candidate_hash or self.candidate_hash,
        ]
        quoted = " ".join(shlex.quote(arg) for arg in args)
        command = f". {shlex.quote(str(LIB))}; onclite_flash_prebuilt {quoted}"
        shell = os.environ.get("ONCLITE_TEST_SHELL", "bash")
        return subprocess.run(
            [shell, "-c", command],
            text=True,
            capture_output=True,
            env={**os.environ, **(env or {})},
            check=False,
        )

    def test_success_backs_up_then_writes_and_verifies(self) -> None:
        result = self.run_helper()
        backup = self.backup_dir / "onclite-kernel-experimental-original-boot.img"
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.block.read_bytes(), self.candidate_bytes)
        self.assertEqual(backup.read_bytes(), self.stock_bytes)
        self.assertIn("read-back matches", result.stderr)

    def test_unrecognized_current_boot_aborts_before_backup_or_write(self) -> None:
        unknown = b"x" * len(self.stock_bytes)
        self.block.write_bytes(unknown)
        result = self.run_helper()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.block.read_bytes(), unknown)
        self.assertFalse((self.backup_dir / "onclite-kernel-experimental-original-boot.img").exists())

    def test_wrong_candidate_hash_aborts_without_write(self) -> None:
        result = self.run_helper(candidate_hash="0" * 64)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.block.read_bytes(), self.stock_bytes)
        self.assertFalse((self.backup_dir / "onclite-kernel-experimental-original-boot.img").exists())

    def test_mismatched_existing_backup_is_never_overwritten(self) -> None:
        backup = self.backup_dir / "onclite-kernel-experimental-original-boot.img"
        existing = b"keep existing backup"
        backup.write_bytes(existing)
        result = self.run_helper()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.block.read_bytes(), self.stock_bytes)
        self.assertEqual(backup.read_bytes(), existing)

    def test_missing_persistent_backup_directory_aborts_before_write(self) -> None:
        self.backup_dir.rmdir()
        result = self.run_helper()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.block.read_bytes(), self.stock_bytes)

    def test_partial_write_failure_triggers_verified_restore(self) -> None:
        real_dd = shutil.which("dd")
        self.assertIsNotNone(real_dd)
        shim_dir = self.root / "shim-bin"
        shim_dir.mkdir()
        marker = self.root / "fail-once"
        shim = shim_dir / "dd"
        shim.write_text(
            "#!/bin/sh\n"
            "input= output=\n"
            "for arg do\n"
            "  case $arg in if=*) input=${arg#if=};; of=*) output=${arg#of=};; esac\n"
            "done\n"
            "if [ \"$input\" = \"$FAIL_INPUT\" ] && [ \"$output\" = \"$FAIL_BLOCK\" ] && [ ! -e \"$FAIL_MARKER\" ]; then\n"
            "  : > \"$FAIL_MARKER\"\n"
            f"  \"{real_dd}\" if=\"$input\" of=\"$output\" bs=1024 count=1 2>/dev/null\n"
            "  exit 1\n"
            "fi\n"
            f"exec \"{real_dd}\" \"$@\"\n"
        )
        shim.chmod(0o755)
        env = {
            "PATH": f"{shim_dir}:{os.environ.get('PATH', '')}",
            "FAIL_INPUT": str(self.candidate),
            "FAIL_BLOCK": str(self.block),
            "FAIL_MARKER": str(marker),
        }
        result = self.run_helper(env=env)
        backup = self.backup_dir / "onclite-kernel-experimental-original-boot.img"
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.block.read_bytes(), self.stock_bytes)
        self.assertEqual(backup.read_bytes(), self.stock_bytes)
        self.assertIn("original boot restored", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
