#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The CI job's orchestration of the battery (hil_ci.py): selection, pre-flight, record, attempts, verdicts,
# markers, pruning and the exit. check_build and pgrep are stubbed; the battery is a stand-in script that prints
# a canned report, so the streaming, the report copy and the in-process holder path run for real.
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'))
import hil_ci  # noqa: E402

BOARD = 'imxrt1064_evk'

STAND_IN = '''
import json, os, sys, time
spec = json.load(open(os.environ["HIL_STAND_IN"]))
i = int(open(os.environ["HIL_STAND_IN"] + ".n").read() or 0) if os.path.exists(os.environ["HIL_STAND_IN"] + ".n") else 0
open(os.environ["HIL_STAND_IN"] + ".n", "w").write(str(i + 1))
one = spec[min(i, len(spec) - 1)]
run_dir = os.environ["HIL_STAND_IN"] + "-run"
os.makedirs(run_dir, exist_ok=True)
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
    self.tmp = Path(tempfile.mkdtemp())
    self.state = self.tmp / 'state'
    self.out = self.state / 'run-1'
    self.roster = self.tmp / 'ci.json'
    self.roster.write_text(json.dumps({'boards': [{'name': BOARD}]}))
    self.stand_in = self.tmp / 'hil_test.py'
    self.stand_in.write_text(STAND_IN)
    self.spec = self.tmp / 'spec.json'
    self.pgrep = {}
    self.build_ok = True
    self.selection = {'boards': [BOARD], 'full': True, 'uncovered': []}
    self.commands = []
    mock.patch.object(hil_ci, 'HIL_TEST', self.stand_in).start()
    mock.patch.object(hil_ci, 'ROOT', self.tmp).start()
    mock.patch.object(hil_ci, 'run', self.fake_run).start()
    mock.patch.object(hil_ci.time, 'sleep').start()
    mock.patch.dict(os.environ, {'HIL_STAND_IN': str(self.spec)}).start()
    self.addCleanup(mock.patch.stopall)
    self.addCleanup(self.reap_hung_stand_in)

  def reap_hung_stand_in(self):
    """A stand-in left hanging as the in-process holder would match the real pre-flight's pgrep."""
    pid_file = self.spec.with_suffix('.json.pid')
    if pid_file.exists():
      pid = int(pid_file.read_text())
      os.kill(pid, 9)
      os.waitpid(pid, 0)

  def fake_run(self, cmd, **kw):
    cmd = [str(c) for c in cmd]
    self.commands.append(cmd)
    if cmd[0] == 'pgrep':
      hit = self.pgrep.get(cmd[-1])
      return completed(hit or '', 0 if hit else 1) if not isinstance(hit, int) else completed('', hit, 'pgrep: boom')
    assert cmd[1].endswith('check_build.py'), cmd
    if '--select-only' in cmd:
      return completed(json.dumps({'hil': self.selection}))
    row = {'board': BOARD, 'status': 'ok' if self.build_ok else 'failed', 'firstError': '' if self.build_ok else 'boom'}
    return completed(json.dumps({'pass': self.build_ok, 'boards': [row]}))

  def main(self, *argv, batteries=(), out=None):
    self.spec.write_text(json.dumps(list(batteries)))
    (self.spec.parent / 'spec.json.n').unlink(missing_ok=True)
    with mock.patch.object(sys, 'stdout', io.StringIO()):
      return hil_ci.main(['--roster', 'ci.json', '--out', str(out or self.out), *argv])

  def rows(self, out=None):
    return json.loads(((out or self.out) / 'summary.json').read_text())['boards']

  def test_a_passing_battery_is_a_pass_with_its_output_report_and_log_kept(self):
    ok = {'row': {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}}}
    self.assertEqual(self.main('--board', BOARD, batteries=[ok]), 0)
    self.assertEqual((self.rows()[0]['verdict'], self.rows()[0]['attempts']), ('pass', 1))
    attempt = self.out / BOARD / 'attempt-1'
    self.assertTrue(all((attempt / f).is_file() for f in ('stdout.txt', 'stderr.txt', 'hil_report.json', 'hil.log')))
    self.assertIn('noise', (attempt / 'stdout.txt').read_text())
    self.assertTrue((self.out / f'{BOARD}.started').exists() and (self.out / f'{BOARD}.done').exists())
    self.assertTrue((self.out / f'{BOARD}.build.json').is_file())

  def test_a_failed_step_is_a_fail_and_a_locked_board_is_retried_within_the_wait(self):
    locked = {'row': {'ran': False, 'locked': True, 'detail': 'board locked: pid 7 tinyusb'}}
    failed = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True},
                                                            {'step': 'dfu', 'pass': False, 'detail': 'not seen'}],
                      'cleanup': {'pass': True, 'state': 'blinky copied'}}}
    self.assertEqual(self.main('--board', BOARD, '--lock-wait', '100', batteries=[locked, failed]), 1)
    r = self.rows()[0]
    self.assertEqual((r['verdict'], r['attempts'], r['detail']), ('fail', 2, 'dfu: not seen'))
    self.assertTrue((self.out / BOARD / 'attempt-2' / 'hil_report.json').is_file())

  def test_a_board_locked_past_the_wait_is_not_run_never_a_pass(self):
    locked = {'row': {'ran': False, 'locked': True, 'detail': 'board locked: pid 7 tinyusb'}}
    with mock.patch.object(hil_ci.time, 'monotonic', side_effect=[0, 0, 800]):   # deadline 700: one retry
      self.assertEqual(self.main('--board', BOARD, '--lock-wait', '700', batteries=[locked, locked]), 1)
    r = self.rows()[0]
    self.assertEqual((r['verdict'], r['attempts']), ('not-run', 2))
    self.assertIn('locked', r['detail'])
    self.assertTrue((self.out / f'{BOARD}.done').exists())

  def test_a_failed_cleanup_is_a_blocker_that_keeps_its_marker_and_blocks_the_next_run(self):
    held = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True}],
                    'cleanup': {'pass': False, 'state': 'blinky copied', 'heldAfter': True, 'holder': {'pid': 9}}},
            'exit': 4}
    self.assertEqual(self.main('--board', BOARD, batteries=[held]), 2)
    self.assertTrue((self.out / f'{BOARD}.started').exists())
    self.assertFalse((self.out / f'{BOARD}.done').exists())
    later = self.state / 'run-2'
    self.assertEqual(self.main('--board', BOARD, batteries=[held], out=later), 2)
    r = self.rows(later)[0]
    self.assertEqual(r['attempts'], 0)
    self.assertIn('run-1', r['detail'])
    self.assertFalse((later / BOARD).exists())   # no battery ran

  def test_a_holder_kept_in_process_is_not_waited_for(self):
    held = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True}],
                    'cleanup': {'pass': False, 'state': 'blinky copied', 'heldAfter': True,
                                'holder': {'pid': 9, 'inProcess': True}}},
            'hang': True}
    t0 = time.monotonic()
    self.assertEqual(self.main('--board', BOARD, batteries=[held]), 2)
    self.assertLess(time.monotonic() - t0, 20)
    self.assertEqual(self.rows()[0]['verdict'], 'blocker')
    self.assertFalse((self.out / f'{BOARD}.done').exists())

  def test_a_run_without_a_report_is_a_blocker(self):
    self.assertEqual(hil_ci.verdict(137, None, BOARD)[0], 'blocker')
    self.assertEqual(hil_ci.verdict(1, {'results': []}, BOARD)[0], 'blocker')
    self.assertEqual(hil_ci.verdict(1, {'results': [{'board': BOARD, 'ran': None, 'pass': False}]}, BOARD)[0], 'blocker')

  def test_a_refusal_before_hardware_and_an_untouched_failure_are_not_run(self):
    self.assertEqual(hil_ci.verdict(2, {'results': [{'board': BOARD, 'ran': False, 'detail': 'no probe'}]}, BOARD),
                     ('not-run', 'no probe', False))
    row = {'board': BOARD, 'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': False, 'detail': 'x'}],
           'cleanup': {'pass': True, 'state': 'untouched'}}
    self.assertEqual(hil_ci.verdict(1, {'results': [row]}, BOARD)[0], 'not-run')
    row['steps'] = []
    self.assertEqual(hil_ci.verdict(1, {'results': [row]}, BOARD)[0], 'blocker')   # an abort

  def test_leftover_processes_or_a_pgrep_that_cannot_look_block_every_board_before_any_battery(self):
    ok = {'row': {'ran': True, 'pass': True, 'cleanup': {'pass': True}}}
    for what, hit in (('a battery left', '123 python3 hil_test.py run -b x\n'), ('pgrep error', 3)):
      with self.subTest(what):
        self.pgrep = {r'[h]il_test\.py': hit}
        out = self.state / what.replace(' ', '-')
        self.assertEqual(self.main('--board', BOARD, batteries=[ok], out=out), 2)
        self.assertFalse((out / BOARD).exists())
        self.assertIn('host not ready', self.rows(out)[0]['detail'])

  def test_a_failed_build_is_not_run_and_touches_nothing(self):
    self.build_ok = False
    self.assertEqual(self.main('--board', BOARD), 1)
    r = self.rows()[0]
    self.assertEqual(r['verdict'], 'not-run')
    self.assertIn('boom', r['detail'])
    self.assertFalse((self.out / f'{BOARD}.started').exists())

  def test_the_selection_drives_the_boards_and_uncovered_reaches_the_summary(self):
    self.selection = {'boards': [], 'full': False,
                      'uncovered': [{'target': 'ports/espressif/boards/x/board.h', 'reason': 'no ci.json board'}]}
    summary = self.tmp / 'summary.md'
    with mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}):
      self.assertEqual(self.main('--base', 'HEAD^1'), 0)
    self.assertIn('no ci.json board', summary.read_text())
    self.assertFalse((self.out / BOARD).exists())
    self.assertEqual(self.commands[0][2:5], ['--select-only', '--base', 'HEAD^1'])

  def test_a_board_outside_the_roster_and_a_bad_step_are_usage_errors(self):
    with self.assertRaises(SystemExit), mock.patch.object(sys, 'stderr', io.StringIO()):
      self.main('--board', 'frdm_k64f')
    with self.assertRaises(SystemExit), mock.patch.object(sys, 'stderr', io.StringIO()):
      self.main('--board', BOARD, '--fail-at', 'rm-rf')

  def test_fail_at_reaches_the_battery(self):
    held = {'row': {'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True}],
                    'cleanup': {'pass': False, 'state': 'blinky copied', 'heldAfter': True}}, 'exit': 4}
    self.assertEqual(self.main('--board', BOARD, '--fail-at', 'cleanup', batteries=[held]), 2)
    self.assertIn('--fail-at cleanup', (self.out / BOARD / 'attempt-1' / 'stdout.txt').read_text())

  def test_old_finished_runs_are_pruned_and_an_unfinished_one_is_kept_whatever_its_age(self):
    old = time.time() - 40 * 86400
    for name, done in (('run-old-done', True), ('run-old-held', False), ('run-new-held', False), ('orphans', None)):
      d = self.state / name
      d.mkdir(parents=True)
      if done is not None:
        (d / f'{BOARD}.started').touch()
      if done:
        (d / f'{BOARD}.done').touch()
      if 'new' not in name:
        os.utime(d, (old, old))
    hil_ci.prune(self.state, keep=self.out)
    self.assertEqual(sorted(p.name for p in self.state.iterdir()), ['orphans', 'run-new-held', 'run-old-held'])


if __name__ == '__main__':
  unittest.main()
