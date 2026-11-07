# Export validation — 2026-10-29

## Update — 2026-11-07

After the validation below, one stack was removed from this public copy, along
with its dated notes and its dashboard, backup-list and recovery entries. Claude
Code made that change and re-ran what it could on a Windows machine without Docker,
the SQLite CLI, rsync or jq. The results further down are from 2026-10-29: they ran
against the earlier copy with the full toolchain and were **not** repeated in full.

| Check on 2026-11-07 | Result |
| --- | --- |
| Shell syntax, Python AST, YAML/JSON parsing, runbook shell blocks | Passed |
| Markdown code fences, local links, manifest against files, recovery stacks against `stacks/` | Passed; the manifest lists 88 files and the recovery list 12 stacks |
| `repository/scripts/homepage/test-config.py` | 4 tests passed; updated for the removed services and now checks the remaining private credential reference |
| `repository/scripts/homepage/test-lol-schedule.cjs` | 3 tests passed |
| `repository/scripts/backup/test-bookorbit-dump.sh` | Valid dump accepted; 5 failure fixtures rejected |
| `repository/scripts/recovery/test-immich-motion.py` | 4 of 6 passed; 2 need POSIX user IDs or symlink rights |
| `repository/scripts/backup/test-postersplus-capture.py` | 5 passed; 11 skipped because they need the SQLite CLI and rsync |
| `repository/scripts/backup/test-dump-timeouts.py` | 2 of 5 passed; 3 process-timeout tests fail or hang on Windows |
| `repository/scripts/recovery/test-recovery.py` | 8 of 15 passed, including runbook shell syntax; 5 failed and 1 hung here; 1 skipped without Docker |

Suites ran from an LF copy through a small local harness that adapts paths for
Windows; the tests themselves were not changed for this. Each suite gave the same
test-by-test outcome on the previous commit on the same machine, so the removal did
not change them. The tests that failed, hung or were skipped here remain unverified
against this copy.

`validate-showcase.py` stops on this machine because the SQLite CLI, rsync and jq
are missing. `repository/scripts/validate-repo.sh` was not run: it needs Docker
Compose and a Git root at `repository/`. Compose files were parsed as YAML only.
No container was started and no live service was touched.

Codex validated the sanitized original-source snapshot as well as the smaller
showcase examples. No production checks were run.

## Original source tests, run in a temporary copy

| Suite | Result |
| --- | --- |
| `repository/scripts/backup/test-dump-timeouts.py` | 5 Python tests passed; real shortened timeouts, fake container command |
| `repository/scripts/backup/test-postersplus-capture.py` | 16 Python tests passed; real temporary SQLite/filesystem fixtures, mocked containers and notification requests |
| `repository/scripts/recovery/test-recovery.py` | 14 Python tests passed; 1 real Docker/Compose parsing test deliberately skipped |
| `repository/scripts/recovery/test-immich-motion.py` | 6 Python tests passed; invented byte/checksum fixtures, no personal media |
| `repository/scripts/homepage/test-config.py` | 4 Python tests passed; local configuration parsing only |
| `repository/scripts/homepage/test-lol-schedule.cjs` | 3 Node tests passed; synthetic schedule fixtures, no upstream fetch |
| `repository/scripts/backup/test-bookorbit-dump.sh` | Valid dump accepted; 5 failure fixtures rejected as expected; Docker shell stub only |

Total: **45 Python tests passed, 1 skipped; 3 Node tests passed; 6 Bash fixture
cases behaved as expected**. Expected errors from corrupt/incomplete dump fixtures
are successful negative checks, not production failures.

The [safe runner](validate-showcase.py) repeats these checks using a fresh temporary
copy, a minimal environment and guards blocking unmocked Docker, HTTP, SSH, Restic,
sudo and service commands. The tests use local dependencies already installed:
Python 3 with SQLite and PyYAML, Node, Bash, SQLite CLI, rsync, jq and standard GNU
utilities. No dependency was installed or downloaded. This is controlled fixture
execution, not an operating-system isolation guarantee for arbitrary unreviewed code.

One initial export regression failed because the censoring missed an escaped
storage path in an installer comparison rule. The exported rule was corrected
consistently with its fixtures, and the source suites and final runner passed.
The original repository was not changed.

## Static and packaging checks

- All 10 exported shell source files, including the extensionless storage-report
  tool, passed `bash -n`; they were not operationally executed.
- All 12 exported original Python files passed AST parsing. The new runner and
  showcase Python examples were also parsed.
- All exported YAML and JSON configuration files parsed successfully. This is
  syntax parsing, not Compose deployment validation, a Docker build or proof of
  runtime compatibility.
- Local Markdown links resolve inside the export. Missing source-document links
  explicitly point to the omission note. Intentional runtime dependencies absent
  from the snapshot are listed in `EXPORT.md`.
- The manifest lists 88 copied source files (93 at this validation, before the
  2026-11-07 removal). No Git metadata, symlinks, real
  environment/secret files, backup contents, private inventories, logs, bytecode
  caches or media/library records were included. Original executable flags and
  source comments/notices were preserved.
- Automated pattern checks and a separate read-only review checked personal
  identity values, deployment domains/hosts, live addresses, credentials,
  webhook/account/bucket/snapshot identifiers and personal storage paths.
  Necessary deployment values are marked examples. Public software URLs, public
  image/source digests, generic service keys and loopback/wildcard constants are
  retained deliberately. Pattern checks do not guarantee detection of every secret.

## Earlier small examples

The unchanged explanatory examples previously passed 1 synthetic SQLite test and
5 adapted timeout tests, plus shell syntax. They are supplementary; the actual
original-source suites above are now the core validation evidence. The network
sketch parsed as YAML and remains deliberately incomplete.

## What was not checked

The full Git-aware repository validator and hosted CI were inspected, not run.
The real Compose parsing test was skipped, and no images were pulled or built.
Backup/installer/remote-restore scripts and runbook deployment commands were not
executed. No service, network, production file, real application login, alert,
snapshot or recovery job was touched. Nothing was pushed or published by that
validation.

Historical networking, recovery and troubleshooting records remain dated
September–October 2026. They do not establish current production state, complete
snapshot coverage, every restored user workflow or full disaster-recovery bounds.
Earlier AI transcripts and exact historical code authorship remain unavailable;
no project-level public-reuse license was discovered.

Bounded read-only supporting reviews checked source-test dependencies, privacy
and packaging; the parent reviewed findings and corrected omissions. No approval
or production-access escalation was needed.
