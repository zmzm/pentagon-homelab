"""Docker repository inspection must preserve matching sources and reject conflicts."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'roles/host_prerequisites/files/docker_repository.py'
spec = importlib.util.spec_from_file_location('docker_repository', SCRIPT)
repository = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository)


class DockerRepositoryInspection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='docker-repo-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / 'etc/apt/sources.list.d'
        self.sources.mkdir(parents=True)
        self.key = self.root / 'etc/apt/keyrings/docker.asc'
        self.key.parent.mkdir()
        self.key.write_text('public key fixture; crypto validation happens in the role')

    def inspect(self, **kwargs):
        return repository.inspect(str(self.root), kwargs.get('distribution', 'debian'),
                                  kwargs.get('suite', 'trixie'), kwargs.get('architecture', 'arm64'))

    def legacy(self, suite='trixie', architecture='arm64'):
        return f'deb [arch={architecture} signed-by={self.key}] https://download.docker.com/linux/debian {suite} stable\n'

    def test_missing_source_is_planned_without_writes(self):
        before = sorted(str(p) for p in self.root.rglob('*'))
        result = self.inspect()
        self.assertFalse(result['existing'])
        self.assertEqual(result['source_path'], str(self.sources / 'docker.sources'))
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob('*')))

    def test_matching_legacy_source_is_preserved(self):
        path = self.sources / 'docker.list'
        path.write_text(self.legacy())
        before = path.read_bytes()
        result = self.inspect()
        self.assertTrue(result['existing'])
        self.assertEqual(result['source_path'], str(path))
        self.assertEqual(path.read_bytes(), before)

    def test_matching_deb822_source_is_preserved(self):
        path = self.sources / 'docker.sources'
        path.write_text('Types: deb\nURIs: https://download.docker.com/linux/debian\n'
                        f'Suites: trixie\nComponents: stable\nArchitectures: arm64\nSigned-By: {self.key}\n')
        self.assertTrue(self.inspect()['existing'])

    def test_duplicate_wrong_suite_and_wrong_architecture_are_rejected(self):
        path = self.sources / 'docker.list'
        for text in (self.legacy() * 2, self.legacy(suite='bookworm'), self.legacy(architecture='amd64')):
            with self.subTest(text=text):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    self.inspect()

    def test_missing_or_symlinked_key_is_rejected(self):
        (self.sources / 'docker.list').write_text(self.legacy())
        self.key.unlink()
        with self.assertRaises(ValueError):
            self.inspect()
        self.key.symlink_to(self.root / 'missing')
        with self.assertRaises(ValueError):
            self.inspect()

    def test_existing_disabled_source_is_not_overwritten(self):
        (self.sources / 'docker.sources').write_text('Enabled: no\nTypes: deb\nURIs: https://download.docker.com/linux/debian\n')
        with self.assertRaises(ValueError):
            self.inspect()

    def test_signature_bypass_is_rejected_in_both_source_formats(self):
        path = self.sources / 'docker.list'
        path.write_text(self.legacy().replace('[arch=', '[trusted=yes arch='))
        with self.assertRaises(ValueError):
            self.inspect()
        path.unlink()
        (self.sources / 'docker.sources').write_text('Types: deb\nURIs: https://download.docker.com/linux/debian\n'
                         f'Suites: trixie\nComponents: stable\nArchitectures: arm64\nSigned-By: {self.key}\nTrusted: yes\n')
        with self.assertRaises(ValueError):
            self.inspect()

    def test_unsupported_os_release_and_architecture_are_rejected(self):
        for options in ({'distribution': 'raspbian'}, {'suite': 'bullseye'}, {'architecture': 'armhf'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.inspect(**options)


if __name__ == '__main__':
    unittest.main()
