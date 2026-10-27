#!/usr/bin/env python3
"""Collect read-only radio image and cell resource evidence as JSON."""
import datetime
import json
import platform
import subprocess


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, check=True, timeout=60)
    return result.stdout.strip()


def collect():
    ids = run('docker', 'ps', '-aq', '--filter', 'name=ric5g-').split()
    containers = []
    for identifier in ids:
        item = json.loads(run('docker', 'inspect', identifier))[0]
        if not item['Name'].startswith(('/ric5g-gnb-cell', '/ric5g-ue-cell')):
            continue
        image = json.loads(run('docker', 'image', 'inspect', item['Image']))[0]
        labels = image.get('Config', {}).get('Labels') or {}
        limits = item.get('HostConfig', {})
        containers.append({
            'name': item['Name'].lstrip('/'),
            'running': item['State']['Running'],
            'image_reference': item['Config']['Image'],
            'image_id': item['Image'],
            'image_created': image.get('Created'),
            'repo_digests': image.get('RepoDigests', []),
            'provenance': {key: labels.get(key) for key in (
                'org.opencontainers.image.revision',
                'org.opencontainers.image.source',
                'org.opencontainers.image.version')},
            'limits': {key: limits.get(key) for key in (
                'NanoCpus', 'CpuQuota', 'CpuPeriod', 'CpusetCpus', 'Memory')},
        })
    active = [item['name'] for item in containers if item['running']]
    stats = run('docker', 'stats', '--no-stream', '--format', '{{json .}}', *active) if active else ''
    return {
        'collected_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'hostname': platform.node(),
        'cpu_topology': run('lscpu'),
        'containers': containers,
        'stats': [json.loads(line) for line in stats.splitlines()],
    }


if __name__ == '__main__':
    print(json.dumps(collect(), indent=2))
