> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# PostersPlus deployment and recovery

PostersPlus is the poster provider for all three AIOMetadata configurations.
It was deployed on 2026-10-09; XRDB was retired on 2026-10-10 at the owner's
request. This record describes deployed behavior and completed checks.
Production files and databases remain authoritative.

## Production layout

| Item | Location or setting |
| --- | --- |
| Compose | `/opt/example-stacks/postersplus/compose.yaml` |
| Private environment | `/opt/example-stacks/postersplus/.env` |
| Durable state and generated cache | `/srv/example-app-data/postersplus/cache` mounted at `/app/cache` |
| Docker network | `example-shared-network` |
| Internal poster service | `http://postersplus:8000` |
| Host UI binding | `127.0.0.1:8001` |
| Configurator | [posters.example.invalid](https://posters.example.invalid/) |
| Admin dashboard | [posters.example.invalid/admin](https://posters.example.invalid/admin) |
| Cloudflare origin | `http://postersplus:8000` on the gateway's shared network |
| Image delivery to clients | AIOMetadata's signed public HTTPS image proxy |

The deployed image is
`ghcr.io/umbraprojects/postersplus:latest@sha256:6d4719fbe2dbf628dd4f597ee8932c7e3f5a5782d23c059d67c4f3999002f498`.
It identifies source revision `31e6e3ce348e361cf1ba8224c3436bff8cf1bc5f`,
built on 2026-10-06 and checked against upstream `latest` on 2026-10-09.
That tag follows upstream `dev`. Review, pull and verify the next build before
changing the pin; recreating an unrelated stack must not silently change this
renderer.

The upstream entrypoint fixes cache ownership before switching to `appuser`.
Compose limits the service to two CPUs, 2 GiB, one worker and two concurrent
renders. These are deployed limits, not a measured capacity guarantee.

The UI can also be reached from the owner's workstation with:

```bash
ssh -L 8001:127.0.0.1:8001 example-host
```

Then open `http://127.0.0.1:8001`. The admin dashboard uses its separate
`ADMIN_KEY`. Rendering/configurator access follows the effective saved
`ACCESS_KEY` setting; when one is enabled, append `?access_key=...`.
Keys and private client URLs must stay outside Git.

## Current configuration

TMDB, MDBList and TVDB credentials are saved in the admin dashboard.
TVDB accepted its key during setup. The owner's AIOStreams profile is connected
at internal `http://aiostreams:3000`; its authenticated lookup returned
20 streams without scraper errors. Its Basic authentication contains the
profile UUID and installation password token, rather than the server's
dashboard login. Preserve AIOStreams's private environment, including its
encryption secret, when restoring that integration.

Saved `/app/cache/settings.json` values override environment values. Saving a
setting may require a PostersPlus restart; check the dashboard's pending
restart indication. A fresh `.env.example` does not recreate the saved
settings by itself.

All three AIOMetadata profiles select `posterRatingProvider=custom` and
`usePosterProxy=true`. The owner-selected template is recorded without real
keys in [the settings example](../stacks/postersplus/aiometadata-settings.example.json).
It uses original artwork, centered minimalist ratings, low gradients, hidden
year/sash and the selected movie/series/anime rating sources and weights.

The **Current AIOMetadata style** operator preset matches the deployed
template. Use **Load preset → Operator** in the configurator to edit that
look. When copying a new template to AIOMetadata, use internal
`http://postersplus:8000` as its origin. Clients receive AIOMetadata's proxy
URLs; they do not need direct access to this Docker hostname.

AIOMetadata permits only `postersplus` as the local art host for this setup,
while `POSTER_PROXY_ALLOW_PRIVATE=false` remains in effect.
PostersPlus images have a one-hour cache policy; the existing external
ExtendedRatings policy remains 30 days. Dashboard overrides and the production
Compose were updated together when XRDB was retired.

PostersPlus's own cache warming is disabled. AIOMetadata performs image warming
with adaptive concurrency 2–4. A changed template produces different image
cache keys. Background warming counts are observations, not proof that every
catalog or client has finished refreshing.

Lumiere title and people searches for movies and series are enabled in all
three AIOMetadata profiles. Anime/AI search settings and catalog preferences
were preserved.

## Backup and restoration

Canonical reviewed lists live in [backup/](../backup/README.md); production
uses the installed root-owned lists under `/etc/example-homelab`.
The active SQLite map includes
`postersplus|/srv/example-app-data/postersplus/cache/cache.db`.
The main backup script invokes the root-owned, mode-0700
`/usr/local/sbin/homelab-capture-postersplus-state.sh`.

The helper briefly stops the verified PostersPlus container, copies its SQLite
database and matching settings/artwork/font files, then resumes it if it was
running. Capture or resume failure fails the backup. It excludes known
generated artwork caches and rebuildable datasets and preserves unknown files.
The live cache tree is excluded from Restic only because this coherent capture
hook stages durable state separately.

Restore these two artifacts from the same complete snapshot, with PostersPlus
stopped and numeric ownership preserved:

- `/var/backups/example-homelab/current/sqlite/postersplus.sqlite`
- `/var/backups/example-homelab/current/applications/postersplus/cache/`

Also restore the real `/opt/example-stacks/postersplus/.env`. Follow the
[disaster-recovery runbook](disaster-recovery-runbook.md) for filesystem,
SQLite ownership, pinned images and startup order. Start PostersPlus before
AIOMetadata. XRDB is not an active backup or recovery dependency.
Normal Restic retention still governs historical snapshots containing XRDB.

## Verification and retirement record

[Detailed operational result and cleanup inventory omitted from this public export.
The showcase case study summarizes the dated 2026-10-10 component restore check.]
