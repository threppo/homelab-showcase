#!/usr/bin/env bash

set -Eeuo pipefail

ok() {
    printf 'OK: %s\n' "$*"
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

ROOT_DIR=$(
    git rev-parse --show-toplevel 2>/dev/null
) || fail "Run this script from inside the Git repository"

cd "$ROOT_DIR"

for command_name in \
    bash \
    git \
    docker \
    find \
    grep \
    sort \
    cp \
    mktemp \
    dirname \
    basename \
    mkdir \
    rm
do
    command -v "$command_name" >/dev/null 2>&1 ||
        fail "Required command not found: $command_name"
done

docker compose version >/dev/null 2>&1 ||
    fail "Docker Compose plugin is not available"

ok "required commands are available"

for config_name in backup-sources.txt backup-excludes.txt sqlite-databases.conf; do
    [[ -f "backup/$config_name" ]] ||
        fail "canonical backup configuration missing: backup/$config_name"
    [[ ! -e "scripts/backup/$config_name" ]] ||
        fail "duplicate backup configuration: scripts/backup/$config_name; use backup/"
done

ok "single canonical backup configuration directory"

mapfile -d '' shell_files < <(
    git ls-files \
        -z \
        -c \
        -o \
        --exclude-standard \
        -- '*.sh' |
    sort -zu
)

for file in "${shell_files[@]}"; do
    bash -n "$file" ||
        fail "shell syntax check failed: $file"
done

ok "shell syntax"

EMPTY_TREE=$(
    git hash-object -t tree /dev/null
)

(
    TEMP_INDEX=$(mktemp)

    cleanup_index() {
        rm -f "$TEMP_INDEX"
    }

    trap cleanup_index EXIT

    rm -f "$TEMP_INDEX"

    GIT_INDEX_FILE="$TEMP_INDEX" \
        git read-tree HEAD ||
        fail "failed to create temporary Git index"

    GIT_INDEX_FILE="$TEMP_INDEX" \
        git add -A -- . ||
        fail "failed to add working-tree files to temporary Git index"

    GIT_INDEX_FILE="$TEMP_INDEX" \
        git diff \
            --cached \
            --check \
            "$EMPTY_TREE" \
            -- ||
        fail "working-tree whitespace errors detected"
)

git diff --check ||
    fail "unstaged whitespace errors detected"

git diff --cached --check ||
    fail "staged whitespace errors detected"

ok "Git whitespace checks"

bad_files=()

while IFS= read -r -d '' file; do
    case "$file" in
        *.env.example | \
        *.env.*.example | \
        *.example.env | \
        */secrets/*.example)
            continue
            ;;
    esac

    case "$file" in
        *.env | \
        *.env.* | \
        *.key | \
        *.pem | \
        *.p12 | \
        *.pfx | \
        *.crt | \
        */secrets/*.txt | \
        *.sql | \
        *.sql.gz | \
        *.dump | \
        *.backup)
            bad_files+=("$file")
            ;;
    esac
done < <(
    git ls-files \
        -z \
        -c \
        -o \
        --exclude-standard |
    sort -zu
)

if ((${#bad_files[@]} > 0)); then
    printf 'Files that look like secrets or backup data:\n' >&2
    printf '  %s\n' "${bad_files[@]}" >&2

    fail "potential sensitive files detected"
fi

ok "no sensitive files are tracked or pending"

TEMP_DIR=$(
    mktemp -d
)

TEMP_REPO="$TEMP_DIR/repository"

cleanup() {
    rm -rf "$TEMP_DIR"
}

trap cleanup EXIT

mkdir -p "$TEMP_REPO"

while IFS= read -r -d '' file; do
    [[ -e "$file" ]] ||
        fail "repository file is missing from working tree: $file"

    mkdir -p "$TEMP_REPO/$(dirname "$file")"

    cp -a \
        -- "$file" \
        "$TEMP_REPO/$file"
done < <(
    git ls-files \
        -z \
        -c \
        -o \
        --exclude-standard
)

mapfile -d '' compose_files < <(
    find "$TEMP_REPO/stacks" \
        -type f \
        \( \
            -name 'compose.yaml' \
            -o -name 'compose.yml' \
            -o -name 'docker-compose.yaml' \
            -o -name 'docker-compose.yml' \
        \) \
        -print0 |
    sort -z
)

((${#compose_files[@]} > 0)) ||
    fail "no Compose files found"

for compose_file in "${compose_files[@]}"; do
    stack_dir=$(dirname "$compose_file")
    compose_name=$(basename "$compose_file")

    while IFS= read -r -d '' example_file; do
        example_name=$(basename "$example_file")

        case "$example_name" in
            *.example.env)
                target_name="${example_name%.example.env}.env"
                ;;

            *.example)
                target_name="${example_name%.example}"
                ;;

            *)
                fail "unsupported environment example name: $example_name"
                ;;
        esac

        cp \
            -- "$example_file" \
            "$stack_dir/$target_name"
    done < <(
        find "$stack_dir" \
            -maxdepth 1 \
            -type f \
            \( \
                -name '.env.example' \
                -o -name '.env.*.example' \
                -o -name '*.env.example' \
                -o -name '*.example.env' \
            \) \
            -print0
    )

    if [[ -d "$stack_dir/secrets" ]]; then
        while IFS= read -r -d '' secret_example; do
            secret_name=$(basename "$secret_example")
            target_name="${secret_name%.example}.txt"

            cp \
                -- "$secret_example" \
                "$stack_dir/secrets/$target_name"
        done < <(
            find "$stack_dir/secrets" \
                -maxdepth 1 \
                -type f \
                -name '*.example' \
                -print0
        )
    fi

    relative_file=${compose_file#"$TEMP_REPO/"}

    (
        cd "$stack_dir"

        docker compose \
            -f "$compose_name" \
            config \
            --quiet
    ) || fail "Compose validation failed: $relative_file"

    ok "$relative_file"

    if [[ -f "$stack_dir/docker-compose.override.yml" &&
          "$compose_name" == "docker-compose.yml" ]]; then
        (
            cd "$stack_dir"

            docker compose \
                -f "$compose_name" \
                -f docker-compose.override.yml \
                config \
                --quiet
        ) || fail "Compose validation failed with override: $relative_file"

        ok "$relative_file + docker-compose.override.yml"
    fi
done

mapfile -d '' markdown_files < <(
    git ls-files \
        -z \
        -c \
        -o \
        --exclude-standard \
        -- '*.md' |
    sort -zu
)

for file in "${markdown_files[@]}"; do
    backtick_fences=$(
        grep -Ec \
            '^[[:space:]]*`{3,}' \
            "$file" ||
        true
    )

    tilde_fences=$(
        grep -Ec \
            '^[[:space:]]*~{3,}' \
            "$file" ||
        true
    )

    if ((backtick_fences % 2 != 0)); then
        fail "unclosed backtick Markdown code fence: $file"
    fi

    if ((tilde_fences % 2 != 0)); then
        fail "unclosed tilde Markdown code fence: $file"
    fi
done

ok "Markdown code fences"
ok "repository validation completed successfully"
