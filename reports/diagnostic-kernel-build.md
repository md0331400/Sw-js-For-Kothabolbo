# Redmi 7 `onclite` diagnostic kernel and experimental test ZIP

**Artifact outcome: TEST ZIP READY; installation-readiness verdict: BLOCKED.** A separate host-built test package exists at `build-artifacts/onclite-experimental-test.zip` (SHA-256 `b742792c92b1f9135858dcddc6e12743781ee33da54fda3d04e905a5adea3462`; 12,830,146 bytes). “Ready” means its inputs, installer logic on file-backed host fixtures, package contents, and ZIP integrity passed the checks below. **It has not run in Android recovery or on a phone; boot/AVB acceptance is unknown.** The existing `Redmi7_onclite_Kernel_Flashable.zip` remains unchanged (SHA-256 `58df6f662cce96d1106e406ecad30dc757027619ceb363d9d5fcd1ec013ae79f`). No original image or backup is included in the test ZIP or added to Git.

## Rebuilt-kernel hash mismatch

| Artifact | Size | SHA-256 |
|---|---:|---|
| Previously recorded `Image.gz` | 11,050,592 bytes | `e177c6841bc8150d9488b2fc80127c91b169a15f19be47d9467747d3a8af54d5` |
| Pinned rebuild `Image.gz` | 11,050,600 bytes | `255b8cf621055cc1ff48d256204f8690a6c9892047a40d0cb9cb2c838c23eb96` |
| Previously recorded decompressed `Image` | 28,602,880 bytes | `3fa6e7c8c4cedea1dbab75750fba32d4c824b01ae83119191725efb9fa3d698e` |
| Rebuilt decompressed `Image` | 28,602,880 bytes | `6920a3f055bc2fc02b31652c37d2b886d63eba3aa47f95052f4a4aea848052dc` |

The previous `Image.gz` binary is unavailable, so the changed byte offsets/content cannot be compared. The rebuilt file is 8 bytes larger; the uncompressed images have equal sizes but different hashes. The rebuild used the recorded pinned public Xiaomi source (`onc-q-oss`, commit `fa577bc566886db1e0dfb1ddf66ff7c528148b2b`), pinned GCC 4.9 toolchain, and validated config (SHA-256 `f3d8d3b08369b0c433e6e7106447df4176df010659537d50652a60f50547660e`). The rebuild embeds timestamp `Sat Oct 10 07:45:09 UTC 2026`; changed build-time metadata is a plausible explanation, not a proven cause. The rebuilt release is `4.9.186-perf-gfa577bc5-dirty`, not the stock-reported `4.9.186-perf-g131f907`; no authoritative source revision matching `g131f907` was found, and the label was not forced.

The strict repacker accepts only the prior recorded kernel hash or this exact pinned rebuild and records which artifact was used; it does not call the rebuild an exact match. `scripts/repack_onclite_boot.py` plus `tests/test_repack_onclite_boot.py` preserve that gate. Earlier records also note stock-only `CONFIG_KTRACE` and `CONFIG_RTMM` are unavailable in the pinned public source, while `CONFIG_MODULE_SIG_FORCE` is intentionally disabled. These facts keep the kernel experimental; exact MIUI source/config equivalence, module compatibility, root behavior, and runtime behavior are unestablished.

## Static image and AVB findings

- Original boot: `google_drive/boot.img`, 67,108,864 bytes, SHA-256 `cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30`.
- Static candidate packaged in the test ZIP at `payload/boot.img`: 67,108,864 bytes, SHA-256 `684d5f2f29ee0dfeb9519a007be99594a8ba9af7c57c1734dec3b0fc06a0495c`. Its redundant standalone copy was removed during cleanup.
- Parsed layout: Android boot header v1, 2,048-byte page, kernel at offset 2,048, zero ramdisk and second component, and 17 appended FDT blobs retained byte-identically (tail SHA-256 `4a5fd265b67b34a535b3bda15bb88568948d80154da15eab1dfaf7cc70268ca5`). Structural validation passed; this is not bootability evidence.
- Original footer/VBMeta/suffix bytes were preserved, but that does not refresh their digest. The stock external boot descriptor digest is `3193f936e928c7780bfecbd4d8f573619c04bea20e997c5c9461c291122be250`; the candidate body digest is `81114a6048abd5c3e970134fe482204dcc201c7b36b24286e08dfec989844415`. They **mismatch**. No AVB metadata was disabled, re-signed, or written.
- Generic AVB references describe potentially non-fatal verification errors in unlocked mode. The user reports the bootloader is **UNLOCKED**, which is the working premise, but it was not independently measured. The active `vbmeta`, trusted key, rollback state, device-specific unlocked-mode policy, warning/refusal behavior, and acceptance of this candidate remain unknown. Generic AVB behavior is not proof that this Redmi accepts it. See the generic [AVB README](https://github.com/AndroidBootloader/platform_external_avb/blob/master/README.md) and [VBMeta flag definitions](https://github.com/AndroidBootloader/platform_external_avb/blob/master/libavb/avb_vbmeta_image.h#L51-L62).

## Separate installer and host validation

The existing AnyKernel installer still rejects the original zero-ramdisk image; that guard was not edited or bypassed. The separate test ZIP uses a small prebuilt-image recovery bootstrap and `installer/prebuilt_boot_lib.sh`. It writes only `boot`, never `vbmeta`, and fails closed unless recovery identifies `onclite` (rejects `onc`), reports no unexpected A/B slot, resolves an unambiguous boot block exactly 67,108,864 bytes long, verifies the candidate hash, and finds the current boot partition to have the exact original SHA-256 above. It requires block-backed persistent `/data` for staging, roughly 128 MiB free for the staged candidate plus backup, and writable `/data/media/0`; before writing, it saves and verifies `/data/media/0/onclite-kernel-experimental-original-boot.img`. A mismatched existing backup is never overwritten. Boot read-back is hashed; on write/read-back failure it attempts to restore the verified backup and verifies that read-back. If restoration cannot be verified, remain in recovery and preserve the backup. A sudden power loss or recovery/runtime failure can still prevent automatic rollback.

Checks completed:

- `python3 -m unittest discover -s tests -v`: **16 tests passed under both Bash and dash** (10 repacker-format tests plus 6 synthetic file-backed installer tests, including missing-backup refusal and partial-write restore).
- `python3 scripts/host_validate_experimental_installer.py` ran under both Bash and dash: actual 64 MiB original/candidate artifacts were exercised against temporary regular-file targets; backup SHA matched the original and read-back SHA matched the candidate. This is not a block-device, recovery, or phone test.
- `bash -n` and `dash -n` passed for the recovery bootstrap, flash wrapper, and shared helper.
- The ZIP builder pinned the unchanged existing ZIP and the exact stock/kernel/candidate hashes; the resulting archive passed `ZipFile.testzip()`, entry/path checks, and candidate/BusyBox SHA checks. It contains the candidate, test installer, BusyBox/license, disclosures, and diagnostic records; it does not contain the original boot image, `vbmeta`, MagiskBoot, or modules. `TEST_ZIP_MANIFEST.txt` is included.

Before any future physical test, a compatible custom recovery must accept the unsigned legacy shell update-binary, provide `unzip`/`getprop` and the boot block node, run the packaged BusyBox applets, have persistent/decrypted `/data` with about 128 MiB free and writable `/data/media/0`, and preserve a reliable recovery/bootloader restore path. Keep an independent copy of the original image. Do not relock the bootloader. The candidate may be refused or fail to boot; no physical-device or recovery installation test was performed, and no guarantee of boot, root, or module behavior is made.

## Evidence files

- `reports/onclite-experimental-repack.txt` — actual-image repack and AVB digest results.
- `reports/onclite-experimental-boot-audit.json` — candidate component/layout audit.
- `reports/kernel-component-rebuild-validation.txt` — rebuilt kernel/FDT component validation.
- `reports/diagnostic-kernel-build-metadata.txt` and `reports/kernel-component-rebuild-validation.txt` — pinned rebuild identity and artifact validation.
- `tests/test_prebuilt_boot_installer.py` and `scripts/host_validate_experimental_installer.py` — file-backed installer validation.
- `scripts/build_onclite_experimental_zip.py` — fail-closed separate ZIP builder; refuses to overwrite an existing output and checks the existing ZIP hash before extracting its BusyBox/license.
