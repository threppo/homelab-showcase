> Sanitized source snapshot. Identifying values and selected private records were replaced or omitted. Operational commands are for inspection only.

# Deploy the reviewed recovery backup changes

This installs the updated backup script and reviewed lists. It does not start
recovery helpers, restore databases, restart application stacks or change secrets.
Use the reviewed, merged PostersPlus deployment/retirement changes and confirm
their CI checks pass before installation. See [current deployment evidence](postersplus-deployment.md).

The `example-reviewer` account has no sudo permission to perform this deployment.
An administrator must run these commands on `example-host`. Use a checkout of
the merged commit containing the reviewed installer; do not execute a script
from an unreviewed working tree. The example production checkout is
`/home/EXAMPLE_OWNER/homelab-infrastructure`; confirm its actual location as its owner.

## Prepare the checkout

As the repository owner, update the clean `main` checkout with `git pull --ff-only`
and verify its HEAD against the GitHub merge commit. Resolve local modifications
before continuing; do not reset or overwrite them. Keep full Git history so the
installer can compare production with the reviewed baseline commits.

Run the checks from that checkout:

```bash
./scripts/validate-repo.sh
python3 scripts/recovery/test-recovery.py
bash scripts/backup/test-bookorbit-dump.sh
python3 scripts/backup/test-dump-timeouts.py
python3 scripts/backup/test-postersplus-capture.py
```

Database containers must provide `timeout` (with `-k` support) and `sh`.
Each database dump runs with a 30-minute limit inside its container, with a
30-second grace period before forced termination. A separate 32-minute host
limit bounds the Docker connection. Exceeding either limit fails the backup;
the script does not publish the incomplete dump set as `current`. The systemd
unit also limits the whole scheduled job to six hours. Both PostgreSQL dumps
must contain the `pg_dumpall` completion marker.

## Install with rollback

In a root Bash shell, set `repo` to the verified checkout:

```bash
sudo -i
set -Eeuo pipefail
umask 077
repo=/home/EXAMPLE_OWNER/homelab-infrastructure
systemctl stop homelab-restic-backup.timer
systemctl is-active homelab-restic-backup.service || true
```

If the service is active, let it finish before installation; do not kill it.
The installer obtains the same nonblocking lock as the backup job and refuses
installation if a backup is running. It accepts only files matching the new
checkout or a reviewed historical version. Any unrecognized installed
file stops deployment; compare it locally and preserve production-only entries.
Do not print credentials or `.env` contents into chat.

```bash
bash "$repo/scripts/backup/install-backup-extension.sh"
bash -n /usr/local/sbin/homelab-restic-backup.sh
cmp "$repo/scripts/backup/homelab-restic-backup.sh" /usr/local/sbin/homelab-restic-backup.sh
```

Record the protected rollback directory printed by the installer. Installation
errors restore the previous files, including the PostersPlus capture helper,
automatically. For a later runtime
failure, stop the timer and wait for any backup to finish, then restore files
from that directory (its indexes map to the installer `targets` array). Do not
delete that rollback copy until a complete backup is verified.

## Verify a complete backup before enabling the timer

The commands below create real database dumps. `--no-notify` suppresses Discord
notifications; omitting that flag uses normal notification behavior.
`--dry-run` is not read-only and briefly pauses PostersPlus for coherent capture.
The full backup also applies configured retention
and may prune the repository on Sunday.

```bash
/usr/local/sbin/homelab-restic-backup.sh --dry-run --no-notify
/usr/local/sbin/homelab-restic-backup.sh --no-notify
base=/var/backups/example-homelab/current
(cd "$base" && sha256sum --check SHA256SUMS)
jq -e 'length > 0 and all(.[]; .image_id != null and .repo_digests != null)' \
  "$base/system/docker-recovery-images.json" >/dev/null
for name in uptime-kuma aiometadata grafana aiostreams postersplus; do
  test "$(awk -F '|' -v n="$name" '$1 == n {count++} END {print count+0}' \
    "$base/system/sqlite-ownership.conf")" = 1
done
set -a
source /etc/example-restic/homelab-s3.env
set +a
snapshot=$(sed -n 's/^snapshot=//p' "$base/.remote-success")
[[ $snapshot =~ ^[0-9a-f]{64}$ ]]
restic snapshots "$snapshot" --json > /var/tmp/homelab-deploy-snapshot.json
jq -e 'length == 1 and (.[0] | .hostname == "example-host" and
  ((.tags // []) | index("homelab") != null and index("automatic") != null and index("complete") != null))' \
  /var/tmp/homelab-deploy-snapshot.json >/dev/null
```

Inspect the new snapshot for all three database dumps, all five SQLite copies, matching
`current/applications/postersplus/cache/` state, and both inventory files, following the runbook's snapshot checks.
Record the snapshot ID and any missing repository digests; unavailable digests
still require the manual image recovery fallback. Only after verification:

```bash
systemctl enable --now homelab-restic-backup.timer
systemctl status homelab-restic-backup.timer --no-pager
exit
```

A successful deployment verifies backup generation, not full disaster recovery.
The dated PostersPlus isolated restore/render and Bookorbit database-import
checks are recorded in the deployment notes and runbook. A complete host/client
disaster-recovery exercise remains distinct from those checks.
