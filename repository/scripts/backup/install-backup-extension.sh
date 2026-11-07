#!/usr/bin/env bash
# Run manually as administrator after reviewing backup changes.
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
(( $# == 0 )) || { echo 'No arguments accepted.' >&2; exit 2; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
# Accept the original, post-retirement and deployed recovery-metadata baselines. Never overwrite unrecognized production-only changes.
baselines=(e2ad538f66b789f60141dc0052b62d80d93aae85 a46e99fe8677295bd590d83b027e410c2b63a833 498665678bb8a36e3b7ca72029d6af7d232569f0)
exec 9>/run/lock/homelab-restic-backup.lock
flock -n 9 || { echo 'Backup is running; retry when it finishes.' >&2; exit 1; }

sources=(scripts/backup/homelab-restic-backup.sh backup/backup-sources.txt backup/backup-excludes.txt backup/sqlite-databases.conf scripts/backup/capture-postersplus-state.sh)
targets=(/usr/local/sbin/homelab-restic-backup.sh /etc/example-homelab/backup-sources.txt /etc/example-homelab/backup-excludes.txt /etc/example-homelab/sqlite-databases.conf /usr/local/sbin/homelab-capture-postersplus-state.sh)
retirement_baseline() {
    # Accept the prior lists only when deleting exact retired entries yields the
    # reviewed replacement byte-for-byte. Production-only entries still refuse.
    local config=$1 installed=$2
    awk -v config="$config" '
        config == "backup/backup-sources.txt" && $0 == "/srv/example-app-data/xrdb" {next}
        config == "backup/backup-excludes.txt" &&
            $0 ~ /^\/srv\/example-app-data\/xrdb\/xrdb\.db(\.settings)?(-wal|-shm)?$/ {next}
        config == "backup/sqlite-databases.conf" &&
            ($0 == "# XRDB default paths; confirm the installed XRDB_DB before deployment." ||
             $0 == "xrdb-profiles|/srv/example-app-data/xrdb/xrdb.db" ||
             $0 == "xrdb-settings|/srv/example-app-data/xrdb/xrdb.db.settings") {next}
        {print}
    ' "$installed" | cmp -s - "$repo/$config"
}
for i in "${!sources[@]}"; do
    src=${sources[i]}
    dest=${targets[i]}
    [[ -f $repo/$src && ! -L $repo/$src ]] || { echo "Missing reviewed source: $src" >&2; exit 1; }
    if [[ $src == scripts/backup/capture-postersplus-state.sh && ! -e $dest && ! -L $dest ]]; then
        continue
    fi
    [[ -f $dest && ! -L $dest ]] || { echo "Unexpected target: $dest" >&2; exit 1; }
    if cmp -s "$repo/$src" "$dest"; then continue; fi
    case $src in
        backup/backup-sources.txt|backup/backup-excludes.txt|backup/sqlite-databases.conf)
            if retirement_baseline "$src" "$dest"; then continue; fi ;;
    esac
    recognized=false
    for baseline in "${baselines[@]}"; do
        if git -c safe.directory="$repo" -C "$repo" show "$baseline:$src" 2>/dev/null | cmp -s - "$dest"; then
            recognized=true
            break
        fi
        if [[ $src == backup/backup-sources.txt || $src == backup/sqlite-databases.conf ]]; then
            if git -c safe.directory="$repo" -C "$repo" show "$baseline:scripts/$src" | cmp -s - "$dest"; then
                recognized=true
                break
            fi
        fi
    done
    if [[ $recognized == true ]]; then continue; fi
    echo "STOP: installed file differs from reviewed versions: $dest" >&2
    echo 'Compare locally and preserve production-only entries before retrying.' >&2
    exit 1
done

test -d /srv/example-app-data/arcane
test -d /srv/example-app-data/postersplus/cache
test -f /srv/example-app-data/postersplus/cache/cache.db
bash -n "$repo/scripts/backup/homelab-restic-backup.sh"
bash -n "$repo/scripts/backup/capture-postersplus-state.sh"

rollback=$(mktemp -d /var/tmp/example-homelab-backup-rollback.XXXXXX)
for i in "${!targets[@]}"; do
    if [[ -e ${targets[i]} ]]; then cp -a -- "${targets[i]}" "$rollback/$i"; fi
done
printf 'Rollback copy: %s\n' "$rollback"

restore_on_error() {
    local rc=$?
    trap - ERR
    echo 'Installation failed; restoring previous files.' >&2
    for i in "${!targets[@]}"; do
        if [[ -e $rollback/$i ]]; then
            cp -a -- "$rollback/$i" "${targets[i]}" || echo "Restore failed: ${targets[i]}" >&2
        else
            rm -f -- "${targets[i]}" || echo "Restore failed: ${targets[i]}" >&2
        fi
    done
    exit "$rc"
}
trap restore_on_error ERR
for i in "${!sources[@]}"; do
    mode=600
    [[ $i != 0 && ${sources[i]} != scripts/backup/capture-postersplus-state.sh ]] || mode=700
    install -o root -g root -m "$mode" -- "$repo/${sources[i]}" "${targets[i]}"
done
bash -n /usr/local/sbin/homelab-restic-backup.sh
bash -n /usr/local/sbin/homelab-capture-postersplus-state.sh
test "$(stat -c '%u:%a' /usr/local/sbin/homelab-capture-postersplus-state.sh)" = 0:700
trap - ERR
printf 'Installed backup extension. No backup started. Rollback: %s\n' "$rollback"
