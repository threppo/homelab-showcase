#!/usr/bin/env bash
# Fixture tests only: never invoke Docker or the production backup entry point.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."

if [[ ${1:-} == --case ]]; then
    fixture_mode=$2
    WORK_DIR=$(mktemp -d)
    trap 'rm -rf -- "$WORK_DIR"' EXIT
    mkdir -p "$WORK_DIR/databases"
    # Load function definitions only, stopping before the source-validation function.
    source <(sed -n '/^require_container() {/,/^load_sources() {/p' \
        scripts/backup/homelab-restic-backup.sh | sed '$d')

    # Keep fixtures local: host timeout must call the Docker shell stub.
    timeout() {
        [[ $1 == --kill-after=30s && $2 == 32m ]] || return 97
        shift 2
        "$@"
    }

    docker() {
        if [[ $1 == inspect ]]; then
            printf 'true\n'
            return
        fi
        [[ $1 == exec ]] || return 98
        case $2 in
            immich_postgres)
                [[ $fixture_mode != immich-dump-fails ]] || return 23
                printf '%s\n' '-- PostgreSQL database cluster dump'
                if [[ $fixture_mode != immich-incomplete ]]; then
                    printf '%s\n' '-- PostgreSQL database cluster dump complete'
                fi
                ;;
            bookorbit-db)
                [[ $fixture_mode != dump-fails ]] || return 23
                printf '%s\n' '-- PostgreSQL database cluster dump'
                if [[ $fixture_mode != incomplete ]]; then
                    printf '%s\n' '-- PostgreSQL database cluster dump complete'
                fi
                ;;
            jikan_mongo) printf 'fixture archive\n' | gzip ;;
            *) return 99 ;;
        esac
    }

    dump_databases
    if [[ $fixture_mode == corrupt ]]; then
        printf 'not gzip\n' > "$WORK_DIR/databases/bookorbit-postgres.sql.gz"
    fi
    validate_dumps
    test -s "$WORK_DIR/databases/bookorbit-postgres.sql.gz"
    test ! -e "$WORK_DIR/databases/booklore.sql.gz"
    exit 0
fi

bash scripts/backup/test-bookorbit-dump.sh --case good
for failure in dump-fails incomplete corrupt immich-dump-fails immich-incomplete; do
    if bash scripts/backup/test-bookorbit-dump.sh --case "$failure"; then
        printf 'ERROR: accepted failure case %s\n' "$failure" >&2
        exit 1
    fi
    printf 'OK: rejected %s\n' "$failure"
done
printf 'OK: Bookorbit dump fixture tests passed\n'
