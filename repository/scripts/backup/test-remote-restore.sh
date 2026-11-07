#!/usr/bin/env bash
# Administrator-run drill: restores active databases from B2 into isolated storage.
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
(( $# == 0 )) || { echo 'No arguments accepted.' >&2; exit 2; }
exec 9>/run/lock/homelab-restic-backup.lock
flock -n 9 || { echo 'Backup is running; retry later.' >&2; exit 1; }
for tool in restic jq docker sqlite3 gzip sha256sum timeout awk; do
    command -v "$tool" >/dev/null
done

work=$(mktemp -d /var/tmp/homelab-restore-drill.XXXXXXXX)
printf 'Protected test directory: %s\n' "$work"
exec > >(tee "$work/report.txt") 2>&1
cleanup() {
    rc=$?
    trap - EXIT INT TERM
    if [[ -s $work/container.id ]]; then
        cid=$(<"$work/container.id")
        if [[ $cid =~ ^[0-9a-f]{64}$ ]]; then
            docker logs "$cid" > "$work/postgres-container.log" 2>&1 || true
            docker inspect --format '{{json .State}}' "$cid" \
                > "$work/postgres-state.json" 2>/dev/null || true
            docker rm -f -v "$cid" >/dev/null || rc=1
        else
            echo 'Invalid test container ID; manual cleanup required.'
            rc=1
        fi
    fi
    printf 'Drill exit code: %s\nProtected artifacts retained: %s\n' "$rc" "$work"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

snapshot=$(sed -n 's/^snapshot=//p' /var/backups/example-homelab/current/.remote-success)
[[ $snapshot =~ ^[0-9a-f]{64}$ ]] || { echo 'Missing valid successful snapshot ID.'; exit 1; }
set -a
source /etc/example-restic/homelab-s3.env
set +a
restic --cache-dir "$work/restic-cache" snapshots "$snapshot" --json > "$work/snapshot.json"
jq -e --arg id "$snapshot" --arg host "$(hostname -s)" \
    'length == 1 and (.[0] | .id == $id and .hostname == $host and
    ((.tags // []) | (index("homelab") != null and index("automatic") != null and index("complete") != null)))' \
    "$work/snapshot.json" >/dev/null
printf 'Snapshot: %s\n' "$snapshot"
base=/var/backups/example-homelab/current
files=(databases/bookorbit-postgres.sql.gz sqlite/postersplus.sqlite)
includes=(--include "$base/SHA256SUMS")
for file in "${files[@]}"; do includes+=(--include "$base/$file"); done
includes+=(--include "$base/applications/postersplus/cache" --include "$base/applications/postersplus/cache/**")
restic --cache-dir "$work/restic-cache" restore "$snapshot" \
    --target "$work/restored" "${includes[@]}" > "$work/restic-restore.log" 2>&1
restored=$work/restored$base
for file in "${files[@]}"; do
    test -s "$restored/$file"
    expected=$(awk -v path="./$file" '$2 == path {print $1}' "$restored/SHA256SUMS")
    [[ $expected =~ ^[0-9a-f]{64}$ ]] || { echo "Missing checksum: $file"; exit 1; }
    actual=$(sha256sum "$restored/$file")
    [[ ${actual%% *} == "$expected" ]] || { echo "Checksum mismatch: $file"; exit 1; }
    printf 'SHA256 OK: %s\n' "$file"
done
for file in postersplus; do
    result=$(sqlite3 -readonly "$restored/sqlite/$file.sqlite" 'PRAGMA integrity_check;')
    [[ $result == ok ]] || { echo "SQLite integrity failed: $file"; exit 1; }
    count=$(sqlite3 -readonly "$restored/sqlite/$file.sqlite" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    (( count > 0 )) || { echo "No application tables: $file"; exit 1; }
    printf 'SQLite OK: %s, tables=%s\n' "$file" "$count"
done

# The database and authored files must come from the same snapshot generation.
test -d "$restored/applications/postersplus/cache"
state_checksums=$work/postersplus-files.SHA256SUMS
awk '$2 ~ /^\.\/applications\/postersplus\/cache\//' "$restored/SHA256SUMS" > "$state_checksums"
if [[ -s $state_checksums ]]; then
    (cd "$restored" && sha256sum --check --strict "$state_checksums")
fi
echo 'PostersPlus matching filesystem generation restored and verified.'

archive=$restored/databases/bookorbit-postgres.sql.gz
gzip -t "$archive"
# Match the exact locally installed pgvector image; no image pull or production mounts.
image=$(docker inspect --type container --format '{{.Image}}' bookorbit-db)
[[ $image =~ ^sha256:[0-9a-f]{64}$ ]]
bootstrap=restore_admin_$(basename "$work" | tr -cd 'a-z0-9')
# Let Docker provision isolated storage with container-side ownership. A root-owned
# mode-700 host bind directory can prevent the image's database user from initializing.
# The PostgreSQL entrypoint starts as root, fixes ownership and drops to postgres.
# This anonymous test volume is removed with the test container by cleanup's -v.
docker run -d --pull=never --network=none --memory=1g --cpus=1 --pids-limit=256 \
    --user 0:0 \
    --cidfile "$work/container.id" \
    --mount type=volume,dst=/var/lib/postgresql \
    -e PGDATA=/var/lib/postgresql/18/docker \
    -e POSTGRES_USER="$bootstrap" -e POSTGRES_DB=postgres \
    -e POSTGRES_HOST_AUTH_METHOD=trust "$image" > "$work/container-start.log" 2>&1
cid=$(<"$work/container.id")
ready=false
for attempt in $(seq 1 60); do
    if [[ $(docker inspect --format '{{.State.Running}}' "$cid") != true ]]; then
        break
    fi
    # TCP avoids accepting the temporary socket-only server used by initdb.
    if timeout 5s docker exec "$cid" psql -X -w -h 127.0.0.1 \
        -U "$bootstrap" -d postgres -At -c 'SELECT 1;' \
        > "$work/readiness.log" 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
if [[ $ready != true ]]; then
    echo 'Test PostgreSQL failed to become ready.'
    docker inspect --format \
        'Status={{.State.Status}} ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} Error={{.State.Error}}' \
        "$cid" || true
    echo 'Initialization log (no backup SQL has been imported yet):'
    docker logs --tail 50 "$cid" 2>&1 || true
    echo 'Last readiness probe:'
    if [[ -f $work/readiness.log ]]; then tail -n 10 "$work/readiness.log"; fi
    exit 1
fi
# Fail on every SQL error; the unique bootstrap role avoids the usual role conflict.
gzip -cd "$archive" | timeout 20m docker exec -i "$cid" \
    psql -X -U "$bootstrap" -d postgres -v ON_ERROR_STOP=1 \
    > "$work/postgres-import.log" 2>&1
docker exec "$cid" psql -X -U "$bootstrap" -d postgres -At \
    -c "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres';" \
    > "$work/databases.txt"
test -s "$work/databases.txt"
while IFS= read -r db; do
    count=$(docker exec "$cid" psql -X -U "$bootstrap" --dbname="$db" -At \
        -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema');")
    (( count > 0 )) || { echo 'Restored database has no application tables.'; exit 1; }
    printf 'PostgreSQL database restored, application tables=%s\n' "$count"
done < "$work/databases.txt"
echo 'PASS: remote file checksums, PostersPlus SQLite/filesystem integrity and Bookorbit PostgreSQL import.'
echo 'Application login, media consistency and functional checks remain to be tested.'
