# What is in this export

The `repository/` directory is a sanitized source snapshot of the actual current
`homelab-infrastructure` working tree, taken on 2026-10-29. It includes existing
uncommitted project work. No Git history or remote configuration is included.
The top-level documents are a portfolio introduction, not replacements for the
implementation. `examples/` retains the earlier small explanatory demonstrations.

## Start with the real files

| To inspect | Original project material, sanitized |
| --- | --- |
| Service definitions and connections | [Compose stacks](repository/stacks/), [gateway](repository/stacks/gateway/docker-compose.yml), [application/database example](repository/stacks/bookorbit/docker-compose.yml) |
| Dashboard and monitoring | [Dashboard configuration](repository/stacks/admin/homepage/), [monitoring stack](repository/stacks/monitoring/docker-compose.yml) |
| Backup design and implementation | [Backup documentation](repository/backup/README.md), [full backup script](repository/scripts/backup/homelab-restic-backup.sh), [coherent capture helper](repository/scripts/backup/capture-postersplus-state.sh), [timer](repository/systemd/homelab-restic-backup.timer) |
| Recovery | [Runbook](repository/docs/disaster-recovery-runbook.md), [helpers](repository/scripts/recovery/recovery-functions.sh), [regression tests](repository/scripts/recovery/test-recovery.py) |
| Debugging evidence | [Incident summary](troubleshooting.md) (its dated source record is omitted from this export), [deployment and restore record](repository/docs/postersplus-deployment.md) |
| Security implementation | [Security build helpers](repository/scripts/security/), [application restrictions](repository/stacks/bookorbit/docker-compose.yml) |
| Automated checks | [Original validation script](repository/scripts/validate-repo.sh), [original CI workflow](repository/.github/workflows/validate.yml) |

The [manifest](export-manifest.json) lists every copied source file and whether it
was copied verbatim or sanitized. Original executable flags are preserved. Operational scripts remain capable of
changing systems if invoked; inclusion is for inspection, not permission to run them.

## Censoring and exclusions

Deployment domains use `example.invalid`. Live public/LAN/VPN addresses use
reserved `192.0.2.0/24` documentation addresses, with example tunnel endpoints
kept in the same illustrative subnet. Owner accounts, private machine names,
network/volume names, fingerprints and personal storage paths use clearly marked
example replacements. Secret templates contain placeholders; account registration,
snapshot identifiers and private inventory/results are removed or generalized.
The examples are not a deployable replacement configuration.

Standard loopback/wildcard addresses, generic Docker service keys, product names,
public software documentation, package registries and public image/source digests
remain because they explain the implementation and preserve upstream references.
They are not the owner's private domains, hosts, accounts or credentials. Synthetic
fixture values and public sports-feed identifiers are not personal account data.

Excluded: real environment and secret files, private access instructions, Git
metadata/history, operational inventories and machine reports, logs, backup and
build contents, media files, library records and unrelated library-processing
scripts. Selected source documentation has marked omissions. Links to excluded
documents point explicitly to an [omission note](repository/docs/OMITTED.md).
The removed source files were not recovered from history.

On 2026-11-07 one further stack was removed from this public copy, along with
its dated notes and its dashboard, backup-list and recovery entries. A container
mount path that named it was renamed. Stack and database counts in the snapshot
describe what remains, not the full production system. See the
[omission note](repository/docs/OMITTED.md).

## Inspection versus execution

The full backup script, installer, remote-restore scripts, recovery helpers,
security tools and deployment/runbook commands are included to show the original
work. They can modify files/services or contact external systems. They were
**not executed** for this export. Configuration and Dockerfiles were not deployed
or built. Do not use this censored snapshot as a production restore kit.

To repeat the safe checks, with Python 3/PyYAML, Node, Bash, GNU core utilities,
SQLite CLI, rsync and jq already available, run from this export:

```bash
python3 validate-showcase.py
```

The runner copies the source snapshot to a fresh temporary directory, clears the
environment, blocks operational command fallbacks and skips the real Docker check.
It executes only the reviewed fixture suites and syntax/parsing checks; no package
installation or network access is needed.

Selected original tests are suitable for local fixtures: database dump/timeout
checks, mocked coherent capture, recovery regressions, dashboard configuration
and parser checks, and synthetic embedded-video recovery. See
[validation.md](validation.md) for the exact executed scope, skipped Docker check
and dependencies. No new production recovery is claimed.

The original repository validator assumes it runs at the root of a Git repository
and requires Docker Compose. It was inspected, not run against this nested,
history-free snapshot. The original CI workflow is preserved as evidence, not a
claim of a newly successful hosted CI run. Creating a new public repository,
committing, configuring CI and publishing remain outside this task.

## Runtime dependencies deliberately absent

Some Compose mounts reference files that belong to the original runtime, not the
public source snapshot: monitoring's Prometheus configuration, the unrelated
library sorting helper and an optional dashboard background image. Real `.env`
and mounted secret files are replaced by templates. Security image builds need
separately verified certificates/wheels and pinned upstream inputs. Those private
or generated artifacts are not included. These omissions do not prevent the
selected fixture tests but do prevent treating the snapshot as a complete,
ready-to-start installation.

## Attribution

Original source comments and upstream notices are retained. Source Markdown has a
sanitization banner. No project-level license was found; no third-party license
grant is inferred. [Source notes](SOURCES.md) distinguish original project work,
new showcase prose and synthetic examples. Historical checks remain dated and
limited to the recorded scope.
