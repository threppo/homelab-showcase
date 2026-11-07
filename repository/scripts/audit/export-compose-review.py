#!/usr/bin/env python3
"""Fixed-path Compose inventory. Never read .env or print environment values.

This is a review inventory, not deployable Compose. Values from environment,
labels and executable commands are never printed.
"""
import json
import re
import sys
from pathlib import Path

import yaml

FILES = (
    '/opt/example-stacks/bookorbit/docker-compose.yml',
    '/opt/example-stacks/bookorbit/docker-compose.override.yml',
    '/opt/example-stacks/postersplus/compose.yaml',
)
FIELDS = ('image', 'container_name', 'restart', 'user', 'ports', 'volumes',
          'depends_on', 'networks', 'read_only', 'init', 'working_dir', 'expose',
          'cap_add', 'cap_drop', 'security_opt', 'stop_grace_period', 'tmpfs',
          'mem_limit', 'pull_policy')
HEALTH_FIELDS = ('interval', 'timeout', 'retries', 'start_period', 'start_interval',
                 'disable')


def inventory(document):
    result = {'services': {}}
    for name, service in (document.get('services') or {}).items():
        row = {key: service[key] for key in FIELDS if key in service}
        environment = service.get('environment') or {}
        names = environment.keys() if isinstance(environment, dict) else (
            item.split('=', 1)[0] for item in environment)
        row['environment_names'] = sorted(
            key for key in names if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key))
        row['has_env_file'] = 'env_file' in service
        row['omitted_fields'] = sorted(set(service) - set(FIELDS) - {'environment', 'env_file'})
        if 'healthcheck' in service:
            row['healthcheck'] = {
                key: service['healthcheck'][key] for key in HEALTH_FIELDS
                if key in service['healthcheck']
            }
            row['healthcheck']['test'] = '<redacted command>'
        if 'labels' in service:
            labels = service['labels'] or {}
            names = labels.keys() if isinstance(labels, dict) else (
                item.split('=', 1)[0] for item in labels)
            row['label_names'] = sorted(names)
        result['services'][name] = row
    # Network/volume driver options can contain credentials: publish names only.
    for key in ('networks', 'volumes', 'configs', 'secrets'):
        if key in document:
            result[key + '_names'] = sorted((document[key] or {}).keys())
    return result


def main():
    if len(sys.argv) != 1:
        raise SystemExit('No arguments accepted.')
    results = {}
    for filename in FILES:
        try:
            document = yaml.safe_load(Path(filename).read_text()) or {}
            results[filename] = inventory(document)
        except PermissionError:
            results[filename] = {'error': 'permission denied'}
        except FileNotFoundError:
            results[filename] = {'error': 'file missing'}
        except Exception:
            # Parser errors may echo sensitive source lines; do not print them.
            results[filename] = {'error': 'invalid or unsupported Compose structure'}
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
