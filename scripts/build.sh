#!/usr/bin/env bash
# Build a diagnostic kernel only. This script intentionally does not package a ZIP.
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SOURCE_URL=https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git
SOURCE_BRANCH=onc-q-oss
SOURCE_COMMIT=fa577bc566886db1e0dfb1ddf66ff7c528148b2b
DEFCONFIG=onc-perf_defconfig
TOOLCHAIN_URL=https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_aarch64_aarch64-linux-android-4.9.git
TOOLCHAIN_BRANCH=lineage-19.1
TOOLCHAIN_COMMIT=5e030eafe024784a73cdf47e6936ac0dbfc763dc
BC_URL=https://github.com/gavinhoward/bc.git
BC_TAG=7.1.0
BC_COMMIT=70c51d95e02d20fc3fc82791dc3f1aa0e9d47f0d
PATCH_FILE="$ROOT/patches/0001-onclite-disable-module-signature-enforcement.patch"
ARTIFACT_DIR=${ARTIFACT_DIR:-"$ROOT/build-artifacts/onclite-kernel-only-stock-config"}
IMAGE_OUTPUT=${IMAGE_OUTPUT:-"$ARTIFACT_DIR/Image.gz"}
CONFIG_OUTPUT=${CONFIG_OUTPUT:-"$ARTIFACT_DIR/.config"}
METADATA_OUTPUT=${METADATA_OUTPUT:-"$ARTIFACT_DIR/build-metadata.txt"}
STOCK_BOOT_IMAGE=${STOCK_BOOT_IMAGE:-"$ROOT/backups/original/boot.img"}
CONFIG_ONLY=${CONFIG_ONLY:-0}
JOBS=${JOBS:-2}

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for tool in git make gcc python3 readelf sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || fail "Required host tool not found: $tool"
done
[[ -f "$PATCH_FILE" ]] || fail "Missing patch: $PATCH_FILE"
[[ -f "$STOCK_BOOT_IMAGE" ]] || fail "A local stock boot image is required for the pre-build config comparison: $STOCK_BOOT_IMAGE"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || fail "JOBS must be a positive integer"
[[ "$CONFIG_ONLY" == 0 || "$CONFIG_ONLY" == 1 ]] || fail "CONFIG_ONLY must be 0 or 1"

mkdir -p "$ARTIFACT_DIR"
python3 - "$ROOT" "$IMAGE_OUTPUT" "$CONFIG_OUTPUT" "$METADATA_OUTPUT" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
outputs = [pathlib.Path(value).resolve() for value in sys.argv[2:]]
if len(set(outputs)) != len(outputs):
    raise SystemExit("ERROR: image, config, and metadata outputs must be different paths")
protected = [
    root / "Redmi7_onclite_Kernel_Flashable.zip",
    root / "backups" / "original",
    root / "google_drive",
]
for output in outputs:
    if output.exists():
        raise SystemExit(f"ERROR: refusing to overwrite existing output: {output}")
    for item in protected:
        item = item.resolve()
        if output == item or item in output.parents:
            raise SystemExit(f"ERROR: diagnostic output must not overwrite or enter protected path: {output}")
PY

WORK=$(mktemp -d "${TMPDIR:-/tmp}/redmi7-onclite-kernel.XXXXXXXX")
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT INT TERM
SOURCE=${KERNEL_SOURCE_DIR:-"$WORK/source"}
TC="$WORK/toolchain"
OUT="$WORK/out"
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
[[ "$(git -C "$SOURCE" status --porcelain)" == ' M arch/arm64/configs/onc-perf_defconfig' ]] || fail "Source tree contains changes beyond the one-line module-signature patch"
[[ "$(git -C "$SOURCE" diff --numstat -- arch/arm64/configs/onc-perf_defconfig)" == $'1\t1\tarch/arm64/configs/onc-perf_defconfig' ]] || fail "The defconfig patch is not a single-line change"
git -C "$SOURCE" diff --check

git clone --quiet --depth 1 --single-branch --branch "$TOOLCHAIN_BRANCH" "$TOOLCHAIN_URL" "$TC"
[[ "$(git -C "$TC" rev-parse HEAD)" == "$TOOLCHAIN_COMMIT" ]] || fail "Toolchain branch no longer resolves to the pinned commit"
[[ -z "$(git -C "$TC" status --porcelain)" ]] || fail "Toolchain checkout contains unexpected modifications"
CROSS_COMPILE="$TC/bin/aarch64-linux-android-"
COMPILER="${CROSS_COMPILE}gcc"
[[ -x "$COMPILER" ]] || fail "Pinned AArch64 GCC compiler is missing"

# bc is a normal Linux-kernel host prerequisite. Build the exact pinned copy
# in temporary storage only when the host does not already provide bc.
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

# Linux 4.9 host helpers need OpenSSL development files. Prefer system headers;
# on this minimal image use its Node-vendored headers and OpenSSL 3 runtime.
HOSTCFLAGS=${HOSTCFLAGS:-"-O2 -Wall"}
HOST_LOADLIBES=${HOST_LOADLIBES:-}
# Old generated DTC code expects GCC's pre-GCC-10 common-symbol default.
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
  "HOSTCC=${HOSTCC:-gcc}"
  "HOSTCFLAGS=$HOSTCFLAGS"
  "HOSTLDFLAGS=$HOSTLDFLAGS"
  "HOST_LOADLIBES=$HOST_LOADLIBES"
)
run_make() { make "${make_args[@]}" "$@"; }

printf '%s\n' "Configuring $DEFCONFIG; restoring two stock-y settings omitted from the upstream defconfig"
run_make "$DEFCONFIG"
"$SOURCE/scripts/config" --file "$OUT/.config" --enable TASK_DELAY_ACCT --enable SOCKEV_NLMCAST
run_make olddefconfig
for setting in \
  'CONFIG_LOCALVERSION="-perf"' \
  'CONFIG_LOCALVERSION_AUTO=y' \
  'CONFIG_MODULES=y' \
  'CONFIG_MODVERSIONS=y' \
  'CONFIG_MODULE_SIG=y' \
  'CONFIG_MODULE_SIG_SHA512=y' \
  'CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE=y' \
  'CONFIG_TASK_DELAY_ACCT=y' \
  'CONFIG_SOCKEV_NLMCAST=y' \
  '# CONFIG_MODULE_SIG_FORCE is not set'; do
  grep -qxF "$setting" "$OUT/.config" || fail "Generated config does not contain expected setting: $setting"
done

# Compare the fully-resolved build config with IKCONFIG extracted from the
# unchanged stock boot image before compiling. Only force-signature may differ
# among recognized source symbols; KTRACE/RTMM are stock-only legacy symbols
# absent from the pinned Xiaomi source's Kconfig and cannot be reproduced here.
python3 - "$STOCK_BOOT_IMAGE" "$OUT/.config" <<'PY'
import hashlib, pathlib, sys, zlib
boot_path, config_path = map(pathlib.Path, sys.argv[1:])
data = boot_path.read_bytes()
if data[:8] != b"ANDROID!" or len(data) < 2048:
    raise SystemExit(f"{boot_path}: not a supported Android boot image")
page = int.from_bytes(data[36:40], "little")
kernel_size = int.from_bytes(data[8:12], "little")
if page < 512 or page & (page - 1) or page + kernel_size > len(data):
    raise SystemExit(f"{boot_path}: invalid boot header component bounds")
kernel = data[page:page + kernel_size]
if not kernel.startswith(b"\x1f\x8b"):
    raise SystemExit(f"{boot_path}: stock kernel component is not gzip")
decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
try:
    image = decoder.decompress(kernel) + decoder.flush()
except zlib.error as exc:
    raise SystemExit(f"{boot_path}: invalid stock kernel gzip: {exc}")
start = image.find(b"IKCFG_ST")
end = image.find(b"IKCFG_ED", start + 8) if start >= 0 else -1
if start < 0 or end <= start:
    raise SystemExit(f"{boot_path}: embedded IKCONFIG not found")
try:
    stock_text = zlib.decompress(image[start + 8:end], 16 + zlib.MAX_WBITS).decode("utf-8", "replace")
except zlib.error as exc:
    raise SystemExit(f"{boot_path}: invalid embedded IKCONFIG: {exc}")
def parse(text):
    values = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            values[line.split()[1]] = "n"
    return values
stock = parse(stock_text)
built_text = config_path.read_text(errors="replace")
built = parse(built_text)
changed = sorted(key for key in stock.keys() & built.keys() if stock[key] != built[key])
stock_only = sorted(stock.keys() - built.keys())
build_only = sorted(built.keys() - stock.keys())
expected_changed = ["CONFIG_MODULE_SIG_FORCE"]
expected_stock_only = ["CONFIG_KTRACE", "CONFIG_RTMM"]
if changed != expected_changed or stock_only != expected_stock_only or build_only:
    raise SystemExit(
        "pre-build config mismatch: "
        f"changed={changed}, stock_only={stock_only}, build_only={build_only}"
    )
print(f"Stock config: {len(stock_text.splitlines())} lines, sha256={hashlib.sha256(stock_text.encode()).hexdigest()}")
print(f"Generated config: {len(built_text.splitlines())} lines, sha256={hashlib.sha256(built_text.encode()).hexdigest()}")
print("Recognized config delta: CONFIG_MODULE_SIG_FORCE stock=y, build=n")
print("Stock-only symbols unsupported by pinned Kconfig: CONFIG_KTRACE, CONFIG_RTMM")
print("Other stock config values match; pre-build config gate passed")
PY

if [[ "$CONFIG_ONLY" == 1 ]]; then
  printf '%s\n' 'CONFIG_ONLY=1: pre-build config gate passed; no kernel image compiled.'
  exit 0
fi

KERNEL_RELEASE=$(run_make -s kernelrelease)
[[ "$KERNEL_RELEASE" == 4.9.186-perf* ]] || fail "Unexpected kernel release string: $KERNEL_RELEASE"
printf 'Generated kernel release: %s\n' "$KERNEL_RELEASE"
printf '%s\n' "Building Image.gz only with JOBS=$JOBS; no DTBs, modules, installer, or ZIP will be produced"
run_make -j"$JOBS" Image.gz

IMAGE_GZ="$OUT/arch/arm64/boot/Image.gz"
VMLINUX="$OUT/vmlinux"
[[ -s "$IMAGE_GZ" ]] || fail 'Image.gz was not produced'
[[ -s "$VMLINUX" ]] || fail 'vmlinux was not produced'
ELF_MACHINE=$(readelf -h "$VMLINUX" | sed -n 's/^[[:space:]]*Machine:[[:space:]]*//p')
[[ "$ELF_MACHINE" == AArch64 ]] || fail "vmlinux is not AArch64 (readelf reports: ${ELF_MACHINE:-unknown})"

python3 - "$IMAGE_GZ" "$OUT/.config" "$KERNEL_RELEASE" <<'PY'
import hashlib, pathlib, sys, zlib
image_path, config_path, expected_release = sys.argv[1:]
data = pathlib.Path(image_path).read_bytes()
if not data.startswith(b"\x1f\x8b"):
    raise SystemExit(f"{image_path}: missing gzip magic")
decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
try:
    image = decoder.decompress(data) + decoder.flush()
except zlib.error as exc:
    raise SystemExit(f"{image_path}: invalid gzip kernel stream: {exc}")
if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
    raise SystemExit(f"{image_path}: gzip stream is incomplete or has unexpected trailing bytes")
if len(image) < 1024 * 1024 or image[56:60] != b"ARM\x64":
    raise SystemExit(f"{image_path}: decompressed payload is not a plausible arm64 Image")
version = b"Linux version " + expected_release.encode()
if version not in image:
    raise SystemExit(f"{image_path}: embedded Linux version does not contain {expected_release}")
start = image.find(b"IKCFG_ST")
end = image.find(b"IKCFG_ED", start + 8) if start >= 0 else -1
if start < 0 or end <= start:
    raise SystemExit(f"{image_path}: embedded IKCONFIG was not found")
try:
    embedded = zlib.decompress(image[start + 8:end], 16 + zlib.MAX_WBITS).decode("utf-8", "replace")
except zlib.error as exc:
    raise SystemExit(f"{image_path}: embedded IKCONFIG is invalid: {exc}")
def parse(text):
    values = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            values[line.split()[1]] = "n"
    return values
built = parse(embedded)
expected = parse(pathlib.Path(config_path).read_text(errors="replace"))
if built != expected:
    changed = sorted(key for key in set(built) | set(expected) if built.get(key) != expected.get(key))
    raise SystemExit(f"embedded IKCONFIG differs from generated .config for: {', '.join(changed[:20])}")
if built.get("CONFIG_MODULE_SIG_FORCE") != "n":
    raise SystemExit("embedded IKCONFIG still forces module signatures")
if built.get("CONFIG_MODULE_SIG") != "y" or built.get("CONFIG_MODVERSIONS") != "y":
    raise SystemExit("embedded IKCONFIG changed module signing or MODVERSIONS unexpectedly")
print(f"Validated gzip arm64 Image: {len(image)} bytes; sha256={hashlib.sha256(image).hexdigest()}")
print(f"Embedded IKCONFIG matches generated .config ({len(built)} settings); module signature enforcement is unset")
PY

COMPILER_VERSION_TEXT=$("$COMPILER" --version)
COMPILER_VERSION=${COMPILER_VERSION_TEXT%%$'\n'*}
COMPILER_TARGET=$("$COMPILER" -dumpmachine)
COMPILER_DUMP_VERSION=$("$COMPILER" -dumpversion)
COMPILER_SHA256=$(sha256sum "$COMPILER" | awk '{print $1}')
SOURCE_PATCH_BLOB=$(git -C "$SOURCE" hash-object arch/arm64/configs/onc-perf_defconfig)
PATCH_SHA256=$(sha256sum "$PATCH_FILE" | awk '{print $1}')
IMAGE_SHA256=$(sha256sum "$IMAGE_GZ" | awk '{print $1}')
CONFIG_SHA256=$(sha256sum "$OUT/.config" | awk '{print $1}')
IMAGE_BYTES=$(wc -c < "$IMAGE_GZ" | tr -d '[:space:]')

mkdir -p "$(dirname -- "$IMAGE_OUTPUT")" "$(dirname -- "$CONFIG_OUTPUT")" "$(dirname -- "$METADATA_OUTPUT")"
cp -- "$IMAGE_GZ" "$IMAGE_OUTPUT"
cp -- "$OUT/.config" "$CONFIG_OUTPUT"
cat > "$METADATA_OUTPUT" <<EOF
Diagnostic kernel-only build metadata
Build UTC: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
Source URL: $SOURCE_URL
Source branch: $SOURCE_BRANCH
Source commit: $SOURCE_COMMIT
Defconfig: $DEFCONFIG
Patched defconfig blob: $SOURCE_PATCH_BLOB
Patch: $PATCH_FILE
Patch SHA-256: $PATCH_SHA256
Toolchain URL: $TOOLCHAIN_URL
Toolchain branch: $TOOLCHAIN_BRANCH
Toolchain commit: $TOOLCHAIN_COMMIT
Compiler: $COMPILER
Compiler version: $COMPILER_VERSION
Compiler dumpversion: $COMPILER_DUMP_VERSION
Compiler target: $COMPILER_TARGET
Compiler binary SHA-256: $COMPILER_SHA256
bc fallback commit: $BC_COMMIT (used only if host bc was absent)
Host: $(uname -srvmo)
Host GCC: $(gcc --version | sed -n '1p')
GNU Make: $(make --version | sed -n '1p')
Build targets: $DEFCONFIG; restore CONFIG_TASK_DELAY_ACCT=y and CONFIG_SOCKEV_NLMCAST=y from stock IKCONFIG; olddefconfig; Image.gz
Stock boot used only for read-only config comparison: $STOCK_BOOT_IMAGE
Config delta gate: CONFIG_MODULE_SIG_FORCE stock=y, build=n; stock-only unsupported symbols CONFIG_KTRACE and CONFIG_RTMM
Build command: make -C <pinned source> O=<temporary output> ARCH=arm64 CROSS_COMPILE=<pinned Android GCC 4.9 prefix> HOSTCC=${HOSTCC:-gcc} HOSTCFLAGS='$HOSTCFLAGS' HOSTLDFLAGS='$HOSTLDFLAGS' HOST_LOADLIBES='$HOST_LOADLIBES' -j$JOBS Image.gz
Jobs: $JOBS
Kernel release: $KERNEL_RELEASE
vmlinux ELF machine: $ELF_MACHINE
Image.gz bytes: $IMAGE_BYTES
Image.gz SHA-256: $IMAGE_SHA256
Generated .config SHA-256: $CONFIG_SHA256
Output: $IMAGE_OUTPUT
Packaging: none; no ZIP created
EOF

printf '\nDiagnostic kernel only; no ZIP was generated.\n'
printf 'Image.gz: %s (%s bytes)\n' "$IMAGE_OUTPUT" "$IMAGE_BYTES"
printf 'Config:   %s\n' "$CONFIG_OUTPUT"
printf 'Metadata: %s\n' "$METADATA_OUTPUT"
printf 'Release:  %s\n' "$KERNEL_RELEASE"
sha256sum "$IMAGE_OUTPUT" "$CONFIG_OUTPUT" "$METADATA_OUTPUT"
printf 'Existing blocked ZIP was not read or modified by this script.\n'
