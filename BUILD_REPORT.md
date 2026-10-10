# Build and original boot-image audit report

## Decision

**BLOCKED — DO NOT FLASH `Redmi7_onclite_Kernel_Flashable.zip`.** The supplied original boot image and Drive `dtbo.img`/`vbmeta.img` were audited. The zero-ramdisk header means the unchanged installer aborts before writing; the signed external vbmeta covers the original boot bytes; exact stock source/module ABI and live bootloader enforcement remain unresolved. A separate, config-corrected **kernel-only diagnostic build** was completed from pinned Xiaomi `onc-q-oss` using `onc-perf_defconfig`; it did not create or alter any ZIP. The generated config differs from the embedded stock config only at `CONFIG_MODULE_SIG_FORCE` among supported symbols, while `CONFIG_KTRACE` and `CONFIG_RTMM` remain unsupported by the pinned public source. See [`reports/diagnostic-kernel-build.md`](reports/diagnostic-kernel-build.md) for commands, hashes, config deltas, and static image/FDT checks. The 926 MB `vendor.img` could not be downloaded under the Drive connector's 100 MB limit. No flash or phone test occurred.

## Diagnostic kernel-only build summary

- Source: Xiaomi `onc-q-oss` commit `fa577bc566886db1e0dfb1ddf66ff7c528148b2b`; `onc-perf_defconfig`; Android AArch64 GCC 4.9 toolchain pinned at `5e030eafe024784a73cdf47e6936ac0dbfc763dc`.
- Output: `build-artifacts/onclite-kernel-only-stock-config/Image.gz`, 11,050,592 bytes, SHA-256 `e177c6841bc8150d9488b2fc80127c91b169a15f19be47d9467747d3a8af54d5`; release `4.9.186-perf-gfa577bc5-dirty`, which differs from stock `g131f907`.
- The generated `.config` matches all stock values supported by the pinned source except the intended force-signature change; stock-only `CONFIG_KTRACE`/`CONFIG_RTMM` have no Kconfig declarations in that source. This is not exact source/module-ABI proof.
- Image architecture, gzip stream, embedded release/config, and a byte-identical append of the original 17-FDT tail were statically checked with [`scripts/validate_kernel_artifact.py`](scripts/validate_kernel_artifact.py); output is in [`reports/kernel-component-validation.txt`](reports/kernel-component-validation.txt). This is not a boot-image repack or boot test.
- No module build/load, AnyKernel repack, test ZIP, recovery run, flash, or phone test occurred. The ZIP remains unchanged.

## Original image provenance and backup

The repository's `main` branch tree identified `boot.zip` (11,876,677 bytes; Git blob SHA-1 `0a622bee5ba9466344961715cc302e7c2accd7db`; tree SHA-1 `d89f4f11a46db6ae8737890c40d0dc8be5b6f74a`). The archive was fetched through GitHub's codeload route without changing this working branch. Its ZIP integrity test passed; its only member is `boot.img`. The extracted image was checked against the GitHub Releases API asset digest.

| Item | Result |
|---|---|
| Local backup | `backups/original/boot.img` |
| Size | 67,108,864 bytes |
| SHA-256 | `cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30` |
| Git status | Ignored by root `.gitignore`; not tracked, not committed, not included in the candidate ZIP |

This is a byte-for-byte local original. Preserve it unmodified and separately; it is not part of any public deliverable.

## Header and image layout

The image has `ANDROID!` magic and a legacy boot header v1:

| Component/field | Value |
|---|---:|
| Page size / header size | 2,048 / 1,648 bytes |
| Kernel size | 15,214,803 bytes |
| Ramdisk size | **0 bytes** |
| Second-stage size | 0 bytes |
| Embedded recovery-DTBO size | 0 bytes |
| Full image/partition dump size | 67,108,864 bytes |
| AVB footer | Present at offset 67,108,800 |

Header v1 has no separate v2 DTB-size field. The kernel component consists of an 11,071,842-byte gzip member followed by 4,142,961 bytes of concatenated FDT blobs. The gzip member expands to a 28,606,976-byte arm64 Linux `Image`. The FDT tail has 17 structurally valid trees; its roots include Qualcomm APQ8016, MSM8953, SDM450, and SDM632/PMI632 reference models. This does not establish which board tree is selected at boot. The separately supplied Drive `dtbo.img` is inspected below; its entries also do not establish the selected onclite overlay.

The boot command line includes `androidboot.hardware=qcom`, `androidboot.bootdevice=7824900.sdhci`, and `buildvariant=user`; these are not sufficient to prove device codename or exact ROM. The image's AVB properties report Android `10` and security patch `2021-03-01`, but do not establish the requested MIUI Global build `11.0.2.0(QFLMIXM)`.

Kernel identity from the original image:

```text
Linux version 4.9.186-perf-g131f907 (builder@c5-miui-ota-bd18.bj)
(gcc version 4.9.x 20150123 (prerelease) (GCC) )
#1 SMP PREEMPT Tue Mar 9 23:13:57 WIB 2021
```

The release string is real evidence of the reported stock kernel release, not proof that a public source commit, config, toolchain binary, or module ABI is identical.

## Google Drive supplemental images

The user supplied four files under My Drive `kernel`. Drive lists all as generic `application/octet-stream` and reports the hashes/sizes below. Three were downloaded into the Git-ignored `google_drive/` directory; locally computed hashes match Drive metadata. `google_drive/boot.img` is byte-identical to `backups/original/boot.img`. The full inventory and parsing record are in [`reports/google-drive-image-audit.md`](reports/google-drive-image-audit.md).

| File | Size | Content established |
|---|---:|---|
| `boot.img` | 67,108,864 bytes | `ANDROID!` header v1; exact previously audited boot. |
| `dtbo.img` | 8,388,608 bytes | Android DT-table v0, 17 FDT entries, 2048-byte page; AVB footer. Table IDs/revisions/custom fields are zero; entry roots include Qualcomm reference models and `onc_*` camera strings, but do not identify the phone or selected overlay. |
| `vbmeta.img` | 4,096 bytes | AVB0 top-level metadata, `SHA256_RSA2048`, embedded public-key SHA-1 fingerprint `b2a02f1e56e366d727a1a8e089762fe0b91bbc84`, rollback index/flags zero. |
| `vendor.img` | 926,327,184 bytes | Not downloaded or parsed: exceeds the connector's 100 MB maximum. Only Drive size and hash metadata were available. |

The signed vbmeta has boot and DTBO hash descriptors that match and verify against the supplied original images. It also references a missing recovery image and system/vendor hashtrees. `avbtool verify_image` verifies the vbmeta signature plus boot/DTBO hashes, then exits non-zero at missing `recovery.img`; it is not a complete descriptor verification. The vendor hashtree descriptor expects a logical image size of 1,056,714,752 bytes; the smaller Drive object could be sparse, but its format cannot be established without downloading it. No `.ko` files, module metadata, vendor build fingerprint, or `Module.symvers` could be read.

## Embedded configuration, candidate source, and module ABI

The stock kernel contains `IKCONFIG`; the extracted config has 5,009 lines and SHA-256 `db5eafdaab4c5d2739f74291e49971a6baf06ca1c196261ada7ca531dbb28bb3`. Relevant stock settings are:

```text
CONFIG_LOCALVERSION="-perf"
CONFIG_LOCALVERSION_AUTO=y
CONFIG_MODULES=y
CONFIG_MODVERSIONS=y
CONFIG_MODULE_SIG=y
CONFIG_MODULE_SIG_FORCE=y
CONFIG_MODULE_SIG_SHA512=y
CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE=y
```

The existing ZIP's historical candidate used Xiaomi source [`onc-q-oss`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/onc-q-oss), pinned to [`fa577bc566886db1e0dfb1ddf66ff7c528148b2b`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/commit/fa577bc566886db1e0dfb1ddf66ff7c528148b2b), with `arch/arm64/configs/onclite-perf_defconfig`. This is a relevant official source candidate, but the exact source revision used to build stock `g131f907` remains unresolved. A separate diagnostic build now uses `onc-perf_defconfig`; it is not the ZIP payload.

The embedded stock `.config` was compared with the two defconfig files at that pinned commit:

| Reference config | Entries | Values matching the embedded stock config | Missing in embedded config | Value mismatches |
|---|---:|---:|---:|---:|
| `onclite-perf_defconfig` (used by candidate) | 680 | 663 | 11 | 6 |
| `onc-perf_defconfig` | 698 | 692 | 6 | 0 |

For `onclite-perf_defconfig`, the mismatched values are `CONFIG_CORESIGHT`, `CONFIG_MEMBARRIER`, `CONFIG_MSM_SMD_DEBUG`, `CONFIG_NETFILTER_XT_MATCH_SCTP`, `CONFIG_PM_AUTOSLEEP`, and `CONFIG_POWER_RESET_SYSCON`. The machine-readable lists are in [`reports/onclite-boot-audit.json`](reports/onclite-boot-audit.json). This comparison is a source/configuration discrepancy, **not** proof that this boot image is from Redmi Y3 (`onc`): a defconfig filename does not identify the hardware, and the exact stock source/Kconfig revision is not known. A separate LineageOS onclite reference tree has used `onc-perf_defconfig`, which is corroborating reference evidence only, not proof of MIUI's build configuration.

The existing ZIP payload's earlier build intentionally changes `CONFIG_MODULE_SIG_FORCE=y` to unset, disables `CONFIG_LOCALVERSION_AUTO`, and supplies `LOCALVERSION=-g131f907` even though stock has `CONFIG_LOCALVERSION_AUTO=y`. That manually retained release label is not proof of source or ABI equivalence. The current one-line patch instead targets `onc-perf_defconfig`; its diagnostic build keeps `CONFIG_LOCALVERSION_AUTO=y` and reports its actual source-derived suffix. Disabling enforcement changes the stock signature policy: unsigned modules or modules without a trusted signing key may pass that policy check and taint the kernel; cryptographically invalid signatures and other module failures remain possible. This is not evidence that arbitrary modules will load.

`CONFIG_MODVERSIONS=y` makes matching `uname -r` or vermagic insufficient for module compatibility. Drive contains a 926,327,184-byte `vendor.img`, above the connector's 100 MB download limit, so its modules and any `modules.*` metadata could not be read. No firmware-matched `.ko` files or `Module.symvers` are available for comparison. No device module-load test was performed.

The candidate was built with the pinned LineageOS mirror of Android AArch64 GCC 4.9 (`lineage-19.1`, commit `5e030eafe024784a73cdf47e6936ac0dbfc763dc`), whose compiler version text is `GCC 4.9.x 20150123 (prerelease)`. This text agrees with the stock kernel's printed compiler version, but does not prove identical compiler binaries, build flags, source tree, or output. The candidate's release suffix was set to `-g131f907`; that setting preserves a label, not the missing source identity or ABI evidence.

## AVB

The supplied `boot.img` and `dtbo.img` each have an AVB v1.0 footer with `Algorithm: NONE` and empty authentication blocks. Their internal SHA-256 descriptors verify against their original bytes, but neither embedded vbmeta is cryptographically signed by itself.

The separate Drive `vbmeta.img` is a signed AVB0 image using `SHA256_RSA2048` (authentication block 320 bytes, auxiliary block 2,816 bytes, rollback index 0, flags 0). `avbtool verify_image` verified the signature against its embedded public key (SHA-1 fingerprint `b2a02f1e56e366d727a1a8e089762fe0b91bbc84`), then verified the original boot and DTBO hashes. The boot descriptor covers 15,218,688 bytes and matches the hash in the boot footer. The DTBO descriptor covers 955,953 bytes and matches the DTBO footer. This confirms consistency among the three supplied images under the key embedded in vbmeta.

The same signed vbmeta describes a 27,971,584-byte recovery image, plus system/vendor dm-verity hashtrees, and contains Android 10 / `2021-03-01` properties and conditional verity kernel-command-line descriptors. The recovery, system, and vendor contents were not all available. Full `verify_image` therefore exits non-zero at the first missing `recovery.img`, after verifying the vbmeta signature and boot/DTBO hashes; it did not verify system/vendor hashtrees. The vendor descriptor expects a 1,056,714,752-byte logical image, but the Drive object is smaller and inaccessible at this connector size; sparse format is possible but unconfirmed.

This validates the signature against the vbmeta's own embedded public key, **not** that a device bootloader trusts that key or is currently enforcing AVB. Device rollback state and live vbmeta are also unknown. If the supplied signed vbmeta is enforced unchanged, replacing the kernel while writing only boot leaves its signed boot hash descriptor stale, so the candidate will not satisfy that descriptor. The existing installer does not write/re-sign vbmeta and leaves `PATCH_VBMETA_FLAG=0`; this audit did not modify AVB metadata or disable verification. Full tool output is in [`reports/google-drive-avb-verification.txt`](reports/google-drive-avb-verification.txt); the original boot-footer transcript remains in [`reports/avb-original-boot.txt`](reports/avb-original-boot.txt).

## Magisk/root state and installer behavior

The original header has a zero-byte ramdisk, so there is no ramdisk cpio to inspect for Magisk markers. The image contains no obvious `magisk`, `Magisk`, `SUPERSU`, `init.magisk`, or `.magisk` strings, but this cannot prove the device is unrooted. Magisk may be installed through another partition/image or a different live state. The recovery image and device state were not supplied. No root-preservation claim is supportable from this boot image.

The existing installer checks for a non-empty extracted ramdisk and aborts with `Expected boot ramdisk is missing. Refusing to replace boot.` before `flash_boot`. Since the audited image's `ramdisk_size` is zero, the candidate will fail that preflight if given this image; it should not write the boot partition. The guard was not removed: allowing installation without knowing how this device holds Magisk or handles AVB would be unsafe. The package's code leaves `PATCH_VBMETA_FLAG=0`, but that alone does not guarantee AVB acceptance or root preservation.

## Candidate archive and kernel comparison

The ZIP is unchanged from the prior static candidate:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `payload/Image.gz` | 10,748,052 bytes | `b53cef1c92fa65e1f5f69093760f79ed49e4475e2a3a2551c0e7474f53bc7625` |
| Candidate decompressed `Image` | 28,570,112 bytes | `7b5ff7fe1ea19b531cd8bbae13077478644b488d560a1879dd48fff4f40bf816` |
| Original decompressed `Image` | 28,606,976 bytes | `95abdb1e2b2e8768ce251549195f422e5798b918ef4fbe965c5b6ccf07820ce9` |
| `Redmi7_onclite_Kernel_Flashable.zip` | 11,975,575 bytes | `58df6f662cce96d1106e406ecad30dc757027619ceb363d9d5fcd1ec013ae79f` |

The candidate and original report the same `4.9.186-perf-g131f907` release string, but their uncompressed kernels are not byte-identical: 21,595,768 bytes differ in the 28,570,112-byte common range; first difference is at offset 17. The difference alone cannot identify the cause, but the matching release string cannot be used as proof of source or ABI compatibility.

The archive carries only the new kernel payload and AnyKernel3 tools; it contains no original boot image, ramdisk, DTB/DTBO, recovery, vendor_boot, vbmeta, or modules. It passed the prior archive integrity and static guard checks. No recovery execution, flash, physical boot, AVB, Magisk, or module-load test occurred.

## Existing ZIP's historical build record

- Source: Xiaomi `onc-q-oss` at `fa577bc566886db1e0dfb1ddf66ff7c528148b2b`; build config `onclite-perf_defconfig`.
- AnyKernel3: pinned at `020dfeccf9d7e962a48400fc94d3e451df92eead`.
- bc fallback: pinned at `70c51d95e02d20fc3fc82791dc3f1aa0e9d47f0d`.
- Host at build time: Debian 12 x86_64, GCC 12.2.0, GNU Make 4.3, OpenSSL 3.0.20; build used `JOBS=2`.
- Effective kernel steps were `onclite-perf_defconfig`, `olddefconfig`, and `make Image.gz`. A broad `make dtbs` attempt failed on unresolved `typec_ssmux_config` references in unrelated APQ8053 Lite Dragon DTS files; no guessed generic DTB was packaged. The installer was designed to require a DTB extracted from the live boot image.
- Host-side compatibility adjustments included `-fcommon` for legacy generated DTC code, available Node/OpenSSL headers plus OpenSSL 3 `libcrypto` for host helpers, and a temporary pinned bc 7.1.0 build. None are shipped in the ZIP.
- Static archive checks previously included `bash -n`, ZIP CRC/path/payload checks, candidate gzip/arm64 checks, build release/config guards, and source patch apply/reverse-apply checks.

These records establish how the prior candidate was built and statically inspected; they do not approve it for the supplied image.

## Verification performed for this audit

- Repository `boot.zip`: ZIP integrity check passed; inner archive lists only `boot.img`.
- Drive `kernel` folder: exactly four image files listed. The downloaded `boot.img`, `dtbo.img`, and `vbmeta.img` local hashes match Drive metadata; the Drive boot also matches `backups/original/boot.img`. The 926 MB `vendor.img` was not downloaded because the connector caps regular-file downloads at 100 MB.
- `backups/original/boot.img`: SHA-256 recalculated; matches the GitHub release metadata digest. Original backup is ignored by Git.
- `python3 scripts/inspect_boot.py backups/original/boot.img`: boot header, gzip kernel, embedded config, appended FDTs, AVB footer, and no-ramdisk status parsed; JSON saved in `reports/onclite-boot-audit.json`.
- Defconfig value comparison against `onclite-perf_defconfig` and `onc-perf_defconfig` at the pinned Xiaomi commit recorded in the JSON report.
- `avbtool.py info_image`/`verify_image`: embedded boot and DTBO `NONE` footers and hashes verify; external `vbmeta.img` RSA signature and supplied boot/DTBO hashes verify. Full vbmeta verification stops at missing `recovery.img`; system/vendor hashtrees remain unverified. Transcript saved in `reports/google-drive-avb-verification.txt` and the boot-only transcript in `reports/avb-original-boot.txt`.
- Candidate payload decompressed and compared against the original gzip kernel output; matching release string and substantial binary differences recorded above.
- New diagnostic build: `CONFIG_ONLY=1 ARTIFACT_DIR=/tmp/onclite-config-only-check bash scripts/build.sh` passed the stock-config gate before the corrected build; `bash scripts/build.sh` built only `Image.gz`. Full command/compiler/config/hash details and the separate FDT static check are saved in [`reports/diagnostic-kernel-build.md`](reports/diagnostic-kernel-build.md). The output is Git-ignored and is not a ZIP.
- `scripts/verify_zip.py` static mode passes with an explicit **not flash approval** label. Target-aware mode with `--target-image backups/original/boot.img` reports **BLOCKED** and intentionally exits with status 1 due to `ramdisk_size=0`; the exact output/statuses are saved in [`reports/zip-verification.txt`](reports/zip-verification.txt).
- No physical-device, recovery, flashing, AVB enforcement, root, or module-load test occurred.

## Limitations and next evidence required

The exact stock source commit/config generation remains unresolved; the boot header and generic DTBO entries do not identify the physical device or selected overlay; the vendor module set could not be downloaded; no ramdisk exists in this image to establish Magisk state; and no matching `Module.symvers` is available. The signed vbmeta and boot/DTBO hashes are internally consistent, but the bootloader's trust/enforcement state is unknown and recovery/system/vendor data prevented full AVB descriptor verification. Do not flash or bypass the ramdisk guard. A future release needs confirmed target/ROM identity, resolved source/config and module ABI, the actual zero-ramdisk/Magisk arrangement, and a safe AVB acceptance plan. No phone test occurred and the candidate ZIP was not modified.
