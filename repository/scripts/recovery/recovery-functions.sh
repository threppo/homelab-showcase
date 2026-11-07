#!/usr/bin/env bash
# Source in the recovery shell. Sourcing this file performs no operations.

RECOVERY_DIR=${RECOVERY_DIR:-/var/tmp/example-homelab-recovery}
STACKS_ROOT=${STACKS_ROOT:-/opt/example-stacks}
RECOVERY_STACKS=(admin aiometadata arcane bookorbit gateway immich jikan monitoring postersplus stirling-pdf syncthing streaming)

recovery_compose() (
    set -Eeuo pipefail
    local stack=$1 base pins
    shift
    [[ " ${RECOVERY_STACKS[*]} " == *" $stack "* ]] || { echo 'Unknown recovery stack' >&2; exit 1; }
    cd "$STACKS_ROOT/$stack"
    if [[ -f compose.yaml ]]; then base=compose.yaml; else base=docker-compose.yml; fi
    local args=(-f "$base")
    if [[ $stack == bookorbit ]]; then args+=(-f docker-compose.override.yml); fi
    pins=$RECOVERY_DIR/images/$stack.json
    # JSON is valid YAML. Every service must be pinned, with recovery restart disabled.
    sudo jq -e '.services | length > 0 and all(.[];
        (.image | test("@sha256:[0-9a-f]{64}$")) and
        .pull_policy == "never" and .restart == "no")' "$pins" >/dev/null
    local expected actual
    expected=$(sudo docker compose "${args[@]}" config --services | sort)
    actual=$(sudo jq -r '.services | keys[]' "$pins" | sort)
    [[ $expected == "$actual" ]] || { echo "Incomplete image pins: $stack" >&2; exit 1; }
    sudo docker compose "${args[@]}" -f "$pins" "$@"
)

wait_recovery_container() (
    set -Eeuo pipefail
    local container=$1 state
    for attempt in {1..60}; do
        state=$(sudo docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")
        case "$state" in
            'running healthy'|'running none') return 0 ;;
            exited*|dead*) break ;;
        esac
        sleep 2
    done
    sudo docker inspect --format '{{json .State}}' "$container" >&2
    sudo docker logs --tail 50 "$container" >&2
    echo "Readiness failed: $container" >&2
    exit 1
)

restore_sqlite() (
    set -Eeuo pipefail
    local backup=$1 target=$2 uid=$3 gid=$4 staged old result suffix
    command -v fuser >/dev/null
    [[ $uid =~ ^[0-9]+$ && $gid =~ ^[0-9]+$ ]]
    sudo test -s "$backup"
    sudo test -d "$(dirname "$target")"
    # This is an independent SQLite online backup, never an arbitrary raw DB copy.
    result=$(sudo sqlite3 -readonly "$backup" 'PRAGMA integrity_check;')
    [[ $result == ok ]] || { echo "Invalid SQLite backup: $backup" >&2; exit 1; }
    for suffix in '' -wal -shm -journal; do
        if sudo test -e "$target$suffix"; then
            if sudo fuser -s -- "$target$suffix"; then
                echo "SQLite is still in use: $target$suffix" >&2
                exit 1
            else
                local rc=$?
                [[ $rc == 1 ]] || { echo 'Cannot establish SQLite quiescence' >&2; exit 1; }
            fi
        fi
    done
    staged=$(sudo mktemp "${target}.restore.XXXXXXXX")
    trap 'sudo rm -f -- "$staged"' EXIT
    sudo cp -- "$backup" "$staged"
    sudo chown "$uid:$gid" "$staged"
    sudo chmod 600 "$staged"
    # Preserve the entire old generation, including any uncheckpointed WAL.
    old=$(sudo mktemp -d "${target}.before-restore.XXXXXXXX")
    for suffix in '' -wal -shm -journal; do
        if sudo test -e "$target$suffix"; then
            sudo mv -- "$target$suffix" "$old/"
        fi
    done
    sudo mv -- "$staged" "$target"
    result=$(sudo sqlite3 -readonly "$target" 'PRAGMA integrity_check;')
    [[ $result == ok ]]
    printf 'OK: %s; previous generation: %s\n' "$target" "$old"
)

restore_postgres() (
    set -Eeuo pipefail
    local stack=$1 service=$2 container=$3 archive=$4 pgdata=$5
    local bootstrap override database owner ready=false report
    # Refuse to import over an initialized cluster. Quarantine it first, if needed.
    if sudo test -e "$pgdata/PG_VERSION"; then
        echo "Existing PostgreSQL cluster: $pgdata; preserve it before recovery" >&2
        exit 1
    fi
    sudo gzip -t "$archive"
    database=$(recovery_compose "$stack" config --format json | jq -er --arg s "$service" '.services[$s].environment.POSTGRES_DB')
    owner=$(recovery_compose "$stack" config --format json | jq -er --arg s "$service" '.services[$s].environment.POSTGRES_USER')
    bootstrap=restore_admin_$(date +%s)_${RANDOM}
    override=$RECOVERY_DIR/$stack.bootstrap.json
    jq -n --arg s "$service" --arg u "$bootstrap" \
        '{services:{($s):{environment:{POSTGRES_USER:$u,POSTGRES_DB:"postgres"}}}}' |
        sudo tee "$override" >/dev/null
    # Use the same pinned image, mounts, password and PGDATA as the final service.
    recovery_compose "$stack" -f "$override" up -d --no-deps "$service"
    for attempt in {1..60}; do
        if sudo timeout 5s docker exec "$container" sh -ec '
            export PGPASSWORD="$POSTGRES_PASSWORD"
            psql -X -w -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres -At -c "SELECT 1"
        ' >/dev/null 2>&1; then ready=true; break; fi
        sleep 2
    done
    [[ $ready == true ]] || { sudo docker logs --tail 50 "$container" >&2; exit 1; }
    report=$RECOVERY_DIR/$stack.postgres-import.log
    # A different bootstrap name avoids CREATE ROLE conflicts without suppressing errors.
    sudo gzip -cd "$archive" |
        sudo timeout 30m docker exec -i "$container" sh -ec '
            export PGPASSWORD="$POSTGRES_PASSWORD"
            exec psql -X -w -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1
        ' >"$report" 2>&1
    # Verify the expected DB owner and at least one populated application table.
    report=$RECOVERY_DIR/$stack.postgres-data.txt
    sudo docker exec -i "$container" psql -X -w -U "$bootstrap" -d "$database" \
        -v ON_ERROR_STOP=1 -v expected_db="$database" -v expected_owner="$owner" >"$report" <<'SQL'
SELECT 1 / count(*) FROM pg_database
 WHERE datname = :'expected_db' AND pg_get_userbyid(datdba) = :'expected_owner';
SELECT extname, extversion FROM pg_extension ORDER BY extname;
SELECT 1 / count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema');
CREATE TEMP TABLE recovery_counts(name text, rows bigint);
SELECT format('INSERT INTO recovery_counts SELECT %L, count(*) FROM %I.%I;',
              schemaname || '.' || tablename, schemaname, tablename)
FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')
ORDER BY schemaname, tablename \gexec
SELECT * FROM recovery_counts ORDER BY name;
SELECT 1 / count(*) FROM recovery_counts WHERE rows > 0;
SQL
    # Review the report against the expected users/assets/books/progress before startup.
    sudo docker exec "$container" psql -X -w -U "$bootstrap" -d postgres \
        -v ON_ERROR_STOP=1 -c "ALTER ROLE $bootstrap NOLOGIN;" >/dev/null
    recovery_compose "$stack" up -d --no-deps --force-recreate "$service"
    wait_recovery_container "$container"
    echo "Imported $stack; review protected report: $report"
)
