#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The HIL workflow's per-board hosted builds (.github/workflows/hil.yml), over the GitHub API (`gh api`, GH_TOKEN):
one `hosted-build (<board>)` leg per board uploads `hil-hosted-<board>`, and `hosted-collect` hands the rig the latest
attempt's builds, never an older one's.

  hil_hosted_pick.py clear --repo R --run-id N --board B
  hil_hosted_pick.py collect --repo R --run-id N --attempt A --board B [B ...] --out DIR
  hil_hosted_pick.py fault --spec SPEC --step STEP [--board B] --attempt A

`clear`, a leg's first step, deletes every artifact of the run named exactly `hil-hosted-<B>`: a leg that succeeds has
deleted every earlier attempt's build of its board, and any API error fails it (exit 1).

`collect` takes each B's leg from this attempt's job list (a leg a partial re-run kept is listed in it with its
conclusion). A leg that concluded success with exactly one unexpired `hil-hosted-<B>` artifact has that artifact, by
id, extracted into DIR/B; anything else, an API error included, leaves B out with the reason. DIR/collection.json
records per B its leg's conclusion and the artifact id, or the reason; it is written whatever was collected (exit 0),
and DIR must not exist (exit 2).

`fault`, acceptance only: exit 1 when SPEC (the dispatch's `hosted_fault`, space separated `<step>:<board>@<attempt>`,
or `collect@<attempt>`) names this step, board and attempt; 2 on a malformed SPEC.
"""
import argparse
import json
import re
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath

COLLECTION = 'collection.json'
VERSION = 1
PER_PAGE = 100
LEG_STEPS = ('pre-clear', 'clear', 'build')
FAULT = re.compile(rf'(?:({"|".join(LEG_STEPS)}):([^\s@]+)|(collect))@([1-9]\d*)')


class ApiError(Exception):
  pass


def artifact_name(board):
  return f'hil-hosted-{board}'


def leg_name(board):
  return f'hosted-build ({board})'


def gh_api(path, method='GET', out=None):
  """`gh api` of `path`: its JSON (None when empty), or its body written to `out`."""
  cmd = ['gh', 'api', '-X', method, path]
  if out is None:
    r = subprocess.run(cmd, capture_output=True)
  else:
    with open(out, 'wb') as f:
      r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
  if r.returncode:
    raise ApiError(f'gh api -X {method} {path}: exit {r.returncode}: {r.stderr.decode(errors="replace").strip()[:300]}')
  if out is None:
    try:
      return json.loads(r.stdout) if r.stdout.strip() else None
    except ValueError as e:
      raise ApiError(f'gh api {path}: not JSON ({e})')


def listing(api, path, key):
  """Every item of a paginated list endpoint, deduplicated by id; an ApiError unless the pages add up to its
  total_count."""
  items, page = {}, 1
  sep = '&' if '?' in path else '?'
  while True:
    d = api(f'{path}{sep}per_page={PER_PAGE}&page={page}')
    try:
      batch, total, before = d[key], d['total_count'], len(items)
      for i in batch:
        items.setdefault(i['id'], i)
    except (TypeError, KeyError) as e:
      raise ApiError(f'{path}: page {page} has no {key}, total_count or ids ({e!r})')
    if len(items) >= total:
      return list(items.values())
    if len(items) == before:
      raise ApiError(f'{path}: {len(items)} of {total} {key} listed, then a page with none new')
    page += 1


def run_artifacts(api, repo, run_id, board):
  """The run's artifacts named exactly `hil-hosted-<board>`, expired ones included."""
  name = artifact_name(board)
  arts = listing(api, f'repos/{repo}/actions/runs/{run_id}/artifacts?name={urllib.parse.quote(name)}', 'artifacts')
  return [a for a in arts if a.get('name') == name]


def clear(api, repo, run_id, board):
  gone = []
  for a in run_artifacts(api, repo, run_id, board):
    api(f'repos/{repo}/actions/artifacts/{a["id"]}', method='DELETE')
    gone.append(a['id'])
  print(f'{artifact_name(board)}: deleted {gone or "none"}')


def extract(archive, board, out):
  """The artifact's zip into `out`: every member a file or dir under `<board>/`, no link, no escape."""
  with zipfile.ZipFile(archive) as z:
    members = z.infolist()
    for m in members:
      p = PurePosixPath(m.filename)
      if '\\' in m.filename or p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != board or \
         stat.S_ISLNK(m.external_attr >> 16):
        raise ApiError(f'the artifact holds {m.filename!r}, not a file under {board}/')
    if not any(not m.is_dir() for m in members):
      raise ApiError(f'the artifact holds no file under {board}/')
    z.extractall(out)


def pick(api, download, repo, run_id, attempt, board, jobs, out):
  """One board's collection entry: {'conclusion', 'artifact'} once extracted into out/<board>, else with 'reason'."""
  if isinstance(jobs, str):
    return {'conclusion': None, 'reason': jobs}
  legs = [j for j in jobs if j.get('name') == leg_name(board)]
  if len(legs) != 1:
    return {'conclusion': None, 'reason': f'{len(legs) or "no"} job{"s" if len(legs) > 1 else ""} named '
                                          f'{leg_name(board)!r} in attempt {attempt}'}
  leg = legs[0]
  conclusion = leg.get('conclusion')
  if leg.get('status') != 'completed' or conclusion != 'success':
    return {'conclusion': conclusion, 'reason': f'its hosted build in attempt {attempt} is '
                                                f'{conclusion or leg.get("status") or "of unknown state"}'}
  try:
    arts = run_artifacts(api, repo, run_id, board)
  except ApiError as e:
    return {'conclusion': conclusion, 'reason': f'its artifact cannot be listed: {e}'}
  live = [a for a in arts if not a.get('expired')]
  if len(live) != 1:
    expired = len(arts) - len(live)
    return {'conclusion': conclusion,
            'reason': f'{len(live) or "no"} unexpired {artifact_name(board)} artifact{"s" if len(live) > 1 else ""}'
                      + (f' ({expired} expired)' if expired else '')}
  art = live[0]['id']
  with tempfile.TemporaryDirectory() as t:
    try:
      download(art, Path(t) / 'a.zip')
      extract(Path(t) / 'a.zip', board, out)
    except (ApiError, zipfile.BadZipFile, OSError) as e:
      return {'conclusion': conclusion, 'reason': f'artifact {art} cannot be extracted: {e}'[:400]}
  return {'conclusion': conclusion, 'artifact': art}


def collect(api, download, repo, run_id, attempt, boards, out):
  out.mkdir(parents=True)
  try:
    jobs = listing(api, f'repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
  except ApiError as e:
    jobs = f'the job list of attempt {attempt} is unavailable: {e}'
  picked = {b: pick(api, download, repo, run_id, attempt, b, jobs, out) for b in sorted(set(boards))}
  (out / COLLECTION).write_text(json.dumps({'version': VERSION, 'run': run_id, 'attempt': attempt, 'boards': picked},
                                           indent=1))
  for b, e in picked.items():
    print(f'{b}: artifact {e["artifact"]}' if 'artifact' in e else f'{b}: not collected: {e["reason"]}')
  return picked


def load_collection(path):
  """collection.json's per-board entries; ValueError or OSError when it is not one."""
  d = json.loads(Path(path).read_text())
  if not isinstance(d, dict) or d.get('version') != VERSION or not isinstance(d.get('boards'), dict) or \
     not all(isinstance(e, dict) for e in d['boards'].values()):
    raise ValueError(f'{path} is no version {VERSION} hosted collection')
  return d['boards']


def gap(boards, board):
  """Why `board` has no collected hosted build (load_collection's `boards`), or None."""
  e = boards.get(board)
  if e is None:
    return f'the hosted collection has no entry for {board}'
  return None if e.get('artifact') else f'hosted build not collected: {e.get("reason") or "no reason recorded"}'


def faulted(spec, step, board, attempt):
  """Whether `spec` injects a fault at `step` (of `board`'s leg, or `collect`) in `attempt`; ValueError when a token
  is malformed."""
  for token in spec.split():
    m = FAULT.fullmatch(token)
    if not m:
      raise ValueError(f'hosted_fault {token!r} is neither <{"|".join(LEG_STEPS)}>:<board>@<attempt> nor '
                       'collect@<attempt>')
    if int(m[4]) == attempt and ((m[3] or m[1]) == step and (m[3] or m[2] == board)):
      return True
  return False


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  sub = ap.add_subparsers(dest='cmd', required=True)
  for name in ('clear', 'collect'):
    p = sub.add_parser(name)
    p.add_argument('--repo', required=True)
    p.add_argument('--run-id', required=True, type=int)
  sub.choices['clear'].add_argument('--board', required=True)
  c = sub.choices['collect']
  c.add_argument('--attempt', required=True, type=int)
  c.add_argument('--board', nargs='+', required=True)
  c.add_argument('--out', required=True, type=Path)
  f = sub.add_parser('fault')
  f.add_argument('--spec', default='')
  f.add_argument('--step', required=True, choices=(*LEG_STEPS, 'collect'))
  f.add_argument('--board')
  f.add_argument('--attempt', required=True, type=int)
  args = ap.parse_args(argv)
  if args.cmd == 'fault':
    if (args.step == 'collect') != (args.board is None):
      ap.error('--board names a leg step\'s board, and only that')
    try:
      hit = faulted(args.spec, args.step, args.board, args.attempt)
    except ValueError as e:
      print(f'::error title=Malformed hosted_fault::{e}')
      return 2
    if hit:
      print(f'::error title=Injected fault::{args.step} {args.board or ""} in attempt {args.attempt} (hosted_fault)')
      return 1
    return 0
  if args.cmd == 'clear':
    try:
      clear(gh_api, args.repo, args.run_id, args.board)
    except ApiError as e:
      print(f'::error title=Earlier hosted build not deleted::{e}')
      return 1
    return 0
  if args.out.exists():
    print(f'::error title=Hosted collection::{args.out} exists')
    return 2
  collect(gh_api, lambda art, dest: gh_api(f'repos/{args.repo}/actions/artifacts/{art}/zip', out=dest), args.repo,
          args.run_id, args.attempt, args.board, args.out)
  return 0


if __name__ == '__main__':
  sys.exit(main())
