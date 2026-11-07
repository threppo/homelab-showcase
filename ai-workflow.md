# How I orchestrate with Claude/Codex

I use Claude/Codex to help debug individual containers, connect services and write
backup scripts. My contribution is the direction: what the system should do,
what must be preserved, which tradeoffs are acceptable and whether the result
meets the requirement. AI helps turn that into investigation, implementation and
repeatable checks. This is an account of AI-assisted project ownership, not a
claim that I independently wrote all the code.

## What that looks like in practice

| Work | My direction and feedback | Implementation and evidence |
| --- | --- | --- |
| Networking | The dated record credits me with preparing a remote instance, SSH access and cloud ingress, and supplying a connection-test result. | A dedicated VPN namespace kept one workload's route separate. The record checks its actual egress, incoming reachability and behavior during tunnel failure. |
| Container compatibility | The maintenance record attributes feedback about an incompatible application version to me. | A rollback preserved saved state. A later dashboard failure exposed version-specific authentication keys; its repair was checked through the actual dashboard API route. |
| Application integration | Deployment notes document my replacement-service choice and revised presentation settings. | The renderer, application proxy and saved templates were coordinated rather than configured as independent containers. |
| Backup scripting | I use AI to develop the scripts around recoverable application state. | Current code includes database-aware copies, bounded dumps, staged generations, checksums, snapshot status, retention and notifications. A dated component restore checked matching files and actual rendered output. |
| Recovery acceptance | A dated recovery report records my choice of one complete sample and my login/playback/persisted-position confirmation. | The technical exercise checked selected database and file results; it explicitly left other workflows and full recovery-time measurement open. |

## The working loop

1. Describe the observed problem or desired behavior, including what must not
   change. A useful question concerns the whole path: dashboard → application API,
   application → database, or workload → VPN → remote gateway.
2. Use AI to inspect relevant configuration and records and narrow the cause.
   A healthy container is one clue, not an answer to every integration problem.
3. Have AI draft a focused change or script. Preserve the existing state and keep
   credentials out of generated reports and version control.
4. Check the behavior that matters: the failing API route, expected restored data,
   a rendered output, or a deliberately simulated timeout.
5. Record the result and limits. Local fixtures, installed configuration and a
   real recovery exercise answer different questions.

The table describes supported project examples; this loop summarizes my stated
way of working. Earlier Claude/Codex transcripts are not available in this chat,
so exact historical prompts, assistant identity per incident and line-by-line
code authorship are not reconstructed.

## This showcase is also AI-assisted

I asked Codex for a recruiter-friendly export with strict privacy and no production
operations. After reviewing the first draft, I redirected it toward the system I
orchestrated: service connections, networking, security, backup strategy and AI
use in debugging and scripting. Codex revised it against repository evidence. I then clarified that the actual
repository should be the core of the export, with appropriate censoring and
showcase documentation added around it. Codex copied the selected source tree
and checked the censored files and original fixture suites.

Codex wrote these documents, extracted the timeout helper, adapted its tests and
created a synthetic SQLite demonstration. Codex ran the local validation; those
runs are not presented as my independent testing. The existing operational code
and dated records remain distinct from the new showcase examples.

The source notes retain provenance. The [validation record](validation.md) gives
the checks and boundaries; no new production work was required for this export.
