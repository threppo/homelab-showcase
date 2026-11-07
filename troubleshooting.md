# Container debugging: running services, broken integration

Historical incident: **2026-10-27**. Generic labels replace the application names.

## What was wrong

A dashboard widget showed an API error even though both the dashboard and target
application containers were running. Its login requests returned HTTP 401; retries
then triggered the application's temporary address ban.

## How the investigation narrowed it down

1. Check the integration failure rather than assuming that container health proves
   the application works. The dashboard's login response identified authentication
   as the failing layer.
2. Verify the saved credentials without publishing them. The record reports an
   offline comparison against the stored password hash: they matched.
3. Review the recent change. The application had been rolled back to an older
   version after compatibility feedback. That version read authentication settings
   from a different configuration section.
4. Explain the symptom: the old version ignored the newer-format entries and
   generated a temporary password. Correct saved credentials therefore failed.

## Repair and outcome

The recorded repair stopped retries, stopped the target cleanly and preserved a
private pre-change configuration copy. Only the existing username and password
hash were copied to the keys understood by the older version, preserving other
settings and file permissions. Authentication remained enabled; no password reset
was required.

The meaningful check used the dashboard's own proxy route, which returned HTTP 200
and the expected application response. This verified the integration path that
had failed, beyond checking that the target was reachable directly.

## My role and AI's role

I use Claude/Codex to debug containers in this project, as well as to draft scripts.
I bring the problem, compatibility requirements and feedback; AI helps inspect
configuration and construct a repair and checks. The preceding maintenance record
explicitly attributes the version-compatibility feedback to me. The incident
record describes the technical diagnosis and repair but does not assign individual
commands to a named assistant or to me. I do not claim independent authorship of
that implementation.

The lesson transfers directly to support: follow the failed request across the
connected services, consider recent changes, preserve data and verify the original
customer-visible action. This is a dated incident summary, not a new login test;
no credentials, hashes, private logs or live application records are exported.
