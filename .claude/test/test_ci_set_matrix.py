"""build.yml's matrix: ci_set_matrix.py cuts the full matrix to a pull request's build.ci, builds every board or
none for a push, and falls back to the full matrix whenever the selection cannot be made or used."""
import contextlib
import importlib.util
import io
import json
import unittest
from unittest import mock

from test_build import ROOT, ScratchRepo, cb, run_main

spec = importlib.util.spec_from_file_location('ci_set_matrix', ROOT / '.github' / 'workflows' / 'ci_set_matrix.py')
csm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(csm)

FULL = csm.full_matrix()


def manifest(full=False, ports=None, ghostfat=False):
  return {'version': 1, 'build': {'ci': {'full': full, 'ports': ports or {}, 'ghostfat': ghostfat}}}


def run(base, selection=None, before=None):
  """(matrix, stderr) of the script for `base` or a push from `before`; `selection` stands in for check_build.py's
  output text."""
  out, err = io.StringIO(), io.StringIO()
  with contextlib.ExitStack() as stack:
    stack.enter_context(contextlib.redirect_stdout(out))
    stack.enter_context(contextlib.redirect_stderr(err))
    if selection is not None:
      stack.enter_context(mock.patch.object(csm, 'selection', lambda base: json.loads(selection)))
    csm.set_matrix_json(base, before)
  return json.loads(out.getvalue()), err.getvalue()


class Matrix(unittest.TestCase):
  def test_no_base_is_every_board_of_every_port(self):
    matrix, err = run(None)
    self.assertEqual((matrix, err), (FULL, ''))
    self.assertIn('lpcxpresso55s28', matrix['lpc55']['board'])
    self.assertNotIn('template_port', matrix)

  def test_full_selection_is_the_full_matrix(self):
    self.assertEqual(run('b', json.dumps(manifest(full=True, ghostfat=True))), (FULL, ''))

  def test_selection_keeps_every_port_key_and_only_the_selected_boards(self):
    matrix, err = run('b', json.dumps(manifest(ports={'lpc55': ['lpcxpresso55s28']})))
    self.assertEqual(err, '')
    self.assertEqual(matrix.keys(), FULL.keys())
    self.assertEqual(matrix['lpc55'], {'board': ['lpcxpresso55s28']})
    self.assertEqual({p: v for p, v in matrix.items() if p != 'lpc55'},
                     {p: {'board': []} for p, v in FULL.items() if p != 'lpc55'})

  def test_ghostfat_selection_adds_every_ghostfat_config(self):
    matrix, _ = run('b', json.dumps(manifest(ghostfat=True)))
    self.assertEqual(matrix['test_ghostfat'], FULL['test_ghostfat'])
    self.assertEqual(matrix['espressif'], {'board': []})

  def test_check_build_manifest_is_accepted(self):
    _, sel = run_main(['--select-only', '--scope', 'ports/stm32h5/boards/stm32h503_nucleo/board.h'])
    matrix, err = run('b', json.dumps(sel))
    self.assertEqual(err, '')
    self.assertEqual(matrix['stm32h5'], {'board': ['stm32h503_nucleo']})

  def test_the_selector_runs_against_the_base(self):
    matrix, err = run('HEAD')   # no change since HEAD: nothing to build
    self.assertEqual(err, '')
    self.assertEqual(matrix, {p: ({'board': []} if 'board' in v else {}) for p, v in FULL.items()})

  def test_a_failed_selector_falls_back_to_the_full_matrix_with_a_warning(self):
    matrix, err = run('no-such-ref')
    self.assertEqual(matrix, FULL)
    self.assertTrue(err.startswith('::warning::'))
    self.assertIn('check_build.py exited 2', err)

  def test_unusable_selection_falls_back_to_the_full_matrix_with_a_warning(self):
    legacy = manifest()
    del legacy['build']['ci']
    for text in ('', 'not json', '[]', json.dumps({'version': 2, 'build': {}}), json.dumps(legacy),
                 json.dumps({'version': 1, 'build': []}),
                 json.dumps(manifest(ports={'lpc55': ['no_such_board']})),
                 json.dumps(manifest(ports={'no_such_port': []})),
                 json.dumps(manifest(ports={'test_ghostfat': ['huge']})),
                 json.dumps(manifest(ports={'lpc55': 'lpcxpresso55s28'})),
                 json.dumps(manifest(full='yes')), json.dumps(manifest(full=None)),
                 json.dumps(manifest(ghostfat=None)), json.dumps({**manifest(), 'version': True}),
                 '[' * 10000 + ']' * 10000):
      matrix, err = run('b', text)
      self.assertEqual(matrix, FULL, text)
      self.assertTrue(err.startswith('::warning::'), text)


class Push(unittest.TestCase):
  def test_docs_and_hook_inputs_build_nothing(self):
    for path in ('README.md', 'ports/stm32f4/README.md', '.codespellrc', 'tools/codespell/exclude-file.txt',
                 '.github/ISSUE_TEMPLATE/bug_report.yml', '.github/workflows/codeql.yml', '.claude/test/test_build.py',
                 'test/hil/local.json'):
      self.assertFalse(csm.builds_on_push(path), path)

  def test_build_inputs_build_everything(self):
    for path in ('lib/tinyusb', 'ports/stm32f4/boards/feather_stm32f405_express/board.h', 'apps/blinky/blinky.c'):
      self.assertTrue(csm.builds_on_push(path), path)

  def test_every_full_build_input_of_the_selector_builds_on_push(self):
    for path in cb.CORE + cb.BUILD_CONTROL + cb.GHOSTFAT_INPUTS + cb.MAKE_SHARED:
      self.assertTrue(csm.builds_on_push(path + 'x.c' if path.endswith('/') else path), path)

  def test_push_compares_the_tips_and_never_runs_the_selector(self):
    def no_selector(base):
      raise AssertionError('push mode ran the selector')
    with mock.patch.object(csm, 'selection', no_selector):
      self.assertEqual(run(None, before='HEAD'), (csm.empty_matrix(FULL), ''))
      with mock.patch.object(csm, 'push_paths', lambda before: ['README.md', 'src/main.c']):
        self.assertEqual(run(None, before='b'), (FULL, ''))

  def test_a_new_branch_builds_everything_with_a_warning(self):
    matrix, err = run(None, before='0' * 40)
    self.assertEqual(matrix, FULL)
    self.assertTrue(err.startswith('::warning::'))


class PushPaths(ScratchRepo):
  def commit(self, path):
    (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
    (self.repo / path).write_text(path)
    self.git('add', path)
    self.git('commit', '-qm', path)
    return self.git('rev-parse', 'HEAD')

  def test_every_commit_of_a_push_and_what_a_force_push_undid(self):
    self.git('init', '-q')
    a = self.commit('README.md')
    self.commit('src/main.c')
    b = self.commit('docs.md')
    self.assertEqual(sorted(csm.push_paths(a, self.repo)), ['docs.md', 'src/main.c'])   # a two-commit push
    self.git('reset', '-q', '--hard', a)
    self.commit('changelog.md')
    self.assertIn('src/main.c', csm.push_paths(b, self.repo))   # a force push over B undoes its src/main.c

if __name__ == '__main__':
  unittest.main()
