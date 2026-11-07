> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# Homepage and Dozzle

The live stack is `/opt/example-stacks/admin/docker-compose.yml`. Homepage configuration
is `/opt/example-stacks/admin/data/homepage`; the files in `homepage/` are sanitized
copies of the configuration deployed on 2026-10-12. Git updates do not deploy
these files. Preserve the private `.env`, images and any newer live changes.

`homepage/services.yaml` references private `HOMEPAGE_VAR_*` variables from the
stack's `.env`; `.env.example` lists their names. Never commit API keys or
other credentials. After changing environment variables, recreate only
Homepage with `docker compose up -d --no-deps --pull never homepage` from the
live stack directory. Check that the local image tag still points to the
reviewed running image before recreating it. YAML, CSS and JavaScript changes
may also require a browser reload.

## Dashboard

- PostersPlus links to its configurator and reports renderer health.
- LumiereDB reports index readiness; it does not have a separate public UI.
- AIOMetadata's image cache shows images, disk usage, size limit and default TTL.
  Per-provider TTL overrides remain configured in AIOMetadata.
- Arcane and server Syncthing use the server's Tailscale address. The PC
  Syncthing link deliberately targets the viewer's own localhost.
- Legacy XRDB, cricket, sample logout and Portainer controls are removed.
- The dashboard opens directly; the redundant single Services tab is removed.

## League of Legends schedule

The corner panel shows up to ten live or next scheduled matches, using Warsaw
time. It covers LEC, LCK, LPL, LCS, CBLOL, LCP, Worlds, MSI and First Stand.
The panel is initially expanded on desktop and collapsed on mobile; its
collapse preference is saved only in the browser. It refreshes every five
minutes while visible and provides the official full-schedule link on failure.

The native LoL Esports service widget and corner panel use Homepage's existing
read-only `customapi` proxy. The upstream is the official website's anonymous
`https://lolesports.com/api/gql` endpoint with its public `homeEvents` persisted
query ID, JSON Content-Type and public Apollo client headers. No personal Riot
API key, new container or external iframe is needed. The endpoint supplies the first page of up to
40 upcoming/live events; the count is the fetched page size, not a season total.
The corner panel prioritizes live games and excludes finished games/results.

This is a website API, not a promised stable developer interface. If its query
ID/schema changes, inspect anonymous requests on the official schedule page,
update the encoded URL in `services.yaml` and, if necessary, the parser in
`custom.js`. Do not substitute a private Riot account token. A failed feed
shows a fallback message and keeps the official schedule link usable.

Run `node scripts/homepage/test-lol-schedule.cjs` and
`python3 scripts/homepage/test-config.py` (requires PyYAML) from the repository
root for parser/filter/error and configuration nesting regression checks. Verify the real proxy and UI after
deployment; fixture checks do not prove the upstream feed is available.

## Backup and recovery

Existing backups include `/opt/example-stacks`, covering Homepage's live configuration,
images and the private admin `.env`. No new backup source or database is needed.
Restore those files together before starting the admin stack; Git's sanitized
files and example environment are insufficient to restore widget credentials.
LoL schedules are fetched again from the official source, and the collapse
preference stays in each viewer's browser. See the main disaster recovery
runbook for the stack restore order and validation limits.
