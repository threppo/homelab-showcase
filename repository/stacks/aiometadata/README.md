> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# AIOMetadata and LumiereDB

LumiereDB is included in this stack and starts without a Compose profile. It
shares the existing `main` network with AIOMetadata. Port 8000 is available
inside Docker only; no host port or public proxy route is added.
AIOMetadata defaults to `LUMIERE_API_BASE=http://lumiere-db:8000`.

Deployed on the production host on 2026-10-04. AIOMetadata, Redis and LumiereDB
passed their container health checks, and AIOMetadata reached LumiereDB over
the shared Docker network. The first index build completed in 2m32s and
`/readyz` returned HTTP 200 with `status: ready`. Search and the Popular catalog
also returned HTTP 200 with nonempty results from inside AIOMetadata.
The initial Compose rollback copy was removed during verified retirement
cleanup on 2026-10-10.

On 2026-10-09, Lumiere title search for movies/series and People Search for both
types were enabled in the other two saved profiles, matching the existing main
profile. All three now select those providers. The native save routine preserved
passwords, anime/AI search settings, catalogs and poster configuration. Live
manifests exposed all four search slots; each newly enabled profile returned
nonempty movie, series and both people searches. Temporary setup rollback copies
were removed after the fresh snapshot and isolated PostersPlus restore passed
on 2026-10-10; see the [deployment record](../../docs/postersplus-deployment.md).

The service follows the [upstream setup guide](https://github.com/cedya77/aiometadata/blob/dev/docs/lumiere-db.md).
Allow at least 5 GB of free space under `DOCKER_DATA_DIR`. The first start
downloads IMDb datasets and builds an index; search and catalogs return empty
results until the index is ready.

## Deploy on the homelab host

Copy the updated `docker-compose.yml` to the production AIOMetadata stack
directory (normally `/opt/example-stacks/aiometadata`), preserving its private `.env`.
Set `PUID` and `PGID` in that `.env` to the numeric host account IDs that should
own the new data directory. Both default to 1000 when absent. If
`LUMIERE_API_BASE` is already present, set it to `http://lumiere-db:8000`.

Create the data directory with the matching owner. The example below assumes
`DOCKER_DATA_DIR=/srv/example-app-data` and `PUID=PGID=1000`; use the actual values
from the production `.env` if different:

```bash
sudo install -d -o 1000 -g 1000 -m 0750 /srv/example-app-data/lumiere-db
cd /opt/example-stacks/aiometadata
sudo docker compose config --quiet
sudo docker compose pull lumiere-db aiometadata
sudo docker compose up -d lumiere-db aiometadata
sudo docker compose logs --tail=100 lumiere-db
sudo docker compose exec -T aiometadata node -e 'fetch(process.env.LUMIERE_API_BASE+"/readyz").then(async r=>console.log(r.status,await r.text())).catch(e=>{console.error(e.message);process.exit(1)})'
```

The readiness endpoint reports `not_ready` during the first build and returns
HTTP 200 once the index is published. Readiness is deliberately not a startup
dependency for AIOMetadata, so the addon can run while indexing takes place.
LumiereDB receives only its own environment settings, not the addon API keys.
Its downloads and index are stored at `${DOCKER_DATA_DIR}/lumiere-db` and can
be rebuilt; this directory is outside the current backup source list.

Once ready, open AIOMetadata's `/configure` page and select LumiereDB Search
and/or People Search, and enable Popular/Trending catalogs as desired.
