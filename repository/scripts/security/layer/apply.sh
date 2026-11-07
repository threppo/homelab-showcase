#!/bin/sh
# Build-time only: replace public trust data without invoking package installers.
set -eu
export LC_ALL=C
test -s /opt/homelab-ca/ca-certificates.crt
test -s /opt/homelab-ca/certifi-cacert.pem
python_cmd=''
for candidate in python3 python /opt/venv/bin/python /venv/bin/python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        python_cmd=$candidate
        break
    fi
done
if [ -n "$python_cmd" ]; then
    "$python_cmd" -I -S /opt/homelab-security/patch-certifi.py
else
    # Images without a Python executable can still contain Python trust bundles.
    for directory in /usr/local/lib /usr/lib /opt /app /venv /venvs /home /root/.local; do
        [ -d "$directory" ] || continue
        find "$directory" -type f -path '*/certifi/cacert.pem' \
            -exec cp /opt/homelab-ca/certifi-cacert.pem '{}' \;
    done
    printf 'package-metadata-unchanged\tinstaller-version-not-upgraded\n'
fi

if command -v keytool >/dev/null 2>&1; then
    listing=$(mktemp)
    trap 'rm -f "$listing"' EXIT HUP INT TERM
    for store in "${JAVA_HOME:-/nonexistent}/lib/security/cacerts" \
        "${JAVA_HOME:-/nonexistent}/jre/lib/security/cacerts" \
        /etc/ssl/certs/java/cacerts /opt/java/openjdk/lib/security/cacerts \
        /usr/lib/jvm/*/lib/security/cacerts /usr/lib/jvm/*/jre/lib/security/cacerts; do
        [ -f "$store" ] || continue
        # The password is the standard public cacerts password, not an app secret.
        # Subject matching catches distro-specific aliases, preserving other roots.
        keytool -J-Duser.language=en -J-Duser.country=US -list -v \
            -keystore "$store" -storepass changeit > "$listing"
        aliases=$(awk '
            /^Alias name: / { alias = substr($0, 13) }
            /^Owner: / && ($0 ~ /emSign ECC Root CA - G3/ || $0 ~ /AAA Certificate Services/) { print alias }
        ' "$listing")
        printf '%s\n' "$aliases" | while IFS= read -r alias; do
            [ -n "$alias" ] || continue
            keytool -J-Duser.language=en -delete -alias "$alias" \
                -keystore "$store" -storepass changeit
            printf 'java-root-removed\t%s\t%s\n' "$store" "$alias"
        done
    done
fi
