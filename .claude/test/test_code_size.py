"""The code-size launcher and TinyUF2's profile for agentrc's engine (the engine's own tests are
agentrc's): the pin check, what is sized, how each tree builds through its own check_build.py, and
the base worktree's submodules. Builds and git are stubbed; a size is evidence only from a run of
the launcher itself."""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.claude' / 'skills' / 'build' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(1, str(ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'))
import check_build  # noqa: E402
import code_size  # noqa: E402
import code_size_profile as prof  # noqa: E402


def done(rc=0, stdout='', stderr=''):
  return subprocess.CompletedProcess([], rc, stdout, stderr)


class Launcher(unittest.TestCase):
  def test_an_agentrc_off_its_pin_refuses_before_anything_runs(self):
    with mock.patch.object(check_build, 'check_agentrc_pin', side_effect=check_build.Fail('lib/agentrc is at x')), \
         mock.patch.object(code_size.hil_run_report, 'load_agentrc') as load, \
         contextlib.redirect_stderr(io.StringIO()) as err:
      self.assertEqual(code_size.main(['report', '-b', 'swan_r5']), 2)
    load.assert_not_called()
    self.assertIn('refused: lib/agentrc is at x', err.getvalue())

  def test_the_engine_is_lib_agentrcs(self):
    engine = mock.Mock()
    with mock.patch.object(check_build, 'check_agentrc_pin'), \
         mock.patch.object(code_size.hil_run_report, 'load_agentrc', return_value=engine) as load:
      code_size.main(['report', '-b', 'swan_r5'])
    load.assert_called_once_with(ROOT / 'lib' / 'agentrc' / 'skills' / 'code-size' / 'scripts' / 'code_size.py',
                                 'agentrc_code_size')
    engine.main.assert_called_once_with(prof, ['report', '-b', 'swan_r5'])


# check() leaves the sized boards behind for prepare_base(): each test starts and ends without them
NO_SIZED_BOARDS = mock.patch.object(prof, '_boards', None)


@NO_SIZED_BOARDS
class Profile(unittest.TestCase):
  def test_examples_and_unknown_boards_are_refused(self):
    self.assertEqual(prof.check('report', ['swan_r5'], [], None, False), [])
    errors = prof.check('diff', ['no_such_board'], ['device/x'], 'a' * 40, True)
    self.assertIn('TinyUF2 has no examples: -b sizes a board\'s bootloader', errors)
    self.assertTrue(any('no_such_board' in e for e in errors), errors)

  def test_the_sized_elf_is_the_bootloaders(self):
    with tempfile.TemporaryDirectory() as tmp:
      for rel in ('tinyuf2.elf', 'ports/stm32h7/tinyuf2-daisy_seed.elf',
                  'ports/stm32h7/apps/erase_firmware/erase_firmware-daisy_seed.elf', 'apps/blinky/blinky.elf'):
        (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(tmp) / rel).write_text('')
      self.assertEqual(sorted(os.path.relpath(e, tmp) for e in prof.elfs(tmp, None)),
                       ['ports/stm32h7/tinyuf2-daisy_seed.elf', 'tinyuf2.elf'])

  def test_the_filters_are_the_checkouts_src_and_ports(self):
    with mock.patch.object(prof, 'engine', mock.Mock(filter_arg=lambda p: p)):
      self.assertEqual(prof.filters('/c'), [os.path.realpath('/c/src') + os.sep, os.path.realpath('/c/ports') + os.sep])

  def test_the_first_error_is_the_contracts(self):
    self.assertEqual(prof.first_error('make: *** [x] Error 2\nlog: /b/check_build.log\n'), 'make: *** [x] Error 2')
    self.assertIsNone(prof.first_error(''))


class Build(unittest.TestCase):
  def _tree(self, tmp, has_build_dir):
    src = Path(tmp) / 'src'
    (src / prof.CHECK_BUILD).parent.mkdir(parents=True)
    (src / prof.CHECK_BUILD).write_text('--build-dir' if has_build_dir else 'an older contract')
    build = Path(tmp) / 'out' / 'build'
    build.mkdir(parents=True)
    return str(src), str(build)

  def _build(self, src, build, result, rc=0):
    run = mock.Mock(return_value=done(rc, 'building\n' + json.dumps(result) + '\n'))
    with mock.patch.object(prof, 'engine', mock.Mock(run=run)), mock.patch.object(prof.shutil, 'which', return_value=None):
      return prof.build(src, build, 'swan_r5', None), run.call_args.args[0]

  def test_a_tree_with_build_dir_builds_into_the_engines_dir(self):
    with tempfile.TemporaryDirectory() as tmp:
      src, build = self._tree(tmp, True)
      ret, cmd = self._build(src, build, {'pass': True})
    self.assertIsNone(ret)
    self.assertEqual(cmd, [sys.executable, os.path.join(src, prof.CHECK_BUILD), '--board', 'swan_r5',
                           '--build-dir', build])

  def test_an_older_base_builds_shared_in_its_worktree_and_is_moved_where_the_engine_sizes(self):
    with tempfile.TemporaryDirectory() as tmp:
      src, build = self._tree(tmp, False)
      shared = Path(src) / 'cmake-build' / 'cmake-build-swan_r5'
      (shared / 'ports' / 'stm32l4').mkdir(parents=True)
      (shared / 'ports' / 'stm32l4' / 'tinyuf2-swan_r5.elf').write_text('elf')
      ret, cmd = self._build(src, build, {'pass': True, 'boards': [{'buildDir': 'cmake-build/cmake-build-swan_r5'}]})
      self.assertIsNone(ret)
      self.assertEqual(cmd[-1], '--shared')
      self.assertTrue((Path(build) / 'ports' / 'stm32l4' / 'tinyuf2-swan_r5.elf').is_file())
      self.assertFalse(shared.exists())

  def test_a_failure_leads_with_the_contracts_first_error_and_names_its_log(self):
    with tempfile.TemporaryDirectory() as tmp:
      src, build = self._tree(tmp, True)
      ret, _ = self._build(src, build, {'pass': False, 'firstError': 'main.c:1: error: x',
                                        'boards': [{'log': 'cmake-build/b/check_build.log'}]}, rc=1)
    self.assertEqual(ret.returncode, 1)
    self.assertEqual(ret.stdout.splitlines(), ['main.c:1: error: x',
                                               f'log: {os.path.join(src, "cmake-build/b/check_build.log")}'])
    self.assertEqual(prof.first_error(ret.stdout), 'main.c:1: error: x')

  def test_an_exported_idf_builds_both_trees_locally(self):
    with tempfile.TemporaryDirectory() as tmp:
      src, build = self._tree(tmp, True)
      run = mock.Mock(return_value=done(0, json.dumps({'pass': True})))
      with mock.patch.object(prof, 'engine', mock.Mock(run=run)), \
           mock.patch.object(prof.shutil, 'which', return_value='/idf/idf.py'):
        prof.build(src, build, 'espressif_esp32s3_devkitm_1', None)
    self.assertIn('--idf', run.call_args.args[0])
    self.assertEqual(run.call_args.args[0][run.call_args.args[0].index('--idf') + 1], 'local')


class BaseInUse(Exception):
  pass


class DockerContainment(unittest.TestCase):
  def _build(self, outcome, idf=None, listings=('c1\nc2\n',), ps_rc=0, base=False):
    """build() of an ESP board, of the checkout or with `base` another tree, through a stubbed run(): check_build's
    `outcome`, then each `docker ps` lists the next of `listings`, then nothing. (result or exception, docker calls
    with their timeouts, the mount looked up)"""
    calls, listed = [], iter(listings)

    def run(cmd, timeout=None):
      if cmd[0] == 'docker':
        calls.append((cmd, timeout))
        return done(ps_rc, next(listed, '')) if cmd[1] == 'ps' else done()
      if isinstance(outcome, BaseException):
        raise outcome
      return outcome
    with tempfile.TemporaryDirectory() as tmp:
      tree = Path(tmp) / 'src'
      (tree / prof.CHECK_BUILD).parent.mkdir(parents=True, exist_ok=True)
      (tree / prof.CHECK_BUILD).write_text('--build-dir')
      build = Path(tmp) / 'out' / 'swan_r5' / 'build'
      with mock.patch.object(prof, 'engine', mock.Mock(run=run, BaseInUse=BaseInUse)), \
           mock.patch.object(prof, 'ROOT', '/the/checkout' if base else str(tree)), \
           mock.patch.object(prof.shutil, 'which', side_effect=lambda t: {'docker': '/bin/docker', 'idf.py': idf}[t]), \
           mock.patch.object(check_build, 'CONTAINER_SETTLE', 0.05), mock.patch.object(check_build, 'CONTAINER_GONE_WAIT', 0.3):
        try:
          ret = prof.build(str(tree), str(build), 'espressif_esp32s3_devkitm_1', None)
        except BaseException as e:
          ret = e
      return ret, calls, os.path.dirname(os.path.realpath(build))

  def test_a_timed_out_docker_build_has_its_containers_removed_and_leads_with_the_timeout(self):
    ret, docker, mount = self._build(done(124, '', 'Command timed out after 1800s: python3 check_build.py'))
    t = check_build.DOCKER_TIMEOUT
    self.assertEqual(docker[:3], [(['docker', 'ps', '-aq', '--filter', f'volume={mount}'], t),
                                  (['docker', 'rm', '-f', 'c1', 'c2'], t),
                                  (['docker', 'ps', '-aq', '--filter', f'volume={mount}'], t)])
    self.assertEqual((ret.returncode, ret.stdout, ret.stderr),
                     (124, 'Command timed out after 1800s: python3 check_build.py\n', ''))

  def test_an_interrupted_docker_build_has_its_containers_removed_and_stops(self):
    ret, docker, _ = self._build(KeyboardInterrupt())
    self.assertIsInstance(ret, KeyboardInterrupt)
    self.assertEqual(docker[1][0], ['docker', 'rm', '-f', 'c1', 'c2'])

  def test_containers_that_stay_listed_keep_the_base_and_are_named_for_the_current_tree(self):
    ret, _, mount = self._build(done(124, '', 'Command timed out'), listings=('c1\n',) * 1000)
    self.assertIn(f'a container mounting {mount} may be left', ret.stdout)
    ret, _, mount = self._build(done(124, '', 'Command timed out'), listings=('c1\n',) * 1000, base=True)
    self.assertIsInstance(ret, BaseInUse)
    self.assertEqual(str(ret), f'a container mounting {mount} may be left: docker ps -a --filter volume={mount}')

  def test_a_cleanup_cut_short_keeps_the_base_and_stops_the_current_tree(self):
    for error in (OSError(24, 'Too many open files'), KeyboardInterrupt()):
      for base in (True, False):
        with self.subTest(error=error, base=base), mock.patch.object(prof, '_remove_containers', side_effect=error):
          ret, _, mount = self._build(done(124, '', 'Command timed out'), base=base)
          if base:
            self.assertIsInstance(ret, BaseInUse)
            self.assertIs(ret.__cause__, error)
            self.assertIn(f'cut short ({error!r}), so a container mounting {mount} may be left', str(ret))
          else:
            self.assertIs(ret, error)

  def test_a_failed_docker_ps_is_named(self):
    ret, _, mount = self._build(done(124, '', 'Command timed out'), ps_rc=1)
    self.assertIn(f'docker ps failed, so a container mounting {mount} may be left', ret.stdout)

  def test_a_finished_or_local_idf_build_touches_no_container(self):
    for outcome, idf in ((done(1, json.dumps({'pass': False, 'error': 'x'})), None),
                         (done(124, '', 'Command timed out'), '/idf/idf.py')):
      with self.subTest(idf=idf):
        _ret, docker, _ = self._build(outcome, idf)
        self.assertEqual(docker, [])


@NO_SIZED_BOARDS
class PrepareBase(unittest.TestCase):
  def test_each_submodule_is_checked_out_at_the_bases_pin_borrowing_its_objects_and_its_get_deps_rows_are_linked(self):
    with tempfile.TemporaryDirectory() as main, tempfile.TemporaryDirectory() as wt:
      (Path(wt) / 'tools').mkdir()
      (Path(wt) / 'tools' / 'get_deps.py').write_text("deps_all = {'lib/mcu/st': ['u', 'p', 'f'], 'lib/absent': ['u', 'p', 'f']}\n")
      pins = {f'HEAD:{rel}': f'{n}' * 40 for n, rel in enumerate(check_build.SUBMODULES, 1)}
      engine = mock.Mock()
      with mock.patch.object(prof.subprocess, 'run',
                             side_effect=lambda cmd, **_k: done(0, pins[cmd[-1]] + '\n')), \
           mock.patch.object(prof, '_dep_checkout', side_effect=lambda src: (src + '/.git', 'f' * 40)), \
           mock.patch.object(prof, '_checkout_borrowing') as borrow, \
           mock.patch.object(prof, 'engine', engine):
        prof.prepare_base(main, wt)
    engine.link_deps.assert_called_once_with(main, wt, ['lib/mcu/st', 'lib/absent'])
    self.assertEqual([c.args for c in borrow.call_args_list],
                     [(os.path.join(main, rel) + '/.git', os.path.join(wt, rel), f'{n}' * 40, rel, os.path.join(main, rel))
                      for n, rel in enumerate(check_build.SUBMODULES, 1)])

  def test_a_base_needing_shared_is_refused_without_posix_locks(self):
    for text, refused in (('an older contract', True), ('--build-dir', False)):
      with self.subTest(refused=refused), tempfile.TemporaryDirectory() as wt:
        (Path(wt) / prof.CHECK_BUILD).parent.mkdir(parents=True)
        (Path(wt) / prof.CHECK_BUILD).write_text(text)
        stop = SystemExit('cloned')
        with mock.patch.object(check_build, 'fcntl', None), \
             mock.patch.object(prof.subprocess, 'run', side_effect=stop), \
             self.assertRaisesRegex(SystemExit, '--shared build needs a POSIX lock' if refused else 'cloned'):
          prof.prepare_base('/main', wt)

  def test_a_submodule_that_is_no_checkout_names_its_init(self):
    with tempfile.TemporaryDirectory() as main, tempfile.TemporaryDirectory() as wt:
      with mock.patch.object(prof.subprocess, 'run', return_value=done(0, 'a' * 40)), \
           mock.patch.object(prof, '_dep_checkout', return_value=None), \
           self.assertRaisesRegex(SystemExit, r'pins lib/tinyusb at aaaaaaaaaa.*git submodule update --init lib/tinyusb'):
        prof.prepare_base(main, wt)


GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=m']


def git(*args):
  return subprocess.run([*GIT, *args], capture_output=True, text=True, check=True).stdout.strip()


@NO_SIZED_BOARDS
class PrepareBaseDeps(unittest.TestCase):
  """prepare_base() on real git: get_deps.py's dependencies are --depth 1 fetches with no refs. Every GIT_* variable
  is dropped first: under pre-commit they point at the real checkout, and git would act on it."""

  def setUp(self):
    env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, clear=True)
    env.start()
    self.addCleanup(env.stop)
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.tmp = Path(tmp.name)
    up = self.tmp / 'up'
    git('init', '-q', str(up))
    git('-C', str(up), 'config', 'uploadpack.allowAnySHA1InWant', 'true')
    self.commits = []
    for n in ('old', 'new'):
      (up / 'hal.c').write_text(n)
      git('-C', str(up), 'add', 'hal.c')
      git('-C', str(up), 'commit', '-q', '-m', n)
      self.commits.append(git('-C', str(up), 'rev-parse', 'HEAD'))
    self.old, self.new = self.commits
    # the primary checkout's dependency, symlinked into this one as a worktree's are
    self.dep = self.tmp / 'primary' / 'lib' / 'mcu' / 'hal'
    self.dep.mkdir(parents=True)
    git('-C', str(self.dep), 'init', '-q')
    git('-C', str(self.dep), 'remote', 'add', 'origin', up.as_uri())
    self.fetch(self.new)
    git('-C', str(self.dep), 'checkout', '-q', 'FETCH_HEAD')
    self.main = self.tmp / 'main'
    (self.main / 'lib' / 'mcu').mkdir(parents=True)
    (self.main / 'lib' / 'mcu' / 'hal').symlink_to(self.dep)
    self.wt = self.tmp / 'wt'
    (self.wt / 'tools').mkdir(parents=True)

  def fetch(self, sha):
    git('-C', str(self.dep), 'fetch', '-q', '--depth', '1', 'origin', sha)

  def prepare(self, pin, extra=''):
    (self.wt / 'tools' / 'get_deps.py').write_text(
      f"deps_all = {{'lib/mcu/hal': ['u', '{pin}', 'stm32f4'], 'lib/plain': ['u', '{'0' * 40}', 'stm32f4']}}\n"
      + extra)
    engine = mock.Mock(run=lambda cmd, timeout=None: subprocess.run(cmd, capture_output=True, text=True))
    with mock.patch.object(prof, 'engine', engine):
      prof.prepare_base(str(self.main), str(self.wt))
    return engine.link_deps.call_args.args[2]

  def test_a_clean_dependency_at_the_bases_pin_and_an_absent_one_are_linked(self):
    self.assertEqual(self.prepare(self.new), ['lib/mcu/hal', 'lib/plain'])
    self.assertFalse((self.wt / 'lib').exists())

  def test_a_dirty_dependency_at_the_bases_pin_is_checked_out_clean(self):
    for name, text in (('hal.c', 'current-only change'), ('new.c', 'untracked')):
      with self.subTest(name=name):
        (self.dep / name).write_text(text)
        self.assertEqual(self.prepare(self.new), ['lib/plain'])
        hal = self.wt / 'lib' / 'mcu' / 'hal'
        self.assertFalse(hal.is_symlink())
        self.assertEqual(((hal / 'hal.c').read_text(), (hal / 'new.c').exists()), ('new', False))
        self.assertEqual((self.dep / name).read_text(), text)
        git('-C', str(self.dep), 'checkout', '-q', '--', 'hal.c')

  def test_an_untracked_file_hidden_by_status_config_still_counts_as_dirty(self):
    git('-C', str(self.dep), 'config', 'status.showUntrackedFiles', 'no')
    (self.dep / 'new.c').write_text('untracked')
    self.assertEqual(self.prepare(self.new), ['lib/plain'])
    hal = self.wt / 'lib' / 'mcu' / 'hal'
    self.assertFalse(hal.is_symlink())
    self.assertEqual(((hal / 'hal.c').read_text(), (hal / 'new.c').exists()), ('new', False))

  def test_a_dependency_that_is_no_checkout_is_refused_naming_its_fetch(self):
    (self.main / 'lib' / 'plain').mkdir()
    with self.assertRaisesRegex(SystemExit, re.escape(f"{self.main / 'lib' / 'plain'} is no git checkout") +
                                r'.*python3 tools/get_deps\.py stm32f4'):
      self.prepare(self.new)

  def test_a_dependency_the_base_pins_elsewhere_is_checked_out_at_the_bases_pin(self):
    self.fetch(self.old)
    self.assertEqual(self.prepare(self.old), ['lib/plain'])
    hal = self.wt / 'lib' / 'mcu' / 'hal'
    self.assertFalse(hal.is_symlink())
    self.assertEqual((hal / 'hal.c').read_text(), 'old')
    self.assertEqual(git('-C', str(hal), 'rev-parse', 'HEAD'), self.old)
    self.assertEqual(git('-C', str(hal), 'status', '--porcelain'), '')
    self.assertEqual((git('-C', str(self.dep), 'rev-parse', 'HEAD'), (self.dep / 'hal.c').read_text()), (self.new, 'new'))
    self.assertFalse((self.dep / '.git' / 'objects' / 'info' / 'alternates').exists())

  def test_a_reused_bases_link_is_replaced_not_written_through(self):
    self.fetch(self.old)
    (self.wt / 'lib' / 'mcu').mkdir(parents=True)
    (self.wt / 'lib' / 'mcu' / 'hal').symlink_to(self.dep)
    self.prepare(self.old)
    self.assertEqual((self.wt / 'lib' / 'mcu' / 'hal' / 'hal.c').read_text(), 'old')
    self.assertEqual((git('-C', str(self.dep), 'rev-parse', 'HEAD'), (self.dep / 'hal.c').read_text()), (self.new, 'new'))

  def test_only_the_dependencies_of_the_bases_ports_of_the_sized_boards_and_mandatory_ones_are_checked(self):
    self.assertEqual(prof.check('diff', ['feather_stm32f405_express'], [], None, True), [])
    (self.wt / 'ports' / 'stm32f4' / 'boards' / 'feather_stm32f405_express').mkdir(parents=True)
    for rel in ('lib/other', 'lib/must'):
      (self.main / rel).mkdir()
    rows = "{'lib/other': ['u', '%s', 'maxim'], 'lib/must': ['u', '%s', '']}" % ('1' * 40, '2' * 40)
    self.assertEqual(self.prepare(self.new, f"deps_all.update({rows})\n"),
                     ['lib/mcu/hal', 'lib/plain', 'lib/other', 'lib/must'])
    with self.assertRaisesRegex(SystemExit, re.escape(f"{self.main / 'lib' / 'must'} is no git checkout")):
      self.prepare(self.new, f"deps_all.update({rows})\ndeps_mandatory = {{'lib/must': deps_all['lib/must']}}\n")
    # the base keeps the board in a port the head has renamed: the base's port is the one whose dependencies count
    (self.wt / 'ports' / 'stm32f4').rename(self.wt / 'ports' / 'maxim')
    with self.assertRaisesRegex(SystemExit, re.escape(f"{self.main / 'lib' / 'other'} is no git checkout")):
      self.prepare(self.new, f"deps_all.update({rows})\n")

  def test_a_pin_this_checkout_has_not_fetched_names_the_fetch(self):
    with self.assertRaisesRegex(SystemExit, rf'pins lib/mcu/hal at {self.old[:10]}.*'
                                            rf'git -C lib/mcu/hal fetch --depth 1 origin {self.old}'):
      self.prepare(self.old)

  def test_a_pin_a_full_clone_has_not_fetched_names_a_fetch_that_keeps_it_full(self):
    git('-C', str(self.dep), 'fetch', '-q', '--unshallow', 'origin')
    up = self.tmp / 'up'
    (up / 'hal.c').write_text('newer')
    git('-C', str(up), 'commit', '-q', '-am', 'newer')
    newer = git('-C', str(up), 'rev-parse', 'HEAD')
    fetch = rf'git -C lib/mcu/hal fetch origin {newer}'
    with self.assertRaisesRegex(SystemExit, rf'pins lib/mcu/hal at {newer[:10]}.*\({fetch}\)'):
      self.prepare(newer)
    git('-C', str(self.dep), *fetch.split()[3:])
    self.assertEqual(git('-C', str(self.dep), 'rev-parse', '--is-shallow-repository'), 'false')
    self.assertEqual(self.prepare(newer), ['lib/plain'])


@NO_SIZED_BOARDS
class PrepareBaseSubmodules(unittest.TestCase):
  """prepare_base() on real git: a --depth 1 submodule, whose git dir is the superproject's, given the base's pin by a
  fetch by SHA that no ref reaches, which a clone --shared of it would miss. GIT_* variables dropped as above."""

  def setUp(self):
    env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, clear=True)
    env.start()
    self.addCleanup(env.stop)
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.tmp = Path(tmp.name)
    up = self.tmp / 'up'
    git('init', '-q', str(up))
    git('-C', str(up), 'config', 'uploadpack.allowAnySHA1InWant', 'true')
    for n in ('old', 'new'):
      (up / 'tusb.c').write_text(n)
      git('-C', str(up), 'add', 'tusb.c')
      git('-C', str(up), 'commit', '-q', '-m', n)
    self.old, self.new = git('-C', str(up), 'rev-parse', 'HEAD~1', 'HEAD').split()
    self.main = self.tmp / 'main'
    git('init', '-q', str(self.main))
    git('-C', str(self.main), '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', '--depth', '1',
        up.as_uri(), 'lib/tinyusb')
    self.sub = self.main / 'lib' / 'tinyusb'
    (self.main / 'tools').mkdir()
    (self.main / 'tools' / 'get_deps.py').write_text('deps_all = {}\n')
    git('-C', str(self.main), 'add', 'tools/get_deps.py')
    git('-C', str(self.main), 'update-index', '--cacheinfo', f'160000,{self.old},lib/tinyusb')
    git('-C', str(self.main), 'commit', '-q', '-m', 'base')
    self.wt = self.tmp / 'wt'
    git('-C', str(self.main), 'worktree', 'add', '-q', '--detach', str(self.wt), 'HEAD')

  def prepare(self):
    engine = mock.Mock(run=lambda cmd, timeout=None: subprocess.run(cmd, capture_output=True, text=True))
    with mock.patch.object(prof, 'engine', engine):
      prof.prepare_base(str(self.main), str(self.wt))

  def test_a_shallow_submodule_gives_the_bases_pin_it_fetched_by_sha(self):
    git('-C', str(self.sub), 'fetch', '-q', '--depth', '1', 'origin', self.old)
    self.assertEqual(git('-C', str(self.sub), 'rev-parse', '--is-shallow-repository'), 'true')
    self.prepare()
    tusb = self.wt / 'lib' / 'tinyusb'
    self.assertEqual((git('-C', str(tusb), 'rev-parse', 'HEAD'), (tusb / 'tusb.c').read_text()), (self.old, 'old'))
    self.assertEqual(git('-C', str(tusb), 'status', '--porcelain'), '')
    self.assertEqual((git('-C', str(self.sub), 'rev-parse', 'HEAD'), (self.sub / 'tusb.c').read_text()), (self.new, 'new'))

  def test_the_bases_submodule_status_names_the_sources_tag(self):
    git('-C', str(self.sub), 'fetch', '-q', '--depth', '1', 'origin', self.old)
    git('-C', str(self.sub), '-c', 'tag.gpgsign=false', 'tag', '-a', '-m', 'v1', 'v1', self.old)
    self.prepare()
    # the build embeds `git submodule status`, whose describe needs the source's tags
    self.assertEqual(git('-C', str(self.wt), 'submodule', 'status', 'lib/tinyusb'), f'{self.old} lib/tinyusb (v1)')

  def test_a_pin_the_submodule_has_not_fetched_names_the_fetch(self):
    with self.assertRaisesRegex(SystemExit, rf'pins lib/tinyusb at {self.old[:10]}.*'
                                            rf'git -C lib/tinyusb fetch --depth 1 origin {self.old}'):
      self.prepare()


if __name__ == '__main__':
  unittest.main()
