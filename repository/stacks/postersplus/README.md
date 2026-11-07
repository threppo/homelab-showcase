> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# PostersPlus

Deployed on 2026-10-09 and used by all three AIOMetadata profiles through the
image proxy. XRDB was retired on 2026-10-10.
The [deployment record](../../docs/postersplus-deployment.md) records the
current settings, image warming, backup/restore checks and retirement cleanup.

This stack uses upstream `latest`, pinned to the build observed on 2026-10-09.
Upstream publishes `latest` from `dev`, so this includes features newer than
the tagged release. The pin prevents an unrelated image update during cutover;
change the digest after reviewing and testing the next `latest` build.
The source revision is `31e6e3ce348e361cf1ba8224c3436bff8cf1bc5f`.

The configurator and admin UI bind to host loopback port 8001. Reach them
through an SSH tunnel or the owner's Cloudflare hostname
`https://posters.example.invalid`, routed to `http://postersplus:8000`.
AIOMetadata reaches `http://postersplus:8000` on
`example-shared-network` and supplies public HTTPS image proxy URLs to clients.
The image proxy does not depend on the public configurator route.

Copy `.env.example` to a protected production `.env`, then replace every
`CHANGE_ME` value. Generate separate random rendering and admin keys. Populate
TMDB/MDBList server-side rather than through copied poster URLs. `ADMIN_KEY`
must be at least 12 characters. The upstream entrypoint fixes cache ownership
then drops to `appuser`; this stack intentionally uses that mechanism.

The 2 GiB memory and two-CPU limits, one worker, and two concurrent renders are
deployment limits, not measured capacity guarantees. PostersPlus's own warming
is off; AIOMetadata warms images with concurrency 2–4.
Dashboard settings in `/app/cache/settings.json` override environment values;
confirm effective settings there after saving. TMDB, MDBList and TVDB keys and
the owner's AIOStreams profile authentication are saved there privately.
The **Current AIOMetadata style** operator preset matches the current URL used
by all profiles. Load it in the configurator before adjusting the style; save
the copied template into AIOMetadata with the internal service address.

## Smoke checks after first startup

Run on the host from the infrastructure checkout:

```bash
docker exec -i postersplus python3 - < scripts/postersplus/smoke.py
docker exec aiometadata node -e 'fetch("http://postersplus:8000/health").then(async r=>{console.log(r.status,await r.text());if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))'
```

The smoke script verifies health, the effective rendering access setting, decoded movie/series/
anime/landscape images and a repeated cached render. It does not print credentials
or URLs. It creates cache entries and spends upstream API quota. It does not
prove the appearance matches the chosen style, that ratings are populated, or
that the end-to-end AIOMetadata/client proxy route works; those are separate
acceptance checks in the migration plan.

`/app/cache` contains durable settings, authored artwork, presets and database
state as well as disposable image caches. The installed capture hook briefly
pauses this app and stages the database plus matching authored filesystem state.
The backup excludes the live tree only with that hook installed. Restore
`current/sqlite/postersplus.sqlite` and
`current/applications/postersplus/cache/` together. A remote snapshot restore
and isolated restored-container render passed on deployment day.
