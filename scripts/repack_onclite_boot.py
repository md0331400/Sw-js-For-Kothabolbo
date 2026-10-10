#!/usr/bin/env python3
"""Build a static, full-size onclite header-v1 boot-image candidate.

This host-side tool is deliberately not an installer. It accepts only the
previously audited stock boot image (pinned by SHA-256), replaces its gzip
kernel while retaining the exact contiguous 17-FDT tail, recomputes the legacy
boot ID, and copies every byte from the original AVB body boundary onward.
The existing AnyKernel zero-ramdisk guard is not changed by this tool.

The resulting body no longer matches the original boot hash descriptors. The
CLI therefore requires an explicit lab-only acknowledgement before writing an
output image. It never changes vbmeta, signs AVB data, flashes, or asserts that
an unlocked Redmi 7 will accept the image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
import sys
import tempfile
import zlib

sys.dont_write_bytecode = True
from inspect_boot import inspect_dtbs  # noqa: E402

ANDROID_MAGIC = b"ANDROID!"
GZIP_MAGIC = b"\x1f\x8b"
ARM64_IMAGE_MAGIC = b"ARM\x64"
AVB_FOOTER_MAGIC = b"AVBf"
AVB_VBMETA_MAGIC = b"AVB0"

# Identity and layout recorded by the previous, completed onclite artifact audit.
ONCLITE_BOOT_SHA256 = "cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30"
ONCLITE_DIAGNOSTIC_IMAGE_GZ_SHA256 = "e177c6841bc8150d9488b2fc80127c91b169a15f19be47d9467747d3a8af54d5"
ONCLITE_REBUILT_IMAGE_GZ_SHA256 = "255b8cf621055cc1ff48d256204f8690a6c9892047a40d0cb9cb2c838c23eb96"
KNOWN_DIAGNOSTIC_KERNELS = {
    ONCLITE_DIAGNOSTIC_IMAGE_GZ_SHA256: "previously recorded diagnostic build",
    ONCLITE_REBUILT_IMAGE_GZ_SHA256: "2026-10-10 rebuild; same pinned source/toolchain/config",
}
ONCLITE_PARTITION_SIZE = 67_108_864
ONCLITE_HEADER_VERSION = 1
ONCLITE_PAGE_SIZE = 2_048
ONCLITE_HEADER_SIZE = 1_648
ONCLITE_KERNEL_SIZE = 15_214_803
ONCLITE_BODY_SIZE = 15_218_688
ONCLITE_VBMETA_OFFSET = 15_220_736
ONCLITE_VBMETA_SIZE = 704
ONCLITE_FOOTER_OFFSET = 67_108_800
ONCLITE_FDT_COUNT = 17
ONCLITE_FDT_TAIL_SIZE = 4_142_961
ONCLITE_FDT_TAIL_SHA256 = "4a5fd265b67b34a535b3bda15bb88568948d80154da15eab1dfaf7cc70268ca5"

# Digest and salt from the separately supplied, previously audited signed
# vbmeta descriptor for the original boot body. This verifies the audited
# descriptor-to-original relationship offline; it does not prove device trust.
AUDITED_EXTERNAL_BOOT_SALT = bytes.fromhex(
    "00a22bda86e291059a837ebd3baa4193872cf215922b24f9a9a483073f12fc5c"
)
AUDITED_EXTERNAL_BOOT_DIGEST = "3193f936e928c7780bfecbd4d8f573619c04bea20e997c5c9461c291122be250"


class RepackError(ValueError):
    """Input or output failed a fail-closed layout check."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int, page_size: int) -> int:
    return (value + page_size - 1) // page_size * page_size


def avb_sha256(salt: bytes, image: bytes) -> str:
    """AVB hash-descriptor digest: SHA-256 over salt followed by image bytes."""
    return hashlib.sha256(salt + image).hexdigest()


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def decode_gzip(data: bytes, label: str, *, allow_appended_data: bool) -> tuple[bytes, bytes]:
    if not data.startswith(GZIP_MAGIC):
        raise RepackError(f"{label}: missing gzip magic")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        image = decoder.decompress(data) + decoder.flush()
    except zlib.error as exc:
        raise RepackError(f"{label}: invalid gzip stream: {exc}") from exc
    if not decoder.eof or decoder.unconsumed_tail:
        raise RepackError(f"{label}: incomplete gzip stream")
    tail = decoder.unused_data
    if tail and not allow_appended_data:
        raise RepackError(f"{label}: unexpected bytes after gzip stream")
    if len(image) < 1024 * 1024 or image[56:60] != ARM64_IMAGE_MAGIC:
        raise RepackError(f"{label}: not a plausible arm64 Linux Image")
    return image, tail


def validate_fdt_sequence(tail: bytes, expected_count: int) -> list[dict[str, object]]:
    if expected_count < 1:
        raise RepackError("expected FDT count must be positive")
    blobs = inspect_dtbs(tail)
    if len(blobs) != expected_count:
        raise RepackError(f"appended FDT count is {len(blobs)}, expected {expected_count}")
    cursor = 0
    for index, blob in enumerate(blobs):
        offset = int(blob["offset"])
        size = int(blob["size"])
        if offset != cursor:
            raise RepackError(f"appended FDT {index} is not contiguous at byte {cursor}")
        cursor += size
    if cursor != len(tail):
        raise RepackError(f"appended FDTs cover {cursor} of {len(tail)} tail bytes")
    return blobs


def legacy_boot_id(
    kernel: bytes,
    ramdisk: bytes = b"",
    second: bytes = b"",
    recovery_dtbo: bytes = b"",
    dtb: bytes = b"",
) -> bytes:
    """Return the legacy mkbootimg SHA-1 ID followed by its 12 reserved zeros."""
    digest = hashlib.sha1()
    for component in (kernel, ramdisk, second, recovery_dtbo, dtb):
        digest.update(component)
        digest.update(struct.pack("<I", len(component)))
    return digest.digest() + (b"\0" * 12)


def _parse_layout(data: bytes, expected_fdts: int) -> dict[str, object]:
    if len(data) < 2_048 or data[:8] != ANDROID_MAGIC:
        raise RepackError("not a supported Android boot image")
    header_version = u32(data, 40)
    page_size = u32(data, 36)
    kernel_size = u32(data, 8)
    ramdisk_size = u32(data, 16)
    second_size = u32(data, 24)
    if header_version != 1:
        raise RepackError(f"expected Android boot header v1, got v{header_version}")
    if page_size < 512 or page_size & (page_size - 1):
        raise RepackError(f"invalid boot page size {page_size}")
    if len(data) < page_size or u32(data, 1_644) != 1_648:
        raise RepackError("invalid or truncated Android boot header v1")
    if ramdisk_size != 0:
        raise RepackError(f"expected zero ramdisk; image reports {ramdisk_size} bytes")
    if second_size != 0:
        raise RepackError(f"unsupported non-empty second component: {second_size} bytes")
    if u32(data, 1_632) != 0 or u64(data, 1_636) != 0:
        raise RepackError("unsupported recovery_dtbo component; refusing to move its metadata")

    kernel_offset = page_size
    kernel_end = kernel_offset + kernel_size
    if kernel_size == 0 or kernel_end > len(data):
        raise RepackError("kernel component has invalid bounds")
    component_aligned_end = align(kernel_end, page_size)
    if component_aligned_end > len(data):
        raise RepackError("aligned kernel component extends past the image")

    kernel_image, fdt_tail = decode_gzip(
        data[kernel_offset:kernel_end], "stock kernel component", allow_appended_data=True
    )
    fdts = validate_fdt_sequence(fdt_tail, expected_fdts)

    footer_offset = len(data) - 64
    if footer_offset < 0 or data[footer_offset : footer_offset + 4] != AVB_FOOTER_MAGIC:
        raise RepackError("AVB footer is missing from the end of the boot partition image")
    magic, footer_major, footer_minor, original_size, vbmeta_offset, vbmeta_size = struct.unpack_from(
        ">4sIIQQQ", data, footer_offset
    )
    if magic != AVB_FOOTER_MAGIC or footer_major != 1 or footer_minor != 0:
        raise RepackError("unsupported AVB footer version")
    if original_size < component_aligned_end or original_size > footer_offset:
        raise RepackError(
            f"AVB original_image_size {original_size} cannot contain the aligned kernel component ending at {component_aligned_end}"
        )
    body_end = original_size
    if any(data[kernel_end:body_end]):
        raise RepackError("non-zero data in the original kernel/body page padding")
    if vbmeta_offset < original_size or vbmeta_size < 4 or vbmeta_offset + vbmeta_size > footer_offset:
        raise RepackError("AVB vbmeta range is invalid or overlaps the footer")
    if data[vbmeta_offset : vbmeta_offset + 4] != AVB_VBMETA_MAGIC:
        raise RepackError("AVB footer does not point to an AVB0 structure")

    return {
        "image_size": len(data),
        "header_version": header_version,
        "header_size": u32(data, 1_644),
        "page_size": page_size,
        "kernel_offset": kernel_offset,
        "kernel_size": kernel_size,
        "kernel_end": kernel_end,
        "kernel_image_size": len(kernel_image),
        "ramdisk_size": ramdisk_size,
        "second_size": second_size,
        "body_end": body_end,
        "fdt_tail": fdt_tail,
        "fdt_tail_sha256": sha256(fdt_tail),
        "fdt_count": len(fdts),
        "fdt_blobs": fdts,
        "footer_offset": footer_offset,
        "footer_version": f"{footer_major}.{footer_minor}",
        "original_image_size": original_size,
        "vbmeta_offset": vbmeta_offset,
        "vbmeta_size": vbmeta_size,
    }


def _validate_diagnostic_kernel(kernel_gz: bytes) -> tuple[str, str]:
    kernel_hash = sha256(kernel_gz)
    label = KNOWN_DIAGNOSTIC_KERNELS.get(kernel_hash)
    if label is None:
        raise RepackError(
            "replacement kernel SHA-256 is neither the prior documented artifact nor the "
            f"verified pinned rebuild ({kernel_hash}); refusing an untracked payload"
        )
    return kernel_hash, label


def _validate_onclite_stock(data: bytes, layout: dict[str, object]) -> dict[str, object]:
    image_hash = sha256(data)
    if image_hash != ONCLITE_BOOT_SHA256:
        raise RepackError(
            "stock boot SHA-256 does not match the previously audited onclite image "
            f"({image_hash}); refusing non-pinned firmware"
        )
    expected = {
        "image_size": ONCLITE_PARTITION_SIZE,
        "header_version": ONCLITE_HEADER_VERSION,
        "header_size": ONCLITE_HEADER_SIZE,
        "page_size": ONCLITE_PAGE_SIZE,
        "kernel_size": ONCLITE_KERNEL_SIZE,
        "ramdisk_size": 0,
        "second_size": 0,
        "body_end": ONCLITE_BODY_SIZE,
        "fdt_tail_sha256": ONCLITE_FDT_TAIL_SHA256,
        "fdt_count": ONCLITE_FDT_COUNT,
        "footer_offset": ONCLITE_FOOTER_OFFSET,
        "footer_version": "1.0",
        "original_image_size": ONCLITE_BODY_SIZE,
        "vbmeta_offset": ONCLITE_VBMETA_OFFSET,
        "vbmeta_size": ONCLITE_VBMETA_SIZE,
    }
    for key, value in expected.items():
        if layout[key] != value:
            raise RepackError(f"audited onclite layout mismatch for {key}: {layout[key]!r} != {value!r}")
    if u32(data, 12) != 0x80008000:
        raise RepackError("audited onclite kernel load address mismatch")
    external_digest = avb_sha256(AUDITED_EXTERNAL_BOOT_SALT, data[:ONCLITE_BODY_SIZE])
    if external_digest != AUDITED_EXTERNAL_BOOT_DIGEST:
        raise RepackError(
            "the audited external vbmeta descriptor does not match the supplied original boot body"
        )
    return {
        "original_external_descriptor_digest": external_digest,
        "original_external_descriptor_matches": True,
    }


def repack_image(
    stock_data: bytes,
    kernel_gz: bytes,
    *,
    expected_fdts: int = ONCLITE_FDT_COUNT,
    require_onclite_fingerprint: bool = True,
) -> tuple[bytes, dict[str, object]]:
    """Return a validated candidate image and report; never write or flash it."""
    layout = _parse_layout(stock_data, expected_fdts)
    if require_onclite_fingerprint:
        avb_original = _validate_onclite_stock(stock_data, layout)
        kernel_record_hash, kernel_record_label = _validate_diagnostic_kernel(kernel_gz)
    else:
        avb_original = {"original_external_descriptor_matches": "not checked in synthetic-test mode"}
        kernel_record_hash, kernel_record_label = None, "synthetic test kernel"

    new_kernel_image, unexpected_tail = decode_gzip(
        kernel_gz, "replacement kernel payload", allow_appended_data=False
    )
    if unexpected_tail:
        raise RepackError("replacement kernel payload contains trailing bytes")
    new_component = kernel_gz + bytes(layout["fdt_tail"])
    if len(new_component) > 0xFFFFFFFF:
        raise RepackError("replacement kernel component exceeds the Android header size field")
    new_kernel_end = int(layout["kernel_offset"]) + len(new_component)
    if align(new_kernel_end, int(layout["page_size"])) > int(layout["body_end"]):
        raise RepackError("replacement kernel plus retained FDT tail does not fit the original AVB body boundary")

    candidate = bytearray(stock_data)
    struct.pack_into("<I", candidate, 8, len(new_component))
    candidate[576:608] = legacy_boot_id(new_component)
    candidate[int(layout["kernel_offset"]) : int(layout["body_end"])] = (
        new_component + (b"\0" * (int(layout["body_end"]) - new_kernel_end))
    )
    result = bytes(candidate)

    # Reparse the output and verify precisely what this routine promises to keep.
    new_layout = _parse_layout(result, expected_fdts)
    if result[:8] != stock_data[:8] or result[12:576] != stock_data[12:576]:
        raise RepackError("boot header bytes other than kernel_size and legacy ID changed")
    if result[608 : int(layout["page_size"])] != stock_data[608 : int(layout["page_size"])]:
        raise RepackError("boot header/page bytes beyond the legacy ID changed")
    if result[int(layout["body_end"]) :] != stock_data[int(layout["body_end"]) :]:
        raise RepackError("bytes at/after the original AVB body boundary changed")
    if new_layout["fdt_tail"] != layout["fdt_tail"]:
        raise RepackError("the appended FDT tail changed during repacking")
    expected_id = legacy_boot_id(new_component)
    if result[576:608] != expected_id:
        raise RepackError("legacy boot ID does not match the repacked components")
    if new_layout["kernel_size"] != len(new_component):
        raise RepackError("repacked kernel_size field does not match the new component")

    avb_report: dict[str, object] = {
        **avb_original,
        "footer_and_embedded_vbmeta_bytes_preserved": (
            result[int(layout["footer_offset"]) :] == stock_data[int(layout["footer_offset"]) :]
            and result[int(layout["vbmeta_offset"]) : int(layout["vbmeta_offset"]) + int(layout["vbmeta_size"])]
            == stock_data[int(layout["vbmeta_offset"]) : int(layout["vbmeta_offset"]) + int(layout["vbmeta_size"])]
        ),
        "separate_external_vbmeta": "not an input to this tool and never written",
        "repacked_body_matches_audited_original_external_descriptor": None,
        "device_acceptance": "unknown; an unlocked report is not proof of this bootloader's AVB error policy",
    }
    if require_onclite_fingerprint:
        repacked_digest = avb_sha256(
            AUDITED_EXTERNAL_BOOT_SALT, result[:ONCLITE_BODY_SIZE]
        )
        avb_report["repacked_external_descriptor_digest"] = repacked_digest
        avb_report["repacked_body_matches_audited_original_external_descriptor"] = (
            repacked_digest == AUDITED_EXTERNAL_BOOT_DIGEST
        )
        if avb_report["repacked_body_matches_audited_original_external_descriptor"]:
            raise RepackError("repacked body unexpectedly matches the original external descriptor")

    report: dict[str, object] = {
        "result": "STATIC_REPACK_VALIDATED_ONLY_NOT_BOOT_OR_FLASH_TESTED",
        "stock_boot_sha256": sha256(stock_data),
        "candidate_boot_sha256": sha256(result),
        "candidate_partition_size": len(result),
        "header_version": new_layout["header_version"],
        "page_size": new_layout["page_size"],
        "kernel_component_offset": new_layout["kernel_offset"],
        "kernel_component_size": new_layout["kernel_size"],
        "kernel_image_size": len(new_kernel_image),
        "kernel_image_sha256": sha256(new_kernel_image),
        "kernel_payload_sha256": sha256(kernel_gz),
        "kernel_artifact_recorded_sha256": kernel_record_hash,
        "kernel_artifact_record": kernel_record_label,
        "ramdisk_size": new_layout["ramdisk_size"],
        "body_size_preserved": new_layout["original_image_size"] == layout["original_image_size"],
        "appended_fdt_count": new_layout["fdt_count"],
        "appended_fdt_tail_size": len(new_layout["fdt_tail"]),
        "appended_fdt_tail_sha256": new_layout["fdt_tail_sha256"],
        "appended_fdt_tail_byte_identical": new_layout["fdt_tail"] == layout["fdt_tail"],
        "header_preserved_except_kernel_size_and_legacy_id": True,
        "legacy_boot_id": result[576:596].hex(),
        "suffix_from_original_image_size_byte_identical": (
            result[int(layout["body_end"]) :] == stock_data[int(layout["body_end"]) :]
        ),
        "avb": avb_report,
        "written_to_device": False,
    }
    return result, report


def write_new_file(path: pathlib.Path, data: bytes) -> None:
    """Atomically create a new file without ever replacing an existing path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_name, path)
    except FileExistsError as exc:
        raise RepackError(f"refusing to overwrite existing output: {path}") from exc
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_boot", type=pathlib.Path, help="exact audited original onclite boot image (read-only)")
    parser.add_argument("kernel_image_gz", type=pathlib.Path, help="pure gzip arm64 Image (no appended FDT bytes)")
    parser.add_argument("output", type=pathlib.Path, help="new candidate .img path; existing files are never overwritten")
    parser.add_argument(
        "--allow-stale-avb-lab-artifact",
        action="store_true",
        help="explicitly permit writing a static image whose original AVB body digest is stale; not a boot/flash claim",
    )
    args = parser.parse_args()
    if args.output.suffix.lower() != ".img":
        parser.error("output must use a .img extension")
    root = pathlib.Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    protected = {
        (root / "Redmi7_onclite_Kernel_Flashable.zip").resolve(),
        (root / "backups" / "original" / "boot.img").resolve(),
    }
    if output in protected or (root / "backups" / "original").resolve() in output.parents:
        parser.error("output path is protected; choose a separate experimental artifact path")
    if output.exists():
        parser.error(f"refusing to overwrite existing output: {output}")
    if args.stock_boot.resolve() == output or args.kernel_image_gz.resolve() == output:
        parser.error("output must differ from both input paths")

    try:
        stock_data = args.stock_boot.read_bytes()
        kernel_data = args.kernel_image_gz.read_bytes()
        candidate, report = repack_image(stock_data, kernel_data, require_onclite_fingerprint=True)
    except (OSError, RepackError) as exc:
        parser.exit(1, f"REPACK REFUSED: {exc}\n")

    print(json.dumps(report, indent=2, sort_keys=True))
    if not args.allow_stale_avb_lab_artifact:
        parser.exit(
            2,
            "No output written. The original AVB descriptor is stale for a modified boot. "
            "Use --allow-stale-avb-lab-artifact only for a static lab artifact after reviewing that mismatch.\n",
        )
    try:
        write_new_file(output, candidate)
        written = output.read_bytes()
        if sha256(written) != report["candidate_boot_sha256"]:
            output.unlink(missing_ok=True)
            parser.exit(1, "REPACK FAILED: output read-back hash mismatch; partial output removed\n")
    except (OSError, RepackError) as exc:
        parser.exit(1, f"REPACK FAILED: {exc}\n")
    print(f"Wrote new static candidate only: {output}")
    print("AVB is not disabled or re-signed; no device acceptance or physical test is claimed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
