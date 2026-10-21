#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The HIL workflow's sticky PR comment (hil_comment.py): the body rendered from summary.json and the selection, the
# freshness check over a stubbed API, and the workflow's fresh step run as the runner runs it over a stand-in `gh`.
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import hil_comment as hc  # noqa: E402

META = {'roster': 'ci.json', 'head': '4f1c2e9aaaaaaaaa', 'tested': '8a7d3b0bbbbbbbbb',
        'runUrl': 'https://github.com/o/r/actions/runs/39512345678/attempts/1', 'runId': '39512345678', 'attempt': '1'}
OK = {s: True for s in ('install', 'dfu', 'copy', 'app-ran', 'reenter')}


def row(board, verdict='pass', shared='pass', **kw):
  r = {'board': board, 'phase': 'battery', 'verdict': verdict, 'detail': '', 'sharedVerdict': shared,
       'sharedDetail': '', 'steps': dict(OK), 'cleanupPass': True, 'buildS': 40, 'runS': 15}
  return {k: v for k, v in dict(r, **kw).items() if v is not None}


def selection(n=1, full=False, uncovered=()):
  return {'boards': [f'b{i}' for i in range(n)], 'full': full, 'uncovered': list(uncovered)}


def lines(text):
  return text.splitlines()


class Render(unittest.TestCase):
  def test_the_approved_shape(self):
    rows = [row('imxrt1064_evk', buildS=49, runS=22),
            row('espressif_p4_function_ev', steps=dict(OK, recopy=True), espressif=True, buildS=270, runS=160),
            row('stm32h743nucleo', 'fail', 'fail', detail='copy: CURRENT.UF2 read-back differs at block 12',
                steps={'install': True, 'dfu': True, 'copy': False})]
    sel = selection(3, full=True, uncovered=[{'target': 'ports/ch32v20x', 'reason': 'no roster board on this host'}])
    self.assertEqual(hc.render({'boards': rows, 'elapsedS': 1200}, sel, META), textwrap.dedent('''\
      ## Hardware-in-the-loop (HIL) Test Report

      ### ci.json (ci.lan)

      _PR head `4f1c2e9` · tested `8a7d3b0` · [run 39512345678, attempt 1](https://github.com/o/r/actions/runs/39512345678/attempts/1)_

      _Every roster board: the HIL runner or a roster changed (3 boards)._

      **✅ 2 passed · ❌ 1 failed** · HIL driver elapsed 20m

      | Board | install | dfu | copy | app-ran | reenter | recopy | blinky | build | run |
      | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --: | --: |
      | imxrt1064_evk | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | 49s | 22s |
      | espressif_p4_function_ev | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 4m30s | 2m40s |
      | stm32h743nucleo | ✅ | ✅ | ❌ |  |  | — | ✅ | 40s | 15s |

      ✅ passed · ❌ failed · blank not run · — not in this board's run · run time includes lock wait and blinky

      - `stm32h743nucleo` copy: CURRENT.UF2 read-back differs at block 12

      Not covered on this rig:
      - `ports/ch32v20x`: no roster board on this host

      _[Records, reports and logs](https://github.com/o/r/actions/runs/39512345678/attempts/1)_
      '''))

  def test_mixed_outcomes_are_counted_by_both_verdicts_and_noted(self):
    rows = [row('a'),
            row('b', 'fail', 'fail', detail='dfu: not seen', steps={'install': True, 'dfu': False}),
            row('c', 'blocker', 'blocker', cleanupPass=False, detail='cleanup failed or no report; board held'),
            row('d', 'not-run', 'not-run', steps={}, cleanupPass=None, detail='locked: held by pid 7'),
            row('e', 'pass', 'blocker', sharedDetail='run caveat denies a pass')]
    body = hc.render({'boards': rows}, selection(5), META)
    self.assertIn('\n**✅ 1 passed · ❌ 1 failed · ⛔ 2 blocked · ⚪ 1 not run**\n', body)   # no elapsed: none given
    self.assertIn('_Boards the change reaches: 5._', body)
    notes = [ln for ln in lines(body) if ln.startswith('- `')]
    self.assertEqual(notes, ['- `b` dfu: not seen',
                             '- `c` blinky: cleanup failed or no report; board held',
                             '- `d` battery: locked: held by pid 7',
                             '- `e` battery: run caveat denies a pass (native pass, shared run rules blocker)'])
    self.assertNotIn('verdict', body)
    self.assertIn('| d |  |  |  |  |  |  |  | 40s | 15s |', body)   # no steps: every step cell blank

  def test_recopy_is_absent_on_a_non_espressif_battery_and_blank_with_no_steps(self):
    rows = [row('esp', steps=dict(OK, recopy=False), espressif=True), row('arm'),
            row('esp2', 'fail', 'fail', steps={'install': True, 'dfu': False}, espressif=True),
            {'board': 'pre', 'phase': 'preflight', 'verdict': 'blocker', 'detail': 'run r1 never finished'}]
    table = [ln for ln in lines(hc.render({'boards': rows}, selection(3), META)) if ln.startswith('| ')]
    self.assertEqual(table[2:], ['| esp | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | 40s | 15s |',
                                 '| arm | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | 40s | 15s |',
                                 '| esp2 | ✅ | ❌ |  |  |  |  | ✅ | 40s | 15s |',
                                 '| pre |  |  |  |  |  |  |  | — | — |'])

  def test_a_withheld_report_shows_no_steps_and_says_why(self):
    for what, extra in (('unprepared', {}), ('unsafe', {'unsafeArtifacts': ['/x/hil_report.md']})):
      with self.subTest(what):
        r = row('w', 'pass', 'blocker', sharedDetail='report not prepared: OSError: x', **extra)
        body = hc.render({'boards': [r]}, selection(), META)
        self.assertIn('| w |  |  |  |  |  |  |  | 40s | 15s |', body)
        self.assertIn('- `w` battery: report not prepared: OSError: x (native pass, shared run rules blocker; '
                      'report withheld)', body)
        self.assertNotIn('✅ 1', body)
    r = row('u', 'pass', 'blocker', sharedDetail='run aborted', unsafeArtifacts=['/x'])
    self.assertIn('| u |  |', hc.render({'boards': [r]}, selection(), META))   # unsafe alone withholds

  def test_a_corrupt_or_missing_report_shows_no_steps_and_keeps_the_native_detail(self):
    for detail in ('report corrupt: Expecting value', 'report missing: no run directory'):
      with self.subTest(detail):
        r = row('c', 'fail', 'blocker', detail='copy: drive vanished', sharedDetail=detail,
                steps={'install': True, 'copy': False})
        body = hc.render({'boards': [r]}, selection(), META)
        self.assertIn('| c |  |  |  |  |  |  |  | 40s | 15s |', body)
        self.assertIn(f'- `c` battery: copy: drive vanished (native fail, shared run rules blocker: {detail}; '
                      'report withheld)', body)

  def test_views_the_upload_withholds_hide_every_boards_steps(self):
    for views in ('withhold', None):
      with self.subTest(views):
        body = hc.render({'boards': [row('a'), row('b')]}, selection(2), META, views)
        self.assertIn('| a |  |  |  |  |  |  |  | 40s | 15s |', body)
        self.assertIn(f'- report views withheld by the upload (upload-views: {views or "missing"}): no steps shown',
                      body)
        self.assertIn('**✅ 2 passed**', body)   # the verdicts are summary.json's, not the views'

  def test_a_missing_summary_is_an_incomplete_run_never_a_pass(self):
    sel = selection(2, uncovered=[{'target': 'ports/ch32v20x', 'reason': 'none here'}])
    body = hc.render(None, sel, META)
    self.assertIn('**HIL report unavailable: the run ended without a summary (run incomplete).**', body)
    self.assertIn('- `ports/ch32v20x`: none here', body)
    self.assertTrue(body.endswith(f'_[Records, reports and logs]({META["runUrl"]})_\n'))
    self.assertNotIn('| Board', body)
    self.assertNotIn('blank not run', body)   # the legend only with the table

  def test_a_missing_selection_is_never_no_affected_boards(self):
    body = hc.render({'boards': [row('a')]}, None, META)
    self.assertIn('_Selection unavailable._', body)
    self.assertNotIn('No affected boards', body)
    self.assertIn('| a |', body)
    self.assertIn('**HIL report unavailable', hc.render(None, None, META))

  def test_no_selected_board_says_so_with_what_is_uncovered(self):
    sel = selection(0, uncovered=[{'target': 'ports/ch32v20x', 'reason': 'none here'}])
    body = hc.render(None, sel, META)
    self.assertEqual(lines(body)[6:], ['_No affected boards on this rig; no HIL run for this push._', '',
                                       'Not covered on this rig:', '- `ports/ch32v20x`: none here'])

  def test_mentions_are_neutralised_everywhere(self):
    r = row('m', 'fail', 'fail', detail='copy: @hathach and @org/team, mail a@b', steps={'copy': False})
    sel = selection(uncovered=[{'target': 'x', 'reason': 'ask @someone'}])
    body = hc.render({'boards': [r]}, sel, META)
    self.assertIsNone(re.search(r'@\w', body), body)
    self.assertIn('@​hathach and @​org/team, mail a@​b', body)
    self.assertIn('ask @​someone', body)

  def test_report_text_cannot_break_the_table_or_a_bullet(self):
    r = row('p|q', 'fail', 'fail', detail='copy: a | b\nc\r\nd', steps={'copy': False})
    body = hc.render({'boards': [r]}, selection(), META)
    self.assertIn('| p/q | ', body)
    self.assertIn('- `p/q` copy: a / b c d\n', body)

  def test_durations(self):
    for s, want in ((None, '—'), (0, '0s'), (49, '49s'), (60, '1m'), (270, '4m30s'), (1200, '20m'), (3600, '1h'),
                    (3720, '1h2m'), (3725, '1h2m')):
      self.assertEqual(hc.duration(s), want, s)


class Fresh(unittest.TestCase):
  HEAD = 'a' * 40

  def api(self, head=None, newest=7, attempt=2):
    replies = {'repos/o/r/pulls/5': {'head': {'sha': head or self.HEAD}},
               f'repos/o/r/actions/workflows/hil.yml/runs?event=pull_request&head_sha={self.HEAD}&per_page=1':
               {'workflow_runs': [{'id': newest}]},
               'repos/o/r/actions/runs/7': {'run_attempt': attempt}}
    return lambda path: replies[path]

  def fresh(self, **kw):
    return hc.fresh(self.api(**kw), 'o/r', '5', self.HEAD, '7', '2')

  def test_only_the_newest_attempt_of_the_newest_run_for_the_current_head_is_fresh(self):
    self.assertEqual(self.fresh(), (True, 'fresh'))
    for what, kw, why in (('head moved', {'head': 'b' * 40}, 'head moved to bbbbbbb'),
                          ('an older run', {'newest': 9}, 'run 9 is newer'),
                          ('an older attempt', {'attempt': 3}, 'attempt 3 is newer')):
      with self.subTest(what):
        ok, reason = self.fresh(**kw)
        self.assertFalse(ok)
        self.assertIn(why, reason)


GH = '''#!/usr/bin/env python3
import json, os, sys
replies = json.load(open(os.environ["GH_REPLIES"]))
path = sys.argv[2]
if path not in replies:
    sys.exit("HTTP 502: " + path)
print(json.dumps(replies[path]))
'''


class Cli(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    (self.tmp / 'bin').mkdir()
    gh = self.tmp / 'bin' / 'gh'
    gh.write_text(GH)
    gh.chmod(0o755)
    self.replies = self.tmp / 'replies.json'
    head = 'a' * 40
    self.ok = {'repos/o/r/pulls/5': {'head': {'sha': head}},
               f'repos/o/r/actions/workflows/hil.yml/runs?event=pull_request&head_sha={head}&per_page=1':
               {'workflow_runs': [{'id': 7}]},
               'repos/o/r/actions/runs/7': {'run_attempt': 1}}
    self.env = dict(os.environ, PATH=f'{self.tmp / "bin"}:{os.environ["PATH"]}', GH_REPLIES=str(self.replies),
                    GITHUB_REPOSITORY='o/r', PR='5', HEAD_SHA=head, GITHUB_RUN_ID='7', GITHUB_RUN_ATTEMPT='1')

  def test_render_reads_missing_or_unreadable_files_as_unavailable(self):
    (self.tmp / 'bad.json').write_text('{"boards": [')
    out = self.tmp / 'comment.md'
    with mock.patch.object(sys, 'stdout', io.StringIO()):
      self.assertEqual(hc.main(['render', '--summary', str(self.tmp / 'none.json'), '--selection',
                                str(self.tmp / 'bad.json'), '--views', str(self.tmp / 'none'), '--roster', 'ci.json', '--head', 'h' * 40, '--tested',
                                't' * 40, '--run-url', 'https://x', '--run-id', '7', '--attempt', '1', '--out',
                                str(out)]), 0)
    body = out.read_text(encoding='utf-8')
    self.assertIn('_Selection unavailable._', body)
    (self.tmp / 'views').write_bytes(b'\xff')
    (self.tmp / 'summary.json').write_text(json.dumps({'boards': [{'board': 'a', 'verdict': 'pass', 'steps': {'install': True}}]}))
    with mock.patch.object(sys, 'stdout', io.StringIO()):
      self.assertEqual(hc.main(['render', '--summary', str(self.tmp / 'summary.json'), '--selection',
                                str(self.tmp / 'bad.json'), '--views', str(self.tmp / 'views'), '--roster', 'ci.json',
                                '--head', 'h' * 40, '--tested', 't' * 40, '--run-url', 'https://x', '--run-id', '7',
                                '--attempt', '1', '--out', str(out)]), 0)
    self.assertIn('upload-views: missing', out.read_text(encoding='utf-8'))
    self.assertIn('**HIL report unavailable', body)

  def fresh_step(self, replies):
    """The workflow's fresh step run as the runner runs it: (exit, its GITHUB_OUTPUT, its stdout)."""
    self.replies.write_text(json.dumps(replies))
    text = (ROOT / '.github' / 'workflows' / 'hil.yml').read_text()
    body = re.search(r'\n        id: fresh\n(?:        .*\n)*?        run: \|\n((?:          .*\n)+)', text).group(1)
    output = self.tmp / 'github-output'
    output.write_text('')
    p = subprocess.run(['bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', textwrap.dedent(body)], cwd=ROOT,
                       env=dict(self.env, GITHUB_OUTPUT=str(output)), capture_output=True, text=True)
    return p.returncode, output.read_text(), p.stdout

  def test_the_workflow_posts_when_fresh_skips_when_stale_and_fails_when_the_api_cannot_tell(self):
    self.assertEqual(self.fresh_step(self.ok)[:2], (0, 'post=true\n'))
    stale = dict(self.ok, **{'repos/o/r/actions/runs/7': {'run_attempt': 2}})
    code, output, stdout = self.fresh_step(stale)
    self.assertEqual((code, output), (0, ''))
    self.assertIn('::notice title=HIL report not posted::run 7 attempt 2 is newer than attempt 1', stdout)
    broken = {k: v for k, v in self.ok.items() if 'pulls' not in k}
    self.assertEqual(self.fresh_step(broken)[:2], (2, ''))


if __name__ == '__main__':
  unittest.main()
