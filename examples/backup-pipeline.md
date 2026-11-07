# Backup pipeline: illustrative reading guide

This is a prose summary of `scripts/backup/homelab-restic-backup.sh`, its capture
helper and systemd units, not a runnable script or a full recovery procedure.

```text
Scheduled job → acquire lock → check required inputs
  → create restricted temporary staging generation
  → online SQLite copies / coherent application capture
  → logical database dumps with inner and outer time limits
  → nonempty, archive and completion-marker checks
  → image/ownership context and generated-artifact checksum manifest
  → publish prepared local generation
  → encrypted remote snapshot
      partial → label separately, check repository, return partial status
      complete → label complete, apply retention, check repository
  → record success and notify, or report failing stage
```

The local preparation precedes the remote snapshot. A locally prepared generation
is not proof of remote success. The script records remote completion separately
and distinguishes previously successful local state from a failed attempt.

The copied timeout function and adapted tests demonstrate one implementation
component without including the backup entrypoint, secrets, retention commands or
service-stop logic. The SQLite demonstration shows why validating a database's
structure is not enough to establish its expected content.

The source's dry-run mode still prepares real dumps and can pause an application;
it is deliberately not used by this showcase. No operational backup command is
provided here for execution.
