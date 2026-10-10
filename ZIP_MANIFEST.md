# Manifest for the existing candidate ZIP — BLOCKED, DO NOT FLASH

`Redmi7_onclite_Kernel_Flashable.zip` is the unchanged prior static candidate, **not an approved or flash-ready release**. A separate kernel-only diagnostic build now exists under the ignored `build-artifacts/onclite-kernel-only-stock-config/`; it was not inserted into this archive, and no test ZIP was produced. Its details and hashes are in [`reports/diagnostic-kernel-build.md`](reports/diagnostic-kernel-build.md). The audited original image is `backups/original/boot.img` (local, Git-ignored, and excluded from the ZIP). It has `ramdisk_size=0`; the candidate's installer requires a non-empty ramdisk and will abort before writing. Source revision/module ABI, AVB, Magisk/root state, and device identity remain unresolved. Do not bypass the installer guard.

## Archive identity

- Size: **11,975,575 bytes**
- SHA-256: `58df6f662cce96d1106e406ecad30dc757027619ceb363d9d5fcd1ec013ae79f`
- Payload `payload/Image.gz`: **10,748,052 bytes**, SHA-256 `b53cef1c92fa65e1f5f69093760f79ed49e4475e2a3a2551c0e7474f53bc7625`
- Payload after gzip decompression: **28,570,112 bytes**, SHA-256 `7b5ff7fe1ea19b531cd8bbae13077478644b488d560a1879dd48fff4f40bf816`
- ZIP CRC, path-safety, payload-format, shell syntax, and static installer-guard checks pass. These checks are not target compatibility or device tests.

## Contents

| Path | Purpose |
|---|---|
| `META-INF/com/google/android/update-binary` | AnyKernel3 recovery ZIP entry point. |
| `META-INF/com/google/android/updater-script` | AnyKernel3 updater metadata. |
| `anykernel.sh` | `onclite`-only checks, boot-header checks, and boot-only install flow. Requires a non-empty live ramdisk; aborts if missing. |
| `tools/ak3-core.sh` | AnyKernel3 live boot-image unpack/repack/flash helpers. |
| `tools/busybox` | Recovery shell applets required by AnyKernel3. |
| `tools/magiskboot` | Android boot-image parser/repacker used by AnyKernel3. |
| `payload/Image.gz` | Compressed arm64 kernel only. The installer expects to reuse DTB bytes extracted from the live boot image. |
| `banner`, `ZIP_CONTENTS.txt` | Recovery progress banner and archive description. |
| `LICENSES/AnyKernel3-LICENSE.txt` | Upstream installer/tool license notice. |

There are no original `boot.img`, ramdisk, `dtbo`, recovery, `vendor_boot`, `vbmeta`, or module images in the ZIP. The installer requests writes only to the by-name `boot` partition and leaves `PATCH_VBMETA_FLAG=0`; that does not prove AVB acceptance or root preservation.

## Supplied image compatibility finding

The original image at `backups/original/boot.img` is 67,108,864 bytes, SHA-256 `cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30`, Android boot header v1, page size 2048, kernel size 15,214,803, and ramdisk size **0**. Thus the ZIP's own ramdisk preflight should fail closed before `flash_boot`; the target-aware verifier confirms this with exit status 1. Do not edit out this guard.

The candidate and original kernel report the same `4.9.186-perf-g131f907` release label, but the uncompressed images differ: 21,595,768 bytes differ over the 28,570,112-byte common range, first difference at offset 17. The stock embedded config also differs from the candidate's selected `onclite-perf_defconfig`; exact source and module ABI are not proven. The Drive `vbmeta.img` is RSA-signed and its boot descriptor verifies for the original bytes; changing the kernel while leaving that vbmeta unchanged would not match the descriptor if AVB is enforced. Device key trust/enforcement state is unknown. See [`BUILD_REPORT.md`](BUILD_REPORT.md), [`reports/onclite-boot-audit.json`](reports/onclite-boot-audit.json), and [`reports/google-drive-image-audit.md`](reports/google-drive-image-audit.md).

## Verification

```sh
python3 scripts/verify_zip.py Redmi7_onclite_Kernel_Flashable.zip
python3 scripts/verify_zip.py Redmi7_onclite_Kernel_Flashable.zip --target-image backups/original/boot.img
```

The first command reports static package checks only. The second reports **BLOCKED** for the supplied zero-ramdisk image and exits non-zero. The exact output and exit statuses are saved in [`reports/zip-verification.txt`](reports/zip-verification.txt). Neither command modifies the ZIP or writes to a device. No recovery, physical-device, boot, AVB-enforcement, Magisk/root, or module-load test was performed.
