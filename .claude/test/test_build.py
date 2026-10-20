"""The build contract: check_build.py's tables agree with CI, each selection rule picks the boards
that compile a change, and the JSON and exit code follow SKILL.md. Builds are stubbed here; a real
build is evidence only from a run of the script itself."""
import contextlib
import functools
import importlib.util
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '.claude' / 'skills' / 'build' / 'scripts' / 'check_build.py'
LPC55_ARTIFACTS = ['_bin/tinyuf2-lpcxpresso55s69.bin', '_bin/tinyuf2-lpcxpresso55s69.hex',
                   '_bin/apps/update-tinyuf2-lpcxpresso55s69.uf2']


FAKE_TOOL = '''#!{python}
import os, subprocess, sys, time
from pathlib import Path
log = Path(os.environ['TOOLS_LOG'])
container = log.with_name('container')   # the one container the fake daemon holds
with open(log, 'a') as f:
  f.write(' '.join([Path(sys.argv[0]).name] + sys.argv[1:]) + '\\n')
if sys.argv[1] == 'rm':
  if os.environ.get('RM_EXIT'):
    sys.exit(int(os.environ['RM_EXIT']))
  container.unlink(missing_ok=True)
  sys.exit(0)
if sys.argv[1] == 'ps':
  print('c0ffee' if container.exists() else '')
  sys.exit(0)
if sys.argv[1] == 'run' and os.environ.get('CREATE_AFTER'):   # the daemon's create, landing after its client is gone
  subprocess.Popen([sys.executable, '-c', 'import pathlib, sys, time; time.sleep(float(sys.argv[1])); pathlib.Path(sys.argv[2]).touch(); '
                    'open(sys.argv[3], "a").write("daemon created")', os.environ['CREATE_AFTER'], str(container), str(log)],
                   start_new_session=True)
elif sys.argv[1] == 'run':
  container.touch()
if os.environ.get('HANG'):
  with open(os.environ['PIDS'], 'a') as f:
    f.write(f'{{os.getpid()}} {{subprocess.Popen(["sleep", "60"]).pid}}\\n')
  time.sleep(60)
if os.environ.get('UNKNOWN_TARGET'):   # as ninja 1.13 reports it: stderr only, nothing on stdout
  print(f"ninja: error: unknown target '{{sys.argv[-1]}}'", file=sys.stderr)
  sys.exit(1)
print(os.environ.get('STDOUT', "ninja: Entering directory `x'"))
print('ninja: warning: on stderr', file=sys.stderr)
'''


def alive(pid, wait=2):
  """Whether `pid` is still a live process (not gone or a zombie) after up to `wait` s."""
  end = time.monotonic() + wait
  while True:
    try:
      if Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
        return False
    except OSError:
      return False
    if time.monotonic() >= end:
      return True
    time.sleep(0.05)


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

  def test_espressif_representatives_cover_every_idf_target(self):
    target = lambda b: re.search(r'IDF_TARGET "(\w+)"', (ROOT / 'ports/espressif/boards' / b / 'board.cmake').read_text())[1]
    every = {target(b.name) for b in (ROOT / 'ports/espressif/boards').iterdir() if (b / 'board.cmake').is_file()}
    self.assertEqual({target(b) for b in cb.REPRESENTATIVES['espressif']}, every)

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
                 'ports/mimxrt10xx/apps/app.mk', 'ports/espressif/Makefile', 'ports/lpc55/Makefile'):
      self.assertEqual(classify(path)[:2], ('other-backend', 'gap'), path)

  def test_shared_make_file_selects_make_ports_and_the_codeql_build(self):
    make_reps = [(b, 'make') for p, be in cb.BACKENDS.items() if be == 'make' for b in cb.REPRESENTATIVES[p]]
    for path in ('ports/make.mk', 'ports/rules.mk'):
      rule, effect, boards, _, _ = classify(path)
      self.assertEqual((rule, effect), ('make-shared', 'select'), path)
      self.assertEqual(boards, sorted(make_reps + [('feather_stm32f405_express', 'make')]), path)

  def test_make_files_codeql_builds_select_its_make_build(self):
    for path in ('ports/stm32f4/Makefile', 'ports/stm32f4/port.mk',
                 'ports/stm32f4/boards/feather_stm32f405_express/board.mk', '.github/workflows/codeql-buildscript.sh'):
      self.assertEqual(classify(path)[2], [('feather_stm32f405_express', 'make')], path)

  def test_port_file_selects_its_representatives(self):
    rule, effect, boards, _, _ = classify('ports/mimxrt10xx/board_flash.c')
    self.assertEqual((rule, effect), ('port', 'select'))
    self.assertEqual(boards, [('imxrt1064_evk', 'cmake'), ('imxrt1170_evk', 'cmake')])

  def test_app_selects_the_boards_that_build_it(self):
    self.assertEqual(classify('ports/mimxrt10xx/apps/factory_test/main.c')[2], [('metro_m7_1011', 'cmake')])
    self.assertEqual(classify('ports/mimxrt10xx/apps/dfu_runtime/board_dfu_runtime.c')[2],
                     [('imxrt1064_evk', 'cmake'), ('imxrt1170_evk', 'cmake')])

  def test_app_nothing_builds_is_uncovered(self):
    self.assertEqual(classify('ports/stm32l4/apps/erase_firmware/Makefile')[:2], ('port-app', 'gap'))
    self.assertEqual(classify('ports/espressif/apps/erase_firmware/main/CMakeLists.txt')[:2], ('port-app', 'gap'))
    self.assertEqual(classify('ports/espressif/apps/blinky/main/CMakeLists.txt')[:2], ('port-app', 'select'))

  def test_top_level_app_selects_ports_whose_backend_compiles_it(self):
    ports = {cb.port_of(b) for b, _ in classify('apps/blinky/src/blinky.c')[2]}
    self.assertEqual(ports, {'espressif', 'maxim', 'mimxrt10xx', 'samd51', 'stm32f3', 'stm32f4', 'stm32h5'})

  def test_dependency_selects_the_ports_get_deps_names(self):
    self.assertEqual(classify('lib/mcu/st/cmsis_device_f4/x.h')[2],
                     [('feather_stm32f405_express', 'cmake'), ('stm32f411ve_discovery', 'cmake')])
    self.assertEqual(classify('lib/sct_neopixel/x.c')[2], [('lpcxpresso55s69', 'cmake')])

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
    for path in ('.claude/skills/hil-contract/scripts/hil_test.py', 'test/hil/local.json', 'test/hil/ci.json', 'lib/agentrc',
                 '.github/workflows/hil.yml'):
      r = cb.classify(path)
      self.assertEqual((r['rule'], r['tests'], r['hil'], r['boards']), ('hil-control', True, True, {}), path)
    self.assertEqual(cb.classify('.claude/skills/hil-contract/SKILL.md')['effect'], 'none')   # wording costs no hardware
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


def ci(*paths):
  return cb.ci_selection(cb.select(paths))


class CiSelection(unittest.TestCase):
  """build.ci: what CI builds, every board a change reaches rather than the representatives."""
  def test_board_file_selects_that_board_even_off_the_representatives(self):
    self.assertEqual(ci('ports/lpc55/boards/lpcxpresso55s28/board.h'),
                     {'full': False, 'ports': {'lpc55': ['lpcxpresso55s28']}, 'ghostfat': False})

  def test_port_wide_changes_select_every_board_of_the_port(self):
    for path, ports in (('ports/mimxrt10xx/board_flash.c', ['mimxrt10xx']),
                        ('ports/lpc55/boards/no_such_board/board.h', ['lpc55']),   # a deleted board
                        ('lib/mcu/st/cmsis_device_f4/x.h', ['stm32f4']),
                        ('ports/make.mk', [p for p, be in cb.BACKENDS.items() if be == 'make']),
                        ('apps/blinky/src/blinky.c', cb.ports_using_app('blinky'))):
      self.assertEqual(ci(path), {'full': False, 'ports': {p: cb.boards_of(p) for p in sorted(ports)},
                                  'ghostfat': False}, path)

  def test_port_app_selects_the_boards_that_build_it(self):
    self.assertEqual(ci('ports/mimxrt10xx/apps/factory_test/main.c')['ports'], {'mimxrt10xx': ['metro_m7_1011']})
    self.assertEqual(ci('ports/mimxrt10xx/apps/dfu_runtime/board_dfu_runtime.c')['ports'],
                     {'mimxrt10xx': cb.boards_of('mimxrt10xx')})
    self.assertEqual(ci('ports/espressif/apps/blinky/main/CMakeLists.txt')['ports'],
                     {'espressif': cb.boards_of('espressif')})

  def test_shared_code_and_how_ci_builds_select_everything(self):
    for path in ('lib/tinyusb', 'src/main.c', 'ports/family_support.cmake', 'tools/get_deps.py', 'some/new/file.c',
                 '.github/workflows/build.yml', '.github/workflows/build_util.yml', '.github/actions/x/action.yml',
                 '.github/workflows/ci_set_matrix.py', '.claude/skills/build/scripts/check_build.py'):
      self.assertEqual(ci(path), {'full': True, 'ports': {}, 'ghostfat': True}, path)
    self.assertTrue(ci('ports/lpc55/boards/lpcxpresso55s28/board.h', 'lib/tinyusb')['full'])

  def test_ghostfat_input_selects_ghostfat_only(self):
    self.assertEqual(ci('ports/test_ghostfat/main.c'), {'full': False, 'ports': {}, 'ghostfat': True})

  def test_paths_no_build_job_compiles_select_nothing(self):
    for path in ('README.md', '.claude/test/test_build.py', 'test/hil/local.json', '.github/workflows/codeql.yml',
                 '.github/workflows/codeql-buildscript.sh', 'ports/stm32f4/Makefile', 'ports/ch32v20x/boards.c',
                 'ports/lpc55/apps/erase_firmware/Makefile', 'lib/agentrc'):
      self.assertEqual(ci(path), {'full': False, 'ports': {}, 'ghostfat': False}, path)

  def test_selections_union_and_a_whole_port_absorbs_its_boards(self):
    self.assertEqual(ci('ports/lpc55/boards/lpcxpresso55s28/board.h', 'ports/lpc55/boards/lpcxpresso55s69/board.h',
                        'ports/stm32h5/boards/stm32h503_nucleo/board.h')['ports'],
                     {'lpc55': ['lpcxpresso55s28', 'lpcxpresso55s69'], 'stm32h5': ['stm32h503_nucleo']})
    self.assertEqual(ci('ports/lpc55/boards/lpcxpresso55s28/board.h', 'ports/lpc55/boards.c')['ports'],
                     {'lpc55': cb.boards_of('lpc55')})

  def test_ci_covers_every_board_a_tracked_path_selects_locally(self):
    _, codeql_board = cb.codeql_build()
    for path in cb.git('ls-files').split():
      r = cb.classify(path)
      if r['ci'] == cb.FULL:
        continue
      local = {b for b, _ in r['boards']} - ({codeql_board} if r['rule'] in ('codeql', 'make-shared') else set())
      covered = {b for p, boards in r['ci'].items() for b in (cb.boards_of(p) if boards is None else boards)}
      self.assertLessEqual(local, covered, path)


class ScratchRepo(unittest.TestCase):
  """A test in a scratch directory, self.repo. Every GIT_* variable is dropped first:
  under pre-commit they point at the real checkout, and git would act on it."""

  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.repo = Path(tmp.name)
    env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, clear=True)
    env.start()
    self.addCleanup(env.stop)

  def git(self, *args, cwd=None):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', *args],
                          cwd=cwd or self.repo, check=True, capture_output=True, text=True).stdout.strip()


class ChangedPaths(ScratchRepo):
  """--base and --worktree in a scratch repository."""

  def setUp(self):
    super().setUp()
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
    h = self.hil('.claude/skills/hil-contract/scripts/hil_test.py')
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
    h = self.hil('ports/stm32f4/board_flash.c', 'ports/lpc55/boards.c', '.claude/skills/hil-contract/scripts/hil_test.py')
    self.assertEqual(h['boards'], ['lpcxpresso55s69'])
    self.assertEqual([u['target'] for u in h['uncovered']], ['stm32f4'])

  def test_a_build_gap_stays_uncovered_beside_a_runner_change(self):
    h = self.hil('ports/ch32v20x/board_flash.c', '.claude/skills/hil-contract/scripts/hil_test.py')
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
    rt_gap = {'target': 'apps/dfu_runtime/src/nonce.c on mimxrt10xx',
              'reason': f'no {self.config} Espressif board of mimxrt10xx runs dfu_runtime'}
    h = self.hil('apps/dfu_runtime/src/nonce.c')   # espressif and mimxrt10xx build it; only the S3 runs it
    self.assertEqual((h['boards'], h['uncovered']), (['espressif_esp32s3_devkitc_1'], [rt_gap]))
    h = self.hil('apps/dfu_runtime/src/nonce.c', 'src/main.c')   # the whole roster's battery still never runs it on RT
    self.assertEqual(h['boards'], ['espressif_esp32s3_devkitc_1', 'imxrt1060_evk'])
    self.assertIn(rt_gap, h['uncovered'])
    h = self.hil('ports/espressif/apps/dfu_runtime/main/board_dfu_runtime.c')
    self.assertEqual((h['boards'], h['uncovered']), (['espressif_esp32s3_devkitc_1'], []))
    h = self.hil('ports/mimxrt10xx/apps/dfu_runtime/board_dfu_runtime.c')
    self.assertEqual((h['boards'], [u['reason'] for u in h['uncovered']]),
                     ([], [f'no {self.config} Espressif board of mimxrt10xx runs dfu_runtime']))
    h = self.hil('apps/blinky/src/blinky.c', 'ports/espressif/apps/blinky/main/CMakeLists.txt')
    self.assertEqual((h['boards'], len(h['uncovered'])), ([], 2))
    self.roster.write_text(json.dumps({'boards': [{'name': 'imxrt1060_evk', 'flasher': {'name': 'jlink'}}]}))
    h = self.hil('apps/dfu_runtime/src/nonce.c')
    self.assertEqual((h['boards'], sorted(u['target'] for u in h['uncovered'])),
                     ([], ['apps/dfu_runtime/src/nonce.c on espressif', 'apps/dfu_runtime/src/nonce.c on mimxrt10xx']))

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
    self.assertEqual(sorted(cb.select([app])['boards']), [('metro_m7_1011', 'cmake')])   # its build is unchanged
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


class Identity(ScratchRepo):
  """A build record names each input it used and whether it has local changes; a dependency is a
  separate git checkout (a symlink in a worktree), so the parent's status cannot see its changes."""

  def setUp(self):
    super().setUp()
    self.pin = None
    for patch in (mock.patch.object(cb, 'ROOT', self.repo),
                  mock.patch.object(cb, 'get_deps_table', lambda: {'lib/mcu/dep': (self.pin, ['lpc55']),
                                                                   'lib/mcu/other': ('x', ['maxim'])})):
      patch.start()
      self.addCleanup(patch.stop)
    self.dep = self.repo / 'lib' / 'mcu' / 'dep'
    for repo in (self.repo, self.dep):
      repo.mkdir(parents=True, exist_ok=True)
      self.git('init', '-q', '-b', 'master', cwd=repo)
      (repo / 'x.c').write_text('x')
      self.git('add', 'x.c', cwd=repo)
      self.git('commit', '-q', '-m', 'init', cwd=repo)
    self.pin = self.git('rev-parse', 'HEAD', cwd=self.dep)

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
    self.git('checkout', '-q', '--', 'x.c', cwd=self.dep)
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
    self.assertTrue((self.build_dir / f'cmake-build-agent-{cb.os.getpid()}-lpcxpresso55s69-make').is_dir())

  def test_shared_root_is_rebuilt_from_clean_and_kept(self):
    self.args.shared = True
    root = self.build_dir / 'cmake-build-lpcxpresso55s69-make'
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
      {'name': 'stm32h563_nucleo', 'uid': 'S', 'flasher': {'name': 'stlink', 'uid': '0023ab', 'args': '-device stm32h563zi'}},
      {'name': 'lpcxpresso55s69', 'uid': 'L', 'flasher': {'name': 'openocd', 'uid': 'x', 'args': '-f a.cfg'}}]}))
    self.config = str(self.roster.relative_to(ROOT))

  def jlink_tree(self, root, script=None, options='-USB 000801012283 -ExitOnError 1 -NoGui 1', interface='swd'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'tinyuf2.jlink').write_text(script or f'halt\nloadfile {root / "tinyuf2.hex"}\nr\ngo\nexit')
    line = (f'cd {root} && JLinkExe -device MIMXRT1011DAE5A {options} -if {interface} -JTAGConf -1,-1 -speed auto '
            f'-CommandFile {root / "tinyuf2.jlink"}')
    return lambda d, args: subprocess.CompletedProcess(args, 0, f'arm-none-eabi-gcc ...\n{line}\n', '')

  def stlink_tree(self, root, connect='port=swd sn=0023ab', image=None, go='--go'):
    root.mkdir(parents=True, exist_ok=True)
    line = f'cd {root} && /home/u/bin/STM32_Programmer_CLI --connect {connect} --write {image or root / "tinyuf2.hex"} {go}'
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
    self.assertEqual(cb.roster_flasher(self.config, 'stm32h563_nucleo'),
                     ({'name': 'stlink', 'uid': '0023ab', 'device': 'stm32h563zi'}, ['STLINK_SERIAL=0023ab']))
    self.assertEqual(cb.roster_flasher(self.config, 'espressif_esp32s3_devkitc_1'),
                     ({'name': 'esptool', 'uid': 'b1', 'device': 'esp32s3'}, []))   # the tty is chosen at flash time
    for board, err in (('lpcxpresso55s69', 'no HIL flash target'), ('imxrt1060_evk', 'not on')):
      with self.subTest(board), self.assertRaisesRegex(cb.Fail, err):
        cb.roster_flasher(self.config, board)

  def test_a_route_binds_the_esptool_bindings_segments(self):
    p4 = 'espressif_p4_function_ev'
    route = {'name': 'openocd_esp', 'uid': '30:ED:A0:E0:C9:02', 'device': 'esp32p4'}
    self.assertEqual(cb.roster_routes('test/hil/local.json', p4), [route])
    self.assertEqual(cb.roster_routes('test/hil/local.json', 'metro_m7_1011'), [])
    inputs = list(cb.FLASH['esptool'][1])
    rec = {'board': p4, 'flash': {'flasher': {'name': 'esptool', 'uid': 'b', 'device': 'esp32p4'}, 'inputs': inputs}}
    self.assertEqual(cb.flash_routes(rec, [route]), {'openocd_esp': {'flasher': route, 'inputs': inputs}})
    with self.assertRaisesRegex(cb.Fail, 'needs the esptool binding of that chip'):
      cb.flash_routes(rec, [dict(route, device='esp32s3')])
    with tempfile.TemporaryDirectory() as d:
      for args in ('-f board/esp32p4-builtin.cfg -c init', '-f interface/esp_usb_jtag.cfg -f target/esp32p4.cfg'):
        cfg = Path(d) / 'r.json'
        cfg.write_text(json.dumps({'boards': [{'name': p4, 'tinyuf2': {'routes': [{'flasher': dict(route, args=args)}]}}]}))
        with self.subTest(args), self.assertRaisesRegex(cb.Fail, 'not the roster form'):
          cb.roster_routes(str(cfg), p4)

  def fake_tools(self, **env):
    """`ninja` and `docker` on PATH that log their argv; as the query, each prints ninja's dry run with a warning on
    stderr, or with HANG starts a grandchild, adds both pids to `self.pids` and hangs. `docker run` creates the
    container, CREATE_AFTER s later if set; `docker rm` removes it, or exits RM_EXIT; `docker ps` lists it."""
    tools = self.tmp / 'bin'
    tools.mkdir(exist_ok=True)
    for name in ('ninja', 'docker'):
      (tools / name).write_text(FAKE_TOOL.format(python=sys.executable))
      (tools / name).chmod(0o755)
    self.tools_log, self.pids = self.tmp / 'tools.log', self.tmp / 'pids'
    self.tools_log.unlink(missing_ok=True)
    (self.tmp / 'container').unlink(missing_ok=True)
    self.addCleanup(self.kill_hung)
    return mock.patch.dict(os.environ, {'PATH': f'{tools}:{os.environ["PATH"]}', 'TOOLS_LOG': str(self.tools_log),
                                        'PIDS': str(self.pids), **env})

  def hung(self):
    return [int(pid) for pid in self.pids.read_text().split()] if self.pids.exists() else []

  def kill_hung(self):
    for pid in self.hung():
      if alive(pid, wait=0):
        with contextlib.suppress(ProcessLookupError):   # it may exit between the check and the kill
          os.kill(pid, signal.SIGKILL)

  def tool_calls(self, tool):
    return [l.split()[1:] for l in self.tools_log.read_text().splitlines() if l.split()[0] == tool]

  def test_an_unbound_query_returns_ninja_stdout_alone_and_a_timeout_kills_it(self):
    root = self.tmp / 'b'
    with self.fake_tools():
      r = cb.ninja_in('cmake', None, None, root, ['-n', '-v'])
    self.assertEqual(r.stdout, "ninja: Entering directory `x'\n")   # the stderr warning is not in it
    self.assertEqual((r.returncode, r.stderr), (0, 'ninja: warning: on stderr\n'))
    with self.fake_tools(HANG='1'), mock.patch.object(cb, 'NINJA_QUERY_TIMEOUT', 0.5), \
         self.assertRaisesRegex(cb.Fail, '^' + re.escape(f'b: ninja -n -v timed out after {cb.NINJA_QUERY_TIMEOUT}s') + '$'):
      cb.ninja_in('cmake', None, None, root, ['-n', '-v'])
    self.assertFalse(alive(self.hung()[0]))
    self.assertEqual(self.tool_calls('docker'), [])

  def test_a_kill_of_check_builds_process_group_also_ends_its_query(self):
    # as `timeout` ends what it runs: the whole process group, which the query and what it starts never leave
    code = ('import importlib.util, sys; from pathlib import Path; '
            'spec = importlib.util.spec_from_file_location("check_build", sys.argv[1]); '
            'cb = importlib.util.module_from_spec(spec); spec.loader.exec_module(cb); '
            'cb.ninja_in("cmake", None, None, Path(sys.argv[2]), ["-n", "-v"])')
    with self.fake_tools(HANG='1'):
      outer = subprocess.Popen([sys.executable, '-c', code, str(SCRIPT), str(self.tmp / 'b')], cwd=ROOT,
                               start_new_session=True)
    end = time.monotonic() + 10
    while len(self.hung()) < 2 and time.monotonic() < end:
      time.sleep(0.05)
    os.killpg(outer.pid, signal.SIGKILL)
    outer.wait()
    self.assertEqual(len(self.hung()), 2)
    self.assertEqual([pid for pid in self.hung() if alive(pid)], [])

  def test_a_timed_out_idf_query_removes_its_named_container_or_names_the_one_left(self):
    root, name, bound = self.tmp / 'b', f'tinyuf2-query-{os.getpid()}-deadbeef', 0.5
    timed_out = re.escape(f'b: ninja -n -v timed out after {bound}s')
    cases = (('removed', {}, '$'), ('created after the kill', {'CREATE_AFTER': str(bound + 0.1)}, '$'),
             ('still listed', {'RM_EXIT': '1'}, re.escape(f'; container {name} still exists: docker rm -f {name}') + '$'))
    for what, env, tail in cases:
      with self.subTest(what), self.fake_tools(HANG='1', **env), mock.patch.object(cb, 'git', return_value=str(self.tmp)), \
           mock.patch.object(cb.uuid, 'uuid4', return_value=mock.Mock(hex='deadbeef')), \
           mock.patch.object(cb, 'NINJA_QUERY_TIMEOUT', bound), mock.patch.object(cb, 'CONTAINER_SETTLE', 1), \
           mock.patch.object(cb, 'CONTAINER_GONE_WAIT', 3), self.assertRaisesRegex(cb.Fail, '^' + timed_out + tail):
        try:
          cb.ninja_in('idf', 'docker', 'idf:image', root, ['-n', '-v'])
        finally:
          query = next(c for c in self.tool_calls('docker') if c[0] == 'run')
          self.assertEqual((query[query.index('--name') + 1], query[-6:]), (name, ['idf:image', 'ninja', '-C', str(root), '-n', '-v']))
          self.assertEqual([c for c in self.tool_calls('docker') if c[0] == 'rm'][0], ['rm', '-f', name])
          # absent once is not gone: a create pending at the kill lands later and is removed too
          end = time.monotonic() + 5
          while 'CREATE_AFTER' in env and 'daemon created' not in self.tools_log.read_text() and time.monotonic() < end:
            time.sleep(0.05)
          self.assertEqual((self.tmp / 'container').exists(), bool(env.get('RM_EXIT')))
    calls = []

    def no_docker(cmd, **k):   # the query times out, then docker is gone
      calls.append(cmd)
      raise subprocess.TimeoutExpired(cmd, bound) if len(calls) == 1 else FileNotFoundError('docker')
    with mock.patch.object(cb, 'git', return_value=str(self.tmp)), mock.patch.object(cb, 'NINJA_QUERY_TIMEOUT', bound), \
         mock.patch.object(cb.uuid, 'uuid4', return_value=mock.Mock(hex='deadbeef')), \
         mock.patch.object(cb.subprocess, 'run', no_docker), \
         self.assertRaisesRegex(cb.Fail, '^' + timed_out + re.escape(f'; docker failed (docker), so container {name} may be left')):
      cb.ninja_in('idf', 'docker', 'idf:image', root, ['-n', '-v'])

  def test_an_interrupted_idf_query_is_killed_and_its_container_removed_and_the_interruption_kept(self):
    root, name, communicate = self.tmp / 'b', f'tinyuf2-query-{os.getpid()}-deadbeef', subprocess.Popen.communicate
    for what, env, err in (('removed', {}, ''), ('still listed', {'RM_EXIT': '1'},
                                                 f'b: interrupted ninja -n -v; container {name} still exists: docker rm -f {name}\n')):
      interrupted = []

      def ctrl_c(p, *a, **k):   # the query's own communicate only: container_left's docker calls run as usual
        if not interrupted:
          interrupted.append(p.pid)
          raise KeyboardInterrupt
        return communicate(p, *a, **k)
      stderr = io.StringIO()
      with self.subTest(what), self.fake_tools(HANG='1', **env), mock.patch.object(cb, 'git', return_value=str(self.tmp)), \
           mock.patch.object(cb.uuid, 'uuid4', return_value=mock.Mock(hex='deadbeef')), \
           mock.patch.object(subprocess.Popen, 'communicate', ctrl_c), mock.patch.object(cb, 'CONTAINER_SETTLE', 0.2), \
           mock.patch.object(cb, 'CONTAINER_GONE_WAIT', 0.5), contextlib.redirect_stderr(stderr), \
           self.assertRaises(KeyboardInterrupt):
        (self.tmp / 'container').touch()   # created before the interruption
        cb.ninja_in('idf', 'docker', 'idf:image', root, ['-n', '-v'])
      self.assertEqual((stderr.getvalue(), (self.tmp / 'container').exists()), (err, bool(env)))
      self.assertIn(['rm', '-f', name], self.tool_calls('docker'))
      self.assertFalse(alive(interrupted[0]))

  def test_each_unbound_idf_query_gets_a_distinct_container_name(self):
    root = self.tmp / 'b'
    ids = [mock.Mock(hex='first'), mock.Mock(hex='second')]
    with self.fake_tools(), mock.patch.object(cb, 'git', return_value=str(self.tmp)), \
         mock.patch.object(cb.uuid, 'uuid4', side_effect=ids):
      cb.ninja_in('idf', 'docker', 'idf:image', root, ['-n', '-v'])
      cb.ninja_in('idf', 'docker', 'idf:image', root, ['-t', 'commands'])
    names = [c[c.index('--name') + 1] for c in self.tool_calls('docker') if c[0] == 'run']
    self.assertEqual(names, [f'tinyuf2-query-{os.getpid()}-first', f'tinyuf2-query-{os.getpid()}-second'])

  def test_an_unbound_idf_querys_container_is_named_for_the_pid_and_a_uuid4(self):   # as hil-contract documents it
    with self.fake_tools(), mock.patch.object(cb, 'git', return_value=str(self.tmp)):
      cb.ninja_in('idf', 'docker', 'idf:image', self.tmp / 'b', ['-n', '-v'])
    [name] = [c[c.index('--name') + 1] for c in self.tool_calls('docker') if c[0] == 'run']
    self.assertRegex(name, '^' + re.escape(f'tinyuf2-query-{os.getpid()}-') + '[0-9a-f]{32}$')

  def test_the_build_time_commands_query_reads_ninjas_stdout_and_reports_its_stderr(self):
    # a real query through the unbound ninja_in: a failure's diagnostic is on stderr only, a warning there is never
    # parsed as a command (#572 B1)
    flasher = {'name': 'jlink', 'uid': '000801012283', 'device': 'MIMXRT1011DAE5A'}
    root, query = self.tmp / 'b', functools.partial(cb.ninja_in, 'cmake', None, None)
    with self.fake_tools(UNKNOWN_TARGET='1'), \
         self.assertRaisesRegex(cb.Fail, re.escape("ninja: error: unknown target 'tinyuf2-jlink'")):
      cb.flash_binding(flasher, root, query)
    line = self.jlink_tree(root)(root, [])
    with self.fake_tools(STDOUT=line.stdout.strip()):
      self.assertEqual(cb.flash_binding(flasher, root, query)['command'], line.stdout.splitlines()[1])
    self.assertEqual(self.tool_calls('ninja'), [['-C', str(root), '-t', 'commands', 'tinyuf2-jlink']])

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

  def test_the_generated_stlink_target_must_name_the_roster_probe_and_the_build_hex(self):
    flasher = {'name': 'stlink', 'uid': '0023ab', 'device': 'stm32h563zi'}
    root = self.tmp / 's'
    out = cb.flash_binding(flasher, root, self.stlink_tree(root))
    self.assertEqual((out['target'], out['inputs']), ('tinyuf2-stlink', ['tinyuf2.hex']))
    for what, tree in (('no probe serial', dict(connect='port=swd')),
                       ('another probe', dict(connect='port=swd sn=1')),
                       ('another connect mode', dict(connect='port=swd sn=0023ab mode=UR')),
                       ('the ELF', dict(image=root / 'tinyuf2.elf')),
                       ('another image', dict(image=self.tmp / 'other.hex')),
                       ('no start', dict(go='')),
                       ('a second write', dict(go=f'--go --write {self.tmp / "o.hex"}'))):
      with self.subTest(what), self.assertRaisesRegex(cb.Fail, 'does not flash'):
        cb.flash_binding(flasher, root, self.stlink_tree(root, **tree))

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
  def fake_selftest(cmd, log, verbose, cwd=None):
    """Configure passes; the selftest target leaves build files and fails its comparison."""
    root = Path(cmd[cmd.index('-B') + 1] if '-B' in cmd else cmd[cmd.index('--build') + 1])
    (root / 'CMakeFiles').mkdir(exist_ok=True)
    (root / 'tinyuf2').write_text('x')
    if 'selftest' in cmd:
      log.write_text('comparing against known good disk image\nFAIL: (-10) FILES_NOT_IDENTICAL\n')
      return 1
    return 0

  def test_a_failed_comparison_fails_and_keeps_only_the_log(self):
    with build_tmpdir() as tmp, mock.patch.object(cb, 'BUILD_DIR', Path(tmp)), \
         mock.patch.object(cb, 'boards_of', lambda port: ['4k']), \
         mock.patch.object(cb, 'run', self.fake_selftest):
      [rec] = cb.run_ghostfat(False)
      root = Path(tmp) / f'cmake-build-agent-{cb.os.getpid()}-ghostfat-4k'
      self.assertEqual((rec['status'], rec['firstError']), ('failed', 'FAIL: (-10) FILES_NOT_IDENTICAL'))
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
    # mimxrt10xx copies its self-update image to ARTIFACT_PATH instead of building apps/self_update;
    # its board-conditional apps are expected on their boards only
    rt = {'_bin/tinyuf2.bin', '_bin/tinyuf2.hex', '_bin/apps/update-tinyuf2.uf2', '_bin/apps/blinky.uf2',
          '_bin/apps/erase_firmware.uf2', '_bin/apps/dfu_runtime.uf2'}
    self.assertEqual(names('mimxrt10xx', 'metro_m7_1011', 'cmake'),
                     rt | {'_bin/apps/esp32programmer.uf2', '_bin/apps/factory_test.uf2'})
    self.assertEqual(names('mimxrt10xx', 'metro_m7_1011_sd', 'cmake'), rt | {'_bin/apps/factory_test_metro_sd.uf2'})
    self.assertEqual(names('mimxrt10xx', 'imxrt1060_evk', 'cmake'), rt)
    self.assertEqual(names('stm32f3', 'stm32f303disco', 'cmake'),
                     {'_bin/tinyuf2.bin', '_bin/tinyuf2.hex', '_bin/apps/update-tinyuf2.uf2', '_bin/apps/blinky.uf2'})


class FirstError(unittest.TestCase):
  def test_compiler_diagnostic_beats_ninjas_failed_line(self):
    log = 'FAILED: CMakeFiles/tinyuf2.dir/src/main.c.obj\n/x/src/main.c:12:3: error: unknown type name\n'
    self.assertEqual(cb.first_error(log), '/x/src/main.c:12:3: error: unknown type name')

  def test_cmake_error_is_reported_with_its_message(self):
    log = ('[736/1124] Building C object esp-idf/mbedtls/mbedtls/library/CMakeFiles/mbedx509.dir/error.c.obj\n'
           'FAILED: bootloader-prefix/src/bootloader-stamp/bootloader-configure\n'
           'CMake Error at /opt/esp/idf/tools/cmake/build.cmake:380 (message):\n'
           '\n'
           "  Failed to resolve component 'usb' required by component 'main'\n"
           'Call Stack (most recent call first):\n')
    self.assertEqual(cb.first_error(log), 'CMake Error at /opt/esp/idf/tools/cmake/build.cmake:380 (message): '
                                          "Failed to resolve component 'usb' required by component 'main'")

  def test_cmake_error_with_its_message_on_the_line(self):
    log = 'CMake Error: The source directory "/x" does not exist.\n  next\n'
    self.assertEqual(cb.first_error(log), 'CMake Error: The source directory "/x" does not exist.')

  def test_cmake_error_in_form_takes_its_message(self):
    log = 'CMake Error in main/CMakeLists.txt:\n  Target "x" links to itself.\n'
    self.assertEqual(cb.first_error(log), 'CMake Error in main/CMakeLists.txt: Target "x" links to itself.')

  def test_cmake_error_header_takes_no_indented_line_after_a_progress_line(self):
    log = 'CMake Error at CMakeLists.txt:3 (message):\n[2/3] Running another command\n  unrelated output\n'
    self.assertEqual(cb.first_error(log), 'CMake Error at CMakeLists.txt:3 (message):')

  def test_cmake_error_header_takes_no_unindented_line(self):
    log = 'CMake Error at CMakeLists.txt:3 (message):\nninja: build stopped: subcommand failed.\n'
    self.assertEqual(cb.first_error(log), 'CMake Error at CMakeLists.txt:3 (message):')

  def test_cmake_error_with_continuation_is_capped(self):
    log = 'CMake Error at CMakeLists.txt:3 (message):\n  ' + 'x' * 500 + '\n'
    self.assertEqual(len(cb.first_error(log)), 400)

  def test_fallback_skips_progress_lines(self):
    log = '[5/9] Building C object x/error.c.obj\nninja: error: loading build.ninja\n'
    self.assertEqual(cb.first_error(log), 'ninja: error: loading build.ninja')

  def test_a_failed_script_test_is_named_with_its_exception_line(self):
    """From unittest's own report: a multi-line assertion message, a chained exception, and a docstring that unittest
    prints under the test's id."""
    with tempfile.TemporaryDirectory() as tmp:
      Path(tmp, 'test_contract.py').write_text(
        'import unittest\n'
        'class Contract(unittest.TestCase):\n'
        '  def test_diff(self):\n'
        '    self.assertEqual({"a": 1, "b": [1, 2]}, {"a": 2, "b": [1, 3]})\n'
        '  def test_chained(self):\n'
        '    try:\n'
        '      {}["k"]\n'
        '    except KeyError as e:\n'
        '      raise RuntimeError("wrapped") from e\n'
        '  def test_documented(self):\n'
        '    """A docstring line."""\n'
        '    self.fail("documented")\n')
      for test, verdict, exc in (
          ('test_diff', 'FAIL', "AssertionError: {'a': 1, 'b': [1, 2]} != {'a': 2, 'b': [1, 3]}"),
          ('test_chained', 'ERROR', 'RuntimeError: wrapped'),
          ('test_documented', 'FAIL', 'AssertionError: documented')):
        with self.subTest(test):
          real = subprocess.run([sys.executable, '-m', 'unittest', f'test_contract.Contract.{test}'],
                                capture_output=True, text=True, cwd=tmp)
          with mock.patch.object(cb.subprocess, 'run', return_value=real):
            rec = cb.run_tests()
          self.assertEqual(rec['status'], 'failed')
          pattern = rf'^{verdict}: {test} \(test_contract\.Contract[^)]*\): {re.escape(exc)}$'
          self.assertRegex(rec['firstError'], pattern)


if __name__ == '__main__':
  unittest.main()
