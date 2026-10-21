"""Remote-target guards must reject unsafe inventories before connecting."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ANSIBLE = Path(__file__).resolve().parents[1]


class RemoteTargetGuards(unittest.TestCase):
    def check_rejection(self, inventory):
        with tempfile.TemporaryDirectory(prefix='remote-guard-test-') as folder:
            result = subprocess.run(
                ['ansible-playbook', 'remote-preflight.yml', '-i', str(inventory)],
                cwd=ANSIBLE, capture_output=True, text=True,
                env=dict(os.environ, ANSIBLE_LOCAL_TEMP=str(Path(folder) / 'ansible-local')),
                timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Use one configured replacement host', result.stdout)
        self.assertNotIn('UNREACHABLE', result.stdout)

    def test_default_local_inventory_is_rejected(self):
        self.check_rejection(ANSIBLE / 'inventory.ini')

    def test_example_placeholders_are_rejected(self):
        self.check_rejection(ANSIBLE / 'inventory.ssh.example.yml')

    def test_multiple_targets_are_rejected_before_ssh(self):
        with tempfile.TemporaryDirectory(prefix='remote-inventory-test-') as folder:
            path = Path(folder) / 'inventory.yml'
            host = {'ansible_connection': 'ssh', 'ansible_host': '192.0.2.10',
                    'ansible_user': 'fixture', 'homelab_expected_hostname': 'fixture',
                    'homelab_expected_machine_id': 'a' * 32}
            path.write_text(yaml.safe_dump({'homelab': {'children': {
                'homelab_replacement': {'hosts': {'one': host, 'two': host}}}}}))
            self.check_rejection(path)


if __name__ == '__main__':
    unittest.main()
