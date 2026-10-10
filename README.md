# Redmi 7 (`onclite`) kernel candidate — MIUI Global Android 10

> **BLOCKED — DO NOT FLASH `Redmi7_onclite_Kernel_Flashable.zip`.** The supplied original image is audited. It has a zero-length ramdisk, while the candidate installer requires a non-empty ramdisk and will abort before writing. Exact stock-source provenance, module ABI, AVB acceptance, and Magisk state remain unresolved. A separate diagnostic build's config comparison is documented below; it does not approve the ZIP. The archive remains unchanged, a static candidate—not a release.

This project targets the Xiaomi Redmi 7 (`onclite`) and the requested MIUI Global `11.0.2.0(QFLMIXM)` / Android 10 context. The contents of the supplied boot image alone do **not** prove that the physical device or exact ROM matches those labels. Do not confuse `onclite` with Redmi 7A, Redmi Note 7, or Redmi Y3 (`onc`). A kernel defconfig filename is not device-identification evidence.

## Original boot image and audit

The original was obtained from `boot.zip` on this repository's `main` branch. The archive's Git blob ID matched the GitHub tree, the inner ZIP passed integrity checks and contains only `boot.img`, and the extracted image SHA-256 matches the GitHub Releases API digest.

- Local byte-for-byte backup: `backups/original/boot.img` (**ignored by Git; not included in the candidate ZIP**).
- Size: **67,108,864 bytes**; SHA-256: `cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30`.
- Header: Android boot header **v1**, 2048-byte page, 1648-byte header; kernel component 15,214,803 bytes; ramdisk 0; second stage 0; recovery-DTBO 0. There is no separate v2 DTB field; the kernel component contains a gzip `Image` followed by appended FDT data.
- Kernel release: `4.9.186-perf-g131f907`; build string says GCC 4.9.x 20150123 and 9 March 2021. The release string is not proof of source revision, configuration equivalence, or ABI equivalence.
- The appended data contains **17 structurally valid FDTs**, including Qualcomm SDM632/PMI632 and other reference SoC trees. The Google Drive `dtbo.img` was also inspected: it has an Android DT table with 17 generic Qualcomm overlays, but none establishes which onclite board tree/overlay the bootloader selects.
- Android AVB properties report Android 10 and security patch `2021-03-01`; they do not identify the exact MIUI build or physical device.

The Drive folder also contains an external `vbmeta.img`. Its `SHA256_RSA2048` signature verifies against the embedded public key, and its boot and DTBO hash descriptors verify against these exact supplied images. The boot image's embedded AVB footer is v1.0 with `Algorithm: NONE` and a zero-byte authentication block; this internal hash is not a cryptographic signature. The external signed vbmeta covers the original boot bytes, so changing the kernel while leaving vbmeta unchanged will not match that descriptor if the device enforces it. The bootloader's trust anchor and enforcement state remain unknown; no AVB metadata was changed. Full vbmeta verification stops at the missing `recovery.img`; system/vendor hashtrees were not verified.

The boot header reports **no ramdisk**. There is therefore no ramdisk cpio to inspect for Magisk markers. No obvious Magisk marker strings were found in the raw image, decompressed kernel, or appended FDT data; this cannot establish that the phone is unrooted or rooted, because Magisk could be installed through another image or partition. Root preservation cannot be promised from this input.

Detailed results are in [`BUILD_REPORT.md`](BUILD_REPORT.md), [`reports/google-drive-image-audit.md`](reports/google-drive-image-audit.md), [`reports/onclite-boot-audit.json`](reports/onclite-boot-audit.json), [`reports/avb-original-boot.txt`](reports/avb-original-boot.txt), [`reports/google-drive-avb-verification.txt`](reports/google-drive-avb-verification.txt), and [`reports/zip-verification.txt`](reports/zip-verification.txt). The boot inspector is [`scripts/inspect_boot.py`](scripts/inspect_boot.py), the static kernel/FDT-layout checker is [`scripts/validate_kernel_artifact.py`](scripts/validate_kernel_artifact.py), and the static/target-aware ZIP verifier is [`scripts/verify_zip.py`](scripts/verify_zip.py). Original and Drive-staged images stay local and ignored; do not add them to Git or any release.

## Source, configuration, toolchain, and ABI findings

The existing ZIP's historical candidate was built from Xiaomi's `onc-q-oss` source pinned at `fa577bc566886db1e0dfb1ddf66ff7c528148b2b`, using `onclite-perf_defconfig` and an Android AArch64 GCC 4.9 toolchain; that archive remains unchanged. A separate **kernel-only diagnostic build** now uses `onc-perf_defconfig` and is not included in any ZIP. Xiaomi's pinned commit is relevant, but the exact revision that produced stock `g131f907` has not been established: GitHub's commit API found no `131f907` commit in the Xiaomi repository.

The original kernel has an embedded 5,009-line config (`IKCONFIG`). It reports `CONFIG_MODULES=y`, `CONFIG_MODVERSIONS=y`, `CONFIG_MODULE_SIG=y`, `CONFIG_MODULE_SIG_FORCE=y`, and SHA-512 module signatures. Comparing the two pinned defconfigs to stock makes `onc-perf_defconfig` the stronger reference: zero assignment-value mismatches (six defconfig entries absent) versus six mismatches (and eleven entries absent) for `onclite-perf_defconfig`. This is configuration evidence, **not proof that the phone is an `onc` device**. The final diagnostic config restored stock `CONFIG_TASK_DELAY_ACCT=y` and `CONFIG_SOCKEV_NLMCAST=y`, which the upstream defconfig omits. Its full generated config (SHA-256 `f3d8d3b08369b0c433e6e7106447df4176df010659537d50652a60f50547660e`) differs from stock only at `CONFIG_MODULE_SIG_FORCE` among symbols supported by the pinned source; stock-only `CONFIG_KTRACE` and `CONFIG_RTMM` have no Kconfig declarations there. Exact source revision and target identity remain unresolved. See [`reports/diagnostic-kernel-build.md`](reports/diagnostic-kernel-build.md) for the full diff.

The existing ZIP's payload intentionally unsets `CONFIG_MODULE_SIG_FORCE`; its historical build also disables automatic local-version suffixing and manually sets `-g131f907`, while stock has `CONFIG_LOCALVERSION_AUTO=y`. That spoofed label does not reproduce source or ABI. The new diagnostic build keeps `CONFIG_LOCALVERSION_AUTO=y`, reports `4.9.186-perf-gfa577bc5-dirty`, and changes only forced-signature policy among supported stock config symbols. `CONFIG_MODVERSIONS=y` remains enabled. Matching release labels alone cannot establish module compatibility: symbol CRCs, the exact `Module.symvers`, and matching `.ko` files are needed. Drive contains `vendor.img`, but it is 926,327,184 bytes—over the connector's 100 MB download limit—so no modules or `Module.symvers` were read. No module was loaded on a phone.

The stock GCC banner and the pinned compiler's `4.9.x 20150123 (prerelease)` text agree, but the stock compiler binary cannot be recovered from that banner. The diagnostic compiler binary SHA-256 is `d6feb5d499457af0e4ed41d45e008e61dc69a6b644940686703f2e8386461049`; identical stock compiler/build inputs remain unproven. The separate diagnostic `Image.gz` is 11,050,592 bytes (SHA-256 `e177c6841bc8150d9488b2fc80127c91b169a15f19be47d9467747d3a8af54d5`), with release `4.9.186-perf-gfa577bc5-dirty`; it is not the old ZIP kernel payload or evidence of matching stock binary/ABI. Its local artifact and full metadata are under the ignored `build-artifacts/onclite-kernel-only-stock-config/` directory.

## Candidate ZIP and installer result

The existing `Redmi7_onclite_Kernel_Flashable.zip` is unchanged. Static archive, CRC, shell syntax, payload-format, path-safety, and installer-guard checks pass. That is **not** target or boot verification.

The candidate's kernel has the same `4.9.186-perf-g131f907` release string as the original, but the uncompressed images differ: candidate 28,570,112 bytes; stock 28,606,976 bytes; 21,595,768 differing bytes across their common range, first difference at byte 17. A matching release label cannot cure the unresolved source/config/ABI differences.

The installer checks for a non-empty live ramdisk and aborts if none is found. The audited image has `ramdisk_size=0`, so the candidate's expected behavior for this image is a **fail-closed abort before `flash_boot`**. The target-aware verifier reports a blocked result (exit status 1) for this image. Do not bypass the guard or modify it to force installation. The package also carries no image from which to recover the missing ramdisk, no original `boot.img`, no DTBO, no `vbmeta`, and no modules.

## Build and verification

The completed kernel-only build, exact commands, compiler identity, config delta, artifact hashes, and static FDT/layout checks are documented in [`reports/diagnostic-kernel-build.md`](reports/diagnostic-kernel-build.md) and [`BUILD_REPORT.md`](BUILD_REPORT.md). `scripts/build.sh` now builds only a diagnostic kernel and never packages a ZIP; its output is Git-ignored. The static inventory for the unchanged blocked archive is in [`ZIP_MANIFEST.md`](ZIP_MANIFEST.md). The successful host build does not resolve the source-revision, module-ABI, zero-ramdisk installer, or AVB blockers.

```sh
python3 scripts/inspect_boot.py backups/original/boot.img
python3 scripts/verify_zip.py Redmi7_onclite_Kernel_Flashable.zip
python3 scripts/verify_zip.py Redmi7_onclite_Kernel_Flashable.zip --target-image backups/original/boot.img
```

The last command intentionally exits non-zero and reports **BLOCKED** because the supplied target has no ramdisk. None of these commands flashes or writes to a device.

## Device testing status

No flashing, recovery execution, physical-device boot, AVB test, Magisk/root test, or module-load test occurred. There is no approved image for a phone test. Keep the original backup unchanged and separate; do not flash this ZIP. A future candidate would first need confirmed device/ROM identity, source/config and module-ABI review, a validated zero-ramdisk installation design that preserves the actual root arrangement, and an AVB plan that does not guess or silently disable verification. Only then would controlled device testing be appropriate.
