#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The CI job's HIL run on this host's roster: the selection, the host pre-flight, one battery per board from
a record built here, every attempt kept, a `hil` verdict per board and one exit for the job.

  hil_ci.py (--base REF | --board B ...) --roster test/hil/ci.json --out DIR [--lock-wait S] [--fail-at STEP]

`--out` is this run's directory under a state directory kept across runs (`<state>/<run id>`): the build
record, every attempt's output, report and hil.log, and the `<board>.started` / `<board>.done` markers go
there. A `.started` without its `.done` in any earlier run is a run that ended without a report or kept a
cleanup holder (SKILL.md Recovery): that board is a blocker here until recovery removes the marker. Runs
older than PRUNE_DAYS with every marker done are removed; one with a marker left is kept, whatever its age.

Exit 0: every selected board passed. 1: a board failed or was not run (locked past `--lock-wait`, its build
or admission refused). 2: a blocker (host not ready, a run without a report, a failed cleanup), or nothing
could be selected. An empty selection with nothing uncovered exits 0 and runs nothing.
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
# SKILL.md Recovery: a battery, holder, J-Link, mtools or esptool child left on the host keeps the blocker
LEFTOVERS = (['pgrep', '-ax', 'JLinkExe'], ['pgrep', '-ax', 'mcopy'], ['pgrep', '-af', r'[h]il_test\.py'],
             ['pgrep', '-af', r'[e]sp_session\.py'], ['pgrep', '-af', r'[u]sb_dfu\.py'])
LOCK_POLL = 15
LOCK_WAIT = 600
PRUNE_DAYS = 30


def run(cmd, **kw):
  return subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, **kw)


def roster_boards(roster):
  try:
    return sorted(b['name'] for b in json.loads((ROOT / roster).read_text())['boards'])
  except (OSError, ValueError, KeyError, TypeError) as e:
    raise SystemExit(f'cannot read boards from {roster}: {e}')


def selection(base, roster):
  """`hil` of the build contract's selection manifest for the change since `base`: (boards, uncovered)."""
  r = run([sys.executable, CHECK_BUILD, '--select-only', '--base', base, '--hil-config', roster])
  if r.returncode:
    raise SystemExit(f'selection failed (exit {r.returncode}): {(r.stdout or r.stderr).strip()[-400:]}')
  hil = json.loads(r.stdout)['hil']
  return hil['boards'], hil['uncovered']


def leftovers():
  """Lines naming processes the Recovery list says must be gone before a board is touched; a pgrep that could
  not look (any exit but 0 and 1) is a line too, since absence is then not established."""
  found = []
  for cmd in LEFTOVERS:
    r = run(cmd)
    if r.returncode == 0:
      found += [f'{cmd[-1]}: {line}' for line in r.stdout.splitlines() if line.strip()]
    elif r.returncode != 1:
      found.append(f'{cmd[-1]}: pgrep exit {r.returncode} {r.stderr.strip()[:100]}')
  return found


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


def battery(board, roster, record, out, attempt, fail_at=None):
  """One `hil_test.py run`, its output streamed to `out/<board>/attempt-N/` as it comes, so a killed run keeps
  what it printed; its last JSON line is the report (SKILL.md Results), copied there with hil.log. A runner
  left holding the board in process (`cleanup.holder.inProcess`, Recovery) never exits: it is not waited for.
  Returns (exit or None, report or None, attempt dir)."""
  where = out / board / f'attempt-{attempt}'
  where.mkdir(parents=True)
  cmd = [sys.executable, HIL_TEST, 'run', '-b', board, '--build-record', record]
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
  row = next((r for r in (report or {}).get('results', []) if r.get('board') == board), {})
  in_process = ((row.get('cleanup') or {}).get('holder') or {}).get('inProcess')
  code = None if in_process else p.wait()
  if report and report.get('reportPath'):
    src = Path(report['reportPath'])
    for name in (src.name, 'hil.log'):
      if (src.parent / name).is_file():
        shutil.copy(src.parent / name, where / name)
  return code, report, where


def verdict(code, report, board):
  """The `hil` verdict of one attempt from the report's row (SKILL.md Verdicts): (verdict, detail, locked)."""
  if report is None:
    return 'blocker', f'run ended without a report (exit {code})', False
  row = next((r for r in report.get('results', []) if r.get('board') == board), None)
  if row is None:
    return 'blocker', f'report has no row for {board} (exit {code}): {report.get("caveat") or report.get("error")}', False
  cleanup = row.get('cleanup') or {}
  if code in (4, None) or row.get('ran') is None or cleanup.get('heldAfter'):
    return 'blocker', f'cleanup failed or no report; board held: {row.get("detail")} {cleanup}'[:400], False
  if row.get('locked'):
    return 'not-run', f'locked: {row.get("detail")}', True
  if not row.get('ran'):
    return 'not-run', str(row.get('detail') or report.get('error')), False
  failed = next((s for s in row.get('steps', []) if not s.get('pass')), None)
  if row.get('pass') and cleanup.get('pass'):
    return 'pass', '', False
  if failed is None:
    return 'blocker', f'aborted: {row.get("detail")}', False
  if cleanup.get('state') == 'untouched':
    return 'not-run', f'{failed["step"]}: {failed.get("detail")} (nothing written)', False
  return 'fail', f'{failed["step"]}: {failed.get("detail")}', False


def run_board(board, roster, out, state, lock_wait, fail_at=None):
  """Every attempt on one board: a locked board is tried again every LOCK_POLL s within `lock_wait`."""
  earlier = unfinished(state, board)
  if earlier:
    return {'board': board, 'verdict': 'blocker', 'attempts': 0,
            'detail': f'run {", ".join(earlier)} ended without finishing: recover the board, then remove its marker'}
  record, ok, why = build_record(board, roster, out)
  if not ok:
    return {'board': board, 'verdict': 'not-run', 'attempts': 0, 'detail': why}
  (out / f'{board}.started').touch()
  deadline = time.monotonic() + lock_wait
  attempt = 0
  while True:
    attempt += 1
    code, report, where = battery(board, roster, record, out, attempt, fail_at)
    v, detail, locked = verdict(code, report, board)
    if not locked or time.monotonic() >= deadline:
      break
    time.sleep(LOCK_POLL)
  if v != 'blocker':
    (out / f'{board}.done').touch()
  return {'board': board, 'verdict': v, 'attempts': attempt, 'detail': detail, 'report': str(where)}


def summary(rows, uncovered, roster):
  lines = [f'HIL on `{roster}`', '', '| board | verdict | attempts | detail |', '|---|---|---:|---|']
  lines += [f'| {r["board"]} | {r["verdict"]} | {r["attempts"]} | {r["detail"].replace("|", "/")} |' for r in rows]
  if uncovered:
    lines += ['', 'Uncovered (no roster board on this host can run it):']
    lines += [f'- `{u["target"]}`: {u["reason"]}' for u in uncovered]
  return '\n'.join(lines) + '\n'


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  what = ap.add_mutually_exclusive_group(required=True)
  what.add_argument('--base', help="the change's base ref: the battery on the boards the selection reaches")
  what.add_argument('--board', action='append', help='this roster board, whatever changed (repeatable)')
  ap.add_argument('--roster', required=True)
  ap.add_argument('--out', required=True, type=Path, help="this run's directory under the state directory")
  ap.add_argument('--lock-wait', type=int, default=LOCK_WAIT, help='seconds to keep trying a locked board')
  ap.add_argument('--fail-at', choices=STEPS, help='acceptance only (SKILL.md Execution): passed to every battery')
  args = ap.parse_args(argv)
  known = roster_boards(args.roster)
  if args.base:
    boards, uncovered = selection(args.base, args.roster)
  else:
    boards, uncovered = sorted(set(args.board)), []
    if set(boards) - set(known):
      ap.error(f'not in {args.roster}: {sorted(set(boards) - set(known))}')
  args.out.mkdir(parents=True, exist_ok=True)
  state = args.out.parent
  prune(state, keep=args.out)
  rows = []
  if boards:
    left = leftovers()
    if left:
      rows = [{'board': b, 'verdict': 'blocker', 'attempts': 0,
               'detail': 'host not ready (SKILL.md Recovery): ' + '; '.join(left)[:300]} for b in boards]
    else:
      rows = [run_board(b, args.roster, args.out, state, args.lock_wait, args.fail_at) for b in boards]
  text = summary(rows, uncovered, args.roster)
  sys.stdout.write(text)
  if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
      f.write(text)
  (args.out / 'summary.json').write_text(json.dumps({'boards': rows, 'uncovered': uncovered}, indent=1))
  verdicts = {r['verdict'] for r in rows}
  return 2 if 'blocker' in verdicts else 1 if verdicts & {'fail', 'not-run'} else 0


if __name__ == '__main__':
  sys.exit(main())
