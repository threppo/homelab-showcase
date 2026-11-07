#!/usr/bin/env python3
"""Local regression checks; no Docker daemon, credentials or production writes."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts/recovery/recovery-functions.sh"
DOC = ROOT / "docs/disaster-recovery-runbook.md"
spec = importlib.util.spec_from_file_location("pins", LIB.with_name("prepare-image-pins.py"))
pins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pins)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="recovery-test-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.tool("sudo", '#!/bin/sh\nexec "$@"\n')
        # The host may lack psmisc; emulate fuser by inspecting accessible /proc FDs.
        self.tool("fuser", '''#!/usr/bin/env python3
import os, pathlib, sys
target = os.path.realpath(sys.argv[-1])
for process in pathlib.Path('/proc').iterdir():
    if not process.name.isdigit(): continue
    try:
        for fd in (process / 'fd').iterdir():
            try:
                if os.readlink(fd) == target: sys.exit(0)
            except OSError: pass
    except OSError: pass
sys.exit(1)
''')
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + os.environ["PATH"],
                    "RECOVERY_DIR": str(self.work), "CALL_LOG": str(self.work / "calls")}

    def tool(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def shell(self, code):
        return subprocess.run(["bash", "-c", 'source "$1"; ' + code, "test", str(LIB)],
                              env=self.env, text=True, capture_output=True)

    def database(self, name, value):
        path = self.work / name
        with closing(sqlite3.connect(path)) as db:
            db.execute("create table recovery(value text)")
            db.execute("insert into recovery values (?)", (value,))
            db.commit()
        return path

    def restore(self, backup, target):
        self.env.update(BACKUP=str(backup), TARGET=str(target))
        return self.shell('restore_sqlite "$BACKUP" "$TARGET" "$(id -u)" "$(id -g)"')

    def test_sqlite_stale_wal_is_quarantined(self):
        target = self.database("target.db", "snapshot")
        backup = self.work / "backup.db"
        shutil.copyfile(target, backup)
        subprocess.run(["python3", "-c", '''
import os, sqlite3, sys
c = sqlite3.connect(sys.argv[1]); c.execute('pragma journal_mode=wal')
c.execute('pragma wal_autocheckpoint=0')
c.execute("update recovery set value='stale WAL'"); c.commit(); os._exit(0)
''', str(target)], check=True)
        wal = Path(str(target) + "-wal")
        old_wal = wal.read_bytes()
        result = self.restore(backup, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("select value from recovery").fetchone()[0], "snapshot")
        saved = list(self.work.glob("target.db.before-restore.*"))
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0] / "target.db-wal").read_bytes(), old_wal)
        with closing(sqlite3.connect(saved[0] / "target.db")) as db:
            self.assertEqual(db.execute("select value from recovery").fetchone()[0], "stale WAL")

    def test_invalid_backup_leaves_target_unchanged(self):
        target = self.database("target.db", "keep")
        before = target.read_bytes()
        backup = self.work / "bad.db"
        backup.write_text("not a database")
        self.assertNotEqual(self.restore(backup, target).returncode, 0)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(list(self.work.glob("*.before-restore.*")), [])

    def test_database_in_use_is_rejected(self):
        target = self.database("target.db", "keep")
        backup = self.database("backup.db", "snapshot")
        db = sqlite3.connect(target)
        self.addCleanup(db.close)
        db.execute("select * from recovery").fetchall()
        result = self.restore(backup, target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("still in use", result.stderr)

    def test_restore_without_empty_application_start(self):
        backup = self.database("backup.db", "snapshot")
        target = self.work / "new.db"
        self.assertEqual(self.restore(backup, target).returncode, 0)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("select value from recovery").fetchone()[0], "snapshot")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_postgres_import_error_prevents_recreation(self):
        import gzip
        archive = self.work / "dump.sql.gz"
        with gzip.open(archive, "wt") as file:
            file.write("SELECT bad_sql;\n")
        self.env.update(ARCHIVE=str(archive), PGDATA=str(self.work / "fresh"))
        self.tool("docker", '''#!/bin/sh
printf '%s\n' "$*" >> "$CALL_LOG"
case "$*" in
  *ON_ERROR_STOP=1*) cat >/dev/null; exit 17 ;;
  *) exit 0 ;;
esac
''')
        code = '''recovery_compose() {
  case "$*" in
    *'config --format json'*) printf '%s' '{"services":{"postgres":{"environment":{"POSTGRES_DB":"books","POSTGRES_USER":"owner"}}}}' ;;
    *) printf '%s\\n' "$*" >> "$CALL_LOG" ;;
  esac
}
restore_postgres bookorbit postgres test-db "$ARCHIVE" "$PGDATA"
'''
        result = self.shell(code)
        self.assertEqual(result.returncode, 17, result.stderr)
        calls = (self.work / "calls").read_text()
        self.assertIn("ON_ERROR_STOP=1", calls)
        self.assertNotIn("force-recreate", calls)

    def test_image_pins_reject_missing_and_conflicting_digests(self):
        item = {"project": "postersplus", "service": "postersplus", "repo_digests": []}
        with self.assertRaises(ValueError):
            pins.prepare([item])
        first = {**item, "repo_digests": ["example/postersplus@sha256:" + "a" * 64]}
        other = {**item, "repo_digests": ["example/postersplus@sha256:" + "b" * 64]}
        with self.assertRaises(ValueError):
            pins.prepare([first, other])
        config = pins.prepare([first])["postersplus"]["services"]["postersplus"]
        self.assertEqual(config["restart"], "no")
        self.assertEqual(config["pull_policy"], "never")

    def test_retired_xrdb_cannot_start_through_current_recovery_helper(self):
        self.tool("docker", '#!/bin/sh\nprintf called >> "$CALL_LOG"\n')
        result = self.shell('recovery_compose xrdb up -d')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown recovery stack", result.stderr)
        self.assertFalse((self.work / "calls").exists())

    def test_postersplus_filesystem_manifest_rejects_missing_or_corrupt_state(self):
        source = (ROOT / "scripts/backup/test-remote-restore.sh").read_text()
        block = source.split("# The database and authored files must come from the same snapshot generation.", 1)[1].split("\narchive=", 1)[0]
        restored = self.work / "restored"
        cache = restored / "applications/postersplus/cache"
        files = {"settings.json": b'{"style":"original"}',
                 "custom_art/cover with spaces.webp": b"authored image",
                 "custom_fonts/font\\name.font": b"authored font"}
        for condition in ("good", "corrupt", "missing", "missing-cache"):
            with self.subTest(condition=condition):
                for name, content in files.items():
                    path = cache / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                manifest = subprocess.run(["sha256sum", "--", *[
                    "./applications/postersplus/cache/" + name for name in files]],
                    cwd=restored, capture_output=True, text=True, check=True).stdout
                # A partial restore must verify its authored files without requiring
                # unrelated system inventory files that were intentionally omitted.
                (restored / "SHA256SUMS").write_text(manifest + "a" * 64 + "  ./system/unrestored.json\n")
                if condition == "corrupt":
                    (cache / "settings.json").write_text("changed after capture")
                elif condition == "missing":
                    (cache / "custom_art/cover with spaces.webp").unlink()
                elif condition == "missing-cache":
                    shutil.rmtree(cache)
                self.env.update(TEST_WORK=str(self.work), TEST_RESTORED=str(restored))
                result = self.shell('set -Eeuo pipefail; work=$TEST_WORK; restored=$TEST_RESTORED;\n' + block)
                if condition == "good":
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)

    def test_installer_retirement_baseline_preserves_unrelated_entries(self):
        source = (ROOT / "scripts/backup/install-backup-extension.sh").read_text()
        definition = "retirement_baseline() {" + source.split("retirement_baseline() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
        repo = self.work / "reviewed"
        (repo / "backup").mkdir(parents=True)
        installed = self.work / "installed-sources"
        self.env.update(TEST_REPO=str(repo), TEST_INSTALLED=str(installed))
        cases = {
            "backup-sources.txt": ("/srv/example-app-data/postersplus\n/srv/example-app-data/arcane\n",
                                   "/srv/example-app-data/xrdb\n"),
            "backup-excludes.txt": ("/srv/example-app-data/postersplus/cache\n/srv/example-app-data/lumiere-db\n",
                "".join("/srv/example-app-data/xrdb/" + name + "\n" for name in
                        ("xrdb.db", "xrdb.db-wal", "xrdb.db-shm", "xrdb.db.settings",
                         "xrdb.db.settings-wal", "xrdb.db.settings-shm"))),
            "sqlite-databases.conf": ("postersplus|/srv/example-app-data/postersplus/cache/cache.db\n",
                "# XRDB default paths; confirm the installed XRDB_DB before deployment.\n"
                "xrdb-profiles|/srv/example-app-data/xrdb/xrdb.db\n"
                "xrdb-settings|/srv/example-app-data/xrdb/xrdb.db.settings\n"),
        }
        for name, (active, retired) in cases.items():
            (repo / "backup" / name).write_text(active)
            self.env["TEST_CONFIG"] = "backup/" + name
            for extra, expected in [("", 0), ("/srv/example-app-data/production-only\n", 1)]:
                with self.subTest(config=name, extra=extra):
                    original = retired + active + extra
                    installed.write_text(original)
                    result = self.shell(definition + '\nrepo=$TEST_REPO; retirement_baseline "$TEST_CONFIG" "$TEST_INSTALLED"')
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual(installed.read_text(), original)

    def test_installer_failure_restores_existing_script_and_removes_new_helper(self):
        source = (ROOT / "scripts/backup/install-backup-extension.sh").read_text()
        definition = "restore_on_error() {" + source.split("restore_on_error() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
        rollback = self.work / "rollback"
        rollback.mkdir()
        (rollback / "0").write_text("original backup script")
        existing = self.work / "backup-script"
        existing.write_text("new backup script")
        helper = self.work / "new-capture-helper"
        helper.write_text("new helper")
        self.env.update(TEST_ROLLBACK=str(rollback), TEST_EXISTING=str(existing), TEST_HELPER=str(helper))
        result = self.shell(definition + '\nrollback=$TEST_ROLLBACK; targets=("$TEST_EXISTING" "$TEST_HELPER"); false; restore_on_error')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(existing.read_text(), "original backup script")
        self.assertFalse(helper.exists())

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI needed for offline Compose parsing")
    def test_compose_merges_bookorbit_override_pins_and_bootstrap(self):
        stack = self.work / "stacks/bookorbit"
        stack.mkdir(parents=True)
        (stack / "docker-compose.yml").write_text('''services:
  app:
    image: example/app:latest
    restart: unless-stopped
    volumes: ["./data:/data"]
  postgres:
    image: example/postgres:latest
    environment: {POSTGRES_USER: owner, POSTGRES_DB: books}
''')
        (stack / "docker-compose.override.yml").write_text('''services:
  app:
    volumes: ["/srv/example-library/audiobooks:/books/Audiobooks:ro"]
''')
        images = self.work / "images"
        images.mkdir()
        data = {"services": {name: {"image": f"example/{name}@sha256:" + "a" * 64,
                                    "pull_policy": "never", "restart": "no"}
                             for name in ("app", "postgres")}}
        (images / "bookorbit.json").write_text(json.dumps(data))
        bootstrap = self.work / "bootstrap.json"
        bootstrap.write_text(json.dumps({"services": {"postgres": {"environment": {
            "POSTGRES_USER": "restore_admin", "POSTGRES_DB": "postgres"}}}}))
        self.env.update(STACKS_ROOT=str(self.work / "stacks"), BOOTSTRAP=str(bootstrap))
        result = self.shell('recovery_compose bookorbit -f "$BOOTSTRAP" config --format json')
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        self.assertEqual(services["postgres"]["environment"]["POSTGRES_USER"], "restore_admin")
        self.assertEqual(services["app"]["restart"], "no")
        self.assertEqual(services["app"]["pull_policy"], "never")
        self.assertTrue(any(v["target"] == "/books/Audiobooks" for v in services["app"]["volumes"]))
        del data["services"]["postgres"]
        (images / "bookorbit.json").write_text(json.dumps(data))
        self.assertNotEqual(self.shell('recovery_compose bookorbit config --quiet').returncode, 0)

    def test_container_readiness_is_bounded_and_reports_failure(self):
        self.tool("sleep", "#!/bin/sh\nexit 0\n")
        self.tool("docker", '''#!/bin/sh
case "$*" in
  *'State.Status'*) echo 'running starting' ;;
  *'json .State'*) echo '{"Status":"running"}' ;;
  *logs*) echo 'readiness diagnostics' ;;
esac
''')
        result = self.shell('wait_recovery_container test-container')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Readiness failed", result.stderr)
        self.assertIn("readiness diagnostics", result.stderr)

    def test_runbook_shell_syntax(self):
        blocks = re.findall(r"```bash\n(.*?)```", DOC.read_text(), re.S)
        for index, block in enumerate(blocks, 1):
            result = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, f"Block {index}: {result.stderr}")

    def test_recorded_owner_errors_are_explicit_and_prevent_restore(self):
        text = DOC.read_text()
        definition = text.split("restore_sqlite_with_recorded_owner() {", 1)[1].split("\n}\n", 1)[0]
        definition = "restore_sqlite_with_recorded_owner() {" + definition + "\n}\n"
        definition = definition.replace("/var/backups/example-homelab/current/system/sqlite-ownership.conf",
                                        '"$OWNER_FILE"')
        owner_file = self.work / "owners.conf"
        self.env["OWNER_FILE"] = str(owner_file)
        cases = [
            ("other|/other.db|1000|1000|600\n", "no recorded owner", 1),
            ("sample|/sample.db|1000|1000|600\n" * 2, "duplicate recorded owners", 1),
            ("sample|/sample.db|invalid|1000|600\n", "invalid recorded UID/GID", 1),
            ("sample|/sample.db|1000|1000|600\n", "", 0),
        ]
        for content, message, status in cases:
            with self.subTest(content=content):
                owner_file.write_text(content)
                code = definition + '''
restore_sqlite() { printf 'RESTORE:%s:%s\\n' "$3" "$4"; }
restore_sqlite_with_recorded_owner /backup/sample.sqlite /target/sample.db
'''
                result = self.shell(code)
                self.assertEqual(result.returncode, status, result.stderr)
                if status:
                    self.assertIn(message, result.stderr)
                    self.assertIn("sample", result.stderr)
                    self.assertNotIn("RESTORE:", result.stdout)
                else:
                    self.assertEqual(result.stdout.strip(), "RESTORE:1000:1000")

    @unittest.skipUnless(shutil.which("node"), "Node needed to execute Mongo validation JavaScript")
    def test_mongo_validation_quoting_and_failure_cases(self):
        blocks = re.findall(r"```bash\n(.*?)```", DOC.read_text(), re.S)
        block = next(b for b in blocks if "const names = db.getCollectionNames()" in b)
        inner = block.split("sh -lc '", 1)[1].rsplit("'", 1)[0]
        self.tool("mongosh", '''#!/usr/bin/env python3
import json, sys
print(json.dumps(sys.argv[1:]))
''')
        result = self.shell('cat() { printf mock; }; ' + inner)
        args = json.loads(result.stdout)
        self.assertEqual(args[-2], "--eval")
        js = args[-1]
        self.assertIn('print("ERROR: no collections found")', js)
        for names, valid, status in [(["anime"], True, 0), ([], True, 2), (["anime"], False, 3)]:
            harness = ('global.quit=c=>process.exit(c);global.print=()=>{};global.printjson=()=>{};'
                       'global.db={getCollectionNames:()=>NAMES,getCollection:()=>({countDocuments:()=>12}),'
                       'runCommand:()=>({valid:VALID})};eval(process.argv[1]);')
            harness = harness.replace("NAMES", json.dumps(names)).replace("VALID", json.dumps(valid))
            run = subprocess.run(["node", "-e", harness, js], capture_output=True, text=True)
            self.assertEqual(run.returncode, status, run.stderr)


if __name__ == "__main__":
    unittest.main()
