#!/sbin/sh
# Device/partition preflight and invocation of prebuilt_boot_lib.sh.
set -u

ui_print() {
  [ -n "${OUTFD:-}" ] || return 1
  while [ "$#" -gt 0 ]; do
    printf 'ui_print %s\nui_print\n' "$1" >> "/proc/self/fd/$OUTFD"
    shift
  done
}

abort() {
  ui_print " " "$@"
  exit 1
}

candidate=${1:-}
helper=${2:-}
STOCK_BOOT_SHA256=cb110f4ff0f252af903a5c1adca5d49d8d33cc490afef529487f1d89fc6d2f30
CANDIDATE_BOOT_SHA256=684d5f2f29ee0dfeb9519a007be99594a8ba9af7c57c1734dec3b0fc06a0495c
PARTITION_SIZE=67108864
BACKUP_DIR=/data/media/0

[ -n "${OUTFD:-}" ] || abort "Recovery UI descriptor is unavailable."
[ -f "$candidate" ] || abort "Prebuilt candidate is missing."
[ -f "$helper" ] || abort "Verified backup/write helper is missing."

onclite=0
for prop in ro.product.device ro.build.product ro.product.vendor.device ro.vendor.product.device; do
  value=$(getprop "$prop" 2>/dev/null || true)
  [ "$value" = "onclite" ] && onclite=1
  [ "$value" = "onc" ] && abort "Redmi Y3 codename onc is not supported."
done
[ "$onclite" = 1 ] || abort "No device property identifies Redmi 7 onclite."

slot_suffix=$(getprop ro.boot.slot_suffix 2>/dev/null || true)
[ -z "$slot_suffix" ] || [ "$slot_suffix" = "normal" ] || abort "Unexpected A/B slot suffix '$slot_suffix'; refusing to write."

boot_block=""
for path in \
  /dev/block/by-name/boot \
  /dev/block/bootdevice/by-name/boot \
  /dev/block/platform/7824900.sdhci/by-name/boot \
  /dev/block/platform/*/by-name/boot \
  /dev/block/platform/*/*/by-name/boot; do
  [ -b "$path" ] || continue
  resolved=$(readlink -f "$path" 2>/dev/null || true)
  [ -n "$resolved" ] || abort "Could not canonicalize boot block path $path."
  if [ -n "$boot_block" ] && [ "$boot_block" != "$resolved" ]; then
    abort "Ambiguous boot block paths resolve to different devices."
  fi
  boot_block=$resolved
done
[ -n "$boot_block" ] || abort "Could not resolve the onclite boot partition."

partition_size=$(blockdev --getsize64 "$boot_block" 2>/dev/null | tr -d '[:space:]')
[ "$partition_size" = "$PARTITION_SIZE" ] || abort "Boot partition size is '$partition_size', expected $PARTITION_SIZE bytes."

candidate_size=$(wc -c < "$candidate" | tr -d '[:space:]')
[ "$candidate_size" = "$PARTITION_SIZE" ] || abort "Candidate image size is not exactly $PARTITION_SIZE bytes."
candidate_hash=$(sha256sum "$candidate" 2>/dev/null | cut -d ' ' -f 1)
[ "$candidate_hash" = "$CANDIDATE_BOOT_SHA256" ] || abort "Candidate image SHA-256 mismatch."

# Stage and preserve the verified backup on the persistent data partition.
# Refuse recovery RAM disks, unmounted/encrypted /data, and symlinked backup paths.
mounts=$(mount 2>/dev/null || true)
data_source=$(printf '%s\n' "$mounts" | awk '$2 == "on" && $3 == "/data" { print $1; exit }')
case "$data_source" in
  /dev/block/*|/dev/mapper/*|/dev/dm-*) ;;
  *) abort "Persistent block-backed /data is not mounted; refusing to flash without a recovery copy.";;
esac
[ ! -L "$BACKUP_DIR" ] || abort "Persistent backup directory is a symbolic link."
mkdir -p "$BACKUP_DIR" || abort "Could not create /data/media/0 for the persistent backup."
[ -d "$BACKUP_DIR" ] && [ -w "$BACKUP_DIR" ] || abort "Persistent /data/media/0 is unavailable or read-only."
backup_real=$(readlink -f "$BACKUP_DIR" 2>/dev/null || true)
case "$backup_real" in
  /data/*) ;;
  *) abort "Backup path does not resolve inside persistent /data.";;
esac
probe="$BACKUP_DIR/.onclite-experimental-write-check.$$"
(umask 077; set -C; : > "$probe") 2>/dev/null || abort "Could not create a persistent backup under /data/media/0."
rm -f "$probe"

command -v blockdev >/dev/null 2>&1 || abort "Recovery lacks blockdev; refusing to write."
blockdev --setrw "$boot_block" >/dev/null 2>&1 || abort "Could not set the boot partition writable."

. "$helper" || abort "Could not load the backup/write helper."
onclite_flash_prebuilt \
  "$candidate" \
  "$boot_block" \
  "$BACKUP_DIR" \
  "$PARTITION_SIZE" \
  "$STOCK_BOOT_SHA256" \
  "$CANDIDATE_BOOT_SHA256"
result=$?
case "$result" in
  0)
    ui_print "Experimental boot written and read-back hash verified."
    ui_print "Original boot backup: /data/media/0/onclite-kernel-experimental-original-boot.img"
    ui_print "No vbmeta partition was written. Boot acceptance remains untested."
    exit 0
    ;;
  2)
    abort "Write/read-back failed; original boot was restored and verified."
    ;;
  3)
    abort "Automatic restore could not be verified. Remain in recovery and preserve the backup file."
    ;;
  *)
    abort "Preflight or backup failed; no boot write was performed."
    ;;
esac
