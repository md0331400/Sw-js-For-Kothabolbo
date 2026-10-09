# Redmi 7 (onclite) kernel — MIUI Global Android 10

This repository builds **`Redmi7_onclite_Kernel_Flashable.zip`** for the Xiaomi Redmi 7, codename **`onclite`**, targeting MIUI Global Stable **`11.0.2.0(QFLMIXM)`**, Android 10, Linux **4.9.186**. It is not for Redmi 7A, Redmi Note 7, or Redmi Y3 (`onc`).

> **BLOCKED — DO NOT FLASH.** The repository ZIP is a prior static-build candidate, **not a flash-ready release**. The supplied original `boot.img` could not be downloaded into this workspace: GitHub redirected the asset request to `release-assets.githubusercontent.com`, which this environment cannot reach. Therefore its header, kernel, ramdisk, DTB/DTBO, and Magisk state have not been inspected, and no local backup copy was created. The Xiaomi source commit corresponding to `g131f907` is also unverified. The existing candidate must not be flashed until both source and boot-image compatibility are audited.

## Original boot-image audit status

The user-provided [GitHub Release asset](https://github.com/md0331400/Sw-js-For-Kothabolbo/releases/download/Boot/boot.img) is listed by GitHub's Releases API as **67,108,864 bytes** with API-reported SHA-256 `cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30`. This digest is GitHub metadata only; it was **not independently calculated** because the binary download redirected to a host unavailable in this environment. No header/layout, kernel, ramdisk, DTB/DTBO, or Magisk inspection was possible, and the original was not copied into the workspace. Do not treat the API digest as local backup verification.

To continue, the exact 64 MiB `boot.img` bytes must be made available as a conversation attachment or another directly accessible input. The exact Xiaomi source commit behind `g131f907` and module ABI compatibility must also be established. Until then, the ZIP remains only a static candidate.

## Source and change

- Official Xiaomi source: [`MiCode/Xiaomi_Kernel_OpenSource`, `onc-q-oss`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/onc-q-oss)
- Pinned source commit: [`fa577bc566886db1e0dfb1ddf66ff7c528148b2b`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/commit/fa577bc566886db1e0dfb1ddf66ff7c528148b2b). Xiaomi's commit message identifies Android Q kernel changes for Redmi Y3 and Redmi 7, lists `onclite-perf_defconfig`, and is based on Qualcomm `LA.UM.8.6.2.r1-04900-89xx.0`.
- Kernel Makefile version: `4.9.186`; device configuration: `arch/arm64/configs/onclite-perf_defconfig`.
- Change: keep `CONFIG_MODULE_SIG=y` and SHA-512 verification, but unset `CONFIG_MODULE_SIG_FORCE`. Unsigned modules and signatures for which the kernel has no trusted key may then pass this policy check and taint the kernel; a cryptographically invalid signature still fails verification, and other module checks remain in place. The one-line patch is in [`patches/`](patches/0001-onclite-disable-module-signature-enforcement.patch).
- Toolchain: AArch64 Google Android GCC 4.9 prebuilt, mirrored by [LineageOS](https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_aarch64_aarch64-linux-android-4.9/tree/lineage-19.1), pinned in `scripts/build.sh`. The release string is deliberately set to the currently reported `4.9.186-perf-g131f907` for module vermagic compatibility; this string is **not** evidence that source commit `g131f907` is in the public Xiaomi source. The exact stock source revision and module CRCs remain unverified.

The reference [onclite device tree](https://github.com/onclite/android_device_xiaomi_onclite/blob/lineage-22.1/BoardConfig.mk) describes an arm64 `Image.gz-dtb`, 2048-byte kernel page size, boot header v1, separate DTBO, 64 MiB boot partition, and a non-A/B layout. That is corroborating device-tree evidence, **not** a substitute for inspecting this exact MIUI build's original `boot.img`. Accordingly, the installer requires and reuses the DTB extracted from the live image instead of guessing a board DTS from the Qualcomm source tree. The recovery fstab names the `boot` partition separately from `recovery` ([fstab](https://github.com/onclite/android_device_xiaomi_onclite/blob/lineage-22.1/rootdir/etc/fstab.qcom)).

## Prior candidate's intended installer flow — not target-validated

The following describes static code behavior only; the supplied boot image could not be inspected and the candidate must not be flashed.

- Checks the recovery-reported product is exactly `onclite`.
- Resolves and checks a partition whose by-name name is exactly `boot`; checks the live boot image can be unpacked and contains a ramdisk before any write.
- Stages only the built `Image.gz` kernel. For header v0/v1, requires MagiskBoot to extract the live appended DTB as `kernel_dtb`; for header v2, requires the live separate `dtb`. AnyKernel3/MagiskBoot repacks the new kernel with those original live DTB bytes, along with the original ramdisk and recovery-DTBO section. It aborts if the expected DTB cannot be extracted, or for unsupported header versions.
- Uses AnyKernel3/MagiskBoot to repack the **live** boot image. The ZIP contains no prebuilt `boot.img`; it does not request writes to `recovery`, `dtbo`, `vendor_boot`, `vbmeta`, system, or userdata. It does not format or wipe anything.
- Skips ramdisk editing and leaves `PATCH_VBMETA_FLAG=0`. AnyKernel3 detects a Magisk-patched ramdisk and applies its kernel-side Magisk preservation handling. This is an expectation based on the installer code, **not a guarantee** of root preservation; the actual Magisk version and boot image were unavailable for inspection.

The recovery must support the legacy update-binary ZIP format (as current TWRP/OrangeFox builds generally do). Flash it as a **ZIP**, not as an image. This package does not sign the modified boot with Xiaomi's key, patch vbmeta, or disable AVB; use it only where the bootloader/recovery setup already permits a custom boot image. If recovery reports an updater/format error or the installer aborts a preflight check, do not force the flash.

## Build

Run from Linux with Git, Bash, Make, a host C compiler, Python 3, `zip`, gzip, OpenSSL development headers/library, and enough disk/RAM. The script fetches pinned Xiaomi source, the pinned AArch64 GCC 4.9 prebuilt, and pinned AnyKernel3 framework into a temporary directory, builds outside the repository, verifies the ZIP, and removes its temporary work directory. It uses an installed `bc` when available; otherwise it builds pinned bc 7.1.0 in the temporary directory. On modern GCC hosts it passes `-fcommon` for this legacy kernel's generated DTC code. It builds only `Image.gz`, not a guessed DTB: the installer code requires and carries through a DTB extracted from the live boot image, a path not yet verified against the supplied target image. It does not fetch or publish a stock boot image. **The existing script output is not cleared for flashing**; the target image and exact matching source revision must be verified first.

```sh
chmod +x scripts/build.sh
JOBS=2 ./scripts/build.sh
python3 scripts/verify_zip.py Redmi7_onclite_Kernel_Flashable.zip
```

`JOBS` may be adjusted for the build host. To use a locally installed cross compiler, set `CROSS_COMPILE=/path/to/aarch64-linux-android-` (including the trailing dash). The build uses `onclite-perf_defconfig`, sets `LOCALVERSION=-g131f907` and disables automatic Git suffixing solely to keep the reported kernel release aligned with the installed kernel's vermagic. That release label does not verify the source or module CRCs. The actual source commit and build artifacts are recorded separately in [`BUILD_REPORT.md`](BUILD_REPORT.md).

## Pre-flash requirements for a future audited build — not current approval

1. Confirm the phone is a **Redmi 7 / `onclite`**. From Fastboot, `fastboot getvar product` must identify `onclite`; do not use this ZIP on another Xiaomi model.
2. Confirm the installed ROM really is MIUI Global `11.0.2.0(QFLMIXM)` / Android 10. This build is not established for other regions, ROMs, or Android versions.
3. In recovery, make a backup of the current **Boot** partition and copy it off the phone. Separately keep the exact original firmware-matching `boot.img` on a PC and preserve a second copy. Verify the backup file with `sha256sum`; do not overwrite the only copy.
4. Ensure recovery can access the backup and can install AnyKernel3-style update ZIPs. Keep battery charge and a working Fastboot path available.

## Install status

**Do not install the current `Redmi7_onclite_Kernel_Flashable.zip`.** The original image could not be inspected and exact source correspondence is unverified. No corrected ZIP is approved by this audit. Do not bypass the installer checks or flash the candidate as a test.

## Rollback / bootloop

- **Recovery still opens:** do not repeat the flash. Transfer the saved, firmware-matching original `boot.img` to recovery storage/USB-OTG. In TWRP/OrangeFox choose **Install Image**, select that image, choose the **Boot** target (not Recovery or DTBO), and restore it. Alternatively restore the recovery's saved Boot backup.
- **Recovery unavailable, Fastboot works:** enter Fastboot, verify `fastboot getvar product` reports `onclite`, then from the PC run `fastboot flash boot /path/to/original-boot.img`. Do not substitute an image from another region/build, and do not erase userdata or flash other partitions.
- Confirm the original image came from the installed Global `QFLMIXM` firmware/build and has the same device/partition generation. The GitHub Releases API reports the provided asset as 67,108,864 bytes with SHA-256 `cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30`; this was not independently recalculated here. After downloading, run `sha256sum boot.img` and compare before restoring. A stock, unpatched original boot image removes Magisk's boot patch: reapply Magisk using the Magisk app's supported **install to inactive/patch boot image** flow for that exact ROM, then verify root. If the saved boot image was already Magisk-patched, root may remain, but still test it.
- Restoring boot cannot fix every possible failure (for example, a separate damaged partition or unrelated firmware issue). Stop if the product/partition does not match rather than trying guessed commands.

## After a future audited flash — verification checklist

- [ ] **Boot:** reaches the lock screen; test display, touch, storage, charging, Wi-Fi, camera, and other essential functions. If it bootloops, stop repeated attempts and roll back.
- [ ] **Magisk:** open Magisk and inspect its installation/status page. Then use a trusted local terminal and run `su -c id`; approve the prompt and verify it prints `uid=0(root)`. The app icon alone is not proof of root.
- [ ] **Kernel:** run `uname -a` / `uname -r`. The build intentionally keeps `4.9.186-perf-g131f907` as the release string for module vermagic, so that string alone cannot distinguish the new image from stock. Compare `/proc/version` build metadata and test the requested behavior as well.
- [ ] **Module signature:** use only a trusted module built for this exact kernel/config and matching symbols/version. As root, attempt to load it and inspect `su -c 'dmesg | grep -iE "module|signature|verification|key|Unknown symbol|invalid module"'`. `Required key not available`/`Key was rejected` indicates signature enforcement/verification; `invalid module format`, vermagic mismatch, `Unknown symbol`, SELinux denials, and permission errors are different failures. With force enforcement disabled, unsigned modules and signatures lacking a trusted key can pass the policy check but may still be rejected for any of those other reasons. Cryptographically invalid signatures are still rejected by the verifier.

No physical-device or module-load test has been performed by this build. Do not infer boot, root, or signature-test success until you perform these checks and report the results.

## Reports and deliverables

- [`BUILD_REPORT.md`](BUILD_REPORT.md): source/toolchain/config/build and verification record.
- [`ZIP_MANIFEST.md`](ZIP_MANIFEST.md): concise archive contents.
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md): AnyKernel3 and included utility notices.
- Prior static candidate (**NOT FLASH-READY; do not install**): [`Redmi7_onclite_Kernel_Flashable.zip`](Redmi7_onclite_Kernel_Flashable.zip).
