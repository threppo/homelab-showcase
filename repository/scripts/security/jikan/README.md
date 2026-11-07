> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# Jikan PHP runtime remediation

This build retains the official image's application, locked vendor libraries,
RoadRunner, scheduler and entrypoint, replacing PHP 8.1.27/Bullseye with patched
PHP 8.3.36/Bookworm. It does not upgrade application dependencies or database
schemas. Treat it as a candidate until the checks below pass.

The upstream [Dockerfile](https://github.com/jikan-me/jikan-rest/blob/master/Dockerfile)
confirms `/app`, `/usr/bin/rr`, `/usr/bin/supercronic`, `/etc/supercronic` and
UID 10001. Its [composer.lock](https://github.com/jikan-me/jikan-rest/blob/master/composer.lock)
requires MongoDB extension 1.x through `mongodb/mongodb:1.12.0`; blindly installing
the default extension 2.x breaks that requirement. This build selects
[MongoDB 1.21.12](https://pecl.php.net/package/mongodb/1.21.12) and
[Redis 6.3.0](https://pecl.php.net/package/redis/6.3.0).
Unused development Xdebug is omitted. PHP's [security release](https://www.php.net/)
announced the fixed 8.3.36 runtime on October 21, 2026.

## Build without production credentials

Resolve and record the source application's exact digest before building. Use
the official image digest already reviewed/running, not a container filesystem
that may contain its generated `.env` and secrets. Pin the PHP and installer
image arguments to reviewed digests for a reproducible deployment. A missing PHP
tag or incompatible extension must fail the build; do not downgrade PHP or use
`--ignore-platform-reqs` to bypass a failure.

```sh
docker build --pull \
  --build-arg JIKAN_SOURCE_IMAGE='jikanme/jikan-rest@sha256:REVIEWED_SOURCE_DIGEST' \
  --build-arg PHP_IMAGE='php:8.3.36-cli-bookworm' \
  -t homelab/jikan-rest:php8.3.36 \
  scripts/security/jikan

docker run --rm --network none --entrypoint php homelab/jikan-rest:php8.3.36 -v
docker run --rm --network none --entrypoint php homelab/jikan-rest:php8.3.36 -m
docker run --rm --network none --entrypoint php homelab/jikan-rest:php8.3.36 \
  -r 'require "/app/vendor/autoload.php"; echo "autoload OK\n";'
docker run --rm --network none --entrypoint /usr/bin/rr homelab/jikan-rest:php8.3.36 --version
docker run --rm --network none --entrypoint /usr/bin/supercronic homelab/jikan-rest:php8.3.36 -version
```

Inspect actual PHP/extension versions, linkage (`ldd`), runtime user, and image
history. Compare hashes of `/app` application/vendor files with the original
image. No `composer update`, Composer execution or production secret is needed
in the build. Build-time platform checks supplement, rather than replace,
runtime application validation. PHP base and extension installer compatibility
still require a real Docker build; repository syntax checks cannot establish it.

## Isolated application checks and rollback

Before changing production, preserve the old image digest and Compose file and
verify a recent logical MongoDB dump. Run the candidate with separate restored
MongoDB, Redis and Typesense data, an isolated network, private test secrets and
loopback-only HTTP port. Do not share live database volumes or assume GET
requests are read-only: caching, queues, bootstrap and scheduled jobs can write.
Disable periodic full indexing during the trial. Startup uses the original
entrypoint which writes `/app/.env` and `.rr.yaml`; do not make `/app` read-only.

Require successful RoadRunner health, real `/v4/anime/1` detail and anime-search
responses matching the old app's structure, Mongo read/write/cache behavior,
Redis authentication, Typesense queries, queue/scheduler startup, and logs free
of fatal errors. Account for PHP 8.3 deprecation notices separately. Do not
expose test secrets in logs or command output.

When validated, change only Jikan REST's image reference, preserving its mounts,
secrets, UID, network and dependent database images. Recreate only that service,
then repeat health/API checks from its actual consumer. Save the built image by
immutable digest or an offline image archive; a local tag alone is not recoverable
after host loss. Record the image in the backup recovery inventory.

Rollback to the preserved image if application checks fail. This image performs
no intentional schema migration; still inspect any bootstrap/worker effects
before assuming that rollback needs no matching data restore. Long-term Lumen,
Mongo library, Mongo server and other dependency upgrades remain separate work.
