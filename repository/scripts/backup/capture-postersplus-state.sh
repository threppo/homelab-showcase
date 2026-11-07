#!/usr/bin/env bash
# Called by the locked backup job; captures one database/filesystem generation.
set -Eeuo pipefail
umask 077

wait_postersplus_ready() {
    local container=$1 deadline=$((SECONDS+30)) remaining state
    while (( SECONDS < deadline )); do
        remaining=$((deadline-SECONDS))
        state=$(timeout --kill-after=1s "${remaining}s" docker inspect --type container \
            --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
            "$container") || return 1
        case $state in
            'running healthy') return 0 ;;
            exited*|dead*|removing*) break ;;
        esac
        sleep 1
    done
    echo 'ERROR: PostersPlus did not become healthy within 30 seconds' >&2
    return 1
}

resume_postersplus() {
    timeout --kill-after=5s 15s docker start "$1" >/dev/null || return 1
    wait_postersplus_ready "$1"
}

capture_postersplus_state() (
    set -Eeuo pipefail
    (( $# == 3 )) || { echo 'Usage: capture-postersplus-state.sh SOURCE_DB OUTPUT_DB OUTPUT_CACHE' >&2; exit 2; }
    local source=$1 output=$2 target=$3 generation source_dir metadata container resume=false
    for tool in docker jq sqlite3 rsync timeout realpath stat dirname install find chmod rm; do
        command -v "$tool" >/dev/null || { echo "ERROR: missing capture dependency: $tool" >&2; exit 1; }
    done
    source_dir=/srv/example-app-data/postersplus/cache
    [[ $source == "$source_dir/cache.db" && -f $source && ! -L $source &&
       -d $source_dir && ! -L $source_dir && $(realpath "$source_dir") == "$source_dir" ]] || {
        echo 'ERROR: unexpected PostersPlus database source' >&2; exit 1;
    }
    generation=$(dirname "$(dirname "$output")")
    [[ $generation == /* && -d $generation && ! -L $generation &&
       $(realpath "$generation") == "$generation" &&
       $(stat -c '%u:%a' "$generation") == "$EUID:700" &&
       $generation != "$source_dir" && $generation != "$source_dir/"* &&
       $source_dir != "$generation/"* &&
       $output == "$generation/sqlite/postersplus.sqlite" &&
       $target == "$generation/applications/postersplus/cache" &&
       -d $generation/sqlite && ! -L $generation/sqlite &&
       $(stat -c '%u:%a' "$generation/sqlite") == "$EUID:700" &&
       ! -e $output && ! -L $output && ! -e $generation/applications/postersplus &&
       ! -L $generation/applications/postersplus ]] || {
        echo 'ERROR: unsafe or existing PostersPlus capture destination' >&2; exit 1;
    }
    [[ ! -L $generation/applications ]] || { echo 'ERROR: capture parent is a symlink' >&2; exit 1; }
    metadata=$(timeout --kill-after=5s 15s docker inspect --type container --format \
        '{"id":{{json .Id}},"name":{{json .Name}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"running":{{json .State.Running}},"paused":{{json .State.Paused}},"status":{{json .State.Status}},"mounts":{{json .Mounts}}}' \
        postersplus)
    jq -e --arg source "$source_dir" '
        .name == "/postersplus" and .project == "postersplus" and .service == "postersplus" and
        (.id | test("^[0-9a-f]{64}$")) and (.running | type == "boolean") and .paused == false and
        ((.status == "running" and .running) or
         ((.status == "exited" or .status == "created") and (.running | not))) and
        ([.mounts[] | select(.Destination == "/app/cache")] |
            length == 1 and .[0].Type == "bind" and .[0].Source == $source and .[0].RW == true)
    ' <<<"$metadata" >/dev/null || { echo 'ERROR: unexpected PostersPlus container identity or cache mount' >&2; exit 1; }
    container=$(jq -r .id <<<"$metadata")
    resume=$(jq -r .running <<<"$metadata")
    finish_capture() {
        local rc=$?
        trap - EXIT INT TERM
        if [[ $resume == true ]]; then
            if ! resume_postersplus "$container"; then
                echo 'ERROR: PostersPlus could not be resumed; administrator action required' >&2
                rc=1
            fi
        fi
        if (( rc != 0 )); then
            rm -f -- "$output"
            rm -rf -- "$generation/applications/postersplus"
        fi
        exit "$rc"
    }
    trap finish_capture EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    if [[ $resume == true ]]; then
        timeout --kill-after=5s 40s docker stop --time 30 "$container" >/dev/null
    fi
    [[ $(timeout --kill-after=5s 10s docker inspect --type container --format '{{.State.Running}}' "$container") == false ]] || {
        echo 'ERROR: PostersPlus is still running; capture refused' >&2; exit 1;
    }
    install -d -m 0700 "$generation/applications" "$generation/applications/postersplus" "$target"
    sqlite3 -readonly "$source" '.timeout 30000' ".backup '$output'"
    [[ $(sqlite3 -readonly "$output" 'PRAGMA quick_check;') == ok ]] || {
        echo 'ERROR: PostersPlus capture failed SQLite validation' >&2; exit 1;
    }
    rsync -a --numeric-ids \
        --exclude=/cache.db --exclude=/cache.db-wal --exclude=/cache.db-shm --exclude=/cache.db-journal \
        --exclude=/tmdb_posters/ --exclude=/tmdb_logos/ --exclude=/company_logos/ --exclude=/commons/ \
        --exclude=/anime_ids.db --exclude=/anime_ids.db-wal --exclude=/anime_ids.db-shm --exclude=/anime_ids.db-journal \
        --exclude=/imdb_ratings.db --exclude=/imdb_ratings.db-wal --exclude=/imdb_ratings.db-shm --exclude=/imdb_ratings.db-journal \
        -- "$source_dir/" "$target/"
    # Publication keeps staging protected; application ownership remains recorded/preserved.
    chmod 0600 "$output"
    find "$target" -type d -exec chmod 0700 {} +
    find "$target" -type f -exec chmod 0600 {} +
    if [[ $resume == true ]]; then
        resume_postersplus "$container"
        resume=false
    fi
    echo 'PostersPlus database and filesystem generation captured'
)

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    (( EUID == 0 )) || { echo 'ERROR: run as root' >&2; exit 1; }
    capture_postersplus_state "$@"
fi
