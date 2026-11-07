> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# Homelab disaster recovery runbook

Last full documented recovery verification: 2026-09-04
Documentation and inventory audit: 2026-09-29 (no new restore drill)
Bookorbit PostgreSQL and XRDB SQLite restore drill: 2026-09-30 (passed)
Independent Oracle ARM64 recovery drill: 2026-10-01 (databases, media integrity and Bookorbit playback passed; limited application scope)
Procedure corrections: 2026-10-01 (see the [drill report — omitted from export](OMITTED.md))
Active recovery configuration: 2026-10-10 (PostersPlus replaces XRDB)
PostersPlus remote restore/render: 2026-10-10 (snapshot `EXAMPLE_SNAPSHOT_ID`, matching database/settings/artwork, all three AIOMetadata profiles and a decoded 500x750 poster passed; see the [deployment record](postersplus-deployment.md))

## Current migration and recovery gaps

Bookorbit is the active replacement for Grimmory and Audiobookshelf. The two old
applications and BookLore MariaDB were stopped on 2026-09-30 after a final
archive and verified remote snapshot; their local application data was then
deleted. PostersPlus became the primary poster provider on 2026-10-09. The current
recovery target includes PostersPlus and excludes XRDB. Bookorbit and PostersPlus
Compose definitions are tracked, but production `.env` values are not.
Bookorbit's database restore drill passed; login, audiobook playback,
seeking and position persistence also passed on an independent Oracle host on
2026-10-01. Other application workflows remain partly unverified. See [audit findings — omitted from export](OMITTED.md) and the
[retirement procedure — omitted from export](OMITTED.md).

The historical backup extension added a Bookorbit PostgreSQL dump and XRDB SQLite
copies. The 2026-09-30 remote-snapshot drill verified all three
file checksums, both SQLite databases and PostgreSQL import with 153 application
tables. The test was repeated successfully after removal of the retired stack
using snapshot `EXAMPLE_SNAPSHOT_ID`. See the
[Bookorbit and XRDB backup guide — omitted from export](OMITTED.md). Grimmory and
Audiobookshelf are not part of the current recovery path. Their former Compose
definition and restore instructions remain available in Git history. The owner
does not require permanent retention of their final snapshot.

The commands below cover the 12 recovery stacks in this public copy (one further
stack is omitted from the export), including Bookorbit
and PostersPlus. PostersPlus requires its online SQLite copy and matching
filesystem state from the same snapshot, created after its 2026-10-09 backup
activation. XRDB is not part of the current recovery path; the older XRDB drill
remains historical evidence only.
The procedure was exercised against a remote snapshot on a replacement ARM64
host on 2026-10-01. This exposed additional bootstrap and cache-recovery steps
documented below. The [drill report — omitted from export](OMITTED.md) records
the tested scope and remaining checks; this was not a full production cutover.

## Purpose

This document describes recovery of the Debian homelab after:

- accidental file deletion
- application database corruption
- Docker stack failure
- disk failure
- complete loss of the server

The procedure assumes that the Restic repository in Backblaze B2 is available.

## Recovery status

Previously recorded as verified (not repeated in the 2026-09-29 audit):

- Restic repository access
- complete homelab backup
- Restic repository check
- restore of a real ebook-library file
- byte-for-byte comparison of the restored file
- restore of a Docker Compose file
- post-migration backup containing `/srv/example-library`
- repository-to-production configuration comparison

Previously recorded isolated recovery drills:

- AIOStreams application state and SQLite restore
- BookLore MariaDB import with table and row-count verification
- Immich PostgreSQL import with roles, extensions and row-count verification
- Jikan MongoDB restore with collection counts and full validation
- seven SQLite databases covered by the historical drill, with `PRAGMA quick_check`; the current recovery procedure in this public copy covers five active databases (one omitted stack's entries are not shown)
- final staged disaster recovery restore from snapshot `EXAMPLE_SNAPSHOT_ID`, including SHA-256 verification, database archive validation and repository validation at a historical source revision (Git history excluded)

## Important limitations

The following directories are intentionally excluded from the remote backup:

- `/srv/example-library/audiobooks`
- `/srv/example-library/downloads`
- `/opt/example-stacks/jikan/data` — raw MongoDB, Redis and Typesense state; MongoDB is restored from its dump, Redis is disposable, and Typesense is rebuilt when required

Audiobooks must be restored from the Windows Syncthing mirror or another local copy.

Files in the downloads directory are considered replaceable and may be missing after recovery.

Do not start Syncthing with an empty `/srv/example-library/audiobooks` directory while the server folder is configured as Send Only. Restore the audiobook files first or temporarily change the Syncthing folder directions.

Generated caches, machine-learning models, Redis state and rebuildable indexes may not be present in the backup.

LumiereDB at `/srv/example-app-data/lumiere-db` is intentionally excluded. It contains
upstream-downloadable IMDb datasets and a generated index, with no user-authored
state. On a full recovery, recreate the directory with the runtime UID/GID and let
the service download current datasets and rebuild. The first production build
completed in 2m32s on 2026-10-04. Treat 2m32s as an observed rebuild component,
not a bound or full-host RTO; image pull and data-download time were not measured,
so total LumiereDB recovery time remains unknown. Its state RPO is intentionally
waived: no exact snapshot of the IMDb dataset is retained, and rebuilt results
may reflect newer upstream data. Service availability resumes only after
`/readyz` returns HTTP 200 and search/catalog checks pass. Do not report the
full-host RTO as verified until this rebuild step is timed in an isolated drill.

Prometheus configuration is backed up with the monitoring stack, but time-series data in the external volume `example_prometheus_data` is intentionally not backed up. Historical metrics are considered disposable; Prometheus starts with an empty data set after a full recovery.

## Required offline information

The following items must exist outside the Restic repository because they are required to open it:

- Restic repository URL
- Restic password
- Backblaze B2 S3 access key ID
- Backblaze B2 S3 secret key
- Backblaze region and endpoint
- GitHub account access
- Debian installation media
- a copy of this runbook and the reviewed `scripts/recovery/` directory
- the approved recovery Git commit, image digests and expected application data counts
- access to the Windows audiobook mirror

The production Restic environment file is:

`/etc/example-restic/homelab-s3.env`

A separate offline copy of its values must be maintained securely. The file is also included in complete encrypted snapshots as part of `/etc/example-restic`, but that internal copy cannot bootstrap access to the repository that contains it.

## Production layout

- Docker stacks: `/opt/example-stacks`
- shared book data: `/srv/example-library`
- Immich originals: `/srv/example-photos/immich/library`
- Immich PostgreSQL data: `/srv/example-photos/immich/postgres`
- AIOMetadata data: `/srv/example-app-data/aiometadata/data`
- LumiereDB rebuildable data (excluded): `/srv/example-app-data/lumiere-db`
- infrastructure repository used by the tracked backup configuration: `/home/EXAMPLE_OWNER/homelab-infrastructure` (presence not verified by the audit account)
- audit checkout: `/home/EXAMPLE_REVIEWER/projects/homelab-infrastructure` (not included in the tracked backup sources)
- backup configuration: `/etc/example-homelab`
- Restic configuration: `/etc/example-restic`
- backup script: `/usr/local/sbin/homelab-restic-backup.sh`
- current database dumps: `/var/backups/example-homelab/current`
- Grafana data: `/var/lib/docker/volumes/example_grafana_data/_data`
- AIOStreams data: `/opt/example-stacks/streaming/data/aiostreams`
- Arcane application data: `/srv/example-app-data/arcane`

The shared external Docker network is:

`example-shared-network`

## Backup contents

The documented backup design includes the following. Current snapshot coverage
must be checked against the installed configuration; see the
[canonical configuration guide](../backup/README.md).

- Docker Compose files
- production `.env` files and application secrets
- application configuration
- ebook library
- Immich originals
- Homepage configuration
- monitoring configuration
- Grafana dashboards, datasources and SQLite state
- PostgreSQL dump for Bookorbit
- PostgreSQL dump for Immich
- MongoDB dump for Jikan
- online SQLite backups
- systemd backup units
- backup scripts
- selected system configuration
- Git infrastructure repository
- SSH configuration

Database dump files:

- `databases/bookorbit-postgres.sql.gz`
- `databases/immich-postgres.sql.gz`
- `databases/jikan-mongodb.archive.gz`

SQLite backup files:

- `sqlite/uptime-kuma.sqlite`
- `sqlite/aiometadata.sqlite`
- `sqlite/grafana.sqlite`
- `sqlite/aiostreams.sqlite`
- `sqlite/postersplus.sqlite`
- matching PostersPlus filesystem state: `applications/postersplus/cache/`

## Selecting a snapshot

Always use a snapshot tagged:

- `homelab`
- `automatic`
- `complete`

Do not automatically choose an untagged or partial snapshot.

```bash
sudo -i

set -a
source /etc/example-restic/homelab-s3.env
set +a

restic snapshots \
  --host example-host \
  --tag 'homelab,automatic,complete'
```

Select an explicit snapshot ID:

```bash
SNAPSHOT=REPLACE_WITH_SNAPSHOT_ID
```

Verify the repository before a full restore:

```bash
restic check
```

## Restoring one file or directory

Create a temporary restore directory:

```bash
sudo install -d -m 700 /var/tmp/homelab-restore
```

Load the Restic environment:

```bash
sudo -i

set -a
source /etc/example-restic/homelab-s3.env
set +a

SNAPSHOT=REPLACE_WITH_SNAPSHOT_ID
```

Restore one file:

```bash
restic restore "$SNAPSHOT" \
  --target /var/tmp/homelab-restore \
  --include /srv/example-library/library/path/to/file
```

Compare before replacing production data:

```bash
sha256sum \
  /srv/example-library/library/path/to/file \
  /var/tmp/homelab-restore/srv/example-library/library/path/to/file
```

Remove the temporary restore directory after validation:

```bash
rm -rf /var/tmp/homelab-restore
```

## Full server recovery

### Recovery scope and quiescence

Use the full procedure on a fresh host. For a single lost file, use the earlier
file-restore section. For corruption on an existing host, first preserve the
current state and stop the affected applications; do not import cluster dumps
into an existing schema. A full in-place recovery requires a maintenance window
and stopping all containers before copying data.

On an existing host, run this in a root Bash maintenance shell:

```bash
sudo -i
set -Eeuo pipefail
umask 077
systemctl stop homelab-restic-backup.timer
systemctl stop homelab-restic-backup.service
# Scope: full-host recovery. This stops every running container on this host.
mapfile -t running < <(docker ps -q)
if (( ${#running[@]} )); then
  docker update --restart=no "${running[@]}"
  docker stop --time 60 "${running[@]}"
fi
test -z "$(docker ps -q)"
systemctl stop docker.service docker.socket
exit
```

Keep Docker's existing `/var/lib/docker` separate from replacement-host recovery.
Do not restore it from the snapshot. On an in-place recovery the restart policy
changes above prevent old applications from restarting with the daemon; verify
that no containers are running again when Docker is restarted. Do not reboot
or re-enable unattended updates during recovery. Save existing application
state, Compose/environment files and databases in protected rollback storage
before replacing them. If a previous import fails, preserve its cluster and
restart from a fresh cluster; never retry over a partially imported schema.


### 1. Install the base system

Install Debian and create the normal user:

- username: `example-owner`
- UID: `1000`
- GID: `1000`
- hostname: `example-host`


Configure networking:

- use DHCP for the actual NIC identified by `ip -brief link`; `enp7s0` below is an example
- do not configure a static IPv4 address in Debian
- if a stable LAN address is needed, create a DHCP reservation on the router
- remote administration should use Tailscale / MagicDNS rather than relying on the LAN address

Example `/etc/network/interfaces`:

```text
source /etc/network/interfaces.d/*

auto lo
iface lo inet loopback

auto enp7s0
iface enp7s0 inet dhcp

iface enp7s0 inet6 auto
```

The actual LAN address depends on the network and may change when the server is moved.


Install required tools:

```bash
sudo apt update

sudo apt install -y \
  ca-certificates \
  curl \
  git \
  gzip \
  jq \
  restic \
  rsync \
  sqlite3 \
  psmisc \
  python3 \
  util-linux
```

Install Docker Engine and the Docker Compose v2 plugin.

Verify:

```bash
docker --version
docker compose version
restic version
```

Reinstall Tailscale and authenticate the new host. Tailscale runtime identity is not part of the documented backup set.

### 2. Bootstrap Restic access

Create the Restic configuration directory:

```bash
sudo install -d -m 700 /etc/example-restic

sudo nano /etc/example-restic/homelab-s3.env
```

Enter the offline-stored values:

```bash
RESTIC_REPOSITORY=REPLACE_ME
RESTIC_PASSWORD=REPLACE_ME
AWS_ACCESS_KEY_ID=REPLACE_ME
AWS_SECRET_ACCESS_KEY=REPLACE_ME
AWS_DEFAULT_REGION=REPLACE_ME
```

Protect the file:

```bash
sudo chmod 600 /etc/example-restic/homelab-s3.env
```

Test repository access:

```bash
sudo bash -c '
set -a
source /etc/example-restic/homelab-s3.env
set +a

restic snapshots \
  --host example-host \
  --tag "homelab,automatic,complete"
'
```

### 3. Restore into a staging directory

Do not initially restore directly over /. Use a dedicated staging directory and
confirm its filesystem has space for the snapshot. Destination filesystems also
need space for restored files, imported databases and retained rollback copies.
Inspect `df -h`, `df -i` and `findmnt` before downloading or copying. Do not
write media to an unmounted mountpoint on the root disk.

From this point, use one root Bash shell with `set -Eeuo pipefail` and `umask 077`.
A failed command ends the recovery shell. Resolve the failure before continuing;
do not blindly paste the next block. On re-entry, use the instructions below to
reload the reviewed helper and variables. Files under `/var/tmp/example-homelab-recovery`
survive shell exits; shell variables and functions do not.

```bash
sudo install -d -m 700 /mnt/homelab-restore

sudo -i
set -Eeuo pipefail
umask 077

set -a
source /etc/example-restic/homelab-s3.env
set +a

SNAPSHOT=REPLACE_WITH_SNAPSHOT_ID
install -d -m 700 /var/tmp/example-homelab-recovery
restic snapshots "$SNAPSHOT" --json > /var/tmp/example-homelab-recovery/snapshot.json
jq -e 'length == 1 and (.[0] | .hostname == "example-host" and
  ((.tags // []) | index("homelab") != null and index("automatic") != null and index("complete") != null))' \
  /var/tmp/example-homelab-recovery/snapshot.json >/dev/null
restic check
restic restore "$SNAPSHOT" \
  --target /mnt/homelab-restore
# Record the full ID independently: .remote-success is written AFTER snapshot creation.
jq -r '.[0].id' /var/tmp/example-homelab-recovery/snapshot.json > /var/tmp/example-homelab-recovery/snapshot.id
base=/mnt/homelab-restore/var/backups/example-homelab/current
(cd "$base" && sha256sum --check SHA256SUMS)
for archive in bookorbit-postgres.sql.gz immich-postgres.sql.gz jikan-mongodb.archive.gz; do
  test -s "$base/databases/$archive"
  gzip -t "$base/databases/$archive"
done
for db in uptime-kuma aiometadata grafana aiostreams postersplus; do
  test -s "$base/sqlite/$db.sqlite"
  test "$(sqlite3 -readonly "$base/sqlite/$db.sqlite" 'PRAGMA integrity_check;')" = ok
done
```

Remain in this root shell for the remaining steps. Install the reviewed recovery
code from the offline copy or a checkout at the approved commit into
`/var/tmp/example-homelab-recovery/source`. Do not use an older helper from the restored
snapshot without reviewing it. Then load it:

```bash
source /var/tmp/example-homelab-recovery/source/scripts/recovery/recovery-functions.sh
```

#### Contract of recovery-functions.sh

Keep the reviewed helper with the offline runbook at the same approved Git
commit. The runbook requires the following Bash variables and functions after
sourcing it; they are shell definitions, not exported environment variables.
Sourcing the helper does not start containers or restore data.

| Variable | Default / required value | Purpose |
| --- | --- | --- |
| `RECOVERY_DIR` | `/var/tmp/example-homelab-recovery` | Protected image overrides, snapshot ID and reports |
| `STACKS_ROOT` | `/opt/example-stacks` | Restored Compose project directories |
| `RECOVERY_STACKS` | Bash array: `admin aiometadata arcane bookorbit gateway immich jikan monitoring postersplus stirling-pdf syncthing streaming` | All 12 stack directories in this public copy |

`RECOVERY_DIR` and `STACKS_ROOT` may be set before sourcing for an isolated drill.
The production commands in this runbook use the default paths.

| Function signature | Preconditions and behavior |
| --- | --- |
| `recovery_compose STACK [COMPOSE_ARGUMENTS...]` | Requires restored Compose files and a complete `$RECOVERY_DIR/images/STACK.json`; includes Bookorbit's override, requires image digests, `pull_policy: never` and `restart: no`, then invokes Compose. Its effects depend on the requested command. |
| `wait_recovery_container CONTAINER_NAME_OR_ID` | Requires an existing container; polls up to 60 times with two-second sleeps for running/healthy, or running without a healthcheck. Reports state/logs and fails if readiness is not reached. This does not verify application data. |
| `restore_sqlite BACKUP_FILE TARGET_FILE UID GID` | Requires an independent online backup, an existing target directory, numeric ownership and no process using the old database. Checks integrity, preserves the previous database/sidecars, installs mode 600 with the supplied owner and checks integrity again. |
| `restore_postgres STACK SERVICE CONTAINER ARCHIVE PGDATA_DIRECTORY` | Requires a gzip cluster dump, reviewed pins and fresh database storage. Starts only the database service with a separate bootstrap role, imports with SQL error checking, writes owner/extension/row-count reports, disables the bootstrap login and recreates the database service with its normal environment. Never starts the app. |

Each operation returns nonzero on failure. With the required strict Bash settings,
stop recovery and investigate before proceeding; a failed replacement/import
may have left partial state that must be preserved and inspected. Prerequisite
tools are installed in step 1. `restore_sqlite_with_recorded_owner`, defined
later in the SQLite section, is a runbook wrapper rather than part of this helper.

#### Re-entering the recovery shell

After a successful staging restore and installation of the reviewed helper,
resume with the following block. If `snapshot.id` is absent, return to step 3
and determine whether the staging restore completed; do not invent a successful
checkpoint. This block restores shell context, not confirmation that every
previous operation passed.

```bash
sudo -i
set -Eeuo pipefail
umask 077
set -a
source /etc/example-restic/homelab-s3.env
set +a
source /var/tmp/example-homelab-recovery/source/scripts/recovery/recovery-functions.sh
SNAPSHOT=$(cat "$RECOVERY_DIR/snapshot.id")
[[ $SNAPSHOT =~ ^[0-9a-f]{64}$ ]]
base=/mnt/homelab-restore/var/backups/example-homelab/current
```

Restart at the last uncompleted step and review its preconditions. Section-local
variables such as `grafana_data` are recomputed where needed below. The SQLite
wrapper must also be defined again by executing its definition when resuming
that section. Do not rerun completed database imports against initialized storage.

The SHA256 manifest covers generated dump/inventory files, not all snapshot
media. No import is allowed unless all checks above pass.

### 4. Restore main directories

Stop Docker before copying application state:

```bash
sudo systemctl stop docker.service docker.socket
```

Restore Docker stacks:

```bash
sudo install -d /opt/example-stacks

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/opt/example-stacks/ \
  /opt/example-stacks/
```

Restore book data:

```bash
sudo install -d /srv/example-library

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/srv/example-library/ \
  /srv/example-library/
```

Restore Immich originals:

```bash
sudo install -d /srv/example-photos/immich/library

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/srv/example-photos/immich/library/ \
  /srv/example-photos/immich/library/
```

Restore AIOMetadata data:

```bash
sudo install -d /srv/example-app-data/aiometadata/data

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/srv/example-app-data/aiometadata/data/ \
  /srv/example-app-data/aiometadata/data/
```

LumiereDB data is deliberately absent from the snapshot. Read `PUID` and `PGID`
from the restored AIOMetadata `.env`, then create an empty directory with that
numeric owner. The example assumes 1000:1000. Do not restore a stale or partial
index: LumiereDB downloads current IMDb datasets and publishes a new index.

```bash
# Replace 1000:1000 with the numeric PUID:PGID values from the restored .env.
sudo install -d -o 1000 -g 1000 -m 0750 /srv/example-app-data/lumiere-db
```

Restore Arcane application data:

```bash
sudo install -d /srv/example-app-data/arcane

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/srv/example-app-data/arcane/ \
  /srv/example-app-data/arcane/
```

PostersPlus was added on 2026-10-09. Its live cache tree is excluded only because
the backup hook stages a matching database and authored-filesystem generation
under `current`. Restore the staged files, not the excluded live tree. Keep
PostersPlus stopped until its independent SQLite copy is installed later:

```bash
sudo test -d /mnt/homelab-restore/var/backups/example-homelab/current/applications/postersplus/cache
sudo install -d -m 0700 /srv/example-app-data/postersplus/cache
sudo rsync -aHAX --numeric-ids \
  /mnt/homelab-restore/var/backups/example-homelab/current/applications/postersplus/cache/ \
  /srv/example-app-data/postersplus/cache/
```

The staged filesystem's permissions/owners and online SQLite copy are restored
together. The pinned PostersPlus entrypoint fixes runtime cache ownership before
dropping privileges. Provider/admin/access keys remain in the backed-up private
`/opt/example-stacks/postersplus/.env`; never substitute the public example file.

Restore the infrastructure repository:

```bash
sudo install -d -o example-owner -g example-owner \
  /home/EXAMPLE_OWNER/homelab-infrastructure

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/home/EXAMPLE_OWNER/homelab-infrastructure/ \
  /home/EXAMPLE_OWNER/homelab-infrastructure/
```

Restore SSH files:

```bash
sudo install -d -o example-owner -g example-owner -m 700 \
  /home/EXAMPLE_OWNER/.ssh

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/home/EXAMPLE_OWNER/.ssh/ \
  /home/EXAMPLE_OWNER/.ssh/
```

Restore backup configuration:

```bash
sudo install -d -m 700 \
  /etc/example-homelab \
  /etc/example-restic

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/etc/example-homelab/ \
  /etc/example-homelab/

sudo rsync -aHAX \
  --numeric-ids \
  --exclude='homelab-s3.env' \
  /mnt/homelab-restore/etc/example-restic/ \
  /etc/example-restic/
```

The `homelab-s3.env` file is excluded from this rsync because it was created manually in step 2 from the offline-stored credentials and has already been verified by opening the repository.

The snapshot also contains `/etc/example-restic`, including the copy of `homelab-s3.env` that existed when the backup was created. That copy may be older than the credentials used for the current recovery and must not overwrite the verified bootstrap file. The offline copy remains mandatory because the repository cannot be opened to retrieve its internal copy until valid credentials are already available.

Restore scripts:

```bash
sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/usr/local/sbin/ \
  /usr/local/sbin/
```

Restore current database dumps:

```bash
sudo install -d -m 700 /var/backups/example-homelab/current

sudo rsync -aHAX \
  --numeric-ids \
  /mnt/homelab-restore/var/backups/example-homelab/current/ \
  /var/backups/example-homelab/current/
```

Do not blindly restore the whole /etc directory over a newly installed system.

Restore only reviewed files such as the backup units:

```bash
sudo install -m 644 \
  /mnt/homelab-restore/etc/systemd/system/homelab-restic-backup.service \
  /etc/systemd/system/homelab-restic-backup.service

sudo install -m 644 \
  /mnt/homelab-restore/etc/systemd/system/homelab-restic-backup.timer \
  /etc/systemd/system/homelab-restic-backup.timer
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

### 5. Restore audiobook media before Syncthing

The remote Restic backup does not contain audiobook payload files.

Restore:

```bash
/srv/example-library/audiobooks
```

from the Windows Syncthing mirror or another local backup.

Do not start the server-side Syncthing container while the directory is empty and configured as Send Only.

Confirm the Syncthing marker exists:

```bash
sudo test -d /srv/example-library/audiobooks/.stfolder
```

Create it when necessary:

```bash
sudo install -d \
  -o example-owner \
  -g example-owner \
  -m 755 \
  /srv/example-library/audiobooks/.stfolder
```

### 6. Start Docker and create external Docker resources

```bash
sudo systemctl enable --now docker
test -z "$(sudo docker ps -q)"
```

Create the external network when it does not exist:

```bash
sudo docker network inspect example-shared-network \
  >/dev/null 2>&1 ||
sudo docker network create example-shared-network
```

Create the external volumes used by the monitoring stack when they do not exist:

```bash
sudo docker volume inspect example_grafana_data \
  >/dev/null 2>&1 ||
sudo docker volume create example_grafana_data

sudo docker volume inspect example_prometheus_data \
  >/dev/null 2>&1 ||
sudo docker volume create example_prometheus_data
```

These volumes must exist before the monitoring stack is started or before the Grafana SQLite database can be created and restored.

### 7. Restore Grafana files and pin recovery images

Copy Grafana state into the prepared external volume, without its raw database:

```bash
grafana_data=$(sudo docker volume inspect -f '{{.Mountpoint}}' example_grafana_data)
sudo rsync -aHAX --numeric-ids --exclude='grafana.db*' \
  /mnt/homelab-restore/var/lib/docker/volumes/example_grafana_data/_data/ \
  "$grafana_data/"
```

Create one recovery override per stack under `/var/tmp/example-homelab-recovery/images`.
Use digests recorded in the selected snapshot, never today's `latest` or `nightly`.
New backups capture `system/docker-recovery-images.json` after the updated backup
script is deployed:

```bash
python3 /var/tmp/example-homelab-recovery/source/scripts/recovery/prepare-image-pins.py \
  /var/backups/example-homelab/current/system/docker-recovery-images.json \
  /var/tmp/example-homelab-recovery/images
```

For older snapshots lacking that JSON, use `system/docker-containers.txt` and
`system/docker-images.txt` to map each Compose service to its recorded repository
digest. Save manually reviewed JSON overrides with the following structure
for **every** service, replacing the example digest. Project names may differ
from stack directory names (especially stacks without `name:`); name each file
for its directory, e.g. `postersplus.json`, after reviewing the generated mapping.
A local image ID (`sha256:...`) is not generally a pullable registry digest.
The 2026-10-01 snapshot had five empty `repo_digests` entries. Their recorded
image IDs happened to identify registry manifests: each was verified with
`docker manifest inspect --verbose REPOSITORY@RECORDED_IMAGE_ID`, including
ARM64 availability, before use. Keep the original inventory, record this
registry evidence and generate pins from a separately reviewed inventory.
Do not blindly substitute local image IDs for missing repository digests.
If verification fails, stop and recover an archived image or qualify another
version in an isolated restore first. The pin generator intentionally refuses
unverified missing digests.

```json
{
  "services": {
    "postersplus": {
      "image": "ghcr.io/umbraprojects/postersplus@sha256:REPLACE_WITH_64_HEX_DIGEST",
      "pull_policy": "never",
      "restart": "no"
    }
  }
}
```

Pull each reviewed digest explicitly, then validate all configurations:

```bash
for stack in "${RECOVERY_STACKS[@]}"; do
  recovery_compose "$stack" config --quiet
  while IFS= read -r image; do
    sudo docker pull "$image"
  done < <(sudo jq -r '.services[].image' "$RECOVERY_DIR/images/$stack.json")
done
```

All subsequent Compose commands use `recovery_compose`, which requires a digest
for every service, includes Bookorbit's base and override, disables automatic
pulls and uses `restart: no`. Do not replace it with a plain `docker compose up`
during recovery. Restore application databases before starting applications.
SQLite apps are **not** started to create empty databases.

## Database restoration

### Fresh PostgreSQL storage

Both imports below require empty PostgreSQL data. On a new host the excluded
raw data should be absent. On an existing host, first stop all relevant
containers, then preserve the old directories instead of deleting them.
Before executing, confirm the paths match restored production `.env` values,
including Immich's `DB_DATA_LOCATION`; adjust these paths if needed:

```bash
stamp=$(date +%Y%m%dT%H%M%S)
for path in /opt/example-stacks/bookorbit/data/postgres /srv/example-photos/immich/postgres; do
  if sudo test -d "$path" && sudo find "$path" -mindepth 1 -print -quit | grep -q .; then
    sudo test ! -e "$path.before-restore.$stamp"
    sudo mv -- "$path" "$path.before-restore.$stamp"
  fi
  sudo install -d "$path"
done
```

The helper refuses a cluster with `PG_VERSION`. A fresh bootstrap superuser,
absent from the original dump, avoids duplicate-role conflicts. Initializing
only `postgres` avoids pre-creating the application database. Every SQL error
is fatal (`ON_ERROR_STOP=1`); no errors are ignored. The helper uses the original
pinned image, password and storage, imports the cluster dump, checks the
application database owner and populated tables, saves a per-table count and
extension report, disables login for the temporary role, and recreates only
the DB service with its original environment. The retained NOLOGIN role may
own bootstrap objects; do not blindly drop it.

This follows [PostgreSQL's bootstrap-role guidance](https://www.postgresql.org/docs/18/app-pg-dumpall.html).
Do not restore a cluster archive using a single transaction: it creates databases.

### Bookorbit PostgreSQL

```bash
restore_postgres bookorbit postgres bookorbit-db \
  /var/backups/example-homelab/current/databases/bookorbit-postgres.sql.gz \
  /opt/example-stacks/bookorbit/data/postgres/pgdata
```

Review `/var/tmp/example-homelab-recovery/bookorbit.postgres-data.txt` and the import log.
Check the expected pgvector extension, restored users, books, libraries and
progress against snapshot-time records or known representative entries. The
2026-09-30 test had 153 application tables; that is historical evidence, not
an immutable expected count for future snapshots. Table presence or a positive
row count alone does not establish complete recovery. Start `app` only after
this review; validate login and media access in the final application checks.

### Immich PostgreSQL

```bash
restore_postgres immich database immich_postgres \
  /var/backups/example-homelab/current/databases/immich-postgres.sql.gz \
  /srv/example-photos/immich/postgres
```

Review `/var/tmp/example-homelab-recovery/immich.postgres-data.txt` and the import log.
Check extensions required by the recorded Immich release, users, assets and
albums against known entries and expected counts. Do not start the Immich
server until this passes. The strict import was exercised successfully on
2026-10-01. Follow the [Immich restore prerequisites](https://docs.immich.app/administration/backup-and-restore/)
for the restored release, including regeneration of excluded thumbnails and
encoded video after originals and the database are verified.

Before starting the server, verify that `/srv/example-photos/immich/library` is the
intended restored storage and that its `upload`, `library` and `profile` folders
and existing `.immich` markers are present. Do not create markers on an empty
or incorrectly mounted originals directory. The backup excludes `thumbs`,
`encoded-video` and `backups`; recreate only those derived directories and
their markers using the numeric owner of the verified storage directory:

```bash
immich_storage=/srv/example-photos/immich/library
test -d "$immich_storage"
for directory in upload library profile; do
  test -f "$immich_storage/$directory/.immich"
done
immich_uid=$(stat -c '%u' "$immich_storage")
immich_gid=$(stat -c '%g' "$immich_storage")
for directory in thumbs encoded-video backups; do
  install -d -m 755 -o "$immich_uid" -g "$immich_gid" "$immich_storage/$directory"
  if [[ ! -e "$immich_storage/$directory/.immich" ]]; then
    install -m 644 -o "$immich_uid" -g "$immich_gid" /dev/null \
      "$immich_storage/$directory/.immich"
  fi
done
```

Keep Immich's mount checks enabled. These marker prerequisites follow
[Immich's system-integrity guidance](https://docs.immich.app/administration/system-integrity/).

The excluded `encoded-video` directory can also contain motion clips referenced
as asset originals. On 2026-10-01, all 137 such clips could be reconstructed
exactly from preserved Motion Photo JPGs. Some JPGs contain a trailer after the
MP4: taking the entire suffix did not reproduce their recorded checksum.
After verifying original photos, export the restored database's linked pairs:

```bash
docker exec immich_postgres sh -c '
  PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"
' sh "SELECT json_agg(row_to_json(t)) FROM (
  SELECT parent.\"originalPath\" AS photo, video.\"originalPath\" AS video,
    video.\"checksumAlgorithm\" AS algorithm, encode(video.checksum, 'hex') AS checksum
  FROM asset parent JOIN asset video ON parent.\"livePhotoVideoId\" = video.id
  WHERE video.\"originalPath\" LIKE '/data/encoded-video/%'
    AND parent.\"deletedAt\" IS NULL
) t;" > "$RECOVERY_DIR/immich-motion-pairs.json"
```

The SQL schema and `/data` mapping above match the tested release; review them
against the pinned image and mounts before use. If the result is `null`, no
such pairs exist and this step can be skipped. Otherwise, run a read-only
preflight, then explicitly write only checksum-verified missing clips:

```bash
python3 "$RECOVERY_DIR/source/scripts/recovery/restore-immich-motion.py" \
  "$RECOVERY_DIR/immich-motion-pairs.json" "$immich_storage"
python3 "$RECOVERY_DIR/source/scripts/recovery/restore-immich-motion.py" \
  "$RECOVERY_DIR/immich-motion-pairs.json" "$immich_storage" --apply
```

The helper refuses mismatched existing clips, path escapes and unmatched
checksums. It leaves source photos untouched. A failure means recovery remains
incomplete; obtain another verified copy rather than accepting a different clip.
Recheck all active assets' original-file checksums after reconstruction. Thumbnail
and playback transcode jobs are still needed for excluded previews and other
derived videos; recovering motion originals does not regenerate all caches.

### Jikan MongoDB

For in-place recovery, quarantine the old raw directory before startup. This
must happen while the old container is stopped; it preserves the rollback copy
and avoids a mixed old/new database. The new host normally has no such directory:

```bash
mongo_path=/opt/example-stacks/jikan/data/mongo
if sudo test -d "$mongo_path"; then
  old_mongo="$mongo_path.before-restore.$(date +%Y%m%dT%H%M%S)"
  sudo test ! -e "$old_mongo"
  sudo mv -- "$mongo_path" "$old_mongo"
fi
sudo install -d "$mongo_path"
```

Start only MongoDB:

```bash
recovery_compose jikan up -d --no-deps jikan_mongo
```

Wait for health:

```bash
wait_recovery_container jikan_mongo
```

Restore into the `jikan_mongo` container:

```bash
(
  set -o pipefail

  sudo cat \
    /var/backups/example-homelab/current/databases/jikan-mongodb.archive.gz |
  sudo docker exec -i jikan_mongo sh -lc '
    set -eu
    DB_USER=$(cat /run/secrets/jikan_db_admin_username)
    DB_PASS=$(cat /run/secrets/jikan_db_admin_password)

    mongorestore \
      --username "$DB_USER" \
      --password "$DB_PASS" \
      --authenticationDatabase admin \
      --archive \
      --gzip \
      --drop
  '
)
```

Verify that the `jikan` database contains collections, print their document counts and run full collection validation:

```bash
sudo docker exec jikan_mongo sh -lc '
  DB_USER=$(cat /run/secrets/jikan_db_admin_username)
  DB_PASS=$(cat /run/secrets/jikan_db_admin_password)

  mongosh \
    --quiet \
    --username "$DB_USER" \
    --password "$DB_PASS" \
    --authenticationDatabase admin \
    jikan \
    --eval "
      const names = db.getCollectionNames().sort();

      if (names.length === 0) {
        print(\"ERROR: no collections found\");
        quit(2);
      }

      names.forEach(name => {
        const count = db.getCollection(name).countDocuments({});
        const validation = db.runCommand({validate: name, full: true});

        if (!validation.valid) {
          printjson(validation);
          quit(3);
        }

        print(name + \"\\t\" + count + \"\\tvalid\");
      });
    "
'
```

A historical MongoDB drill passed. The corrected command quoting was checked
locally; rerun the import and compare collection counts with snapshot-time
records in the next isolated drill. If this is an in-place recovery, preserve
and empty the Jikan `data/mongo` directory before starting MongoDB; do not use
`--drop` as a substitute for preserving a rollback copy.

### Jikan Typesense reindex

The excluded Typesense directory must be rebuilt from restored MongoDB, not by
scraping the entire catalogue again. Keep the gateway stopped. Start the pinned
Jikan stack only after MongoDB validation:

```bash
recovery_compose jikan up -d
wait_recovery_container jikan_rest
sudo docker exec -w /app jikan_rest php artisan help scout:import
```

Confirm the installed image exposes the models and command before import.
The model list comes from the [AIOMetadata self-hosted Jikan guide](https://github.com/cedya77/aiometadata/blob/dev/docs/self-hosted-jikan.md#populating-the-index).
The script checks model existence and Mongo counts first; it refuses an empty
collection rather than creating an unusable empty search schema. If some models
are intentionally absent from this snapshot, document that fact and remove only
those from the list; verify the corresponding search endpoint remains usable
before declaring recovery complete. Do not guess schemas from another release.

```bash
for model in Anime Manga Character Person Club Magazine Producers; do
  sudo docker exec -w /app jikan_rest php -r '
    require "vendor/autoload.php";
    $app = require "bootstrap/app.php";
    $app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
    $app->boot();
    $class = "App\\" . $argv[1];
    if (!class_exists($class) || $class::count() === 0) {
      fwrite(STDERR, "Missing or empty model: " . $argv[1] . PHP_EOL);
      exit(1);
    }
  ' "$model"
  sudo timeout 30m docker exec -w /app jikan_rest php artisan scout:import "App\\$model"
done
recovery_compose jikan restart jikan_rest
wait_recovery_container jikan_rest
```

Choose a known restored anime title and its MAL ID from MongoDB and check the
search API from inside Jikan's container. This avoids exposing a public port:

```bash
JIKAN_QUERY=REPLACE_WITH_KNOWN_RESTORED_TITLE
JIKAN_EXPECTED_ID=REPLACE_WITH_KNOWN_MAL_ID
sudo docker exec jikan_rest curl --fail --silent --show-error --max-time 30 \
  --get --data-urlencode "q=$JIKAN_QUERY" --data 'limit=25' \
  http://127.0.0.1:8080/v4/anime > "$RECOVERY_DIR/jikan-search.json"
jq -e --argjson id "$JIKAN_EXPECTED_ID" '.data | any(.mal_id == $id)' \
  "$RECOVERY_DIR/jikan-search.json" >/dev/null
```

Repeat for each populated model's API endpoint and record title/ID, counts,
duration and image digest. Import success alone is insufficient. If an import
or expected search result fails, leave the gateway stopped. Allow up to 30
minutes per model; increase the bound deliberately for a large restored dataset.
The 2026-10-01 drill exercised model checks and imports for Anime, Magazine and
Producers, and verified an anime search result. Calling `$app->boot()` after
kernel bootstrap is required by the pinned Lumen image to initialize Mongo
connections. Other populated models and search endpoints require their own
checks; an empty snapshot model must not be presented as successfully restored.

### SQLite restoration without application startup

Do not start applications to create empty files. Restore independent online
copies directly into the restored data directories. First confirm all related
containers are stopped. Recovering the server must not run application jobs,
notifications or migrations before databases have been installed.

Use the snapshot's restored directory ownership as the initial UID/GID reference.
Review it against the pinned service's runtime user, `PUID`/`PGID` and original
ownership before copying. Grafana normally uses UID 472; verify the restored volume and pinned
image. Do not assign all databases to root merely because backup files are
root-owned. New backups record original database UID/GID/mode in
`current/system/sqlite-ownership.conf` as `name|source|uid|gid|mode`. Use that
record preferentially; for older snapshots use the reviewed directory owner.

```bash
# Recompute after a shell restart; this volume must have been prepared in step 6.
grafana_data=$(sudo docker volume inspect -f '{{.Mountpoint}}' example_grafana_data)
sudo test -d "$grafana_data"

# Quiescent full-host recovery: no SQLite application may be running.
for container in uptime-kuma grafana aiometadata aiostreams postersplus; do
  if sudo docker container inspect "$container" >/dev/null 2>&1; then
    test "$(sudo docker inspect -f '{{.State.Running}}' "$container")" = false
  fi
done

restore_sqlite_with_recorded_owner() {
  local backup=$1 target=$2 name record uid gid
  name=$(basename "$backup" .sqlite)
  if test -f /var/backups/example-homelab/current/system/sqlite-ownership.conf; then
    record=$(awk -F '|' -v name="$name" '$1 == name {print $3 ":" $4}' \
      /var/backups/example-homelab/current/system/sqlite-ownership.conf)
    if [[ -z $record ]]; then
      printf 'ERROR: no recorded owner for %s in sqlite-ownership.conf\n' "$name" >&2
      return 1
    fi
    if [[ $record == *$'\n'* ]]; then
      printf 'ERROR: duplicate recorded owners for %s in sqlite-ownership.conf\n' "$name" >&2
      return 1
    fi
    if [[ ! $record =~ ^[0-9]+:[0-9]+$ ]]; then
      printf 'ERROR: invalid recorded UID/GID for %s in sqlite-ownership.conf\n' "$name" >&2
      return 1
    fi
    uid=${record%:*}
    gid=${record#*:}
  else
    # Older snapshot: use only after reviewing runtime and directory ownership.
    uid=$(sudo stat -c %u "$(dirname "$target")")
    gid=$(sudo stat -c %g "$(dirname "$target")")
  fi
  restore_sqlite "$backup" "$target" "$uid" "$gid"
}

base=/var/backups/example-homelab/current/sqlite
restore_sqlite_with_recorded_owner "$base/uptime-kuma.sqlite" /opt/example-stacks/monitoring/data/uptime-kuma/kuma.db
restore_sqlite_with_recorded_owner "$base/aiometadata.sqlite" /srv/example-app-data/aiometadata/data/db.sqlite
restore_sqlite_with_recorded_owner "$base/grafana.sqlite" "$grafana_data/grafana.db"
restore_sqlite_with_recorded_owner "$base/aiostreams.sqlite" /opt/example-stacks/streaming/data/aiostreams/db.sqlite
restore_sqlite_with_recorded_owner "$base/postersplus.sqlite" /srv/example-app-data/postersplus/cache/cache.db
```

For a recorded database owner differing from its directory owner, call
`restore_sqlite` with the recorded numeric UID/GID instead. Missing parent
directories are a failed restore precondition: investigate rather than inventing
ownership. The helper verifies the backup first, rejects files in use, stages
with the chosen owner and mode 600, preserves the old database **and**
`-wal`/`-shm`/`-journal` together in a unique protected `.before-restore.*`
directory, and only then installs the backup. All sidecars from the previous
generation are moved aside; never remove sidecars of a running database.
A failure during replacement requires inspection of the retained generation
before retrying. All five calls must succeed. Check actual application data
after startup; an integrity check alone does not prove the right data was restored.
An existing ownership file with missing, duplicate or malformed entries is an
error; directory ownership is used only when the entire file is absent from an
older snapshot and that fallback has been reviewed.

## Recommended startup order

After all database restores:

1. `jikan`
2. `immich`
3. `bookorbit`
4. `postersplus`
5. `aiometadata`
6. `monitoring`
7. `admin`
8. `arcane`
9. `stirling-pdf`
10. `syncthing`
11. `streaming`
12. `gateway`

The Cloudflare Tunnel stack should be started last so applications are not exposed before validation.

Start one stack at a time:

```bash
recovery_compose STACK_NAME up -d
```

Wait and inspect before proceeding:

```bash
sudo docker ps \
  --format 'table {{.Names}}\t{{.Status}}'
```

During an isolated drill, keep `gateway` stopped and do not start a Send Only
Syncthing folder with an incomplete audiobook mirror. AIOStreams' public anime
database bootstrap can block startup when internet egress is denied. For a
limited offline readiness test, add `ANIME_DB_LEVEL_OF_DETAIL=none` to the
`aiostreams` service's `environment` in `$RECOVERY_DIR/images/streaming.json`
before starting it. Record this test override and its excluded feature scope.
Remove it only when restoring the intended anime mappings with reviewed network
access; local HTTP readiness alone does not validate external providers.

## Post-recovery validation

### Container state

Require every configured service to exist, be running and, where available,
healthy. Unlike `docker ps`, this detects missing and exited containers:

```bash
for stack in "${RECOVERY_STACKS[@]}"; do
  services=$(recovery_compose "$stack" config --services)
  test -n "$services"
  while IFS= read -r service; do
    cid=$(recovery_compose "$stack" ps -a -q "$service")
    test -n "$cid"
    wait_recovery_container "$cid"
  done <<<"$services"
done
sudo docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
```

Run this final all-stack check after the gateway is started. Before starting the
gateway, perform the same check for the other 11 stacks and complete local
application checks. Record any deliberately disabled service instead of silently
accepting a missing container.


```bash
sudo docker ps \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
```

Check unhealthy containers:

```bash
sudo docker ps \
  --filter health=unhealthy \
  --format 'table {{.Names}}\t{{.Status}}'
```

### Active mount paths

```bash
sudo docker inspect $(sudo docker ps -q) |
jq -r '
  .[] |
  .Name[1:] as $container |
  .Mounts[]? |
  [$container, .Source, .Destination] |
  @tsv
' |
column -t -s $'\t'
```

No active container should mount:

```bash
/opt/example-stacks/example-retired-stack
```

### Data checks

Confirm:

- LumiereDB `/readyz` returns HTTP 200 with `status: ready`; search and the
  Popular catalog return HTTP 200 with nonempty results from inside AIOMetadata.
  Record the start time, readiness time and elapsed rebuild time; compare against
  the 2m32s first production build, noting that upstream download time can vary.
- Bookorbit displays the ebook and audiobook libraries, users and progress
- PostersPlus settings, authored artwork/presets/fonts and corresponding DB rows
  are restored together; an authenticated render works through AIOMetadata's
  public HTTPS image proxy. `/health` alone does not prove rendering or data.
- Jikan search returns expected restored IDs after Typesense import
- AIOMetadata returns expected metadata using restored settings
- audiobook files are present and sampled file checksums match the Windows mirror
- Immich displays photos and albums
- Uptime Kuma monitors are present
- Grafana dashboards and datasources are present
- Syncthing reports the correct audiobook folder
- Cloudflare hostnames resolve to the restored applications
- AIOStreams loads its configuration and Stremio endpoint
- Arcane detects running containers and projects without errors
- Arcane reports available image updates without errors

## Backup verification, normal operation and timer

Keep the timer stopped until a controlled full backup and its snapshot checks
succeed. `Persistent=true` can trigger a missed run immediately on activation.
The dry-run below is **not read-only**: it creates real database dumps, temporary
files and Discord notifications, and requires all three database containers.

```bash
sudo /usr/local/sbin/homelab-restic-backup.sh --dry-run
sudo /usr/local/sbin/homelab-restic-backup.sh
```

Require exit code 0 and `Homelab backup completed successfully`, with
`rc=0, step=complete` in the final log. Inspect the newly created snapshot:

```bash
new_snapshot=$(sudo sed -n 's/^snapshot=//p' /var/backups/example-homelab/current/.remote-success)
[[ $new_snapshot =~ ^[0-9a-f]{64}$ ]]
restic snapshots "$new_snapshot" --json > "$RECOVERY_DIR/new-snapshot.json"
jq -e 'length == 1 and (.[0] | .hostname == "example-host" and
  ((.tags // []) | index("homelab") != null and index("automatic") != null and index("complete") != null))' \
  "$RECOVERY_DIR/new-snapshot.json" >/dev/null
restic ls "$new_snapshot" > "$RECOVERY_DIR/new-snapshot-files.txt"
if grep -F -- '/srv/example-app-data/lumiere-db/' "$RECOVERY_DIR/new-snapshot-files.txt" >/dev/null; then
  echo 'ERROR: LumiereDB rebuildable data unexpectedly present in snapshot' >&2
  exit 1
fi
for artifact in databases/bookorbit-postgres.sql.gz databases/immich-postgres.sql.gz databases/jikan-mongodb.archive.gz \
  sqlite/uptime-kuma.sqlite \
  sqlite/aiometadata.sqlite sqlite/grafana.sqlite sqlite/aiostreams.sqlite \
  sqlite/postersplus.sqlite; do
  grep -F -- "/var/backups/example-homelab/current/$artifact" "$RECOVERY_DIR/new-snapshot-files.txt" >/dev/null
done
grep -F -- '/var/backups/example-homelab/current/applications/postersplus/cache' \
  "$RECOVERY_DIR/new-snapshot-files.txt" >/dev/null
```

Archive the recovery reports and reviewed image overrides securely. Keep the
pinned images for normal operation; do not return to floating tags yet. After
functional validation, change each override's `restart` from `no` to the
service's original policy from the restored Compose, and review the diff.
The following prepares persistent overrides with the original restart policies,
without changing pinned image versions, then recreates each stack. The active
Compose file list remains in Docker's project metadata. Also keep this command
in the operational notes for future manual starts; a plain `up` omits the pins.

```bash
for stack in "${RECOVERY_STACKS[@]}"; do
  cd "/opt/example-stacks/$stack"
  if test -f compose.yaml; then base=compose.yaml; else base=docker-compose.yml; fi
  files=(-f "$base")
  if test "$stack" = bookorbit; then files+=(-f docker-compose.override.yml); fi
  sudo docker compose "${files[@]}" config --format json > "$RECOVERY_DIR/$stack.original.json"
  jq --slurpfile original "$RECOVERY_DIR/$stack.original.json" '
    .services |= with_entries(.key as $service |
      .value.restart = ($original[0].services[$service].restart // "no"))
  ' "$RECOVERY_DIR/images/$stack.json" > "$RECOVERY_DIR/$stack.operational.json"
  sudo install -m 600 "$RECOVERY_DIR/$stack.operational.json" recovery-images.json
  sudo docker compose "${files[@]}" -f recovery-images.json config --quiet
  sudo docker compose "${files[@]}" -f recovery-images.json up -d --pull never
  services=$(sudo docker compose "${files[@]}" -f recovery-images.json config --services)
  while IFS= read -r service; do
    cid=$(sudo docker compose "${files[@]}" -f recovery-images.json ps -a -q "$service")
    test -n "$cid"
    wait_recovery_container "$cid"
  done <<<"$services"
done
```

Enable the timer only after these checks. Updates and Arcane automatic updater actions are a separate
maintenance task; avoid an unplanned upgrade during this transition.

```bash
sudo systemctl enable --now homelab-restic-backup.timer
sudo systemctl status homelab-restic-backup.timer --no-pager
```

## Cleanup after recovery

Only after all applications and backups have been verified:

```bash
sudo rm -rf /mnt/homelab-restore
```

Keep any `.before-restore.*` database directories, old PostgreSQL clusters and recovery reports until the recovered system has completed at least one successful automatic backup.

## Recovery drill schedule

At least every three months:

- run `restic check`
- restore one random ebook file
- restore one Compose file
- restore all SQLite backups into temporary files and run `PRAGMA quick_check`
- test both PostgreSQL imports in isolated temporary containers
- test MongoDB import into an isolated temporary container
- test Jikan Typesense reindex against a restored MongoDB copy and confirm search results are populated
- record the result and date in this document
