#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The CI job's orchestration of the battery (hil_ci.py): record, one run per board, verdicts, markers, pruning
# and the exit. check_build is stubbed; the battery is a stand-in script that prints a canned report into the run
# root it is given, so the streaming, the run directory and the in-process holder path run for real.
import contextlib
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
import hil_run_report as run_report  # noqa: E402
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
report.update(one.get("report", {}))
doc = json.dumps(dict(report, _hil=one["meta"]) if "meta" in one else report)
# a run interrupted between its JSON and Markdown replacement: the JSON cut short, or an earlier Markdown left
open(report["reportPath"], "w").write(doc[:one["cut"]] if "cut" in one else doc)
if "md" in one:
    open(os.path.join(run_dir, "hil_report.md"), "w").write(one["md"])
print("noise", " ".join(sys.argv[1:]))
print(json.dumps(report), flush=True)
if one.get("hang"):
    open(os.environ["HIL_STAND_IN"] + ".pid", "w").write(str(os.getpid()))
    os.close(1); time.sleep(30)
sys.exit(one.get("exit", 0 if report["pass"] else 1))
'''


# hil_ci.verdict() before it moved into the report adapter (tinyuf2 dbe43d3), over the report core's tinyuf2 inputs
# (lib/agentrc tests/data/hil_report_core/inputs.json) and phase A's unfinished-attempt row: (exit, report, verdict)
HELD_ROW = {'board': 'B', 'ran': True, 'pass': False, 'steps': [{'step': 'install', 'pass': True}]}
GOLDEN = {
  'no_report': (137, None, ('blocker', 'run ended without a report (exit 137)')),
  'no_row': (1, {'results': [], 'error': 'boom'}, ('blocker', 'report has no row for B (exit 1): boom')),
  'ran_none': (1, {'results': [{'board': 'B', 'ran': None, 'pass': False}]},
               ('blocker', 'cleanup failed or no report; board held: None {}')),
  'refused_before_hardware': (2, {'results': [{'board': 'B', 'ran': False, 'detail': 'no probe'}]}, ('not-run', 'no probe')),
  'probe_users': (2, {'results': [{'board': 'B', 'ran': False, 'probeUsers': [5], 'detail': 'p'}]}, ('blocker', 'p')),
  'untouched_failure': (1, {'results': [{'board': 'B', 'ran': True, 'pass': False,
                                         'steps': [{'step': 'install', 'pass': False, 'detail': 'x'}],
                                         'cleanup': {'pass': True, 'state': 'untouched'}}]},
                        ('not-run', 'install: x (nothing written)')),
  'abort_without_failed_step': (1, {'results': [{'board': 'B', 'ran': True, 'pass': False, 'steps': [],
                                                 'cleanup': {'pass': True, 'state': 'untouched'}}]},
                                ('blocker', 'aborted: None')),
  'held_after_cleanup': (4, {'results': [dict(HELD_ROW, cleanup={'pass': False, 'state': 'blinky copied', 'heldAfter': True,
                                                                 'holder': {'pid': 9}})]},
                         ('blocker', "cleanup failed or no report; board held: None {'pass': False, 'state': 'blinky "
                                     "copied', 'heldAfter': True, 'holder': {'pid': 9}}")),
  'in_process_holder': (None, {'results': [dict(HELD_ROW, cleanup={'pass': False, 'heldAfter': True,
                                                                   'holder': {'pid': 9, 'inProcess': True}})]},
                        ('blocker', "cleanup failed or no report; board held: None {'pass': False, 'heldAfter': True, "
                                    "'holder': {'pid': 9, 'inProcess': True}}")),
  'locked': (1, {'results': [{'board': 'B', 'ran': False, 'pass': False, 'locked': True, 'recoveryBlocker': False,
                              'detail': 'held by pid 7'}]}, ('not-run', 'locked: held by pid 7')),
  'locked_recovery_blocker': (1, {'results': [{'board': 'B', 'ran': False, 'pass': False, 'locked': True,
                                               'recoveryBlocker': True, 'detail': 'cleanup holder 8'}]},
                              ('blocker', 'locked: cleanup holder 8')),
  'pass': (0, {'results': [{'board': 'B', 'ran': True, 'pass': True, 'steps': [{'step': 'install', 'pass': True}],
                            'cleanup': {'pass': True, 'state': 'blinky copied', 'heldAfter': False}}]}, ('pass', '')),
  'fail_after_write': (1, {'results': [{'board': 'B', 'ran': True, 'pass': False,
                                        'steps': [{'step': 'install', 'pass': True},
                                                  {'step': 'copy', 'pass': False, 'detail': 'drive vanished'}],
                                        'cleanup': {'pass': True, 'state': 'blinky copied', 'heldAfter': False}}]},
                       ('fail', 'copy: drive vanished')),
  'unfinished_attempt': (1, {'results': [{'board': 'B', 'ran': False, 'pass': False, 'locked': False, 'recoveryBlocker': True,
                                          'unfinishedAttempts': ['r1'], 'detail': 'CI run r1 has no .done'}]},
                         ('blocker', 'CI run r1 has no .done')),
}


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

  def test_the_verdicts_are_the_report_adapters_and_unchanged(self):
    self.assertIs(hil_ci.verdict, run_report.verdict)
    for name, (code, report, want) in GOLDEN.items():
      with self.subTest(name):
        self.assertEqual(hil_ci.verdict(code, report, 'B'), want)

  def test_a_report_the_battery_could_not_publish_is_named_in_the_summary(self):
    ok = {'row': {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}},
          'report': {'reportError': 'report not published: ReportError: replace: disk full'}}
    self.assertEqual(self.main('--board', BOARD, battery=ok), 0)   # the run's own outcome stands
    r = self.rows()[0]
    self.assertEqual((r['verdict'], r['reportError']), ('pass', ok['report']['reportError']))

  def meta(self, termination='completed'):
    core = run_report.load_core(hil_ci.REPORT_CORE)
    return core.make_meta(run_report.schema(core), core.Attempt('run-1', None, None, None, None), termination=termination,
                          invocation=['hil_test.py', 'run'], selection=[BOARD], host='h', roster={'path': 'ci.json'})

  def test_the_shared_run_rules_tighten_the_native_verdict_and_never_decide_the_exit(self):
    passed = {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}}
    waited = {'ran': False, 'pass': False, 'locked': True, 'recoveryBlocker': False,
              'detail': 'board locked: pid 7; interrupted by SIGTERM while waiting for the lock'}
    for what, battery, exit_, native, shared, why in (
        ('a pass', {'row': passed, 'meta': self.meta()}, 0, 'pass', 'pass', ''),
        ('a lock wait a signal aborted', {'row': waited, 'meta': self.meta('aborted')}, 1, 'not-run', 'blocker',
         'run aborted'),
        ('a pass under a run caveat', {'row': passed, 'report': {'caveat': 'probe firmware unverified'},
                                       'meta': self.meta()}, 0, 'pass', 'blocker', 'run caveat denies a pass'),
        ('a legacy report', {'row': passed}, 0, 'pass', 'pass', '')):
      with self.subTest(what):
        out = self.state / what.replace(' ', '-')
        self.assertEqual(self.main('--board', BOARD, battery=battery, out=out), exit_)
        r = self.rows(out)[0]
        self.assertEqual((r['verdict'], r['sharedVerdict']), (native, shared))
        self.assertIn(why, r['sharedDetail'])

  def test_the_report_pair_is_prepared_before_the_upload_and_never_left_stale(self):
    passed = {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}}
    core = run_report.load_core(hil_ci.REPORT_CORE)
    for what, battery, md_starts, shared in (
        ('the Markdown never replaced', {'row': passed, 'meta': self.meta()}, 'HIL run: pass\n', 'pass'),
        ('an earlier Markdown left', {'row': passed, 'meta': self.meta(), 'md': 'HIL run: fail\n'}, 'HIL run: pass\n',
         'pass'),
        ('the JSON cut short', {'row': passed, 'meta': self.meta(), 'cut': 40, 'md': 'HIL run: pass\n'}, core.NOTICE,
         'blocker')):
      with self.subTest(what):
        out = self.state / what.replace(' ', '-')
        self.assertEqual(self.main('--board', BOARD, battery=battery, out=out), 0)   # the battery's own exit stands
        md = (out / BOARD / 'run-1' / 'hil_report.md').read_text(encoding='utf-8')
        self.assertTrue(md.startswith(md_starts), md)
        if 'md' in battery and 'cut' in battery:   # the earlier view is kept only as labelled legacy text
          self.assertIn('_Legacy text:', md)
        r = self.rows(out)[0]
        self.assertEqual((r['verdict'], r['sharedVerdict']), ('pass', shared))
        self.assertTrue((out / f'{BOARD}.done').exists())

  def test_a_battery_that_left_no_run_dir_gets_a_blocker(self):
    self.assertEqual(hil_ci.prepare(0, self.tmp / 'nowhere', BOARD)['sharedVerdict'], 'blocker')

  def test_a_failed_preparation_withholds_the_runs_markdown_and_keeps_the_native_outcome(self):
    core = run_report.load_core(hil_ci.REPORT_CORE)
    self.assertEqual(hil_ci.NOTICE, core.NOTICE)
    broken = run_report.load_core(hil_ci.REPORT_CORE)   # a module of its own, so the patch stays here

    def boom(*a):
      raise OSError(5, 'Input/output error')
    broken.prepare_pair = boom
    ok = {'row': {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}}, 'md': 'HIL run: pass\n'}
    for what, failure, err in (
        ('the core does not load', mock.patch.object(hil_ci, 'REPORT_CORE', self.tmp / 'missing.py'), 'missing.py'),
        ('the preparation raises', mock.patch.object(hil_ci.run_report, 'load_core', lambda p: broken), 'Input/output')):
      with self.subTest(what):
        out = self.state / what.replace(' ', '-')
        with failure:
          self.assertEqual(self.main('--board', BOARD, battery=ok, out=out), 0)
        r = self.rows(out)[0]
        self.assertEqual((r['verdict'], r['sharedVerdict']), ('pass', 'blocker'))
        self.assertIn('report not prepared', r['sharedDetail'])
        self.assertIn(err, r['sharedDetail'])
        self.assertTrue((out / f'{BOARD}.done').exists())
        md = (out / BOARD / 'run-1' / 'hil_report.md').read_text(encoding='utf-8')
        head, _, kept = md.partition('_Legacy text:')
        self.assertTrue(head.startswith(core.NOTICE) and 'HIL run: pass' not in head, md)   # the pass view, unchecked,
        self.assertIn('HIL run: pass', kept)                                                # only as labelled text

  def test_a_view_that_can_be_neither_replaced_nor_removed_is_named_unsafe_for_the_upload(self):
    ok = {'row': {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}}, 'md': 'HIL run: pass\n'}
    write_text, unlink = Path.write_text, Path.unlink

    def denied(real):
      def op(path, *a, **k):
        if path.name in ('hil_report.md', '.hil_report.md.withheld'):   # a run dir turned read-only
          raise PermissionError(13, 'Permission denied', str(path))
        return real(path, *a, **k)
      return op
    with mock.patch.object(hil_ci, 'REPORT_CORE', self.tmp / 'missing.py'), \
         mock.patch.object(Path, 'write_text', denied(write_text)), mock.patch.object(Path, 'unlink', denied(unlink)):
      self.assertEqual(self.main('--board', BOARD, battery=ok), 0)   # the battery's exit and markers stand
    md = self.out / BOARD / 'run-1' / 'hil_report.md'
    self.assertEqual(md.read_text(), 'HIL run: pass\n')
    r = self.rows()[0]
    self.assertEqual((r['verdict'], r['sharedVerdict'], r['unsafeArtifacts']), ('pass', 'blocker', [str(md)]))
    self.assertTrue((self.out / f'{BOARD}.done').exists())
    self.assertIn(f'(not uploaded: {md})', hil_ci.summary([r], 'ci.json'))

  def test_the_summary_labels_the_native_verdict_and_shows_the_shared_one_where_it_differs(self):
    passed = {'ran': True, 'pass': True, 'cleanup': {'pass': True, 'state': 'blinky copied'}}
    step_summary = self.tmp / 'step-summary.md'
    for what, battery, patch, shared in (
        ('a pass', {'row': passed, 'meta': self.meta()}, contextlib.nullcontext(), ''),
        ('a pass under a run caveat', {'row': passed, 'report': {'caveat': 'probe | unverified'}, 'meta': self.meta()},
         contextlib.nullcontext(), 'blocker: run caveat denies a pass: probe / unverified'),
        ('an unprepared report', {'row': passed}, mock.patch.object(hil_ci, 'REPORT_CORE', self.tmp / 'missing.py'),
         'blocker: report not prepared')):
      with self.subTest(what), patch, mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(step_summary)}):
        step_summary.write_text('')
        out = self.state / what.replace(' ', '-')
        stdout = io.StringIO()
        self.spec.write_text(json.dumps(battery))
        with mock.patch.object(sys, 'stdout', stdout):
          self.assertEqual(hil_ci.main(['--roster', 'ci.json', '--out', str(out), '--board', BOARD]), 0)
        text = stdout.getvalue()
        self.assertEqual(step_summary.read_text(), text)
        self.assertIn('| board | native verdict | detail | shared run rules |', text)
        line = text.splitlines()[-1]
        self.assertTrue(line.startswith(f'| {BOARD} | pass |  | {shared}'), line)
        if not shared:
          self.assertTrue(line.endswith('|  |'), line)
    blocked = {'board': BOARD, 'verdict': 'blocker', 'detail': 'held', 'sharedVerdict': 'blocker'}
    lines = hil_ci.summary([dict(blocked, sharedDetail='run aborted: held'),
                            dict(blocked, sharedDetail='report not prepared: OSError: x')], 'ci.json').splitlines()
    self.assertEqual(lines[-2:], [f'| {BOARD} | blocker | held |  |',   # the same verdict: nothing more to show
                                  f'| {BOARD} | blocker | held | blocker: report not prepared: OSError: x |'])

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
    # the run dir's report pair, published through the pinned report core, gives the same verdict from the file alone
    run_dir, = (self.out / LPC).glob('run-*')
    with mock.patch.object(ht, 'check_lock_pin'):
      core = ht.report_core()
    reading = core.read_document(run_dir / 'hil_report.json', run_report.schema(core))
    self.assertEqual((reading.outcome, reading.meta['attempt_id'], reading.body['exitCode']), ('valid', run_dir.name, 0))
    self.assertEqual(run_report.verdict(run_report.exit_of(reading.body), reading.body, LPC), ('pass', ''))
    self.assertTrue((run_dir / 'hil_report.md').read_text(encoding='utf-8').startswith('HIL run: pass\n'))
    self.assertEqual(self.row(self.out)['sharedVerdict'], 'pass')
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
    run_dir, = (self.out / LPC).glob('run-*')   # the dead battery's dir uploads an explicit notice, no view
    self.assertTrue((run_dir / 'hil_report.md').read_text(encoding='utf-8').startswith(
      run_report.load_core(hil_ci.REPORT_CORE).NOTICE))
    self.assertIn('report missing', row['sharedDetail'])
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
