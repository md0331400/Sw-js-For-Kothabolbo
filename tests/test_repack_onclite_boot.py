#!/usr/bin/env python3
"""Synthetic host tests for the fail-closed onclite boot-image repacker.

These fixtures exercise format and preservation logic only. They are not the
Redmi 7 firmware and do not test a bootloader, recovery, flashing, or AVB policy.
"""
from __future__ import annotations

import gzip
import hashlib
import pathlib
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repack_onclite_boot as repacker  # noqa: E402
from inspect_boot import inspect_dtbs  # noqa: E402


def be32(value: int) -> bytes:
    return struct.pack(">I", value)


def pad4(data: bytes) -> bytes:
    return data + (b"\0" * ((-len(data)) % 4))


def fake_fdt(index: int) -> bytes:
    """Create a tiny valid FDT whose root compatible includes a unique suffix."""
    strings = b"compatible\0"
    value = f"qcom,onclite-test-{index}\0".encode()
    structure = (
        be32(1) + pad4(b"\0")  # FDT_BEGIN_NODE, empty root name
        + be32(3) + be32(len(value)) + be32(0) + pad4(value)  # FDT_PROP
        + be32(2)  # FDT_END_NODE
        + be32(9)  # FDT_END
    )
    structure_offset = 56
    strings_offset = structure_offset + len(structure)
    total_size = strings_offset + len(strings)
    header = struct.pack(
        ">10I",
        0xD00DFEED,
        total_size,
        structure_offset,
        strings_offset,
        40,  # reserve map starts immediately after the header
        17,
        16,
        0,
        len(strings),
        len(structure),
    )
    return header + (b"\0" * 16) + structure + strings


def fake_arm64_image(fill: int) -> bytes:
    image = bytearray([fill]) * (1024 * 1024)
    image[56:60] = b"ARM\x64"
    return bytes(image)


def make_fixture(*, fdt_count: int = 17) -> tuple[bytes, bytes, bytes, int]:
    stock_image = fake_arm64_image(0)
    stock_gzip = gzip.compress(stock_image, mtime=0)
    tail = b"".join(fake_fdt(index) for index in range(fdt_count))
    stock_component = stock_gzip + tail
    page_size = 2_048
    body_size = repacker.align(page_size + len(stock_component), page_size)

    header = bytearray(page_size)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, len(stock_component))
    struct.pack_into("<I", header, 12, 0x80008000)
    struct.pack_into("<I", header, 16, 0)  # no ramdisk
    struct.pack_into("<I", header, 24, 0)  # no second component
    struct.pack_into("<I", header, 36, page_size)
    struct.pack_into("<I", header, 40, 1)  # header v1
    struct.pack_into("<I", header, 1_632, 0)  # recovery_dtbo_size
    struct.pack_into("<Q", header, 1_636, 0)  # recovery_dtbo_offset
    struct.pack_into("<I", header, 1_644, 1_648)  # v1 header size
    header[576:608] = repacker.legacy_boot_id(stock_component)

    vbmeta_offset = body_size + page_size
    vbmeta_size = 704
    partition_size = repacker.align(vbmeta_offset + vbmeta_size + 64, page_size)
    image = bytearray(partition_size)
    image[:page_size] = header
    image[page_size : page_size + len(stock_component)] = stock_component
    image[vbmeta_offset : vbmeta_offset + 4] = b"AVB0"
    footer_offset = partition_size - 64
    struct.pack_into(
        ">4sIIQQQ",
        image,
        footer_offset,
        b"AVBf",
        1,
        0,
        body_size,
        vbmeta_offset,
        vbmeta_size,
    )

    replacement = gzip.compress(fake_arm64_image(1), mtime=0)
    return bytes(image), replacement, tail, body_size


class RepackOncliteBootTests(unittest.TestCase):
    def test_synthetic_v1_repack_preserves_header_fdt_and_avb_suffix(self) -> None:
        stock, replacement, original_tail, body_size = make_fixture()
        old_component_size = struct.unpack_from("<I", stock, 8)[0]
        old_kernel_end = 2_048 + old_component_size
        old_layout_tail = stock[2_048 + old_component_size - len(original_tail) : old_kernel_end]
        self.assertEqual(old_layout_tail, original_tail)
        self.assertEqual(len(inspect_dtbs(original_tail)), 17)

        candidate, report = repacker.repack_image(
            stock,
            replacement,
            expected_fdts=17,
            require_onclite_fingerprint=False,
        )
        new_size = struct.unpack_from("<I", candidate, 8)[0]
        new_component = candidate[2_048 : 2_048 + new_size]
        decoded, new_tail = repacker.decode_gzip(
            new_component, "test candidate", allow_appended_data=True
        )

        self.assertEqual(len(candidate), len(stock))
        self.assertEqual(candidate[:8], stock[:8])
        self.assertEqual(candidate[12:576], stock[12:576])
        self.assertEqual(candidate[608:2_048], stock[608:2_048])
        self.assertEqual(candidate[2_048 + new_size - len(original_tail) : 2_048 + new_size], original_tail)
        self.assertEqual(new_tail, original_tail)
        self.assertEqual(decoded, fake_arm64_image(1))
        self.assertEqual(len(inspect_dtbs(new_tail)), 17)
        self.assertEqual(candidate[body_size:], stock[body_size:])
        self.assertEqual(candidate[576:608], repacker.legacy_boot_id(new_component))
        self.assertTrue(report["header_preserved_except_kernel_size_and_legacy_id"])
        self.assertTrue(report["appended_fdt_tail_byte_identical"])
        self.assertTrue(report["suffix_from_original_image_size_byte_identical"])
        self.assertFalse(report["written_to_device"])
        self.assertIn("never written", report["avb"]["separate_external_vbmeta"])
        self.assertIn("not checked", report["avb"]["original_external_descriptor_matches"])

    def test_default_mode_rejects_unfingerprinted_synthetic_stock(self) -> None:
        stock, replacement, _, _ = make_fixture()
        with self.assertRaisesRegex(repacker.RepackError, "stock boot SHA-256"):
            repacker.repack_image(stock, replacement)

    def test_strict_kernel_gate_rejects_untracked_payload(self) -> None:
        with self.assertRaisesRegex(repacker.RepackError, "neither the prior documented artifact"):
            repacker._validate_diagnostic_kernel(b"not the pinned diagnostic kernel")

    def test_rejects_nonzero_ramdisk(self) -> None:
        stock, replacement, _, _ = make_fixture()
        mutated = bytearray(stock)
        struct.pack_into("<I", mutated, 16, 1)
        with self.assertRaisesRegex(repacker.RepackError, "zero ramdisk"):
            repacker.repack_image(
                bytes(mutated), replacement, require_onclite_fingerprint=False
            )

    def test_rejects_unexpected_fdt_count(self) -> None:
        stock, replacement, _, _ = make_fixture(fdt_count=16)
        with self.assertRaisesRegex(repacker.RepackError, "FDT count is 16, expected 17"):
            repacker.repack_image(
                stock, replacement, expected_fdts=17, require_onclite_fingerprint=False
            )

    def test_rejects_nonzero_original_page_padding(self) -> None:
        stock, replacement, _, _ = make_fixture()
        kernel_size = struct.unpack_from("<I", stock, 8)[0]
        kernel_end = 2_048 + kernel_size
        body_end = repacker.align(kernel_end, 2_048)
        self.assertGreater(body_end, kernel_end)
        mutated = bytearray(stock)
        mutated[kernel_end] = 0x7F
        with self.assertRaisesRegex(repacker.RepackError, "non-zero data.*padding"):
            repacker.repack_image(
                bytes(mutated), replacement, require_onclite_fingerprint=False
            )

    def test_rejects_payload_trailing_data(self) -> None:
        stock, replacement, _, _ = make_fixture()
        with self.assertRaisesRegex(repacker.RepackError, "unexpected bytes after gzip"):
            repacker.repack_image(
                stock, replacement + b"junk", require_onclite_fingerprint=False
            )

    def test_rejects_recovery_dtbo_layout(self) -> None:
        stock, replacement, _, _ = make_fixture()
        mutated = bytearray(stock)
        struct.pack_into("<I", mutated, 1_632, 1)
        with self.assertRaisesRegex(repacker.RepackError, "recovery_dtbo"):
            repacker.repack_image(
                bytes(mutated), replacement, require_onclite_fingerprint=False
            )

    def test_avb_digest_uses_salt_then_original_image_bytes(self) -> None:
        salt = b"fixture salt"
        body = b"fixture boot body"
        expected = hashlib.sha256(salt + body).hexdigest()
        self.assertEqual(repacker.avb_sha256(salt, body), expected)

    def test_writer_never_overwrites_an_existing_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="onclite-write-check-") as temp:
            existing = pathlib.Path(temp) / "candidate.img"
            existing.write_bytes(b"preserve me")
            with self.assertRaisesRegex(repacker.RepackError, "refusing to overwrite"):
                repacker.write_new_file(existing, b"do not replace")
            self.assertEqual(existing.read_bytes(), b"preserve me")


if __name__ == "__main__":
    unittest.main(verbosity=2)
