#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

RESTIC_ENV=/etc/example-restic/homelab-s3.env
BACKUP_ENV=/etc/example-homelab/backup.env
SOURCES_FILE=/etc/example-homelab/backup-sources.txt
EXCLUDES_FILE=/etc/example-homelab/backup-excludes.txt
SQLITE_MAP=/etc/example-homelab/sqlite-databases.conf

BACKUP_ROOT=/var/backups/example-homelab
CURRENT_DIR=$BACKUP_ROOT/current
PREVIOUS_DIR=$BACKUP_ROOT/previous
FAILED_DIR=$BACKUP_ROOT/failed-latest
LOG_DIR=/var/log/example-homelab
LOG_FILE=$LOG_DIR/homelab-restic-backup.log
LOCK_FILE=/run/lock/homelab-restic-backup.lock
RESTIC_CACHE_DIR=/var/cache/example-restic

MODE=normal
NOTIFICATIONS_DISABLED=false
for option in "$@"; do
    case $option in
        --dry-run) MODE=dry-run ;;
        --no-notify) NOTIFICATIONS_DISABLED=true ;;
        *) echo "Usage: $0 [--dry-run] [--no-notify]" >&2; exit 2 ;;
    esac
done
# The invocation controls notifications, independently of sourced configuration.
readonly NOTIFICATIONS_DISABLED
(( EUID == 0 )) || { echo "ERROR: run as root" >&2; exit 1; }

for cmd in restic curl jq flock gzip sha256sum sqlite3 docker mktemp awk grep find sort xargs du stat hostname timeout install touch chmod tee date rm cp mv; do
    command -v "$cmd" >/dev/null || { echo "ERROR: missing command: $cmd"; exit 1; }
done

install -d -m 700 \
    "$BACKUP_ROOT" \
    "$LOG_DIR" \
    "$RESTIC_CACHE_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

HOST_SHORT=$(hostname -s)
START_EPOCH=$(date +%s)
STEP=initialization
WORK_DIR=
RUNTIME_EXCLUDES=
SNAPSHOT_FULL_ID=
SNAPSHOT_ID=not-created
SQLITE_COUNT=0
BACKUP_SET_SIZE=unknown
BACKUP_PARTIAL=false
PRUNE_STATUS=nie

for file in "$RESTIC_ENV" "$BACKUP_ENV" "$SOURCES_FILE" "$EXCLUDES_FILE" "$SQLITE_MAP"; do
    [[ -r $file ]] || { echo "ERROR: cannot read $file"; exit 1; }
done

set -a
# shellcheck disable=SC1090
source "$RESTIC_ENV"
set +a
# shellcheck disable=SC1090
source "$BACKUP_ENV"

: "${RESTIC_REPOSITORY:?missing RESTIC_REPOSITORY}"
: "${RESTIC_PASSWORD:?missing RESTIC_PASSWORD}"
: "${AWS_ACCESS_KEY_ID:?missing AWS_ACCESS_KEY_ID}"
: "${AWS_SECRET_ACCESS_KEY:?missing AWS_SECRET_ACCESS_KEY}"
: "${AWS_DEFAULT_REGION:?missing AWS_DEFAULT_REGION}"
if [[ $NOTIFICATIONS_DISABLED == false ]]; then
    : "${DISCORD_WEBHOOK_URL:?missing DISCORD_WEBHOOK_URL}"
fi
: "${INFRA_REPO_DIR:?missing INFRA_REPO_DIR}"
: "${HOMELAB_KEEP_LAST:?missing HOMELAB_KEEP_LAST}"
: "${HOMELAB_KEEP_DAILY:?missing HOMELAB_KEEP_DAILY}"
: "${HOMELAB_KEEP_WEEKLY:?missing HOMELAB_KEEP_WEEKLY}"
: "${HOMELAB_KEEP_MONTHLY:?missing HOMELAB_KEEP_MONTHLY}"

for name in HOMELAB_KEEP_LAST HOMELAB_KEEP_DAILY HOMELAB_KEEP_WEEKLY HOMELAB_KEEP_MONTHLY; do
    [[ ${!name} =~ ^[0-9]+$ ]] || { echo "ERROR: $name must be an integer"; exit 1; }
done

RESTIC=(
    restic
    --retry-lock 5m
    --cache-dir "$RESTIC_CACHE_DIR"
)

notify() {
    [[ $NOTIFICATIONS_DISABLED == false ]] || return 0
    local message=$1
    message=${message//\\n/$'\n'}
    jq -n --arg content "$message" '{content:$content,allowed_mentions:{parse:[]}}' |
        curl -fsS --retry 3 --retry-all-errors --retry-delay 3 --max-time 20 \
            -H 'Content-Type: application/json' --data-binary @- \
            "${DISCORD_WEBHOOK_URL}?wait=true" >/dev/null ||
        echo "WARNING: Discord notification failed"
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    notify "⚠️ **Backup homelaba pominięty**\nHost: \`${HOST_SHORT}\`\nPowód: inny backup już działa."
    exit 0
fi

finish() {
    local rc=$? end duration
    trap - EXIT INT TERM
    [[ -z $WORK_DIR || ! -d $WORK_DIR ]] || rm -rf -- "$WORK_DIR"
    [[ -z $RUNTIME_EXCLUDES || ! -f $RUNTIME_EXCLUDES ]] || rm -f -- "$RUNTIME_EXCLUDES"
    end=$(date +%s)
    duration="$(((end-START_EPOCH)/60))m $(((end-START_EPOCH)%60))s"

    echo "Finished: $(date --iso-8601=seconds), rc=$rc, step=$STEP"

    if [[ $MODE == dry-run ]]; then
        if (( rc == 0 )); then
            notify "🧪 **Test backupu homelaba poprawny**\nHost: \`${HOST_SHORT}\`\nSQLite: ${SQLITE_COUNT}\nZestaw: ${BACKUP_SET_SIZE}\nCzas: ${duration}"
        else
            notify "❌ **Test backupu homelaba nieudany**\nHost: \`${HOST_SHORT}\`\nEtap: \`${STEP}\`\nKod: \`${rc}\`\nLog: \`${LOG_FILE}\`"
        fi
    elif (( rc == 0 )); then
        notify "✅ **Backup homelaba zakończony**\nHost: \`${HOST_SHORT}\`\nSnapshot: \`${SNAPSHOT_ID}\`\nZestaw: ${BACKUP_SET_SIZE}\nSQLite: ${SQLITE_COUNT}\nPrune: ${PRUNE_STATUS}\nCzas: ${duration}"
    elif (( rc == 3 )) && [[ $BACKUP_PARTIAL == true ]]; then
        notify "⚠️ **Backup homelaba częściowy**\nHost: \`${HOST_SHORT}\`\nSnapshot: \`${SNAPSHOT_ID}\`\nSprawdź: \`${LOG_FILE}\`"
    else
        notify "❌ **Backup homelaba nieudany**\nHost: \`${HOST_SHORT}\`\nEtap: \`${STEP}\`\nKod: \`${rc}\`\nLog: \`${LOG_FILE}\`"
    fi
    exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo
echo "=== Homelab backup: $(date --iso-8601=seconds), mode=$MODE ==="

require_container() {
    [[ $(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true) == true ]] || {
        echo "ERROR: container not running: $1"
        exit 1
    }
}

optional_capture() {
    local output=$1 description=$2 rc
    shift 2
    if "$@" >"$output" 2>&1; then
        return 0
    else
        rc=$?
    fi
    echo "WARNING: $description failed (rc=$rc)" >&2
    printf '\nCollection failed: %s (rc=%s)\n' "$description" "$rc" >>"$output"
}

backup_sqlite() {
    local name source output result ownership
    STEP='SQLite backups'
    while IFS='|' read -r name source || [[ -n ${name}${source} ]]; do
        name=${name%$'\r'}
        source=${source%$'\r'}
        [[ -z $name || $name =~ ^[[:space:]]*# ]] && continue
        [[ $name =~ ^[A-Za-z0-9._-]+$ ]] || { echo "ERROR: invalid SQLite name: $name"; exit 1; }
        [[ -f $source ]] || { echo "ERROR: missing SQLite DB: $source"; exit 1; }
        ownership=$(stat -c '%u|%g|%a' "$source")
        printf '%s|%s|%s\n' "$name" "$source" "$ownership" \
            >>"$WORK_DIR/system/sqlite-ownership.conf"

        output=$WORK_DIR/sqlite/$name.sqlite
        if [[ $name == postersplus ]]; then
            local capture_helper=/usr/local/sbin/homelab-capture-postersplus-state.sh
            [[ -f $capture_helper && ! -L $capture_helper &&
               $(stat -c '%u:%a' "$capture_helper") == 0:700 ]] || {
                echo 'ERROR: missing root-owned PostersPlus capture helper'; exit 1;
            }
            bash "$capture_helper" "$source" "$output" "$WORK_DIR/applications/postersplus/cache"
        else
            sqlite3 "$source" '.timeout 30000' ".backup '$output'"
        fi
        result=$(sqlite3 "$output" 'PRAGMA quick_check;')
        [[ $result == ok ]] || { echo "ERROR: SQLite check failed: $name"; echo "$result"; exit 1; }
        chmod 600 "$output"
        SQLITE_COUNT=$((SQLITE_COUNT+1))
        echo "SQLite OK: $name"
    done <"$SQLITE_MAP"
}

run_database_dump() {
    local container=$1 script=$2
    # The inner timeout terminates the dump process group inside the container.
    # The longer host limit also bounds a stalled Docker API/exec connection.
    timeout --kill-after=30s 32m docker exec "$container" sh -c '
        command -v timeout >/dev/null 2>&1 || {
            echo "ERROR: timeout is required inside the database container" >&2
            exit 127
        }
        exec timeout -k 30s 30m sh -lc "$1"
    ' sh "$script"
}

dump_databases() {
    STEP='Immich PostgreSQL dump'
    require_container immich_postgres
    run_database_dump immich_postgres '
        set -eu
        export PGPASSWORD="${POSTGRES_PASSWORD:?}"
        pg_dumpall --username="${POSTGRES_USER:?}"
    ' | gzip -1 >"$WORK_DIR/databases/immich-postgres.sql.gz"

    STEP='Bookorbit PostgreSQL dump'
    require_container bookorbit-db
    run_database_dump bookorbit-db '
        set -eu
        if [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
            PGPASSWORD=$(cat "$POSTGRES_PASSWORD_FILE")
        else
            PGPASSWORD=${POSTGRES_PASSWORD:-}
        fi
        export PGPASSWORD
        pg_dumpall --no-password --username="${POSTGRES_USER:-postgres}"
    ' | gzip -1 >"$WORK_DIR/databases/bookorbit-postgres.sql.gz"

    STEP='Jikan MongoDB dump'
    require_container jikan_mongo
    run_database_dump jikan_mongo '
        set -eu
        DB_USER=$(cat /run/secrets/jikan_db_admin_username)
        DB_PASS=$(cat /run/secrets/jikan_db_admin_password)
        mongodump --username "$DB_USER" --password "$DB_PASS" \
          --authenticationDatabase admin --archive --gzip
    ' >"$WORK_DIR/databases/jikan-mongodb.archive.gz"

    chmod 600 "$WORK_DIR"/databases/*
}

validate_dumps() {
    local file
    STEP='database dump validation'
    for file in "$WORK_DIR"/databases/*; do
        [[ -s $file ]] || { echo "ERROR: empty dump: $file"; exit 1; }
        gzip -t "$file"
    done
    gzip -cd "$WORK_DIR/databases/immich-postgres.sql.gz" |
        grep -E '^-- PostgreSQL database cluster dump complete$' >/dev/null || {
            echo 'ERROR: Immich dump is not a complete pg_dumpall archive'; exit 1;
        }
    gzip -cd "$WORK_DIR/databases/bookorbit-postgres.sql.gz" |
        grep -E '^-- PostgreSQL database cluster dump complete$' >/dev/null || {
            echo 'ERROR: Bookorbit dump is not a complete pg_dumpall archive'; exit 1;
        }
    echo 'Database dumps OK'
}

capture_recovery_images() (
    set -Eeuo pipefail
    local ids id metadata image_id digests
    ids=$(docker ps -aq) || exit 1
    [[ -n $ids ]] || { echo 'No containers to inventory' >&2; exit 1; }
    for id in $ids; do
        metadata=$(docker inspect --format '{"container":{{json .Name}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"image_id":{{json .Image}},"image_reference":{{json .Config.Image}}}' "$id") || exit 1
        image_id=$(jq -er '.image_id' <<<"$metadata") || exit 1
        digests=$(docker image inspect --format '{{json .RepoDigests}}' "$image_id") || exit 1
        jq --argjson digests "$digests" '. + {repo_digests:($digests // [])}' <<<"$metadata" || exit 1
    done | jq -s .
)

inventory() {
    STEP='system inventory'
    local dir=$WORK_DIR/system
    date --iso-8601=seconds >"$dir/created-at.txt"
    hostname >"$dir/hostname.txt"
    cp "$SOURCES_FILE" "$dir/backup-sources.txt"
    cp "$EXCLUDES_FILE" "$dir/backup-excludes.txt"
    cp "$SQLITE_MAP" "$dir/sqlite-databases.conf"

    optional_capture "$dir/docker-compose-ls.json" 'docker compose inventory' docker compose ls --format json
    optional_capture "$dir/docker-containers.txt" 'docker container inventory' \
        docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}'
    optional_capture "$dir/docker-images.txt" 'Docker image inventory' \
        docker image ls --digests --no-trunc
    optional_capture "$dir/docker-recovery-images.json" 'Recovery image digest inventory' \
        capture_recovery_images
    optional_capture "$dir/systemd-timers.txt" 'systemd timer inventory' systemctl list-timers --all --no-pager

    if [[ -d $INFRA_REPO_DIR/.git ]]; then
        optional_capture "$dir/infrastructure-git-commit.txt" 'Git commit inventory' \
            git -c safe.directory="$INFRA_REPO_DIR" -C "$INFRA_REPO_DIR" rev-parse HEAD
        optional_capture "$dir/infrastructure-git-status.txt" 'Git status inventory' \
            git -c safe.directory="$INFRA_REPO_DIR" -C "$INFRA_REPO_DIR" status --short
    fi
}

checksums() {
    STEP='checksums'
    (
        cd "$WORK_DIR"
        find . -type f ! -name SHA256SUMS -print0 |
            sort -z | xargs -0 -r sha256sum >SHA256SUMS
    )
    chmod 600 "$WORK_DIR/SHA256SUMS"
}

load_sources() {
    STEP='source validation'
    mapfile -t BACKUP_SOURCES < <(
        awk 'NF && $0 !~ /^[[:space:]]*#/ {sub(/\r$/,""); print}' "$SOURCES_FILE"
    )
    (( ${#BACKUP_SOURCES[@]} > 0 )) || { echo 'ERROR: no backup sources'; exit 1; }
    for path in "${BACKUP_SOURCES[@]}"; do
        [[ -e $path ]] || { echo "ERROR: missing source: $path"; exit 1; }
        [[ $path != "$CURRENT_DIR" ]] || {
            echo "ERROR: remove $CURRENT_DIR from $SOURCES_FILE"
            exit 1
        }
    done
}

prepare_excludes() {
    RUNTIME_EXCLUDES=$(mktemp /run/homelab-excludes.XXXXXX)
    awk 'NF && $0 !~ /^[[:space:]]*#/ {sub(/\r$/,""); print}' \
        "$EXCLUDES_FILE" >"$RUNTIME_EXCLUDES"
    chmod 600 "$RUNTIME_EXCLUDES"
}

publish_current() {
    STEP='local backup publication'
    if [[ -d $CURRENT_DIR ]]; then
        if [[ -f $CURRENT_DIR/.remote-success ]]; then
            rm -rf -- "$PREVIOUS_DIR"
            mv "$CURRENT_DIR" "$PREVIOUS_DIR"
        else
            rm -rf -- "$FAILED_DIR"
            mv "$CURRENT_DIR" "$FAILED_DIR"
        fi
    fi
    mv "$WORK_DIR" "$CURRENT_DIR"
    WORK_DIR=
    find "$CURRENT_DIR" -type d -exec chmod 700 {} +
    find "$CURRENT_DIR" -type f -exec chmod 600 {} +
    BACKUP_SET_SIZE=$(du -sh "$CURRENT_DIR" | awk '{print $1}')
}

latest_snapshot() {
    local json
    json=$("${RESTIC[@]}" snapshots --host "$HOST_SHORT" \
        --tag 'homelab,automatic' --json)

    SNAPSHOT_FULL_ID=$(jq -er \
        'if length > 0 then max_by(.time).id else error("no snapshot") end' \
        <<<"$json")

    SNAPSHOT_ID=${SNAPSHOT_FULL_ID:0:8}
}
load_sources
prepare_excludes
WORK_DIR=$(mktemp -d "$BACKUP_ROOT/.work.XXXXXX")
install -d -m 700 "$WORK_DIR/sqlite" "$WORK_DIR/databases" "$WORK_DIR/system"

backup_sqlite
dump_databases
validate_dumps
inventory
checksums

if [[ $MODE == dry-run ]]; then
    BACKUP_SET_SIZE=$(du -sh "$WORK_DIR" | awk '{print $1}')
    BACKUP_SOURCES+=("$WORK_DIR")
else
    publish_current
    BACKUP_SOURCES+=("$CURRENT_DIR")
fi

STEP='Restic backup'
ARGS=(backup --host "$HOST_SHORT" --exclude-file "$RUNTIME_EXCLUDES" --tag homelab --tag automatic)
[[ $MODE == dry-run ]] && ARGS+=(--dry-run)
ARGS+=("${BACKUP_SOURCES[@]}")

set +e
"${RESTIC[@]}" "${ARGS[@]}"
RC=$?
set -e

if [[ $MODE == dry-run ]]; then
    (( RC == 0 )) || { echo "ERROR: restic dry-run rc=$RC"; exit "$RC"; }
    STEP='dry-run complete'
    echo 'Restic dry-run completed successfully'
    exit 0
fi

case $RC in
    0) ;;
    3) BACKUP_PARTIAL=true ;;
    *) echo "ERROR: restic backup rc=$RC"; exit "$RC" ;;
esac

STEP='snapshot identification'
latest_snapshot

echo "Snapshot: $SNAPSHOT_ID"
if [[ $BACKUP_PARTIAL == true ]]; then
    STEP='partial snapshot tagging'
    "${RESTIC[@]}" tag --add partial "$SNAPSHOT_FULL_ID"
    latest_snapshot
    STEP='repository check after partial backup'
    "${RESTIC[@]}" check
    exit 3
fi

STEP='complete snapshot tagging'
"${RESTIC[@]}" tag --add complete "$SNAPSHOT_FULL_ID"
latest_snapshot
echo "Final snapshot: $SNAPSHOT_ID"

STEP='retention'
"${RESTIC[@]}" forget --host "$HOST_SHORT" \
    --tag 'homelab,automatic,complete' --group-by host \
    --keep-last "$HOMELAB_KEEP_LAST" \
    --keep-daily "$HOMELAB_KEEP_DAILY" \
    --keep-weekly "$HOMELAB_KEEP_WEEKLY" \
    --keep-monthly "$HOMELAB_KEEP_MONTHLY"

PARTIAL_COUNT=$("${RESTIC[@]}" snapshots --host "$HOST_SHORT" \
    --tag 'homelab,automatic,partial' --json | jq length)
if (( PARTIAL_COUNT > 0 )); then
    "${RESTIC[@]}" forget --host "$HOST_SHORT" \
        --tag 'homelab,automatic,partial' --group-by host --keep-last 3
fi

if [[ $(date +%u) == 7 ]]; then
    STEP='repository prune'
    PRUNE_STATUS='w toku'
    "${RESTIC[@]}" prune
    PRUNE_STATUS=tak
fi

STEP='repository check'
"${RESTIC[@]}" check

STEP='local success marker'
printf 'snapshot=%s\ncompleted=%s\n' "$SNAPSHOT_FULL_ID" "$(date --iso-8601=seconds)" \
    >"$CURRENT_DIR/.remote-success"
chmod 600 "$CURRENT_DIR/.remote-success"
rm -rf -- "$FAILED_DIR"

STEP=complete
echo 'Homelab backup completed successfully'
