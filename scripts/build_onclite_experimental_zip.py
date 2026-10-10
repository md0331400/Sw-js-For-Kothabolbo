#!/usr/bin/env python3
"""Build a separate, fail-closed experimental onclite test ZIP.

Inputs are read-only. The existing AnyKernel ZIP is only used as a pinned
source for its recovery BusyBox and bundled license notice. The original boot
image is never copied into the package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import stat
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_EXISTING_ZIP_SHA256 = "58df6f662cce96d1106e406ecad30dc757027619ceb363d9d5fcd1ec013ae79f"
EXPECTED_STOCK_BOOT_SHA256 = "cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30"
EXPECTED_KERNEL_SHA256 = "255b8cf621055cc1ff48d256204f8690a6c9892047a40d0cb9cb2c838c23eb96"
EXPECTED_CANDIDATE_SHA256 = "684d5f2f29ee0dfeb9519a007be99594a8ba9af7c57c1734dec3b0fc06a0495c"
EXPECTED_SIZE = 67_108_864
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: pathlib.Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def sha256_zip_entry(archive: zipfile.ZipFile, name: str) -> str:
    with archive.open(name, "r") as stream:
        return sha256_stream(stream)


def require_hash(label: str, path: pathlib.Path, expected: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} is not a file: {path}")
    actual = sha256_path(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch: got {actual}, expected {expected}")


def file_entry(name: str, path: pathlib.Path, mode: int) -> tuple[str, pathlib.Path | bytes, int]:
    return name, path, mode


def bytes_entry(name: str, value: bytes, mode: int = 0o644) -> tuple[str, pathlib.Path | bytes, int]:
    return name, value, mode


def entry_digest(value: pathlib.Path | bytes) -> tuple[int, str]:
    if isinstance(value, bytes):
        return len(value), hashlib.sha256(value).hexdigest()
    return value.stat().st_size, sha256_path(value)


def add_entry(archive: zipfile.ZipFile, name: str, value: pathlib.Path | bytes, mode: int) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.flag_bits |= 0x800
    with archive.open(info, "w", force_zip64=True) as target:
        if isinstance(value, bytes):
            target.write(value)
        else:
            with value.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)


def build(args: argparse.Namespace) -> dict[str, object]:
    existing_zip = args.existing_zip.resolve()
    stock_boot = args.stock.resolve()
    kernel = args.kernel.resolve()
    candidate = args.candidate.resolve()
    audit_path = args.audit.resolve()
    repack_report = args.repack_report.resolve()
    installer_validation = args.installer_validation.resolve()
    output = args.output.resolve()

    require_hash("existing ZIP", existing_zip, EXPECTED_EXISTING_ZIP_SHA256)
    require_hash("original boot", stock_boot, EXPECTED_STOCK_BOOT_SHA256)
    require_hash("rebuilt Image.gz", kernel, EXPECTED_KERNEL_SHA256)
    require_hash("candidate boot", candidate, EXPECTED_CANDIDATE_SHA256)
    if stock_boot.stat().st_size != EXPECTED_SIZE or candidate.stat().st_size != EXPECTED_SIZE:
        raise ValueError(f"stock and candidate boot images must both be {EXPECTED_SIZE} bytes")

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("sha256") != EXPECTED_CANDIDATE_SHA256 or audit.get("file_size") != EXPECTED_SIZE:
        raise ValueError("candidate audit does not match the pinned image hash/size")
    components = audit.get("components", {})
    if components.get("header_version") != 1 or components.get("page_size") != 2048:
        raise ValueError("candidate audit does not describe the expected v1/2048-byte layout")
    if components.get("ramdisk", {}).get("size") != 0 or components.get("second", {}).get("size") != 0:
        raise ValueError("candidate is not the audited zero-ramdisk/zero-second layout")
    kernel_info = audit.get("kernel_info", {})
    if kernel_info.get("appended_fdt_count") != 17 or kernel_info.get("appended_data_sha256") != "4a5fd265b67b34a535b3bda15bb88568948d80154da15eab1dfaf7cc70268ca5":
        raise ValueError("candidate audit does not contain the preserved audited 17-FDT tail")
    avb = audit.get("avb_footer", {})
    if avb.get("footer_version") != "1.0" or avb.get("vbmeta_version") != "1.0":
        raise ValueError("candidate audit does not show the preserved AVB footer/VBMeta structure")
    if not repack_report.is_file() or EXPECTED_CANDIDATE_SHA256 not in repack_report.read_text(encoding="utf-8"):
        raise ValueError("repack report is absent or does not cite the pinned candidate")
    if '"repacked_body_matches_audited_original_external_descriptor": false' not in repack_report.read_text(encoding="utf-8"):
        raise ValueError("repack report must disclose the external AVB descriptor mismatch")
    host_validation = json.loads(installer_validation.read_text(encoding="utf-8"))
    if (
        host_validation.get("result") != "FILE_BACKED_HOST_TEST_PASS_NOT_RECOVERY_OR_DEVICE_TEST"
        or host_validation.get("shells_tested") != ["bash", "dash"]
        or host_validation.get("candidate_sha256_expected_and_readback") != EXPECTED_CANDIDATE_SHA256
        or host_validation.get("original_sha256_expected_and_backup") != EXPECTED_STOCK_BOOT_SHA256
        or host_validation.get("physical_device_tested") is not False
    ):
        raise ValueError("installer host-validation report is missing or inconsistent")

    package_root = ROOT / "installer" / "experimental"
    update_binary = package_root / "update-binary"
    flash_script = package_root / "flash_prebuilt_boot.sh"
    helper = ROOT / "installer" / "prebuilt_boot_lib.sh"
    installation = package_root / "INSTALLATION.txt"
    notices = package_root / "THIRD_PARTY_NOTICES.txt"
    updater_script = b"#FLASHAFTERUPDATEV2\n# Custom prebuilt-boot test installer; no AnyKernel repack path.\n"
    updater_text = update_binary.read_text(encoding="utf-8")
    if f"FLASH_SCRIPT_SHA256={sha256_path(flash_script)}" not in updater_text:
        raise ValueError("recovery bootstrap does not pin the current flash-script SHA-256")
    if f"HELPER_SHA256={sha256_path(helper)}" not in updater_text:
        raise ValueError("recovery bootstrap does not pin the current helper SHA-256")

    with zipfile.ZipFile(existing_zip, "r") as source_zip:
        existing_names = set(source_zip.namelist())
        required = {"tools/busybox", "LICENSES/AnyKernel3-LICENSE.txt"}
        missing = required - existing_names
        if missing:
            raise ValueError(f"pinned source ZIP is missing required entries: {sorted(missing)}")
        busybox = source_zip.read("tools/busybox")
        ak_license = source_zip.read("LICENSES/AnyKernel3-LICENSE.txt")

    entries: list[tuple[str, pathlib.Path | bytes, int]] = [
        file_entry("META-INF/com/google/android/update-binary", update_binary, 0o755),
        bytes_entry("META-INF/com/google/android/updater-script", updater_script),
        file_entry("installer/flash_prebuilt_boot.sh", flash_script, 0o755),
        file_entry("installer/prebuilt_boot_lib.sh", helper, 0o644),
        file_entry("payload/boot.img", candidate, 0o644),
        file_entry("README_TEST_ONLY.txt", installation, 0o644),
        file_entry("THIRD_PARTY_NOTICES.txt", notices, 0o644),
        bytes_entry("LICENSES/AnyKernel3-LICENSE.txt", ak_license),
        bytes_entry("tools/busybox", busybox, 0o755),
        file_entry("DIAGNOSTICS/onclite-experimental-boot-audit.json", audit_path, 0o644),
        file_entry("DIAGNOSTICS/onclite-experimental-repack.txt", repack_report, 0o644),
        file_entry("DIAGNOSTICS/experimental-installer-host-validation.json", installer_validation, 0o644),
    ]

    names = [entry[0] for entry in entries]
    if len(names) != len(set(names)):
        raise ValueError("duplicate archive path")
    if "google_drive/boot.img" in names or "backups/original/boot.img" in names or "boot.img" in names:
        raise ValueError("refusing to package an original boot image")
    manifest_lines = [
        "Redmi 7 onclite experimental test ZIP contents",
        "All paths are package-relative. Candidate boot is not the stock original.",
        "The manifest does not include its own hash.",
        "",
        "PATH\tSIZE_BYTES\tSHA256",
    ]
    for name, value, _mode in entries:
        size, digest = entry_digest(value)
        manifest_lines.append(f"{name}\t{size}\t{digest}")
    manifest_lines.append("")
    manifest = ("\n".join(manifest_lines)).encode("utf-8")
    entries.append(bytes_entry("TEST_ZIP_MANIFEST.txt", manifest))

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
            for name, value, mode in entries:
                add_entry(archive, name, value, mode)
        with zipfile.ZipFile(output, "r") as archive:
            bad_entry = archive.testzip()
            if bad_entry is not None:
                raise ValueError(f"ZIP CRC validation failed at {bad_entry}")
            if set(archive.namelist()) != set(names + ["TEST_ZIP_MANIFEST.txt"]):
                raise ValueError("ZIP entry set differs from the reviewed package manifest")
            if sha256_zip_entry(archive, "payload/boot.img") != EXPECTED_CANDIDATE_SHA256:
                raise ValueError("packaged candidate hash mismatch")
            if sha256_zip_entry(archive, "tools/busybox") != hashlib.sha256(busybox).hexdigest():
                raise ValueError("packaged BusyBox differs from the pinned existing ZIP")
            if "google_drive/boot.img" in archive.namelist() or "backups/original/boot.img" in archive.namelist():
                raise ValueError("an original boot image was included")
    except Exception:
        try:
            output.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "result": "TEST_ZIP_BUILT_AND_ARCHIVE_VALIDATED_NOT_RECOVERY_OR_DEVICE_TESTED",
        "output": str(output),
        "size_bytes": output.stat().st_size,
        "sha256": sha256_path(output),
        "entry_count": len(entries),
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "original_boot_included": False,
        "existing_zip_sha256": sha256_path(existing_zip),
        "external_avb_descriptor_mismatch_disclosed": True,
        "recovery_or_device_tested": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing-zip", type=pathlib.Path, default=ROOT / "Redmi7_onclite_Kernel_Flashable.zip")
    parser.add_argument("--stock", type=pathlib.Path, default=ROOT / "google_drive" / "boot.img")
    parser.add_argument("--kernel", type=pathlib.Path, default=ROOT / "build-artifacts" / "onclite-kernel-only-stock-config" / "Image.gz")
    parser.add_argument("--candidate", type=pathlib.Path, default=ROOT / "build-artifacts" / "onclite-experimental-boot.img")
    parser.add_argument("--audit", type=pathlib.Path, default=ROOT / "reports" / "onclite-experimental-boot-audit.json")
    parser.add_argument("--repack-report", type=pathlib.Path, default=ROOT / "reports" / "onclite-experimental-repack.txt")
    parser.add_argument("--installer-validation", type=pathlib.Path, default=ROOT / "reports" / "experimental-installer-host-validation.json")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "build-artifacts" / "onclite-experimental-test.zip")
    return parser.parse_args()


def main() -> int:
    try:
        result = build(parse_args())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
