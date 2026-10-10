# Third-party notices

## Xiaomi kernel source

The kernel payload is built from Xiaomi's Linux 4.9.186 source at [`MiCode/Xiaomi_Kernel_OpenSource`, commit `fa577bc566886db1e0dfb1ddf66ff7c528148b2b`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/commit/fa577bc566886db1e0dfb1ddf66ff7c528148b2b), with the configuration patch in this repository. The kernel source is distributed under GPL-2.0 as indicated by its upstream `COPYING` file. The pinned source can be fetched with `scripts/build.sh`; see `README.md` and `BUILD_REPORT.md` for the exact revision, configuration, and build procedure. The complete upstream source is not copied into this small project repository.

## AnyKernel3

The recovery installer framework in the ZIP is derived from [osm0sis/AnyKernel3](https://github.com/osm0sis/AnyKernel3), pinned to commit [`020dfeccf9d7e962a48400fc94d3e451df92eead`](https://github.com/osm0sis/AnyKernel3/commit/020dfeccf9d7e962a48400fc94d3e451df92eead). The upstream license and included-tool notices are copied into the ZIP at `LICENSES/AnyKernel3-LICENSE.txt`.

## MagiskBoot

`tools/magiskboot` in the ZIP is the image manipulation utility distributed by the pinned AnyKernel3 revision. It is not the Magisk app, Magisk APK, a root installer, or a bundled Magisk release package. Its source project and GPLv3+ license are identified in the included AnyKernel3 license; upstream Magisk is [topjohnwu/Magisk](https://github.com/topjohnwu/Magisk).

## BusyBox

`tools/busybox` is the recovery-side utility bundled by the pinned AnyKernel3 revision. Its GPLv2 notice and source project link are included in the AnyKernel3 license file. AnyKernel3 uses it to supply shell applets needed by the installer.

No signing keys, credentials, private keys, or original firmware boot images are included.
