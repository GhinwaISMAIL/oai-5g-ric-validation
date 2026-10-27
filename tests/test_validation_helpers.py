import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ReceiverTests(unittest.TestCase):
    def test_drain_is_applied_to_both_receivers_without_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            docker = directory / 'docker'
            docker.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
  *State.Status*) echo running ;;
  *'mgen version'*) echo 'invalid command' ;;
  *'addr show'*) echo '1: oaitun_ue1 inet 12.1.1.2/24' ;;
  *'route get'*) echo 'dev oaitun_ue1' ;;
  *statistics*) echo 0 ;;
esac
''')
            docker.chmod(0o755)
            for name, args in (
                ('cell', ['listen-dl', 'run', '1', '2', '6102', '900']),
                ('cell', ['run-script', 'run', '1', '2', 'rx.mgn', '900', 'rx']),
                ('core', ['listen-ul', 'run', '1', '2', '5102', '900']),
                ('core', ['run-script', 'run', 'rx.mgn', '900', 'rx']),
            ):
                with self.subTest(name=name, args=args):
                    calls = directory / 'calls'
                    calls.write_text('')
                    env = dict(os.environ, PATH=f'{directory}:' + os.environ['PATH'],
                               CALLS=str(calls), MGEN_DRAIN_SECONDS='600',
                               MGEN_HOST_LOG_DIR=str(directory))
                    subprocess.run(['bash', str(ROOT / f'bin/mgen-{name}.sh'), *args],
                                   env=env, capture_output=True, text=True, check=True)
                    self.assertIn("timeout '1500'", calls.read_text())
                    env['MGEN_DRAIN_SECONDS'] = '-1'
                    result = subprocess.run(['bash', str(ROOT / f'bin/mgen-{name}.sh'), *args],
                                            env=env, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)

    def test_generated_qos_matches_local_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'base.sql'
            output = Path(directory) / 'output.sql'
            base.write_text('-- base\n')
            command = ['bash', str(ROOT / 'bin/gen-subscribers.sh'), '1', '2', str(base), str(output)]
            subprocess.run(command, capture_output=True, check=True)
            sql = output.read_text().replace('\\"', '"')
            rows = [line for line in sql.splitlines() if 'sessionAmbr' in line]
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertIn('"5qi": 9', row)
                self.assertIn('"uplink":"200Mbps"', row)
                self.assertIn('"downlink":"400Mbps"', row)


class EvidenceTests(unittest.TestCase):
    def test_inspects_running_image_id_and_excludes_environment(self):
        spec = importlib.util.spec_from_file_location('evidence', ROOT / 'bin/collect-cell-evidence.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        container = {'Name': '/ric5g-gnb-cell1', 'Image': 'sha256:running',
                     'Config': {'Image': 'example:tag', 'Env': ['SECRET=value']},
                     'State': {'Running': True}, 'HostConfig': {}}
        def fake(*args):
            if args[:2] == ('docker', 'ps'):
                return 'container-id'
            if args[:2] == ('docker', 'inspect'):
                return json.dumps([container])
            if args[:3] == ('docker', 'image', 'inspect'):
                self.assertEqual(args[3], 'sha256:running')
                return '[{"Config": {"Labels": null}}]'
            if args[:2] == ('docker', 'stats'):
                return '{"Name":"ric5g-gnb-cell1"}'
            return 'CPU topology'
        with patch.object(module, 'run', side_effect=fake):
            result = module.collect()
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertIsNone(result['containers'][0]['provenance']['org.opencontainers.image.revision'])


if __name__ == '__main__':
    unittest.main()
