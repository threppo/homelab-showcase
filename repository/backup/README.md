> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# Backup configuration

This directory is the canonical source of sanitized backup configuration.
`scripts/backup/` contains executable backup code only. The duplicate source and
SQLite lists formerly kept there have been consolidated here.

| Repository file | Installed location |
| --- | --- |
| `backup/backup-sources.txt` | `/etc/example-homelab/backup-sources.txt` |
| `backup/backup-excludes.txt` | `/etc/example-homelab/backup-excludes.txt` |
| `backup/sqlite-databases.conf` | `/etc/example-homelab/sqlite-databases.conf` |
| `backup/backup.env.example` | Template for `/etc/example-homelab/backup.env` |
| `backup/homelab-s3.env.example` | Template for `/etc/example-restic/homelab-s3.env` |
| `scripts/backup/homelab-restic-backup.sh` | `/usr/local/sbin/homelab-restic-backup.sh` |
| `scripts/backup/capture-postersplus-state.sh` | `/usr/local/sbin/homelab-capture-postersplus-state.sh` (root-owned, mode 0700) |

Changes in Git do not update the installed files. Before deployment, an
administrator must compare the installed configuration with these files and
preserve any newer production entries. Never replace a working credentials file
with an example template.

## Coverage and retirement

- Bookorbit PostgreSQL is dumped logically; its running raw data directory is
  excluded. Its isolated database restore passed on 2026-09-30, but restored
  application login, progress and media checks are still outstanding.
- Five SQLite databases are listed, including PostersPlus. Each is copied
  through SQLite's backup API and checked before upload. PostersPlus also needs
  its matching captured settings/artwork/font files, as described below.
- LumiereDB data at `/srv/example-app-data/lumiere-db` is intentionally excluded.
  It contains downloadable IMDb source datasets and a generated index, not
  user-authored state. A fresh install downloads the datasets and rebuilds the
  index. The first production build completed in 2m32s on 2026-10-04; download
  time and end-to-end recovery time were not measured. The exact indexed dataset
  is not recoverable, so rebuilt results can reflect newer upstream IMDb data.
  Keep the path in `backup/backup-excludes.txt`; do not add it to backup sources
  unless the service stops being reproducible from upstream data.
- XRDB is removed from the active backup and recovery configuration. Historical
  snapshots and dated restore evidence remain subject to existing retention.
- Arcane data, `/srv/example-library` except listed media/download exclusions, PostersPlus
  state and the other configured sources remain covered.

## Verification

The backup script also records original SQLite UID/GID/mode in
`current/system/sqlite-ownership.conf` and selected container-to-image repository
digests in `current/system/docker-recovery-images.json`. Neither inventory
includes environment values or credentials. Deploy the updated backup script
to obtain these artifacts in future snapshots; older snapshots use the manual
image/ownership review described in the recovery runbook. A failed optional
image inventory is reported as a warning and requires that manual fallback.

The reviewed `scripts/recovery/` helpers are for administrator-run recovery,
not automatic deployment. Keep them with the offline runbook. Local regression
checks run with `python3 scripts/recovery/test-recovery.py` and do not access
Docker or production data.

From the repository root, run `./scripts/validate-repo.sh` to check repository
syntax, Compose templates and the absence of duplicate backup configuration.
This does not establish production backup coverage.

To verify production, compare the installed script and lists with the reviewed
repository versions, run a complete backup after deployment, and inspect the
snapshot for Bookorbit and both PostersPlus database/filesystem artifacts. The audit account
cannot read protected backup credentials or installed lists; an administrator
must perform those checks without exposing secrets.

The backup script's `--dry-run` still creates database dumps and temporary files
and sends a Discord notification by default. It is not a read-only audit command.
Use `--no-notify` to suppress all Discord notifications for that invocation; it
may be combined with `--dry-run` and does not edit installed configuration.

When a `postersplus` SQLite entry is activated, install the capture helper and
updated backup script together. The helper validates the canonical bind mount,
briefly stops the exact container, captures its SQLite database and matching
settings/artwork/fonts, and resumes it only if it was originally running. A
capture or restart failure fails the backup. Generated caches are omitted;
unknown files are retained conservatively. `--dry-run` also performs this
capture and may briefly stop PostersPlus. The snapshot contains
`current/sqlite/postersplus.sqlite` and
`current/applications/postersplus/cache/`. Restore both together with the app
stopped, preserving numeric ownership. Exclude the live
`/srv/example-app-data/postersplus/cache` only when this capture hook is installed;
otherwise that exclusion would omit durable settings. The canonical SQLite map
still points at `/srv/example-app-data/postersplus/cache/cache.db`.

Run `python3 scripts/backup/test-postersplus-capture.py` for mocked capture and
notification checks; these do not access production, Docker or the network.

See [the audit — omitted from export](../docs/OMITTED.md) and
[the recovery runbook](../docs/disaster-recovery-runbook.md).
