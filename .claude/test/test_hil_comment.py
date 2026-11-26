#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The HIL workflow's sticky PR comment: the body hil_comment.py renders from summary.json and the selection, and the
# workflow's fresh and post steps run as the runner runs them over a stand-in for agentrc's gh_pr_comment.py, whose own
# tests cover what it decides.
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
RUN_NAME = 'HIL PR #{}'   # hil.yml's run-name for a PR


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

      | Board | install | dfu | copy | app-ran | reenter | recopy | blinky | admit | run |
      | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --: | --: |
      | `imxrt1064_evk` | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | 49s | 22s |
      | `espressif_p4_function_ev` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 4m30s | 2m40s |
      | `stm32h743nucleo` | ✅ | ✅ | ❌ |  |  | — | ✅ | 40s | 15s |

      ✅ passed · ❌ failed · blank not run · — not in this board's run · run time includes lock wait and blinky

      - `stm32h743nucleo` copy: `CURRENT.UF2 read-back differs at block 12`

      Not covered on this rig:
      - `ports/ch32v20x`: `no roster board on this host`

      _[Records, reports and logs](https://github.com/o/r/actions/runs/39512345678/attempts/1)_
      '''))

  def test_mixed_outcomes_are_counted_by_both_verdicts_and_noted(self):
    rows = [row('a'),
            row('b', 'fail', 'fail', detail='dfu: not seen', steps={'install': True, 'dfu': False}),
            row('c', 'blocker', 'blocker', cleanupPass=False,
                detail='cleanup failed or no report; board released, failure logged'),
            row('d', 'not-run', 'not-run', steps={}, cleanupPass=None, detail='locked: held by pid 7'),
            row('e', 'pass', 'blocker', sharedDetail='run caveat denies a pass')]
    body = hc.render({'boards': rows}, selection(5), META)
    self.assertIn('\n**✅ 1 passed · ❌ 1 failed · ⛔ 2 blocked · ⚪ 1 not run**\n', body)   # no elapsed: none given
    self.assertIn('_Boards the change reaches: 5._', body)
    notes = [ln for ln in lines(body) if ln.startswith('- `')]
    self.assertEqual(notes, ['- `b` dfu: `not seen`',
                             '- `c` blinky: `cleanup failed or no report; board released, failure logged`',
                             '- `d` battery: `locked: held by pid 7`',
                             '- `e` battery: `run caveat denies a pass` (native pass, shared run rules blocker)'])
    self.assertNotIn('verdict', body)
    self.assertIn('| `d` |  |  |  |  |  |  |  | 40s | 15s |', body)   # no steps: every step cell blank

  def test_the_cleanup_failures_a_battery_found_and_its_notes_are_shown_whatever_its_verdict(self):
    found = {'how': 'found-left', 'reason': 'hil_test.py', 'pid': 7, 'id': 'f1', 'at': 'T', 'detail': 'left'}
    rows = [row('a', previousCleanupFailure=found, notes=['legacyNote: cleanup log not written: x']),
            row('b', 'fail', 'fail', detail='dfu: not seen', steps={'install': True, 'dfu': False},
                previousCleanupFailure={'unavailable': 'cleanup log unreadable: x'}, openCleanupFailures=3)]
    notes = [ln for ln in lines(hc.render({'boards': rows}, selection(2), META)) if ln.startswith('- `')]
    self.assertEqual(notes, ['- `a` `Previous cleanup failure: T (found-left, hil_test.py pid 7, '
                             'id f1): left`',
                             '- `a` `Notes: legacyNote: cleanup log not written: x`',
                             '- `b` dfu: `not seen`',
                             '- `b` `Previous cleanup failure: cleanup log unreadable: x (2 earlier '
                             'still open)`'])

  def test_an_untouched_board_has_a_blank_blinky_cell(self):
    r = row('u', 'not-run', 'not-run', steps={'install': False}, cleanupPass=None,
            detail='install: no probe (nothing written)')
    body = hc.render({'boards': [r]}, selection(), META)
    self.assertIn('| `u` | ❌ |  |  |  |  | — |  | 40s | 15s |', body)
    self.assertIn('- `u` install: `no probe (nothing written)`', body)

  def test_recopy_is_absent_on_a_non_espressif_battery_and_blank_with_no_steps(self):
    rows = [row('esp', steps=dict(OK, recopy=False), espressif=True), row('arm'),
            row('esp2', 'fail', 'fail', steps={'install': True, 'dfu': False}, espressif=True),
            {'board': 'pre', 'phase': 'preflight', 'verdict': 'blocker', 'detail': 'run r1 never finished'}]
    table = [ln for ln in lines(hc.render({'boards': rows}, selection(3), META)) if ln.startswith('| ')]
    self.assertEqual(table[2:], ['| `esp` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | 40s | 15s |',
                                 '| `arm` | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | 40s | 15s |',
                                 '| `esp2` | ✅ | ❌ |  |  |  |  | ✅ | 40s | 15s |',
                                 '| `pre` |  |  |  |  |  |  |  | — | — |'])

  def test_a_withheld_report_shows_no_steps_and_says_why(self):
    for what, extra in (('unprepared', {}), ('unsafe', {'unsafeArtifacts': ['/x/hil_report.md']})):
      with self.subTest(what):
        r = row('w', 'pass', 'blocker', sharedDetail='report not prepared: OSError: x', **extra)
        body = hc.render({'boards': [r]}, selection(), META)
        self.assertIn('| `w` |  |  |  |  |  |  |  | 40s | 15s |', body)
        self.assertIn('- `w` battery: `report not prepared: OSError: x` (native pass, shared run rules blocker; '
                      'report withheld)', body)
        self.assertNotIn('✅ 1', body)
    r = row('u', 'pass', 'blocker', sharedDetail='run aborted', unsafeArtifacts=['/x'])
    self.assertIn('| `u` |  |', hc.render({'boards': [r]}, selection(), META))   # unsafe alone withholds

  def test_a_corrupt_or_missing_report_shows_no_steps_and_keeps_the_native_detail(self):
    for detail in ('report corrupt: Expecting value', 'report missing: no run directory'):
      with self.subTest(detail):
        r = row('c', 'fail', 'blocker', detail='copy: drive vanished', sharedDetail=detail,
                steps={'install': True, 'copy': False})
        body = hc.render({'boards': [r]}, selection(), META)
        self.assertIn('| `c` |  |  |  |  |  |  |  | 40s | 15s |', body)
        self.assertIn(f'- `c` battery: `copy: drive vanished` (native fail, shared run rules blocker: `{detail}`; '
                      'report withheld)', body)

  def test_views_the_upload_withholds_hide_every_boards_steps(self):
    for views in ('withhold', None):
      with self.subTest(views):
        body = hc.render({'boards': [row('a'), row('b')]}, selection(2), META, views)
        self.assertIn('| `a` |  |  |  |  |  |  |  | 40s | 15s |', body)
        shown = f'`{views}`' if views else 'missing'
        self.assertIn(f'- report views withheld by the upload (upload-views: {shown}): no steps shown',
                      body)
        self.assertIn('**✅ 2 passed**', body)   # the verdicts are summary.json's, not the views'

  def test_a_missing_summary_is_an_incomplete_run_never_a_pass(self):
    sel = selection(2, uncovered=[{'target': 'ports/ch32v20x', 'reason': 'none here'}])
    body = hc.render(None, sel, META)
    self.assertIn('**HIL report unavailable: the run ended without a summary (run incomplete).**', body)
    self.assertIn('- `ports/ch32v20x`: `none here`', body)
    self.assertTrue(body.endswith(f'_[Records, reports and logs]({META["runUrl"]})_\n'))
    self.assertNotIn('| Board', body)
    self.assertNotIn('blank not run', body)   # the legend only with the table

  def test_a_missing_selection_is_never_no_affected_boards(self):
    body = hc.render({'boards': [row('a')]}, None, META)
    self.assertIn('_Selection unavailable._', body)
    self.assertNotIn('No affected boards', body)
    self.assertIn('| `a` |', body)
    self.assertIn('**HIL report unavailable', hc.render(None, None, META))

  def test_no_selected_board_says_so_with_what_is_uncovered(self):
    sel = selection(0, uncovered=[{'target': 'ports/ch32v20x', 'reason': 'none here'}])
    body = hc.render(None, sel, META)
    self.assertEqual(lines(body)[6:], ['_No affected boards on this rig; no HIL run for this push._', '',
                                       'Not covered on this rig:', '- `ports/ch32v20x`: `none here`'])

  def test_mentions_are_neutralised_everywhere(self):
    r = row('m', 'fail', 'fail', detail='copy: @hathach and @org/team, mail a@b', steps={'copy': False})
    sel = selection(uncovered=[{'target': 'x', 'reason': 'ask @someone'}])
    body = hc.render({'boards': [r]}, sel, META)
    self.assertIsNone(re.search(r'@\w', body), body)
    self.assertIn('@​hathach and @​org/team, mail a@​b', body)
    self.assertIn('ask @​someone', body)

  def test_a_body_past_a_comments_size_is_cut_at_a_line_end(self):
    rows = [row(f'b{i}', 'fail', 'fail', detail='copy: ' + 'x' * 250, steps={'copy': False}) for i in range(400)]
    body = hc.render({'boards': rows}, selection(400), META)
    self.assertLessEqual(len(body), hc.gpc().MAX_COMMENT)
    self.assertTrue(body.endswith("…truncated: see the run's artifacts.\n"), body[-200:])

  def test_report_text_cannot_break_the_table_or_a_bullet(self):
    r = row('p|q', 'fail', 'fail', detail='copy: a | b\nc\r\nd', steps={'copy': False})
    body = hc.render({'boards': [r]}, selection(), META)
    # one line; a pipe escaped only in a table cell, where GFM unescapes it inside the code span
    self.assertIn('| `p\\|q` | ', body)
    self.assertIn('- `p|q` copy: `a | b c d`\n', body)

  def test_report_text_renders_literally(self):
    # a build's compiler or CMake output reaches the detail: no image, HTML, link or code span of its own renders
    r = row('x|![b](https://e.invalid/b.svg)', 'fail', 'blocker', steps={'install': False},
            detail='install: ![ok](https://e.invalid/p.svg) <details> [l](https://e.invalid) `a` ``b``',
            sharedDetail='report corrupt: <img src=x> **y**')
    sel = selection(uncovered=[{'target': 'ports/`x`', 'reason': '<b>none</b>'}])
    body = hc.render({'boards': [r]}, sel, META, '<script>')
    self.assertIn('| `x\\|![b](https://e.invalid/b.svg)` |', body)
    self.assertIn('- `x|![b](https://e.invalid/b.svg)` battery: '
                  '``` install: ![ok](https://e.invalid/p.svg) <details> [l](https://e.invalid) `a` ``b`` ``` '
                  '(native fail, shared run rules blocker: `report corrupt: <img src=x> **y**`; report withheld)\n', body)
    self.assertIn('(upload-views: `<script>`)', body)
    self.assertIn('- `` ports/`x` ``: `<b>none</b>`\n', body)

  def test_durations(self):
    for s, want in ((None, '—'), (0, '0s'), (49, '49s'), (60, '1m'), (270, '4m30s'), (1200, '20m'), (3600, '1h'),
                    (3720, '1h2m'), (3725, '1h2m')):
      self.assertEqual(hc.duration(s), want, s)


# agentrc's gh_pr_comment.py as the fresh and post steps run it: its argv kept, G_SAYS printed, exiting G_EXIT
G = '''#!/usr/bin/env python3
import json, os, sys
json.dump(sys.argv[1:], open(os.environ["G_ARGV"], "w"))
print(os.environ["G_SAYS"])
sys.exit(int(os.environ["G_EXIT"]))
'''


class Cli(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    self.env = dict(os.environ, GITHUB_REPOSITORY='o/r', PR='5', HEAD_SHA='a' * 40, GITHUB_RUN_ID='7',
                    GITHUB_RUN_ATTEMPT='1')

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
    (self.tmp / 'link.json').symlink_to(self.tmp / 'summary.json')   # an artifact's link is never followed
    with mock.patch.object(sys, 'stdout', io.StringIO()):
      self.assertEqual(hc.main(['render', '--summary', str(self.tmp / 'link.json'), '--selection',
                                str(self.tmp / 'bad.json'), '--views', str(self.tmp / 'views'), '--roster', 'ci.json',
                                '--head', 'h' * 40, '--tested', 't' * 40, '--run-url', 'https://x', '--run-id', '7',
                                '--attempt', '1', '--out', str(out)]), 0)
    self.assertIn('**HIL report unavailable', out.read_text(encoding='utf-8'))

  def step(self, name, **env):
    """The workflow's step `name` run as the runner runs it: (exit, its GITHUB_OUTPUT, its stdout)."""
    text = (ROOT / '.github' / 'workflows' / 'hil.yml').read_text()
    body = re.search(rf'\n      - name: {re.escape(name)}\n(?:        .*\n)*?        run: \|\n((?:          .*\n)+)',
                     text).group(1)
    output = self.tmp / 'github-output'
    output.write_text('')
    p = subprocess.run(['bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', textwrap.dedent(body)], cwd=ROOT,
                       env=dict(self.env, GITHUB_OUTPUT=str(output), **env), capture_output=True, text=True)
    return p.returncode, output.read_text(), p.stdout

  def g_step(self, name, code, says):
    """Step `name` over a stand-in gh_pr_comment.py exiting `code` after printing `says`: (exit, its GITHUB_OUTPUT,
    its stdout, the stand-in's argv)."""
    g, argv = self.tmp / 'gh_pr_comment.py', self.tmp / 'argv.json'
    g.write_text(G)
    code, output, stdout = self.step(name, G=str(g), G_ARGV=str(argv), G_SAYS=says, G_EXIT=str(code))
    return code, output, stdout, json.loads(argv.read_text())

  def fresh_step(self, code, says):
    return self.g_step('Check this run is the newest for the PR head', code, says)

  def post_step(self, code, says):
    return self.g_step('Post the report', code, says)

  def test_the_workflow_names_a_pull_request_run_as_fresh_and_the_post_match_it(self):
    text = (ROOT / '.github' / 'workflows' / 'hil.yml').read_text()
    name = re.search(r"^run-name: .*format\('([^']*)', github\.event\.pull_request\.number\)", text, re.M)
    self.assertIsNotNone(name, 'hil.yml has no run-name naming the PR')
    self.assertEqual(name.group(1).replace('{0}', '{}'), RUN_NAME)

  def test_fresh_is_agentrcs_check_of_this_attempt_of_this_prs_hil_runs(self):
    code, output, _, argv = self.fresh_step(0, 'current')
    self.assertEqual((code, output), (0, 'post=true\n'))
    self.assertEqual(argv[0], 'fresh')
    self.assertEqual(dict(zip(argv[1::2], argv[2::2])), {
      '--repo': 'o/r', '--pr': '5', '--run-id': '7', '--attempt': '1', '--head-sha': 'a' * 40,
      '--workflow': 'hil.yml', '--run-name': RUN_NAME.format(5)})

  def test_fresh_skips_when_stale_and_fails_when_the_api_cannot_tell(self):
    code, output, stdout, _ = self.fresh_step(1, 'stale: run 7 attempt 2 is newer than attempt 1')
    self.assertEqual((code, output), (0, ''))
    self.assertIn('::notice title=HIL report not posted::stale: run 7 attempt 2 is newer than attempt 1', stdout)
    self.assertEqual(self.fresh_step(2, '')[:2], (2, ''))

  def test_the_post_is_agentrcs_sticky_post_of_the_rendered_body_under_the_existing_marker_for_this_prs_runs(self):
    code, _, stdout, argv = self.post_step(0, 'updated https://c/11')
    self.assertEqual((code, stdout), (0, 'updated https://c/11\n'))
    self.assertEqual(argv[0], 'post')
    self.assertEqual(dict(zip(argv[1::2], argv[2::2])), {
      '--repo': 'o/r', '--pr': '5', '--header': 'hil-report', '--body-file': 'comment.md', '--run-id': '7',
      '--attempt': '1', '--head-sha': 'a' * 40, '--workflow': 'hil.yml', '--run-name': RUN_NAME.format(5)})

  def test_the_post_notes_a_stale_run_and_fails_on_anything_else(self):
    self.assertEqual(self.post_step(1, 'stale: run 8 is newer than run 7')[::2],
                     (0, '::notice title=HIL report not posted::stale: run 8 is newer than run 7\n'))
    self.assertEqual(self.post_step(2, 'unknown: gh api graphql: HTTP 502')[::2],
                     (2, '::error title=HIL report not posted::unknown: gh api graphql: HTTP 502\n'))

  def test_the_rig_artifact_is_the_rig_jobs_attempts_and_fresh_checks_this_one(self):
    # re-running failed jobs keeps a passed rig job's outputs and artifact, so the pr-comment job's own attempt has none
    text = (ROOT / '.github' / 'workflows' / 'hil.yml').read_text()
    jobs = dict(re.findall(r'^  ([\w-]+):\n((?:(?:    .*)?\n)+)', text[text.index('\njobs:\n'):], re.M))
    self.assertIn('    outputs:\n      attempt: ${{ github.run_attempt }}\n', jobs['hil-run'])
    self.assertIn('          name: hil-run-${{ github.run_attempt }}\n', jobs['hil-run'])
    comment = jobs['pr-comment']
    self.assertIn('      RIG_ATTEMPT: ${{ needs.hil-run.outputs.attempt || github.run_attempt }}\n', comment)
    self.assertIn('          name: hil-run-${{ env.RIG_ATTEMPT }}\n', comment)
    self.assertIn('/attempts/$RIG_ATTEMPT" \\\n', comment)
    self.assertIn('--attempt "$RIG_ATTEMPT" --out comment.md', comment)
    self.assertEqual(comment.count('github.run_attempt') + comment.count('GITHUB_RUN_ATTEMPT'), 3)

  def test_the_rig_artifact_is_downloaded_only_once_the_run_may_post(self):
    text = (ROOT / '.github' / 'workflows' / 'hil.yml').read_text()
    step = re.search(r'\n      - name: Download the records, reports and logs\n((?:        .*\n)+)', text)
    self.assertLess(text.index('        id: fresh\n'), step.start())
    self.assertIn("        if: steps.fresh.outputs.post == 'true'\n", step.group(1))


if __name__ == '__main__':
  unittest.main()
