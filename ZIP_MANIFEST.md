# Manifest for prior static candidate — NOT FLASH-READY

**Do not install `Redmi7_onclite_Kernel_Flashable.zip`.** This manifest describes the previously built archive only. Its structure was statically verified, but it was not audited against the supplied boot image because the download was blocked, and the exact source revision remains unresolved.

`Redmi7_onclite_Kernel_Flashable.zip` contains:

| Path | Purpose |
|---|---|
| `META-INF/com/google/android/update-binary` | AnyKernel3 recovery ZIP entry point. |
| `META-INF/com/google/android/updater-script` | AnyKernel3 updater metadata. |
| `anykernel.sh` | Strict `onclite` device check, boot-header selection, and boot-only installation flow. |
| `tools/ak3-core.sh` | AnyKernel3 live boot-image unpack/repack/flash helpers. |
| `tools/busybox` | Recovery shell applets required by AnyKernel3. |
| `tools/magiskboot` | Android boot-image parsing/repacking and Magisk-preservation helper. |
| `payload/Image.gz` | Compressed arm64 kernel only. The installer requires and preserves the DTB extracted from the live boot image (appended `kernel_dtb` for header v0/v1, separate `dtb` for header v2). |
| `banner`, `ZIP_CONTENTS.txt` | Recovery progress banner and archive description. |
| `LICENSES/AnyKernel3-LICENSE.txt` | Upstream installer/tool license notices. |

The ZIP deliberately contains no original `boot.img`, no ramdisk image, no prebuilt `dtbo`, `recovery`, `vendor_boot`, or `vbmeta` image, and no kernel modules. The installer reads the live boot image and requests writing only the by-name `boot` partition after its checks pass.

## Prior archive identity and static checks

- Archive size: **11,975,575 bytes**
- Archive SHA-256: `58df6f662cce96d1106e406ecad30dc757027619ceb363d9d5fcd1ec013ae79f`
- Kernel payload SHA-256: `b53cef1c92fa65e1f5f69093760f79ed49e4475e2a3a2551c0e7474f53bc7625`
- Static verification: `python3 scripts/verify_zip.py` and `unzip -t` passed. No physical-device or recovery test was performed.
