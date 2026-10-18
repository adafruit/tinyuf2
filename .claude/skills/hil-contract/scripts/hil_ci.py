#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The CI job's HIL run on this host's roster: one battery per named board from a record built here, every
run kept, a `hil` verdict per board and one exit for the job.

  hil_ci.py --board B [B ...] --roster test/hil/ci.json --out DIR [--lock-wait S] [--fail-at STEP]

`--out` is this run's directory under a state directory kept across runs (`<state>/<run id>`): the build
record, each board's run directory (`hil_test.py run --run-root`: its report, hil.log and output) and the
`<board>.started` / `<board>.done` markers go there. A `.started` without its `.done` in any earlier run is a
run that ended without a report or kept a cleanup holder (SKILL.md Recovery): that board is a blocker here
until recovery removes the marker. Runs older than PRUNE_DAYS with every marker done are removed; one with a
marker left is kept, whatever its age.

Exit 0: every board passed. 1: a board failed or was not run (held past `--lock-wait`, its build or admission
refused). 2: a blocker (a run without a report, a failed cleanup, a cleanup holder or a stale probe session on
the board).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CHECK_BUILD = ROOT / '.claude' / 'skills' / 'build' / 'scripts' / 'check_build.py'
HIL_TEST = Path(__file__).resolve().with_name('hil_test.py')
STEPS = ('install', 'dfu', 'copy', 'app-ran', 'reenter', 'recopy', 'cleanup')   # hil_test.py --fail-at
LOCK_WAIT = 600
PRUNE_DAYS = 30


def run(cmd):
  return subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True)


def roster_boards(roster):
  try:
    return sorted(b['name'] for b in json.loads((ROOT / roster).read_text())['boards'])
  except (OSError, ValueError, KeyError, TypeError) as e:
    raise SystemExit(f'cannot read boards from {roster}: {e}')


def unfinished(state, board):
  """Earlier runs under `state` whose battery on `board` started and never finished."""
  return sorted(p.parent.name for p in state.glob(f'*/{board}.started') if not p.with_suffix('.done').exists())


def prune(state, keep, days=PRUNE_DAYS):
  """Remove the runs under `state` older than `days` whose every started board finished; never `keep`."""
  cutoff = time.time() - days * 86400
  for d in state.iterdir():
    if d.is_dir() and d != keep and d.stat().st_mtime < cutoff and \
       all(p.with_suffix('.done').exists() for p in d.glob('*.started')):
      shutil.rmtree(d, ignore_errors=True)


def build_record(board, roster, out):
  record = out / f'{board}.build.json'
  r = run([sys.executable, CHECK_BUILD, '--board', board, '--backend', 'cmake', '--shared', '--hil-config', roster])
  record.write_text(r.stdout)
  try:
    rec = json.loads(r.stdout)
    row = next(b for b in rec['boards'] if b['board'] == board)
    ok = rec['pass'] and row['status'] == 'ok'
    why = '' if ok else f'build {row["status"]}: {row.get("firstError", "")}'[:400]
  except (ValueError, KeyError, StopIteration):
    ok, why = False, f'build record unreadable (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}'
  return record, ok, why


def battery(board, roster, record, where, lock_wait, fail_at=None):
  """One `hil_test.py run` with its run directory under `where`, its output streamed to `where/stdout.txt` as
  it comes, so a killed run keeps what it printed; its last JSON line is the report (SKILL.md Results). A runner
  left holding the board in process (`cleanup.holder.inProcess`, Recovery) never exits: it is not waited for.
  Returns (exit or None, report or None)."""
  where.mkdir(parents=True)
  cmd = [sys.executable, HIL_TEST, 'run', '-b', board, '--build-record', record, '--run-root', where,
         '--lock-wait', lock_wait]
  if fail_at:
    cmd += ['--fail-at', fail_at]
  report = None
  with open(where / 'stderr.txt', 'w') as err, open(where / 'stdout.txt', 'w') as log:
    p = subprocess.Popen([str(c) for c in cmd + [roster]], cwd=ROOT, stdout=subprocess.PIPE, stderr=err, text=True)
    for line in p.stdout:
      log.write(line)
      log.flush()
      if line.startswith('{'):
        try:
          report = json.loads(line)
        except ValueError:
          pass
    p.stdout.close()
  row = next((r for r in (report or {}).get('results', []) if r.get('board') == board), {})
  in_process = ((row.get('cleanup') or {}).get('holder') or {}).get('inProcess')
  return (None if in_process else p.wait()), report


def verdict(code, report, board):
  """The `hil` verdict of one run from the report's row (SKILL.md Verdicts): (verdict, detail)."""
  if report is None:
    return 'blocker', f'run ended without a report (exit {code})'
  row = next((r for r in report.get('results', []) if r.get('board') == board), None)
  if row is None:
    return 'blocker', f'report has no row for {board} (exit {code}): {report.get("caveat") or report.get("error")}'
  cleanup = row.get('cleanup') or {}
  if code in (4, None) or row.get('ran') is None or cleanup.get('heldAfter'):
    return 'blocker', f'cleanup failed or no report; board held: {row.get("detail")} {cleanup}'[:400]
  if row.get('probeUsers'):
    return 'blocker', str(row.get('detail'))
  if row.get('locked'):
    return ('blocker' if row.get('recoveryBlocker') else 'not-run'), f'locked: {row.get("detail")}'
  if not row.get('ran'):
    return 'not-run', str(row.get('detail') or report.get('error'))
  failed = next((s for s in row.get('steps', []) if not s.get('pass')), None)
  if row.get('pass') and cleanup.get('pass'):
    return 'pass', ''
  if failed is None:
    return 'blocker', f'aborted: {row.get("detail")}'
  if cleanup.get('state') == 'untouched':
    return 'not-run', f'{failed["step"]}: {failed.get("detail")} (nothing written)'
  return 'fail', f'{failed["step"]}: {failed.get("detail")}'


def run_board(board, roster, out, state, lock_wait, fail_at=None):
  earlier = unfinished(state, board)
  if earlier:
    return {'board': board, 'verdict': 'blocker',
            'detail': f'run {", ".join(earlier)} ended without finishing: recover the board, then remove its marker'}
  record, ok, why = build_record(board, roster, out)
  if not ok:
    return {'board': board, 'verdict': 'not-run', 'detail': why}
  (out / f'{board}.started').touch()
  code, report = battery(board, roster, record, out / board, lock_wait, fail_at)
  v, detail = verdict(code, report, board)
  if v != 'blocker':
    (out / f'{board}.done').touch()
  return {'board': board, 'verdict': v, 'detail': detail, 'run': str(out / board)}


def summary(rows, roster):
  lines = [f'HIL on `{roster}`', '', '| board | verdict | detail |', '|---|---|---|']
  lines += [f'| {r["board"]} | {r["verdict"]} | {r["detail"].replace("|", "/")} |' for r in rows]
  return '\n'.join(lines) + '\n'


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  ap.add_argument('--board', nargs='+', required=True, help='roster boards to run, whatever changed')
  ap.add_argument('--roster', required=True)
  ap.add_argument('--out', required=True, type=Path, help="this run's directory under the state directory")
  ap.add_argument('--lock-wait', type=int, default=LOCK_WAIT, help='seconds each battery keeps trying a held board')
  ap.add_argument('--fail-at', choices=STEPS, help='acceptance only (SKILL.md Execution): passed to every battery')
  args = ap.parse_args(argv)
  boards = sorted(set(args.board))
  unknown = sorted(set(boards) - set(roster_boards(args.roster)))
  if unknown:
    ap.error(f'not in {args.roster}: {unknown}')
  args.out.mkdir(parents=True, exist_ok=True)
  state = args.out.parent
  prune(state, keep=args.out)
  rows = [run_board(b, args.roster, args.out, state, args.lock_wait, args.fail_at) for b in boards]
  text = summary(rows, args.roster)
  sys.stdout.write(text)
  if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
      f.write(text)
  (args.out / 'summary.json').write_text(json.dumps({'boards': rows}, indent=1))
  verdicts = {r['verdict'] for r in rows}
  return 2 if 'blocker' in verdicts else 1 if verdicts & {'fail', 'not-run'} else 0


if __name__ == '__main__':
  sys.exit(main())
