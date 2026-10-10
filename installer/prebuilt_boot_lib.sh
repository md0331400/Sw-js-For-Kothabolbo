#!/sbin/sh
# Shared flash/backup logic for the separate experimental, prebuilt-boot ZIP.
# This library never resolves a device path or decides whether a target is safe;
# the caller must validate codename, partition path, size, and hashes first.

_onclite_report() {
  if command -v ui_print >/dev/null 2>&1; then
    ui_print "$*"
  else
    printf '%s\n' "$*" >&2
  fi
}

_onclite_file_sha256() {
  sha256sum "$1" 2>/dev/null | cut -d ' ' -f 1
}

_onclite_block_sha256() {
  dd if="$1" bs=1048576 2>/dev/null | sha256sum 2>/dev/null | cut -d ' ' -f 1
}

_onclite_restore_stock() {
  local backup block expected actual
  backup=$1
  block=$2
  expected=$3
  _onclite_report "Attempting automatic restore from the verified pre-install backup..."
  if ! dd if="$backup" of="$block" bs=1048576 2>/dev/null; then
    _onclite_report "RESTORE WRITE FAILED. Remain in recovery; preserve $backup."
    return 1
  fi
  if ! sync; then
    _onclite_report "RESTORE SYNC FAILED. Remain in recovery; preserve $backup."
    return 1
  fi
  actual=$(_onclite_block_sha256 "$block")
  if [ "$actual" = "$expected" ]; then
    _onclite_report "Original boot read-back verified after automatic restore."
    return 0
  fi
  _onclite_report "RESTORE HASH MISMATCH ($actual). Remain in recovery; preserve $backup."
  return 1
}

onclite_flash_prebuilt() {
  local candidate block backup_dir expected_size expected_stock expected_candidate
  local candidate_size candidate_hash current_hash backup backup_hash second_hash readback_hash
  candidate=${1-}
  block=${2-}
  backup_dir=${3-}
  expected_size=${4-}
  expected_stock=${5-}
  expected_candidate=${6-}

  if [ "$#" -ne 6 ] || [ ! -f "$candidate" ] || [ -L "$candidate" ] || [ ! -e "$block" ]; then
    _onclite_report "Installer inputs are missing. No partition write attempted."
    return 1
  fi
  case $expected_size in
    ''|*[!0-9]*) _onclite_report "Invalid expected partition size. No write attempted."; return 1;;
  esac
  candidate_size=$(wc -c < "$candidate" | tr -d '[:space:]')
  if [ "$candidate_size" != "$expected_size" ]; then
    _onclite_report "Candidate size $candidate_size differs from expected $expected_size bytes. No write attempted."
    return 1
  fi
  candidate_hash=$(_onclite_file_sha256 "$candidate")
  if [ "$candidate_hash" != "$expected_candidate" ]; then
    _onclite_report "Candidate SHA-256 mismatch. No write attempted."
    return 1
  fi
  if [ ! -d "$backup_dir" ] || [ ! -w "$backup_dir" ]; then
    _onclite_report "Persistent backup directory is unavailable or not writable. No write attempted."
    return 1
  fi

  current_hash=$(_onclite_block_sha256 "$block")
  if [ "$current_hash" != "$expected_stock" ]; then
    _onclite_report "Current boot SHA-256 is not the audited original ($current_hash). Refusing to write."
    return 1
  fi

  backup="$backup_dir/onclite-kernel-experimental-original-boot.img"
  if [ -L "$backup" ] || [ -h "$backup" ]; then
    _onclite_report "Backup path is a symbolic link. Refusing to write."
    return 1
  fi
  if [ -e "$backup" ]; then
    if [ ! -f "$backup" ]; then
      _onclite_report "Existing backup path is not a regular file. Refusing to write."
      return 1
    fi
    backup_hash=$(_onclite_file_sha256 "$backup")
    if [ "$backup_hash" != "$expected_stock" ]; then
      _onclite_report "Existing backup has a different SHA-256. Refusing to overwrite it or flash."
      return 1
    fi
    _onclite_report "Verified existing original-boot backup: $backup"
  else
    _onclite_report "Creating and verifying a persistent original-boot backup..."
    if ! (umask 077; set -C; : > "$backup") 2>/dev/null; then
      _onclite_report "Could not reserve the backup path without replacing an existing file. No write attempted."
      return 1
    fi
    if ! dd if="$block" of="$backup" bs=1048576 2>/dev/null; then
      rm -f "$backup"
      _onclite_report "Could not read the complete original boot into the backup. No partition write attempted."
      return 1
    fi
    backup_hash=$(_onclite_file_sha256 "$backup")
    if [ "$backup_hash" != "$expected_stock" ]; then
      rm -f "$backup"
      _onclite_report "Backup SHA-256 mismatch. No partition write attempted."
      return 1
    fi
    _onclite_report "Verified original-boot backup saved at: $backup"
  fi
  if ! sync; then
    _onclite_report "Could not flush the verified backup to persistent storage. No partition write attempted."
    return 1
  fi

  # Recheck immediately before writing, in case the boot target changed while
  # the persistent backup was being made.
  second_hash=$(_onclite_block_sha256 "$block")
  if [ "$second_hash" != "$expected_stock" ]; then
    _onclite_report "Boot target changed after backup ($second_hash). Refusing to write."
    return 1
  fi

  _onclite_report "Writing only the prevalidated full-size boot image..."
  if ! dd if="$candidate" of="$block" bs=1048576 2>/dev/null || ! sync; then
    if _onclite_restore_stock "$backup" "$block" "$expected_stock"; then
      _onclite_report "Candidate write or sync failed; original boot restored."
      return 2
    fi
    return 3
  fi
  readback_hash=$(_onclite_block_sha256 "$block")
  if [ "$readback_hash" = "$expected_candidate" ]; then
    _onclite_report "Boot partition read-back matches the experimental image."
    _onclite_report "Original boot backup retained at: $backup"
    return 0
  fi

  _onclite_report "Boot read-back mismatch ($readback_hash)."
  if _onclite_restore_stock "$backup" "$block" "$expected_stock"; then
    _onclite_report "Read-back failed; original boot restored."
    return 2
  fi
  return 3
}
