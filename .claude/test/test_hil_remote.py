#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The remote adapter (hil_remote.py) and its rig-side driver (hil_remote_driver.py) over agentrc's remote core, on a
# local "rig": the core's own fake ssh and rsync (lib/agentrc tests/test_hil_remote_core.py) run every remote command
# here under a clean environment, so the attempt, the detached launch, the driver's rebuild of the checkout from git
# bundles, hil_ci.py's build record and battery launch and the copy-back all run for real. The project is a temp
# superproject in a relocated worktree with real submodules, an unpushed candidate lib/agentrc pin and a shallow
# get_deps dependency; its check_build.py and hil_test.py are stand-ins, or the real runner with only admission and
# the probe steps stubbed. Plumbing only: a real ssh session's end and the rig are proved by a run on ci.lan.
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import hil_remote as hr  # noqa: E402
import hil_remote_driver as drv  # noqa: E402
import hil_test as ht  # noqa: E402

CHECK_PIN = hr.check_pin   # before Project patches it
hr.provider()   # the tests' own core: main() checks the pin before it loads one


def load_core_tests():
  spec = importlib.util.spec_from_file_location('agentrc_test_hil_remote_core',
                                                ROOT / 'lib' / 'agentrc' / 'tests' / 'test_hil_remote_core.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


rig = load_core_tests()   # its FAKE_SSH (RIG_PATH /usr/bin:/bin) and FAKE_RSYNC
needs_rig = unittest.skipUnless(os.name != 'nt' and rig.REAL_RSYNC and shutil.which('flock', path=rig.RIG_PATH) and
                                shutil.which('python3', path=rig.RIG_PATH) and shutil.which('git', path=rig.RIG_PATH),
                                'the fake rig needs POSIX, rsync, and flock, python3 and git on /usr/bin:/bin')

LPC = 'lpcxpresso55s69'
OTHER = 'lpcxpresso55s28'
ESP = 'espressif_esp32s3_devkitc_1'
LPC_FACTS = {'flashBase': 0, 'binBase': 0, 'appStart': 0x10000, 'flashSize': 0x98000, 'vid': 0x1fc9, 'pid': 0x0094,
             'boardId': 'LPC55S69-Xpresso-revA', 'family': 0x2abc77ec, 'vectors': 76, 'ram': 0x20000000,
             'dblTapDelayMs': 500, 'dblTapReg': 0x4002C05C, 'dblTapMagic': 0xF01669EF}
ROSTER = {'boards': [
  {'name': LPC, 'uid': 'UID', 'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0'},
   'tinyuf2': {'reentry': 'retained-register'}},
  {'name': OTHER, 'uid': 'UID2', 'flasher': {'name': 'jlink', 'uid': '2', 'args': '-device LPC55S69_M33_0'},
   'tinyuf2': {'reentry': 'retained-register'}},
  {'name': ESP, 'uid': 'MAC', 'flasher': {'name': 'esptool', 'uid': 'X', 'args': '--chip esp32s3'},
   'tinyuf2': {'reentry': 'dfu-detach'}}]}

# the build contract on the rig: run, a record of the board, ok unless FAKE_BUILD=fail, and its build dir's log;
# loaded, the real check_build's lib/agentrc pin check (FAKE_CHECK_BUILD) over this checkout
CHECK_BUILD = r'''
import importlib.util, json, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('real_check_build', os.environ['FAKE_CHECK_BUILD'])
real = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real)
real.ROOT = Path(__file__).resolve().parents[4]
Fail, check_agentrc_pin = real.Fail, real.check_agentrc_pin
if __name__ == '__main__':
  board = sys.argv[sys.argv.index('--board') + 1]
  ok = os.environ.get('FAKE_BUILD', 'ok') == 'ok'
  d = Path('cmake-build') / f'cmake-build-{board}'
  d.mkdir(parents=True, exist_ok=True)
  (d / 'check_build.log').write_text('the build log\n')
  print(json.dumps({'pass': ok, 'boards': [{'board': board, 'status': 'ok' if ok else 'failed',
                                            'firstError': '' if ok else 'boom', 'buildDir': str(d)}]}))
  sys.exit(0 if ok else 1)
'''

# `hil_test.py run` on the rig. It appends its argv and HIL_* environment to FAKE_ARGV, then either runs the real runner (from
# FAKE_REAL_RUNNER, its lock in FAKE_LOCKS, admission and the probe steps stubbed; FAKE_BATTERY=die leaves the battery
# to be killed, FAKE_CI_RACE starts a CI battery's marker just before the lock is taken) or prints a canned report:
# FAKE_BATTERY pass, fail (after a write), die (no report), holder (stays the in-process cleanup holder) or unpublished
# (a pass whose report the core could not publish: reportPath null, reportError). Before its report it sleeps
# FAKE_SLEEP s (only on board FAKE_SLEEP_BOARD when set) and waits up to 30 s for the file FAKE_GATE; FAKE_MD is a
# Markdown view left beside the JSON, FAKE_READONLY leaves the run dir read-only and FAKE_UNLISTABLE its run root
# unlistable.
HIL_TEST = r'''
import json, os, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
argv = sys.argv[1:]
with open(os.environ['FAKE_ARGV'], 'a') as f:
  f.write(json.dumps({'argv': argv, 'hil': sorted(k for k in os.environ if k.startswith('HIL_'))}) + '\n')
mode = os.environ.get('FAKE_BATTERY', 'pass')
if os.environ.get('FAKE_REAL_RUNNER'):
  import importlib.util
  spec = importlib.util.spec_from_file_location('hil_test', os.environ['FAKE_REAL_RUNNER'])
  ht = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(ht)
  ht.check_lock_pin = lambda: None
  load = ht.load_helper

  def load_helper():
    helper = load()
    helper.BOARD_LOCK_DIR = os.environ['FAKE_LOCKS']
    race, acquire = os.environ.get('FAKE_CI_RACE'), helper.acquire_board_lock

    def acquire_after_a_ci_start(lock, *a, **k):
      if race:
        Path(race).mkdir(parents=True, exist_ok=True)
        (Path(race) / f'{lock}.started').touch()
      return acquire(lock, *a, **k)
    helper.acquire_board_lock = acquire_after_a_ci_start
    return helper

  def run(bat, files, version):
    bat.touched = True
    if mode == 'die':
      Path(os.environ['FAKE_PID']).write_text(str(os.getpid()))
      time.sleep(60)
  ht.load_helper = load_helper
  ht.record_facts = lambda record, board, workdir: json.loads(os.environ['FAKE_FACTS'])
  ht.admit_record = lambda *a: ({}, {'version': 'v'})
  ht.probe_users = lambda board: []
  ht.Battery.run = run
  ht.Battery.restore = lambda bat, files, version: {'pass': True, 'state': 'blinky copied', 'evidence': {}}
  sys.exit(ht.main(argv))
board = argv[argv.index('-b') + 1]
run_dir = Path(argv[argv.index('--run-root') + 1]) / f'run-20261020-000000-{os.getpid()}'
run_dir.mkdir(parents=True)
(run_dir / 'hil.log').write_text('log\n')
if os.environ.get('FAKE_SLEEP_BOARD', board) == board:
  time.sleep(float(os.environ.get('FAKE_SLEEP', '0')))
gate, end = os.environ.get('FAKE_GATE'), time.monotonic() + 30
while gate and not os.path.exists(gate) and time.monotonic() < end:
  time.sleep(0.02)
if mode == 'die':
  sys.exit(137)
steps = [{'step': 'install', 'pass': True}, {'step': 'dfu', 'pass': mode != 'fail', 'detail': 'no DFU'}]
cleanup = {'pass': True, 'state': 'blinky copied', 'heldAfter': False}
if mode == 'holder':
  cleanup = {'pass': False, 'state': 'unknown', 'heldAfter': True, 'holder': {'pid': os.getpid(), 'inProcess': True}}
code = {'pass': 0, 'unpublished': 0, 'fail': 1, 'holder': 4}[mode]
passed = mode in ('pass', 'unpublished')
report = {'pass': passed, 'caveat': '', 'reportPath': str(run_dir / 'hil_report.json'), 'exitCode': code,
          'heldInProcess': mode == 'holder', 'results': [{'board': board, 'ran': True, 'pass': passed,
                                                          'locked': False, 'steps': steps, 'cleanup': cleanup, 'detail': ''}]}
if mode == 'unpublished':
  report.update(reportPath=None, reportError='report not published: OSError: disk full')
else:
  (run_dir / 'hil_report.json').write_text(json.dumps(report))
if os.environ.get('FAKE_MD'):
  (run_dir / 'hil_report.md').write_text(os.environ['FAKE_MD'])
if os.environ.get('FAKE_READONLY'):
  run_dir.chmod(0o555)
if os.environ.get('FAKE_UNLISTABLE'):
  run_dir.parent.chmod(0o300)
print('noise')
print(json.dumps(report), flush=True)
if mode == 'holder':
  Path(os.environ['FAKE_PID']).write_text(str(os.getpid()))
  os.close(1)
  time.sleep(60)
sys.exit(code)
'''

GET_DEPS = '''deps_all = {'lib/mcu/vendor/dep': ['https://example.invalid/dep.git', %r, 'lpc55']}\n'''


# a git hook's GIT_DIR/GIT_INDEX_FILE would aim the fixtures' git at the checkout under test
LOCAL_GIT_VARS = subprocess.run(['git', 'rev-parse', '--local-env-vars'], capture_output=True, text=True).stdout.split()


def fixture_env():
  return {k: v for k, v in os.environ.items() if k not in LOCAL_GIT_VARS}


def git(cwd, *argv):
  return subprocess.run(['git', '-C', str(cwd), *argv], check=True, capture_output=True, text=True,
                        env=fixture_env()).stdout.strip()


def commit(repo, files, msg):
  for rel, text in files.items():
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)
  git(repo, 'add', '-A')
  git(repo, 'commit', '-q', '-m', msg)
  return git(repo, 'rev-parse', 'HEAD')


def origin(path, *texts):
  path.mkdir(parents=True)
  git(path, 'init', '-q')
  for i, t in enumerate(texts):
    sha = commit(path, {'README': t}, f'c{i}')
  return sha


def run_main(*argv):
  out = io.StringIO()
  with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
    code = hr.main(list(argv))
  lines = out.getvalue().strip().splitlines()
  return code, json.loads(lines[-1]) if lines else None


class Project(unittest.TestCase):
  """A superproject in a relocated worktree, its submodules at a candidate pin, on a local fake rig."""

  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    gitconfig = self.tmp / 'gitconfig'
    gitconfig.write_text('[user]\n name = t\n email = t@t\n[protocol "file"]\n allow = always\n'
                         '[init]\n defaultBranch = main\n[commit]\n gpgsign = false\n[advice]\n detachedHead = false\n')
    self.home = self.tmp / 'home'
    (self.home / '.local' / 'bin').mkdir(parents=True)
    bindir = self.tmp / 'bin'
    bindir.mkdir()
    rig.fake(bindir / 'ssh', rig.FAKE_SSH)
    rig.fake(bindir / 'rsync', rig.FAKE_RSYNC)
    self.state = self.tmp / 'state'
    self.state.mkdir()
    self.locks = self.tmp / 'locks'
    self.locks.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(('HIL_', 'FAKE_', 'GIT_'))}
    env.update(PATH=f'{bindir}{os.pathsep}{os.environ["PATH"]}', GIT_CONFIG_GLOBAL=str(gitconfig), GIT_CONFIG_NOSYSTEM='1',
               FAKE_LOG=str(self.tmp / 'log.jsonl'), FAKE_HOME=str(self.home), FAKE_ARGV=str(self.tmp / 'argv.json'),
               FAKE_PID=str(self.tmp / 'battery.pid'),
               FAKE_CHECK_BUILD=str(ROOT / '.claude' / 'skills' / 'build' / 'scripts' / 'check_build.py'))
    mock.patch.dict(os.environ, env, clear=True).start()
    self.addCleanup(mock.patch.stopall)
    self.make_project()
    cb = hr.check_build()
    cb.get_deps_table.cache_clear()
    self.addCleanup(cb.get_deps_table.cache_clear)
    mock.patch.object(hr, 'ROOT', self.wt).start()
    mock.patch.object(cb, 'ROOT', self.wt).start()
    mock.patch.object(hr, 'POLL', 0.05).start()
    mock.patch.object(hr, 'check_pin').start()   # the real checkout's pin; check_pin is tested on the project's
    mock.patch.dict(hr.HOSTS, {'rig': {'hostname': socket.gethostname(), 'roster': 'test/hil/ci.json',
                                       'base': str(self.tmp / 'attempts'), 'ciStateRoot': str(self.state)}}).start()
    self.addCleanup(self.kill_left_sessions)

  def make_project(self):
    o = self.tmp / 'origins'
    self.dep = origin(o / 'dep', 'dep 1', 'dep 2')
    for name in ('agentrc', 'tinyusb', 'uf2'):
      origin(o / name, name)
    core = 'skills/hil/scripts/hil_report_core.py'   # the driver prepares each report pair through it, as CI does
    staged = (core, hr.run_report.HIL_LOAD, *hr.run_report.files_of(ROOT / 'lib' / 'agentrc' / core))
    commit(o / 'agentrc', {rel: (ROOT / 'lib' / 'agentrc' / rel).read_text() for rel in staged}, 'report core')
    primary = self.tmp / 'primary'
    primary.mkdir()
    git(primary, 'init', '-q')
    scripts = '.claude/skills/hil-contract/scripts'
    files = {'.gitignore': 'lib/mcu/\ncmake-build/\n__pycache__/\n.hil-remote/\n',
             f'{scripts}/hil_test.py': HIL_TEST, '.claude/skills/build/scripts/check_build.py': CHECK_BUILD,
             'test/hil/ci.json': json.dumps(ROSTER), f'ports/lpc55/boards/{LPC}/board.h': 'lpc\n', f'ports/lpc55/boards/{OTHER}/board.h': 'lpc\n',
             'tools/get_deps.py': GET_DEPS % self.dep}
    files.update({f'{scripts}/{n}': (SCRIPTS / n).read_text() for n in ('hil_ci.py', 'hil_run_report.py', 'hil_remote_driver.py')})
    commit(primary, files, 'project')
    for name in ('agentrc', 'tinyusb', 'uf2'):
      git(primary, 'submodule', 'add', '-q', str(o / name), f'lib/{name}')
    git(primary, 'commit', '-q', '-m', 'submodules')
    self.wt = self.tmp / 'wt'
    git(primary, 'worktree', 'add', '-q', '-b', 'feature', str(self.wt))
    git(self.wt, 'submodule', 'update', '--init', '-q')
    subprocess.run(['git', 'clone', '-q', '--depth', '1', f'file://{o / "dep"}', str(self.wt / 'lib/mcu/vendor/dep')],
                   check=True, capture_output=True, env=fixture_env())
    self.pin = commit(self.wt / 'lib/agentrc', {'NEW': 'unpushed'}, 'candidate')
    git(self.wt, 'add', 'lib/agentrc')
    git(self.wt, 'commit', '-q', '-m', 'pin the candidate')
    self.head = git(self.wt, 'rev-parse', 'HEAD')

  def kill_left_sessions(self):
    for launch in (self.tmp / 'attempts').glob('*/.attempt/launch.json'):
      with contextlib.suppress(OSError, ValueError, KeyError):
        os.killpg(json.loads(launch.read_text())['sid'], signal.SIGKILL)
    pid = self.tmp / 'battery.pid'
    if pid.exists():
      with contextlib.suppress(OSError, ValueError):
        os.kill(int(pid.read_text()), signal.SIGKILL)

  def ssh_calls(self):
    log = self.tmp / 'log.jsonl'
    return [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []

  def attempt(self, run_id='r1'):
    return self.tmp / 'attempts' / run_id

  def run_(self, *extra, run_id='r1', board=LPC):
    return run_main('run', '-b', board, '--run-id', run_id, '--host', 'rig', *extra)

  def batteries(self):
    argv = self.tmp / 'argv.json'
    return [json.loads(ln) for ln in argv.read_text().splitlines()] if argv.exists() else []


class Refusals(Project):
  """Every refusal comes before the rig is touched: no ssh, no attempt."""

  def refused(self, *argv, text):
    argv = argv or ('run', '-b', LPC, '--run-id', 'r1', '--host', 'rig')
    with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
      code = hr.main(list(argv))
    self.assertEqual(code, hr.REFUSED)
    self.assertIn(text, err.getvalue())
    self.assertEqual(self.ssh_calls(), [])
    self.assertFalse((self.tmp / 'attempts').exists())
    self.assertEqual(list((self.wt / hr.RUNS).glob('.*.stage')) if (self.wt / hr.RUNS).exists() else [], [])

  def test_manual_recovery_and_override_operations(self):
    for argv, text in ((('install', '-b', LPC), 'manual or recovery operation'),
                       (('restore', '-b', LPC), 'manual or recovery operation'),
                       (('clear-pending', '-b', LPC), 'manual or recovery operation')):
      self.refused(*argv, text=text)
    for flag in ('--under-hold=x', '--recover-holder', '--recover-takeover', '--try-reentry', '--route', '--run-root',
                 '--ci-state-root', '--done-marker', '--started-marker', '--build-record', '--update-record'):
      self.refused('run', '-b', LPC, flag, 'v', text='takes no manual, recovery, commissioning or override option')

  def test_boards_and_run_ids(self):
    self.refused('run', '-b', 'nope', '--host', 'rig', text='not in test/hil/ci.json at HEAD')
    self.assertEqual(hr.select([ESP, LPC], ROSTER, 'test/hil/ci.json'), sorted([ESP, LPC]))   # ESP-IDF builds on the rig
    self.refused('run', '-b', LPC, '--host', 'elsewhere', text='no rig elsewhere')
    self.refused('run', '-b', LPC, '--host', 'rig', '--run-id', '../x', text='a run id is')
    with mock.patch.dict(os.environ, {'HIL_NO_BOARD_LOCK': '1'}):
      self.refused(text='HIL_NO_BOARD_LOCK is set')
    with mock.patch.object(hr.os, 'name', 'nt'):
      self.refused(text='Windows client is pending')

  def test_lib_agentrc_off_its_pin_or_changed_is_refused(self):
    check = CHECK_PIN   # check_build's check, on the project (cb.ROOT)
    check()
    for what, change, undo in (
        ('a changed file', lambda: (self.wt / 'lib/agentrc/NEW').write_text('changed'),
         lambda: git(self.wt / 'lib/agentrc', 'checkout', '-q', '--', 'NEW')),
        ('an untracked file', lambda: (self.wt / 'lib/agentrc/stray').write_text('x'),
         lambda: (self.wt / 'lib/agentrc/stray').unlink())):
      with self.subTest(what):
        change()
        with self.assertRaisesRegex(hr.core.RemoteError, 'dirty at the pinned'):
          check()
        undo()
    git(self.wt / 'lib/agentrc', 'checkout', '-q', 'HEAD~1')
    with self.assertRaises(hr.core.RemoteError) as e:
      check()
    self.assertIn(f'HEAD pins {self.pin}: git submodule update --init lib/agentrc', e.exception.code)
    git(self.wt, 'add', 'lib/agentrc')   # the pin change staged: submodule update would check that out
    with self.assertRaisesRegex(hr.core.RemoteError, 'is staged: commit or unstage'):
      check()

  def test_wait_and_collect_load_nothing_that_needs_fcntl(self):
    # Windows has no fcntl: the pin check's check_build and every module the client imports must load without it
    r = subprocess.run([sys.executable, '-c', "import sys; sys.modules['fcntl'] = None; import hil_remote; "
                        "hil_remote.check_build(); print('ok')"], cwd=SCRIPTS, capture_output=True, text=True)
    self.assertEqual(r.stdout.strip(), 'ok', r.stderr)

  def test_no_provider_code_runs_before_its_pin_is_checked(self):
    r = subprocess.run([sys.executable, '-c', 'import hil_remote; print(hil_remote.core)'], cwd=SCRIPTS,
                       capture_output=True, text=True)
    self.assertEqual(r.stdout.strip(), 'None', r.stderr)
    with mock.patch.object(hr, 'core', None), mock.patch.object(hr, 'load_core') as load, \
         mock.patch.object(hr, 'check_pin', side_effect=lambda: hr.fail('lib/agentrc is at 0 or locally changed')):
      self.refused('collect', 'r1', text='locally changed')
    load.assert_not_called()

  def test_inputs_that_are_not_heads_committed_identity(self):
    roster = self.wt / 'test/hil/ci.json'
    cases = {
      'a changed roster': lambda: roster.write_text(roster.read_text() + ' '),
      'an untracked file': lambda: (self.wt / 'stray').write_text('x'),
      'a dirty submodule': lambda: (self.wt / 'lib/uf2/README').write_text('changed'),
      'a submodule off its pin': lambda: git(self.wt / 'lib/agentrc', 'checkout', '-q', 'HEAD~1'),
      'a missing dependency': lambda: shutil.rmtree(self.wt / 'lib/mcu'),
      'a dependency off its pin': lambda: commit(self.wt, {'tools/get_deps.py': GET_DEPS % ('0' * 40)}, 'off pin'),
    }
    for what, change in cases.items():
      with self.subTest(what):
        snapshot = self.tmp / 'snap'
        shutil.copytree(self.wt / 'lib', snapshot)
        head = git(self.wt, 'rev-parse', 'HEAD')
        change()
        self.refused(text="not HEAD's committed identity")
        git(self.wt, 'reset', '-q', '--hard', head)
        git(self.wt, 'clean', '-qfd', '-e', 'lib/')
        shutil.rmtree(self.wt / 'lib')
        shutil.move(snapshot, self.wt / 'lib')


@needs_rig
class Attempt(Project):
  def test_a_pass_rebuilds_the_committed_identity_on_the_rig_and_comes_home(self):
    code, out = self.run_()
    self.assertEqual((code, out['outcome'], out['pass'], out['collection']), (0, 'pass', True, 'complete'))
    src = self.attempt() / 'src'
    self.assertEqual(git(src, 'rev-parse', 'HEAD'), self.head)
    self.assertEqual(git(src / 'lib/agentrc', 'rev-parse', 'HEAD'), self.pin, 'the unpushed candidate pin')
    dep = src / 'lib/mcu/vendor/dep'
    self.assertEqual((git(dep, 'rev-parse', 'HEAD'), git(dep, 'rev-parse', '--is-shallow-repository')), (self.dep, 'true'))
    git(dep, 'fsck', '--no-dangling')
    for repo in (src, *(src / f'lib/{n}' for n in ('agentrc', 'tinyusb', 'uf2')), dep):
      self.assertTrue((repo / '.git').is_dir(), f'{repo}: a checkout of its own, no pointer file')
      self.assertEqual(subprocess.run(['git', '-C', str(repo), 'config', '--local', '--get-regexp', 'remote'],
                                      capture_output=True, env=fixture_env()).stdout, b'')
    self.assertFalse([p for p in src.rglob('*') if p.is_symlink()])
    ran, = self.batteries()
    argv = ran['argv']
    self.assertEqual((argv[0], argv[argv.index('--ci-state-root') + 1], argv[argv.index('--lock-wait') + 1], argv[-1]),
                     ('run', str(self.state), '0', 'test/hil/ci.json'))
    self.assertNotIn('--done-marker', argv)   # CI's markers stay CI's
    self.assertNotIn('--started-marker', argv)
    self.assertEqual(ran['hil'], [])
    # home: the records, run dir, report and output, the paths recovery needs on the rig beside their local copies
    local = self.wt / hr.RUNS / 'r1'
    row, = out['boards']
    self.assertEqual((row['verdict'], row['phase']), ('pass', 'battery'))
    report, = row['paths']['reports']
    self.assertTrue((self.wt / report['local']).is_file())
    self.assertEqual(report['remote'], str(self.attempt() / Path(report['local']).relative_to(f'{hr.RUNS}/r1')))
    self.assertEqual(out['remote']['checkout'], str(src))
    for rel in (f'out/{LPC}.build.json', f'out/{LPC}/stdout.txt', f'out/{LPC}/stderr.txt', 'manifest.json', 'result.json'):
      self.assertTrue((local / rel).is_file(), rel)
    self.assertEqual(json.loads((self.wt / hr.RUNS / 'r1.outcome.json').read_text()), out)
    self.assertFalse((self.wt / hr.RUNS / '.r1.stage').exists())
    # reconnecting answers from the complete collection, and nothing launches the attempt again
    launch = (self.attempt() / '.attempt/launch.json').read_text()
    self.assertEqual(run_main('wait', 'r1', '--timeout', '1'), (0, out))
    self.assertEqual(run_main('collect', 'r1'), (0, out))
    self.assertEqual((self.attempt() / '.attempt/launch.json').read_text(), launch)
    self.assertEqual(self.run_()[0], hr.REFUSED, 'a run id is used once')

  def test_boards_run_one_after_another_within_one_lock_wait(self):
    os.environ.update(FAKE_SLEEP='2', FAKE_SLEEP_BOARD=OTHER)   # the first battery uses up 2 s of the budget
    code, out = self.run_('-b', OTHER, '--lock-wait', '100')
    self.assertEqual((code, [r['board'] for r in out['boards']]), (0, [OTHER, LPC]))
    waits = [int(b['argv'][b['argv'].index('--lock-wait') + 1]) for b in self.batteries()]
    self.assertEqual(waits[0], 100)
    self.assertLessEqual(waits[1], 98)

  def test_a_git_override_in_the_callers_environment_is_ignored(self):
    victim = self.tmp / 'victim'
    sha = origin(victim, 'victim')
    os.environ.update(GIT_DIR=str(victim / '.git'), GIT_WORK_TREE=str(victim))
    code, out = self.run_()
    self.assertEqual((code, out['outcome']), (0, 'pass'))
    self.assertEqual(os.environ['GIT_DIR'], str(victim / '.git'), 'restored for the caller')
    del os.environ['GIT_DIR'], os.environ['GIT_WORK_TREE']
    self.assertEqual(git(self.attempt() / 'src', 'rev-parse', 'HEAD'), self.head)
    self.assertEqual(git(victim, 'rev-parse', 'HEAD'), sha)

  def test_a_driver_failure_after_a_passing_row_is_no_success(self):
    stage = hr.core.stage_tree

    def obstructed(tree, src, dest='.'):
      stage(tree, src, dest)
      (Path(tree.dir) / 'progress.json').mkdir()   # the driver's publication of its rows fails
    with mock.patch.object(hr.core, 'stage_tree', obstructed), mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), \
         self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.await_done()
    (self.attempt() / 'progress.json').rmdir()
    code, out = run_main('wait', 'r1', '--timeout', '5')
    self.assertEqual((code, out['outcome'], out['pass'], out['boards'][0]['verdict']), (2, 'blocker', False, 'pass'))
    self.assertIn('progress.json', out['driverFailure'])

  def test_an_unpublished_report_is_an_incomplete_copy_back_beside_the_native_verdict(self):
    os.environ['FAKE_BATTERY'] = 'unpublished'
    code, out = self.run_()
    row, = out['boards']
    self.assertEqual((code, out['outcome'], row['verdict'], row['copyBack']), (hr.INCOMPLETE, 'incomplete', 'pass', 'incomplete'))
    self.assertIn('never published: report not published: OSError: disk full', row['missing'][0])
    self.assertNotIn('reports', row['paths'])

  def test_each_report_pair_is_prepared_on_the_rig_before_it_comes_home(self):
    os.environ['FAKE_MD'] = 'HIL run: fail\n'   # a stale view beside a passing JSON
    code, out = self.run_()
    row, = out['boards']
    self.assertEqual((code, out['outcome'], row['verdict'], row['sharedVerdict']), (0, 'pass', 'pass', 'pass'))
    md, = (self.wt / hr.RUNS / 'r1' / 'out' / LPC).glob('run-*/hil_report.md')
    self.assertTrue(md.read_text(encoding='utf-8').startswith('HIL run: pass\n'), md.read_text())
    self.assertNotIn('HIL run: fail', md.read_text(encoding='utf-8'))

  @unittest.skipUnless(os.name != 'nt' and os.geteuid(), 'root writes a read-only dir')
  def test_a_view_the_rig_could_not_check_never_comes_home(self):
    os.environ.update(FAKE_MD='HIL run: pass\n', FAKE_READONLY='1')   # neither prepared nor withheld on the rig
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.await_done()
    run_dir, = (self.attempt() / 'out' / LPC).glob('run-*')
    run_dir.chmod(0o755)
    rel = (run_dir / 'hil_report.md').relative_to(self.attempt()).as_posix()
    self.assertTrue((self.attempt() / rel).is_file(), 'still on the rig')
    local = self.wt / hr.RUNS / 'r1'
    unlink = Path.unlink

    def stuck(path, *a, **k):
      if path.name == 'hil_report.md':
        raise PermissionError(13, 'Permission denied', str(path))
      return unlink(path, *a, **k)
    with mock.patch.object(Path, 'unlink', stuck):   # a view that cannot be removed is never published
      self.assertEqual(run_main('collect', 'r1')[0], hr.core.INCONCLUSIVE)
    self.assertFalse(local.exists())
    with mock.patch.object(hr, 'report', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      run_main('collect', 'r1')   # interrupted once the core published the collection
    self.assertEqual(json.loads((local / hr.core.COLLECTION).read_text())['state'], 'complete')
    self.assertFalse((local / rel).exists(), 'never published as evidence')
    self.assertTrue((local / rel).with_name('hil_report.json').is_file())
    code, out = run_main('collect', 'r1')
    row, = out['boards']
    self.assertEqual((code, out['outcome'], out['collection'], row['verdict'], row['sharedVerdict'], row['unsafeArtifacts']),
                     (0, 'pass', 'complete', 'pass', 'blocker', [rel]))
    self.assertFalse((local / rel).exists())

  @unittest.skipUnless(os.name != 'nt' and os.geteuid(), 'root lists an unlistable dir')
  def test_a_view_under_a_run_root_the_rig_could_not_list_never_comes_home(self):
    os.environ.update(FAKE_MD='HIL run: pass\n', FAKE_UNLISTABLE='1')
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.await_done()
    board = self.attempt() / 'out' / LPC
    board.chmod(0o755)   # readable again by the copy-back
    md, = board.glob('run-*/hil_report.md')
    self.assertEqual(md.read_text(encoding='utf-8'), 'HIL run: pass\n', 'never checked on the rig')
    code, out = run_main('collect', 'r1')
    row, = out['boards']
    local = self.wt / hr.RUNS / 'r1' / md.relative_to(self.attempt())
    self.assertEqual((row['verdict'], row['sharedVerdict'], local.with_name('hil_report.json').is_file(),
                      local.exists()), ('pass', 'blocker', True, False))
    # the rig's inventory of that board is unverified: never a final collection
    self.assertEqual((code, out['outcome'], row['unsafeArtifacts']), (hr.INCOMPLETE, 'incomplete', [f'out/{LPC}']))

  def test_an_incomplete_collection_brings_home_no_unchecked_view(self):
    os.environ['FAKE_MD'] = 'HIL run: pass\n'
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.await_done()
    result = self.attempt() / 'result.json'
    good = result.read_text()
    result.write_text('{')   # the driver's outcome unreadable: no view is known prepared
    local = self.wt / hr.RUNS / 'r1' / 'out' / LPC
    unlink = Path.unlink

    def stuck(path, *a, **k):
      if path.name == 'hil_report.md':
        raise PermissionError(13, 'Permission denied', str(path))
      return unlink(path, *a, **k)
    with mock.patch.object(Path, 'unlink', stuck):   # an unchecked view that cannot be removed is never published
      self.assertEqual(run_main('collect', 'r1')[0], hr.core.INCONCLUSIVE)
    self.assertFalse(local.exists())
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome'], out['collection']), (hr.INCOMPLETE, 'incomplete', 'incomplete'))
    self.assertTrue(list(local.glob('run-*/hil_report.json')))
    self.assertEqual(list(local.glob('run-*/hil_report.md')), [], 'an unchecked view came home')
    result.write_text(good)
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome'], out['collection']), (0, 'pass', 'complete'))
    md, = local.glob('run-*/hil_report.md')   # prepared on the rig: it comes home with its result
    self.assertTrue(md.read_text(encoding='utf-8').startswith('HIL run: pass\n'))

  def test_a_board_without_a_prepared_row_brings_home_no_view(self):
    os.environ['FAKE_MD'] = 'HIL run: pass\n'
    for run_id, edit in (('r1', lambda rows: []),   # the driver ended before the board's row
                         ('r2', lambda rows: [{k: v for k, v in r.items() if k not in ('sharedVerdict', 'sharedDetail')}
                                              for r in rows])):   # a row whose report pair was never prepared
      with self.subTest(run_id):
        with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
          self.run_(run_id=run_id)
        self.await_done(run_id)
        result = self.attempt(run_id) / 'result.json'
        data = json.loads(result.read_text())
        result.write_text(json.dumps(dict(data, boards=edit(data['boards']))))
        code, out = run_main('collect', run_id)
        self.assertNotEqual(out['outcome'], 'pass')
        local = self.wt / hr.RUNS / run_id / 'out' / LPC
        self.assertTrue(list(local.glob('run-*/hil_report.json')))
        self.assertEqual(list(local.glob('run-*/hil_report.md')), [], 'an unchecked view came home')

  def test_a_short_collection_recovers_once_the_rig_has_the_artifact_again(self):
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.await_done()
    log, = (self.attempt() / 'out' / LPC).glob('run-*/hil.log')
    log.rename(self.tmp / 'hil.log')
    self.assertEqual(run_main('collect', 'r1')[0], hr.INCOMPLETE)
    (self.tmp / 'hil.log').rename(log)
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome'], out['collection']), (0, 'pass', 'complete'))
    self.assertTrue((self.wt / hr.RUNS / 'r1' / log.relative_to(self.attempt())).is_file())
    self.assertFalse([p for p in (self.wt / hr.RUNS).glob('.r1.*') if p.is_dir()], 'no staging dir left')

  def test_an_unreadable_result_is_never_a_final_collection(self):
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.await_done()
    result = self.attempt() / 'result.json'
    good = result.read_text()
    for corrupt in ('{', json.dumps(dict(json.loads(good), runId='another'))):
      with self.subTest(corrupt[:12]):
        result.write_text(corrupt)
        code, out = run_main('collect', 'r1')
        self.assertEqual((code, out['outcome'], out['collection']), (hr.INCOMPLETE, 'incomplete', 'incomplete'))
        self.assertTrue(json.loads((self.wt / hr.RUNS / 'r1' / hr.core.COLLECTION).read_text())['unaccepted'])
    result.write_text(good)
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome'], out['collection']), (0, 'pass', 'complete'))

  def test_concurrent_collectors_never_remove_a_published_collection(self):
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.await_done()
    tree, manifest = hr.core.load_attempt(self.wt, self.wt / hr.RUNS, 'r1'), hr.load_manifest('r1')
    groups, optional = hr.members(manifest)
    inside, release, got = threading.Event(), threading.Event(), []

    def held(path):   # the first collector pauses inside its predicate, under the collector lock
      inside.set()
      release.wait(30)
      return hr.acceptance(tree, manifest)(path)
    first = threading.Thread(target=lambda: got.append(hr.core.collect(tree, self.wt / hr.RUNS / 'r1', groups, optional, accept=held)))
    first.start()
    self.assertTrue(inside.wait(30))
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome']), (hr.core.INCONCLUSIVE, 'inconclusive'))
    self.assertIn('another collector holds', out['detail'])
    release.set()
    first.join(30)
    self.assertEqual(got[0]['state'], 'complete')
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome'], out['collection']), (0, 'pass', 'complete'))

  def test_a_transport_failure_after_the_launch_is_inconclusive_not_a_refusal(self):
    code, out = self.run_()
    self.assertEqual(code, 0)
    shutil.rmtree(self.wt / hr.RUNS / 'r1')   # nothing cached: the next collect must reach the rig
    os.environ['FAKE_SSH_DOWN'] = "' status "
    for argv in (('collect', 'r1'), ('wait', 'r1', '--timeout', '0')):
      code, out = run_main(*argv)
      self.assertEqual((code, out['outcome'], out['pass']), (hr.core.INCONCLUSIVE, 'inconclusive', False), argv)
    self.assertEqual(run_main('collect', 'nope')[0], hr.REFUSED, 'an unknown run is still a refusal')

  def await_done(self, run_id='r1'):
    done = self.attempt(run_id) / '.attempt/done.json'
    deadline = time.monotonic() + 30
    while not done.exists() and time.monotonic() < deadline:
      time.sleep(0.05)
    self.assertTrue(done.exists())

  def test_a_build_refusal_brings_its_diagnostics_and_no_battery(self):
    os.environ['FAKE_BUILD'] = 'fail'
    code, out = self.run_()
    row, = out['boards']
    self.assertEqual((code, row['verdict'], row['phase'], row['detail']), (1, 'not-run', 'build', 'build failed: boom'))
    local = self.wt / hr.RUNS / 'r1'
    self.assertFalse((local / 'out' / LPC).exists())
    self.assertTrue((local / f'out/{LPC}.build.json').is_file())
    self.assertTrue((local / f'src/cmake-build/cmake-build-{LPC}/check_build.log').is_file())
    self.assertFalse((self.tmp / 'argv.json').exists(), 'no battery ran')

  def test_a_battery_without_a_report_is_a_blocker(self):
    os.environ['FAKE_BATTERY'] = 'die'
    code, out = self.run_()
    self.assertEqual((code, out['outcome'], out['boards'][0]['verdict']), (2, 'blocker', 'blocker'))
    self.assertIn('without a report', out['boards'][0]['detail'])

  def test_an_in_process_holder_is_left_running_and_reported_as_a_blocker(self):
    os.environ['FAKE_BATTERY'] = 'holder'
    code, out = self.run_()
    row, = out['boards']
    self.assertEqual((code, row['verdict'], row['heldInProcess']), (2, 'blocker', True))
    pid = int((self.tmp / 'battery.pid').read_text())
    self.assertEqual(row['holder']['pid'], pid)
    os.kill(pid, 0)   # the attempt completed; the holder keeps the board, untouched by the driver's end

  def test_an_abandoned_ci_marker_is_a_blocker_before_any_build(self):
    (self.state / 'ci-run').mkdir()
    (self.state / 'ci-run' / f'{LPC}.started').touch()
    code, out = self.run_()
    row, = out['boards']
    self.assertEqual((code, row['verdict'], row['phase'], row['unfinishedAttempts']), (2, 'blocker', 'preflight', ['ci-run']))
    self.assertFalse((self.attempt() / f'out/{LPC}.build.json').exists())

  def test_an_unreadable_ci_state_root_refuses_on_the_rig(self):
    shutil.rmtree(self.state)
    code, out = self.run_()
    self.assertEqual((code, out['outcome']), (hr.REFUSED, 'refused'))
    self.assertIn('cannot be read', out['detail'])

  def test_corrupt_packages_are_refused_before_the_launch(self):
    stage = hr.core.stage_tree

    def corrupting(tree, src, dest='.'):
      stage(tree, src, dest)
      (Path(tree.dir) / 'bundles' / '0.bundle').write_bytes(b'corrupt')
    with mock.patch.object(hr.core, 'stage_tree', corrupting):
      code, out = self.run_()
    self.assertEqual((code, out), (hr.REFUSED, None))
    self.assertFalse((self.attempt() / '.attempt/launch.claim').exists())
    self.assertEqual(run_main('wait', 'r1', '--timeout', '0')[0], hr.core.DEAD)
    self.assertFalse((self.attempt() / '.attempt/launch.claim').exists(), 'waiting never launches')

  def test_a_replaced_attempt_token_refuses_the_staging(self):
    create = hr.core.create_attempt

    def replaced(*a, **k):
      tree = create(*a, **k)
      (Path(tree.dir) / hr.core.TOKEN_FILE).write_text('another session\n')
      return tree
    with mock.patch.object(hr.core, 'create_attempt', replaced), rig.captured_fd2():
      self.assertEqual(self.run_()[0], hr.REFUSED)
    self.assertFalse((self.attempt() / 'manifest.json').exists())

  def test_a_wrapper_dead_while_staging_leaves_an_attempt_never_launched(self):
    def killed(*a, **k):
      raise KeyboardInterrupt
    with mock.patch.object(hr.core, 'stage_tree', killed), self.assertRaises(KeyboardInterrupt):
      self.run_()
    self.assertFalse((self.wt / hr.RUNS / '.r1.stage').exists())
    code, out = run_main('wait', 'r1', '--timeout', '0')
    self.assertEqual((code, out['outcome']), (hr.core.DEAD, 'not-launched'))
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome'], out['remoteState']), (hr.core.DEAD, 'incomplete', 'not-launched'))
    self.assertFalse((self.attempt() / '.attempt/launch.claim').exists())

  def test_a_lost_launch_acknowledgement_finds_the_attempt_and_never_launches_another(self):
    os.environ['FAKE_SSH_DROP'] = "' launch "
    code, out = self.run_()
    self.assertEqual((code, out['outcome']), (0, 'pass'))
    launches = [c for c in self.ssh_calls() if "' launch " in ' '.join(c['argv'])]
    self.assertEqual(len(launches), 1)

  def test_the_attempt_outlives_its_wrapper_and_partial_evidence_never_passes(self):
    gate = self.tmp / 'gate'
    os.environ['FAKE_GATE'] = str(gate)   # the battery holds until the gate opens, at most 30 s
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    code, out = run_main('wait', 'r1', '--timeout', '0.2')
    self.assertEqual((code, out['outcome']), (hr.core.RUNNING, 'running'))
    code, out = run_main('collect', 'r1')
    self.assertEqual((code, out['outcome'], out['remoteState'], out['pass']), (hr.core.RUNNING, 'incomplete', 'running', False))
    gate.touch()
    code, out = run_main('wait', 'r1', '--timeout', '30')
    self.assertEqual((code, out['outcome'], out['collection']), (0, 'pass', 'complete'))
    self.assertEqual(run_main('collect', 'r1'), (0, out))

  def test_a_driver_dead_before_completion_is_dead_never_done(self):
    os.environ['FAKE_SLEEP'] = '30'
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    launch = self.attempt() / '.attempt/launch.json'
    deadline = time.monotonic() + 10
    while not (self.tmp / 'argv.json').exists() and time.monotonic() < deadline:
      time.sleep(0.05)
    os.killpg(json.loads(launch.read_text())['sid'], signal.SIGKILL)
    deadline = time.monotonic() + 10
    while run_main('wait', 'r1', '--timeout', '0')[0] != hr.core.DEAD and time.monotonic() < deadline:
      time.sleep(0.1)
    code, out = run_main('wait', 'r1', '--timeout', '0')
    self.assertEqual((code, out['outcome'], out['pass']), (hr.core.DEAD, 'dead', False))
    self.assertEqual(run_main('collect', 'r1')[1]['outcome'], 'incomplete')
    self.assertFalse((self.attempt() / '.attempt/done.json').exists(), 'nothing inferred a completion')

  def test_a_missing_artifact_is_an_incomplete_copy_back_even_when_the_battery_passed(self):
    with mock.patch.object(hr, 'wait_for', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
      self.run_()
    done = self.attempt() / '.attempt/done.json'
    deadline = time.monotonic() + 30
    while not done.exists() and time.monotonic() < deadline:
      time.sleep(0.05)
    log, = (self.attempt() / 'out' / LPC).glob('run-*/hil.log')
    log.unlink()   # gone from the rig after the driver listed it
    code, out = run_main('wait', 'r1', '--timeout', '5')
    row, = out['boards']
    self.assertEqual((code, out['outcome'], out['collection'], row['verdict'], row['copyBack']),
                     (hr.INCOMPLETE, 'incomplete', 'incomplete', 'pass', 'incomplete'))
    self.assertEqual(row['missing'], [log.relative_to(self.attempt()).as_posix()])
    col = json.loads((self.wt / hr.RUNS / 'r1' / hr.core.COLLECTION).read_text())
    self.assertEqual(col['unaccepted'], [f'{LPC}: {row["missing"][0]}'], 'the core keeps it unaccepted, never final')


@needs_rig
class RealRunner(Project):
  """The driver over the real `hil_test.py run` and the pinned lock helper: the protected battery lock as every project
  sees it."""

  def setUp(self):
    super().setUp()
    os.environ.update(FAKE_REAL_RUNNER=str(SCRIPTS / 'hil_test.py'), FAKE_LOCKS=str(self.locks),
                      FAKE_FACTS=json.dumps(LPC_FACTS))
    with mock.patch.object(ht, 'check_lock_pin'):
      self.helper = ht.load_helper()
    mock.patch.object(self.helper, 'BOARD_LOCK_DIR', str(self.locks)).start()

  def test_a_clean_battery_releases_the_board(self):
    code, out = self.run_()
    self.assertEqual((code, out['boards'][0]['verdict']), (0, 'pass'))
    self.assertEqual(self.helper.record_state(LPC)[0], 'empty')

  def test_another_attempt_on_the_same_board_meets_its_lock(self):
    fh = self.helper.take_board_lock(LPC, 'another attempt')
    self.addCleanup(self.helper.release_board_lock, fh)
    code, out = self.run_()
    row, = out['boards']
    self.assertEqual((code, row['verdict']), (1, 'not-run'))
    self.assertIn('locked', row['detail'])

  def test_a_ci_battery_started_between_the_preflight_and_the_lock_keeps_the_board_a_blocker(self):
    os.environ['FAKE_CI_RACE'] = str(self.state / 'ci-old')
    code, out = self.run_()
    row, = out['boards']
    self.assertEqual((code, row['verdict'], row['phase']), (2, 'blocker', 'battery'))
    self.assertIn('ci-old', row['detail'])
    rec = self.helper.read_record(LPC)
    self.assertTrue(self.helper.is_recovery_blocker(rec))   # every project's helper refuses the board
    self.assertEqual((rec['reason'], rec['protected']), ('hil_test.py', True))
    self.assertEqual(Path(rec['runDir']).parent, self.attempt() / 'out' / LPC)

  def test_a_battery_killed_mid_run_leaves_a_stale_protected_record(self):
    os.environ['FAKE_BATTERY'] = 'die'
    pid = self.tmp / 'battery.pid'

    def kill_the_battery():
      end = time.monotonic() + 30
      while not pid.exists() and time.monotonic() < end:
        time.sleep(0.02)
      os.kill(int(pid.read_text()), signal.SIGKILL)
    killer = threading.Thread(target=kill_the_battery)
    killer.start()
    code, out = self.run_()
    killer.join()
    row, = out['boards']
    self.assertEqual((code, row['verdict']), (2, 'blocker'))
    self.assertIn('without a report', row['detail'])
    rec = self.helper.read_record(LPC)
    self.assertTrue(self.helper.is_recovery_blocker(rec))
    self.assertEqual((rec['reason'], rec['protected']), ('hil_test.py', True))


class Driver(unittest.TestCase):
  def test_the_rigs_hil_environment_never_reaches_a_runner(self):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('HIL_', 'GIT_'))}
    env.update(HIL_NO_BOARD_LOCK='1', HIL_X='y', GIT_DIR='/elsewhere/.git')
    with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, env, clear=True):
      m = {'schema': drv.SCHEMA, 'version': drv.VERSION, 'runId': 'r', 'head': '0' * 40, 'hostname': 'not-this-host',
           'repos': [], 'submodules': {}, 'roster': {'path': 'r.json'}, 'driver': {'path': 'd.py'}, 'boards': [],
           'lockWait': 0, 'failAt': None, 'ciStateRoot': d}
      (Path(d) / 'manifest.json').write_text(json.dumps(m))
      with mock.patch.object(drv.Path, 'cwd', return_value=Path(d)):
        self.assertEqual(drv.main(['manifest.json']), drv.REFUSED)
      self.assertFalse([k for k in os.environ if k.startswith(('HIL_', 'GIT_'))])
      result = json.loads((Path(d) / drv.RESULT).read_text())
    self.assertEqual(result['strippedEnv'], ['GIT_DIR', 'HIL_NO_BOARD_LOCK', 'HIL_X'])
    self.assertIn('not not-this-host', result['refused'])

  def test_a_git_override_on_the_rig_never_aims_the_rebuild_at_another_repository(self):
    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      env = {k: v for k, v in os.environ.items() if not k.startswith(('HIL_', 'GIT_'))}
      config = d / 'gitconfig'
      config.write_text('[user]\n name = t\n email = t@t\n[commit]\n gpgsign = false\n')
      with mock.patch.dict(os.environ, dict(env, GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM='1'), clear=True):
        head = origin(d / 'repo', 'candidate')
        victim = origin(d / 'victim', 'victim')
      attempt = d / 'attempt'
      (attempt / 'bundles').mkdir(parents=True)
      git(d / 'repo', 'bundle', 'create', '-q', str(attempt / 'bundles/0.bundle'), 'HEAD')
      m = {'schema': drv.SCHEMA, 'version': drv.VERSION, 'runId': 'r', 'head': head, 'hostname': socket.gethostname(),
           'repos': [{'path': '.', 'commit': head, 'bundle': 'bundles/0.bundle', 'shallow': [],
                      'sha256': hashlib.sha256((attempt / 'bundles/0.bundle').read_bytes()).hexdigest()}],
           'submodules': {}, 'roster': {'path': 'r.json', 'sha256': ''}, 'driver': {'path': 'd.py', 'sha256': ''},
           'boards': [], 'lockWait': 0, 'failAt': None, 'ciStateRoot': str(d)}
      (attempt / 'manifest.json').write_text(json.dumps(m))
      with mock.patch.dict(os.environ, dict(env, GIT_DIR=str(d / 'victim/.git'), GIT_WORK_TREE=str(d / 'victim')), clear=True), \
           mock.patch.object(drv.Path, 'cwd', return_value=attempt):
        drv.main(['manifest.json'])
      self.assertEqual((git(d / 'victim', 'rev-parse', 'HEAD'), (d / 'victim/README').read_text()), (victim, 'victim'))
      self.assertEqual(git(attempt / 'src', 'rev-parse', '--absolute-git-dir'), str(attempt / 'src/.git'))
      self.assertEqual(git(attempt / 'src', 'rev-parse', 'HEAD'), head)

  def test_a_malformed_manifest_is_refused(self):
    with tempfile.TemporaryDirectory() as d:
      bad = {'schema': drv.SCHEMA, 'version': drv.VERSION}
      for m in (bad, dict(bad, version=2), {**bad, **{k: [] for k in drv.FIELDS}, 'repos': [{'path': '../x', 'commit': '0' * 40, 'shallow': []}]}):
        (Path(d) / 'manifest.json').write_text(json.dumps(m))
        with self.assertRaises(drv.Refused):
          drv.load_manifest(Path(d) / 'manifest.json')

  def test_inventory_entries_outside_the_boards_artifacts_are_an_incomplete_copy_back(self):
    with tempfile.TemporaryDirectory() as d:
      for listed in (['out/other.build.json'], ['out/b/../x'], ['out/b//x'], ['out/b/./x'], ['/etc/passwd'], [3], 'x'):
        with self.subTest(listed):
          self.assertTrue(hr.artifacts_missing({'phase': 'battery', 'artifacts': listed}, 'b', Path(d))[0].startswith('('))
      for unsafe in (['out/b/stdout.txt'], ['out/b/run-1/../hil_report.md'], ['out/c/run-1/hil_report.md'], 'x'):
        with self.subTest(unsafe):
          row = {'phase': 'build', 'artifacts': [], 'unsafeArtifacts': unsafe}
          self.assertTrue(hr.artifacts_missing(row, 'b', Path(d))[0].startswith('(unsafeArtifacts'))


if __name__ == '__main__':
  unittest.main()
