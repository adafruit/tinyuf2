# SPDX-License-Identifier: MIT
"""tinyuf2's run report as agentrc's report core (`hil` Reporting) reads and writes it: the body schema, its Markdown
view of the steps, the native `hil` verdict of a board's row (SKILL.md Results, Verdicts) and its rows normalised for
the core's shared run rules. The core module is passed in, loaded by hil_test.py or hil_ci.py through the agentrc
bootstrap (agentrc.py); verdict() needs no core. Stdlib and portable: hil_remote.py imports it on any client."""
import importlib.util

NAME, VERSION, STEM = 'tinyuf2-hil-run', 1, 'hil_report'
STEP_MARK = {True: '✅', False: '❌'}
# native fields typed when present: a legacy report never recorded exitCode; heldInProcess only an older runner's
TYPES = {'pass': bool, 'caveat': str, 'reportPath': str, 'error': str, 'exitCode': int, 'heldInProcess': bool}


def check(body):
  if not isinstance(body.get('results'), list) or not all(isinstance(r, dict) for r in body['results']):
    raise ValueError('results must be a list of objects')
  for k, t in TYPES.items():
    if k in body and type(body[k]) is not t:
      raise ValueError(f'{k} must be {t.__name__}')


def legacy(raw):
  """A report without `_hil`, from a runner before this one: its native fields are this version's, read as they are."""
  return raw


def cell(v):
  return ' '.join(str(v).splitlines()).replace('|', '\\|')


def render(core, body):
  lines = [f'HIL run: {"pass" if body.get("pass") else "fail"}']
  for k in ('error', 'caveat'):
    if body.get(k):
      lines.append(f'{k.capitalize()}: {cell(body[k])}')
  lines += [cell(text) for text in board_notes(body)]   # a manual install's or restore's, at its top level
  for r in body['results']:
    steps = [[cell(s.get('step', '?')), STEP_MARK[bool(s.get('pass'))], cell(s.get('detail', ''))]
             for s in r.get('steps') or [] if isinstance(s, dict)]
    cleanup = r.get('cleanup')
    if isinstance(cleanup, dict) and cleanup:
      steps.append(['cleanup', STEP_MARK[bool(cleanup.get('pass'))], cell(cleanup.get('state', ''))])
    lines += ['', f'### {cell(r.get("board", "?"))}', '']
    if r.get('detail'):
      lines += [cell(r['detail']), '']
    for text in board_notes(r):
      lines += [cell(text), '']
    lines.append(core.table(['Step', 'Result', 'Detail'], steps, center={1}) if steps else '_No steps ran._')
  return '\n'.join(lines) + '\n'


def schema(core):
  return core.BodySchema(name=NAME, version=VERSION, stem=STEM, evidence='firmware-validation', check=check,
                         empty=lambda b: not b['results'], render=lambda b: render(core, b), legacy=legacy)


def failure_text(f):
  """One logged cleanup failure (agentrc hil_lock's failure_report entry) on one line, as its own failure_text."""
  if not isinstance(f, dict):
    return str(f)
  if 'unavailable' in f:
    return str(f['unavailable'])
  return (f'{f.get("at")} ({f.get("how")}, {f.get("reason") or "unknown task"} pid {f.get("pid")}, id {f.get("id")}): '
          f'{f.get("detail")}' + (f'; {f["noteError"]}' if f.get('noteError') else ''))


def previous_failures(row):
  """The open cleanup failures a run found on its board as it took it (SKILL.md Results), '' when none."""
  f = row.get('previousCleanupFailure')
  if f is None:
    return ''
  n = row.get('openCleanupFailures')
  return f'Previous cleanup failure: {failure_text(f)}' + (f' ({n - 1} earlier still open)' if n else '')


def lock_of(row):
  """The row's board lock end (`lock`, run_board's), {} when it recorded none."""
  return row['lock'] if isinstance(row.get('lock'), dict) else {}


def diagnostics(row):
  """What a run could not record, and an older runner's pending mark it met, beside its verdict, which they never
  change (SKILL.md Results), as `key: text`: `legacyPending`, each non-empty `*Note` and a manual body's `logError`;
  the lock's end (`describe`) when it did not end cleanly, logged a failure, was bypassed or met errors, or an older
  runner's cleanup holder still holding the board; and each of its `restoreNotes`."""
  lock = lock_of(row)
  notes = [f'{k}: {v}' for k, v in row.items() if v and (k.endswith('Note') or k in ('legacyPending', 'logError'))]
  cleanup = row.get('cleanup') if isinstance(row.get('cleanup'), dict) else {}
  if cleanup.get('heldAfter') or cleanup.get('holder'):   # SKILL.md Recovery, Legacy
    notes.append(f'lock: board held by an older runner\'s cleanup holder {cleanup.get("holder") or ""}'.rstrip())
  if lock.get('endedCleanly') is False or lock.get('failureLogged') is not None or lock.get('bypassed') or \
     lock.get('errors'):
    notes.append(f'lock: {lock.get("describe")}')
  return notes + [f'restoredNote: {n}' for n in lock.get('restoreNotes') or []]


def board_notes(row):
  """The lines a row (or a manual body, or hil_ci's summary row with its native row's `notes`) carries beside its
  verdict: the open cleanup failures its run found on taking the board, and its notes (diagnostics)."""
  notes = row['notes'] if isinstance(row.get('notes'), list) else diagnostics(row)
  return [text for text in (previous_failures(row), notes_text(notes)) if text]


def notes_text(notes):
  return f'Notes: {"; ".join(notes)}' if notes else ''


def board_state(row):
  """What a run left of the board's lock: its task's own line (`lock.describe`); an older runner's report records only
  its cleanup holder (`heldAfter`/`holder`), never assumed released when unrecorded."""
  if describe := lock_of(row).get('describe'):
    return describe
  cleanup = row.get('cleanup') if isinstance(row.get('cleanup'), dict) else {}
  return 'board held' if cleanup.get('heldAfter') or cleanup.get('holder') else 'board lock end not recorded'


def exit_of(body):
  """verdict()'s `code` from a report alone: None for a legacy report, which never recorded its exit (an older runner's
  holder kept in process recorded at least 4)."""
  return body.get('exitCode')


def row_of(report, board):
  """`board`'s row of a runner report, None when it has none or there is no report."""
  return next((r for r in (report or {}).get('results', []) if r.get('board') == board), None)


def fold_exit(verdicts):
  """The one exit of a set of `hil` verdicts (SKILL.md Verdicts): 2 a blocker, 1 a fail or not-run, else 0."""
  verdicts = set(verdicts)
  return 2 if 'blocker' in verdicts else 1 if verdicts & {'fail', 'not-run'} else 0


def verdict(code, report, board):
  """The `hil` verdict of one run from the report's row (SKILL.md Verdicts): (verdict, detail). `code` is the runner's
  exit, None when unknown (exit_of). A process on the probe (`probeUsers`) or a session an older tinyuf2 left still
  running (`pendingSessions`) is a blocker."""
  if report is None:
    return 'blocker', f'run ended without a report (exit {code})'
  row = row_of(report, board)
  if row is None:
    return 'blocker', f'report has no row for {board} (exit {code}): {report.get("caveat") or report.get("error")}'
  cleanup = row.get('cleanup') or {}
  if code in (4, None) or row.get('ran') is None:
    return 'blocker', f'cleanup failed or no report; {board_state(row)}: {row.get("detail")} {cleanup}'[:400]
  if row.get('probeUsers') or row.get('pendingSessions') or \
     row.get('recoveryBlocker') and not row.get('locked'):
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


def load(path, name):
  """The module at `path` as `name`, loaded by path: check_build.py, for tinyuf2's scripts outside its import path."""
  spec = importlib.util.spec_from_file_location(name, path)
  if spec is None:
    raise ImportError(f'{path} not found')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


def run_rows(code, report, requested):
  """One normalised {board, verdict, detail, evidence} row per requested board, from the native verdict()."""
  evidence = [report['reportPath']] if (report or {}).get('reportPath') else []
  return [dict(zip(('verdict', 'detail'), verdict(code, report, b)), board=b, evidence=evidence) for b in requested]


def shared_run(core, code, reading, requested):
  """The core's apply_run_rules over the rows of `reading` (read_document or prepare_pair of a run's report), apart
  from the native verdict, which it can only tighten: `_hil.termination` aborted makes every board a blocker and a
  caveat denies a pass. A report that cannot be read is a blocker for every board; a legacy one never recorded its
  termination and is read as completed."""
  if reading.outcome not in core.READABLE:
    rows = [{'board': b, 'verdict': 'blocker', 'detail': f'report {reading.outcome}: {reading.detail}', 'evidence': []}
            for b in requested]
    return core.apply_run_rules(schema(core), requested, rows, 'completed', '')
  termination = reading.meta['termination'] if reading.meta else 'completed'
  return core.apply_run_rules(schema(core), requested, run_rows(code, reading.body, requested), termination,
                              reading.body.get('caveat', ''))
