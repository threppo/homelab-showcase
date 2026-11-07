#!/usr/bin/env python3
"""Synthetic showcase fixture inspired by the project's SQLite regression.

New Codex-produced example, not the operational restore helper. All database
paths originate inside TemporaryDirectory; no services or external data used.
"""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class SQLiteWALDemo(unittest.TestCase):
    def test_wrong_value_can_pass_integrity_then_generation_separation_fixes_fixture(self):
        with tempfile.TemporaryDirectory(prefix="showcase-sqlite-") as directory:
            work = Path(directory)
            target = work / "target.db"
            snapshot = work / "snapshot.db"
            with closing(sqlite3.connect(target)) as db:
                db.execute("CREATE TABLE example_state(value TEXT)")
                db.execute("INSERT INTO example_state VALUES ('snapshot')")
                db.commit()
                with closing(sqlite3.connect(snapshot)) as copy:
                    db.backup(copy)
            # Leave a committed WAL by ending only this fixture writer abruptly.
            subprocess.run([sys.executable, "-c", """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA journal_mode=WAL')
connection.execute('PRAGMA wal_autocheckpoint=0')
connection.execute("UPDATE example_state SET value='later change'")
connection.commit()
os._exit(0)
""", str(target)], check=True, timeout=10)
            # Preserve the whole fixture generation before demonstrating the bug.
            generation = work / "preserved"
            generation.mkdir()
            for suffix in ("", "-wal", "-shm"):
                path = Path(str(target) + suffix)
                self.assertTrue(path.exists())
                shutil.copyfile(path, generation / path.name)
            shutil.copyfile(snapshot, target)
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT value FROM example_state').fetchone()[0], 'later change')
            # Demonstrate generation separation with a fresh fixture, not a live DB.
            separated = work / "separated"
            separated.mkdir()
            for old in generation.iterdir():
                shutil.copyfile(old, separated / old.name)
            retained = separated / "old-generation"
            retained.mkdir()
            for suffix in ("", "-wal", "-shm"):
                path = separated / ("target.db" + suffix)
                path.rename(retained / path.name)
            restored = separated / "target.db"
            shutil.copyfile(snapshot, restored)
            with closing(sqlite3.connect(restored)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT value FROM example_state').fetchone()[0], 'snapshot')
            self.assertEqual((retained / 'target.db-wal').read_bytes(),
                             (generation / 'target.db-wal').read_bytes())


if __name__ == '__main__':
    unittest.main()
