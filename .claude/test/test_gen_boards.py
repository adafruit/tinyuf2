#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# tools/gen_boards.py: a board's display override, and the gen-boards pre-commit hook failing a board added without
# regenerating supported_boards.md.
import importlib.util
import os
import shutil
import subprocess
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


@unittest.skipUnless(shutil.which('pre-commit'), 'pre-commit is not installed')
class Hook(ScratchRepo):
  def setUp(self):
    super().setUp()
    import yaml
    cache = tempfile.TemporaryDirectory()
    self.addCleanup(cache.cleanup)
    self.env = dict(os.environ, PRE_COMMIT_HOME=cache.name)
    (self.repo / 'tools').mkdir()
    shutil.copy(ROOT / 'tools' / 'gen_boards.py', self.repo / 'tools')
    config = yaml.safe_load((ROOT / '.pre-commit-config.yaml').read_text())
    hook = next(h for r in config['repos'] if r['repo'] == 'local' for h in r['hooks'] if h['id'] == 'gen-boards')
    (self.repo / '.pre-commit-config.yaml').write_text(yaml.safe_dump({'repos': [{'repo': 'local', 'hooks': [hook]}]}))
    write_board(self.repo, 'espressif', 'm5stack_stamps3')
    gb.generate(self.repo, self.repo / 'supported_boards.md')
    self.git('init', '-q')
    self.git('add', '.')

  def run_hook(self):
    return subprocess.run(['pre-commit', 'run', 'gen-boards', '--all-files'], cwd=self.repo, env=self.env,
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


if __name__ == '__main__':
  unittest.main()
