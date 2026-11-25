"""Runtime policy and fail-closed startup checks; no Hermes SDK required."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest

GUARD = Path(__file__).resolve().parents[1] / 'apps/hermes/runtime_guard'
sys.path.insert(0, str(GUARD))
from telegram_policy import TelegramPolicy


class TelegramPolicyTests(unittest.TestCase):
    def test_numeric_user_lists(self):
        for value in ('123456', '123456,789012', ' 123456 , 789012 '):
            with self.subTest(value=value):
                self.assertIn('123456', TelegramPolicy(value).allowed_users)

    def test_invalid_lists_stop_python_before_command_without_echoing_values(self):
        for value in ('', '*', '123456,*', '   ', '@PRIVATE-FIXTURE', '-100123456',
                      '0', '123456,', ',123456', '123456,,789012', '١٢٣',
                      '123456\n789012', '12345678901234567'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    TelegramPolicy(value)
                result = subprocess.run([sys.executable, '-c', 'print("COMMAND_STARTED")'],
                    env={**os.environ, 'PYTHONPATH': str(GUARD),
                         'TELEGRAM_BOT_TOKEN': 'fixture-token', 'TELEGRAM_ALLOWED_USERS': value},
                    capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('COMMAND_STARTED', result.stdout)
                self.assertNotIn('PRIVATE-FIXTURE', result.stderr)
                self.assertNotIn('fixture-token', result.stderr)

    def test_only_allowlisted_human_in_own_dm_is_authorized(self):
        policy = TelegramPolicy('123456')
        source = dict(chat_type='dm', user_id='123456', chat_id='123456', is_bot=False)
        self.assertTrue(policy.allows(SimpleNamespace(**source)))
        for override in ({'user_id': '654321'}, {'is_bot': True}, {'user_id': None},
                         {'chat_id': '-100123456'}, {'chat_id': '654321'},
                         *({'chat_type': kind} for kind in ('group', 'forum', 'channel', None))):
            with self.subTest(override=override):
                self.assertFalse(policy.allows(SimpleNamespace(**{**source, **override})))


if __name__ == '__main__':
    unittest.main()
