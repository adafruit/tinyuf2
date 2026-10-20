#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The CI job's orchestration of the battery (hil_ci.py): record, one run per board, verdicts, markers, pruning
# and the exit. check_build is stubbed; the battery is a stand-in script that prints a canned report into the run
# root it is given, so the streaming, the run directory and the in-process holder path run for real.
import io
import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'))
import hil_ci  # noqa: E402
import hil_test as ht  # noqa: E402

BOARD = 'imxrt1064_evk'

STAND_IN = '''
import json, os, sys, time
one = json.load(open(os.environ["HIL_STAND_IN"]))
run_dir = os.path.join(sys.argv[sys.argv.index("--run-root") + 1], "run-1")
os.makedirs(run_dir)
open(os.path.join(run_dir, "hil.log"), "w").write("log\\n")
report = {"pass": one["row"].get("pass", False), "caveat": "", "results": [dict(board=sys.argv[sys.argv.index("-b") + 1], **one["row"])],
          "reportPath": os.path.join(run_dir, "hil_report.json")}
open(report["reportPath"], "w").write(json.dumps(report))
print("noise", " ".join(sys.argv[1:]))
print(json.dumps(report), flush=True)
if one.get("hang"):
    open(os.environ["HIL_STAND_IN"] + ".pid", "w").write(str(os.getpid()))
    os.close(1); time.sleep(30)
sys.exit(one.get("exit", 0 if report["pass"] else 1))
'''


def completed(stdout='', code=0, stderr=''):
  return mock.Mock(returncode=code, stdout=stdout, stderr=stderr)


class Stubbed(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    self.state = self.tmp / 'state'
    self.out = self.state / 'run-1'
    self.roster = self.tmp / 'ci.json'
    self.roster.write_text(json.dumps({'boards': [{'name': BOARD}]}))
    self.stand_in = self.tmp / 'hil_test.py'
    self.stand_in.write_text(STAND_IN)
    self.spec = self.tmp / 'spec.json'
    self.build_ok = True
    self.commands = []
    mock.patch.object(hil_ci, 'HIL_TEST', self.stand_in).start()
    mock.patch.object(hil_ci, 'ROOT', self.tmp).start()
    mock.patch.object(hil_ci, 'run', self.fake_run).start()
    mock.patch.dict(os.environ, {'HIL_STAND_IN': str(self.spec)}).start()
    self.addCleanup(mock.patch.stopall)
    self.addCleanup(self.reap_hung_stand_in)

  def reap_hung_stand_in(self):
    """A stand-in left hanging as the in-process holder would be a stale hil_test.py on the host."""
    pid_file = self.spec.with_suffix('.json.pid')
    if pid_file.exists():
      pid = int(pid_file.read_text())
      os.kill(pid, 9)
      os.waitpid(pid, 0)

  def fake_run(self, cmd):
    cmd = [str(c) for c in cmd]
    self.commands.append(cmd)
    assert cmd[1].endswith('check_build.py'), cmd
    row = {'board': BOARD, 'status': 'ok' if self.build_ok else 'failed', 'firstError': '' if self.build_ok else 'boom'}
    return completed(json.dumps({'pass': self.build_ok, 'boards': [row]}))

  def main(self, *argv, battery=None, out=None):
    self.spec.write_text(json.dumps(battery or {}))
    with mock.patch.object(sys, 'stdout', io.StringIO()):
      return hil_ci.main(['--roster', 'ci.json', '--out', str(out or self.out), *argv])

  def rows(self, out=None):
    return json.loads(((out or self.out) / 'summary.json').read_text())['boards']

  def test_a_passing_battery_is_a_pass_with_its_run_directory_and_output_kept(self):
    ok = {'row': {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}}}
    self.assertEqual(self.main('--board', BOARD, '--lock-wait', '7', battery=ok), 0)
    self.assertEqual(self.rows()[0]['verdict'], 'pass')
    where = self.out / BOARD
    self.assertTrue(all((where / f).is_file() for f in ('stdout.txt', 'stderr.txt', 'run-1/hil_report.json', 'run-1/hil.log')))
    argv = (where / 'stdout.txt').read_text().splitlines()[0].split()
    self.assertEqual(argv[argv.index('--lock-wait') + 1], '7')
    self.assertTrue((self.out / f'{BOARD}.started').exists() and (self.out / f'{BOARD}.done').exists())
    self.assertTrue((self.out / f'{BOARD}.build.json').is_file())

  def test_a_failed_step_is_a_fail(self):
    failed = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True},
                                                            {'step': 'dfu', 'pass': False, 'detail': 'not seen'}],
                      'cleanup': {'pass': True, 'state': 'blinky copied'}}}
    self.assertEqual(self.main('--board', BOARD, battery=failed), 1)
    r = self.rows()[0]
    self.assertEqual((r['verdict'], r['detail']), ('fail', 'dfu: not seen'))
    self.assertTrue((self.out / f'{BOARD}.done').exists())   # finished, with a report and no holder

  def test_a_board_held_past_the_wait_is_not_run_and_a_cleanup_holder_a_blocker(self):
    for blocker, want in ((False, 'not-run'), (True, 'blocker')):
      with self.subTest(want):
        out = self.state / want
        locked = {'row': {'ran': False, 'locked': True, 'recoveryBlocker': blocker, 'detail': 'board locked: pid 7'}}
        self.assertEqual(self.main('--board', BOARD, battery=locked, out=out), 1 if want == 'not-run' else 2)
        self.assertEqual(self.rows(out)[0]['verdict'], want)
        self.assertEqual((out / f'{BOARD}.done').exists(), want == 'not-run')

  def test_a_failed_cleanup_is_a_blocker_that_keeps_its_marker_and_blocks_the_next_run(self):
    held = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True}],
                    'cleanup': {'pass': False, 'state': 'blinky copied', 'heldAfter': True, 'holder': {'pid': 9}}},
            'exit': 4}
    self.assertEqual(self.main('--board', BOARD, battery=held), 2)
    self.assertTrue((self.out / f'{BOARD}.started').exists())
    self.assertFalse((self.out / f'{BOARD}.done').exists())
    later = self.state / 'run-2'
    self.assertEqual(self.main('--board', BOARD, battery=held, out=later), 2)
    r = self.rows(later)[0]
    self.assertIn('run-1', r['detail'])
    self.assertFalse((later / BOARD).exists())   # no battery ran

  def test_a_holder_kept_in_process_is_not_waited_for(self):
    held = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True}],
                    'cleanup': {'pass': False, 'state': 'blinky copied', 'heldAfter': True,
                                'holder': {'pid': 9, 'inProcess': True}}},
            'hang': True}
    t0 = time.monotonic()
    self.assertEqual(self.main('--board', BOARD, battery=held), 2)
    self.assertLess(time.monotonic() - t0, 20)
    self.assertEqual(self.rows()[0]['verdict'], 'blocker')
    self.assertFalse((self.out / f'{BOARD}.done').exists())

  def test_a_run_without_a_report_is_a_blocker(self):
    self.assertEqual(hil_ci.verdict(137, None, BOARD)[0], 'blocker')
    self.assertEqual(hil_ci.verdict(1, {'results': []}, BOARD)[0], 'blocker')
    self.assertEqual(hil_ci.verdict(1, {'results': [{'board': BOARD, 'ran': None, 'pass': False}]}, BOARD)[0], 'blocker')

  def test_a_refusal_before_hardware_and_an_untouched_failure_are_not_run_and_a_used_probe_a_blocker(self):
    self.assertEqual(hil_ci.verdict(2, {'results': [{'board': BOARD, 'ran': False, 'detail': 'no probe'}]}, BOARD),
                     ('not-run', 'no probe'))
    self.assertEqual(hil_ci.verdict(2, {'results': [{'board': BOARD, 'ran': False, 'probeUsers': [5], 'detail': 'p'}]}, BOARD),
                     ('blocker', 'p'))
    row = {'board': BOARD, 'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': False, 'detail': 'x'}],
           'cleanup': {'pass': True, 'state': 'untouched'}}
    self.assertEqual(hil_ci.verdict(1, {'results': [row]}, BOARD)[0], 'not-run')
    row['steps'] = []
    self.assertEqual(hil_ci.verdict(1, {'results': [row]}, BOARD)[0], 'blocker')   # an abort

  def test_a_failed_build_is_not_run_and_touches_nothing(self):
    self.build_ok = False
    self.assertEqual(self.main('--board', BOARD), 1)
    r = self.rows()[0]
    self.assertEqual(r['verdict'], 'not-run')
    self.assertIn('boom', r['detail'])
    self.assertFalse((self.out / f'{BOARD}.started').exists())

  def test_a_board_outside_the_roster_and_a_bad_step_are_usage_errors(self):
    with self.assertRaises(SystemExit), mock.patch.object(sys, 'stderr', io.StringIO()):
      self.main('--board', BOARD, 'frdm_k64f')
    with self.assertRaises(SystemExit), mock.patch.object(sys, 'stderr', io.StringIO()):
      self.main('--board', BOARD, '--fail-at', 'rm-rf')

  def test_the_fail_at_steps_are_the_runners(self):
    self.assertEqual(hil_ci.STEPS, (*ht.STEPS['esp'], 'cleanup'))

  def test_fail_at_reaches_the_battery(self):
    held = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True}],
                    'cleanup': {'pass': False, 'state': 'blinky copied', 'heldAfter': True}}, 'exit': 4}
    self.assertEqual(self.main('--board', BOARD, '--fail-at', 'cleanup', battery=held), 2)
    self.assertIn('--fail-at cleanup', (self.out / BOARD / 'stdout.txt').read_text())

  def test_launch_returns_the_report_the_exit_and_whether_the_runner_stayed_a_holder(self):
    def cmd(where):
      where.mkdir()
      return [sys.executable, self.stand_in, 'run', '-b', BOARD, '--run-root', where]
    self.spec.write_text(json.dumps({'row': {'ran': True, 'pass': True}}))
    report, code, held = hil_ci.launch(cmd(self.tmp / 'a'), self.tmp / 'a', BOARD)
    self.assertEqual((report['results'][0]['board'], code, held), (BOARD, 0, False))
    self.spec.write_text(json.dumps({'row': {'ran': True, 'cleanup': {'holder': {'pid': 9, 'inProcess': True}}},
                                     'hang': True}))
    report, code, held = hil_ci.launch(cmd(self.tmp / 'b'), self.tmp / 'b', BOARD)
    self.assertEqual((code, held), (None, True))
    self.assertTrue((self.tmp / 'b' / 'stdout.txt').read_text().endswith(json.dumps(report) + '\n'))

  def test_a_recovery_blocker_row_is_a_blocker_locked_or_not(self):
    for row in ({'ran': False, 'locked': True, 'recoveryBlocker': True, 'detail': 'stale record'},
                {'ran': False, 'locked': False, 'recoveryBlocker': True, 'detail': 'an unfinished attempt'}):
      self.assertEqual(hil_ci.verdict(1, {'results': [dict(row, board=BOARD)]}, BOARD)[0], 'blocker')

  def test_old_finished_runs_are_pruned_and_an_unfinished_one_is_kept_whatever_its_age(self):
    old = time.time() - 40 * 86400
    for name, done in (('run-old-done', True), ('run-old-held', False), ('run-new-held', False)):
      d = self.state / name
      d.mkdir(parents=True)
      (d / f'{BOARD}.started').touch()
      if done:
        (d / f'{BOARD}.done').touch()
      if 'old' in name:
        os.utime(d, (old, old))
    hil_ci.prune(self.state, keep=self.out)
    self.assertEqual(sorted(p.name for p in self.state.iterdir()), ['run-new-held', 'run-old-held'])


LPC = 'lpcxpresso55s69'
LPC_FACTS = {'flashBase': 0, 'binBase': 0, 'appStart': 0x10000, 'flashSize': 0x98000, 'vid': 0x1fc9, 'pid': 0x0094,
             'boardId': 'LPC55S69-Xpresso-revA', 'family': 0x2abc77ec, 'vectors': 76, 'ram': 0x20000000,
             'dblTapDelayMs': 500, 'dblTapReg': 0x4002C05C, 'dblTapMagic': 0xF01669EF}
# the real runner's main(), its lock taken through the pinned helper in a test lock dir; only admission and the probe
# steps are stand-ins, and HIL_BATTERY=die leaves the battery to be SIGKILLed mid-run
REAL_RUNNER = """
import importlib.util, json, os, sys, time
spec = importlib.util.spec_from_file_location('hil_test', os.environ['HIL_RUNNER'])
ht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ht)
ht.check_lock_pin = lambda: None
load = ht.load_helper


def load_helper():
  helper = load()
  helper.BOARD_LOCK_DIR = os.environ['HIL_LOCKS']
  return helper


def run(bat, files, version):
  bat.touched = True
  if os.environ['HIL_BATTERY'] == 'die':
    open(os.environ['HIL_PID'], 'w').write(str(os.getpid()))
    time.sleep(60)


ht.load_helper = load_helper
ht.source_facts = lambda board: json.loads(os.environ['HIL_FACTS'])
ht.admit_record = lambda *a: ({}, {'version': 'v'})
ht.probe_users = lambda board: []
ht.Battery.run = run
ht.Battery.restore = lambda bat, files, version: {'pass': True, 'state': 'blinky copied', 'evidence': {}}
sys.exit(ht.main(sys.argv[1:]))
"""


class RealRunner(unittest.TestCase):
  """hil_ci.py over the real `hil_test.py run` and the pinned lock helper: the protected battery lock as CI sees it."""

  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    self.state = self.tmp / 'state'
    self.out = self.state / 'run-1'
    (self.tmp / 'ci.json').write_text(json.dumps({'boards': [
      {'name': LPC, 'uid': 'UID', 'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0'},
       'tinyuf2': {'reentry': 'retained-register'}}]}))
    runner = self.tmp / 'hil_test.py'
    runner.write_text(REAL_RUNNER)
    locks = self.tmp / 'locks'
    locks.mkdir()
    self.pid_file = self.tmp / 'battery.pid'
    if not ht.LOCK_HELPER.is_file():
      self.fail('lib/agentrc not checked out: git submodule update --init lib/agentrc')
    with mock.patch.object(ht, 'check_lock_pin'):
      self.helper = ht.load_helper()
    self.helper.BOARD_LOCK_DIR = str(locks)
    self.env = {'HIL_RUNNER': str(Path(ht.__file__).resolve()), 'HIL_LOCKS': str(locks), 'HIL_PID': str(self.pid_file),
                'HIL_FACTS': json.dumps(LPC_FACTS)}
    mock.patch.object(hil_ci, 'HIL_TEST', runner).start()
    mock.patch.object(hil_ci, 'ROOT', self.tmp).start()
    mock.patch.object(hil_ci, 'run', lambda cmd: completed(json.dumps(
      {'pass': True, 'boards': [{'board': LPC, 'status': 'ok', 'firstError': ''}]}))).start()
    self.addCleanup(mock.patch.stopall)

  def main(self, battery, out, lock_wait):
    with mock.patch.dict(os.environ, dict(self.env, HIL_BATTERY=battery)), mock.patch.object(sys, 'stdout', io.StringIO()):
      return hil_ci.main(['--roster', 'ci.json', '--out', str(out), '--board', LPC, '--lock-wait', str(lock_wait)])

  def row(self, out):
    return json.loads((out / 'summary.json').read_text())['boards'][0]

  def test_a_clean_exit_releases_the_protected_lock(self):
    self.assertEqual(self.main('pass', self.out, 0), 0)
    self.assertEqual(self.row(self.out)['verdict'], 'pass')
    self.assertTrue((self.out / f'{LPC}.done').exists())
    self.assertEqual(self.helper.record_state(LPC)[0], 'empty')
    self.helper.release_board_lock(self.helper.take_board_lock(LPC, 'next'))

  def test_a_battery_killed_mid_run_leaves_a_blocker_the_next_run_reports_without_waiting(self):
    def kill_the_battery():
      end = time.monotonic() + 30
      while not self.pid_file.exists() and time.monotonic() < end:
        time.sleep(0.02)
      os.kill(int(self.pid_file.read_text()), signal.SIGKILL)
    killer = threading.Thread(target=kill_the_battery)
    killer.start()
    self.assertEqual(self.main('die', self.out, 0), 2)
    killer.join()
    row = self.row(self.out)
    self.assertEqual(row['verdict'], 'blocker')
    self.assertIn('without a report', row['detail'])
    self.assertFalse((self.out / f'{LPC}.done').exists())
    rec = self.helper.read_record(LPC)
    self.assertTrue(self.helper.is_recovery_blocker(rec))   # the shared helper's view: every project refuses the board
    self.assertEqual((rec['reason'], rec['protected']), ('hil_test.py', True))
    self.assertEqual(Path(rec['runDir']).parent, self.out / LPC)
    # a later CI run with no marker of its own (another state dir) meets the record: a blocker at once, never waited for
    later = self.tmp / 'state-2' / 'run-1'
    t0 = time.monotonic()
    self.assertEqual(self.main('pass', later, 600), 2)
    self.assertLess(time.monotonic() - t0, 20)
    row = self.row(later)
    self.assertEqual(row['verdict'], 'blocker')
    self.assertIn('stale record', row['detail'])
    self.assertFalse((later / f'{LPC}.done').exists())
    self.assertEqual(self.helper.read_record(LPC), rec)



if __name__ == '__main__':
  unittest.main()
