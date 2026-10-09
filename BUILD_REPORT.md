# Build and static verification report

**Run date:** 2026-10-09 (UTC)
**Target requested:** Xiaomi Redmi 7 (`onclite`), MIUI Global `11.0.2.0(QFLMIXM)`, Android 10, reported stock kernel `4.9.186-perf-g131f907`.

## Result

A kernel was compiled and packaged as [`Redmi7_onclite_Kernel_Flashable.zip`](Redmi7_onclite_Kernel_Flashable.zip). The source/build script and archive passed host-side structural checks. **This is not a device-tested release:** no matching original `boot.img`, physical phone, or recovery test image was available here.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `payload/Image.gz` | 10,748,052 bytes | `b53cef1c92fa65e1f5f69093760f79ed49e4475e2a3a2551c0e7474f53bc7625` |
| `Redmi7_onclite_Kernel_Flashable.zip` | 11,975,575 bytes | `58df6f662cce96d1106e406ecad30dc757027619ceb363d9d5fcd1ec013ae79f` |

The decompressed kernel has the arm64 Linux `Image` magic (`ARM\x64` at offset 56). `make kernelrelease` returned **`4.9.186-perf-g131f907`**. That deliberately matches the reported release label; it does **not** prove that the source matches the installed MIUI kernel or that its module CRCs/ABI are identical.

## Source, config, and toolchain

- **Candidate Xiaomi source:** [`MiCode/Xiaomi_Kernel_OpenSource`, branch `onc-q-oss`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/onc-q-oss), pinned at [`fa577bc566886db1e0dfb1ddf66ff7c528148b2b`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/commit/fa577bc566886db1e0dfb1ddf66ff7c528148b2b). Its tree is Linux 4.9.186 and contains `onclite-perf_defconfig`; that is the config used here.
- **Unresolved source correspondence:** a public lookup for commit prefix `131f907` found no matching Xiaomi commit. The source above is a relevant official candidate, but the exact source revision used for the installed `g131f907` kernel is unverified. No stock image was available to compare its embedded config, DTB, or module ABI.
- **Change:** [`patches/0001-onclite-disable-module-signature-enforcement.patch`](patches/0001-onclite-disable-module-signature-enforcement.patch) changes only `CONFIG_MODULE_SIG_FORCE=y` to unset in `onclite-perf_defconfig`.
- **Final config checks:** `CONFIG_MODULES=y`, `CONFIG_MODVERSIONS=y`, `CONFIG_MODULE_SIG=y`, `CONFIG_MODULE_SIG_SHA512=y`, and `# CONFIG_MODULE_SIG_FORCE is not set`. Automatic local versioning is disabled and `LOCALVERSION=-g131f907` is supplied, while the config retains `CONFIG_LOCALVERSION="-perf"`.
- **Module-signature behavior from this source:** `module_sig_check()` ignores `-ENOKEY` when `sig_enforce` is false. Thus unsigned modules and signatures without a trusted key may pass that policy check and taint the kernel. Cryptographically invalid signatures and malformed signatures still fail verification; architecture, symbol/version, and other module checks are unchanged. With `CONFIG_MODULE_SIG_FORCE` unset, the `module.sig_enforce` runtime parameter remains available. No module was loaded on a device.
- **Cross toolchain:** LineageOS mirror of Android AArch64 GCC 4.9, branch `lineage-19.1`, pinned commit [`5e030eafe024784a73cdf47e6936ac0dbfc763dc`](https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_aarch64_aarch64-linux-android-4.9/tree/lineage-19.1); compiler identifies as `GCC 4.9.x 20150123 (prerelease)`. Exact equivalence to Xiaomi's MIUI build toolchain is not established.
- **Installer framework:** AnyKernel3 pinned at [`020dfeccf9d7e962a48400fc94d3e451df92eead`](https://github.com/osm0sis/AnyKernel3/commit/020dfeccf9d7e962a48400fc94d3e451df92eead).

## Build record

The pinned source, compiler, and AnyKernel3 checkouts were validated by `scripts/build.sh`; the script performed the build and ZIP packaging with `JOBS=2`. To reuse the already-fetched, hash-checked temporary checkouts and incremental output tree, this run supplied `KERNEL_SOURCE_DIR`, `CROSS_COMPILE`, `ANYKERNEL3_DIR`, and `KERNEL_OUT` overrides. A default run fetches the pinned dependencies itself. The host was Debian 12 x86_64 with GCC 12.2.0, GNU Make 4.3, and OpenSSL 3.0.20. Host-side compatibility workarounds were limited to `-fcommon` for legacy generated DTC code, the available Node/OpenSSL headers plus the OpenSSL 3 `libcrypto` runtime for kernel host helpers, and a temporary pinned `bc` 7.1.0 build (commit `70c51d95e02d20fc3fc82791dc3f1aa0e9d47f0d`). None of those host tools are shipped in the ZIP.

The effective kernel build steps were `onclite-perf_defconfig`, `olddefconfig`, and `make Image.gz`. An initial broad `make dtbs` attempt failed on unresolved `typec_ssmux_config` references in unrelated APQ8053 Lite Dragon development-board DTS files. Those DTBs are not included in the final package. Because the target's exact live DTB could not be inspected, the safer package contains **only the new compressed kernel** and requires AnyKernel3/MagiskBoot to extract and preserve the original DTB from the phone's live boot image. The final build therefore does not guess or append a generic Qualcomm DTS.

## Image layout and install scope

A current onclite device-tree reference ([BoardConfig.mk](https://github.com/onclite/android_device_xiaomi_onclite/blob/lineage-22.1/BoardConfig.mk), [recovery fstab](https://github.com/onclite/android_device_xiaomi_onclite/blob/lineage-22.1/rootdir/etc/fstab.qcom)) reports `Image.gz-dtb`, 2048-byte pages, boot header v1, a separate DTBO, a non-A/B layout, a 64 MiB boot partition, and distinct by-name `boot` and `recovery` entries. This is corroborating reference-tree evidence only; it is not direct verification of MIUI Global `11.0.2.0(QFLMIXM)`.

The installer checks the recovery-reported product is exactly `onclite`, resolves `BLOCK=boot` with `IS_SLOT_DEVICE=0`, unpacks the live image before any write, and requires a ramdisk. For headers v0/v1 it requires MagiskBoot's extracted `kernel_dtb`; for header v2 it requires the separate `dtb`. It selects `payload/Image.gz` and lets AnyKernel3/MagiskBoot repack the live image with the existing DTB, ramdisk, and recovery-DTBO component. It aborts on unsupported headers or missing components. Static inspection of the included MagiskBoot binary confirms it lists `kernel_dtb`, `dtb`, and `recovery_dtbo` components and documents splitting/repacking `Image.*-dtb` images.

The installer requests writing only the by-name `boot` partition. It contains no stock `boot.img`, DTBO, recovery, vendor_boot, vbmeta, modules, or userdata operation; it sets `PATCH_VBMETA_FLAG=0` and does not re-sign with Xiaomi's signing key. The bootloader/recovery must already permit a custom boot image. Magisk ramdisk content is not intentionally edited, and AnyKernel3 has Magisk-detection handling, but root preservation is not guaranteed without a real target image and device test.

## Verification performed

- `bash -n scripts/build.sh installer/anykernel.sh` — passed.
- `python3 -m py_compile scripts/verify_zip.py` — passed.
- `git diff --check` and source patch apply/reverse-apply checks — passed.
- `scripts/build.sh` kernel release/config guards — passed; `Image.gz` gzip stream and arm64 header checks — passed.
- `python3 scripts/verify_zip.py Redmi7_onclite_Kernel_Flashable.zip` — passed: 10 entries, clean CRCs, safe archive paths, exact single kernel payload, onclite-only installer guards, no extra partition images, shell syntax checks, and required live-DTB guards.
- `unzip -t Redmi7_onclite_Kernel_Flashable.zip` — passed with no compressed-data errors.
- SHA-256 of `unzip -p ... payload/Image.gz` matches the built `Image.gz` hash above.

## Limitations / required user checks

There has been **no recovery execution, flash, boot, Magisk/root-preservation test, AVB test, or module-load test on physical hardware**. The exact installed boot header, page size, ramdisk, DTB, AVB state, source revision, and module ABI remain unverified. The matching original firmware boot image must be backed up and verified by the device owner before any installation; use only on Redmi 7 `onclite` running the stated MIUI build, and follow the rollback instructions in [`README.md`](README.md). Do not treat the matching kernel release string as proof of source or ABI compatibility.
