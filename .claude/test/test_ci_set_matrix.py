"""build.yml's matrix: ci_set_matrix.py cuts the full matrix to a pull request's build.ci and falls back to
the full matrix whenever the selection cannot be used."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ci_set_matrix', ROOT / '.github' / 'workflows' / 'ci_set_matrix.py')
csm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(csm)
spec = importlib.util.spec_from_file_location('check_build', ROOT / '.claude' / 'skills' / 'build' / 'scripts' / 'check_build.py')
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)

FULL = csm.full_matrix()


def manifest(full=False, ports=None, ghostfat=False):
  return {'version': 1, 'build': {'ci': {'full': full, 'ports': ports or {}, 'ghostfat': ghostfat}}}


def run(select):
  """(matrix, stderr) of the script given `select` as its selection file's text, or no file for None."""
  out, err = io.StringIO(), io.StringIO()
  with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    path = None
    if select is not None:
      path = Path(d) / 'selection.json'
      path.write_text(select)
    csm.set_matrix_json(path)
  return json.loads(out.getvalue()), err.getvalue()


class Matrix(unittest.TestCase):
  def test_no_selection_is_every_board_of_every_port(self):
    matrix, err = run(None)
    self.assertEqual((matrix, err), (FULL, ''))
    self.assertIn('lpcxpresso55s28', matrix['lpc55']['board'])
    self.assertNotIn('template_port', matrix)

  def test_full_selection_is_the_full_matrix(self):
    self.assertEqual(run(json.dumps(manifest(full=True, ghostfat=True))), (FULL, ''))

  def test_selection_keeps_every_port_key_and_only_the_selected_boards(self):
    matrix, err = run(json.dumps(manifest(ports={'lpc55': ['lpcxpresso55s28']})))
    self.assertEqual(err, '')
    self.assertEqual(matrix.keys(), FULL.keys())
    self.assertEqual(matrix['lpc55'], {'board': ['lpcxpresso55s28']})
    self.assertEqual({p: v for p, v in matrix.items() if p != 'lpc55'},
                     {p: {'board': []} for p, v in FULL.items() if p != 'lpc55'})

  def test_ghostfat_selection_adds_every_ghostfat_config(self):
    matrix, _ = run(json.dumps(manifest(ghostfat=True)))
    self.assertEqual(matrix['test_ghostfat'], FULL['test_ghostfat'])
    self.assertEqual(matrix['espressif'], {'board': []})

  def test_check_build_manifest_is_accepted(self):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
      cb.main(['--select-only', '--scope', 'ports/stm32h5/boards/stm32h503_nucleo/board.h'])
    matrix, err = run(out.getvalue())
    self.assertEqual(err, '')
    self.assertEqual(matrix['stm32h5'], {'board': ['stm32h503_nucleo']})

  def test_unusable_selection_falls_back_to_the_full_matrix_with_a_warning(self):
    legacy = manifest()
    del legacy['build']['ci']
    for text in ('', 'not json', '[]', json.dumps({'version': 2, 'build': {}}), json.dumps(legacy),
                 json.dumps({'version': 1, 'build': []}),
                 json.dumps(manifest(ports={'lpc55': ['no_such_board']})),
                 json.dumps(manifest(ports={'no_such_port': []})),
                 json.dumps(manifest(ports={'test_ghostfat': ['huge']})),
                 json.dumps(manifest(ports={'lpc55': 'lpcxpresso55s28'})),
                 json.dumps(manifest(full='yes')), json.dumps({**manifest(), 'version': True}),
                 '[' * 10000 + ']' * 10000):
      matrix, err = run(text)
      self.assertEqual(matrix, FULL, text)
      self.assertTrue(err.startswith('::warning::'), text)

  def test_missing_selection_file_falls_back(self):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
      csm.set_matrix_json('/no/such/selection.json')
    self.assertEqual(json.loads(out.getvalue()), FULL)
    self.assertIn('::warning::', err.getvalue())


if __name__ == '__main__':
  unittest.main()
