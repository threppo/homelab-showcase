#!/usr/bin/env python3
"""Rebuild reviewed local images from a saved maintenance context; never deploy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('context', type=Path)
    parser.add_argument('--name', action='append', help='Build only this recorded service (repeatable)')
    parser.add_argument('--execute', action='store_true', help='Build images; default only verifies and prints plan')
    args = parser.parse_args()
    root = args.context.resolve()
    manifest = json.loads((root / 'rebuild-manifest.json').read_text())
    for filename, expected in manifest['context_sha256'].items():
        path = (root / filename).resolve()
        if not path.is_relative_to(root):
            raise SystemExit('Context path escapes maintenance directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('Context hash mismatch: ' + filename)
    selected = set(args.name or [])
    known = {entry['name'] for entry in manifest['images']}
    if selected - known:
        raise SystemExit('Unknown service: ' + ', '.join(sorted(selected - known)))
    for entry in manifest['images']:
        if selected and entry['name'] not in selected:
            continue
        command = ['docker', 'build', '-f', entry['dockerfile'], '-t', entry['tag']]
        for key, value in sorted(entry['build_args'].items()):
            if key.endswith('_IMAGE') and '@sha256:' not in value:
                raise SystemExit('Unpinned image in manifest: ' + key)
            command += ['--build-arg', key + '=' + value]
        command += ['.']
        print(json.dumps({'name': entry['name'], 'command': command}), flush=True)
        if args.execute:
            subprocess.run(command, cwd=root / entry['context'], check=True)


if __name__ == '__main__':
    main()
