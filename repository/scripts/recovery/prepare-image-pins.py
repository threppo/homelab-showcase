#!/usr/bin/env python3
"""Generate reviewed Compose overrides from a snapshot's selected image inventory."""
import json
import re
import sys
from pathlib import Path


def prepare(inventory):
    projects = {}
    for item in inventory:
        project, service = item.get("project"), item.get("service")
        if not project or not service:
            continue
        if not all(re.fullmatch(r"[a-zA-Z0-9_-]+", value) for value in (project, service)):
            raise ValueError("Invalid Compose project/service")
        digests = item.get("repo_digests", [])
        if not digests or not all(re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", value) for value in digests):
            raise ValueError(f"No usable repository digest for {project}/{service}")
        # Each RepoDigest names the same image. Choose deterministically.
        definition = {"image": sorted(digests)[0], "pull_policy": "never", "restart": "no"}
        services = projects.setdefault(project, {"services": {}})["services"]
        if service in services and services[service] != definition:
            raise ValueError(f"Conflicting image versions for {project}/{service}")
        services[service] = definition
    if not projects:
        raise ValueError("No Compose services in image inventory")
    return projects


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: prepare-image-pins.py INVENTORY.json OUTPUT_DIRECTORY")
    projects = prepare(json.loads(Path(sys.argv[1]).read_text()))
    output = Path(sys.argv[2])
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    for project, config in projects.items():
        path = output / f"{project}.json"
        if path.exists():
            raise ValueError(f"Refusing to overwrite image pins: {path}")
    for project, config in projects.items():
        (output / f"{project}.json").write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
