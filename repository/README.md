> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.


# Homelab Infrastructure

Version-controlled configuration, scripts and documentation for my Debian-based homelab.

## Repository scope

This repository contains sanitized infrastructure files:

- Docker Compose configurations
- maintenance and backup scripts
- systemd services and timers
- example environment and secret files
- operational, migration and recovery documentation

Production secrets, application databases, media files and runtime data are not stored in Git.

Codex work follows the repository's `AGENTS.md` and its
[adaptive delegation policy — omitted from export](docs/OMITTED.md), using bounded workers
when useful and direct review for consequential infrastructure changes.

## Active stacks

[Operational inventory paragraph omitted from this public export.]
[One further stack is also omitted from this public export.]

LumiereDB was added to the production AIOMetadata stack on 2026-10-04.
Its IMDb index is ready, and search and Popular catalog requests were verified
from AIOMetadata. See the [setup and deployment notes](stacks/aiometadata/README.md).

- `admin`
  - Homepage ([dashboard, LoL schedule and recovery configuration](stacks/admin/README.md))
  - Dozzle
- `aiometadata`
  - AIOMetadata
  - Redis
  - poster cache
  - LumiereDB: IMDb search and catalogs ([setup](stacks/aiometadata/README.md))
- `bookorbit`
  - Bookorbit: active replacement for Grimmory and Audiobookshelf
  - PostgreSQL (pgvector)
  - Compose base and override copied from the production definitions, without `.env`
- `postersplus`
  - poster provider for all three AIOMetadata profiles; XRDB retired on 2026-10-10
  - upstream latest build observed on 2026-10-09, pinned for reviewed updates
  - configurator/admin UI via Cloudflare or SSH; images use AIOMetadata's HTTPS proxy
  - [deployment, backup and recovery notes](docs/postersplus-deployment.md)
- `gateway`
  - Cloudflare Tunnel
- `immich`
  - Immich Server
  - Immich Machine Learning
  - PostgreSQL
  - Valkey
- `jikan`
  - Jikan REST
  - MongoDB
  - Redis
  - Typesense
- `monitoring`
  - Prometheus
  - Grafana
  - Node Exporter
  - cAdvisor
  - Uptime Kuma
- `stirling-pdf`
- `syncthing`
- `streaming`
  - AIOStreams nightly
- `arcane`
  - Docker stack management
  - Docker image update management

## Current production layout

- shared book media and exchange directories: `/srv/example-library`
- administration application data: `/opt/example-stacks/admin/data`
- monitoring configuration and data: `/opt/example-stacks/monitoring`
- Immich library: `/srv/example-photos/immich/library`
- AIOMetadata data: `/srv/example-app-data/aiometadata`
- PostersPlus state and image cache: `/srv/example-app-data/postersplus/cache`
- LumiereDB datasets and rebuildable index: `/srv/example-app-data/lumiere-db`
- administrative scripts: `/usr/local/sbin`
- systemd units: `/etc/systemd/system`
- private configuration: `/root/.config`
- streaming application data: `/opt/example-stacks/streaming/data`
- Arcane application data: `/srv/example-app-data/arcane`


## Backup

The homelab is backed up with Restic to Backblaze B2 through its S3-compatible API.

The backup process includes:

- application configuration
- sanitized infrastructure repository
- PostgreSQL and MongoDB dumps
- online SQLite backups
- Immich originals
- ebook library
- system configuration
- backup verification and retention
- Discord status notifications

Large audiobook media, generated caches and rebuildable indexes are excluded.

Canonical backup configuration is in [`backup/`](backup/README.md); executable
backup code is in `scripts/backup/`. Production reads its own configuration from
`/etc/example-homelab`. Editing this repository does not deploy that configuration.

Bookorbit PostgreSQL and PostersPlus database/filesystem captures are deployed.
Restore PostersPlus's SQLite copy together with its matching settings, artwork
and fonts. XRDB is absent from active backup lists and recovery dependencies.
See [backup coverage](backup/README.md), the
[recovery runbook](docs/disaster-recovery-runbook.md), and the
[PostersPlus deployment record](docs/postersplus-deployment.md) for verification
evidence and its limits. The dated
[Bookorbit/XRDB drill — omitted from export](docs/OMITTED.md) remains historical evidence.

## Security

Files containing passwords, API keys, tokens, private keys, Discord webhooks and other credentials must never be committed.

Only sanitized `.env.example` and `*.example` secret templates belong in this repository.
