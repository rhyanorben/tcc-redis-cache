import importlib.util
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('empacotar_paginacao', PROJECT / 'scripts/empacotar_paginacao.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PaginationPackageTests(unittest.TestCase):
    def fixture(self, directory):
        project = directory / 'project'
        project.mkdir()
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        (project / 'load').mkdir()
        for name in ('experiment.js', 'navigation.js', 'navigation.json', 'campanha.json'):
            (project / 'load' / name).write_text('{}')
        (project / '.gitignore').write_text('secrets/\n.env\nresults/\n')
        (project / 'load/secrets').mkdir()
        (project / 'load/secrets/password.json').write_text('private')
        (project / 'load/.env').write_text('private')
        return project

    def test_package_includes_new_navigation_but_excludes_ignored_files_and_old_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = self.fixture(directory)
            destination = directory / 'code.tar.gz'
            self.assertEqual(4, package.build_package(project, destination))
            with tarfile.open(destination) as archive:
                self.assertEqual({'load/experiment.js', 'load/navigation.js', 'load/navigation.json', 'load/campanha.json'},
                                 set(archive.getnames()))

    def test_existing_package_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = self.fixture(directory)
            destination = directory / 'code.tar.gz'
            destination.write_bytes(b'previous')
            with self.assertRaises(FileExistsError):
                package.build_package(project, destination)
            self.assertEqual(b'previous', destination.read_bytes())

    def test_missing_navigation_is_rejected_before_creating_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            project = self.fixture(directory)
            (project / 'load/navigation.json').unlink()
            destination = directory / 'code.tar.gz'
            with self.assertRaisesRegex(ValueError, 'incompleto'):
                package.build_package(project, destination)
            self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
