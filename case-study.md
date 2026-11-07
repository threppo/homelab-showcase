# Backup case study: preserving an application's complete state

Historical component recovery check: **2026-10-10**.

## The problem

A rendering application stores its SQLite database alongside settings, authored
artwork and fonts in a directory that also contains generated caches. Backing up
only the database would miss some durable state. Copying the entire live tree
could mix files from different moments and include large rebuildable caches.

This makes the backup strategy a dependency problem: identify what the application
needs to behave the same way after recovery, then capture those pieces together.

## Investigation and design

The repository's deployment record identifies which settings live in files,
which values are private and which generated files can be recreated. It also
records that saved settings can override environment values: an example environment
file alone cannot recreate the deployed behavior.

The backup implementation uses a dedicated capture helper. It verifies the expected
container and storage mount, briefly stops the application, captures the database
and matching authored/settings files, then resumes the service only if it was
originally running. A capture or restart failure stops the backup. Known generated
caches are excluded; unknown files are retained conservatively.

The live tree is excluded from the main snapshot only because the helper stages
the necessary durable state separately. The runbook requires the database and
filesystem capture from the same complete snapshot, plus the real private
configuration, before application startup.

## Verification and result

The **2026-10-10** deployment record describes a complete backup followed by a
selected remote-snapshot restore. Database checksums and integrity checks passed;
matching settings/authored-file checksums passed. A separate restored container
with no published ports produced a successfully decoded image using the saved
template. The connected application's restored settings also matched the intended
integration.

This is stronger evidence than a successful backup exit code: it checks that
restored state can produce the expected kind of application output. It does not
verify every setting or personal client. The separate **2026-10-01** replacement-host
drill covered other selected workflows and is not a fresh result of this export.

## My involvement and AI assistance

I orchestrate the system and use Claude/Codex for debugging and backup scripting.
The deployment record also documents my choice to replace the previous renderer
and my template revisions. These human choices set the desired behavior; capture
helpers, integration changes and tests implement it with AI assistance. The
available records do not establish who authored every line or personally ran each
historical command.

## What remains limited

The component test is not a complete host-loss recovery test. It does not measure
total recovery time, establish every application workflow or guarantee current
snapshot completeness. Production configuration remains authoritative.

The exported examples deliberately omit the operational stop/capture helper.
Instead, they safely demonstrate backup timeout handling and a SQLite pitfall:
wrong data can pass an integrity check when an old journal is left behind.
[Validation](validation.md) records exactly which local tests were newly run.
