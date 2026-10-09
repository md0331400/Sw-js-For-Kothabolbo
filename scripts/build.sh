#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SOURCE_URL=https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git
SOURCE_BRANCH=onc-q-oss
SOURCE_COMMIT=fa577bc566886db1e0dfb1ddf66ff7c528148b2b
TOOLCHAIN_URL=https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_aarch64_aarch64-linux-android-4.9.git
TOOLCHAIN_BRANCH=lineage-19.1
TOOLCHAIN_COMMIT=5e030eafe024784a73cdf47e6936ac0dbfc763dc
ANYKERNEL_URL=https://github.com/osm0sis/AnyKernel3.git
ANYKERNEL_COMMIT=020dfeccf9d7e962a48400fc94d3e451df92eead
BC_URL=https://github.com/gavinhoward/bc.git
BC_TAG=7.1.0
BC_COMMIT=70c51d95e02d20fc3fc82791dc3f1aa0e9d47f0d
PATCH_FILE="$ROOT/patches/0001-onclite-disable-module-signature-enforcement.patch"
OUTPUT=${OUTPUT:-"$ROOT/Redmi7_onclite_Kernel_Flashable.zip"}
JOBS=${JOBS:-2}

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for tool in git make gcc python3 zip sha256sum gzip; do
  command -v "$tool" >/dev/null 2>&1 || fail "Required host tool not found: $tool"
done
[[ -f "$PATCH_FILE" ]] || fail "Missing patch: $PATCH_FILE"
[[ -f "$ROOT/installer/anykernel.sh" ]] || fail "Missing installer/anykernel.sh"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/redmi7-onclite-build.XXXXXXXX")
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT INT TERM
SOURCE=${KERNEL_SOURCE_DIR:-"$WORK/source"}
TC="$WORK/toolchain"
AK3=${ANYKERNEL3_DIR:-"$WORK/AnyKernel3"}
OUT=${KERNEL_OUT:-"$WORK/out"}
PKG="$WORK/package"
HOSTLIB="$WORK/hostlib"
mkdir -p "$HOSTLIB"

printf '%s\n' "Fetching/validating Xiaomi source $SOURCE_BRANCH at $SOURCE_COMMIT"
if [[ ! -d "$SOURCE/.git" ]]; then
  git clone --quiet --depth 1 --single-branch --branch "$SOURCE_BRANCH" "$SOURCE_URL" "$SOURCE"
fi
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$SOURCE_COMMIT" ]] || fail "Xiaomi source branch no longer resolves to the pinned commit"
if ! git -C "$SOURCE" apply --reverse --check "$PATCH_FILE" >/dev/null 2>&1; then
  git -C "$SOURCE" apply --check "$PATCH_FILE"
  git -C "$SOURCE" apply "$PATCH_FILE"
fi
[[ "$(git -C "$SOURCE" status --porcelain)" == ' M arch/arm64/configs/onclite-perf_defconfig' ]] || fail "Source tree contains changes beyond the pinned module-signature patch"
git -C "$SOURCE" diff --check

if [[ -z "${CROSS_COMPILE:-}" ]]; then
  printf '%s\n' "Fetching pinned Android GCC 4.9 toolchain"
  git clone --quiet --depth 1 --single-branch --branch "$TOOLCHAIN_BRANCH" "$TOOLCHAIN_URL" "$TC"
  [[ "$(git -C "$TC" rev-parse HEAD)" == "$TOOLCHAIN_COMMIT" ]] || fail "Toolchain branch no longer resolves to the pinned commit"
  CROSS_COMPILE="$TC/bin/aarch64-linux-android-"
fi
[[ -x "${CROSS_COMPILE}gcc" ]] || fail "AArch64 GCC compiler is missing from CROSS_COMPILE"

printf '%s\n' "Fetching/validating pinned AnyKernel3 installer framework"
if [[ ! -d "$AK3/.git" ]]; then
  git clone --quiet --depth 1 "$ANYKERNEL_URL" "$AK3"
fi
[[ "$(git -C "$AK3" rev-parse HEAD)" == "$ANYKERNEL_COMMIT" ]] || fail "AnyKernel3 upstream HEAD changed; review/pin a tested revision before rebuilding"
[[ -z "$(git -C "$AK3" status --porcelain)" ]] || fail "AnyKernel3 checkout contains unexpected modifications"

# bc is a normal Linux-kernel host prerequisite. Build a pinned temporary copy
# only on minimal hosts that do not already provide the bc executable.
if ! command -v bc >/dev/null 2>&1; then
  printf '%s\n' "bc is missing; building pinned bc $BC_TAG in the temporary work directory"
  BC_SRC="$WORK/bc"
  git clone --quiet --depth 1 --branch "$BC_TAG" "$BC_URL" "$BC_SRC"
  [[ "$(git -C "$BC_SRC" rev-parse HEAD)" == "$BC_COMMIT" ]] || fail "bc tag does not resolve to the pinned commit"
  (cd "$BC_SRC" && ./configure.sh -O2 >/dev/null && make -j"$JOBS" >/dev/null)
  [[ -x "$BC_SRC/bin/bc" ]] || fail "temporary bc build did not produce bin/bc"
  mkdir -p "$WORK/hostbin"
  ln -s "$BC_SRC/bin/bc" "$WORK/hostbin/bc"
  export PATH="$WORK/hostbin:$PATH"
fi

# Kernel 4.9's sign-file and extract-cert host helpers need OpenSSL headers and
# libcrypto. Prefer distro development files; this fallback is for containers
# that expose Node's vendored OpenSSL headers plus the OpenSSL 3 runtime only.
HOSTCFLAGS=${HOSTCFLAGS:-"-O2 -Wall"}
HOST_LOADLIBES=${HOST_LOADLIBES:-}
# This legacy 4.9 tree has generated host DTC code that relies on GCC's
# pre-GCC-10 common-symbol default (notably yylloc). Restore it for modern hosts.
[[ " $HOSTCFLAGS " == *" -fcommon "* ]] || HOSTCFLAGS+=" -fcommon"
HOSTLDFLAGS=${HOSTLDFLAGS:-}
if [[ ! -f /usr/include/openssl/opensslv.h ]]; then
  if [[ -f /usr/local/include/node/openssl/opensslv.h ]]; then
    HOSTCFLAGS+=" -I/usr/local/include/node"
    if [[ ! -e /usr/lib/x86_64-linux-gnu/libcrypto.so && -e /usr/lib/x86_64-linux-gnu/libcrypto.so.3 ]]; then
      ln -s /usr/lib/x86_64-linux-gnu/libcrypto.so.3 "$HOSTLIB/libcrypto.so"
      HOSTLDFLAGS+=" -L$HOSTLIB"
      HOST_LOADLIBES+=" -L$HOSTLIB"
    fi
  else
    fail "OpenSSL development headers are required (install libssl-dev or set HOSTCFLAGS appropriately)"
  fi
fi

export ARCH=arm64 SUBARCH=arm64
make_args=(
  -C "$SOURCE"
  "O=$OUT"
  "ARCH=$ARCH"
  "CROSS_COMPILE=$CROSS_COMPILE"
  "LOCALVERSION=-g131f907"
  "HOSTCC=${HOSTCC:-gcc}"
  "HOSTCFLAGS=$HOSTCFLAGS"
  "HOSTLDFLAGS=$HOSTLDFLAGS"
  "HOST_LOADLIBES=$HOST_LOADLIBES"
)
run_make() { make "${make_args[@]}" "$@"; }

printf '%s\n' 'Configuring onclite-perf_defconfig'
run_make onclite-perf_defconfig
"$SOURCE/scripts/config" --file "$OUT/.config" --disable LOCALVERSION_AUTO
run_make olddefconfig

[[ "$(run_make -s kernelrelease)" == '4.9.186-perf-g131f907' ]] || fail 'Unexpected kernel release string'
grep -qx 'CONFIG_MODULES=y' "$OUT/.config" || fail 'CONFIG_MODULES must remain enabled'
grep -qx 'CONFIG_MODULE_SIG=y' "$OUT/.config" || fail 'CONFIG_MODULE_SIG must remain enabled'
grep -qx '# CONFIG_MODULE_SIG_FORCE is not set' "$OUT/.config" || fail 'CONFIG_MODULE_SIG_FORCE was not disabled'
grep -qx 'CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE=y' "$OUT/.config" || fail 'Expected appended-DTB image configuration is missing'

printf '%s\n' 'Building the compressed kernel only; the installer will retain the live device tree'
run_make -j"$JOBS" Image.gz

IMAGE_GZ="$OUT/arch/arm64/boot/Image.gz"
[[ -s "$IMAGE_GZ" ]] || fail 'Image.gz was not produced'
python3 - "$IMAGE_GZ" <<'PY'
import pathlib, sys, zlib
name = sys.argv[1]
data = pathlib.Path(name).read_bytes()
if not data.startswith(b"\x1f\x8b"):
    raise SystemExit(f"{name}: missing gzip kernel magic")
decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
try:
    decoded = decoder.decompress(data) + decoder.flush()
except zlib.error as exc:
    raise SystemExit(f"{name}: invalid compressed kernel stream: {exc}")
if not decoder.eof or decoder.unused_data:
    raise SystemExit(f"{name}: gzip stream is incomplete or has unexpected trailing bytes")
if len(decoded) < 1024 * 1024:
    raise SystemExit(f"{name}: decompressed kernel is implausibly small")
if len(decoded) < 64 or decoded[56:60] != b"ARM\x64":
    raise SystemExit(f"{name}: decompressed payload does not have the arm64 Image header magic")
print("Image.gz contains a valid arm64 Image; the exact device tree will be preserved from the live boot image.")
PY

mkdir -p "$PKG/META-INF" "$PKG/tools" "$PKG/payload" "$PKG/LICENSES"
cp -a "$AK3/META-INF" "$PKG/"
cp "$AK3/tools/ak3-core.sh" "$AK3/tools/busybox" "$AK3/tools/magiskboot" "$PKG/tools/"
cp "$AK3/LICENSE" "$PKG/LICENSES/AnyKernel3-LICENSE.txt"
cp "$ROOT/installer/anykernel.sh" "$PKG/anykernel.sh"
cp "$ROOT/installer/banner" "$PKG/banner"
cp "$IMAGE_GZ" "$PKG/payload/Image.gz"
chmod 0755 "$PKG/META-INF/com/google/android/update-binary" "$PKG/tools/busybox" "$PKG/tools/magiskboot"
chmod 0644 "$PKG/tools/ak3-core.sh" "$PKG/anykernel.sh" "$PKG/banner"

cat > "$PKG/ZIP_CONTENTS.txt" <<'EOF'
Redmi 7 (onclite) kernel installer archive.

- META-INF/com/google/android/: AnyKernel3 recovery update-binary and metadata.
- anykernel.sh: onclite-only checks and live boot-image kernel replacement.
- tools/: AnyKernel3 core plus BusyBox and MagiskBoot image tools.
- payload/Image.gz: arm64 compressed kernel; AnyKernel3/MagiskBoot preserves the device DTB extracted from the live boot image.
- LICENSES/: AnyKernel3 and included tool license notices.

No original boot image, ramdisk, recovery, DTBO, vendor_boot, vbmeta, or modules are included.
EOF

mkdir -p "$(dirname "$OUTPUT")"
ZIP_TMP="$WORK/Redmi7_onclite_Kernel_Flashable.zip"
(
  cd "$PKG"
  find . -type f -print0 | LC_ALL=C sort -z | xargs -0 zip -q -9 -X "$ZIP_TMP"
)
python3 "$ROOT/scripts/verify_zip.py" "$ZIP_TMP"
cp "$ZIP_TMP" "$OUTPUT"
printf '\nBuilt: %s\n' "$OUTPUT"
sha256sum "$OUTPUT"
printf 'Source commit: %s\nToolchain commit: %s\nAnyKernel3 commit: %s\n' \
  "$SOURCE_COMMIT" "$TOOLCHAIN_COMMIT" "$ANYKERNEL_COMMIT"
