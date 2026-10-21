"""Exercise the Matrix importer with disposable secrets and real Vault encryption."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ANSIBLE = Path(__file__).resolve().parents[1]


class MatrixVaultImport(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='matrix-vault-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / '.env'
        self.output = self.root / 'matrix.vault.yml'
        self.unlock = self.root / 'unlock'
        self.unlock.write_text('disposable-fixture-unlock\n')
        self.unlock.chmod(0o600)
        self.environment = dict(os.environ, ANSIBLE_LOCAL_TEMP=str(self.root / 'ansible-local'))

    def import_file(self):
        return subprocess.run(['python3', '-B', str(ANSIBLE / 'import-matrix-vault.py'),
                               '--source', str(self.source), '--output', str(self.output),
                               '--vault-password-file', str(self.unlock)],
                              capture_output=True, text=True, env=self.environment)

    def test_encrypted_round_trip_private_output_and_unchanged_source(self):
        original = "# retained source\nMATRIX_POSTGRES_PASSWORD='fixturePassword-123_+/='\n"
        self.source.write_text(original)
        result = self.import_file()
        self.assertEqual(result.returncode, 0, result.stderr)
        ciphertext = self.output.read_bytes()
        self.assertTrue(ciphertext.startswith(b'$ANSIBLE_VAULT;'))
        self.assertNotIn(b'fixturePassword', ciphertext)
        self.assertNotIn('fixturePassword', result.stdout + result.stderr)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.source.read_text(), original)
        decrypted = subprocess.run(['ansible-vault', 'view', str(self.output),
                                    '--vault-password-file', str(self.unlock)],
                                   capture_output=True, text=True, check=True, env=self.environment)
        self.assertEqual(json.loads(decrypted.stdout),
                         {'vault_matrix_postgres_password': 'fixturePassword-123_+/='})

    def test_existing_output_and_symlink_cannot_be_overwritten(self):
        self.source.write_text('MATRIX_POSTGRES_PASSWORD=fixturePassword\n')
        self.output.write_text('existing vault')
        self.assertNotEqual(self.import_file().returncode, 0)
        self.assertEqual(self.output.read_text(), 'existing vault')
        self.output.unlink()
        target = self.root / 'untouched'
        target.write_text('keep')
        self.output.symlink_to(target)
        self.assertNotEqual(self.import_file().returncode, 0)
        self.assertEqual(target.read_text(), 'keep')

    def test_invalid_sources_are_rejected_without_creating_output(self):
        for contents in ('MATRIX_POSTGRES_PASSWORD=\n',
                         'MATRIX_POSTGRES_PASSWORD=REPLACE_WITH_EXISTING_PASSWORD\n',
                         'MATRIX_POSTGRES_PASSWORD=fixture\nEXTRA=keep\n',
                         'MATRIX_POSTGRES_PASSWORD=fixture$interpolation\n'):
            with self.subTest(contents=contents):
                self.source.write_text(contents)
                self.assertNotEqual(self.import_file().returncode, 0)
                self.assertFalse(self.output.exists())

    def test_failed_encryption_removes_incomplete_output(self):
        self.source.write_text('MATRIX_POSTGRES_PASSWORD=fixturePassword\n')
        self.unlock.unlink()
        self.assertNotEqual(self.import_file().returncode, 0)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
