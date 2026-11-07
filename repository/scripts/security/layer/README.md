> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# Temporary persistent security layers

These build helpers apply explicit runtime, Python-package and trust changes to a
pinned application image. Prefer an upstream security release when available.
The maintenance build installs verified pip 26.2.2 and certifi 2026.10.19 wheels
offline into existing package locations and updates bundled ensurepip's pip.
It also filters selected OS certificate stores and replaces Python trust bundles.
These targeted layers do not perform a general operating-system package upgrade.

Prepare a private build context containing this directory as `layer/` and a
`clean-ca/` directory. Supply verified public certificate artifacts:

- `ca-certificates.crt`: clean OS PEM bundle with compromised trust paths removed.
- `certifi-cacert.pem`: verified certifi 2026.10.19 or newer bundle.
- `certifi-2026.10.19-py3-none-any.whl` and
  `pip-26.2.2-py3-none-any.whl`: official package wheels, required for the package
  upgrades described above.
- Hash-named PEM files/symlinks for the clean OS certificate directory, at the top
  level of `clean-ca/`, if clients use `SSL_CERT_DIR` instead of the PEM bundle.

Verify each wheel's SHA-256 against the official PyPI release metadata before
putting it in the context, and verify certificate artifacts against trusted
vendor metadata. The helpers rely on this preparation; they do not independently
authenticate wheel hashes. No downloads happen in the final application stages;
Docker can still fetch the selected base and build-tool images. Do not include
production configuration, credentials, private keys, or application data in the
build context.

Build with `-f layer/Dockerfile.trust`, a digest-pinned `BASE_IMAGE`, and
`ORIGINAL_USER` equal to the inspected base image's original user (empty means
root: pass `0`). Each Dockerfile's `trust_builder` stage runs the Go helper's
tests and builds it statically with `CGO_ENABLED=0`. Pin `TRUST_TOOLS_IMAGE` to a
reviewed digest as well. The helper parses certificates and removes exact subject
common names `emSign ECC Root CA - G3` and `AAA Certificate Services` from the
fixed OS PEM-store paths in `filter-roots.go`. It preserves unrelated certificate
blocks and surrounding bytes, limits symlink targets to those store paths, and
validates all selected PEM data before applying changes. It removes its own
executable after successful filtering.

The result also sets `SSL_CERT_FILE` and `SSL_CERT_DIR`. `apply.sh` invokes
`patch-certifi.py` with Python's `-I -S` flags to disable startup hooks. The helper
replaces discovered certifi bundles, including vendored copies, then extracts the
verified wheels into existing pip/certifi package locations and replaces their
old distribution metadata. It does not execute an existing pip installer or
install packages where they were absent. When its interpreter is Python 3.9 or
newer, it also replaces bundled ensurepip pip wheels and updates `_PIP_VERSION`
to 26.2.2. Verify every targeted interpreter supports the supplied pip release.

If a wheel is omitted, its package upgrade is skipped; replacing CA data alone
does not upgrade the package or installer. If no Python executable is available,
`apply.sh` only replaces discovered Python PEM bundles and leaves package versions
unchanged. It also removes matching G3/AAA subjects from known Java truststores
when `keytool` is available. Custom truststores,
custom passwords, embedded Java stores, nonstandard package paths, and application
overrides require separate verification. Cached TLS contexts require restart.

`Dockerfile.node` additionally requires a digest-pinned `NODE_IMAGE` containing
the security-patched **matching Node major, CPU architecture, and libc family**.
It copies only `/usr/local/bin/node`; it does not upgrade npm or arbitrary Node
installations elsewhere. Confirm the application's actual executable path and
check the copied binary's dynamic library requirements before deployment.

`Dockerfile.python` additionally requires `PYTHON_IMAGE`. Use it only after
reviewing that the official image has the **same Python minor, ABI, architecture,
OS release, and libc** as the application. Copying `/usr/local` can overwrite
application packages or executables; inspect conflicts first. Native extensions
and virtual environments require runtime verification. Do not use this variant
for arbitrary distro Python or a Python minor migration.

After building, run the runtime/trust audit and application health checks against
the resulting image. Verify trust bundle contents, actual Node/Python versions,
native extension imports, original user, entrypoint and command. Subject absence
alone is not a full certificate-path validation test. A local tag or successful
build does not establish deployment: retain image digests and confirm running
containers use them. Keep previous images for rollback. Rebuild or remove these
layers when upstream images incorporate fixes; automated pulls cannot maintain
local overlays automatically.

For images without a shell, use `Dockerfile.distroless`: its exec-form `RUN`
invokes the static Go helper directly, filters the known OS PEM stores, and copies
the clean CA directory with the same trust environment variables. This variant
does not run `apply.sh`, install Python wheels or modify Java truststores. Verify
any embedded application-specific trust stores separately.
