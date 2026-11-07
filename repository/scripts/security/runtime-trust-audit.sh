#!/bin/sh
# Read-only inventory. No network calls, package changes, or application imports.
# Pipe into `docker exec -i CONTAINER sh` or run inside an image with a shell.
set -u
export LC_ALL=C

printf 'probe\truntime-trust-audit-v1\n'
if command -v node >/dev/null 2>&1; then
    (unset NODE_OPTIONS NODE_PATH; node --version 2>/dev/null) |
        sed 's/^/node\t/'
fi
if command -v php >/dev/null 2>&1; then
    php -n -v 2>/dev/null | sed -n '1s/^/php\t/p'
fi
if command -v dpkg-query >/dev/null 2>&1; then
    dpkg-query -W -f='os-package\t${Package}\t${Version}\n' \
        ca-certificates libnss3 libbrotli1 python3-certifi python3-pip 2>/dev/null || :
elif command -v apk >/dev/null 2>&1; then
    apk info -v ca-certificates ca-certificates-bundle nss brotli-libs \
        py3-certifi py3-pip 2>/dev/null | sed 's/^/os-package\t/'
fi

# List only matching certificate subjects, never certificate or private-key data.
check_bundle() {
    bundle=$1
    [ -r "$bundle" ] || return 0
    if ! command -v openssl >/dev/null 2>&1; then
        printf 'ca-bundle\t%s\tunknown:no-openssl\n' "$bundle"
        return 0
    fi
    subjects=$(openssl crl2pkcs7 -nocrl -certfile "$bundle" 2>/dev/null |
        openssl pkcs7 -print_certs -noout 2>/dev/null) || {
        printf 'ca-bundle\t%s\tunknown:parse-failed\n' "$bundle"
        return 0
    }
    if [ -z "$subjects" ]; then
        printf 'ca-bundle\t%s\tunknown:empty-or-unparseable\n' "$bundle"
        return 0
    fi
    if printf '%s\n' "$subjects" | grep -Ei \
        'emSign ECC Root CA[[:space:]]*-[[:space:]]*G3|AAA Certificate Services' >/dev/null; then
        printf 'ca-bundle\t%s\tflagged-root-subject-present\n' "$bundle"
    else
        printf 'ca-bundle\t%s\tflagged-root-subject-not-found\n' "$bundle"
    fi
}
for bundle in /opt/homelab-ca/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem \
    /etc/pki/tls/certs/ca-bundle.crt /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem; do
    check_bundle "$bundle"
done
for cert in /etc/ssl/certs/*emSign* /etc/ssl/certs/*AAA* \
    /usr/share/ca-certificates/mozilla/*emSign* \
    /usr/share/ca-certificates/mozilla/*AAA*; do
    [ -f "$cert" ] && check_bundle "$cert"
done

audit_python=''
for candidate in python3 python /opt/venv/bin/python /opt/venv/bin/python3 \
    /venv/bin/python /venv/bin/python3 /app/.venv/bin/python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        audit_python=$candidate
        break
    fi
done
if [ -z "$audit_python" ]; then
    printf 'python-metadata\tunknown:no-python-interpreter\n'
    exit 0
fi

# -I ignores environment/user paths; -S prevents all site/.pth startup processing.
# Inspect metadata directly: never import pip, certifi, LiteLLM, or application code.
"$audit_python" -I -S - <<'PY'
import json
import os
import re
import subprocess
import sys

def emit(kind, **values):
    print(json.dumps(dict(kind=kind, **values), sort_keys=True))

emit("python", version=sys.version.split()[0], executable=sys.executable,
     startup_site_disabled=bool(sys.flags.no_site), isolated=bool(sys.flags.isolated))
roots = ["/usr/local/lib", "/usr/lib", "/opt", "/app", "/venv", "/venvs",
         "/root/.local", "/home"]
prune = {"node_modules", ".git", ".cache", "proc", "sys", "dev", "media", "data"}
wanted = {"certifi", "pip", "uv", "litellm", "sigstore", "conda", "pixi"}
seen = set()
bundles = set()
visited = 0
limit = 20000
truncated = False
for root in roots:
    if not os.path.isdir(root):
        continue
    for directory, dirs, files in os.walk(root, followlinks=False):
        visited += 1
        if visited > limit:
            truncated = True
            break
        depth = os.path.relpath(directory, root).count(os.sep)
        dirs[:] = sorted(d for d in dirs if d not in prune and depth < 8)
        if "pyvenv.cfg" in files:
            emit("venv", path=directory)
        in_packages = "site-packages" in directory.split(os.sep) or "dist-packages" in directory.split(os.sep)
        if not in_packages:
            continue
        for filename in files:
            if filename in {"cook.pth", "cook.py", "sitecustomize.py"} or (
                filename.endswith(".pyc") and filename.startswith(("cook.", "sitecustomize."))
            ):
                emit("startup-indicator", path=os.path.join(directory, filename),
                     note="inspection-required; presence-alone-is-not-proof-of-compromise")
        if os.path.basename(directory).endswith((".dist-info", ".egg-info")):
            for filename in ("METADATA", "PKG-INFO"):
                if filename not in files:
                    continue
                path = os.path.join(directory, filename)
                name = version = None
                try:
                    with open(path, encoding="utf-8", errors="replace") as source:
                        for index, line in enumerate(source):
                            if index > 300 or not line.strip():
                                break
                            if line.startswith("Name: "):
                                name = line[6:].strip().lower().replace("_", "-")
                            elif line.startswith("Version: "):
                                version = line[9:].strip()
                except OSError:
                    continue
                if name in wanted and path not in seen:
                    seen.add(path)
                    emit("python-package", name=name, version=version, metadata=path)
        if "cacert.pem" in files and os.path.basename(directory) == "certifi":
            bundles.add(os.path.join(directory, "cacert.pem"))
if truncated:
    emit("coverage", status="incomplete", reason="directory-limit", limit=limit)
else:
    emit("coverage", status="bounded", max_depth=8, roots=roots,
         note="unusual install paths and symlinked directories require separate inspection")
for bundle in sorted(bundles):
    try:
        packed = subprocess.run(["openssl", "crl2pkcs7", "-nocrl", "-certfile", bundle],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
        parsed = subprocess.run(["openssl", "pkcs7", "-print_certs", "-noout"],
                                input=packed.stdout, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=15)
        if packed.returncode or parsed.returncode or not parsed.stdout:
            raise ValueError("parse-failed")
        matches = sorted(set(re.findall(
            rb"emSign ECC Root CA\s*-\s*G3|AAA Certificate Services", parsed.stdout, re.I)))
        emit("certifi-bundle", path=bundle,
             flagged_subjects=[match.decode("ascii") for match in matches],
             note="subject-match; absence-does-not-test-all-trust-paths")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        emit("certifi-bundle", path=bundle, status="unknown:no-openssl-or-parse-failed")
PY
