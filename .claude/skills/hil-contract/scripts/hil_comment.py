#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The HIL workflow's sticky pull request comment: hil_ci.py's summary.json and the select job's selection rendered
as Markdown, and the check that this run is still the newest for the PR's head before it is posted.

  hil_comment.py render --summary PATH --selection PATH --roster NAME --head SHA --tested SHA --run-url URL
                        --run-id N --attempt N --out FILE
  hil_comment.py fresh --repo R --pr N --head SHA --run-id N --attempt N

A missing or unreadable `--summary` or `--selection` renders as such, never as a pass or as no affected boards.
`fresh` exits 0 when the run is the newest attempt of the newest HIL run for the PR's current head, 1 when it is
stale (the reason on stdout), 2 when the API cannot tell. Stdlib only: it runs on a hosted runner.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hil_ci  # noqa: E402   its battery steps
import hil_run_report as run_report  # noqa: E402   its step marks and cell escaping

TITLE = '## Hardware-in-the-loop (HIL) Test Report'
STEPS = tuple(s for s in hil_ci.STEPS if s != 'cleanup')   # the cleanup is the blinky column
ABSENT = '—'
cell = run_report.cell   # report text kept on one Markdown line and out of the table's column syntax
KINDS = (('passed', '✅'), ('failed', '❌'), ('blocked', '⛔'), ('not run', '⚪'))
LEGEND = "✅ passed · ❌ failed · blank not run · — not in this board's run · run time includes lock wait and blinky"


def duration(s):
  """Seconds as `49s`, `4m30s` or `1h2m`; ABSENT when there are none."""
  if s is None:
    return ABSENT
  s = int(s)
  if s < 60:
    return f'{s}s'
  if s < 3600:
    return f'{s // 60}m{s % 60}s' if s % 60 else f'{s // 60}m'
  return f'{s // 3600}h{s % 3600 // 60}m' if s % 3600 // 60 else f'{s // 3600}h'


def kind(r):
  """The board's count: a blocker under either verdict, a pass only under both."""
  native = r.get('verdict')
  shared = r.get('sharedVerdict', native)
  if 'blocker' in (native, shared):
    return 'blocked'
  if native == shared == 'pass':
    return 'passed'
  return 'failed' if 'fail' in (native, shared) else 'not run'


def withheld(r):
  """A row whose report the upload withholds or the shared run rules could not read (`report <outcome>: ...`, as
  report not prepared, corrupt or missing): none of its report material is shown."""
  return not r.get('viewsUploaded', True) or bool(r.get('unsafeArtifacts')) or r.get('report') is False or \
      r.get('sharedVerdict') == 'blocker' and str(r.get('sharedDetail', '')).startswith('report ')


def step_cell(r, step):
  steps = r.get('steps') or {}
  if withheld(r) or not steps:
    return ''
  if step == 'recopy' and not r.get('espressif'):
    return ABSENT   # only the Espressif battery has recopy
  return run_report.STEP_MARK.get(steps.get(step), '')


def table_row(r):
  blinky = '' if withheld(r) else run_report.STEP_MARK.get(r.get('cleanupPass'), '')
  cells = [cell(r['board']), *(step_cell(r, s) for s in STEPS), blinky, duration(r.get('buildS')),
           duration(r.get('runS'))]
  return '| ' + ' | '.join(cells) + ' |'


def note(r):
  """The board's native detail, both verdicts where they differ, and whether its report is withheld."""
  hidden = withheld(r)
  failed = None if hidden else next((s for s, ok in (r.get('steps') or {}).items() if not ok), None)
  where = failed or ('blinky' if not hidden and r.get('cleanupPass') is False else r.get('phase') or 'run')
  native, shared, shared_detail = r.get('verdict'), r.get('sharedVerdict', r.get('verdict')), r.get('sharedDetail')
  detail = str(r.get('detail') or shared_detail or native)
  if failed and detail.startswith(f'{failed}: '):
    detail = detail[len(failed) + 2:]
  extra = []
  if shared != native:
    extra.append(f'native {native}, shared run rules {shared}' +
                 (f': {shared_detail}' if shared_detail and shared_detail != detail else ''))
  if hidden:
    extra.append('report withheld')
  return f'- `{cell(r["board"])}` {where}: {cell(detail)}' + (f' ({cell("; ".join(extra))})' if extra else '')


def report(summary, views):
  """`views` is the upload's decision (hil_ci.py's upload-views): anything but `upload` withholds every report."""
  rows = [dict(r, viewsUploaded=views == 'upload') for r in summary['boards']]
  counts = [f'{icon} {sum(kind(r) == k for r in rows)} {k}' for k, icon in KINDS if any(kind(r) == k for r in rows)]
  head = f'**{" · ".join(counts)}**' if counts else '**No board results.**'
  if summary.get('elapsedS') is not None:
    head += f' · HIL driver elapsed {duration(summary["elapsedS"])}'
  lines = [head, '']
  if rows:
    lines += ['| Board | ' + ' | '.join(STEPS) + ' | blinky | build | run |',
              '| --- | ' + ' | '.join(':-:' for _ in STEPS) + ' | :-: | --: | --: |']
    lines += [table_row(r) for r in rows] + ['', LEGEND, '']
  notes = [note(r) for r in rows if kind(r) != 'passed']
  if views != 'upload':
    notes.append(f'- report views withheld by the upload (upload-views: {cell(views or "missing")}): no steps shown')
  return lines + (notes + [''] if notes else [])


def uncovered(selection):
  items = (selection or {}).get('uncovered') or []
  if not items:
    return []
  return ['Not covered on this rig:', *(f'- `{cell(u["target"])}`: {cell(u["reason"])}' for u in items), '']


def render(summary, selection, meta, views='upload'):
  """The comment body. `summary` and `selection` are the parsed files or None; `meta` is {roster, head, tested,
  runUrl, runId, attempt}."""
  lines = [TITLE, '', f'### {meta["roster"]} (ci.lan)', '',
           f'_PR head `{meta["head"][:7]}` · tested `{meta["tested"][:7]}` · '
           f'[run {meta["runId"]}, attempt {meta["attempt"]}]({meta["runUrl"]})_', '']
  boards = None if selection is None else selection.get('boards') or []
  if boards is None:
    lines += ['_Selection unavailable._', '']
  elif not boards:
    lines += ['_No affected boards on this rig; no HIL run for this push._', ''] + uncovered(selection)
    return finish(lines)
  else:
    n = f'{len(boards)} board{"s" if len(boards) != 1 else ""}'
    lines += [f'_Every roster board: the HIL runner or a roster changed ({n})._' if selection.get('full')
              else f'_Boards the change reaches: {len(boards)}._', '']
  if summary is None:
    lines += ['**HIL report unavailable: the run ended without a summary (run incomplete).**', '']
  else:
    lines += report(summary, views)
  lines += uncovered(selection) + [f'_[Records, reports and logs]({meta["runUrl"]})_']
  return finish(lines)


def finish(lines):
  """The body with every @mention neutralised: report text never pings anyone."""
  while lines and not lines[-1]:
    lines.pop()
  return re.sub(r'@(?=\w)', '@​', '\n'.join(lines)) + '\n'


def fresh(api, repo, pr, head, run_id, attempt):
  """(fresh, reason): this run is the newest attempt of the newest HIL run for the PR's current head. `api(path)`
  returns the parsed JSON of a GitHub REST GET; its errors propagate."""
  now = api(f'repos/{repo}/pulls/{pr}')['head']['sha']
  if now != head:
    return False, f'PR #{pr} head moved to {now[:7]}; this run tested {head[:7]}'
  runs = api(f'repos/{repo}/actions/workflows/hil.yml/runs?event=pull_request&head_sha={head}&per_page=1')
  runs = runs['workflow_runs']
  if not runs:
    return False, f'no HIL run listed for {head[:7]}'
  if int(runs[0]['id']) != int(run_id):
    return False, f'run {runs[0]["id"]} is newer than run {run_id} for {head[:7]}'
  latest = runs[0]['run_attempt']
  if int(latest) != int(attempt):
    return False, f'run {run_id} attempt {latest} is newer than attempt {attempt}'
  return True, 'fresh'


def gh_api(path):
  r = subprocess.run(['gh', 'api', path], capture_output=True, text=True)
  if r.returncode:
    raise RuntimeError(f'gh api {path}: exit {r.returncode}: {r.stderr.strip()}')
  return json.loads(r.stdout)


def read_json(path, key):
  """The parsed file, or None when it is missing, unreadable or not the expected object."""
  try:
    with open(path, encoding='utf-8') as f:
      doc = json.load(f)
  except (OSError, ValueError):
    return None
  return doc if isinstance(doc, dict) and isinstance(doc.get(key), list) else None


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  sub = ap.add_subparsers(dest='cmd', required=True)
  r = sub.add_parser('render', help='write the comment body')
  r.add_argument('--summary', required=True, help="hil_ci.py's summary.json, which may be missing")
  r.add_argument('--selection', required=True, help="the select job's hil-selection.json, which may be missing")
  r.add_argument('--views', required=True, help="hil_ci.py's upload-views decision file, which may be missing")
  r.add_argument('--roster', required=True, help='roster file name, e.g. ci.json')
  r.add_argument('--head', required=True, help="the PR's head SHA")
  r.add_argument('--tested', required=True, help='the merge commit the rig tested')
  r.add_argument('--run-url', required=True)
  r.add_argument('--run-id', required=True)
  r.add_argument('--attempt', required=True)
  r.add_argument('--out', required=True)
  f = sub.add_parser('fresh', help='exit 0 when this run may post, 1 stale, 2 API error')
  f.add_argument('--repo', required=True)
  f.add_argument('--pr', required=True)
  f.add_argument('--head', required=True)
  f.add_argument('--run-id', required=True)
  f.add_argument('--attempt', required=True)
  args = ap.parse_args(argv)
  if args.cmd == 'render':
    meta = {'roster': args.roster, 'head': args.head, 'tested': args.tested,
            'runUrl': args.run_url, 'runId': args.run_id, 'attempt': args.attempt}
    try:
      with open(args.views, encoding='utf-8') as f:
        views = f.read().strip()
    except (OSError, UnicodeError):
      views = None
    body = render(read_json(args.summary, 'boards'), read_json(args.selection, 'boards'), meta, views)
    with open(args.out, 'w', encoding='utf-8') as out:
      out.write(body)
    return 0
  try:
    ok, why = fresh(gh_api, args.repo, args.pr, args.head, args.run_id, args.attempt)
  except (RuntimeError, OSError, ValueError, KeyError, TypeError, IndexError) as e:
    print(f'cannot tell whether run {args.run_id} is fresh: {type(e).__name__}: {e}', file=sys.stderr)
    return 2
  print(why)
  return 0 if ok else 1


if __name__ == '__main__':
  sys.exit(main())
