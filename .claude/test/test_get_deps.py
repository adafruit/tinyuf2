"""tools/get_deps.py refuses to reset a dependency through a symlink."""
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('get_deps', ROOT / 'tools' / 'get_deps.py')
gd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gd)


class SymlinkGuard(unittest.TestCase):
  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.tmp = Path(tmp.name)
    self.root = self.tmp / 'checkout'
    self.root.mkdir()
    self.dep = 'lib/mcu/vendor/sdk'
    self.pin = '0123456789abcdef'
    mock.patch.object(gd, 'TOP', self.root).start()
    mock.patch.object(gd, 'deps_all', {self.dep: ['https://example.invalid/sdk.git', self.pin, 'port']}).start()
    self.run_cmd = mock.patch.object(gd, 'run_cmd').start()
    self.addCleanup(mock.patch.stopall)

  def run_dep(self):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
      status = gd.get_a_dep(self.dep)
    return status, output.getvalue()

  def assert_refused(self, component):
    status, output = self.run_dep()
    self.assertEqual(status, 1)
    self.assertIn(f'{component} is a symlink', output)
    self.assertIn(self.pin, output)
    self.assertIn('checkout that owns the dependency', output)
    self.run_cmd.assert_not_called()

  def test_dependency_symlink_is_refused_before_git_runs(self):
    target = self.tmp / 'primary-sdk'
    path = self.root / self.dep
    path.parent.mkdir(parents=True)
    path.symlink_to(target, target_is_directory=True)

    self.assert_refused(self.dep)

  def test_symlinked_ancestor_is_refused_before_git_runs(self):
    target = self.tmp / 'primary-mcu'
    target.mkdir()
    path = self.root / 'lib' / 'mcu'
    path.parent.mkdir(parents=True)
    path.symlink_to(target, target_is_directory=True)

    self.assert_refused('lib/mcu')

  def test_regular_dependency_path_continues_to_git(self):
    status, output = self.run_dep()
    self.assertEqual(status, 0)
    self.assertIn(f'cloning {self.dep}', output)
    self.assertEqual(self.run_cmd.call_count, 4)
    self.assertTrue((self.root / self.dep).is_dir())


if __name__ == '__main__':
  unittest.main()
