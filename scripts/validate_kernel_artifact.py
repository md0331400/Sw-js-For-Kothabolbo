#!/usr/bin/env python3
"""Statically validate a kernel-only gzip Image against a stock boot's FDT tail.

This reads both inputs and constructs a candidate kernel component only in
memory. It does not write/repack a boot image, ZIP, or device partition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import zlib

sys.dont_write_bytecode = True
from inspect_boot import inspect_dtbs  # noqa: E402

ANDROID_MAGIC = b"ANDROID!"
GZIP_MAGIC = b"\x1f\x8b"
ARM64_IMAGE_MAGIC = b"ARM\x64"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_stock_boot(path: pathlib.Path) -> tuple[bytes, bytes, dict[str, int]]:
    data = path.read_bytes()
    if len(data) < 2048 or data[:8] != ANDROID_MAGIC:
        raise ValueError(f"{path}: not a supported Android boot image")
    page_size = int.from_bytes(data[36:40], "little")
    version = int.from_bytes(data[40:44], "little")
    kernel_size = int.from_bytes(data[8:12], "little")
    ramdisk_size = int.from_bytes(data[16:20], "little")
    if version not in (0, 1, 2):
        raise ValueError(f"{path}: unsupported boot header version {version}")
    if page_size < 512 or page_size & (page_size - 1):
        raise ValueError(f"{path}: invalid page size {page_size}")
    if page_size + kernel_size > len(data):
        raise ValueError(f"{path}: kernel component extends past the image")
    kernel_component = data[page_size : page_size + kernel_size]
    if not kernel_component.startswith(GZIP_MAGIC):
        raise ValueError(f"{path}: stock kernel component is not gzip")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        stock_image = decoder.decompress(kernel_component) + decoder.flush()
    except zlib.error as exc:
        raise ValueError(f"{path}: invalid stock kernel gzip stream: {exc}") from exc
    if not decoder.eof:
        raise ValueError(f"{path}: stock kernel gzip stream is incomplete")
    fdt_tail = decoder.unused_data
    if not fdt_tail:
        raise ValueError(f"{path}: no appended data follows the stock gzip kernel")
    details = {
        "boot_header_version": version,
        "page_size": page_size,
        "ramdisk_size": ramdisk_size,
        "kernel_component_size": kernel_size,
        "stock_image_size": len(stock_image),
        "stock_gzip_member_size": kernel_size - len(fdt_tail),
    }
    return data, fdt_tail, details


def decode_kernel(path: pathlib.Path) -> tuple[bytes, bytes]:
    compressed = path.read_bytes()
    if not compressed.startswith(GZIP_MAGIC):
        raise ValueError(f"{path}: missing gzip magic")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        image = decoder.decompress(compressed) + decoder.flush()
    except zlib.error as exc:
        raise ValueError(f"{path}: invalid gzip stream: {exc}") from exc
    if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise ValueError(f"{path}: incomplete gzip stream or unexpected trailing data")
    return compressed, image


def validate(stock_path: pathlib.Path, kernel_path: pathlib.Path, expected_fdts: int) -> dict[str, object]:
    stock_data, stock_tail, boot = parse_stock_boot(stock_path)
    compressed, image = decode_kernel(kernel_path)
    if image[56:60] != ARM64_IMAGE_MAGIC:
        raise ValueError(f"{kernel_path}: decompressed image lacks arm64 Image magic at offset 56")
    if len(image) < 1024 * 1024:
        raise ValueError(f"{kernel_path}: decompressed kernel is implausibly small")
    stock_fdt = inspect_dtbs(stock_tail)
    if len(stock_fdt) != expected_fdts:
        raise ValueError(f"stock FDT count {len(stock_fdt)} does not equal expected {expected_fdts}")

    # Model only the kernel component that a future repacker might assemble:
    # the new gzip stream followed by the exact FDT bytes extracted from stock.
    synthetic_component = compressed + stock_tail
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        synthetic_image = decoder.decompress(synthetic_component) + decoder.flush()
    except zlib.error as exc:
        raise ValueError(f"synthetic component gzip prefix is invalid: {exc}") from exc
    if not decoder.eof or decoder.unused_data != stock_tail:
        raise ValueError("synthetic component did not preserve the original appended tail")
    if synthetic_image != image:
        raise ValueError("synthetic component's decompressed image differs from the kernel-only input")
    rebuilt_fdt = inspect_dtbs(decoder.unused_data)
    if len(rebuilt_fdt) != expected_fdts:
        raise ValueError(f"synthetic component FDT count {len(rebuilt_fdt)} does not equal expected {expected_fdts}")

    return {
        "stock_boot": {
            "path": str(stock_path),
            "sha256": sha256(stock_data),
            **boot,
        },
        "kernel_only_input": {
            "path": str(kernel_path),
            "compressed_size": len(compressed),
            "compressed_sha256": sha256(compressed),
            "decompressed_size": len(image),
            "decompressed_sha256": sha256(image),
            "gzip_eof": True,
            "gzip_trailing_bytes": 0,
            "arm64_image_magic_at_56": image[56:60].decode("ascii"),
        },
        "stock_appended_fdt_tail": {
            "size": len(stock_tail),
            "sha256": sha256(stock_tail),
            "valid_fdt_count": len(stock_fdt),
            "fdt_headers": stock_fdt,
        },
        "in_memory_synthetic_kernel_component_only": {
            "size": len(synthetic_component),
            "sha256": sha256(synthetic_component),
            "size_delta_vs_stock_component": len(synthetic_component) - boot["kernel_component_size"],
            "tail_byte_identical": decoder.unused_data == stock_tail,
            "valid_fdt_count": len(rebuilt_fdt),
            "written_to_disk": False,
            "boot_image_repacked": False,
            "device_or_bootloader_tested": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_boot", type=pathlib.Path)
    parser.add_argument("kernel_image_gz", type=pathlib.Path)
    parser.add_argument("--expected-fdts", type=int, default=17)
    args = parser.parse_args()
    if args.expected_fdts < 1:
        parser.error("--expected-fdts must be positive")
    try:
        result = validate(args.stock_boot, args.kernel_image_gz, args.expected_fdts)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("STATIC LAYOUT CHECK ONLY: no boot image or device partition was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
