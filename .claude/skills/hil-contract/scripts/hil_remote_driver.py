#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The rig side of hil_remote.py (SKILL.md Execution, Remote): launched detached in its attempt directory by
agentrc's remote core, it rebuilds the committed checkout from the staged git bundles, verifies it against the
manifest, then per board builds the HIL record and runs one battery as hil_ci.py does (its report pair prepared
before the copy-back), and writes result.json, the attempt's outcome.

  python3 driver/hil_remote_driver.py manifest.json        (cwd: the attempt directory)

Stdlib only until the checkout is rebuilt; from then on the checkout's own hil_ci.py (run_board(markers=False): CI's
markers read, never written, the build record, the battery, the verdict and the report pair). The driver takes no
board lock: each `hil_test.py run` locks its board itself, protected, and checks CI's state directory
(`--ci-state-root`) once it holds the lock.

Exit 0 every board passed, 1 a board failed or was not run, 2 a blocker, 3 refused before any build.
"""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

SCHEMA, VERSION = 'tinyuf2-hil-remote', 1
RESULT = 'result.json'          # written once, when the driver ends
PROGRESS = 'progress.json'      # the rows so far, after each board: what a driver that died had reached
CHECKOUT = 'src'
OUT = 'out'
REFUSED = 3
SCRIPTS = '.claude/skills/hil-contract/scripts'
REPO_PATH = re.compile(r'[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*')
SHA = re.compile(r'[0-9a-f]{40}')
FIELDS = ('runId', 'head', 'hostname', 'repos', 'submodules', 'roster', 'driver', 'boards', 'lockWait', 'failAt',
          'ciStateRoot')


class Refused(Exception):
  """Nothing was built and no board was touched."""


def git(where, *argv):
  r = subprocess.run(['git', '-C', str(where), *argv], capture_output=True, text=True)
  if r.returncode:
    raise Refused(f'git -C {where} {" ".join(argv)}: {r.stderr.strip()}')
  return r.stdout.strip()


def sha256(path):
  try:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
  except OSError:
    return None


def write_json(path, data):
  tmp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
  with open(tmp, 'w') as f:
    f.write(json.dumps(data, indent=1) + '\n')
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp, path)


def load_manifest(path):
  try:
    m = json.loads(Path(path).read_text())
  except (OSError, ValueError) as e:
    raise Refused(f'manifest {path} unreadable: {e}')
  if not isinstance(m, dict) or (m.get('schema'), m.get('version')) != (SCHEMA, VERSION):
    raise Refused(f'manifest {path} is not {SCHEMA} version {VERSION}')
  missing = [k for k in FIELDS if k not in m]
  if missing:
    raise Refused(f'manifest {path} lacks {missing}')
  try:
    for r in m['repos']:
      if not (r['path'] == '.' or REPO_PATH.fullmatch(r['path']) and '..' not in r['path'].split('/')) \
         or not SHA.fullmatch(r['commit']) or not all(SHA.fullmatch(s) for s in r['shallow']):
        raise Refused(f'manifest repo entry {r} is malformed')
  except (KeyError, TypeError) as e:
    raise Refused(f'manifest {path}: a repo entry lacks {e}')
  return m


def check_packages(attempt, m):
  """The staged bundles hash as the manifest froze them (the transfer was verified too; this is the driver's own
  check, before any of them is read)."""
  bad = [r['bundle'] for r in m['repos'] if sha256(attempt / r['bundle']) != r['sha256']]
  if bad:
    raise Refused(f'staged packages missing or changed since the manifest froze them: {", ".join(bad)}')


def rebuild(attempt, m):
  """Detached checkouts of every repository from its bundle, the superproject first: no remote, no worktree pointer
  file, no link to the dev PC. A shallow repository gets its shallow boundary before the fetch, which then checks
  the bundle's objects are complete above it."""
  src = attempt / CHECKOUT
  if src.exists():
    raise Refused(f'{src} exists: an attempt rebuilds its checkout once')
  for r in sorted(m['repos'], key=lambda r: (r['path'] != '.', r['path'].count('/'), r['path'])):
    where = src if r['path'] == '.' else src / r['path']
    if where.exists() and any(where.iterdir()):
      raise Refused(f'{where} is not empty before its checkout')
    where.mkdir(parents=True, exist_ok=True)
    git(where, 'init', '-q', '--template=')
    if r['shallow']:
      Path(git(where, 'rev-parse', '--absolute-git-dir'), 'shallow').write_text(''.join(f'{s}\n' for s in r['shallow']))
    git(where, 'fetch', '-q', '--no-tags', str(attempt / r['bundle']), 'HEAD')
    got = git(where, 'rev-parse', 'FETCH_HEAD')
    if got != r['commit']:
      raise Refused(f'{r["bundle"]} holds {got} for {r["path"]}, not {r["commit"]}')
    git(where, '-c', 'advice.detachedHead=false', 'checkout', '-q', '--detach', r['commit'])
  return src


def verify(src, m, driver):
  """Why the rebuilt checkout is not the manifest's committed identity on a clean tree; empty when it is."""
  why = []
  for r in m['repos']:
    where = src if r['path'] == '.' else src / r['path']
    if os.path.realpath(git(where, 'rev-parse', '--show-toplevel')) != os.path.realpath(where):
      why.append(f'{r["path"]} is not a checkout of its own')
      continue
    if git(where, 'rev-parse', 'HEAD') != r['commit']:
      why.append(f'{r["path"]} is not at {r["commit"]}')
    status = git(where, 'status', '--porcelain', *(() if r['path'] == '.' else ('--untracked-files=all',)))
    if status:
      why.append(f'{r["path"]} is not clean: {status.splitlines()[:5]}')
  for path, commit in m['submodules'].items():
    if git(src, 'rev-parse', f'HEAD:{path}') != commit:
      why.append(f'HEAD does not pin {path} at {commit}')
  if sha256(src / m['roster']['path']) != m['roster']['sha256']:
    why.append(f'{m["roster"]["path"]} is not the roster the manifest names')
  if sha256(src / m['driver']['path']) != sha256(driver) or sha256(driver) != m['driver']['sha256']:
    why.append('the running driver is not the checkout\'s committed one')
  return why


def state_root(m):
  root = Path(os.path.expanduser(m['ciStateRoot']))
  try:
    os.listdir(root)
  except OSError as e:
    raise Refused(f'CI state root {root} cannot be read: {e}')
  return root


def inventory(attempt, board):
  """The attempt-relative regular files a board left under out/, links never followed: what the copy-back must
  bring home."""
  out = attempt / OUT
  found = [f'{OUT}/{board}.build.json'] if (out / f'{board}.build.json').is_file() else []
  for d, dirs, files in os.walk(out / board):
    dirs[:] = [x for x in dirs if not os.path.islink(os.path.join(d, x))]
    found += [Path(d, f).relative_to(attempt).as_posix() for f in files if os.path.isfile(os.path.join(d, f))
              and not os.path.islink(os.path.join(d, f))]
  return sorted(found)


def run_board(hil_ci, board, m, attempt, ci_root, budget):
  def lock_wait():   # one budget for every battery, counted from the first one's start, after its build
    deadline = budget.setdefault('deadline', time.monotonic() + m['lockWait'])
    return max(0, round(deadline - time.monotonic()))
  row = hil_ci.run_board(board, m['roster']['path'], attempt / OUT, ci_root, lock_wait, m['failAt'], markers=False)
  if row.get('unsafeArtifacts'):   # attempt-relative, for the copy-back to withhold
    row['unsafeArtifacts'] = [Path(p).relative_to(attempt).as_posix() for p in row['unsafeArtifacts']]
  return row


def drive(attempt, m, driver, result):
  stripped = sorted(k for k in os.environ if k.startswith(('HIL_', 'GIT_')))
  for k in stripped:   # no lock bypass or override reaches the runner, and no GIT_DIR aims a rebuild elsewhere
    del os.environ[k]
  result['strippedEnv'] = stripped
  if socket.gethostname() != m['hostname']:
    raise Refused(f'this rig is {socket.gethostname()}, not {m["hostname"]}, the host {m["roster"]["path"]} is for')
  check_packages(attempt, m)
  src = rebuild(attempt, m)
  why = verify(src, m, driver)
  if why:
    raise Refused(f'the rebuilt checkout is not the committed identity: {"; ".join(why)}')
  result['checkout'] = str(src)
  ci_root = state_root(m)
  sys.dont_write_bytecode = True   # nothing imported from the checkout may write into it
  sys.path.insert(0, str(src / SCRIPTS))
  import hil_ci   # noqa: E402   the checkout's own: its ROOT is the rebuilt checkout
  budget = {}
  for board in m['boards']:
    try:
      row = run_board(hil_ci, board, m, attempt, ci_root, budget)
    except Exception as e:   # a battery may have started: never a pass, never a not-run
      row = {'board': board, 'phase': 'driver', 'verdict': 'blocker', 'detail': f'driver error: {type(e).__name__}: {e}'}
    row['artifacts'] = inventory(attempt, board)
    result['boards'].append(row)
    write_json(attempt / PROGRESS, result)
  return hil_ci.run_report.fold_exit(r['verdict'] for r in result['boards'])


def main(argv=None):
  argv = sys.argv[1:] if argv is None else argv
  attempt, driver = Path.cwd(), Path(__file__).resolve()
  result = {'schema': SCHEMA, 'version': VERSION, 'boards': [], 'startedAt': time.time()}
  code = REFUSED
  try:
    m = load_manifest(attempt / argv[0])
    result.update(runId=m['runId'], head=m['head'])
    code = drive(attempt, m, driver, result)
  except Refused as e:
    result['refused'] = str(e)
  except Exception as e:   # after the checkout: whatever ran is in boards[]; a board never reached is no pass
    result['error'] = f'{type(e).__name__}: {e}'
    code = 2
  result.update(exit=code, endedAt=time.time())
  write_json(attempt / RESULT, result)
  return code


if __name__ == '__main__':
  sys.exit(main())
