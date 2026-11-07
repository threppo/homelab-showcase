# Evidence and attribution

Prepared 2026-10-29 from the current working tree of the owner's
`homelab-infrastructure` project, including existing uncommitted changes.
No Git history is included. Source paths below identify provenance within that
project; they are not dependencies or links into a private repository.

| Source | Used for |
| --- | --- |
| `README.md` and `backup/README.md` | Project purpose, broad architecture, backup coverage and validation limits |
| `docs/disaster-recovery-review-2026-09-30.md`, finding 2 | Historical stale-WAL reproduction and misleading integrity result |
| `docs/disaster-recovery-runbook.md`, SQLite recovery guidance | Current recovery preconditions, preservation and application-data checks |
| `scripts/recovery/recovery-functions.sh`, `restore_sqlite` | Inspected implementation; deliberately not exported as executable recovery code |
| `scripts/recovery/test-recovery.py`, SQLite tests | Existing regression evidence; inspiration for the synthetic demonstration |
| `docs/disaster-recovery-drill-2026-10-01.md` | Dated selected recovery results, owner confirmation and scope decision, remaining checks |
| `scripts/backup/homelab-restic-backup.sh`, `run_database_dump` | Copied timeout function excerpt; full backup script omitted |
| `scripts/backup/capture-postersplus-state.sh` | Inspected coherent capture, container/mount checks and failure handling; not exported or executed |
| `scripts/backup/test-dump-timeouts.py` | Adapted five-test local timeout suite |
| `.github/workflows/validate.yml` and `scripts/validate-repo.sh` | Inspected CI/local checks; no claim of a new full repository validation |
| `docs/deploy-recovery-backup.md` | Distinction between local checks, deployment and backup verification |
| `stacks/monitoring/docker-compose.yml` | Generic monitoring components, not a published configuration |
| `AGENTS.md` and `docs/skills/adaptive-delegation/SKILL.md` | Evidence rules, bounded supporting inspection and validation limits |
| Dated dashboard-authentication repair record, 2026-10-27 (omitted from this export) | Dated authentication diagnosis, focused repair and real integration-route check |
| `docs/security-maintenance-2026-10-23.md` | Dated staged maintenance, data-preservation checks, compatibility feedback and unresolved limits |
| Dated connectivity record, 2026-10-07 (omitted from this export) | Layered reachability diagnosis and limits of router/upstream evidence |
| Dated routing record, 2026-10-07 (omitted from this export) | Dedicated routing design, human setup input, failure test and lifecycle caveat |
| `docs/postersplus-deployment.md` | Connected renderer integration, owner choices, coherent capture and 2026-10-10 restore/render result |
| `stacks/bookorbit/docker-compose.yml` and override | Frontend/database networking, health dependency and selected restrictions |
| `stacks/gateway/docker-compose.yml` | Tunnel pattern |
| Compose file of one stack (omitted from this export) | Shared-VPN-namespace pattern |
| `stacks/aiometadata/docker-compose.yml`, `stacks/immich/docker-compose.yml` | Application/cache/database/search and worker relationships |
| `stacks/admin/README.md`, `stacks/admin/docker-compose.yml` | Dashboard integrations, private access and administrative socket exposure |
| `systemd/homelab-restic-backup.service` and timer | Scheduling, restrictive process umask and overall job timeout |
| Current chat | Owner's system-orchestration/AI-use account and feedback; Codex's preparation and validation |

The timeout excerpt retains its original function and comments. The timeout test
adaptation changes only its source-loading block to read the adjacent excerpt.
The SQLite demo is newly generated for this export, inspired by the repository
regression and dated review; it is not a copy of the production restore helper.
The network sketch is a newly prepared, incomplete adaptation of relationships
in the application, gateway and VPN Compose files (the VPN file is not in this
export). Its image values and labels
are clearly marked examples. The pipeline is an explanatory summary, not copied
operational code. Generic labels replace application-specific detail in narrative
summaries. The owner's stated AI use is attributed to their account; the dated
records support the described implementations and outcomes without establishing
exact historical assistant identities or command authorship.
No historical reports, operational inventories, private logs or media datasets
are copied into this export.

No project-level LICENSE or NOTICE file was found during inspection, and the
selected source files contain no explicit license notice. No third-party license
grant is inferred or added. Original project attribution is retained here and in
the examples. Before any separate public publication, the owner should confirm
rights to copied code and choose suitable licensing; nothing was published by
this task. Software product names are used descriptively, without endorsement.

## Actual source snapshot

The revised export now includes the [sanitized original repository](repository/README.md),
not only explanatory excerpts. The [manifest](export-manifest.json) identifies
the copied files. Source paths in the table above refer to that snapshot where
included; excluded historical reports remain source evidence for the summaries.
[Export notes](EXPORT.md) explain omissions and value substitutions. One stack and
its dated records were removed from this public copy on 2026-11-07; the rows marked
as omitted above describe records no longer included.
