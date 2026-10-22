#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run TinyUF2's HIL battery on the ci.lan rig from a dev PC, built there from this checkout's committed identity
(SKILL.md Execution, Remote).

  hil_remote.py run -b BOARD [-b BOARD ...] [--run-id ID] [--host HOST] [--lock-wait S] [--fail-at STEP]
  hil_remote.py wait RUN_ID [--timeout S]
  hil_remote.py collect RUN_ID

`run` freezes HEAD and every repository it pins -- the submodules and the get_deps dependencies of the boards' ports,
unpushed commits and a candidate lib/agentrc pin included -- as self-contained git bundles bound by a manifest
(commits, roster digest, boards, bundle digests), refusing a dirty, off-pin or missing input or one that moved while
frozen. It then creates the create-only attempt <base>/<run id> on the rig, stages and verifies the bundles there,
launches hil_remote_driver.py detached in it (the rig rebuilds and checks the checkout, builds each board's record
with check_build.py --hil-config and runs `hil_test.py run` per board, one after another), waits for the attempt's
completion record and collects it into .hil-remote/<run id>/. `wait` reconnects and does the same within --timeout;
`collect` fetches the attempt whatever its state. Neither ever launches it: an attempt runs once. Ending this process
ends nothing on the rig.

The transport is agentrc's hil_remote_core, loaded from this checkout's lib/agentrc at its pin. stdout is one JSON
line; progress goes to stderr.

Exit 0 every board passed and came home whole; 1 a board failed or was not run; 2 a blocker; 3 still running at the
timeout; 4 the attempt ended without completing, or was never launched; 5 inconclusive (the rig unreachable or its
evidence incomplete); 6 an incomplete copy-back; 7 refused (nothing launched, unless the message says it may have).
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import hil_ci  # noqa: E402   STEPS, the battery's --fail-at steps
import hil_remote_driver as driver  # noqa: E402   the rig side's names: manifest schema, result, checkout, out
import hil_run_report as run_report  # noqa: E402   the loader, the verdict fold

ROOT = HERE.parents[3]
AGENTRC = 'lib/agentrc'
CHECK_BUILD = HERE.parents[1] / 'build' / 'scripts' / 'check_build.py'
DRIVER = Path(driver.__file__).resolve().relative_to(ROOT).as_posix()
RUNS = '.hil-remote'
# the rigs a remote run may use: the roster that host's battery takes, the attempts' base dir, and CI's state root
# for the runner's transition check (hil.yml: $(dirname $GITHUB_WORKSPACE)/hil-state, the runner's account on ci.lan)
HOSTS = {'ci.lan': {'hostname': 'ci', 'roster': 'test/hil/ci.json', 'base': '~/hil-remote/tinyuf2',
                    'ciStateRoot': '~/actions-runner-tinyuf2/_work/tinyuf2/hil-state'}}
LOCK_WAIT_MAX = 3600
INCOMPLETE, REFUSED = 6, 7
MANUAL = ('install', 'restore', 'clear-pending', 'fat-read', 'keep-held', 'keep-build')
# hil_test.py's manual, recovery and commissioning options and the overrides a remote run never takes
REFUSED_FLAGS = ('--under-hold', '--recover-holder', '--recover-takeover', '--report', '--try-reentry', '--route',
                 '--build-record', '--run-root', '--ci-state-root', '--done-marker', '--started-marker',
                 '--after-reviewed-recovery')

core = None   # the provider, loaded by provider() only once check_pin() passed


def fail(why):
  """core.fail once the core is loaded (RemoteError, a SystemExit), a plain SystemExit before."""
  raise SystemExit(f'error: {why}') if core is None else core.RemoteError(why)


def git(where, *argv, binary=False):
  r = subprocess.run(['git', '-C', str(where), *argv], capture_output=True, text=not binary)
  if r.returncode:
    err = r.stderr.decode(errors='replace') if binary else r.stderr
    fail(f'git -C {where} {" ".join(argv)}: {err.strip()}')
  return r.stdout if binary else r.stdout.strip()


def load_core():
  """hil_remote_core from this checkout's lib/agentrc, never an installed agentrc; main() checks the pin first."""
  path = HERE.parents[3] / AGENTRC / 'skills' / 'hil' / 'scripts' / 'hil_remote_core.py'
  if not path.is_file():
    fail(f'{path} is missing: git submodule update --init {AGENTRC}')
  return run_report.load(path, 'tinyuf2_hil_remote_core')


def check_pin():
  """Refuse unless lib/agentrc is its own checkout, clean at the commit HEAD pins (check_build's check): never
  another provider."""
  cb = check_build()
  try:
    cb.check_agentrc_pin()
  except cb.Fail as e:
    fail(str(e))


POLL = None   # seconds between status polls, the core's own when None


def provider():
  """The remote core, loaded once: no provider code runs before main() has checked its pin."""
  global core
  if core is None:
    core = load_core()
  return core


_cb = None


def check_build():
  """The build contract's module, for the checkout identity its build records and the runner check."""
  global _cb
  if _cb is None:
    _cb = run_report.load(CHECK_BUILD, 'tinyuf2_check_build')
  return _cb


# --- inputs --------------------------------------------------------------------------------------------------------
def select(boards, roster, roster_path):
  entries = {b.get('name'): b for b in roster.get('boards', [])}
  unknown = sorted(set(boards) - set(entries))
  if unknown:
    fail(f'not in {roster_path} at HEAD: {unknown}')
  return sorted(set(boards))


def identity(boards):
  """check_build's identity of this checkout for the boards' ports, refused unless clean, every submodule at the
  commit HEAD pins and every dependency its own checkout at its get_deps pin."""
  cb = check_build()
  try:
    info = cb.identity({cb.port_of(b) for b in boards})
  except (cb.Fail, OSError) as e:
    fail(f'cannot establish the checkout identity: {e}')
  bad = [f'{k}: {info[k]}' for k in ('dirtyInputs', 'missingInputs', 'depsOffPin') if info[k]]
  if info['dirty']:
    bad.insert(0, f'changed or untracked: {git(ROOT, "status", "--porcelain").splitlines()[:5]}')
  bad += [f'{p} is at {sha[:12]}, HEAD pins {pin[:12]}' for p, sha in info['submodules'].items()
          if (pin := git(ROOT, 'rev-parse', f'HEAD:{p}')) != sha]
  if bad:
    fail(f'the inputs are not HEAD\'s committed identity ({"; ".join(bad)}): commit, or check out the pins, first')
  return info


def shallow_marks(where, commit):
  """The shallow boundaries under commit in a shallow repository: what the rig's fetch needs to accept its bundle."""
  path = Path(where) / git(where, 'rev-parse', '--git-path', 'shallow')
  if not path.is_file():
    return []
  return sorted(set(path.read_text().split()) & set(git(where, 'rev-list', commit).split()))


def freeze(stage, run_id, host, cfg, boards, args):
  """Bundle every repository into stage with the driver and a manifest binding them; refused when an input moved
  meanwhile. Returns the manifest."""
  info = identity(boards)
  (stage / 'bundles').mkdir(parents=True)
  repos = []
  for i, (path, commit) in enumerate([('.', info['head']), *sorted(info['submodules'].items()),
                                      *sorted(info['deps'].items())]):
    where, bundle = ROOT / path, f'bundles/{i}.bundle'
    git(where, 'bundle', 'create', '-q', str(stage / bundle), 'HEAD')
    if git(where, 'bundle', 'list-heads', str(stage / bundle)) != f'{commit} HEAD':
      fail(f'the bundle of {path} is not {commit} alone: it moved while it was frozen')
    repos.append({'path': path, 'commit': commit, 'bundle': bundle, 'sha256': core.digest(stage / bundle),
                  'shallow': shallow_marks(where, commit)})
  (stage / 'driver').mkdir()
  (stage / 'driver' / Path(DRIVER).name).write_bytes(git(ROOT, 'cat-file', 'blob', f'HEAD:{DRIVER}', binary=True))
  roster = git(ROOT, 'cat-file', 'blob', f'HEAD:{cfg["roster"]}', binary=True)
  manifest = {'schema': driver.SCHEMA, 'version': driver.VERSION, 'runId': run_id, 'host': host,
              'hostname': cfg['hostname'], 'head': info['head'], 'repos': repos, 'submodules': info['submodules'],
              'deps': info['deps'], 'roster': {'path': cfg['roster'], 'sha256': hashlib.sha256(roster).hexdigest()},
              'boards': boards, 'lockWait': args.lock_wait, 'failAt': args.fail_at, 'ciStateRoot': cfg['ciStateRoot'],
              'driver': {'path': DRIVER, 'sha256': core.digest(stage / 'driver' / Path(DRIVER).name)},
              'createdAt': time.time()}
  core.write_json(stage / 'manifest.json', manifest)
  if identity(boards) != info:
    fail('the checkout moved while it was frozen; nothing was sent: run again')
  return manifest


# --- the attempt ---------------------------------------------------------------------------------------------------
def members(manifest):
  """The copy-back: one group (the manifest, the driver's result and every board's records, run dirs, reports, logs
  and output under out/), and optional evidence: the driver's progress and a failed build's log, at the build dir
  check_build.py names for either backend."""
  logs = [f'{driver.CHECKOUT}/cmake-build/cmake-build-{b}{s}/check_build.log' for b in manifest['boards'] for s in ('', '-cmake')]
  return [['manifest.json', driver.RESULT, f'{driver.OUT}/']], [driver.PROGRESS, *logs]


def local_manifest(run_id):
  return core.attempt_record(ROOT / RUNS, run_id).with_name(f'{run_id}.manifest.json')


def load_manifest(run_id):
  try:
    return json.loads(local_manifest(run_id).read_text())
  except (OSError, ValueError) as e:
    fail(f'the manifest of run {run_id} is unreadable: {e}')


def emit(data, code):
  print(json.dumps(data), flush=True)
  return code


def where(tree, manifest):
  return {'host': tree.host, 'dir': tree.dir, 'checkout': f'{tree.dir}/{driver.CHECKOUT}',
          'local': f'{RUNS}/{manifest["runId"]}'}


def wait_for(tree, manifest, timeout=None):
  """Poll until the attempt completes and collect it (report()); with no timeout keep polling while it runs."""
  while True:
    groups, optional = members(manifest)
    code, st = core.wait_attempt(tree, core.WAIT_SECS if timeout is None else timeout, poll=POLL or core.POLL_SECS,
                                 dest=ROOT / RUNS / manifest['runId'], groups=groups, optional=optional,
                                 accept=acceptance(tree, manifest))
    if code == 0:
      return report(tree, manifest, st['collection'])
    if code != core.RUNNING or timeout is not None:
      outcome = {core.RUNNING: 'running', core.DEAD: st['state'], core.INCONCLUSIVE: 'inconclusive'}[code]
      return emit({'runId': manifest['runId'], 'outcome': outcome, 'pass': False, 'state': st['state'],
                   'remote': where(tree, manifest), **({'detail': st['detail']} if st.get('detail') else {})}, code)
    print(f'==> {manifest["runId"]} still running on {tree.host}', file=sys.stderr)


def canonical(rel):
  """Whether `rel` is a relative path the core's check_relative takes as it is spelt."""
  try:
    return isinstance(rel, str) and core.check_relative(rel, 'an inventory path') == rel
  except core.RemoteError:
    return False


def unsafe_views(row, board):
  """The board's report views the rig could neither prepare nor withhold (`unsafeArtifacts`), None when that list
  names anything else."""
  views = row.get('unsafeArtifacts', [])
  view = re.compile(rf'{re.escape(driver.OUT)}/{re.escape(board)}/run-[^/]+/{run_report.STEM}\.md')
  ok = isinstance(views, list) and all(canonical(v) and view.fullmatch(v) for v in views)
  return views if ok else None


def artifacts_missing(row, board, dest):
  """What the board's phase requires, and the rig's inventory of what it left, that did not come home. An inventory
  path is checked to lie under the board's own out/ entries, never followed elsewhere; an unsafe view is not
  required (withhold_unchecked() removes it)."""
  need = {'build': [f'{driver.OUT}/{board}.build.json'],
          'battery': [f'{driver.OUT}/{board}.build.json', f'{driver.OUT}/{board}/stdout.txt',
                      f'{driver.OUT}/{board}/stderr.txt']}.get(row.get('phase'), [])
  listed = row.get('artifacts')
  if not isinstance(listed, list):
    return ['(no artifact inventory)']
  own = (f'{driver.OUT}/{board}.build.json', f'{driver.OUT}/{board}/')
  bad = [rel for rel in listed if not canonical(rel) or not (rel == own[0] or rel.startswith(own[1]))]
  if bad:
    return [f'(inventory entries outside {board}\'s artifacts: {bad[:3]!r})']
  unsafe = unsafe_views(row, board)
  if unsafe is None:
    return [f'(unsafeArtifacts outside {board}\'s report views: {row.get("unsafeArtifacts")!r:.200})']
  lost = [p for p in dict.fromkeys([*need, *listed])
          if p not in unsafe and (not (dest / p).is_file() or (dest / p).is_symlink())]
  report_json = re.compile(rf'{re.escape(own[1])}run-[^/]+/hil_report\.json')
  if row.get('phase') == 'battery' and not any(report_json.fullmatch(p) for p in listed):
    lost.append(f'{own[1]}run-*/hil_report.json (never published{": " + row["reportError"] if row.get("reportError") else ""})')
  return lost


def read_result(dest, run_id):
  """The driver's result.json in dest, None when missing, unreadable or another run's."""
  try:
    result = json.loads((dest / driver.RESULT).read_text())
  except (OSError, ValueError):
    return None
  return result if isinstance(result, dict) and result.get('runId') == run_id else None


def acceptance(tree, manifest):
  """The core's completeness predicate over a collected tree, run under its collector lock before it publishes a
  fetch and on a cached collection: the tree's unchecked views removed first (withhold_unchecked()), then each board's
  required artifacts the copy-back lacks, so a collection short of them is never final and a later collect fetches
  it again."""
  def missing(path):
    path = Path(path)
    result = read_result(path, manifest['runId'])
    boards = [] if result is None or result.get('refused') else board_rows(tree, manifest, path, result)
    withhold_unchecked(path, boards)
    if result is None:   # never a final collection: a later collect fetches it again
      return [f'{driver.RESULT} missing, unreadable or not run {manifest["runId"]}\'s']
    return [f'{r["board"]}: {m}' for r in boards for m in r.get('missing', [])]
  return missing


def withhold_unchecked(path, boards):
  """Each report view under a collected tree's out/ that the rig did not check removed before the tree is published,
  never here as evidence: a board's `unsafeArtifacts`, and every view of a board whose row has no prepared report pair
  (no `sharedVerdict`: no row, or no result at all) or an unreadable `unsafeArtifacts`, as CI's upload excludes every
  view when hil_ci.py did not finish. A removal that fails refuses the publication, the cached collection kept as it
  was."""
  checked = {r['board'] for r in boards if 'sharedVerdict' in r and unsafe_views(r, r['board']) is not None}
  out = path / driver.OUT
  views = {p.relative_to(path).as_posix(): p.relative_to(out).parts[0]
           for p in out.glob(f'*/run-*/{run_report.STEM}.md')}
  drop = {*(rel for r in boards for rel in unsafe_views(r, r['board']) or []),
          *(rel for rel, board in views.items() if board not in checked)}
  for rel in sorted(drop):
    try:
      (path / rel).unlink(missing_ok=True)
    except OSError as e:
      fail(f'cannot remove {rel}, a report view the rig could not check, from {path}: {e}')


def board_rows(tree, manifest, dest, result):
  """Each requested board's row of the result, with its copy-back state and paths."""
  rows = {r.get('board'): r for r in result.get('boards', []) if isinstance(r, dict)}
  boards = []
  for b in manifest['boards']:
    row = rows.get(b)
    if row is None:   # the driver ended before this board: an error after the checkout may have left a battery
      boards.append({'board': b, 'verdict': 'blocker' if result.get('error') else 'incomplete',
                     'detail': result.get('error') or 'no row in the result'})
      continue
    got = {k: row.get(k) for k in ('board', 'phase', 'verdict', 'detail', 'exit', 'heldInProcess', 'holder',
                                   'reportError', 'unfinishedAttempts', 'sharedVerdict', 'sharedDetail',
                                   'unsafeArtifacts') if row.get(k) is not None}
    lost = artifacts_missing(row, b, dest)
    if lost:
      got.update(copyBack='incomplete', missing=lost)
    boards.append(dict(got, paths=board_paths(tree, b, dest)))
  return boards


def board_paths(tree, board, dest):
  """Each of a board's evidence paths on the rig, as recovery names them, beside its local copy."""
  def pair(rel):
    return {'remote': f'{tree.dir}/{rel}', 'local': f'{dest.relative_to(ROOT).as_posix()}/{rel}'}
  paths = {'buildRecord': pair(f'{driver.OUT}/{board}.build.json'), 'runRoot': pair(f'{driver.OUT}/{board}')}
  reports = sorted(p.relative_to(dest).as_posix() for p in (dest / driver.OUT / board).glob('run-*/hil_report.json')
                   if not p.is_symlink())
  if reports:
    paths['reports'] = [pair(r) for r in reports]
  return paths


def report(tree, manifest, collection):
  """The attempt's outcome from its collected copy: each requested board's verdict, the paths recovery needs, and
  an incomplete copy-back named as such whatever the battery said."""
  run_id = manifest['runId']
  dest = ROOT / RUNS / run_id
  out = {'runId': run_id, 'remote': where(tree, manifest), 'collection': collection['state'],
         'remoteState': collection['remoteState']}
  result = read_result(dest, run_id)
  if collection['remoteState'] != 'done' or result is None:
    missing = collection.get('missing') or [[driver.RESULT]]
    code = {'running': core.RUNNING, 'dead': core.DEAD, 'not-launched': core.DEAD,
            'inconclusive': core.INCONCLUSIVE}.get(collection['remoteState'], INCOMPLETE)
    return finish(dest, {**out, 'outcome': 'incomplete', 'pass': False, 'missing': missing}, code)
  if result.get('refused'):
    return finish(dest, {**out, 'outcome': 'refused', 'pass': False, 'detail': result['refused']}, REFUSED)
  boards = board_rows(tree, manifest, dest, result)
  verdicts = {r['verdict'] for r in boards}
  ran = run_report.fold_exit(verdicts)
  # the driver's own failure, or an exit its rows do not explain, is never a success
  failed = bool(result.get('error')) or result.get('exit') != ran
  # a collection the predicate found short (acceptance()) keeps each board's verdict beside its missing evidence
  lost = collection['state'] != 'complete' or any(r.get('copyBack') for r in boards) or 'incomplete' in verdicts
  code = 2 if ran == 2 or failed else INCOMPLETE if lost else ran
  outcome = {0: 'pass', 1: 'fail', 2: 'blocker', INCOMPLETE: 'incomplete'}[code]
  return finish(dest, {**out, 'outcome': outcome, 'pass': code == 0, 'boards': boards,
                       **({'driverFailure': result.get('error') or f'the driver exited {result.get("exit")!r}'}
                          if failed else {})}, code)


def finish(dest, data, code):
  core.write_json(dest.with_name(f'{dest.name}.outcome.json'), data)
  return emit(data, code)


# --- commands ------------------------------------------------------------------------------------------------------
def refuse_unsupported(argv):
  if argv[:1] and argv[0] in MANUAL:
    fail(f'{argv[0]} is a manual or recovery operation: it runs on the rig, from the attempt\'s retained checkout '
         f'(SKILL.md Recovery), never through hil_remote.py')
  hit = [a for a in argv for f in REFUSED_FLAGS if a == f or a.startswith(f + '=')]
  if hit:
    fail(f'{", ".join(hit)}: a remote run takes no manual, recovery, commissioning or override option')


def lock_wait(text):
  secs = int(text)
  if not 0 <= secs <= LOCK_WAIT_MAX:
    raise argparse.ArgumentTypeError(f'0 to {LOCK_WAIT_MAX} s')
  return secs


def run(args):
  if os.name == 'nt':
    fail('the Windows client is pending (SKILL.md Limits): run from a POSIX host')
  if 'HIL_NO_BOARD_LOCK' in os.environ:
    fail('HIL_NO_BOARD_LOCK is set: a remote run is always locked and forwards no HIL_* variable; unset it')
  cfg = HOSTS.get(args.host) or fail(f'no rig {args.host}: one of {sorted(HOSTS)}')
  run_id = args.run_id or f'{time.strftime("%Y%m%d-%H%M%S")}-{secrets.token_hex(3)}'
  runs = ROOT / RUNS
  if core.attempt_record(runs, run_id).exists() or local_manifest(run_id).exists():
    fail(f'run id {run_id} was used before ({RUNS}/{run_id}.*); pick a new one')
  try:
    roster = json.loads(git(ROOT, 'cat-file', 'blob', f'HEAD:{cfg["roster"]}'))
  except ValueError as e:
    fail(f'{cfg["roster"]} at HEAD is unreadable: {e}')
  boards = select(args.board, roster, cfg['roster'])
  runs.mkdir(exist_ok=True)
  stage = runs / f'.{run_id}.stage'   # inside the checkout, where rsync can name it on every client
  try:
    stage.mkdir()
  except FileExistsError:
    fail(f'{stage} exists: another run with id {run_id} is staging')
  try:
    print(f'==> Freezing HEAD and its pinned repositories for {", ".join(boards)}', file=sys.stderr)
    manifest = freeze(stage, run_id, args.host, cfg, boards, args)
    with open(local_manifest(run_id), 'x') as f:
      f.write(json.dumps(manifest) + '\n')
    digests = core.file_digests(stage, [p for p in stage.rglob('*') if p.is_file()])
    tree = core.create_attempt(ROOT, runs, run_id, args.host, cfg['base'], (driver.OUT,))
    print(f'==> Staging attempt {tree.spec()}', file=sys.stderr)
    core.stage_tree(tree, stage)
    bad = core.verify_remote(tree, digests)
    if bad:
      fail(f'staged files differ on the rig: {", ".join(bad)}; attempt {run_id} stays unlaunched')
    try:
      core.launch(tree, ['python3', f'driver/{Path(DRIVER).name}', 'manifest.json'])
      print(f'==> Launched {run_id}: `hil_remote.py wait {run_id}` reconnects', file=sys.stderr)
    except core.RemoteError as e:   # it may have started: the wait below finds out, and nothing launches it again
      print(e.code, file=sys.stderr)
  finally:
    shutil.rmtree(stage, ignore_errors=True)
  return after_launch(tree, manifest, lambda: wait_for(tree, manifest))


def after_launch(tree, manifest, op):
  """op() on a launched attempt: a transport failure is inconclusive (it says nothing of the attempt), never a
  refusal."""
  try:
    return op()
  except core.RemoteError as e:
    print(e.code, file=sys.stderr)
    return emit({'runId': manifest['runId'], 'outcome': 'inconclusive', 'pass': False, 'remote': where(tree, manifest),
                 'detail': str(e.code)}, core.INCONCLUSIVE)


@contextlib.contextmanager
def without_git_overrides():
  """A hook's GIT_DIR, GIT_WORK_TREE or GIT_INDEX_FILE would aim every git call, check_build's included, at another
  repository: none reaches them, and the caller's are restored."""
  saved = {k: os.environ.pop(k) for k in [k for k in os.environ if k.startswith('GIT_')]}
  try:
    yield
  finally:
    os.environ.update(saved)


@without_git_overrides()
def main(argv=None):
  argv = sys.argv[1:] if argv is None else argv
  try:
    check_pin()
  except SystemExit as e:   # raised by fail() before the provider is loaded
    print(e.code, file=sys.stderr)
    return REFUSED
  provider()
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  sub = ap.add_subparsers(dest='cmd', required=True)
  r = sub.add_parser('run', help='freeze, stage, launch, wait and collect one attempt')
  r.add_argument('-b', '--board', action='append', required=True, help='a roster board (repeatable; run one after another)')
  r.add_argument('--run-id', help='the attempt id, used once (default: a time stamp)')
  r.add_argument('--host', default='ci.lan', help=f'the rig, one of {sorted(HOSTS)}')
  r.add_argument('--lock-wait', type=lock_wait, default=0,
                 help='seconds the batteries together keep trying a held board (default 0); a blocker is never waited for')
  r.add_argument('--fail-at', choices=hil_ci.STEPS, help='acceptance only (SKILL.md Execution): passed to every battery')
  w = sub.add_parser('wait', help='reconnect, wait for the attempt and collect it')
  w.add_argument('run_id')
  w.add_argument('--timeout', type=core.wait_secs, default=core.WAIT_SECS, help=f'seconds, at most {core.WAIT_SECS}')
  c = sub.add_parser('collect', help="fetch the attempt's evidence whatever its state")
  c.add_argument('run_id')
  try:
    refuse_unsupported(argv)
    args = ap.parse_args(argv)
    if args.cmd == 'run':
      return run(args)
    tree, manifest = core.load_attempt(ROOT, ROOT / RUNS, args.run_id), load_manifest(args.run_id)
    if args.cmd == 'wait':
      return after_launch(tree, manifest, lambda: wait_for(tree, manifest, args.timeout))
    groups, optional = members(manifest)
    return after_launch(tree, manifest, lambda: report(tree, manifest, core.collect(
      tree, ROOT / RUNS / args.run_id, groups, optional, accept=acceptance(tree, manifest))))
  except core.RemoteError as e:
    print(e.code, file=sys.stderr)
    return REFUSED


if __name__ == '__main__':
  sys.exit(main())
