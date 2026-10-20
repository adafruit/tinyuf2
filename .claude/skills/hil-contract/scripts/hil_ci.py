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
marker left is kept, whatever its age. Each battery's report pair is prepared for the upload (prepare()), and
summary.json carries the shared run rules' `sharedVerdict` beside each native `verdict`, which alone decides the exit.

Exit 0: every board passed. 1: a board failed or was not run (held past `--lock-wait`, its build or admission
refused). 2: a blocker (a run without a report, a failed cleanup, a cleanup holder, a dead battery's record or a
takeover journal, or a stale probe session on the board).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True   # as hil_test.py: nothing CI imports writes into the checkout it builds
import hil_run_report as run_report  # noqa: E402
from hil_run_report import verdict  # noqa: E402   the report adapter's mapping (SKILL.md Verdicts)

ROOT = Path(__file__).resolve().parents[4]
CHECK_BUILD = ROOT / '.claude' / 'skills' / 'build' / 'scripts' / 'check_build.py'
HIL_TEST = Path(__file__).resolve().with_name('hil_test.py')
# the pinned report core, which every battery's own pin check covered in this checkout
REPORT_CORE = ROOT / 'lib' / 'agentrc' / 'skills' / 'hil' / 'scripts' / 'hil_report_core.py'
UNPREPARED = 'report not prepared'
NOTICE = '**HIL report unavailable'   # the core's NOTICE, which this must write when the core itself failed
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


def launch(cmd, where, board, cwd=None):
  """One `hil_test.py run` of `board` (`cmd`, its argv), its output streamed to `where/stdout.txt` as it comes, so a
  killed run keeps what it printed, and its stderr to `where/stderr.txt`; its last JSON line is the report (SKILL.md
  Results). A runner that became the in-process cleanup holder (`cleanup.holder.inProcess`, Recovery) printed its
  report, closed its stdio and never exits: it is left running, not waited for. Returns (report or None, exit or None,
  held), `held` true for that live holder, whose exit is None."""
  report = None
  with open(where / 'stderr.txt', 'w') as err, open(where / 'stdout.txt', 'w') as log:
    p = subprocess.Popen([str(c) for c in cmd], cwd=cwd or ROOT, stdout=subprocess.PIPE, stderr=err, text=True)
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
  if ((row.get('cleanup') or {}).get('holder') or {}).get('inProcess') and p.poll() is None:
    return report, None, True
  return report, p.wait(), False


def battery(board, roster, record, where, lock_wait, fail_at=None):
  """One `hil_test.py run` with its run directory under `where` (launch()). Returns (exit or None, report or None)."""
  where.mkdir(parents=True)
  cmd = [sys.executable, HIL_TEST, 'run', '-b', board, '--build-record', record, '--run-root', where,
         '--lock-wait', lock_wait]
  if fail_at:
    cmd += ['--fail-at', fail_at]
  report, code, _ = launch(cmd + [roster], where, board)
  return code, report


def prepare(code, where, board):
  """Each run dir's report pair under `where` made consistent before the artifact exposes it (the core's
  prepare_pair: the Markdown regenerated from the JSON, else an explicit unavailable notice, never a stale view), and
  the shared run rules' verdict of its JSON (run_report.shared_run), kept beside the native one."""
  try:
    core = run_report.load_core(REPORT_CORE)
    schema = run_report.schema(core)
    readings = [core.prepare_pair(d, schema) for d in sorted(where.glob('run-*')) if d.is_dir()]
    reading = readings[-1] if readings else core.Reading('missing', None, None, f'no run directory under {where}')
    shared = run_report.shared_run(core, code, reading, [board])['rows'][0]
    return {'sharedVerdict': shared['verdict'], 'sharedDetail': shared['detail']}
  except Exception as e:   # the battery's exit, markers and any holder stand: only this board's shared view is lost
    why = f'{UNPREPARED}: {type(e).__name__}: {e}'
    unsafe = withhold(where, why)
    return {'sharedVerdict': 'blocker', 'sharedDetail': why, **({'unsafeArtifacts': unsafe} if unsafe else {})}


def withhold(where, why):
  """Each run dir's Markdown under `where` replaced by an unavailable notice, the view the run left kept below it only
  as labelled text, or removed when that cannot be written. Returns the views that could be neither, which the
  workflow's upload excludes (summary.json `unsafeArtifacts`): an unchecked view never reaches the artifact."""
  unsafe = []
  for d in where.glob('run-*'):
    md = d / 'hil_report.md'
    try:
      old = md.read_text(encoding='utf-8', errors='replace') if md.is_file() else ''
      text = f'{NOTICE}: hil_report.json was not checked ({why}).** No verdict is read from this view.\n'
      if old.strip():
        text += '\n_Legacy text: the view the run left, never checked against its JSON._\n\n' + old
      tmp = d / '.hil_report.md.withheld'
      tmp.write_text(text, encoding='utf-8')
      os.replace(tmp, md)
    except OSError:
      try:
        md.unlink(missing_ok=True)
      except OSError:
        unsafe.append(str(md))
  return unsafe


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
  row = {'board': board, 'verdict': v, 'detail': detail, 'run': str(out / board)}
  if (report or {}).get('reportError'):   # its run dir's report is missing or incomplete; stdout.txt keeps the JSON
    row['reportError'] = report['reportError']
  row.update(prepare(code, out / board, board))
  return row


def summary(rows, roster):
  """The rows as a table: the native verdict, which decides the exit, and the shared run rules' verdict where it
  differs or the report could not be prepared."""
  def cell(text):
    return ' '.join(text.replace('|', '/').splitlines())

  def shared(r):
    if 'sharedVerdict' not in r or (r['sharedVerdict'] == r['verdict'] and not r['sharedDetail'].startswith(UNPREPARED)):
      return ''
    kept = f' (not uploaded: {", ".join(r["unsafeArtifacts"])})' if r.get('unsafeArtifacts') else ''
    return cell(f'{r["sharedVerdict"]}: {r["sharedDetail"]}{kept}')
  lines = [f'HIL on `{roster}`', '', '| board | native verdict | detail | shared run rules |', '|---|---|---|---|']
  lines += [f'| {r["board"]} | {r["verdict"]} | {cell(r["detail"])} | {shared(r)} |' for r in rows]
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
