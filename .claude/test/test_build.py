"""The build contract: check_build.py's tables agree with CI, each selection rule picks the boards
that compile a change, and the JSON and exit code follow SKILL.md. Builds are stubbed here; a real
build is evidence only from a run of the script itself."""
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '.claude' / 'skills' / 'build' / 'scripts' / 'check_build.py'
LPC55_ARTIFACTS = ['_bin/tinyuf2-lpcxpresso55s69.bin', '_bin/tinyuf2-lpcxpresso55s69.hex',
                   '_bin/apps/update-tinyuf2-lpcxpresso55s69.uf2']


def build_tmpdir():
  """A scratch build root inside the checkout's ignored cmake-build/, where the script reports from."""
  (ROOT / 'cmake-build').mkdir(exist_ok=True)
  return tempfile.TemporaryDirectory(dir=ROOT / 'cmake-build', prefix='test-')


spec = importlib.util.spec_from_file_location('check_build', SCRIPT)
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)


def ci_jobs():
  """{port: backend} of build.yml's enabled jobs, and the ports of its disabled ones."""
  text = (ROOT / '.github' / 'workflows' / 'build.yml').read_text()
  jobs = re.split(r'^  (?=[\w-]+:\s*$)', text.split('\njobs:\n', 1)[1], flags=re.M)
  enabled, disabled = {}, set()
  for job in jobs:
    code = '\n'.join(l for l in job.splitlines() if not l.lstrip().startswith('#'))
    toolchain = re.search(r"toolchain:\s*'([^']+)'", code)
    if not toolchain or 'build_util.yml' not in code:
      continue
    ports = re.findall(r"^\s*-\s*'(\w+)'", code, re.M) or re.findall(r"^\s*port:\s*'(\w+)'", code, re.M)
    backend = 'idf' if toolchain.group(1) == 'esp-idf' else re.search(r"build-system:\s*'(\w+)'", code).group(1)
    for port in ports:
      if re.search(r'^\s*if:\s*false', code, re.M):
        disabled.add(port)
      else:
        enabled[port] = backend
  return enabled, disabled


def classify(path):
  r = cb.classify(path)
  return r['rule'], r['effect'], sorted(r['boards']), r['ghostfat'], r['tests']


class TablesMatchTheTree(unittest.TestCase):
  def test_backends_are_build_yml_jobs(self):
    enabled, disabled = ci_jobs()
    self.assertEqual(cb.BACKENDS, enabled)
    self.assertLessEqual(disabled, set(cb.UNBUILT))

  def test_every_port_dir_has_a_backend_or_a_reason(self):
    ports = {p.name for p in (ROOT / 'ports').iterdir() if p.is_dir()} - {cb.GHOSTFAT}
    self.assertEqual(ports, set(cb.BACKENDS) | set(cb.UNBUILT))

  def test_representatives_exist(self):
    self.assertEqual(set(cb.REPRESENTATIVES), set(cb.BACKENDS))
    for port, boards in cb.REPRESENTATIVES.items():
      for b in boards:
        self.assertTrue((ROOT / 'ports' / port / 'boards' / b).is_dir(), f'{port}/{b}')
    for backend, board in cb.SMOKE.items():
      self.assertEqual(cb.BACKENDS[cb.port_of(board)], backend)

  def test_espressif_representatives_cover_both_idf_targets(self):
    targets = {re.search(r'esp32s[23]', (ROOT / 'ports/espressif/boards' / b / 'board.cmake').read_text()).group(0)
               for b in cb.REPRESENTATIVES['espressif']}
    self.assertEqual(targets, {'esp32s2', 'esp32s3'})

  def test_no_self_update_ports_echo_a_stub(self):
    for port in cb.NO_SELF_UPDATE:
      mk = (ROOT / 'ports' / port / 'Makefile').read_text()
      recipe = re.search(r'^self-update:.*\n((?:\t.*\n?)*)', mk.replace('\r', ''), re.M)
      self.assertIn('not implemented', recipe.group(1), port)

  def test_ci_idf_version_is_read_from_build_yml(self):
    self.assertRegex(cb.ci_idf_version(), r'^v\d+\.\d+')


class Selection(unittest.TestCase):
  def test_board_file_selects_that_board(self):
    self.assertEqual(classify('ports/stm32f4/boards/stm32f411ce_blackpill/board.h'),
                     ('board', 'select', [('stm32f411ce_blackpill', 'cmake')], False, False))

  def test_build_file_the_backend_never_reads_is_uncovered(self):
    for path in ('ports/stm32f4/boards/stm32f411ce_blackpill/board.mk', 'ports/stm32f4/apps/self_update/Makefile',
                 'ports/mimxrt10xx/CMakeLists.txt'):
      self.assertEqual(classify(path)[:2], ('other-backend', 'gap'), path)

  def test_make_files_codeql_builds_select_its_make_build(self):
    for path in ('ports/stm32f4/Makefile', 'ports/stm32f4/port.mk',
                 'ports/stm32f4/boards/feather_stm32f405_express/board.mk', '.github/workflows/codeql-buildscript.sh'):
      self.assertEqual(classify(path)[2], [('feather_stm32f405_express', 'make')], path)

  def test_port_file_selects_its_representatives(self):
    rule, effect, boards, _, _ = classify('ports/mimxrt10xx/board_flash.c')
    self.assertEqual((rule, effect), ('port', 'select'))
    self.assertEqual(boards, [('imxrt1064_evk', 'make'), ('imxrt1170_evk', 'make')])

  def test_app_selects_the_boards_that_build_it(self):
    self.assertEqual(classify('ports/mimxrt10xx/apps/factory_test/main.c')[2], [('metro_m7_1011', 'make')])
    self.assertEqual(classify('ports/mimxrt10xx/apps/app.mk')[2],
                     [('metro_m7_1011', 'make'), ('metro_m7_1011_sd', 'make')])

  def test_app_nothing_builds_is_uncovered(self):
    self.assertEqual(classify('ports/lpc55/apps/erase_firmware/Makefile')[:2], ('port-app', 'gap'))
    self.assertEqual(classify('ports/espressif/apps/erase_firmware/main/CMakeLists.txt')[:2], ('port-app', 'gap'))
    self.assertEqual(classify('ports/espressif/apps/blinky/main/CMakeLists.txt')[:2], ('port-app', 'select'))

  def test_top_level_app_selects_ports_whose_backend_compiles_it(self):
    ports = {cb.port_of(b) for b, _ in classify('apps/blinky/src/blinky.c')[2]}
    self.assertEqual(ports, {'espressif', 'maxim', 'stm32f4', 'stm32h5'})

  def test_dependency_selects_the_ports_get_deps_names(self):
    self.assertEqual(classify('lib/mcu/st/cmsis_device_f4/x.h')[2], [('feather_stm32f405_express', 'cmake')])
    self.assertEqual(classify('lib/sct_neopixel/x.c')[2], [('lpcxpresso55s69', 'make')])

  def test_unbuilt_ports_are_uncovered(self):
    for path in ('ports/template_port/boards.c', 'ports/ch32v20x/boards.c'):
      self.assertEqual(classify(path)[:2], ('unbuilt-port', 'gap'), path)

  def test_ghostfat_inputs(self):
    self.assertEqual(classify('ports/test_ghostfat/main.c'), ('ghostfat', 'select', [], True, False))
    self.assertEqual(classify('src/ghostfat.c')[:2] + classify('src/ghostfat.c')[3:4], ('core', 'core', True))
    self.assertFalse(classify('src/main.c')[3])

  def test_build_control_runs_tests_and_one_smoke_build_per_backend(self):
    rule, effect, boards, _, tests = classify('.claude/skills/build/scripts/check_build.py')
    self.assertEqual((rule, effect, tests), ('build-control', 'select', True))
    self.assertEqual(sorted(b for _, b in boards), ['cmake', 'idf', 'make'])
    self.assertTrue(cb.classify('.claude/skills/build/scripts/check_build.py')['hil'])   # hil_test.py imports it
    self.assertFalse(cb.classify('.github/workflows/build.yml')['hil'])

  def test_unknown_port_fails_explicitly(self):
    with self.assertRaises(cb.Fail):
      cb.backend_of('no_such_port')

  def test_contract_test_edit_runs_the_tests_only(self):
    self.assertEqual(classify('.claude/test/test_build.py'), ('contract-tests', 'select', [], False, True))

  def test_unreadable_codeql_script_fails_explicitly(self):
    cb.codeql_build.cache_clear()
    self.addCleanup(cb.codeql_build.cache_clear)
    with mock.patch.object(Path, 'read_text', lambda self, *a, **k: 'cmake -B build\n'):
      with self.assertRaises(cb.Fail):
        cb.codeql_build()

  def test_nothing_to_build(self):
    for path in ('README.md', '.claude/skills/build/SKILL.md', 'tools/gen_boards.py', '.github/workflows/codeql.yml'):
      self.assertEqual(classify(path)[1], 'none', path)

  def test_hil_runner_and_roster_select_tests_and_every_roster_board(self):
    for path in ('.claude/skills/hil/scripts/hil_test.py', 'test/hil/local.json'):
      r = cb.classify(path)
      self.assertEqual((r['rule'], r['tests'], r['hil'], r['boards']), ('hil-control', True, True, {}), path)
    self.assertEqual(cb.classify('.claude/skills/hil/SKILL.md')['effect'], 'none')   # wording costs no hardware
    self.assertEqual(classify('.claude/test/test_hil.py'), ('contract-tests', 'select', [], False, True))

  def test_core_and_unclassified_select_every_representative(self):
    for path in ('src/main.c', 'lib/tinyusb', 'ports/family_support.cmake', 'some/new/file.c'):
      self.assertEqual(classify(path)[1], 'core', path)
    sel = cb.select(['src/main.c', 'README.md'])
    self.assertTrue(sel['full'])
    self.assertEqual({b for b, _ in sel['boards']}, {b for v in cb.REPRESENTATIVES.values() for b in v})

  def test_paths_are_normalised(self):
    self.assertEqual(cb.repo_path('./ports/test_ghostfat/main.c'), 'ports/test_ghostfat/main.c')
    self.assertEqual(cb.repo_path(str(ROOT / 'src' / 'main.c')), 'src/main.c')
    with self.assertRaises(cb.Fail):
      cb.repo_path('/')

  def test_scope_refuses_a_path_neither_present_nor_tracked(self):
    with self.assertRaises(cb.Fail):
      cb.changed_paths(scope=['no/such/file.c'])


class ChangedPaths(unittest.TestCase):
  """--base and --worktree in a scratch repository. Every GIT_* variable is dropped first:
  under pre-commit they point at the real checkout, and git would act on it."""

  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.repo = Path(tmp.name)
    env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, clear=True)
    env.start()
    self.addCleanup(env.stop)
    root = mock.patch.object(cb, 'ROOT', self.repo)
    root.start()
    self.addCleanup(root.stop)
    self.git('init', '-q', '-b', 'master')
    for name in ('a.c', 'b.c', 'c.c', 'e.c'):
      (self.repo / name).write_text(name * 20)
    self.git('add', '.')
    self.git('commit', '-q', '-m', 'base')
    self.git('checkout', '-q', '-b', 'topic')
    (self.repo / 'a.c').write_text('changed')
    self.git('rm', '-q', 'b.c')
    self.git('mv', 'c.c', 'd.c')
    self.git('commit', '-q', '-am', 'topic')
    (self.repo / 'e.c').write_text('unstaged')
    (self.repo / 'g.c').write_text('staged')
    self.git('add', 'g.c')
    (self.repo / 'f.c').write_text('untracked')

  def git(self, *args):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', *args],
                   cwd=self.repo, check=True, capture_output=True)

  def test_base_reports_committed_changes_deletions_and_both_sides_of_a_rename(self):
    paths, info = cb.changed_paths(base='master')
    self.assertEqual(paths, ['a.c', 'b.c', 'c.c', 'd.c'])
    self.assertEqual(info['mode'], 'base')
    # --select-only returns before identity(), so its input names the commit it selected from
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.repo, capture_output=True, text=True).stdout.strip()
    self.assertEqual(info['head'], head)

  def test_worktree_adds_staged_unstaged_and_untracked(self):
    paths, info = cb.changed_paths(base='master', worktree=True)
    self.assertEqual(paths, ['a.c', 'b.c', 'c.c', 'd.c', 'e.c', 'f.c', 'g.c'])
    self.assertEqual(info['mode'], 'worktree')

  def test_scope_accepts_a_tracked_path_deleted_from_the_tree(self):
    (self.repo / 'a.c').unlink()
    self.assertEqual(cb.changed_paths(scope=['a.c'])[0], ['a.c'])
    with self.assertRaises(cb.Fail):   # deleted by a commit: --base reports it, --scope cannot see it
      cb.changed_paths(scope=['b.c'])


CLEAN = {'head': 'h', 'dirty': False, 'submodules': {}, 'deps': {}, 'dirtyInputs': [], 'missingInputs': [], 'depsOffPin': []}


def run_main(argv, boards=None, ghostfat=None, tests=None, identities=None):
  """main() with builds stubbed: `boards` maps board -> status; `identities`, the successive identity() results."""
  boards = boards or {}
  identities = iter(identities or [])

  def build_board(board, backend, args, idf, flasher=None):
    status = boards.get(board, 'ok')
    return {'board': board, 'port': cb.port_of(board), 'backend': backend, 'buildDir': f'cmake-build/x-{board}',
            'status': status, 'firstError': '' if status == 'ok' else f'{board} {status}', 'artifacts': ['a.bin']}

  out = io.StringIO()
  with mock.patch.object(cb, 'build_board', build_board), \
       mock.patch.object(cb, 'run_ghostfat', lambda v: ghostfat or []), \
       mock.patch.object(cb, 'run_tests', lambda: tests or {'status': 'ok', 'summary': 'OK', 'firstError': ''}), \
       mock.patch.object(cb, 'identity', lambda ports=(): dict(next(identities, CLEAN))), \
       contextlib.redirect_stdout(out):
    code = cb.main(argv)
  return code, json.loads(out.getvalue().splitlines()[-1])


class HilSelection(unittest.TestCase):
  def setUp(self):
    tmp = build_tmpdir()
    self.addCleanup(tmp.cleanup)
    self.roster = Path(tmp.name) / 'local.json'
    self.roster.write_text(json.dumps({'boards': [{'name': 'lpcxpresso55s69'}]}))
    self.config = str(self.roster.relative_to(ROOT))

  def hil(self, *paths):
    return cb.hil_selection(cb.select(list(paths)), self.config)

  def test_a_port_change_selects_its_roster_board(self):
    self.assertEqual(self.hil('ports/lpc55/boards.c')['boards'], ['lpcxpresso55s69'])

  def test_docs_select_no_board(self):
    h = self.hil('README.md')
    self.assertEqual((h['boards'], h['uncovered']), ([], []))

  def test_a_runner_change_selects_every_roster_board(self):
    h = self.hil('.claude/skills/hil/scripts/hil_test.py')
    self.assertEqual((h['full'], h['boards'], h['uncovered']), (True, ['lpcxpresso55s69'], []))

  def test_a_change_to_the_build_script_the_runner_imports_selects_every_roster_board(self):
    h = self.hil('.claude/skills/build/scripts/check_build.py')
    self.assertEqual((h['full'], h['boards'], h['uncovered']), (True, ['lpcxpresso55s69'], []))

  def test_a_core_change_selects_every_roster_board_and_names_ports_without_one(self):
    h = self.hil('src/main.c')
    self.assertEqual((h['full'], h['boards']), (True, ['lpcxpresso55s69']))
    self.assertIn('stm32f4', [u['target'] for u in h['uncovered']])
    self.assertNotIn('lpc55', [u['target'] for u in h['uncovered']])

  def test_a_port_without_a_roster_board_is_uncovered_even_beside_a_runner_change(self):
    h = self.hil('ports/stm32f4/board_flash.c', 'ports/lpc55/boards.c', '.claude/skills/hil/scripts/hil_test.py')
    self.assertEqual(h['boards'], ['lpcxpresso55s69'])
    self.assertEqual([u['target'] for u in h['uncovered']], ['stm32f4'])

  def test_a_build_gap_stays_uncovered_beside_a_runner_change(self):
    h = self.hil('ports/ch32v20x/board_flash.c', '.claude/skills/hil/scripts/hil_test.py')
    self.assertEqual(h['boards'], ['lpcxpresso55s69'])
    self.assertEqual([u['target'] for u in h['uncovered']], ['ports/ch32v20x/board_flash.c'])

  def test_a_port_change_reaches_roster_boards_that_are_not_its_representative(self):
    self.roster.write_text(json.dumps({'boards': [{'name': 'stm32f401_blackpill'}]}))
    self.assertEqual(self.hil('ports/stm32f4/board_flash.c')['boards'], ['stm32f401_blackpill'])

  def test_another_boards_own_change_is_uncovered(self):
    self.roster.write_text(json.dumps({'boards': [{'name': 'feather_stm32f405_express'}]}))
    h = self.hil('ports/stm32f4/boards/stm32f401_blackpill/board.h')
    self.assertEqual((h['boards'], [u['target'] for u in h['uncovered']]), ([], ['stm32f401_blackpill']))

  def test_a_roster_entry_is_named_by_its_tinyuf2_board(self):
    self.roster.write_text(json.dumps({'boards': [{'name': 'imxrt1060_evk', 'tinyuf2': {'lock': 'mimxrt1060_evk'}}]}))
    self.assertEqual(self.hil('ports/mimxrt10xx/boards/imxrt1060_evk/board.h')['boards'], ['imxrt1060_evk'])
    self.assertEqual(self.hil('ports/mimxrt10xx/board_flash.c')['boards'], ['imxrt1060_evk'])
    self.assertNotIn('mimxrt10xx', [u['target'] for u in self.hil('src/main.c')['uncovered']])

  def test_the_battery_app_selects_the_esptool_roster_boards_and_other_apps_none(self):
    self.roster.write_text(json.dumps({'boards': [{'name': 'imxrt1060_evk', 'flasher': {'name': 'jlink'}},
                                                  {'name': 'espressif_esp32s3_devkitc_1', 'flasher': {'name': 'esptool'}}]}))
    for path in ('apps/dfu_runtime/src/nonce.c', 'ports/espressif/apps/dfu_runtime/main/board_dfu_runtime.c'):
      with self.subTest(path):
        h = self.hil(path)
        self.assertEqual((h['boards'], h['uncovered']), (['espressif_esp32s3_devkitc_1'], []))
    h = self.hil('apps/blinky/src/blinky.c', 'ports/espressif/apps/blinky/main/CMakeLists.txt')
    self.assertEqual((h['boards'], len(h['uncovered'])), ([], 2))
    self.roster.write_text(json.dumps({'boards': [{'name': 'imxrt1060_evk', 'flasher': {'name': 'jlink'}}]}))
    h = self.hil('apps/dfu_runtime/src/nonce.c')
    self.assertEqual((h['boards'], [u['reason'] for u in h['uncovered']]), ([], [f'no {self.config} esptool board runs dfu_runtime']))

  def test_the_hil_follows_its_cmake_build_not_cis_make(self):
    self.roster.write_text(json.dumps({'boards': [{'name': 'imxrt1060_evk'}]}))
    h = self.hil('ports/mimxrt10xx/family.cmake', 'ports/mimxrt10xx/boards/imxrt1060_evk/board.cmake')
    self.assertEqual((h['boards'], h['uncovered']), (['imxrt1060_evk'], []))
    h = self.hil('ports/mimxrt10xx/port.mk', 'ports/mimxrt10xx/boards/imxrt1064_evk/board.cmake')
    self.assertEqual(h['boards'], [])
    self.assertEqual({u['target']: u['reason'] for u in h['uncovered']},
                     {'ports/mimxrt10xx/port.mk': 'the HIL builds with cmake, which never reads ports/mimxrt10xx/port.mk',
                      'ports/mimxrt10xx/boards/imxrt1064_evk/board.cmake':
                        f'no {self.config} board builds ports/mimxrt10xx/boards/imxrt1064_evk/board.cmake'})

  def test_shared_make_files_and_port_apps_are_outside_the_hil_build(self):
    self.roster.write_text(json.dumps({'boards': [{'name': 'imxrt1060_evk'}]}))
    h = self.hil('ports/make.mk', 'ports/mimxrt10xx/apps/factory_test/CMakeLists.txt')
    self.assertEqual((h['full'], h['boards']), (False, []))
    self.assertEqual([u['target'] for u in h['uncovered']],
                     ['ports/make.mk', 'ports/mimxrt10xx/apps/factory_test/CMakeLists.txt'])
    self.assertEqual(self.hil('ports/family_support.cmake')['boards'], ['imxrt1060_evk'])

  def test_an_app_source_is_uncovered_since_the_battery_runs_no_app(self):
    self.roster.write_text(json.dumps({'boards': [{'name': 'imxrt1060_evk'}]}))
    app, shared = 'ports/mimxrt10xx/apps/factory_test/main.c', 'apps/blinky/src/blinky.c'
    self.assertEqual(sorted(cb.select([app])['boards']), [('metro_m7_1011', 'make')])   # its build is unchanged
    h = self.hil(app, shared)
    self.assertEqual((h['full'], h['boards']), (False, []))
    self.assertEqual([u['target'] for u in h['uncovered']], [shared, app])
    h = self.hil(app, 'ports/mimxrt10xx/board_flash.c')   # a bootloader change beside it still runs the battery
    self.assertEqual((h['boards'], [u['target'] for u in h['uncovered']]), (['imxrt1060_evk'], [app]))

  def test_unreadable_roster_fails(self):
    self.roster.write_text('{}')
    with self.assertRaises(cb.Fail):
      self.hil('ports/lpc55/boards.c')

  def test_select_only_adds_hil_only_when_asked(self):
    for argv, has in ((['--select-only', '--scope', 'README.md'], False),
                      (['--select-only', '--scope', 'README.md', '--hil-config', self.config], True)):
      with contextlib.redirect_stdout(io.StringIO()) as out:
        self.assertEqual(cb.main(argv), 0)
      self.assertEqual('hil' in json.loads(out.getvalue()), has)


class Identity(unittest.TestCase):
  """A build record names each input it used and whether it has local changes; a dependency is a
  separate git checkout (a symlink in a worktree), so the parent's status cannot see its changes."""

  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.repo = Path(tmp.name)
    env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, clear=True)
    env.start()
    self.addCleanup(env.stop)
    self.pin = None
    for patch in (mock.patch.object(cb, 'ROOT', self.repo),
                  mock.patch.object(cb, 'get_deps_table', lambda: {'lib/mcu/dep': (self.pin, ['lpc55']),
                                                                   'lib/mcu/other': ('x', ['maxim'])})):
      patch.start()
      self.addCleanup(patch.stop)
    self.dep = self.repo / 'lib' / 'mcu' / 'dep'
    for repo in (self.repo, self.dep):
      repo.mkdir(parents=True, exist_ok=True)
      self.git(repo, 'init', '-q', '-b', 'master')
      (repo / 'x.c').write_text('x')
      self.git(repo, 'add', 'x.c')
      self.git(repo, 'commit', '-q', '-m', 'init')
    self.pin = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.dep, capture_output=True, text=True).stdout.strip()

  def git(self, repo, *args):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', *args],
                   cwd=repo, check=True, capture_output=True)

  def test_records_the_used_dependency_commit(self):
    ident = cb.identity({'lpc55'})
    self.assertEqual(ident['deps'], {'lib/mcu/dep': self.pin})
    self.assertEqual((ident['dirtyInputs'], ident['missingInputs'], ident['depsOffPin']), ([], [], []))

  def test_a_dependency_off_its_pin_is_flagged(self):
    self.pin = '0' * 40
    self.assertEqual(cb.identity({'lpc55'})['depsOffPin'], ['lib/mcu/dep'])

  def test_a_dependency_that_is_not_its_own_checkout_is_missing_not_the_parent(self):
    import shutil
    shutil.rmtree(self.dep / '.git')   # a plain directory: git -C would answer for the parent
    ident = cb.identity({'lpc55'})
    self.assertEqual((ident['missingInputs'], ident['deps']), (['lib/mcu/dep'], {}))

  def test_a_modified_or_untracked_dependency_file_at_the_same_commit_is_dirty(self):
    sha = cb.identity({'lpc55'})['deps']['lib/mcu/dep']
    (self.dep / 'x.c').write_text('changed')
    ident = cb.identity({'lpc55'})
    self.assertEqual((ident['deps']['lib/mcu/dep'], ident['dirtyInputs']), (sha, ['lib/mcu/dep']))
    self.git(self.dep, 'checkout', '-q', '--', 'x.c')
    (self.dep / 'new.h').write_text('untracked')
    self.assertEqual(cb.identity({'lpc55'})['dirtyInputs'], ['lib/mcu/dep'])


class Verdict(unittest.TestCase):
  def test_pass(self):
    code, r = run_main(['--board', 'lpcxpresso55s69'])
    self.assertEqual((code, r['pass']), (0, True))
    self.assertEqual(r['built'], ['cmake-build/x-lpcxpresso55s69/a.bin'])

  def test_docs_only_builds_nothing_and_passes_with_its_reason(self):
    with mock.patch.object(cb, 'build_board', side_effect=AssertionError('built')):
      code, r = run_main(['--scope', 'README.md'])
    self.assertEqual((code, r['boards'], r['nothingToBuild'][0]['path']), (0, [], 'README.md'))

  def test_failed_board_is_exit_1(self):
    code, r = run_main(['--board', 'lpcxpresso55s69', '--board', 'swan_r5'], boards={'swan_r5': 'failed'})
    self.assertEqual((code, r['pass'], r['firstError']), (1, False, 'swan_r5 failed'))

  def test_error_outranks_failure_and_failure_outranks_uncovered(self):
    code, _ = run_main(['--board', 'lpcxpresso55s69', '--board', 'swan_r5'],
                       boards={'swan_r5': 'failed', 'lpcxpresso55s69': 'error'})
    self.assertEqual(code, 2)
    code, _ = run_main(['--scope', 'ports/stm32f4/board_flash.c', 'ports/template_port/boards.c'],
                       boards={'feather_stm32f405_express': 'failed'})
    self.assertEqual(code, 1)

  def test_uncovered_path_fails_a_green_build(self):
    code, r = run_main(['--scope', 'ports/stm32f4/board_flash.c', 'ports/template_port/boards.c'])
    self.assertEqual((code, r['pass']), (3, False))
    self.assertEqual(r['uncovered'][0]['path'], 'ports/template_port/boards.c')

  def test_failed_ghostfat_or_tests_fail_the_run(self):
    code, _ = run_main(['--scope', 'ports/test_ghostfat/main.c'],
                       ghostfat=[{'config': '4k', 'status': 'failed', 'firstError': 'FAIL: (-10)'}])
    self.assertEqual(code, 1)
    code, r = run_main(['--scope', '.claude/test/test_build.py'],
                       tests={'status': 'failed', 'summary': 'FAILED (failures=1)', 'firstError': 'x'})
    self.assertEqual((code, r['tests']['status']), (1, 'failed'))

  def test_select_only_never_builds(self):
    out = io.StringIO()
    with mock.patch.object(cb, 'build_board', side_effect=AssertionError('built')), contextlib.redirect_stdout(out):
      self.assertEqual(cb.main(['--select-only', '--scope', 'src/main.c']), 0)
    m = json.loads(out.getvalue())
    self.assertEqual((m['version'], m['build']['full'], m['build']['needed']), (1, True, True))

  def test_usage_error_is_json_exit_2(self):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as e:
      cb.main(['--scope', 'README.md', '--worktree'])
    self.assertEqual(e.exception.code, 2)
    self.assertIn('--worktree needs --base', json.loads(out.getvalue())['error'])

  def test_backend_override_needs_board_and_shared_and_a_cmake_build(self):
    for argv, error in ((['--board', 'imxrt1060_evk', '--backend', 'cmake'], '--backend needs --board and --shared'),
                        (['--scope', 'src', '--shared', '--backend', 'cmake'], '--backend needs --board and --shared'),
                        (['--board', 'lpcxpresso55s69', '--shared', '--backend', 'cmake'], 'ports/lpc55 has no cmake build'),
                        (['--board', 'espressif_esp32s3_devkitm_1', '--shared', '--backend', 'cmake'],
                         'ports/espressif has no cmake build')):
      with self.subTest(argv), contextlib.redirect_stdout(io.StringIO()) as out, \
           mock.patch.object(cb, 'build_board', side_effect=AssertionError('built')):
        try:
          code = cb.main(argv)
        except SystemExit as e:
          code = e.code
      self.assertEqual(code, 2)
      self.assertIn(error, json.loads(out.getvalue().splitlines()[-1])['error'])

  def test_backend_override_builds_with_cmake(self):
    seen = []
    def build_board(board, backend, args, idf, flasher=None):
      seen.append(backend)
      return {'board': board, 'port': 'mimxrt10xx', 'backend': backend, 'buildDir': 'cmake-build/x', 'status': 'ok',
              'firstError': '', 'artifacts': [], 'sha256': {}}
    with mock.patch.object(cb, 'build_board', build_board), \
         mock.patch.object(cb, 'identity', lambda ports=(): {'head': 'h', 'dirty': False, 'submodules': {}, 'deps': {}, 'dirtyInputs': [], 'missingInputs': [], 'depsOffPin': []}), contextlib.redirect_stdout(io.StringIO()):
      self.assertEqual(cb.main(['--board', 'imxrt1060_evk', '--shared', '--backend', 'cmake']), 0)
    self.assertEqual(seen, ['cmake'])

  def test_passing_private_roots_leave_nothing_in_built(self):
    def build_board(board, backend, args, idf, flasher=None):
      return {'board': board, 'port': 'lpc55', 'backend': backend, 'buildDir': 'cmake-build/x', 'status': 'ok',
              'firstError': '', 'artifacts': ['a.bin'], 'removed': True}
    with mock.patch.object(cb, 'build_board', build_board), \
         mock.patch.object(cb, 'identity', lambda ports=(): {'head': 'h', 'dirty': False, 'submodules': {}, 'deps': {}, 'dirtyInputs': [], 'missingInputs': [], 'depsOffPin': []}), contextlib.redirect_stdout(io.StringIO()) as out:
      self.assertEqual(cb.main(['--board', 'lpcxpresso55s69']), 0)
    self.assertEqual(json.loads(out.getvalue().splitlines()[-1])['built'], [])

  def test_unreadable_get_deps_is_json_exit_2(self):
    cb.get_deps_table.cache_clear()
    self.addCleanup(cb.get_deps_table.cache_clear)
    with mock.patch.object(cb.runpy, 'run_path', side_effect=SyntaxError('invalid syntax')), \
         mock.patch.object(cb, 'changed_paths', lambda *a: (['lib/mcu/nxp/mcux-sdk/x.h'], {'mode': 'paths'})):
      code, r = run_main(['--scope', 'lib/mcu/nxp/mcux-sdk/x.h'])
    self.assertEqual((code, r['pass']), (2, False))
    self.assertIn('tools/get_deps.py', r['error'])

  def test_an_input_the_build_dirtied_is_recorded(self):
    _, r = run_main(['--board', 'lpcxpresso55s69'], identities=[CLEAN, dict(CLEAN, dirtyInputs=['lib/uf2'])])
    self.assertEqual(r['input']['inputsDirtiedByBuild'], ['lib/uf2'])

  def test_an_input_that_moved_during_the_build_is_recorded(self):
    sdk = 'lib/mcu/nxp/mcux-sdk'
    before = dict(CLEAN, submodules={'lib/uf2': 'a'}, deps={sdk: 'a'})
    for what, changed, moved in (('nothing', {}, []), ('head', {'head': 'h2'}, ['.']), ('tree', {'dirty': True}, ['.']),
                                 ('submodule commit', {'submodules': {'lib/uf2': 'b'}}, ['lib/uf2']),
                                 ('dependency commit', {'deps': {sdk: 'b'}}, [sdk]),
                                 ('dependency unlinked', {'deps': {}, 'missingInputs': [sdk]}, [sdk])):
      with self.subTest(what):
        _, r = run_main(['--board', 'lpcxpresso55s69'], identities=[before, dict(before, **changed)])
        self.assertEqual(r['input']['inputsDirtiedByBuild'], moved)

  def test_resolution_error_is_json_exit_2(self):
    code, r = run_main(['--board', 'no_such_board'])
    self.assertEqual((code, r['pass']), (2, False))
    self.assertIn('no_such_board', r['error'])


class BuildBoard(unittest.TestCase):
  def setUp(self):
    tmp = build_tmpdir()
    self.addCleanup(tmp.cleanup)
    self.build_dir = Path(tmp.name)
    patches = [mock.patch.object(cb, 'BUILD_DIR', self.build_dir), mock.patch.object(cb, 'check_deps', lambda p: None),
               mock.patch.object(cb, 'check_tools', lambda *a: None)]
    for p in patches:
      p.start()
      self.addCleanup(p.stop)
    self.args = mock.Mock(shared=False, define=['LOG=2'], verbose=False, idf='docker')

  def fake_make(self, write):
    calls = []

    def run(cmd, log, verbose, cwd=cb.ROOT):
      cmd = [str(c) for c in cmd]
      calls.append(cmd)
      root = Path(next(c for c in cmd if c.startswith('BUILD_ROOT='))[len('BUILD_ROOT='):])
      for rel in write(cmd):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text('x')
      return 0
    return run, calls

  def test_make_builds_like_ci_and_removes_a_passing_private_root(self):
    run, calls = self.fake_make(lambda cmd: LPC55_ARTIFACTS if 'copy-artifact' in cmd else [])
    with mock.patch.object(cb, 'run', run):
      rec = cb.build_board('lpcxpresso55s69', 'make', self.args, {})
    self.assertEqual(rec['status'], 'ok', rec)
    self.assertTrue(rec['removed'])
    self.assertIn('_bin/apps/update-tinyuf2-lpcxpresso55s69.uf2', rec['artifacts'])
    self.assertEqual(rec['notImplemented'], ['apps/erase_firmware'])
    main, copy = calls[0], calls[1]
    self.assertIn('self-update', main)
    self.assertNotIn('copy-artifact', main)   # never beside self-update under -j
    self.assertIn('copy-artifact', copy)
    self.assertIn('LOG=2', main)
    self.assertFalse(list(self.build_dir.iterdir()))

  def test_missing_expected_artifact_fails_and_keeps_the_root(self):
    run, _ = self.fake_make(lambda cmd: LPC55_ARTIFACTS[:2] if 'copy-artifact' in cmd else [])
    with mock.patch.object(cb, 'run', run):
      rec = cb.build_board('lpcxpresso55s69', 'make', self.args, {})
    self.assertEqual(rec['status'], 'failed')
    self.assertIn('update-tinyuf2-lpcxpresso55s69.uf2', rec['firstError'])
    self.assertTrue((self.build_dir / f'cmake-build-agent-{cb.os.getpid()}-lpcxpresso55s69').is_dir())

  def test_shared_root_is_rebuilt_from_clean_and_kept(self):
    self.args.shared = True
    root = self.build_dir / 'cmake-build-lpcxpresso55s69'
    root.mkdir()
    (root / 'stale.o').write_text('old configuration')
    run, _ = self.fake_make(lambda cmd: LPC55_ARTIFACTS if 'copy-artifact' in cmd else [])
    with mock.patch.object(cb, 'run', run):
      rec = cb.build_board('lpcxpresso55s69', 'make', self.args, {})
    self.assertEqual(rec['status'], 'ok', rec)
    self.assertNotIn('removed', rec)
    self.assertFalse((root / 'stale.o').exists())
    self.assertEqual(set(rec['sha256']), set(rec['artifacts']))
    self.assertTrue((root / '_bin' / 'tinyuf2-lpcxpresso55s69.bin').is_file())

  def test_an_idf_build_hashes_its_flash_config_and_needs_it(self):
    self.args.shared = True
    root = self.build_dir / 'cmake-build-espressif_esp32s3_devkitc_1'
    made = [str(p.relative_to(root)) for p in cb.expected_artifacts('espressif', 'x', 'idf', root)] + list(cb.IDF_CONFIG)

    def run(cmd, log, verbose, cwd=cb.ROOT):
      for rel in made:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel)
      return 0
    inspect = mock.Mock(return_value=mock.Mock(returncode=0))
    with mock.patch.object(cb, 'run', run), mock.patch.object(cb.subprocess, 'run', inspect), \
         mock.patch.object(cb, 'git', lambda *a: str(self.build_dir)):
      rec = cb.build_board('espressif_esp32s3_devkitc_1', 'idf', self.args, {'image': 'espressif/idf:v6.1'})
      self.assertEqual(rec['status'], 'ok', rec)
      self.assertLessEqual({'sdkconfig', '_bin/flash_args', '_bin/ota_data_initial.bin', '_bin/apps/dfu_runtime.uf2'},
                           set(rec['sha256']))
      made.remove('sdkconfig')
      rec = cb.build_board('espressif_esp32s3_devkitc_1', 'idf', self.args, {'image': 'espressif/idf:v6.1'})
    self.assertEqual(rec['status'], 'failed')
    self.assertIn('sdkconfig', rec['firstError'])

  def test_cmake_missing_app_image_fails(self):
    def run(cmd, log, verbose, cwd=cb.ROOT):
      log.write_text('ok')
      if cmd[:2] == ['cmake', '--build']:
        for f in ('tinyuf2.bin', 'tinyuf2.hex'):
          (Path(cmd[2]) / '_bin' / f).parent.mkdir(parents=True, exist_ok=True)
          (Path(cmd[2]) / '_bin' / f).write_text('x')
      return 0
    with mock.patch.object(cb, 'run', run):
      rec = cb.build_board('feather_stm32f405_express', 'cmake', self.args, {})
    self.assertEqual(rec['status'], 'failed')
    self.assertIn('update-tinyuf2.uf2', rec['firstError'])

  def test_non_default_backend_gets_its_own_root(self):
    with mock.patch.object(cb, 'run', lambda cmd, log, verbose, **k: log.write_text('make: *** Error 2') and 1):
      rec = cb.build_board('feather_stm32f405_express', 'make', self.args, {})
    self.assertTrue(rec['buildDir'].endswith('feather_stm32f405_express-make'))

  def test_missing_prerequisite_is_an_error_not_a_failure(self):
    with mock.patch.object(cb, 'check_deps', lambda p: 'lib/mcu/nxp/mcux-sdk missing'):
      rec = cb.build_board('lpcxpresso55s69', 'make', self.args, {})
    self.assertEqual((rec['status'], rec['firstError']), ('error', 'lib/mcu/nxp/mcux-sdk missing'))


class HilRecord(unittest.TestCase):
  """A HIL record binds the build's own flash target to the roster's probe or bridge."""

  def setUp(self):
    tmp = build_tmpdir()
    self.addCleanup(tmp.cleanup)
    self.tmp = Path(tmp.name)
    self.roster = self.tmp / 'local.json'
    self.roster.write_text(json.dumps({'boards': [
      {'name': 'metro_m7_1011', 'uid': 'U', 'flasher': {'name': 'jlink', 'uid': '000801012283', 'args': '-device MIMXRT1011DAE5A'}},
      {'name': 'espressif_esp32s3_devkitc_1', 'uid': 'M', 'flasher': {'name': 'esptool', 'uid': 'b1', 'args': '--chip esp32s3'}},
      {'name': 'lpcxpresso55s69', 'uid': 'L', 'flasher': {'name': 'openocd', 'uid': 'x', 'args': '-f a.cfg'}}]}))
    self.config = str(self.roster.relative_to(ROOT))

  def jlink_tree(self, root, script=None, options='-USB 000801012283 -ExitOnError 1 -NoGui 1', interface='swd'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'tinyuf2.jlink').write_text(script or f'halt\nloadfile {root / "tinyuf2.hex"}\nr\ngo\nexit')
    line = (f'cd {root} && JLinkExe -device MIMXRT1011DAE5A {options} -if {interface} -JTAGConf -1,-1 -speed auto '
            f'-CommandFile {root / "tinyuf2.jlink"}')
    return lambda d, args: subprocess.CompletedProcess(args, 0, f'arm-none-eabi-gcc ...\n{line}\n', '')

  def idf_tree(self, root, chip='esp32s3', extra='', args_file='flash_args'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'flash_args').write_text('--flash-mode dio --flash-freq 80m --flash-size 8MB\n0x0 bootloader/bootloader.bin\n'
                                     '0x410000 tinyuf2.bin\n0x8000 partition_table/partition-table.bin\n'
                                     f'0xe000 ota_data_initial.bin\n{extra}')
    line = (f'cd /opt/esp/idf/components/esptool_py && cmake -D IDF_PATH=/opt/esp/idf '
            f'-D "SERIAL_TOOL=/opt/esp/python_env/idf6.1_py3.12_env/bin/python;-m;esptool;--chip;{chip}" '
            f'-D "SERIAL_TOOL_ARGS=--before=default-reset;--after=hard-reset;write-flash;@{args_file}" '
            f'-D SERIAL_TOOL_IS_WRITE_FLASH=1 -D SERIAL_TOOL_FLASH_ARGS_FILE={args_file} '
            f'-D WORKING_DIRECTORY={root} -P /opt/esp/idf/components/esptool_py/run_serial_tool.cmake')
    return lambda d, args: subprocess.CompletedProcess(args, 0, line + '\n', '')

  def test_the_roster_flasher_selects_the_probe_through_configure_defines(self):
    self.assertEqual(cb.roster_flasher(self.config, 'metro_m7_1011'),
                     ({'name': 'jlink', 'uid': '000801012283', 'device': 'MIMXRT1011DAE5A'},
                      ['JLINK_OPTION=-USB 000801012283 -ExitOnError 1 -NoGui 1']))
    self.assertEqual(cb.roster_flasher(self.config, 'espressif_esp32s3_devkitc_1'),
                     ({'name': 'esptool', 'uid': 'b1', 'device': 'esp32s3'}, []))   # the tty is chosen at flash time
    for board, err in (('lpcxpresso55s69', 'no HIL flash target'), ('imxrt1060_evk', 'not on')):
      with self.subTest(board), self.assertRaisesRegex(cb.Fail, err):
        cb.roster_flasher(self.config, board)

  def test_the_generated_jlink_target_must_name_the_roster_probe_and_the_build_image(self):
    flasher = {'name': 'jlink', 'uid': '000801012283', 'device': 'MIMXRT1011DAE5A'}
    root = self.tmp / 'b'
    out = cb.flash_binding(flasher, root, self.jlink_tree(root))
    self.assertEqual((out['target'], out['inputs']), ('tinyuf2-jlink', ['tinyuf2.jlink', 'tinyuf2.hex']))
    for what, tree in (('another probe', dict(options='-USB 1 -ExitOnError 1 -NoGui 1')),
                       ('no exit on error', dict(options='-USB 000801012283')),
                       ('two probes', dict(options='-USB 000801012283 -USB 2 -ExitOnError 1 -NoGui 1')),
                       ('jtag', dict(interface='jtag')),
                       ('another image', dict(script=f'halt\nloadfile {self.tmp / "other.hex"}\nr\ngo\nexit')),
                       ('a second image', dict(script=f'halt\nloadfile {root / "tinyuf2.hex"}\nloadfile /tmp/o.hex\nr\ngo\nexit'))):
      with self.subTest(what), self.assertRaisesRegex(cb.Fail, 'does not flash'):
        cb.flash_binding(flasher, root, self.jlink_tree(root, **tree))

  def test_the_idf_flash_target_must_write_flash_args_for_the_roster_chip(self):
    flasher = {'name': 'esptool', 'uid': 'b1', 'device': 'esp32s3'}
    root = self.tmp / 'e'
    out = cb.flash_binding(flasher, root, self.idf_tree(root))
    self.assertEqual(out['inputs'][0], 'flash_args')
    for what, tree in (('another chip', dict(chip='esp32s2')),
                       ('a chip prefix', dict(chip='esp32s3WRONG')),
                       ('another argument file', dict(args_file='flash_args.extra')),
                       ('another segment', dict(extra='0x10000 app.bin\n'))):
      with self.subTest(what), self.assertRaisesRegex(cb.Fail, 'does not flash'):
        cb.flash_binding(flasher, root, self.idf_tree(root, **tree))

  def ready(self, flasher, root, tree, steps, nested=(), code=0, banner=True):
    """flash_ready on `root` whose target dry-runs `steps` and whose bootloader subproject dry-runs `nested`;
    `banner` False drops ninja's banner from both, 'nested' from the subproject's only."""
    commands = tree(root)
    command = cb.flash_binding(flasher, root, commands)['command']
    flash = {'target': cb.FLASH[flasher['name']][0], 'flasher': flasher, 'command': command}

    def ninja(d, args):
      self.assertEqual(args[:2], ['-n', '-v'])
      out = [command if x == 'FLASH' else x for x in (steps if d == root else nested)]
      return subprocess.CompletedProcess(args, code, 'entrypoint banner\n' + ("ninja: Entering directory `x'\n" if banner is True or banner == 'nested' and d == root else '') +
                                         ''.join(f'[{i}/9] {x}\n' for i, x in enumerate(out, 1)), '')
    cb.flash_ready(root, flash, ninja)

  def test_a_flash_target_is_ready_only_when_its_dry_run_shows_just_the_flasher(self):
    jlink = {'name': 'jlink', 'uid': '000801012283', 'device': 'MIMXRT1011DAE5A'}
    root = self.tmp / 'b'
    self.ready(jlink, root, self.jlink_tree, ['FLASH'])
    rebuild = [f'/usr/bin/arm-none-eabi-gcc -c {ROOT}/src/main.c -o main.c.obj', ': && arm-none-eabi-gcc -o tinyuf2.elf', 'FLASH']
    for what, steps, kw in (('a rebuild', rebuild, {}), ('a CMake re-run', ['/usr/bin/cmake --regenerate-during-build -S.. -B.'], {}),
                            ('ninja fails', ['FLASH'], {'code': 1}), ('nothing', [], {}),
                            ('no ninja banner', ['FLASH'], {'banner': False}),
                            ('another command', ['JLinkExe -USB 1'], {}), ('the flasher twice', ['FLASH', 'FLASH'], {})):
      with self.subTest(what), self.assertRaisesRegex(cb.Fail, 'would not run only its flasher'):
        self.ready(jlink, root, self.jlink_tree, steps, **kw)

  def test_an_idf_flash_target_may_also_run_steps_that_write_no_flash_input(self):
    esp = {'name': 'esptool', 'uid': 'b1', 'device': 'esp32s3'}
    root = self.tmp / 'e'
    cmake, py = '/opt/esp/tools/cmake/3.30.2/bin/cmake', '/opt/esp/python_env/idf5.3_py3.10_env/bin/python'
    sizes = f'{py} /opt/esp/idf/components/partition_table/check_sizes.py --offset 0x8000'
    size = (f'cd {root}/esp-idf/esptool_py && {sizes} partition --type app {root}/partition_table/partition-table.bin '
            f'{root}/tinyuf2.bin')
    boot_size = f'cd {root}/bootloader/esp-idf/esptool_py && {sizes} bootloader 0x0 {root}/bootloader/bootloader.bin'
    copies = ' && '.join(f'{cmake} -E copy {root}/{f} {root}/_bin/{Path(f).name}' for f in cb.FLASH['esptool'][1])
    post = (f'cd {root} && bash {root}/tinyuf2.postbuild.sh && cd {root} && {cmake} -E echo "Copy binaries for artifact" && '
            f'{copies} && cd {root} && {py}3.10 {ROOT}/lib/uf2/utils/uf2conv.py --carray -o '
            f'{root}/apps/update_tinyuf2/bootloader_bin.c {root}/tinyuf2.bin')
    stamps = (f'cd {root} && {cmake} -E make_directory {root}/CMakeFiles && {cmake} -E touch {root}/CMakeFiles/bootloader-complete '
              f'&& {cmake} -E touch {root}/bootloader-prefix/src/bootloader-stamp/bootloader-done')
    fresh = [f'cd {root}/bootloader && {cmake} --build .', size, f'cd {root}/bootloader && {cmake} -E echo_append', post, stamps,
             'FLASH']
    script = root / 'tinyuf2.postbuild.sh'
    good = ('#!/bin/bash\necho "Creating combined.bin"\n'
            f"esptool.py --chip esp32s3 merge_bin --output combined.bin $(tr '\\n' ' ' < {root}/flash_args)\n")
    self.idf_tree(root)
    script.write_text(good)
    self.ready(esp, root, self.idf_tree, fresh, [boot_size])
    cases = (('a CMake re-run', [f'cd {root} && {cmake} --regenerate-during-build -S/p -B{root}'], [boot_size], good),
             ('an app rebuild', [f'{root}/xtensa-esp32s3-elf-g++ -o tinyuf2.elf'] + fresh, [boot_size], good),
             ('a bootloader rebuild', fresh, ['xtensa-esp32s3-elf-gcc -c bootloader_start.c', boot_size], good),
             ('a size check and a copy', [size + f' && cp /tmp/o.bin {root}/tinyuf2.bin', 'FLASH'], [], good),
             ('a copy out of _bin', [f'{cmake} -E copy /tmp/o.bin {root}/_bin/../tinyuf2.bin', 'FLASH'], [], good),
             ('a redirect', [f'{cmake} -E echo x > {root}/tinyuf2.bin', 'FLASH'], [], good),
             ('a changed post-build script', fresh, [boot_size], good + f'cp /tmp/o.bin {root}/tinyuf2.bin\n'),
             ('a step after the bootloader build', [f'cd {root}/bootloader && {cmake} --build . && {cmake} -E echo_append', 'FLASH'],
              ['xtensa-esp32s3-elf-gcc -c bootloader_start.c'], good),
             ('a copy through a symlink', [f'{cmake} -E copy /tmp/o.bin {root}/_bin/alias/tinyuf2.bin', 'FLASH'], [], good),
             ('a touch of a flash input', [f'{cmake} -E touch {root}/flash_args', 'FLASH'], [], good))
    (root / '_bin').mkdir()
    (root / '_bin/alias').symlink_to('..')
    for what, steps, nested, text in cases:
      with self.subTest(what), self.assertRaisesRegex(cb.Fail, 'would not run only its flasher'):
        script.write_text(text)
        self.ready(esp, root, self.idf_tree, steps, nested)
    script.write_text(good)
    (root / '_bin/alias').unlink()
    (root / '_bin').rmdir()
    (root / '_bin').symlink_to('.')   # a copy into _bin would land on the input itself
    with self.subTest('a symlinked _bin'), self.assertRaisesRegex(cb.Fail, 'would not run only its flasher'):
      self.ready(esp, root, self.idf_tree, [f'{cmake} -E copy /tmp/o.bin {root}/_bin/tinyuf2.bin', 'FLASH'], [boot_size])
    (root / 'apps').symlink_to('.')
    (root / 'update_tinyuf2').symlink_to('.')
    carray = 'cd ' + post.split(' && cd ')[-1]
    self.ready(esp, root, self.idf_tree, [carray, 'FLASH'], [boot_size])   # before the alias
    (root / 'bootloader_bin.c').symlink_to('tinyuf2.bin')
    with self.subTest('a C array onto the image'), self.assertRaisesRegex(cb.Fail, 'would not run only its flasher'):
      self.ready(esp, root, self.idf_tree, [carray, 'FLASH'], [boot_size])
    (root / 'combined.bin').symlink_to('tinyuf2.bin')
    with self.subTest('a post-build onto the image'), self.assertRaisesRegex(cb.Fail, 'would not run only its flasher'):
      self.ready(esp, root, self.idf_tree, [post.split(' && cd ')[0], 'FLASH'], [boot_size])
    (root / 'combined.bin').unlink()
    self.ready(esp, root, self.idf_tree, [post.split(' && cd ')[0], 'FLASH'], [boot_size])
    (root / '_bin').unlink()
    (root / '_bin').mkdir()
    (root / '_bin/image.bin').write_text('x')
    (root / 'ota_data_initial.bin').unlink(missing_ok=True)
    (root / 'ota_data_initial.bin').symlink_to('_bin/image.bin')
    with self.subTest('a copy onto a symlinked input'), self.assertRaisesRegex(cb.Fail, 'would not run only its flasher'):
      self.ready(esp, root, self.idf_tree, [f'{cmake} -E copy /tmp/o.bin {root}/_bin/image.bin', 'FLASH'], [boot_size])
    with self.assertRaisesRegex(cb.Fail, 'bootloader: ninja -n failed'):
      self.ready(esp, root, self.idf_tree, fresh, [boot_size], banner='nested')

  def test_a_hil_record_pins_the_target_inputs_and_holds_the_build_lock(self):
    args = mock.Mock(shared=True, define=[], verbose=False, idf='docker')
    built = []

    def fake_cmake(port, board, root, defines, log, verbose):
      built.append(defines)
      lock = root.with_name(root.name + '.lock')
      with open(lock) as f, self.assertRaises(BlockingIOError):   # held while the build runs
        cb.fcntl.flock(f, cb.fcntl.LOCK_EX | cb.fcntl.LOCK_NB)
      for rel in ('_bin/tinyuf2.bin', '_bin/tinyuf2.hex', '_bin/apps/blinky.uf2', 'tinyuf2.hex'):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel)
      return True, []
    build_dir = self.tmp / 'cmake-build'   # absent: the first shared build creates it before its lock
    with mock.patch.object(cb, 'BUILD_DIR', build_dir), mock.patch.object(cb, 'check_deps', lambda p: None), \
         mock.patch.object(cb, 'check_tools', lambda *a: None), mock.patch.object(cb, 'build_cmake', fake_cmake), \
         mock.patch.object(cb, 'expected_artifacts', lambda *a: []), \
         mock.patch.object(cb, 'ninja_in', lambda backend, mode, image, root, args: self.jlink_tree(root)(root, args)):
      rec = cb.build_board('metro_m7_1011', 'cmake', args, {}, cb.roster_flasher(self.config, 'metro_m7_1011'))
    self.assertEqual(rec['status'], 'ok', rec)
    self.assertEqual(built, [['JLINK_OPTION=-USB 000801012283 -ExitOnError 1 -NoGui 1']])
    self.assertIn('tinyuf2.hex', rec['sha256'])
    self.assertIn('tinyuf2.jlink', rec['sha256'])
    self.assertEqual(rec['flash']['defines'], ['JLINK_OPTION=-USB 000801012283 -ExitOnError 1 -NoGui 1'])

  def test_a_hil_record_takes_probe_selection_only_from_the_roster(self):
    for argv in (['--board', 'metro_m7_1011', '--shared', '--hil-config', self.config, '-D', 'JLINK_OPTION=-USB 1'],
                 ['--board', 'metro_m7_1011', '--shared', '--hil-config', self.config, '-D', 'ESPPORT:STRING=/dev/x'],
                 ['--board', 'metro_m7_1011', '--hil-config', self.config]):
      with self.subTest(argv), contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as e:
        cb.main(argv)
      self.assertEqual(e.exception.code, 2)
      self.assertIn('usage', json.loads(out.getvalue())['error'])


class Ghostfat(unittest.TestCase):
  @staticmethod
  def fake_ghostfat_make(cmd, log, verbose, cwd=None):
    log.write_text('built')
    root = Path(next(str(c) for c in cmd if str(c).startswith('BUILD_ROOT='))[len('BUILD_ROOT='):])
    work = root / 'ports' / cb.GHOSTFAT
    (work / 'obj').mkdir(parents=True)
    for f in ('obj/ghostfat.o', 'tinyuf2-4k.elf', 'knowngood.img'):
      (work / f).write_text('x')
    return 0

  def test_a_damaged_known_good_image_is_an_error_and_keeps_only_the_log(self):
    with build_tmpdir() as tmp, mock.patch.object(cb, 'BUILD_DIR', Path(tmp)), \
         mock.patch.object(cb, 'boards_of', lambda port: ['4k']), \
         mock.patch.object(cb, 'run', self.fake_ghostfat_make), \
         mock.patch.object(cb.gzip, 'open', side_effect=EOFError('truncated')):
      [rec] = cb.run_ghostfat(False)
      root = Path(tmp) / f'cmake-build-agent-{cb.os.getpid()}-ghostfat-4k'
      self.assertEqual(rec['status'], 'error')
      self.assertIn('truncated', rec['firstError'])
      self.assertEqual([p.name for p in root.iterdir()], ['check_build.log'])


class BackendCommands(unittest.TestCase):
  """Each backend builds into the root it is given and nowhere in the source tree."""

  def setUp(self):
    self.root = cb.BUILD_DIR / 'cmake-build-agent-0-x'
    self.calls = []

  def capture(self, results=()):
    results = list(results)

    def run(cmd, log, verbose, cwd=cb.ROOT):
      self.calls.append([str(c) for c in cmd])
      return results.pop(0) if results else 0
    return mock.patch.object(cb, 'run', run)

  def test_cmake_configures_into_the_root_with_artifacts_there(self):
    with self.capture():
      ok, _ = cb.build_cmake('stm32f4', 'feather_stm32f405_express', self.root, ['LOG=2'], Path('log'), False)
    self.assertTrue(ok)
    cfg, build = self.calls
    self.assertEqual(cfg[cfg.index('-B') + 1], str(self.root))
    self.assertIn(f'-DARTIFACT_PATH={self.root / "_bin"}', cfg)
    self.assertIn('-DLOG=2', cfg)
    self.assertEqual(build, ['cmake', '--build', str(self.root)])

  def test_cmake_configure_failure_skips_the_build(self):
    with self.capture([1]):
      ok, _ = cb.build_cmake('stm32f4', 'feather_stm32f405_express', self.root, [], Path('log'), False)
    self.assertFalse(ok)
    self.assertEqual(len(self.calls), 1)

  def test_idf_runs_ci_image_with_the_git_common_dir_mounted(self):
    with self.capture([1]), mock.patch.object(cb, 'git', lambda *a: '/srv/repo/.git\n'):
      ok, _ = cb.build_idf('espressif_esp32s3_devkitm_1', self.root, ['LOG=2'], Path('log'), False, 'docker',
                           'espressif/idf:v6.1')
    self.assertFalse(ok)
    [cmd] = self.calls
    self.assertEqual(cmd[:2], ['docker', 'run'])
    self.assertIn('espressif/idf:v6.1', cmd)
    mounts = {cmd[i + 1] for i, c in enumerate(cmd) if c == '-v'}
    self.assertLessEqual({f'{cb.ROOT}:{cb.ROOT}', '/srv/repo/.git:/srv/repo/.git'}, mounts)
    inner = cmd[-1]
    self.assertIn(f'-B {self.root}', inner)
    self.assertIn(f'-DARTIFACT_PATH={self.root / "_bin"}', inner)
    self.assertIn('-DLOG=2', inner)

  def test_expected_artifacts_per_backend(self):
    names = lambda port, board, backend: {str(p.relative_to(self.root))
                                          for p in cb.expected_artifacts(port, board, backend, self.root)}
    self.assertEqual(names('stm32f4', 'feather_stm32f405_express', 'cmake'),
                     {'_bin/tinyuf2.bin', '_bin/tinyuf2.hex', '_bin/apps/update-tinyuf2.uf2', '_bin/apps/blinky.uf2',
                      '_bin/apps/erase_firmware.uf2'})
    self.assertLessEqual({'_bin/combined.bin', '_bin/apps/update-tinyuf2.uf2'},
                         names('espressif', 'espressif_esp32s3_devkitm_1', 'idf'))
    self.assertNotIn('_bin/apps/update-tinyuf2-swan_r5.uf2', names('stm32l4', 'swan_r5', 'make'))
    # mimxrt10xx copies its self-update image to ARTIFACT_PATH instead of building apps/self_update
    self.assertIn('_bin/apps/update-tinyuf2.uf2', names('mimxrt10xx', 'imxrt1060_evk', 'cmake'))


class FirstError(unittest.TestCase):
  def test_compiler_diagnostic_beats_ninjas_failed_line(self):
    log = 'FAILED: CMakeFiles/tinyuf2.dir/src/main.c.obj\n/x/src/main.c:12:3: error: unknown type name\n'
    self.assertEqual(cb.first_error(log), '/x/src/main.c:12:3: error: unknown type name')


if __name__ == '__main__':
  unittest.main()
