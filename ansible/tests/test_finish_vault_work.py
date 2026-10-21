"""The local Vault finish flow must keep unlock material private and clean it on failure."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'finish-vault-work.py'
spec = importlib.util.spec_from_file_location('finish_vault_work', PATH)
finish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finish)


class VaultUnlockLifecycle(unittest.TestCase):
    def test_failed_unlock_does_not_import_or_deploy_and_removes_unlock_file(self):
        observed = []
        def command(args):
            self.assertEqual(args[:2], ['ansible-vault', 'view'])
            path = Path(args[-1])
            observed.append(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.read_text(), 'disposable-fixture\n')
            return SimpleNamespace(returncode=1)
        mask = os.umask(0o077)
        try:
            with patch.object(finish.os, 'geteuid', return_value=0), \
                 patch.object(finish.getpass, 'getpass', return_value='disposable-fixture'), \
                 patch.object(finish, 'run', side_effect=command) as run:
                with self.assertRaises(SystemExit): finish.main()
                self.assertEqual(run.call_count, 1)
            self.assertFalse(observed[0].exists())
            self.assertFalse(observed[0].parent.exists())
        finally:
            os.umask(mask)

    def test_empty_password_stops_before_creating_unlock_material(self):
        with patch.object(finish.os, 'geteuid', return_value=0), \
             patch.object(finish.getpass, 'getpass', return_value=''), \
             patch.object(finish, 'run') as run:
            mask = os.umask(0o077)
            try:
                with self.assertRaises(SystemExit): finish.main()
                run.assert_not_called()
            finally: os.umask(mask)


if __name__ == '__main__': unittest.main()
