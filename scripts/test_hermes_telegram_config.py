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
        self.env.update(DOCKER_GID='984', TELEGRAM_ALLOWED_USERS='123456', TELEGRAM_HOME_CHAT_ID='123456', OPENCODE_BINARY='/usr/bin/true')

    def render(self, overrides=None):
        return subprocess.run(
            ['docker', 'compose', '--env-file', self.empty.name, 'config', '--format', 'json'],
            cwd=ROOT / 'apps/hermes', env={**self.env, **(overrides or {})},
            capture_output=True, text=True, timeout=30)

    def test_required_telegram_values(self):
        for key in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_ALLOWED_USERS', 'TELEGRAM_APPROVAL_BOT_TOKEN', 'TELEGRAM_HOME_CHAT_ID'):
            with self.subTest(key=key):
                self.assertNotEqual(self.render({key: ''}).returncode, 0)

    def test_runtime_authorization_guard_cannot_be_overridden_by_ambient_pythonpath(self):
        result = self.render({'PYTHONPATH': '/untrusted-fixture'})
        self.assertEqual(result.returncode, 0, 'Fixture Compose rendering failed; output suppressed')
        hermes = json.loads(result.stdout)['services']['hermes']
        self.assertEqual(hermes['environment']['PYTHONPATH'], '/integration/runtime-guard:/opt/hermes')
        guard = next(v for v in hermes['volumes'] if v['target'] == '/integration/runtime-guard')
        self.assertTrue(guard['read_only'])
        self.assertEqual(Path(guard['source']), ROOT / 'apps/hermes/runtime_guard')

    def test_python_cache_is_private_ephemeral_and_pinned(self):
        result = self.render({'PYTHONPYCACHEPREFIX': '/untrusted-fixture'})
        self.assertEqual(result.returncode, 0, 'Fixture Compose rendering failed; output suppressed')
        hermes = json.loads(result.stdout)['services']['hermes']
        self.assertEqual(hermes['environment']['PYTHONPYCACHEPREFIX'], '/tmp/hermes-pycache')
        self.assertIn('/tmp/hermes-pycache:uid=10000,gid=10000,mode=0700,size=128m', hermes['tmpfs'])

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
        self.assertFalse(any(key.startswith('MATRIX_') for key in env))
        self.assertNotIn('matrix-approvals', services)
        relay = services['telegram-approvals']
        self.assertEqual(relay['environment']['TELEGRAM_HOME_CHAT_ID'], '123456')
        self.assertNotIn('TELEGRAM_BOT_TOKEN', relay['environment'])
        self.assertNotIn('TELEGRAM_APPROVAL_BOT_TOKEN', env)
        self.assertFalse(any('docker.sock' in v.get('source', '') for v in relay['volumes']))
        self.assertEqual(relay['command'], ['node', 'src/telegram-approvals.mjs'])
        self.assertEqual(env['TELEGRAM_HOME_CHANNEL'], '123456')


if __name__ == '__main__':
    unittest.main()
