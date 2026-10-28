#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The HIL workflow's per-board hosted builds (hil_hosted_pick.py): a leg's delete of its board's earlier artifact, the
# collection of this attempt's builds over a stubbed GitHub API, the manifest the rig reads, and the acceptance faults.
import io
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import hil_hosted_pick as hp  # noqa: E402

REPO, RUN = 'o/r', 42
A, B, C = 'stm32f407disco', 'imxrt1064_evk', 'espressif_esp32s3_devkitm_1'


def job(board, conclusion='success', status='completed', attempt=2, name=None):
  return {'id': random.randrange(1 << 40), 'name': name or hp.leg_name(board), 'status': status,
          'conclusion': conclusion, 'run_attempt': attempt}


def artifact(board, aid, expired=False, name=None):
  return {'id': aid, 'name': name or hp.artifact_name(board), 'expired': expired}


def zipped(members):
  """A zip of `members` (name -> bytes, or None for a symlink to x)."""
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, 'w') as z:
    for name, data in members.items():
      if data is None:
        info = zipfile.ZipInfo(name)
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, 'x')
      else:
        z.writestr(name, data)
  return buf.getvalue()


def build(board):
  return zipped({f'{board}/{board}.build.json': b'{}', f'{board}/build/_bin/tinyuf2.bin': b'bin'})


class Api:
  """GitHub's list endpoints over `jobs` (this attempt's) and `artifacts` (the run's), paged `per_page` at a time and
  shuffled first, like an API whose order is unspecified; the artifacts' name filter is not applied, so the client's
  own exact match is what counts. `fail` maps (method, path fragment) to the error its call raises."""

  def __init__(self, jobs=(), artifacts=(), zips=None, per_page=2, fail=None):
    self.jobs, self.artifacts, self.zips = list(jobs), list(artifacts), zips or {}
    random.shuffle(self.jobs)
    random.shuffle(self.artifacts)
    self.per_page, self.fail, self.calls, self.deleted = per_page, fail or {}, [], []

  def __call__(self, path, method='GET', out=None):
    self.calls.append((method, path))
    for (m, frag), err in self.fail.items():
      if m == method and frag in path:
        raise hp.ApiError(err)
    if method == 'DELETE':
      self.deleted.append(int(path.rsplit('/', 1)[1]))
      return None
    url = urllib.parse.urlparse(path)
    q = urllib.parse.parse_qs(url.query)
    page = int(q['page'][0])
    if url.path.endswith(f'/runs/{RUN}/attempts/2/jobs'):
      key, items = 'jobs', self.jobs
    elif url.path.endswith(f'/runs/{RUN}/artifacts'):
      key, items = 'artifacts', self.artifacts
    else:
      raise AssertionError(path)
    return {'total_count': len(items), key: items[(page - 1) * self.per_page:page * self.per_page]}

  def download(self, aid, dest):
    if aid not in self.zips:
      raise hp.ApiError(f'artifact {aid}: 410 gone')
    Path(dest).write_bytes(self.zips[aid])


class Collect(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    self.out = self.tmp / 'hosted'

  def collect(self, api, boards=(A,)):
    with mock.patch.object(sys, 'stdout', io.StringIO()):
      got = hp.collect(api, api.download, REPO, RUN, 2, list(boards), self.out)
    manifest = json.loads((self.out / hp.COLLECTION).read_text())
    self.assertEqual((manifest['version'], manifest['run'], manifest['attempt'], manifest['boards']), (1, RUN, 2, got))
    self.assertEqual(hp.load_collection(self.out / hp.COLLECTION), got)
    return got

  def test_a_succeeded_legs_one_artifact_is_downloaded_by_id_among_paginated_shuffled_lists(self):
    jobs = [job(A), job(B, attempt=1), job(C)] + [job(f'other{i}') for i in range(5)] + [{'id': 1, 'name': 'select',
                                                                                         'status': 'completed', 'conclusion': 'success'}]
    arts = [artifact(A, 11), artifact(B, 12), artifact(C, 13), artifact(None, 14, name='hil-hosted-build-1'),
            artifact(None, 15, name='hil-selection'), artifact(None, 16, name=f'hil-hosted-{A}x'),
            artifact(None, 17, name=f'x-hil-hosted-{A}')]
    api = Api(jobs, arts, {11: build(A), 12: build(B), 13: build(C)})
    got = self.collect(api, (A, B, C))
    # a leg a partial re-run kept is listed in this attempt with its conclusion (B ran in attempt 1)
    self.assertEqual(got, {A: {'conclusion': 'success', 'artifact': 11}, B: {'conclusion': 'success', 'artifact': 12},
                           C: {'conclusion': 'success', 'artifact': 13}})
    for b in (A, B, C):
      self.assertEqual((self.out / b / 'build' / '_bin' / 'tinyuf2.bin').read_bytes(), b'bin')
    self.assertEqual(sorted(p.name for p in self.out.iterdir()), sorted([A, B, C, hp.COLLECTION]))
    pages = [p for m, p in api.calls if '/jobs' in p]
    self.assertEqual(len(pages), 5, 'every page of the job list is read')

  def test_a_board_whose_leg_did_not_succeed_is_never_given_its_artifact(self):
    for what, legs, arts, why in (
        ('a newer failure with an older artifact left', [job(A, 'failure')], [artifact(A, 11)],
         'its hosted build in attempt 2 is failure'),
        ('cancelled before its upload', [job(A, 'cancelled')], [], 'is cancelled'),
        ('skipped', [job(A, 'skipped')], [artifact(A, 11)], 'is skipped'),
        ('still running', [job(A, None, 'in_progress')], [artifact(A, 11)], 'is in_progress'),
        ('no leg in this attempt', [job(B)], [artifact(A, 11)], f"no job named 'hosted-build \\({A}\\)' in attempt 2"),
        ('two legs of one name', [job(A), job(A)], [artifact(A, 11)], f"2 jobs named 'hosted-build \\({A}\\)'"),
        ('no artifact', [job(A)], [], f'no unexpired hil-hosted-{A} artifact$'),
        ('an expired artifact only', [job(A)], [artifact(A, 11, expired=True)], r'no unexpired .* \(1 expired\)'),
        ('two artifacts', [job(A)], [artifact(A, 11), artifact(A, 12)], f'2 unexpired hil-hosted-{A} artifacts'),
        ('an artifact gone at download', [job(A)], [artifact(A, 99)], 'artifact 99 cannot be extracted: .*410 gone')):
      with self.subTest(what):
        if self.out.exists():
          shutil.rmtree(self.out)
        api = Api(legs, arts, {11: build(A), 12: build(A)})
        got = self.collect(api)
        self.assertNotIn('artifact', got[A])
        self.assertRegex(got[A]['reason'], why)
        self.assertFalse((self.out / A).exists(), 'nothing of the board reaches the rig')
        self.assertIn('hosted build not collected', hp.gap(got, A))

  def test_an_api_error_leaves_the_boards_out_with_the_reason(self):
    api = Api([job(A), job(B)], [artifact(A, 11), artifact(B, 12)], {11: build(A), 12: build(B)},
              fail={('GET', '/attempts/2/jobs'): 'HTTP 502'})
    got = self.collect(api, (A, B))
    for b in (A, B):
      self.assertEqual(got[b], {'conclusion': None, 'reason': f'the job list of attempt 2 is unavailable: HTTP 502'})
    self.out = self.tmp / 'second'
    got = self.collect(Api([job(A)], [artifact(A, 11)], {11: build(A)}, fail={('GET', '/artifacts'): 'HTTP 403'}))
    self.assertRegex(got[A]['reason'], 'its artifact cannot be listed: HTTP 403')

  def test_a_listing_whose_pages_do_not_add_up_is_an_api_error(self):
    for what, page2 in (('an empty page', []), ('the same page again', [{'id': 1}])):
      with self.subTest(what), self.assertRaisesRegex(hp.ApiError, '1 of 3 jobs listed, then a page with none new'):
        hp.listing(lambda path: {'total_count': 3, 'jobs': [{'id': 1}] if path.endswith('&page=1') else page2}, 'x',
                   'jobs')
    with self.assertRaisesRegex(hp.ApiError, 'page 1 has no jobs'):
      hp.listing(lambda path: {'message': 'Not Found'}, 'x', 'jobs')
    pages = {1: [{'id': 1}, {'id': 2}], 2: [{'id': 2}, {'id': 3}]}   # an item shifted between pages is counted once
    got = hp.listing(lambda path: {'total_count': 3, 'jobs': pages[int(path.rsplit('page=', 1)[1])]}, 'x', 'jobs')
    self.assertEqual([j['id'] for j in got], [1, 2, 3])

  def test_an_artifact_is_extracted_only_as_files_under_its_board(self):
    for what, members in (('an escape', {f'{A}/../x': b'x'}), ('an absolute path', {'/etc/x': b'x'}),
                          ('another board', {f'{B}/x': b'x'}), ('a file at the root', {'x': b'x'}),
                          ('a link', {f'{A}/l': None}), ('nothing', {})):
      with self.subTest(what):
        if self.out.exists():
          shutil.rmtree(self.out)
        got = self.collect(Api([job(A)], [artifact(A, 11)], {11: zipped(members)}))
        self.assertRegex(got[A]['reason'], 'artifact 11 cannot be extracted')
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), [hp.COLLECTION])
    self.assertFalse((self.tmp / 'x').exists())

  def test_the_manifest_is_written_with_no_board_collected_and_the_out_dir_must_be_fresh(self):
    got = self.collect(Api([], []))
    self.assertIn('reason', got[A])
    with mock.patch.object(hp, 'gh_api', side_effect=AssertionError('no API call')), \
         mock.patch.object(sys, 'stdout', io.StringIO()):
      self.assertEqual(hp.main(['collect', '--repo', REPO, '--run-id', str(RUN), '--attempt', '2', '--board', A,
                                '--out', str(self.out)]), 2)


class Clear(unittest.TestCase):
  def main(self, api):
    with mock.patch.object(hp, 'gh_api', api), mock.patch.object(sys, 'stdout', io.StringIO()) as out:
      return hp.main(['clear', '--repo', REPO, '--run-id', str(RUN), '--board', A]), out.getvalue()

  def test_every_artifact_of_the_boards_exact_name_is_deleted_expired_ones_too(self):
    api = Api(artifacts=[artifact(A, 11), artifact(A, 12, expired=True), artifact(B, 13),
                         artifact(None, 14, name='hil-hosted-build-2'), artifact(None, 15, name=f'hil-hosted-{A}x')])
    code, out = self.main(api)
    self.assertEqual((code, sorted(api.deleted)), (0, [11, 12]))
    self.assertIn(('GET', f'repos/{REPO}/actions/runs/{RUN}/artifacts?name=hil-hosted-{A}&per_page=100&page=1'),
                  api.calls)
    self.assertEqual(self.main(Api())[1], f'hil-hosted-{A}: deleted none\n')

  def test_any_api_error_fails_the_leg(self):
    for call in (('GET', '/artifacts'), ('DELETE', '/actions/artifacts/11')):
      with self.subTest(call):
        code, out = self.main(Api(artifacts=[artifact(A, 11)], fail={call: 'HTTP 500'}))
        self.assertEqual(code, 1)
        self.assertIn('::error title=Earlier hosted build not deleted::HTTP 500', out)


class Fault(unittest.TestCase):
  def test_a_fault_fires_only_at_its_step_board_and_attempt(self):
    spec = f'build:{A}@1 pre-clear:{B}@2 collect@3'
    for step, board, attempt, want in (('build', A, 1, True), ('build', A, 2, False), ('build', B, 1, False),
                                       ('clear', A, 1, False), ('pre-clear', B, 2, True), ('collect', None, 3, True),
                                       ('collect', None, 1, False)):
      with self.subTest(step=step, board=board, attempt=attempt):
        self.assertIs(hp.faulted(spec, step, board, attempt), want)
    self.assertFalse(hp.faulted('', 'build', A, 1))

  def test_the_cli_exits_1_on_a_fault_and_2_on_a_malformed_spec_or_misplaced_board(self):
    def run(*argv):
      with mock.patch.object(sys, 'stdout', io.StringIO()) as out, mock.patch.object(sys, 'stderr', io.StringIO()):
        try:
          return hp.main(['fault', *argv]), out.getvalue()
        except SystemExit as e:
          return e.code, out.getvalue()
    self.assertEqual(run('--spec', f'clear:{A}@1', '--step', 'clear', '--board', A, '--attempt', '1')[0], 1)
    self.assertEqual(run('--spec', f'clear:{A}@1', '--step', 'clear', '--board', A, '--attempt', '2'), (0, ''))
    self.assertEqual(run('--step', 'build', '--board', A, '--attempt', '1'), (0, ''))
    for spec in ('build', f'build:{A}', f'deploy:{A}@1', f'build:{A}@0', 'collect:x@1'):
      with self.subTest(spec):
        code, out = run('--spec', spec, '--step', 'build', '--board', A, '--attempt', '1')
        self.assertEqual(code, 2)
        self.assertIn('Malformed hosted_fault', out)
    self.assertEqual(run('--step', 'collect', '--board', A, '--attempt', '1')[0], 2)
    self.assertEqual(run('--step', 'build', '--attempt', '1')[0], 2)


class Manifest(unittest.TestCase):
  def test_a_manifest_that_is_not_one_is_refused_and_a_gap_names_its_reason(self):
    with tempfile.TemporaryDirectory() as d:
      p = Path(d) / hp.COLLECTION
      for text in ('{', '[]', '{"version": 2, "boards": {}}', '{"version": 1}', '{"version": 1, "boards": {"a": 1}}'):
        with self.subTest(text):
          p.write_text(text)
          with self.assertRaises(ValueError):
            hp.load_collection(p)
      with self.assertRaises(OSError):
        hp.load_collection(Path(d) / 'missing.json')
    boards = {A: {'conclusion': 'success', 'artifact': 11}, B: {'conclusion': 'failure', 'reason': 'its build failed'}}
    self.assertIsNone(hp.gap(boards, A))
    self.assertEqual(hp.gap(boards, B), 'hosted build not collected: its build failed')
    self.assertEqual(hp.gap(boards, C), f'the hosted collection has no entry for {C}')


def workflow_job(name):
  text = (ROOT / '.github' / 'workflows' / 'hil.yml').read_text()
  return re.search(rf'\n  {name}:\n((?:    .*\n|\n)+)', text).group(1)


def step_script(job, step):
  """The `run` of `job`'s step `step`, dedented."""
  m = re.search(rf'- name: {re.escape(step)}\n(?:        .*\n)*?        run: \|\n((?:          .*\n)+)', job)
  return textwrap.dedent(m.group(1))


class WorkflowSteps(unittest.TestCase):
  """The hosted jobs' scripts run as the runner runs them (bash -e), with the real script and `gh` a stand-in that
  logs its calls and serves empty lists."""

  def run_step(self, job, step, **env):
    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      (d / 'gh').write_text('#!/bin/sh\necho "$*" >> "$GH_LOG"\n'
                            'case "$*" in *"-X GET"*) echo \'{"total_count": 0, "jobs": [], "artifacts": []}\';; esac\n')
      (d / 'gh').chmod(0o755)
      log = d / 'gh.log'
      base = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_', 'GITHUB_'))}
      r = subprocess.run(['bash', '-e', '-c', step_script(workflow_job(job), step)], cwd=ROOT, capture_output=True,
                         text=True, env=dict(base, PATH=f'{d}:{os.environ["PATH"]}', GH_LOG=str(log), RUNNER_TEMP=str(d),
                                             PICK=str(SCRIPTS / 'hil_hosted_pick.py'), GITHUB_REPOSITORY=REPO,
                                             GITHUB_RUN_ID=str(RUN), GITHUB_STEP_SUMMARY=str(d / 'summary'),
                                             **env))
      return r, log.read_text().splitlines() if log.exists() else []

  def test_the_delete_step_runs_unless_its_fault_fires_first(self):
    step = "Delete this run's earlier build of the board"
    r, calls = self.run_step('hosted-build', step, BOARD=A, FAULT='', GITHUB_RUN_ATTEMPT='1')
    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
    self.assertEqual(calls, [f'api -X GET repos/{REPO}/actions/runs/{RUN}/artifacts?name=hil-hosted-{A}&per_page=100'
                             '&page=1'])
    r, calls = self.run_step('hosted-build', step, BOARD=A, FAULT=f'clear:{A}@1', GITHUB_RUN_ATTEMPT='1')
    self.assertEqual((r.returncode, calls), (1, []))

  def test_the_collect_step_writes_the_manifest_unless_its_fault_fires_first(self):
    step = "Collect each board's build from this attempt"
    r, calls = self.run_step('hosted-collect', step, BOARDS=f'{A} {B}', FAULT='', GITHUB_RUN_ATTEMPT='2')
    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
    self.assertIn(f'{A}: not collected: no job named', r.stdout)
    self.assertEqual(calls, [f'api -X GET repos/{REPO}/actions/runs/{RUN}/attempts/2/jobs?per_page=100&page=1'])
    r, calls = self.run_step('hosted-collect', step, BOARDS=A, FAULT='collect@2', GITHUB_RUN_ATTEMPT='2')
    self.assertEqual((r.returncode, calls), (1, []))

  def test_the_build_step_runs_its_fault_check_before_building(self):
    script = step_script(workflow_job('hosted-build'), 'Build and pack the record')
    self.assertLess(script.index('fault --spec "$FAULT" --step build'), script.index('hil_hosted.py build'))


if __name__ == '__main__':
  unittest.main()
