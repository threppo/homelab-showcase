#!/usr/bin/env python3
"""Exercise real timeout processes with a local Docker stub; never use a daemon."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "scripts/backup/homelab-restic-backup.sh").read_text()
HELPER = SOURCE.split("run_database_dump() {", 1)[1].split("\ndump_databases() {", 1)[0]
HELPER = "run_database_dump() {" + HELPER


class DumpTimeoutTests(unittest.TestCase):
    def run_dump(self, script, stalled_docker=False, missing_inner_timeout=False):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            real_timeout = shutil.which("timeout")
            self.assertIsNotNone(real_timeout)
            # Preserve the production arguments, shorten only their durations.
            (work / "timeout").write_text(
                "#!/bin/bash\n"
                "case $1 in\n"
                "  --kill-after=30s) shift 2; duration=2s;;\n"
                "  -k) shift 3; duration=0.2s;;\n"
                "  *) exit 99;;\n"
                "esac\n"
                f'exec "{real_timeout}" -k 0.2s "$duration" "$@"\n'
            )
            # sh -lc resets PATH on some hosts; remove only -l in this stub.
            (work / "sh").write_text(
                '#!/bin/bash\nif [[ $1 == -lc ]]; then shift; exec /bin/sh -c "$@"; fi\n'
                'exec /bin/sh "$@"\n'
            )
            docker_body = 'shift 2\nexec "$@"\n'
            if stalled_docker:
                docker_body = 'exec /bin/sleep 20\n'
            elif missing_inner_timeout:
                docker_body = 'shift 2\nexport PATH=/nonexistent\nexec /bin/sh "${@:2}"\n'
            (work / "docker").write_text("#!/bin/bash\n" + docker_body)
            for executable in ("timeout", "sh", "docker"):
                (work / executable).chmod(0o700)
            env = dict(os.environ, PATH=f"{work}:{os.environ['PATH']}")
            result = subprocess.run(
                ["bash", "-c", HELPER + '\nrun_database_dump fixture "$1"', "bash", script],
                env=env, capture_output=True, text=True, timeout=5,
            )
            return result

    def test_success_and_dump_exit_status(self):
        self.assertEqual(self.run_dump("printf complete").stdout, "complete")
        self.assertEqual(self.run_dump("exit 23").returncode, 23)

    def test_inner_timeout_kills_dump_and_descendant(self):
        # The background child must receive TERM from the inner process group.
        script = "(trap 'echo child-terminated; exit 0' TERM; while :; do sleep 0.05; done) & wait"
        result = self.run_dump(script)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertIn("child-terminated", result.stdout)

    def test_inner_timeout_escalates_if_term_ignored(self):
        result = self.run_dump("trap '' TERM; exec sleep 20")
        self.assertEqual(result.returncode, 137, result.stderr)

    def test_host_timeout_bounds_stalled_docker(self):
        self.assertEqual(self.run_dump("unused", stalled_docker=True).returncode, 124)

    def test_missing_container_timeout_fails_explicitly(self):
        result = self.run_dump("unused", missing_inner_timeout=True)
        self.assertEqual(result.returncode, 127, result.stderr)
        self.assertIn("timeout is required inside", result.stderr)


if __name__ == "__main__":
    unittest.main()
