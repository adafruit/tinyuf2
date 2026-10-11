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


def run_main(argv, boards=None, ghostfat=None, tests=None):
  """main() with builds stubbed: `boards` maps board -> status."""
  boards = boards or {}

  def build_board(board, backend, args, idf):
    status = boards.get(board, 'ok')
    return {'board': board, 'port': cb.port_of(board), 'backend': backend, 'buildDir': f'cmake-build/x-{board}',
            'status': status, 'firstError': '' if status == 'ok' else f'{board} {status}', 'artifacts': ['a.bin']}

  out = io.StringIO()
  with mock.patch.object(cb, 'build_board', build_board), \
       mock.patch.object(cb, 'run_ghostfat', lambda v: ghostfat or []), \
       mock.patch.object(cb, 'run_tests', lambda: tests or {'status': 'ok', 'summary': 'OK', 'firstError': ''}), \
       mock.patch.object(cb, 'identity', lambda: {'head': 'h', 'dirty': False, 'submodules': {}}), \
       contextlib.redirect_stdout(out):
    code = cb.main(argv)
  return code, json.loads(out.getvalue().splitlines()[-1])


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

  def test_passing_private_roots_leave_nothing_in_built(self):
    def build_board(board, backend, args, idf):
      return {'board': board, 'port': 'lpc55', 'backend': backend, 'buildDir': 'cmake-build/x', 'status': 'ok',
              'firstError': '', 'artifacts': ['a.bin'], 'removed': True}
    with mock.patch.object(cb, 'build_board', build_board), \
         mock.patch.object(cb, 'identity', lambda: {}), contextlib.redirect_stdout(io.StringIO()) as out:
      self.assertEqual(cb.main(['--board', 'lpcxpresso55s69']), 0)
    self.assertEqual(json.loads(out.getvalue().splitlines()[-1])['built'], [])

  def test_unreadable_get_deps_is_json_exit_2(self):
    cb.deps_rows.cache_clear()
    self.addCleanup(cb.deps_rows.cache_clear)
    with mock.patch.object(cb.runpy, 'run_path', side_effect=SyntaxError('invalid syntax')), \
         mock.patch.object(cb, 'changed_paths', lambda *a: (['lib/mcu/nxp/mcux-sdk/x.h'], {'mode': 'paths'})):
      code, r = run_main(['--scope', 'lib/mcu/nxp/mcux-sdk/x.h'])
    self.assertEqual((code, r['pass']), (2, False))
    self.assertIn('tools/get_deps.py', r['error'])

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
    self.assertTrue((root / '_bin' / 'tinyuf2-lpcxpresso55s69.bin').is_file())

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
                           'espressif/idf:v5.3.2')
    self.assertFalse(ok)
    [cmd] = self.calls
    self.assertEqual(cmd[:2], ['docker', 'run'])
    self.assertIn('espressif/idf:v5.3.2', cmd)
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


class FirstError(unittest.TestCase):
  def test_compiler_diagnostic_beats_ninjas_failed_line(self):
    log = 'FAILED: CMakeFiles/tinyuf2.dir/src/main.c.obj\n/x/src/main.c:12:3: error: unknown type name\n'
    self.assertEqual(cb.first_error(log), '/x/src/main.c:12:3: error: unknown type name')


if __name__ == '__main__':
  unittest.main()
