# My Drive/kernel image audit

**Decision: the existing candidate remains blocked; do not flash it.** Three files were downloaded through the connected Drive integration and inspected. The fourth, `vendor.img`, exceeds the connector's 100 MB download ceiling and was not downloaded or treated as inspected. No original was changed or deleted, no device commands were run, and the candidate ZIP was not rebuilt or replaced.

The staged, unmodified copies are in the Git-ignored `google_drive/` directory. The Drive-reported SHA-256 values for the three downloaded files match locally computed hashes. `google_drive/boot.img` also matches the separately retained `backups/original/boot.img` exactly.

## Folder inventory

All four Drive objects are reported as `application/octet-stream`; this is generic MIME metadata, not their actual format. Actual formats below are identified from bytes where downloaded.

| Filename | Drive size | SHA-256 | Actual format / purpose established |
|---|---:|---|---|
| `boot.img` | 67,108,864 bytes | `cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30` (computed; matches Drive metadata and existing backup) | `ANDROID!` boot header v1; 64 MiB boot-partition image with gzip arm64 kernel plus 17 appended FDTs, zero-byte ramdisk, and AVB footer. |
| `dtbo.img` | 8,388,608 bytes | `1e79f11f31f05de260ce3a82f21614f6f2cdf32f1bc9eb8f00631a835f710254` (computed; matches Drive metadata) | Android DT table magic `0xd7b7ab1e`; 17 FDT overlay entries and an AVB footer. Intended DTBO partition image; actual table/entries were parsed. |
| `vbmeta.img` | 4,096 bytes | `ae4f46a2c9e54c9d6ad34daf6f347901c579c16e5cb9e2e92a7918518980f0a1` (computed; matches Drive metadata) | AVB `AVB0` metadata image. It is signed `SHA256_RSA2048` and contains hash descriptors for boot, DTBO and recovery, plus system/vendor hashtree descriptors and kernel command-line/properties. |
| `vendor.img` | 926,327,184 bytes (~883.4 MiB) | `082aa5131749730094c867b8778070fc67ea9e22a2369ad95707cb23d2af7d8b` (Drive metadata only; not locally checked) | Not byte-inspected. Drive reports generic binary MIME. The signed vbmeta has a `vendor` hashtree descriptor, but the image's actual container, filesystem, modules, and build properties remain unknown. |

The downloaded files are retained separately at `google_drive/boot.img`, `google_drive/dtbo.img`, and `google_drive/vbmeta.img`; `/google_drive/` is Git-ignored. No Drive credentials or private signing key were accessed or recorded.

## DTBO contents

The header is big-endian DT-table v0: `total_size=955,953`, `header_size=32`, `entry_size=32`, 17 entries, entries start at byte 32, and page size is 2048. The 8 MiB partition image is padded and has an AVB footer; its AVB `original_image_size` is 955,953 bytes. Each table entry points to a structurally valid FDT. The table's `id`, `rev`, and custom fields are all zero.

Root models include IOT MTP, QRD, RCM, MTP, IPC, several Qualcomm codec/CDP/QRD variants, RUMI, and an MSM8953 + PMI8950 Ext Codec MTP tree (`qcom,msm8953-mtp`). Some overlay strings name `onc_*` camera configurations such as `onc_ov02a10` and `onc_s5k4h7`; no literal `onclite` string was found. These names and generic Qualcomm models are **not** proof that the image belongs to Redmi Y3 (`onc`) or Redmi 7 (`onclite`), nor do zero table IDs show which overlay a bootloader would select. The overlay-to-device/board match remains unresolved.

## AVB and what it establishes

`vbmeta.img` reports algorithm `SHA256_RSA2048`, 320-byte authentication block, 2,816-byte auxiliary block, flags 0, rollback index 0, and public-key SHA-1 fingerprint `b2a02f1e56e366d727a1a8e089762fe0b91bbc84`. `avbtool verify_image` successfully verified the vbmeta signature against its embedded public key and then verified the supplied boot and DTBO descriptors:

- `boot`: 15,218,688 bytes, SHA-256, salt `00a22bda86e291059a837ebd3baa4193872cf215922b24f9a9a483073f12fc5c`, digest `3193f936e928c7780bfecbd4d8f573619c04bea20e997c5c9461c291122be250` — matches the original boot image and its embedded footer descriptor.
- `dtbo`: 955,953 bytes, SHA-256, salt `cd06bb8f38f9c8c66e29eccd41d20d9326b680ebf0c2902d2cafa5224d506001`, digest `a21f185842b7df99b37cb81b8b3652a9f2b14ad37932fd0dc0fc80069617d1c7` — matches the DTBO bytes and its embedded footer descriptor.

The same vbmeta contains a recovery hash descriptor for 27,971,584 bytes; dm-verity hashtree descriptors for system (3,698,716,672-byte image) and vendor (1,056,714,752-byte image); Android 10 / `2021-03-01` security-patch properties for boot, vendor, and system; and conditional dm-verity kernel command-line descriptors. Those descriptors show what this vbmeta expects, not the device's current enforcement or bootloader state.

The complete `avbtool verify_image --image google_drive/vbmeta.img` run exits non-zero after the signature and boot/DTBO checks because `recovery.img` is absent (`FileNotFoundError`). It therefore did **not** verify the recovery, system, or vendor image data. The embedded vbmeta public key's signature is valid, but no device/OEM trust-anchor or rollback-state evidence establishes that a particular phone bootloader trusts it.

Both `boot.img` and `dtbo.img` have embedded AVB footer v1.0 with `Algorithm: NONE` and empty authentication blocks. Their internal hash descriptors are consistent; the signed external vbmeta authenticates their original content. A kernel replacement changes bytes covered by the external `boot` descriptor. If the phone enforces this unchanged signed vbmeta, the candidate boot image will not match its descriptor. The current ZIP writes only boot and does not update or re-sign vbmeta. This is a concrete AVB blocker for an enforcing state—not proof of what an unlocked or modified device would accept. No AVB metadata was modified.

Full tool output is saved in [`google-drive-avb-verification.txt`](google-drive-avb-verification.txt).

## Vendor-image limit and module ABI

Drive reports `vendor.img` as 926,327,184 bytes, exceeding the Drive connector's documented **100 MB maximum** for downloading regular files. No vendor bytes were retrieved, so no Android sparse/raw format, filesystem, build fingerprint, board property, `.ko`, `modules.load`, `modules.dep`, `modules.alias`, `modules.softdep`, module `vermagic`, embedded symbol versions, or `Module.symvers` were inspected. The vbmeta vendor descriptor's 1,056,714,752-byte image size is larger than the Drive object size; this could reflect a sparse representation, but without bytes it cannot be confirmed and should not be treated as a verified size mismatch or format identification.

Practical alternative: in Drive, add either (a) an unchanged split of `vendor.img` into pieces below 90 MB each, plus the original SHA-256, or (b) a small archive containing all vendor `*.ko` files, any `modules.load`/`.dep`/`.alias`/`.softdep` files, vendor build properties/fingerprints, and their paths. The split option allows reassembly and comparison to the Drive SHA-256; the extracted-file option permits module inspection but cannot validate the whole vendor image's AVB hashtree.

## Comparison with the candidate and exact next step

- The Drive boot is byte-identical to the already audited original (`4.9.186-perf-g131f907`, boot v1, no ramdisk). Its stock embedded config has `CONFIG_MODVERSIONS=y` and `CONFIG_MODULE_SIG_FORCE=y`.
- The candidate uses `onclite-perf_defconfig`; the prior comparison found six value mismatches against that defconfig and a closer value match to `onc-perf_defconfig`. This is a source/config concern, **not** device-codename identification. `g131f907` remains insufficient to prove the source revision.
- The candidate kernel's release string matches stock, but 21,595,768 bytes differ in the common uncompressed range. No vendor modules or `Module.symvers` are available to establish module compatibility.
- The AnyKernel installer explicitly requires a non-empty ramdisk. The original has zero, so the installer fails closed before writing. Do not bypass this guard to force installation; Magisk/root placement is still unknown.
- The signed vbmeta covers the original boot and DTBO hashes. The current installer does not change vbmeta, so AVB acceptance of a modified boot is not established and would fail hash verification if that signed vbmeta is enforced.

**Next step:** provide vendor module contents in one of the two forms above. Then compare module vermagic/`__versions` against the stock config and candidate source, and resolve the exact stock source/config revision. Before preparing any testable ZIP, the zero-ramdisk/root arrangement and whether this signed AVB chain is trusted/enforced must also be established. Until those checks are complete, keep the ZIP unchanged and blocked. No phone testing is requested or performed in this phase.
