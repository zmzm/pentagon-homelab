"""Source bundle guards must reject private material even if Git lists it."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import build_recovery_bundle as bundle


class SourceBundleGuards(unittest.TestCase):
    def test_bundle_cannot_be_created_inside_its_backup_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'data').mkdir()
            with patch.object(bundle, 'ROOT', root), patch.object(bundle.os, 'geteuid', return_value=0), patch.object(bundle, 'source_files') as files:
                with self.assertRaisesRegex(RuntimeError, 'outside'):
                    bundle.build(root / 'data/recovery-bundle')
                files.assert_not_called()
            self.assertFalse((root / 'data/recovery-bundle').exists())

    def test_private_files_and_runtime_directories_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            (root / 'README.md').write_text('public source')
            self.assertEqual(bundle.source_files(root), ['README.md'])
            for name in ('.env', '.env.production', 'config.env', 'key.pem', 'matrix.vault.yml',
                         'inventory.ssh.yml', 'id_ed25519', 'data/runtime.json', 'backups/config'):
                with self.subTest(name=name):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('disposable private fixture')
                    with self.assertRaises(RuntimeError): bundle.source_files(root)
                    path.unlink()
            (root / '.env.example').write_text('PLACEHOLDER=')
            self.assertEqual(bundle.source_files(root), ['.env.example', 'README.md'])

    def test_symlinked_source_is_rejected_before_archiving(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            (root / 'linked-file').symlink_to('/etc/hostname')
            with self.assertRaises(RuntimeError): bundle.source_files(root)


if __name__ == '__main__': unittest.main()
