"""Compose interpolation and credential boundaries, using public fixtures only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TelegramComposeTests(unittest.TestCase):
    def setUp(self):
        self.empty = tempfile.NamedTemporaryFile()
        self.addCleanup(self.empty.close)
        self.env = dict(os.environ)
        for line in (ROOT / 'apps/hermes/.env.example').read_text().splitlines():
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                self.env[key] = value or 'offline-fixture'
        self.env.update(DOCKER_GID='984', TELEGRAM_ALLOWED_USERS='123456')

    def render(self, overrides=None):
        return subprocess.run(
            ['docker', 'compose', '--env-file', self.empty.name, 'config', '--format', 'json'],
            cwd=ROOT / 'apps/hermes', env={**self.env, **(overrides or {})},
            capture_output=True, text=True, timeout=30)

    def test_required_telegram_values(self):
        for key in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_ALLOWED_USERS'):
            with self.subTest(key=key):
                self.assertNotEqual(self.render({key: ''}).returncode, 0)

    def test_known_gap_allowlist_syntax_is_not_validated(self):
        # TG-03 evidence: nonempty interpolation is not numeric-ID validation.
        for value in ('*', '123456,*', '   ', '@fixture', '-100123456'):
            with self.subTest(value=value):
                result = self.render({'TELEGRAM_ALLOWED_USERS': value})
                self.assertEqual(result.returncode, 0, 'Fixture Compose rendering failed; output suppressed')
                self.assertEqual(json.loads(result.stdout)['services']['hermes']['environment']
                                 ['TELEGRAM_ALLOWED_USERS'], value)

    def test_telegram_cannot_inherit_open_access_or_publish_ports(self):
        result = self.render({'GATEWAY_ALLOW_ALL_USERS': 'true', 'GATEWAY_ALLOWED_USERS': '*',
                              'TELEGRAM_ALLOW_ALL_USERS': 'true', 'TELEGRAM_WEBHOOK_URL': 'https://fixture.invalid'})
        self.assertEqual(result.returncode, 0, 'Fixture Compose rendering failed; output suppressed')
        services = json.loads(result.stdout)['services']
        hermes = services['hermes']
        env = hermes['environment']
        self.assertEqual(env['TELEGRAM_ALLOWED_USERS'], '123456')
        for key in ('TELEGRAM_ALLOW_ALL_USERS', 'GATEWAY_ALLOW_ALL_USERS',
                    'TELEGRAM_GUEST_MODE', 'TELEGRAM_OBSERVE_UNMENTIONED_GROUP_MESSAGES'):
            self.assertEqual(env[key], 'false')
        self.assertEqual(env['TELEGRAM_ALLOW_BOTS'], 'none')
        for key in ('GATEWAY_ALLOWED_USERS', 'TELEGRAM_WEBHOOK_URL',
                    'TELEGRAM_GROUP_ALLOWED_USERS', 'TELEGRAM_GROUP_ALLOWED_CHATS'):
            self.assertEqual(env[key], '')
        self.assertFalse({'APPROVER_TOKEN', 'BROKER_TOKEN'} & env.keys())
        self.assertFalse(any('docker.sock' in v.get('source', '') for v in hermes['volumes']))
        self.assertTrue(all(not service.get('ports') for service in services.values()))
        self.assertEqual(env['MATRIX_ALLOWED_USERS'], self.env['MATRIX_ALLOWED_USERS'])
        self.assertIn('matrix-approvals', services)


if __name__ == '__main__':
    unittest.main()
