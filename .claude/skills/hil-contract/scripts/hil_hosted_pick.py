#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The rig's hosted builds from this attempt of the HIL workflow (.github/workflows/hil.yml), over the GitHub API
(`gh api`, GH_TOKEN).

  hil_hosted_pick.py collect --repo R --run-id N --attempt A --board B [B ...] --out DIR

Each board's `hosted-build (<B>)` leg uploads its build as `hil-hosted-<B>`, overwriting the one an earlier attempt
left. A board is collected only when its leg in this attempt's job list (a leg a partial re-run kept is listed there,
with its conclusion) concluded success: a leg that failed or was cancelled may have left an earlier attempt's
artifact, which is never used. The board's unexpired artifact, found in one listing of the run's artifacts by its
exact name, is downloaded by id, every member checked to lie under `<B>/` before any is extracted into DIR. Any other
outcome, an API error included, leaves the board out.

DIR/collection.json maps every board to the reason it was left out, '' for one collected (`hil_ci.py --collection`
admits only those). It is written whatever was collected (exit 0); DIR must not exist (exit 2).
"""
import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

COLLECTION = 'collection.json'
VERSION = 1


class ApiError(Exception):
  pass


def artifact_name(board):
  return f'hil-hosted-{board}'


def leg_name(board):
  return f'hosted-build ({board})'


def gh_api(path, out=None):
  """`gh api` of `path`, every page as a list (--paginate --slurp), or its body written to `out`."""
  if out:
    with open(out, 'wb') as f:
      r = subprocess.run(['gh', 'api', path], stdout=f, stderr=subprocess.PIPE)
  else:
    r = subprocess.run(['gh', 'api', '--paginate', '--slurp', path], capture_output=True)
  if r.returncode:
    raise ApiError(f'gh api {path}: exit {r.returncode}: {r.stderr.decode(errors="replace").strip()[:300]}')
  if not out:
    try:
      return json.loads(r.stdout)
    except ValueError as e:
      raise ApiError(f'gh api {path}: not JSON ({e})')


def listing(api, path, key):
  """Every item of a paginated list endpoint; an ApiError unless its pages hold `key` and add up to total_count."""
  pages = api(f'{path}?per_page=100')
  if not isinstance(pages, list) or not pages or \
     not all(isinstance(p, dict) and isinstance(p.get(key), list) and isinstance(p.get('total_count'), int)
             for p in pages):
    raise ApiError(f'{path}: not pages of {key}')
  items = [i for p in pages for i in p[key]]
  if len(items) != pages[0]['total_count']:
    raise ApiError(f'{path}: {len(items)} of {pages[0]["total_count"]} {key} listed')
  return items


def extract(archive, board, out):
  """The artifact's zip into `out`, refused unless it holds a file and every member lies under `<board>/`."""
  with zipfile.ZipFile(archive) as z:
    members = z.infolist()
    stray = [m.filename for m in members if not m.filename.startswith(f'{board}/')]
    if stray:
      raise ApiError(f'the artifact holds {stray[0]!r}, outside {board}/')
    if all(m.is_dir() for m in members):
      raise ApiError(f'the artifact holds no file under {board}/')
    z.extractall(out)


def reason(download, board, legs, artifacts, attempt, out):
  """'' once the board's build is extracted into out/<board>, else why not."""
  conclusions = [j.get('conclusion') for j in legs if j.get('name') == leg_name(board)]
  if len(conclusions) != 1:
    return f'{len(conclusions) or "no"} jobs named {leg_name(board)!r} in attempt {attempt}'
  if conclusions[0] != 'success':
    return f'its hosted build in attempt {attempt} concluded {conclusions[0] or "nothing"}'
  if isinstance(artifacts, str):
    return artifacts
  art = next((a['id'] for a in artifacts.get(artifact_name(board), []) if not a.get('expired')), None)
  if art is None:
    return f'no unexpired {artifact_name(board)} artifact'
  with tempfile.TemporaryDirectory() as t:
    try:
      download(art, Path(t) / 'a.zip')
      extract(Path(t) / 'a.zip', board, out)
    except (ApiError, zipfile.BadZipFile, OSError) as e:
      return f'artifact {art} cannot be extracted: {e}'[:400]
  return ''


def collect(api, download, repo, run_id, attempt, boards, out):
  out.mkdir(parents=True)
  boards = sorted(set(boards))
  try:
    legs = listing(api, f'repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
  except ApiError as e:
    picked = {b: f'the job list of attempt {attempt} is unavailable: {e}' for b in boards}
  else:
    try:
      artifacts = {}
      for a in listing(api, f'repos/{repo}/actions/runs/{run_id}/artifacts', 'artifacts'):
        artifacts.setdefault(a.get('name'), []).append(a)
    except ApiError as e:
      artifacts = f'the run\'s artifacts cannot be listed: {e}'
    picked = {b: reason(download, b, legs, artifacts, attempt, out) for b in boards}
  (out / COLLECTION).write_text(json.dumps({'version': VERSION, 'boards': picked}, indent=1))
  for b, why in picked.items():
    print(f'{b}: not collected: {why}' if why else f'{b}: collected')
  return picked


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  sub = ap.add_subparsers(dest='cmd', required=True)
  c = sub.add_parser('collect')
  c.add_argument('--repo', required=True)
  c.add_argument('--run-id', required=True, type=int)
  c.add_argument('--attempt', required=True, type=int)
  c.add_argument('--board', nargs='+', required=True)
  c.add_argument('--out', required=True, type=Path)
  args = ap.parse_args(argv)
  if args.out.exists():
    print(f'::error title=Hosted collection::{args.out} exists')
    return 2
  collect(gh_api, lambda art, dest: gh_api(f'repos/{args.repo}/actions/artifacts/{art}/zip', out=dest), args.repo,
          args.run_id, args.attempt, args.board, args.out)
  return 0


if __name__ == '__main__':
  sys.exit(main())
