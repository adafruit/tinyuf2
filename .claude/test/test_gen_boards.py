#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# tools/gen_boards.py: a board's display override, and the gen-boards pre-commit hook failing a board added without
# regenerating supported_boards.md.
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_build import ScratchRepo

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gen_boards', ROOT / 'tools' / 'gen_boards.py')
gb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gb)

BOARD_H = '''#define USB_VID 0x303A
#define USB_PID 0x811A
#define USB_MANUFACTURER "M5Stack"
#define USB_PRODUCT "Stamp S3"
#define UF2_INDEX_URL "https://docs.m5stack.com/en/core/StampS3"
'''


def write_board(root, family, board, text=BOARD_H):
  path = root / 'ports' / family / 'boards' / board / 'board.h'
  path.parent.mkdir(parents=True)
  path.write_text(text)
  return path


class Override(unittest.TestCase):
  def test_dial_overrides_name_and_url_but_not_vid_pid(self):
    with tempfile.TemporaryDirectory() as tmp:
      entry = gb._load_board(write_board(Path(tmp), 'espressif', 'm5stack_dial'), Path(tmp))
    self.assertEqual(entry['name'], 'M5Stack Dial')
    self.assertEqual(entry['url'], 'https://docs.m5stack.com/en/core/M5Dial')
    self.assertEqual(entry['vid_pid'], '0x303A:0x811A')


class Cli(unittest.TestCase):
  def test_first_time_output_exits_zero(self):
    with tempfile.TemporaryDirectory() as tmp:
      output = Path(tmp) / 'boards.md'
      result = subprocess.run([sys.executable, ROOT / 'tools' / 'gen_boards.py', '--output', output],
                              capture_output=True, text=True)
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn('# Supported Boards', output.read_text())


def gen_boards_hook():
  """The gen-boards entry of the real config, as text: PyYAML may live only in pre-commit's own environment."""
  lines = (ROOT / '.pre-commit-config.yaml').read_text().splitlines(keepends=True)
  start = lines.index('  - id: gen-boards\n')
  end = next((i for i in range(start + 1, len(lines)) if not lines[i].startswith('    ')), len(lines))
  return ''.join(lines[start:end])


@unittest.skipUnless(shutil.which('pre-commit'), 'pre-commit is not installed')
class Hook(ScratchRepo):
  def setUp(self):
    super().setUp()
    cache = tempfile.TemporaryDirectory()
    self.addCleanup(cache.cleanup)
    self.env = dict(os.environ, PRE_COMMIT_HOME=cache.name)
    (self.repo / 'tools').mkdir()
    shutil.copy(ROOT / 'tools' / 'gen_boards.py', self.repo / 'tools')
    (self.repo / '.pre-commit-config.yaml').write_text('repos:\n- repo: local\n  hooks:\n' + gen_boards_hook())
    write_board(self.repo, 'espressif', 'm5stack_stamps3')
    gb.generate(self.repo, self.repo / 'supported_boards.md')
    self.git('init', '-q')
    self.git('add', '.')

  def run_hook(self, *args):
    return subprocess.run(['pre-commit', 'run', 'gen-boards', *(args or ['--all-files'])], cwd=self.repo, env=self.env,
                          capture_output=True, text=True)

  def test_board_added_without_regenerating_fails_then_passes(self):
    self.assertEqual(self.run_hook().returncode, 0)
    write_board(self.repo, 'espressif', 'new_board', BOARD_H.replace('Stamp S3', 'New Board'))
    self.git('add', '.')
    result = self.run_hook()
    self.assertNotEqual(result.returncode, 0, result.stdout)
    self.assertIn('| new_board | M5Stack New Board |', (self.repo / 'supported_boards.md').read_text())
    self.git('add', '.')
    self.assertEqual(self.run_hook().returncode, 0)

  def test_commit_removing_only_a_board_fails(self):
    self.git('commit', '-q', '-m', 'base')
    self.git('rm', '-q', 'ports/espressif/boards/m5stack_stamps3/board.h')
    result = self.run_hook('--hook-stage', 'pre-commit')
    self.assertNotEqual(result.returncode, 0, result.stdout)
    self.assertNotIn('m5stack_stamps3', (self.repo / 'supported_boards.md').read_text())

  def test_list_deleted_fails_on_every_run(self):
    self.git('commit', '-q', '-m', 'base')
    self.git('rm', '-q', 'supported_boards.md')
    for _ in range(2):
      result = self.run_hook('--hook-stage', 'pre-commit')
      self.assertNotEqual(result.returncode, 0, result.stdout)
    self.git('add', 'supported_boards.md')
    self.assertEqual(self.run_hook('--hook-stage', 'pre-commit').returncode, 0)

  def test_untracked_board_is_left_out(self):
    self.git('commit', '-q', '-m', 'base')
    write_board(self.repo, 'espressif', 'untracked_board', BOARD_H.replace('Stamp S3', 'Untracked'))
    (self.repo / 'other.txt').write_text('x\n')
    self.git('add', 'other.txt')
    result = self.run_hook('--hook-stage', 'pre-commit')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertNotIn('untracked_board', (self.repo / 'supported_boards.md').read_text())

  def test_unstaged_board_deletion_fails_without_a_traceback(self):
    self.git('commit', '-q', '-m', 'base')
    (self.repo / 'ports/espressif/boards/m5stack_stamps3/board.h').unlink()
    result = self.run_hook()
    self.assertNotEqual(result.returncode, 0, result.stdout)
    self.assertNotIn('Traceback', result.stdout)
    self.assertNotIn('m5stack_stamps3', (self.repo / 'supported_boards.md').read_text())

  def test_sparse_excluded_board_stays_listed(self):
    write_board(self.repo, 'stm32f4', 'sparse_board', BOARD_H.replace('Stamp S3', 'Sparse'))
    gb.generate(self.repo, self.repo / 'supported_boards.md')
    self.git('add', '.')
    self.git('commit', '-q', '-m', 'base')
    self.git('sparse-checkout', 'set', '--no-cone', '/*', '!/ports/stm32f4/')
    self.assertFalse((self.repo / 'ports/stm32f4').exists())
    result = self.run_hook('--hook-stage', 'pre-commit')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('| sparse_board | M5Stack Sparse |', (self.repo / 'supported_boards.md').read_text())

  def test_literal_pathspecs_keep_every_board(self):
    # `git --literal-pathspecs commit` exports this to its hooks
    self.git('commit', '-q', '-m', 'base')
    self.env['GIT_LITERAL_PATHSPECS'] = '1'
    result = self.run_hook('--hook-stage', 'pre-commit')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('| m5stack_stamps3 |', (self.repo / 'supported_boards.md').read_text())


if __name__ == '__main__':
  unittest.main()
