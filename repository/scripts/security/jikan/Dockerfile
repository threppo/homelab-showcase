# syntax=docker/dockerfile:1
# Supply the exact previously reviewed upstream digest; do not copy live /app.
ARG JIKAN_SOURCE_IMAGE
ARG PHP_IMAGE=php:8.3.36-cli-bookworm
ARG EXTENSION_INSTALLER_IMAGE=mlocati/php-extension-installer:2.1.77
FROM ${JIKAN_SOURCE_IMAGE} AS application
FROM ${EXTENSION_INSTALLER_IMAGE} AS extension-installer
FROM ${PHP_IMAGE} AS runtime

ARG MONGODB_EXTENSION_VERSION=1.21.12
ARG REDIS_EXTENSION_VERSION=6.3.0

COPY --from=extension-installer /usr/bin/install-php-extensions /usr/local/bin/
RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl wget unzip; \
    install-php-extensions intl mbstring \
        "mongodb-${MONGODB_EXTENSION_VERSION}" "redis-${REDIS_EXTENSION_VERSION}" \
        opcache sockets pcntl; \
    rm -rf /var/lib/apt/lists/* /tmp/pear; \
    rm /usr/local/bin/install-php-extensions; \
    groupadd --gid 10001 jikanapi; \
    useradd --uid 10001 --gid 10001 --home-dir /nonexistent \
        --no-create-home --shell /usr/sbin/nologin jikanapi; \
    mkdir -p /var/run/rr; \
    chown 10001:10001 /var/run/rr

# These are upstream's actual paths. Compiled PHP modules and old PHP config
# are intentionally not copied across the PHP ABI and Debian version change.
COPY --from=application /usr/bin/rr /usr/bin/rr
COPY --from=application /usr/bin/supercronic /usr/bin/supercronic
COPY --from=application --chown=10001:10001 /etc/supercronic /etc/supercronic
COPY --from=application --chown=10001:10001 /app /app

# Preserve CLI opcache/JIT settings from the official image's Dockerfile.
RUN set -eu; \
    printf '%s\n' 'opcache.enable=1' 'opcache.enable_cli=1' \
        'opcache.jit_buffer_size=32M' 'opcache.jit=1235' \
        > /usr/local/etc/php/conf.d/jikan-opcache.ini; \
    chmod +x /app/docker-entrypoint.sh /app/docker-entrypoint.php; \
    php -r 'if (PHP_VERSION_ID < 80336 || PHP_VERSION_ID >= 80400) { exit(1); } foreach (["intl", "mbstring", "mongodb", "redis", "Zend OPcache", "sockets", "pcntl"] as $ext) { if (!extension_loaded($ext)) { fwrite(STDERR, "Missing: $ext\n"); exit(1); } }'; \
    php /app/vendor/composer/platform_check.php

USER 10001:10001
WORKDIR /app
# Override PHP base image's inherited CMD ["php", "-a"]: the upstream
# shell entrypoint forwards arguments to its PHP bootstrap script.
CMD []
EXPOSE 8080 2114
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:2114/health?plugin=http || exit 1
ENTRYPOINT ["/app/docker-entrypoint.sh"]
