# Backup strategy: recover useful state, not just files

I use AI assistance to develop and review backup scripts around the system's
actual dependencies. The repository separates source lists, exclusions, executable
scripts and recovery documentation. Editing these files does not deploy them.

## What is protected

| State | Approach in the inspected repository |
| --- | --- |
| PostgreSQL and MongoDB | Logical dumps rather than relying on a copy of a running raw database directory |
| SQLite | Online database copies followed by checks; special coherent capture for one stateful renderer |
| Configuration and durable files | Selected application/system configuration and authored data included in the encrypted backup set |
| Rebuildable indexes and caches | Deliberately excluded where the documentation explains how they are recreated |
| Large collection outside the main backup | Separate mirror; completeness and reconciliation remain distinct recovery checks |

The backup set can contain private configuration, so encryption and controlled
credential handling matter. This export contains neither backup data nor real
configuration values.

## How the script handles reliability

A daily systemd timer starts the job. A lock prevents overlapping runs. Database
dumps have an inner timeout for the process inside the container and a longer host
timeout for a stalled container connection; the whole job also has a time limit.
The [exported helper and local tests](examples/README.md) demonstrate this part.

Before the prepared set becomes the current local generation, the script checks
for nonempty compressed dumps, validates their archives and looks for PostgreSQL
completion markers. It creates a checksum manifest for generated artifacts and
records selected image/ownership information for recovery. The pipeline is shown
in an [illustrative summary](examples/backup-pipeline.md).

Restic sends encrypted snapshots to off-site object storage. The script marks
partial snapshots separately and gives them a separate retention path. Complete
snapshots use configured recent/daily/weekly/monthly retention; scheduled pruning
and repository checks are included. Status notifications distinguish success,
partial results, failure and an overlapping job being skipped.

A manifest verifies its listed artifacts, not every application behavior or every
file in a snapshot. A repository check is also different from restoring an app.

## Matching database and filesystem state

One rendering service stores durable settings, authored assets and a SQLite
database in a tree that also holds generated caches. Its capture helper briefly
stops the verified container, captures the matching durable files and database,
and resumes it only if it was previously running. Capture or restart failure
fails the backup. Excluding the live cache tree is safe only when this capture
hook stages the durable state elsewhere.

[The case study](case-study.md) describes the dated isolated restore/render check.
The synthetic SQLite demo illustrates a different danger: an old journal can
supply the wrong data even while an integrity check passes.

## Recovery is a separate procedure

The runbook stages a chosen complete snapshot, checks artifacts, reviews image
versions and ownership, restores databases before dependent applications and
checks meaningful user workflows. Old SQLite database generations and sidecars
are preserved rather than silently overwritten. External integrations are brought
back deliberately after internal checks.

The **2026-10-01** replacement-host drill records selected database and application
checks, including my confirmation of login and persisted progress. The
**2026-10-10** component check records restoration of matching renderer state and
a successful rendered image. Neither establishes every workflow, full collection
reconciliation, public cutover, measured total recovery time or guaranteed data-loss
bounds. Current backup coverage was not inspected live for this showcase.
