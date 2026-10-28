#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The CI job's HIL run on this host's roster: one battery per named board from a record built off the rig and admitted
here from `--hosted` (hil_hosted.py; the rig builds nothing), every run kept, a `hil` verdict per board and one exit for
the job.

  hil_ci.py --board B [B ...] --roster test/hil/ci.json --out DIR --hosted DIR [--collection FILE] [--lock-wait S]
            [--fail-at STEP]

`--out` is this run's directory under a state directory kept across runs (`<state>/<run id>`): the build
record, each board's run directory (`hil_test.py run --run-root`: its report, hil.log and output) and the
`<board>.started` / `<board>.done` markers go there; the battery touches `.started` once it holds the board
(`run --started-marker`) and `.done` before it releases it (`run --done-marker`), so whoever takes the lock meanwhile
never sees a waiting battery started, and whoever takes it next sees it finished. A `.started` without its `.done` in
any earlier run is a run that ended without a report or kept a cleanup holder (SKILL.md Recovery): that board is a
blocker here until recovery removes the marker. Runs older than PRUNE_DAYS with every marker done are removed;
one with a marker left is kept, whatever its age. Each battery's report pair is prepared for the upload (prepare()), and
summary.json carries the shared run rules' `sharedVerdict` beside each native `verdict`, which alone decides the exit,
each battery's `steps`, `cleanupPass` (null when the board was untouched) and whether it is the Espressif one
(`espressif`), the seconds its record's admission (`buildS`, a name kept from when the rig built it) and battery
(`runS`) took, and the board loop's `elapsedS`.
`upload-views`, written last, is the upload's decision on the report views (UPLOAD_VIEWS).
`--collection` is the workflow's collection.json (hil_hosted_pick.py): only a board it maps to '' is admitted.

Exit 0: every board passed. 1: a board failed or was not run (held past `--lock-wait`, its hosted build not
collected, missing or its admission refused). 2: a blocker (a run without a report, a failed cleanup, a cleanup holder, a dead battery's
record or a takeover journal, or a stale probe session on the board).
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

ROOT = Path(__file__).resolve().parents[4]
CHECK_BUILD = ROOT / '.claude' / 'skills' / 'build' / 'scripts' / 'check_build.py'
HIL_TEST = Path(__file__).resolve().with_name('hil_test.py')
# the pinned report core, loaded only once check_pin() passed
REPORT_CORE = ROOT / 'lib' / 'agentrc' / 'skills' / 'hil' / 'scripts' / 'hil_report_core.py'
REPORT_NOTICE = REPORT_CORE.with_name('hil_report_notice.py')   # the unavailable notice, loadable when the core is not
UNPREPARED = 'report not prepared'
# `upload` when no view is unsafe; anything else, or no file, and the workflow uploads no hil_report.md at all
UPLOAD_VIEWS = 'upload-views'
STEPS = ('install', 'dfu', 'copy', 'app-ran', 'reenter', 'recopy', 'cleanup')   # hil_test.py --fail-at
LOCK_WAIT = 600
COLLECTION_VERSION = 1   # hil_hosted_pick.py's
PRUNE_DAYS = 30


def roster_entries(roster):
  try:
    return {b['name']: b for b in json.loads((ROOT / roster).read_text())['boards']}
  except (OSError, ValueError, KeyError, TypeError) as e:
    raise SystemExit(f'cannot read boards from {roster}: {e}')


def espressif(board):
  """Whether `board` is in the espressif port (ports/<port>/boards/<board>, check_build's port rule): its battery is
  the Espressif one, with `recopy`, and its build ESP-IDF's."""
  return (ROOT / 'ports' / 'espressif' / 'boards' / board).is_dir()


def backend(board):
  """The backend the HIL builds `board` with: ESP-IDF for an Espressif board, else cmake (check_build's backend_of)."""
  return 'idf' if espressif(board) else 'cmake'


def roster_boards(roster):
  return sorted(roster_entries(roster))


def split(roster, boards, build_pending=False):
  """The workflow's plan for `boards`: (rig, hosted, pending). The rig runs the commissioned ones (`tinyuf2.reentry`
  set, SKILL.md Hosts/rosters), each from a hosted runner's build, and with `build_pending` (a dispatch) that runner
  also builds those pending commissioning, whose artifact commissioning admits by hand; the rest are pending."""
  entries = roster_entries(roster)
  rig = [b for b in boards if ((entries[b].get('tinyuf2') or {}).get('reentry'))]
  pending = [b for b in boards if b not in rig]
  return rig, list(boards if build_pending else rig), pending


def unfinished(state, board):
  """The runs under `state` (`<state>/<run id>/<board>.started`) whose battery on `board` started and has no `.done`,
  its liveness never guessed; a linked run dir is skipped. OSError when `state` or a run in it cannot be listed."""
  found = []
  with os.scandir(state) as runs:
    for run in runs:
      if not run.is_dir(follow_symlinks=False):
        continue
      try:
        names = set(os.listdir(run.path))
      except FileNotFoundError:   # pruned meanwhile: prune() removes only runs whose every battery finished
        continue
      if f'{board}.started' in names and f'{board}.done' not in names:
        found.append(run.name)
  return sorted(found)


def prune(state, keep, days=PRUNE_DAYS):
  """Remove the runs under `state` older than `days` whose every started board finished; never `keep`."""
  cutoff = time.time() - days * 86400
  for d in state.iterdir():
    if d.is_dir() and d != keep and d.stat().st_mtime < cutoff and \
       all(p.with_suffix('.done').exists() for p in d.glob('*.started')):
      shutil.rmtree(d, ignore_errors=True)


def hosted_record(board, roster, out, hosted):
  """The board's record, admitted from its hosted build under `hosted` (hil_hosted.py admit): (record, ok, why)."""
  import hil_hosted   # here only: it loads the runner, which hil_remote.py's clients never import
  record = out / f'{board}.build.json'
  if not (hosted / board).is_dir():
    return record, False, f'no hosted build of {board} under {hosted}: its build failed or never reached the rig'
  try:
    return hil_hosted.admit(hosted / board, board, roster, out), True, ''
  except (hil_hosted.ht.Refused, hil_hosted.cb.Fail, OSError) as e:
    return record, False, f'hosted build refused: {e}'[:400]


def collection_reasons(path, boards):
  """Per board, why the workflow's collection.json did not hand it a build: '' only for an entry that is ''."""
  try:
    d = json.loads(Path(path).read_text())
    if not isinstance(d, dict) or d.get('version') != COLLECTION_VERSION or not isinstance(d.get('boards'), dict) or \
       not all(isinstance(r, str) for r in d['boards'].values()):
      raise ValueError(f'{path} is no version {COLLECTION_VERSION} hosted collection')
  except (OSError, ValueError) as e:
    return {b: f'hosted collection unavailable: {e}'[:400] for b in boards}
  got = d['boards']
  return {b: f'the hosted collection has no entry for {b}' if b not in got else
          got[b] and f'hosted build not collected: {got[b]}'[:400] for b in boards}


def launch(cmd, where, board):
  """One `hil_test.py run` of `board` (`cmd`, its argv), its output streamed to `where/stdout.txt` as it comes, so a
  killed run keeps what it printed, and its stderr to `where/stderr.txt`; its last JSON line is the report (SKILL.md
  Results). A runner that became the in-process cleanup holder (`cleanup.holder.inProcess`, Recovery) printed its
  report, closed its stdio and never exits: it is left running, not waited for. Returns (report or None, exit or None,
  held), `held` true for that live holder, whose exit is None."""
  report = None
  with open(where / 'stderr.txt', 'w') as err, open(where / 'stdout.txt', 'w') as log:
    p = subprocess.Popen([str(c) for c in cmd], cwd=ROOT, stdout=subprocess.PIPE, stderr=err, text=True)
    for line in p.stdout:
      log.write(line)
      log.flush()
      if line.startswith('{'):
        try:
          report = json.loads(line)
        except ValueError:
          pass
    p.stdout.close()
  row = run_report.row_of(report, board) or {}
  if ((row.get('cleanup') or {}).get('holder') or {}).get('inProcess') and p.poll() is None:
    return report, None, True
  return report, p.wait(), False


def battery(board, roster, record, where, lock_wait, fail_at=None, ci_state_root=None, done=None, started=None):
  """One `hil_test.py run` with its run directory under `where`, `ci_state_root` a remote driver's (its
  --ci-state-root), `done` and `started` CI's markers (its --done-marker, --started-marker). Returns launch()'s (report
  or None, exit or None, held)."""
  where.mkdir(parents=True)
  cmd = [sys.executable, HIL_TEST, 'run', '-b', board, '--build-record', record, '--run-root', where,
         '--lock-wait', lock_wait]
  if ci_state_root is not None:
    cmd += ['--ci-state-root', ci_state_root]
  if done is not None:
    cmd += ['--done-marker', done]
  if started is not None:
    cmd += ['--started-marker', started]
  if fail_at:
    cmd += ['--fail-at', fail_at]
  return launch(cmd + [roster], where, board)


def check_pin():
  """check_build's lib/agentrc pin check, raising its Fail: a battery that ran never proved the pin (its own check
  may have refused it)."""
  run_report.load(CHECK_BUILD, 'tinyuf2_check_build').check_agentrc_pin()


def run_dirs(where):
  """The `run-*` entries under `where`, sorted; OSError when it cannot be listed, which pathlib's glob would hide."""
  with os.scandir(where) as entries:
    return sorted(Path(e.path) for e in entries if e.name.startswith('run-'))


def prepare(code, where, board):
  """Each run dir's report pair under `where` made consistent before the artifact exposes it (the core's
  prepare_pair: the Markdown regenerated from the JSON, else an explicit unavailable notice, never a stale view), and
  the shared run rules' verdict of its JSON (run_report.shared_run), kept beside the native one."""
  pinned = False
  try:
    check_pin()   # before any provider code runs
    pinned = True
    core = run_report.load_agentrc(REPORT_CORE)
    schema = run_report.schema(core)
    readings = [core.prepare_pair(d, schema) for d in run_dirs(where) if d.is_dir()]
    reading = readings[-1] if readings else core.Reading('missing', None, None, f'no run directory under {where}')
    shared = run_report.shared_run(core, code, reading, [board])['rows'][0]
    return {'sharedVerdict': shared['verdict'], 'sharedDetail': shared['detail']}
  except Exception as e:   # the battery's exit, markers and any holder stand: only this board's shared view is lost
    why = f'{UNPREPARED}: {type(e).__name__}: {e}'
    unsafe = withhold(where, why, pinned)
    return {'sharedVerdict': 'blocker', 'sharedDetail': why, **({'unsafeArtifacts': unsafe} if unsafe else {})}


def withhold(where, why, pinned):
  """Each run dir's Markdown under `where` made agentrc's unavailable notice (hil_report_notice.write_unavailable, under
  the core's writer lock, the view the run left kept below it only as labelled legacy text) once lib/agentrc was
  proven at its pin (`pinned`): no provider code runs before. Returns the views left as they were, which no upload or
  copy-back may expose (summary.json `unsafeArtifacts`): every view when the notice cannot be written (no proven pin,
  the writer fails to load, another writer holds the view, an unwritable dir), `where` itself when it cannot be
  listed."""
  try:
    runs = run_dirs(where)
  except OSError:
    return [str(where)]
  views = [str(d / f'{run_report.STEM}.md') for d in runs]
  try:
    if not pinned:
      return views
    notice = run_report.load_agentrc(REPORT_NOTICE, 'tinyuf2_hil_report_notice')
  except Exception:
    return views
  unsafe = []
  for d, md in zip(runs, views):
    try:
      notice.write_unavailable(d, run_report.STEM, f'{run_report.STEM}.json was not checked ({why}); no verdict is '
                                                   'read from this view')
    except Exception:   # WriterHeld or OSError: the view stays as it is, never exposed
      unsafe.append(md)
  return unsafe


def run_board(board, roster, out, state, lock_wait, hosted, fail_at=None, markers=True, collection=None):
  """One board's row: CI's markers under `state`, the record admitted from `hosted` (the directory of hosted builds,
  one <board> each) once `collection` (collection_reasons(); None outside the workflow) has no reason against it, the
  battery, its verdict and its prepared report pair. `markers` false is a remote driver's:
  `state` is CI's state directory, read, never written, and checked again by the runner under its lock
  (--ci-state-root). `lock_wait` is seconds, or a function giving them as the battery starts. Its `buildS` and `runS`
  are the seconds the admission and the battery took, lock wait included."""
  try:
    earlier = unfinished(state, board)
  except OSError as e:
    return {'board': board, 'phase': 'preflight', 'verdict': 'blocker',
            'detail': f'state directory {state} cannot be read: {e}'}
  if earlier:
    return {'board': board, 'phase': 'preflight', 'verdict': 'blocker', 'unfinishedAttempts': earlier,
            'detail': f'run {", ".join(earlier)} under {state} started a battery on {board} and never finished: '
                      'recover the board, then remove its marker'}
  if collection is not None and collection[board]:
    return {'board': board, 'phase': 'build', 'verdict': 'not-run', 'detail': collection[board], 'buildS': 0}
  t0 = time.monotonic()
  record, ok, why = hosted_record(board, roster, out, hosted)
  build_s = round(time.monotonic() - t0)
  if not ok:
    return {'board': board, 'phase': 'build', 'verdict': 'not-run', 'detail': why, 'buildS': build_s}
  done, started = (out / f'{board}.done', out / f'{board}.started') if markers else (None, None)
  wait = lock_wait() if callable(lock_wait) else lock_wait
  t0 = time.monotonic()
  report, code, held = battery(board, roster, record, out / board, wait, fail_at, None if markers else state, done,
                               started)
  run_s = round(time.monotonic() - t0)
  v, detail = run_report.verdict(code, report, board)
  if done is not None and v == 'blocker':   # the battery's own touch stands only where this verdict agrees
    done.unlink(missing_ok=True)
  elif done is not None and started.exists():   # a battery that never held the board leaves no marker
    done.touch()
  row = {'board': board, 'phase': 'battery', 'verdict': v, 'detail': detail, 'run': str(out / board), 'exit': code,
         'heldInProcess': held, 'report': report is not None, 'buildS': build_s, 'runS': run_s}
  native = run_report.row_of(report, board)
  if native is not None:
    row['steps'] = {s['step']: bool(s.get('pass')) for s in native.get('steps') or [] if s.get('step')}
    cleanup = native.get('cleanup') or {}
    # an untouched board passes its cleanup with nothing done: no blinky was copied
    row['cleanupPass'] = None if cleanup.get('state') == 'untouched' else cleanup.get('pass')
    row['espressif'] = espressif(board)
  holder = ((native or {}).get('cleanup') or {}).get('holder')
  if holder:
    row['holder'] = holder
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
  ap.add_argument('--hosted', type=Path, required=True,
                  help="the hosted builds' directory (hil_hosted.py build), one <board> each")
  ap.add_argument('--collection', type=Path, help="the workflow's collection.json (hil_hosted_pick.py)")
  args = ap.parse_args(argv)
  boards = sorted(set(args.board))
  unknown = sorted(set(boards) - set(roster_boards(args.roster)))
  if unknown:
    ap.error(f'not in {args.roster}: {unknown}')
  args.out.mkdir(parents=True, exist_ok=True)
  (args.out / UPLOAD_VIEWS).unlink(missing_ok=True)
  state = args.out.parent
  prune(state, keep=args.out)
  collection = collection_reasons(args.collection, boards) if args.collection else None
  t0 = time.monotonic()
  rows = [run_board(b, args.roster, args.out, state, args.lock_wait, args.hosted, args.fail_at,
                    collection=collection) for b in boards]
  elapsed = round(time.monotonic() - t0)
  text = summary(rows, args.roster)
  sys.stdout.write(text)
  if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
      f.write(text)
  (args.out / 'summary.json').write_text(json.dumps({'boards': rows, 'elapsedS': elapsed}, indent=1))
  decide_views(args.out, rows)
  return run_report.fold_exit(r['verdict'] for r in rows)


def decide_views(out, rows):
  """The upload's decision, written last and atomically: any unsafe view withholds every one; the JSON and logs go
  regardless."""
  tmp = out / f'.{UPLOAD_VIEWS}.tmp'
  tmp.write_text('withhold\n' if any(r.get('unsafeArtifacts') for r in rows) else 'upload\n')
  os.replace(tmp, out / UPLOAD_VIEWS)


if __name__ == '__main__':
  sys.exit(main())
