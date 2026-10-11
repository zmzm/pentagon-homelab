import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import backup_matrix_db


class AtomicDatabaseDump(unittest.TestCase):
    def test_failed_dump_or_invalid_archive_preserves_last_good_copy(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                final = target / 'synapse.dump'
                final.write_bytes(b'last good dump')
                calls = []

                def command(args, **kwargs):
                    calls.append(args)
                    if len(calls) == fail_at:
                        raise subprocess.CalledProcessError(1, args)
                    kwargs['stdout'].write(b'new archive')

                with patch.object(backup_matrix_db, 'DESTINATION', target), \
                     patch.object(backup_matrix_db.subprocess, 'run', side_effect=command):
                    with self.assertRaises(subprocess.CalledProcessError):
                        backup_matrix_db.main()
                self.assertEqual(final.read_bytes(), b'last good dump')
                self.assertFalse((target / 'synapse.dump.partial').exists())

    def test_success_publishes_private_dump(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)

            def command(args, **kwargs):
                if 'pg_dump' in args:
                    kwargs['stdout'].write(b'new archive')

            original_umask = os.umask(0o077)
            try:
                with patch.object(backup_matrix_db, 'DESTINATION', target), \
                     patch.object(backup_matrix_db.subprocess, 'run', side_effect=command):
                    backup_matrix_db.main()
                self.assertEqual((target / 'synapse.dump').read_bytes(), b'new archive')
                self.assertEqual((target / 'synapse.dump').stat().st_mode & 0o777, 0o600)
            finally:
                os.umask(original_umask)


if __name__ == '__main__':
    unittest.main()
