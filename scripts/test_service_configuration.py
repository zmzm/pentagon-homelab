"""Secret/identity preservation and recovery target safety regression tests."""
import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
import yaml
import service_configuration as config
from recovery_safety import require_private_restore

ROOT = Path(__file__).resolve().parents[1]


class ManagedConfiguration(unittest.TestCase):
    def setUp(self):
        defaults = yaml.safe_load((ROOT / 'ansible/roles/service_configuration/defaults/main.yml').read_text())
        self.settings = defaults['homelab_matrix_homeserver']
        self.secrets = {key: 'disposable-fixture-' + key for key in config.MATRIX_SECRETS}
        self.previous = config.matrix_configuration(self.settings, None, self.secrets, 'fixture-password')
        self.tunnel_settings = defaults['homelab_cloudflared_configuration']

    def test_matrix_reconstruction_and_adoption_preserve_secrets(self):
        self.assertEqual(config.matrix_configuration(self.settings, self.previous), self.previous)
        self.assertEqual(config.matrix_configuration(self.settings, None, self.secrets, 'fixture-password'), self.previous)

    def test_matrix_rejects_secret_identity_and_database_changes(self):
        altered = copy.deepcopy(self.settings)
        altered['server_name'] = 'different.invalid'
        with self.assertRaises(ValueError): config.matrix_configuration(altered, self.previous)
        with self.assertRaises(ValueError): config.matrix_configuration(self.settings, self.previous, password='different')
        with self.assertRaises(ValueError): config.matrix_configuration(self.settings, self.previous, {'form_secret':'different'})
        altered = copy.deepcopy(self.settings)
        altered['database']['args']['host'] = 'different'
        with self.assertRaises(ValueError): config.matrix_configuration(altered, self.previous)
        for path in ('/tmp/media', '/data/../media'):
            altered = copy.deepcopy(self.settings)
            altered['media_store_path'] = path
            with self.assertRaises(ValueError): config.matrix_configuration(altered, self.previous)
        previous = dict(self.previous, unmodeled_setting=True)
        with self.assertRaises(ValueError): config.matrix_configuration(self.settings, previous)

    def test_missing_synapse_secrets_are_rejected(self):
        with self.assertRaises(ValueError): config.matrix_configuration(self.settings, None, {}, 'fixture-password')

    def test_tunnel_is_reconstructed_from_credentials_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / 'fixture.json'
            tunnel = str(uuid.uuid4())
            path.write_text(json.dumps({'TunnelID':tunnel,'AccountTag':'fixture','TunnelSecret':base64.b64encode(b'x'*32).decode()}))
            candidate = config.tunnel_configuration(self.tunnel_settings, None, folder)
            self.assertEqual(candidate['tunnel'], tunnel)
            self.assertEqual(config.tunnel_configuration(self.tunnel_settings, candidate, folder), candidate)
            previous = dict(candidate, tunnel=str(uuid.uuid4()))
            with self.assertRaises(ValueError): config.tunnel_configuration(self.tunnel_settings, previous, folder)
            invalid = copy.deepcopy(self.tunnel_settings)
            invalid['ingress'][-1] = {'service':'http_status:200'}
            with self.assertRaises(ValueError): config.tunnel_configuration(invalid, candidate, folder)

    def test_production_path_and_permissive_restore_root_are_rejected(self):
        with self.assertRaises(RuntimeError): require_private_restore(ROOT)
        with tempfile.TemporaryDirectory(prefix='homelab-restore-',dir='/tmp') as directory:
            root = Path(directory)
            path = root / 'userdata/homelab'
            path.mkdir(parents=True)
            self.assertEqual(require_private_restore(path),path)
            root.chmod(0o755)
            with self.assertRaises(RuntimeError): require_private_restore(path)


if __name__ == '__main__': unittest.main()
