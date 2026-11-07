# My homelab: a connected system orchestrated with AI

Personal project · Customer Service Specialist application to Automate.travel

**Browse the actual project:** [sanitized repository](repository/README.md) ·
[Compose stacks](repository/stacks/) · [backup scripts](repository/scripts/backup/) ·
[recovery code and tests](repository/scripts/recovery/) ·
[validation workflow](repository/.github/workflows/validate.yml)

This export preserves the original file structure and implementation, with
identifying values replaced and private records excluded. The documents below
explain the system for a portfolio reader. See [export notes](EXPORT.md) for the
copy's scope, substitutions, safe test commands and limitations.

I orchestrated a Linux homelab that brings personal applications, databases,
monitoring and backups together. My work is deciding how the pieces should
connect, using Claude/Codex to investigate problems and develop scripts, and
checking whether changes solve the original problem. It is hands-on personal
project experience, not commercial infrastructure employment.

## What I put together

- **Connected applications:** Docker Compose services communicate through
  container networks. Application-specific databases and caches support them;
  a dashboard brings service status and API integrations into one place.
- **Different access paths:** a tunnel provides selected public access, private
  remote access supports administration, and a dedicated VPN route serves one
  workload without changing every application's connection.
- **Security with compatibility in mind:** credentials stay outside Git,
  selected containers have restricted permissions, and updates are checked
  against application behavior and existing data.
- **A recovery strategy:** scheduled encrypted off-site backups combine database
  dumps, online SQLite copies and selected durable files. Rebuildable caches are
  excluded deliberately; recovery instructions explain the dependencies.
- **Visibility:** metrics, dashboards, availability checks and container logs
  help distinguish an application failure from an integration or network issue.

See the [service map](architecture.md), [networking and security decisions](networking-security.md)
and [backup strategy](backup-strategy.md).

## How I use AI in practice

I use Claude/Codex as technical assistants for container debugging and backup
scripting. I provide the goal, constraints and observed problem; AI helps inspect
configuration, reason through dependencies and produce implementation. Results
need evidence: an API response through the real integration, expected restored
data, or a regression test. [The workflow](ai-workflow.md) separates my role from
AI-produced work and describes the evidence available here.

One documented incident involved a dashboard returning authentication errors even
though both containers were running. Investigation traced it to configuration
keys changed by a version rollback. The repair preserved the credentials and
verified the dashboard's actual API route. [Read the troubleshooting example](troubleshooting.md).

The [backup case study](case-study.md) shows why a database and its related
settings must be recovered together, and how an isolated render checked the result.
[Local examples](examples/README.md) demonstrate timeout handling and a misleading
SQLite integrity result with synthetic data.

For customer service, this demonstrates learning unfamiliar software, describing
problems clearly, investigating connected systems, protecting data and checking
the user's actual outcome. [Validation](validation.md) and [source notes](SOURCES.md)
separate newly run local checks from dated historical records. An optional
[recording plan](demo-script.md) walks through the system safely.
