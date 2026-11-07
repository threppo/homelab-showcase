#!/usr/bin/env python3
"""Run on the Docker host: isolated, disposable Jikan runtime compatibility trial.

Requires Docker Compose's JSON config output. Production MongoDB is read only
via mongodump; all application requests and restores target private clones.
Private diagnostics and clone data remain in the printed /tmp directory.
"""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import shutil
import shlex
import subprocess
import tempfile
import time
import uuid


SERVICES = ("jikan_mongo", "jikan_redis", "jikan_typesense", "jikan_rest")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", default="/opt/example-stacks/jikan/compose.yaml")
    parser.add_argument("--image", default="homelab/jikan-rest:security-20261023")
    parser.add_argument("--source-mongo", default="jikan_mongo")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--typesense-snapshot", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    work = Path(tempfile.mkdtemp(prefix="jikan-check-"))
    project = "jikancheck" + uuid.uuid4().hex[:16]
    print(f"Private trial diagnostics: {work}", flush=True)
    log = (work / "commands.log").open("wb")
    compose = ["docker", "compose", "-p", project, "-f", str(work / "compose.json")]
    names = {service: project + "-" + service for service in SERVICES}

    def run(command, capture=False, timeout=120):
        log.write(("RUN " + json.dumps(command[:4]) + "\n").encode())
        log.flush()
        result = subprocess.run(command, stdout=subprocess.PIPE if capture else log,
                                stderr=log, timeout=timeout, check=True)
        return result.stdout if capture else None

    def inspect(name):
        return json.loads(run(["docker", "inspect", name], capture=True))[0]

    def wait(service, healthy=True):
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            state = inspect(names[service])["State"]
            if state.get("Status") in ("exited", "dead"):
                raise RuntimeError(f"{service} stopped")
            if state.get("Running") and (not healthy or state.get("Health", {}).get("Status") == "healthy"):
                return
            time.sleep(2)
        raise RuntimeError(f"{service} readiness timeout")

    def cleanup():
        # Never use `compose down`: inspect ownership before each removal.
        for service in reversed(SERVICES):
            try:
                obj = inspect(names[service])
                if obj["Config"].get("Labels", {}).get("com.docker.compose.project") == project:
                    run(["docker", "logs", names[service]], timeout=30)
                    run(["docker", "rm", "-f", names[service]], timeout=60)
            except (subprocess.SubprocessError, RuntimeError, KeyError, ValueError):
                pass
        try:
            network = json.loads(run(["docker", "network", "inspect", project + "-isolated"], capture=True))[0]
            if (network.get("Labels", {}).get("com.docker.compose.project") == project
                    and not network.get("Containers")):
                run(["docker", "network", "rm", project + "-isolated"])
        except (subprocess.SubprocessError, KeyError, ValueError):
            pass

    def interrupted(signum, frame):
        raise RuntimeError(f"Interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        source = Path(args.compose).resolve(strict=True)
        original = json.loads(run(["docker", "compose", "-f", str(source), "config", "--format", "json"], capture=True))
        if set(original["services"]) != set(SERVICES):
            raise RuntimeError("Unexpected production service set; review isolation assumptions")
        source_obj = inspect(args.source_mongo)
        if source_obj["Config"].get("Labels", {}).get("com.docker.compose.service") != "jikan_mongo":
            raise RuntimeError("Source is not the production Mongo Compose service")
        run(["docker", "image", "inspect", args.image], capture=True)
        # A sleeping scheduler shim prevents indexing/refresh cron tasks while
        # preserving the normal application bootstrap and RoadRunner command.
        scheduler = work / "supercronic-disabled"
        scheduler.write_text("#!/bin/sh\nexec sleep 2147483647\n")
        scheduler.chmod(0o755)
        candidate = {"services": {}, "networks": {"isolated": {"internal": True, "name": project + "-isolated"}}, "secrets": {}}
        for key, secret in original.get("secrets", {}).items():
            secret_path = Path(secret.get("file", ""))
            if not secret_path.is_absolute() or not secret_path.is_file():
                raise RuntimeError("Only existing file-backed secrets are supported")
            candidate["secrets"][key] = {"file": str(secret_path)}
        for service in SERVICES:
            old = original["services"][service]
            # Whitelist: never inherit host networking, extra_hosts, devices,
            # privileged mode, published ports, live volumes or Docker sockets.
            item = {k: old[k] for k in ("image", "hostname", "user", "environment", "command", "entrypoint", "healthcheck", "secrets", "expose") if k in old}
            item.update(container_name=names[service], restart="no", networks=["isolated"])
            item["volumes"] = []
            if service == "jikan_rest":
                item["image"] = args.image
                item["environment"] = dict(item.get("environment", {}))
                item["environment"].update(DB_HOST="jikan_mongo", REDIS_HOST="jikan_redis", TYPESENSE_HOST="jikan_typesense", APP_DEBUG="false", CACHE_DEFAULT_EXPIRE="86400")
                if old.get("volumes"):
                    raise RuntimeError("Unexpected application mounts; manual review required")
                item["volumes"].append({"type": "bind", "source": str(scheduler), "target": "/usr/bin/supercronic", "read_only": True})
            else:
                targets = {"jikan_mongo": "/data/db", "jikan_redis": "/data", "jikan_typesense": "/data"}
                data = work / service
                data.mkdir()
                if service == "jikan_typesense" and args.typesense_snapshot:
                    snapshot = args.typesense_snapshot.resolve(strict=True)
                    if any(x.is_symlink() for x in snapshot.rglob("*")):
                        raise RuntimeError("Snapshot contains symlinks; review before copying")
                    shutil.copytree(snapshot, data, dirs_exist_ok=True)
                item["volumes"].append({"type": "bind", "source": str(data), "target": targets[service]})
                if service == "jikan_mongo":
                    init = source.parent / "mongo-init.js"
                    if not init.is_file():
                        raise RuntimeError("Mongo initialization script missing")
                    item["volumes"].append({"type": "bind", "source": str(init), "target": "/docker-entrypoint-initdb.d/mongo-init.js", "read_only": True})
            candidate["services"][service] = item
        (work / "compose.json").write_text(json.dumps(candidate))
        resolved = json.loads(run(compose + ["config", "--format", "json"], capture=True))
        for service, item in resolved["services"].items():
            if (item.get("container_name") != names[service] or set(item.get("networks", {})) != {"isolated"}
                    or item.get("ports") or item.get("network_mode") or item.get("privileged")):
                raise RuntimeError("Isolation validation failed")
            for mount in item.get("volumes", []):
                owned = Path(mount["source"]).is_relative_to(work)
                safe_init = mount["source"] == str(source.parent / "mongo-init.js") and mount.get("read_only")
                if not owned and not safe_init:
                    raise RuntimeError("Unexpected non-isolated mount")
        if not resolved["networks"]["isolated"].get("internal"):
            raise RuntimeError("Trial network must be internal")
        # Refuse collisions instead of reusing even an extremely unlikely name.
        existing_names = run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture=True).decode().splitlines()
        existing_networks = run(["docker", "network", "ls", "--format", "{{.Name}}"], capture=True).decode().splitlines()
        if set(names.values()).intersection(existing_names) or project + "-isolated" in existing_networks:
            raise RuntimeError("Trial resource name collision")
        run(compose + ["up", "-d", "--pull", "never", "jikan_mongo", "jikan_redis", "jikan_typesense"])
        wait("jikan_mongo")
        wait("jikan_redis")
        wait("jikan_typesense", healthy=False)
        auth = ' --username "$(cat /run/secrets/jikan_db_admin_username)" --password "$(cat /run/secrets/jikan_db_admin_password)" --authenticationDatabase admin'
        dump_cmd = ["docker", "exec", args.source_mongo, "sh", "-ec", "exec mongodump" + auth + " --archive --db jikan"]
        restore_cmd = ["docker", "exec", "-i", names["jikan_mongo"], "sh", "-ec", "exec mongorestore" + auth + " --archive --nsInclude='jikan.*' --stopOnError"]
        with subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=log) as dump:
            try:
                subprocess.run(restore_cmd, stdin=dump.stdout, stdout=log, stderr=log, timeout=args.timeout, check=True)
                dump.stdout.close()
                if dump.wait(timeout=args.timeout):
                    raise RuntimeError("Production logical dump failed")
            finally:
                if dump.poll() is None:
                    dump.kill()
                    dump.wait()
        # Offline fixture: change freshness metadata ONLY in the restored clone.
        # Verified against the running image's /app/app/Support/CachedData.php:
        # lastModified() reads modifiedAt, falling back to updated_at; expiry()
        # adds CacheOptions TTL. DefaultCachedScraperService::find() scrapes MAL
        # only for empty/expired data. expiresAt is not consulted here.
        # Anime.php selects Mongo collection `anime`; retain the original payload
        # and require its title to survive the real PHP serialization path.
        clone_obj = inspect(names["jikan_mongo"])
        if (clone_obj["Config"].get("Labels", {}).get("com.docker.compose.project") != project
                or set(clone_obj["NetworkSettings"]["Networks"]) != {project + "-isolated"}):
            raise RuntimeError("Refusing fixture write to an unowned Mongo container")
        fixture_js = """
const clone = db.getSiblingDB('jikan');
if (clone.anime.countDocuments({mal_id: 1}) !== 1) {
  throw new Error('Expected exactly one restored anime 1 document');
}
const original = clone.anime.findOne({mal_id: 1});
if (typeof original.title !== 'string' || !original.title.length) {
  throw new Error('Restored anime 1 has no title');
}
const result = clone.anime.updateOne({_id: original._id}, {$set: {modifiedAt: new Date()}});
if (result.matchedCount !== 1) { throw new Error('Fixture freshness update failed'); }
print(JSON.stringify({mal_id: original.mal_id, title: original.title}));
"""
        fixture_output = run(["docker", "exec", names["jikan_mongo"], "sh", "-ec",
                              "exec mongosh --quiet" + auth + " --eval " + shlex.quote(fixture_js)], capture=True)
        fixture = json.loads(fixture_output.decode().strip().splitlines()[-1])
        (work / "offline-fixture.json").write_text(json.dumps(fixture))
        run(compose + ["up", "-d", "--pull", "never", "--no-deps", "jikan_rest"])
        wait("jikan_rest")
        typesense = json.loads(run(["docker", "exec", names["jikan_rest"], "curl", "--fail", "--silent", "--max-time", "15", "http://jikan_typesense:8108/health"], capture=True))
        if typesense.get("ok") is not True:
            raise RuntimeError("Typesense health failed")
        for endpoint in ("/v4/anime/1", "/v4/anime?q=cowboy&limit=1"):
            log.write(("ENDPOINT " + endpoint + "\n").encode())
            body = run(["docker", "exec", names["jikan_rest"], "curl", "--silent", "--show-error", "--max-time", "45", "http://127.0.0.1:8080" + endpoint], capture=True)
            (work / ("response-detail.json" if "anime/1" in endpoint else "response-search.json")).write_bytes(body)
            response = json.loads(body)
            if endpoint == "/v4/anime/1":
                if (response.get("data", {}).get("mal_id") != fixture["mal_id"]
                        or response.get("data", {}).get("title") != fixture["title"]):
                    raise RuntimeError("Cached anime detail check failed")
            elif not isinstance(response.get("data"), list) or not isinstance(response.get("pagination"), dict):
                raise RuntimeError("Anime search response structure failed")
        app_logs = subprocess.run(["docker", "logs", names["jikan_rest"]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, check=True).stdout
        (work / "application.log").write_bytes(app_logs)
        if re.search(rb"PHP Fatal error|Uncaught (?:Error|Exception)|segmentation fault", app_logs, re.IGNORECASE):
            raise RuntimeError("Application fatal error in trial logs")
        print("PASS: isolated health, restored anime 1 payload served offline by PHP after clone-only freshness adjustment, and search response structure. Empty search is allowed for fresh Typesense.", flush=True)
        print("Limitations: no external fetches, production writes, full search reindex or scheduler execution.", flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # Deliberately avoid exception text: tooling errors may include secrets.
        print(f"FAIL ({type(error).__name__}); inspect private diagnostics at {work}", flush=True)
        log.write((type(error).__name__ + "\n").encode())
        if isinstance(error, RuntimeError):
            log.write((str(error) + "\n").encode())
        return 1
    finally:
        cleanup()
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
