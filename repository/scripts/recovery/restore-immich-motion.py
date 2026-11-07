#!/usr/bin/env python3
"""Recover embedded motion clips only when their restored database checksum matches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def media_path(root, recorded, motion=False):
    relative = Path(recorded).relative_to('/data')
    destination = (root / relative).resolve()
    if not relative.parts or not destination.is_relative_to(root) or (motion and relative.parts[0] != 'encoded-video'):
        raise ValueError('Media path escapes the reviewed storage location')
    return destination


def embedded_clip(data, checksum, algorithm):
    # Older originals can contain a trailer after the embedded MP4. Compare both
    # the suffix and ISO BMFF box boundaries, without trusting offsets alone.
    starts = {match.start() - 4 for match in re.finditer(b'ftyp', data) if match.start() >= 4}
    starts.update(len(data) - int(value) for value in
                  re.findall(rb'MicroVideoOffset=["\x27](\d+)', data[:100000])
                  if 0 < int(value) <= len(data))
    matches = set()
    for start in starts:
        ends = {len(data)}
        end = start
        while end + 8 <= len(data):
            size = int.from_bytes(data[end:end + 4], 'big')
            minimum = 8
            if size == 1 and end + 16 <= len(data):
                size = int.from_bytes(data[end + 8:end + 16], 'big')
                minimum = 16
            if size < minimum or end + size > len(data):
                break
            end += size
            ends.add(end)
        for end in ends:
            if hashlib.new(algorithm, memoryview(data)[start:end]).hexdigest() == checksum:
                matches.add((start, end))
    if len(matches) != 1:
        raise ValueError('No unique embedded clip matches the database checksum')
    start, end = matches.pop()
    return data[start:end]


def recover(root, rows, apply=False):
    root = Path(root).resolve(strict=True)
    if not isinstance(rows, list) or not rows:
        raise ValueError('Expected a nonempty JSON list of restored motion-photo pairs')
    counts = {'verified_existing': 0, 'recoverable': 0, 'written': 0}
    seen = set()
    for row in rows:
        photo = media_path(root, row['photo'])
        target = media_path(root, row['video'], motion=True)
        algorithm = row['algorithm']
        checksum = row['checksum']
        if algorithm not in ('sha1', 'sha256') or not re.fullmatch(
                '[0-9a-f]{' + str(hashlib.new(algorithm).digest_size * 2) + '}', checksum):
            raise ValueError('Invalid recorded checksum')
        if target in seen:
            raise ValueError('Duplicate motion-video destination')
        seen.add(target)
        if target.exists():
            if hashlib.new(algorithm, target.read_bytes()).hexdigest() != checksum:
                raise ValueError('Existing motion video differs from the recorded checksum; refusing replacement')
            counts['verified_existing'] += 1
            continue
        clip = embedded_clip(photo.read_bytes(), checksum, algorithm)
        counts['recoverable'] += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Never replace an existing clip, and never modify the source photo.
            with target.open('xb') as stream:
                stream.write(clip)
                stream.flush()
                os.fsync(stream.fileno())
            owner = target.parent.stat()
            if os.geteuid() == 0:
                os.chown(target, owner.st_uid, owner.st_gid)
            target.chmod(0o644)
            counts['written'] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('storage_root', type=Path)
    parser.add_argument('--apply', action='store_true', help='write checksum-verified missing clips; default is read-only')
    args = parser.parse_args()
    try:
        counts = recover(args.storage_root, json.loads(args.inventory.read_text()), args.apply)
    except (ValueError, KeyError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print(json.dumps(counts))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
