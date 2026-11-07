#!/usr/bin/env python3
"""Mock Docker; exercise real SQLite/filesystem captures without production access."""
from contextlib import closing
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = (ROOT / "scripts/backup/capture-postersplus-state.sh").read_text()
BACKUP = (ROOT / "scripts/backup/homelab-restic-backup.sh").read_text()
PARSE = "MODE=normal" + BACKUP.split("MODE=normal", 1)[1].split("(( EUID", 1)[0]
NOTIFY = "notify() {" + BACKUP.split("notify() {", 1)[1].split('\nexec 9>', 1)[0]
FINISH = "finish() {" + BACKUP.split("finish() {", 1)[1].split('\ntrap finish EXIT', 1)[0]
LOCK = "exec 9>" + BACKUP.split("exec 9>", 1)[1].split('\nfinish() {', 1)[0]
WEBHOOK_CHECK = 'if [[ $NOTIFICATIONS_DISABLED == false ]]; then' + BACKUP.split(
    'if [[ $NOTIFICATIONS_DISABLED == false ]]; then', 1)[1].split('\nfi', 1)[0] + '\nfi\n'


@unittest.skipUnless(shutil.which("sqlite3") and shutil.which("rsync"), "sqlite3 and rsync required")
class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="postersplus-capture-test-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.live = self.work / "live-cache"
        self.live.mkdir()
        self.generation = self.work / "generation"
        self.generation.mkdir(mode=0o700)
        (self.generation / "sqlite").mkdir(mode=0o700)
        self.output = self.generation / "sqlite/postersplus.sqlite"
        self.files = self.generation / "applications/postersplus/cache"
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.events = self.work / "events"
        self.state = self.work / "state.json"
        self.state.write_text(json.dumps({"running": True}))
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        FIXTURE_LIVE=str(self.live), FIXTURE_STATE=str(self.state),
                        FIXTURE_EVENTS=str(self.events))
        db = self.live / "cache.db"
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("create table authored (image text, title text)")
            connection.execute("insert into authored values ('cover.webp', 'saved title')")
            connection.commit()
        (self.live / "settings.json").write_text('{"WORKERS":"1"}')
        (self.live / "discovery_overrides.json").write_text('{"directors":["fixture"]}')
        for folder in ("custom_art", "preset_art", "custom_fonts", "new_authored_state"):
            (self.live / folder).mkdir()
            (self.live / folder / "cover.webp").write_bytes(b"operator artwork")
        (self.live / "custom_fonts/fonts.json").write_text('[{"name":"saved font"}]')
        (self.live / "cache.db.notes").write_text("keep unknown files")
        for folder in ("tmdb_posters", "tmdb_logos", "company_logos", "commons"):
            (self.live / folder).mkdir()
            (self.live / folder / "generated").write_bytes(b"regenerated")
        for name in ("anime_ids.db", "imdb_ratings.db"):
            for suffix in ("", "-wal", "-shm", "-journal"):
                (self.live / (name + suffix)).write_bytes(b"regenerated")
        self.executable("docker", '''#!/usr/bin/env python3
from contextlib import closing
import json, os, pathlib, sqlite3, sys
args = sys.argv[1:]
live = pathlib.Path(os.environ["FIXTURE_LIVE"])
state_path = pathlib.Path(os.environ["FIXTURE_STATE"])
state = json.loads(state_path.read_text())
with open(os.environ["FIXTURE_EVENTS"], "a") as log:
    log.write(args[0] + "\\n")
if args[0] == "inspect":
    format = args[args.index("--format") + 1]
    if '"mounts"' in format:
        print(json.dumps({"id": "a" * 64, "name": "/postersplus",
            "project": os.environ.get("WRONG_PROJECT", "postersplus"), "service": "postersplus",
            "running": state["running"], "paused": bool(os.environ.get("PAUSED")),
            "status": "running" if state["running"] else "exited",
            "mounts": [{"Destination": "/app/cache", "Type": "bind", "RW": True,
                "Source": os.environ.get("WRONG_MOUNT", str(live))}]}))
    elif format == '{{.State.Running}}':
        print("true" if state["running"] else "false")
    else:
        print("exited unhealthy" if os.environ.get("FAIL_HEALTH") else
              ("running healthy" if state["running"] else "exited healthy"))
elif args[0] == "stop":
    if os.environ.get("FAIL_STOP"): sys.exit(29)
    state["running"] = False
    state_path.write_text(json.dumps(state))
elif args[0] == "start":
    state["running"] = True
    state_path.write_text(json.dumps(state))
    if os.environ.get("MUTATE_ON_START"):
        with closing(sqlite3.connect(live / "cache.db")) as db:
            db.execute("update authored set title='later edit'")
            db.commit()
        (live / "settings.json").write_text('{"WORKERS":"2"}')
        (live / "custom_art/cover.webp").unlink(missing_ok=True)
else:
    sys.exit(99)
''')
        real_rsync = shutil.which("rsync")
        self.executable("rsync", f'''#!/bin/bash
if [[ ${{FAIL_COPY:-}} == 1 ]]; then
    printf partial > "${{@: -1}}partial"
    exit 28
fi
exec {shlex.quote(real_rsync)} "$@"
''')
        # Replace only the fixed production source in a protected fixture copy.
        self.helper = self.work / "capture-fixture.sh"
        self.helper.write_text(CAPTURE.replace("source_dir=/srv/example-app-data/postersplus/cache",
                                              "source_dir=" + shlex.quote(str(self.live))))

    def executable(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o700)

    def capture(self):
        return subprocess.run(["bash", "-c", 'source "$1"; capture_postersplus_state "$2" "$3" "$4"',
                               "fixture", str(self.helper), str(self.live / "cache.db"),
                               str(self.output), str(self.files)], env=self.env,
                              capture_output=True, text=True, timeout=15)

    def commands(self):
        return self.events.read_text().splitlines() if self.events.exists() else []

    def test_matching_generation_survives_post_restart_edits(self):
        self.env["MUTATE_ON_START"] = "1"
        result = self.capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(sqlite3.connect(self.output)) as db:
            image, title = db.execute("select image,title from authored").fetchone()
        self.assertEqual(title, "saved title")
        self.assertEqual((self.files / "custom_art" / image).read_bytes(), b"operator artwork")
        self.assertEqual(json.loads((self.files / "settings.json").read_text()), {"WORKERS": "1"})
        self.assertEqual((self.files / "new_authored_state/cover.webp").read_bytes(), b"operator artwork")
        self.assertTrue((self.files / "custom_fonts/fonts.json").exists())
        self.assertTrue((self.files / "cache.db.notes").exists())
        for name in ("cache.db", "tmdb_posters", "tmdb_logos", "company_logos", "commons", "anime_ids.db", "imdb_ratings.db"):
            self.assertFalse((self.files / name).exists(), name)
        self.assertEqual(self.files.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.files / "settings.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.commands().count("stop"), 1)
        self.assertEqual(self.commands().count("start"), 1)
        self.assertTrue(json.loads(self.state.read_text())["running"])

    def test_main_sqlite_loop_uses_frozen_capture_without_recopy_after_restart(self):
        self.env["MUTATE_ON_START"] = "1"
        (self.generation / "system").mkdir(mode=0o700)
        self.helper.write_text(self.helper.read_text().replace(
            "    (( EUID == 0 )) || { echo 'ERROR: run as root' >&2; exit 1; }\n", ""))
        self.helper.chmod(0o700)
        mapping = self.work / "sqlite-map.conf"
        mapping.write_text(f"postersplus|{self.live}/cache.db\n")
        function = "backup_sqlite() {" + BACKUP.split("backup_sqlite() {", 1)[1].split(
            "\nrun_database_dump() {", 1)[0]
        function = function.replace("capture_helper=/usr/local/sbin/homelab-capture-postersplus-state.sh",
                                    "capture_helper=" + shlex.quote(str(self.helper)))
        # The fixture helper belongs to this test user, rather than production root.
        function = function.replace("== 0:700", f"== {os.getuid()}:700")
        code = function + '\nWORK_DIR=$1 SQLITE_MAP=$2 SQLITE_COUNT=0; backup_sqlite; printf "COUNT:%s" "$SQLITE_COUNT"'
        result = subprocess.run(["bash", "-euc", code, "fixture", str(self.generation), str(mapping)],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COUNT:1", result.stdout)
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(db.execute("select title from authored").fetchone()[0], "saved title")
        with closing(sqlite3.connect(self.live / "cache.db")) as db:
            self.assertEqual(db.execute("select title from authored").fetchone()[0], "later edit")
        record = (self.generation / "system/sqlite-ownership.conf").read_text().strip().split("|")
        self.assertEqual(record[:2], ["postersplus", str(self.live / "cache.db")])
        self.assertEqual(record[2], str(os.getuid()))
        self.assertTrue((self.files / "custom_art/cover.webp").exists())

    def test_generic_sqlite_loop_still_copies_other_databases(self):
        (self.generation / "system").mkdir(mode=0o700)
        mapping = self.work / "sqlite-map.conf"
        mapping.write_text(f"other-service|{self.live}/cache.db\n")
        function = "backup_sqlite() {" + BACKUP.split("backup_sqlite() {", 1)[1].split(
            "\nrun_database_dump() {", 1)[0]
        code = function + '\nWORK_DIR=$1 SQLITE_MAP=$2 SQLITE_COUNT=0; backup_sqlite; printf "COUNT:%s" "$SQLITE_COUNT"'
        result = subprocess.run(["bash", "-euc", code, "fixture", str(self.generation), str(mapping)],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COUNT:1", result.stdout)
        self.assertTrue((self.generation / "sqlite/other-service.sqlite").exists())
        self.assertEqual(self.commands(), [])

    def test_committed_wal_data_is_captured(self):
        subprocess.run(["python3", "-c", '''
import os,sqlite3,sys
c=sqlite3.connect(sys.argv[1]); c.execute('pragma journal_mode=wal')
c.execute('pragma wal_autocheckpoint=0')
c.execute("update authored set title='committed in WAL'"); c.commit(); os._exit(0)
''', str(self.live / "cache.db")], check=True)
        self.assertTrue((self.live / "cache.db-wal").exists())
        result = self.capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(db.execute("select title from authored").fetchone()[0], "committed in WAL")
        self.assertFalse((self.files / "cache.db-wal").exists())
        self.assertFalse((self.files / "cache.db-shm").exists())

    def test_initially_stopped_service_remains_stopped(self):
        self.state.write_text(json.dumps({"running": False}))
        result = self.capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("stop", self.commands())
        self.assertNotIn("start", self.commands())
        self.assertFalse(json.loads(self.state.read_text())["running"])

    def test_copy_failure_resumes_service_and_discards_partial_capture(self):
        self.env["FAIL_COPY"] = "1"
        result = self.capture()
        self.assertEqual(result.returncode, 28, result.stderr)
        self.assertTrue(json.loads(self.state.read_text())["running"])
        self.assertEqual(self.commands().count("start"), 1)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.files.parent.exists())

    def test_invalid_database_resumes_service(self):
        (self.live / "cache.db").write_text("invalid database")
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.commands().count("start"), 1)
        self.assertTrue(json.loads(self.state.read_text())["running"])
        self.assertFalse(self.output.exists())

    def test_mismatched_mount_or_identity_never_stops_service(self):
        for variable in ("WRONG_MOUNT", "WRONG_PROJECT"):
            with self.subTest(variable=variable):
                self.env[variable] = "/unexpected"
                result = self.capture()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("stop", self.commands())
                self.assertNotIn("start", self.commands())
                self.assertFalse(self.output.exists())
                self.env.pop(variable)

    def test_restart_health_failure_fails_capture(self):
        self.env["FAIL_HEALTH"] = "1"
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("administrator action required", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.files.parent.exists())

    def test_paused_service_is_refused_without_state_change(self):
        self.env["PAUSED"] = "1"
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("stop", self.commands())
        self.assertNotIn("start", self.commands())
        self.assertFalse(self.output.exists())

    def test_capture_destination_cannot_overlap_live_data(self):
        self.live.chmod(0o700)
        self.generation = self.live
        (self.live / "sqlite").mkdir(mode=0o700)
        self.output = self.live / "sqlite/postersplus.sqlite"
        self.files = self.live / "applications/postersplus/cache"
        result = self.capture()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.commands(), [])
        with closing(sqlite3.connect(self.live / "cache.db")) as db:
            self.assertEqual(db.execute("select title from authored").fetchone()[0], "saved title")


class NotificationTests(unittest.TestCase):
    def run_shell(self, arguments, body):
        with tempfile.TemporaryDirectory(prefix="backup-notification-test-") as directory:
            work = Path(directory)
            log = work / "http-tools"
            code = PARSE + '\n' + NOTIFY + '\n' + FINISH + '''
jq() { printf jq >> "$CALL_LOG"; printf '{}'; }
curl() { printf curl >> "$CALL_LOG"; cat >/dev/null; }
WORK_DIR= RUNTIME_EXCLUDES= START_EPOCH=$(date +%s) STEP=fixture
HOST_SHORT=fixture SQLITE_COUNT=9 BACKUP_SET_SIZE=fixture SNAPSHOT_ID=fixture
BACKUP_PARTIAL=false PRUNE_STATUS=no LOG_FILE=fixture DISCORD_WEBHOOK_URL=fixture
''' + body
            return subprocess.run(["bash", "-c", code, "fixture", *arguments],
                                  env=dict(os.environ, CALL_LOG=str(log), LOCK_FILE=str(work / "lock")),
                                  capture_output=True, text=True, timeout=5), log.read_text() if log.exists() else ""

    def test_no_notify_guards_every_finish_branch(self):
        for dry_run in (False, True):
            for rc in (0, 1, 3):
                with self.subTest(dry_run=dry_run, rc=rc):
                    arguments = ["--no-notify"] + (["--dry-run"] if dry_run else [])
                    result, calls = self.run_shell(arguments,
                        f"BACKUP_PARTIAL=true; trap finish EXIT; exit {rc}\n")
                    self.assertEqual(result.returncode, rc, result.stderr)
                    self.assertEqual(calls, "")

    def test_no_notify_guards_lock_contention(self):
        result, calls = self.run_shell(["--no-notify"], 'flock() { return 1; };\n' + LOCK)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")

    def test_existing_default_still_notifies(self):
        result, calls = self.run_shell([], 'notify fixture\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("jq", calls)
        self.assertIn("curl", calls)

    def test_disabled_notifications_do_not_require_a_webhook(self):
        result, calls = self.run_shell(["--no-notify"],
                                      'unset DISCORD_WEBHOOK_URL;\n' + WEBHOOK_CHECK + 'notify fixture\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")
        result, calls = self.run_shell([], 'unset DISCORD_WEBHOOK_URL;\n' + WEBHOOK_CHECK)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing DISCORD_WEBHOOK_URL", result.stderr)
        self.assertEqual(calls, "")

    def test_flags_work_in_both_orders_and_reject_unknown_option(self):
        result, calls = self.run_shell(["--dry-run", "--no-notify"], 'notify fixture\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")
        result, calls = self.run_shell(["--unknown"], 'notify fixture\n')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, "")


if __name__ == "__main__":
    unittest.main()
