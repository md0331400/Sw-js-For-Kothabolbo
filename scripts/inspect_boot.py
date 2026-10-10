#!/usr/bin/env python3
"""Inspect Android boot image v0-v2 components without modifying the input."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import struct
import sys
import zlib

ANDROID_MAGIC = b"ANDROID!"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"
AVB_FOOTER_MAGIC = b"AVBf"
AVB_VBMETA_MAGIC = b"AVB0"


def u32(data: bytes, offset: int, endian: str = "<") -> int:
    return struct.unpack_from(endian + "I", data, offset)[0]


def u64(data: bytes, offset: int, endian: str = "<") -> int:
    return struct.unpack_from(endian + "Q", data, offset)[0]


def align(value: int, page_size: int) -> int:
    return (value + page_size - 1) // page_size * page_size


def cstrings(value: bytes) -> list[str]:
    return [part.decode("ascii", "replace") for part in value.split(b"\0") if part]


def fdt_root_properties(blob: bytes) -> dict[str, bytes]:
    if len(blob) < 40 or blob[:4] != FDT_MAGIC:
        return {}
    total = int.from_bytes(blob[4:8], "big")
    struct_off = int.from_bytes(blob[8:12], "big")
    strings_off = int.from_bytes(blob[12:16], "big")
    strings_size = int.from_bytes(blob[32:36], "big")
    struct_size = int.from_bytes(blob[36:40], "big")
    if total > len(blob) or struct_off + struct_size > total or strings_off + strings_size > total:
        return {}
    structure = blob[struct_off : struct_off + struct_size]
    strings = blob[strings_off : strings_off + strings_size]
    pos = 0
    depth = 0
    props: dict[str, bytes] = {}
    while pos + 4 <= len(structure):
        token = int.from_bytes(structure[pos : pos + 4], "big")
        pos += 4
        if token == 1:  # FDT_BEGIN_NODE
            end = structure.find(b"\0", pos)
            if end < 0:
                break
            pos = (end + 4) & ~3
            depth += 1
        elif token == 2:  # FDT_END_NODE
            depth -= 1
        elif token == 3:  # FDT_PROP
            if pos + 8 > len(structure):
                break
            size = int.from_bytes(structure[pos : pos + 4], "big")
            nameoff = int.from_bytes(structure[pos + 4 : pos + 8], "big")
            pos += 8
            if size > len(structure) - pos:
                break
            value = structure[pos : pos + size]
            pos = (pos + size + 3) & ~3
            end = strings.find(b"\0", nameoff)
            if depth == 1 and nameoff < len(strings) and end >= 0:
                name = strings[nameoff:end].decode("ascii", "replace")
                props[name] = value
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9:  # FDT_END
            break
        else:
            break
    return props


def inspect_dtbs(tail: bytes) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    pos = 0
    while True:
        offset = tail.find(FDT_MAGIC, pos)
        if offset < 0:
            break
        if offset + 40 <= len(tail):
            size = int.from_bytes(tail[offset + 4 : offset + 8], "big")
            if 40 <= size <= len(tail) - offset:
                blob = tail[offset : offset + size]
                props = fdt_root_properties(blob)
                if props:
                    board = props.get("qcom,board-id", b"")
                    msm = props.get("qcom,msm-id", b"")
                    found.append(
                        {
                            "offset": offset,
                            "size": size,
                            "model": "|".join(cstrings(props.get("model", b""))),
                            "compatible": "|".join(cstrings(props.get("compatible", b""))),
                            "qcom_board_id_cells": [f"0x{x:08x}" for x in struct.unpack(f">{len(board)//4}I", board)] if board and len(board) % 4 == 0 else [],
                            "qcom_msm_id_cells": [f"0x{x:08x}" for x in struct.unpack(f">{len(msm)//4}I", msm)] if msm and len(msm) % 4 == 0 else [],
                        }
                    )
                    pos = offset + size
                    continue
        pos = offset + 4
    return found


def parse_config(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            result[line.split()[1]] = "n"
    return result


def inspect(path: pathlib.Path, defconfigs: list[tuple[str, pathlib.Path]] | None = None) -> dict[str, object]:
    defconfigs = defconfigs or []
    embedded_config: dict[str, str] | None = None
    data = path.read_bytes()
    result: dict[str, object] = {
        "path": str(path),
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "magic": data[:8].decode("ascii", "replace"),
    }
    if data[:8] != ANDROID_MAGIC or len(data) < 2048:
        result["error"] = "Not a supported Android boot image (expected ANDROID! v0-v2)."
        return result

    kernel_size = u32(data, 8)
    ramdisk_size = u32(data, 16)
    second_size = u32(data, 24)
    page_size = u32(data, 36)
    version = u32(data, 40)
    if version not in (0, 1, 2):
        result["error"] = f"Header version {version} is outside this inspector's v0-v2 support."
        return result
    if page_size < 512 or page_size & (page_size - 1):
        result["error"] = f"Invalid boot page size: {page_size}"
        return result

    kernel_offset = page_size
    kernel_end = kernel_offset + kernel_size
    ramdisk_offset = align(kernel_end, page_size)
    ramdisk_end = ramdisk_offset + ramdisk_size
    second_offset = align(ramdisk_end, page_size)
    second_end = second_offset + second_size
    components: dict[str, object] = {
        "header_version": version,
        "header_size": u32(data, 1644) if version >= 1 else 1632,
        "page_size": page_size,
        "kernel": {"offset": kernel_offset, "size": kernel_size},
        "ramdisk": {"offset": ramdisk_offset, "size": ramdisk_size, "present": bool(ramdisk_size)},
        "second": {"offset": second_offset, "size": second_size},
        "cmdline": b" ".join(
            part for part in (data[64:576].split(b"\0", 1)[0], data[608:1632].split(b"\0", 1)[0]) if part
        ).decode("ascii", "replace").strip(),
    }
    if version >= 1:
        dtbo_size = u32(data, 1632)
        dtbo_offset = u64(data, 1636)
        components["recovery_dtbo"] = {"offset": dtbo_offset, "size": dtbo_size, "present": bool(dtbo_size)}
        components["header_size"] = u32(data, 1644)
    if version >= 2:
        dtb_size = u32(data, 1648)
        dtb_offset = align(second_end, page_size)
        components["separate_dtb"] = {"offset": dtb_offset, "size": dtb_size, "present": bool(dtb_size)}
    result["components"] = components

    if kernel_end > len(data) or ramdisk_end > len(data) or second_end > len(data):
        result["error"] = "Header component sizes extend past end of file."
        return result

    kernel = data[kernel_offset:kernel_end]
    kernel_info: dict[str, object] = {"prefix_hex": kernel[:8].hex(), "compressed_size": len(kernel)}
    tail = b""
    image = kernel
    if kernel.startswith(b"\x1f\x8b"):
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            image = decoder.decompress(kernel) + decoder.flush()
            tail = decoder.unused_data
            kernel_info["compression"] = "gzip"
            kernel_info["gzip_eof"] = decoder.eof
        except zlib.error as exc:
            kernel_info["compression"] = "gzip (invalid)"
            kernel_info["gzip_error"] = str(exc)
    elif kernel.startswith(b"\x04\x22\x4d\x18"):
        kernel_info["compression"] = "lz4 frame"
    elif kernel.startswith(b"\x02\x21\x4c\x18"):
        kernel_info["compression"] = "lz4 legacy"
    else:
        kernel_info["compression"] = "unrecognized"
    kernel_info["decompressed_size"] = len(image)
    kernel_info["decompressed_sha256"] = hashlib.sha256(image).hexdigest()
    if kernel.startswith(b"\x1f\x8b") and not kernel_info.get("gzip_error"):
        gzip_member_size = len(kernel) - len(tail)
        kernel_info["gzip_member_size"] = gzip_member_size
        kernel_info["gzip_member_sha256"] = hashlib.sha256(kernel[:gzip_member_size]).hexdigest()
    kernel_info["arm64_image_magic_at_56"] = image[56:60].decode("ascii", "replace") if len(image) >= 60 else None
    releases = [x.decode("ascii", "replace") for x in re.findall(rb"Linux version [^\x00\n]{1,200}", image) if b"%" not in x]
    kernel_info["linux_version_strings"] = releases[:3]
    kernel_info["appended_data_size"] = len(tail)
    fdt_blobs = inspect_dtbs(tail)
    kernel_info["appended_fdt_blobs"] = fdt_blobs
    kernel_info["appended_fdt_count"] = len(fdt_blobs)
    if tail:
        kernel_info["appended_data_sha256"] = hashlib.sha256(tail).hexdigest()
    cfg_start = image.find(b"IKCFG_ST")
    cfg_end = image.find(b"IKCFG_ED", cfg_start + 8) if cfg_start >= 0 else -1
    if cfg_start >= 0 and cfg_end > cfg_start:
        try:
            cfg = zlib.decompress(image[cfg_start + 8 : cfg_end], 16 + zlib.MAX_WBITS).decode("utf-8", "replace")
            keys = (
                "CONFIG_LOCALVERSION", "CONFIG_LOCALVERSION_AUTO", "CONFIG_MODULES", "CONFIG_MODVERSIONS",
                "CONFIG_MODULE_SIG", "CONFIG_MODULE_SIG_FORCE", "CONFIG_MODULE_SIG_SHA512",
                "CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE",
            )
            embedded_config = parse_config(cfg)
            kernel_info["embedded_config"] = {key: embedded_config.get(key) for key in keys}
            kernel_info["embedded_config_line_count"] = len(cfg.splitlines())
            kernel_info["embedded_config_sha256"] = hashlib.sha256(cfg.encode("utf-8")).hexdigest()
        except zlib.error as exc:
            kernel_info["embedded_config_error"] = str(exc)
    else:
        kernel_info["embedded_config"] = None
    result["kernel_info"] = kernel_info
    marker_terms = (b"magisk", b"supersu", b"init.magisk", b".magisk")
    marker_regions = {
        "raw_partition_image": data,
        "decompressed_kernel_image": image,
        "appended_kernel_data": tail,
        "ramdisk_component": data[ramdisk_offset:ramdisk_end],
    }
    result["magisk_marker_strings"] = {
        region: [term.decode("ascii") for term in marker_terms if term in content.lower()]
        for region, content in marker_regions.items()
    }
    if embedded_config is not None and defconfigs:
        comparisons = []
        for label, config_path in defconfigs:
            reference = parse_config(config_path.read_text(errors="replace"))
            missing = sorted(key for key in reference if key not in embedded_config)
            mismatches = sorted(
                (key, reference[key], embedded_config[key])
                for key in reference
                if key in embedded_config and reference[key] != embedded_config[key]
            )
            comparisons.append(
                {
                    "label": label,
                    "defconfig_entries": len(reference),
                    "matching_values": len(reference) - len(missing) - len(mismatches),
                    "missing_from_embedded_config": missing,
                    "value_mismatches": [
                        {"key": key, "defconfig": expected, "embedded": actual}
                        for key, expected, actual in mismatches
                    ],
                }
            )
        result["defconfig_comparisons"] = comparisons

    if version >= 1:
        footer_offset = len(data) - 64
        if footer_offset >= 0 and data[footer_offset : footer_offset + 4] == AVB_FOOTER_MAGIC:
            _, major, minor, original_size, vbmeta_offset, vbmeta_size = struct.unpack_from(">4sIIQQQ", data, footer_offset)
            avb: dict[str, object] = {
                "footer_offset": footer_offset,
                "footer_version": f"{major}.{minor}",
                "original_image_size": original_size,
                "vbmeta_offset": vbmeta_offset,
                "vbmeta_size": vbmeta_size,
            }
            if vbmeta_offset + vbmeta_size <= len(data) and data[vbmeta_offset : vbmeta_offset + 4] == AVB_VBMETA_MAGIC:
                _, vbmajor, vbminor, auth_size, aux_size, algorithm = struct.unpack_from(">4sIIQQI", data, vbmeta_offset)
                avb.update({"vbmeta_version": f"{vbmajor}.{vbminor}", "auth_block_size": auth_size, "auxiliary_block_size": aux_size, "algorithm_type": algorithm})
            result["avb_footer"] = avb
        else:
            result["avb_footer"] = None
    if ramdisk_size == 0:
        result["magisk_status"] = "not assessable from this boot image: header reports no ramdisk"
    else:
        result["magisk_status"] = "not determined by this header-only inspector; inspect the extracted ramdisk"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=pathlib.Path, help="input boot.img (never modified)")
    parser.add_argument(
        "--defconfig",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="compare the embedded kernel config with a reference defconfig; repeatable",
    )
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"file not found: {args.image}")
    defconfigs: list[tuple[str, pathlib.Path]] = []
    for item in args.defconfig:
        if "=" not in item:
            parser.error(f"expected LABEL=PATH for --defconfig, got {item!r}")
        label, raw_path = item.split("=", 1)
        config_path = pathlib.Path(raw_path)
        if not config_path.is_file():
            parser.error(f"defconfig not found: {config_path}")
        defconfigs.append((label, config_path))
    print(json.dumps(inspect(args.image, defconfigs), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
