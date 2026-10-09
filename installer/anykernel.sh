### Redmi 7 (onclite) only — AnyKernel3 install script
## The archive is built from Xiaomi's onc-q-oss source. The kernel source is
## distinct from the device's current boot image; this script replaces only
## the kernel component in the live boot image and does not ship a boot.img.

properties() { '
kernel.string=Redmi 7 onclite MIUI Q kernel - module-signature enforcement relaxed
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=1
device.name1=onclite
'; }

# Redmi 7 is a non-A/B device. Only the by-name boot partition is a target.
BLOCK=boot;
IS_SLOT_DEVICE=0;
RAMDISK_COMPRESSION=auto;
# Keep any existing AVB flag state. Never flash vbmeta from this package.
PATCH_VBMETA_FLAG=0;

# AnyKernel3 resolves BLOCK and supplies dump/repack/flash helpers.
. tools/ak3-core.sh;

if [ "$(basename "$BLOCK")" != "boot" ]; then
  abort "Resolved partition is not named boot. Refusing to write.";
fi;

ui_print "Checking and unpacking the existing boot image...";
split_boot;

if [ ! -s "$SPLITIMG/infotmp" ]; then
  abort "Boot-image metadata is missing. No partition was written.";
fi;

header_ver=$(sed -n 's/.*HEADER_VER[[:space:]]*\[\([0-9][0-9]*\)\].*/\1/p' "$SPLITIMG/infotmp" | head -n 1);
if [ ! "$header_ver" ]; then
  abort "Could not identify Android boot header version. No partition was written.";
fi;

ramdisk_found=0;
for ramdisk_candidate in "$SPLITIMG"/ramdisk.cpio*; do
  if [ -s "$ramdisk_candidate" ]; then
    ramdisk_found=1;
    break;
  fi;
done;
if [ "$ramdisk_found" != 1 ]; then
  abort "Expected boot ramdisk is missing. Refusing to replace boot.";
fi;

case "$header_ver" in
  0|1)
    # Keep the exact live appended DTB extracted by MagiskBoot as kernel_dtb.
    if [ ! -s "$SPLITIMG/kernel_dtb" ]; then
      abort "Header v${header_ver} image has no extracted appended DTB. Refusing to guess its layout.";
    fi;
    ;;
  2)
    # Header v2 carries its base DTB separately; keep that original DTB intact.
    if [ ! -s "$SPLITIMG/dtb" ]; then
      abort "Header v2 image has no separate DTB. Refusing to guess its layout.";
    fi;
    ;;
  *)
    abort "Unsupported boot header v${header_ver}; onclite expects legacy boot. No partition was written.";
    ;;
esac;

payload="$AKHOME/payload/Image.gz";
image_name="Image.gz";
if [ ! -s "$payload" ]; then
  abort "Required kernel payload $image_name is missing. No partition was written.";
fi;

ui_print "Boot header v${header_ver}; selecting $image_name.";
ui_print "Magisk ramdisk contents are retained; AnyKernel3 will reapply Magisk's kernel patch if detected.";
cp -f "$payload" "$AKHOME/$image_name" || abort "Could not stage kernel payload.";

# flash_boot repacks the live image and writes only BLOCK (boot). It skips
# ramdisk editing; the existing ramdisk, appended kernel DTB, separate DTB,
# and recovery-DTBO sections are passed through to magiskboot repack.
flash_boot;

ui_print "Boot image updated. No other partition was requested by this installer.";
