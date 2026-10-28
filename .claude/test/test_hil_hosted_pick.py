#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# The HIL workflow's collection of this attempt's hosted builds (hil_hosted_pick.py) over a stubbed GitHub API, the
# collection.json the rig reads, and the hosted jobs' acceptance faults run as the runner runs them.
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import hil_hosted_pick as hp  # noqa: E402
from test_hil_ci import workflow_job  # noqa: E402

REPO, RUN = 'o/r', 42
A, B, C = 'stm32f407disco', 'imxrt1064_evk', 'espressif_esp32s3_devkitm_1'


def job(board, conclusion='success', name=None):
  return {'name': name or hp.leg_name(board), 'status': 'completed', 'conclusion': conclusion}


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
  """`gh api --paginate --slurp` over this attempt's `jobs` and the run's `artifacts`, `per_page` items a page; the
  artifact list holds every artifact of the run, so the client's exact name match is what counts. `fail` maps a path
  fragment to the error its call raises; `pages` replaces a listing's pages outright."""

  def __init__(self, jobs=(), artifacts=(), zips=None, per_page=2, fail=None, pages=None):
    self.jobs, self.artifacts, self.zips = list(jobs), list(artifacts), zips or {}
    self.per_page, self.fail, self.pages, self.calls = per_page, fail or {}, pages or {}, []

  def __call__(self, path):
    self.calls.append(path)
    for frag, err in self.fail.items():
      if frag in path:
        raise hp.ApiError(err)
    for frag, pages in self.pages.items():
      if frag in path:
        return pages
    if path == f'repos/{REPO}/actions/runs/{RUN}/attempts/2/jobs?per_page=100':
      key, items = 'jobs', self.jobs
    elif path == f'repos/{REPO}/actions/runs/{RUN}/artifacts?per_page=100':
      key, items = 'artifacts', self.artifacts
    else:
      raise AssertionError(path)
    n = self.per_page
    return [{'total_count': len(items), key: items[i:i + n]} for i in range(0, max(len(items), 1), n)]

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
    shutil.rmtree(self.out, ignore_errors=True)
    with mock.patch.object(sys, 'stdout', io.StringIO()):
      got = hp.collect(api, api.download, REPO, RUN, 2, list(boards), self.out)
    self.assertEqual(json.loads((self.out / hp.COLLECTION).read_text()), {'version': hp.VERSION, 'boards': got})
    self.assertEqual(set(got), set(boards), 'every board has its entry')
    return got

  def test_a_succeeded_legs_artifact_is_downloaded_by_id_from_one_listing_across_pages(self):
    jobs = [job(A), job(B), job(C), *(job(f'other{i}') for i in range(5)), {'name': 'select', 'conclusion': 'success'}]
    arts = [artifact(A, 11), artifact(B, 12), artifact(C, 13), artifact(None, 14, name='hil-hosted-build-1'),
            artifact(None, 15, name='hil-selection'), artifact(None, 16, name=f'hil-hosted-{A}x'),
            artifact(None, 17, name=f'x-hil-hosted-{A}')]
    api = Api(jobs, arts, {11: build(A), 12: build(B), 13: build(C)})
    self.assertEqual(self.collect(api, (A, B, C)), {A: '', B: '', C: ''})
    for b in (A, B, C):
      self.assertEqual((self.out / b / 'build' / '_bin' / 'tinyuf2.bin').read_bytes(), b'bin')
    self.assertEqual(sorted(p.name for p in self.out.iterdir()), sorted([A, B, C, hp.COLLECTION]))
    self.assertEqual(len(api.calls), 2, 'one job listing and one artifact listing for every board')

  def test_a_board_whose_leg_did_not_succeed_is_never_given_its_artifact(self):
    for what, legs, arts, why in (
        ('a newer failure with an older artifact left', [job(A, 'failure')], [artifact(A, 11)],
         'its hosted build in attempt 2 concluded failure'),
        ('cancelled before its upload', [job(A, 'cancelled')], [], 'concluded cancelled'),
        ('skipped', [job(A, 'skipped')], [artifact(A, 11)], 'concluded skipped'),
        ('unfinished', [job(A, None)], [artifact(A, 11)], 'concluded nothing'),
        ('no leg in this attempt', [job(B)], [artifact(A, 11)], f"no jobs named 'hosted-build \\({A}\\)' in attempt 2"),
        ('two legs of one name', [job(A), job(A)], [artifact(A, 11)], f"2 jobs named 'hosted-build \\({A}\\)'"),
        ('no artifact', [job(A)], [], f'no unexpired hil-hosted-{A} artifact'),
        ('an expired artifact only', [job(A)], [artifact(A, 11, expired=True)], f'no unexpired hil-hosted-{A}'),
        ('an artifact gone at download', [job(A)], [artifact(A, 99)], 'artifact 99 cannot be extracted: .*410 gone')):
      with self.subTest(what):
        got = self.collect(Api(legs, arts, {11: build(A)}))
        self.assertRegex(got[A], why)
        self.assertFalse((self.out / A).exists(), 'nothing of the board reaches the rig')

  def test_a_listing_error_or_shortfall_becomes_every_affected_boards_reason(self):
    for what, api, why in (
        ('the job list fails', Api(fail={'/jobs': 'HTTP 502'}), 'the job list of attempt 2 is unavailable: HTTP 502'),
        ('the artifact list fails', Api([job(A), job(B)], fail={'/artifacts': 'HTTP 403'}),
         "the run's artifacts cannot be listed: HTTP 403"),
        ('pages short of total_count', Api([job(A), job(B)], pages={'/artifacts': [
          {'total_count': 3, 'artifacts': [artifact(A, 11)]}]}), '1 of 3 artifacts listed'),
        ('not pages', Api([job(A), job(B)], pages={'/artifacts': {'message': 'Not Found'}}), 'not pages of artifacts')):
      with self.subTest(what):
        got = self.collect(api, (A, B))
        for b in (A, B):
          self.assertRegex(got[b], why)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), [hp.COLLECTION])

  def test_an_artifact_is_extracted_only_when_every_member_lies_under_its_board(self):
    for what, members in (('an absolute path', {'/etc/x': b'x'}),
                          ('another board', {f'{A}/x': b'x', f'{B}/x': b'x'}), ('a file at the root', {'x': b'x'}),
                          ('a name sharing the prefix', {f'{A}x/y': b'x'}), ('nothing', {}),
                          ('only a dir', {f'{A}/': b''})):
      with self.subTest(what):
        got = self.collect(Api([job(A)], [artifact(A, 11)], {11: zipped(members)}))
        self.assertRegex(got[A], 'artifact 11 cannot be extracted')
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), [hp.COLLECTION], 'nothing extracted')
    self.assertFalse((self.tmp / 'x').exists())
    # zipfile drops a member's `..` and writes a link member as a plain file: both stay under the board
    members = {f'{A}/../y': b'y', f'{A}/l': None}
    self.assertEqual(self.collect(Api([job(A)], [artifact(A, 11)], {11: zipped(members)})), {A: ''})
    self.assertEqual(sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob('*')),
                     sorted([A, f'{A}/l', f'{A}/y', hp.COLLECTION]))
    self.assertFalse((self.out / A / 'l').is_symlink())

  def test_the_manifest_is_written_with_no_board_collected_and_the_out_dir_must_be_fresh(self):
    self.assertRegex(self.collect(Api())[A], 'no jobs named')
    with mock.patch.object(hp, 'gh_api', side_effect=AssertionError('no API call')), \
         mock.patch.object(sys, 'stdout', io.StringIO()):
      self.assertEqual(hp.main(['collect', '--repo', REPO, '--run-id', str(RUN), '--attempt', '2', '--board', A,
                                '--out', str(self.out)]), 2)


def step_script(job, step):
  """The `run` of `job`'s step `step`, dedented."""
  m = re.search(rf'- name: {re.escape(step)}\n(?:        .*\n)*?        run: \|\n((?:          .*\n)+)', job)
  return textwrap.dedent(m.group(1))


class WorkflowSteps(unittest.TestCase):
  """The hosted jobs' scripts run as the runner runs them (bash -eo pipefail), `gh` a stand-in that logs its calls and
  serves one empty page, `python3` a logging stand-in where named."""

  def run_step(self, job, step, stub_python=False, **env):
    with tempfile.TemporaryDirectory() as d:
      d = Path(d)
      (d / 'gh').write_text('#!/bin/sh\necho "$*" >> "$LOG"\necho \'[{"total_count": 0, "jobs": [], "artifacts": []}]\'\n')
      if stub_python:
        (d / 'python3').write_text('#!/bin/sh\necho "python3 $*" >> "$LOG"\n')
      for f in d.iterdir():
        f.chmod(0o755)
      log = d / 'calls.log'
      base = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_', 'GITHUB_'))}
      r = subprocess.run(['bash', '-eo', 'pipefail', '-c', step_script(workflow_job(job), step)], cwd=ROOT,
                         capture_output=True, text=True,
                         env=dict(base, PATH=f'{d}:{os.environ["PATH"]}', LOG=str(log), RUNNER_TEMP=str(d / 'temp'),
                                  GITHUB_REPOSITORY=REPO, GITHUB_RUN_ID=str(RUN), GITHUB_STEP_SUMMARY=str(d / 'summary'),
                                  **env))
      return r, log.read_text().splitlines() if log.exists() else []

  def test_a_build_fault_fails_only_its_board_in_its_attempt_before_building(self):
    step = 'Build and pack the record'
    for fault, attempt, board, fails in ((f'build:{A}@1', '1', A, True), (f'collect@1 build:{A}@1', '1', A, True),
                                         (f'build:{A}@1', '2', A, False), (f'build:{A}@1', '1', B, False),
                                         (f'build:{A}@10', '1', A, False), ('', '1', A, False)):
      with self.subTest(fault=fault, attempt=attempt, board=board):
        r, calls = self.run_step('hosted-build', step, stub_python=True, BOARD=board, FAULT=fault,
                                 GITHUB_RUN_ATTEMPT=attempt)
        self.assertEqual(r.returncode, 1 if fails else 0, r.stdout + r.stderr)
        self.assertEqual(bool(calls), not fails, 'a fault fires before the build')

  def test_a_collect_fault_fails_the_collection_in_its_attempt_only(self):
    step = "Collect each board's build from this attempt"
    r, calls = self.run_step('hosted-collect', step, BOARDS=f'{A} {B}', FAULT='collect@1', GITHUB_RUN_ATTEMPT='2')
    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
    self.assertIn(f'{A}: not collected: no jobs named', r.stdout)
    self.assertEqual(calls, [f'api --paginate --slurp repos/{REPO}/actions/runs/{RUN}/attempts/2/jobs?per_page=100',
                             f'api --paginate --slurp repos/{REPO}/actions/runs/{RUN}/artifacts?per_page=100'])
    r, calls = self.run_step('hosted-collect', step, BOARDS=A, FAULT='collect@2', GITHUB_RUN_ATTEMPT='2')
    self.assertEqual((r.returncode, calls), (1, []))


if __name__ == '__main__':
  unittest.main()
