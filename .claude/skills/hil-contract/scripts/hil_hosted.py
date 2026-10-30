#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""A board's HIL record built off the rig, on a hosted runner or the dev PC, and admitted on the rig (SKILL.md Build,
Hosted).

  hil_hosted.py image
  hil_hosted.py build --board B --roster ROSTER --out DIR
  hil_hosted.py admit --artifact DIR/B --board B --roster ROSTER --out DIR

`build` runs check_build's HIL record -- an Espressif board's in CI's ESP-IDF image, any other's with cmake and
the arm-none-eabi-gcc on PATH, which must be CI's -- and packs it as DIR/B: the record (`B.build.json`), every file
its row hashes under `build/`, and `provenance.json`, which names the board and the roster's path and sha256 (the
record does not say which roster was selected). `admit` refuses (exit 2) unless provenance names this board and this
checkout's roster, the record passes the runner's own admission here (hil_test.record_row: HEAD, submodules and
get_deps dependencies, clean, the board's backend, CI's pinned IDF image) and a cmake record names CI's pinned Arm GNU
Toolchain as its compiler, and the artifact holds exactly the files that record hashes, with the same flash binding;
it then places the files as the record's build dir and writes the record and provenance to --out. The last stdout
line is JSON.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'build' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True   # as hil_test.py: nothing the runner imports writes into the checkout it binds
import check_build as cb  # noqa: E402
import hil_test as ht  # noqa: E402

PROVENANCE = 'provenance.json'
VERSION = 2
BUILD = 'build'   # the record's build dir inside an artifact
LOG_TAIL = 200    # lines of a failed build's log echoed to stderr: the hosted runner uploads nothing on a failure


def sha256(data):
  return hashlib.sha256(data).hexdigest()


def image():
  return f'espressif/idf:{cb.ci_idf_version()}'


def record_name(board):
  return f'{board}.build.json'


def build_dir(board):
  """The build dir a --shared HIL record of `board` names, checkout-relative: the only one admission places."""
  return f'cmake-build/cmake-build-{board}'


def build_root(board):
  return cb.BUILD_DIR / Path(build_dir(board)).name


def check_toolchain(what, row):
  """Refuse a cmake record whose compiler is not the Arm GNU Toolchain release CI's arm-gcc builds install, as
  record_row refuses an IDF record not built in CI's image."""
  release = cb.ci_arm_gcc_release()
  version = (row.get('compiler') or {}).get('version') or ''
  if not re.search(rf'\(Arm GNU Toolchain {re.escape(release)}\b', version, re.I):
    raise ht.Refused(f'{what}: compiled by {version or "an unrecorded compiler"}; a hosted record takes CI\'s Arm GNU '
                     f'Toolchain {release} only (.github/actions/setup_toolchain)')


def build(board, roster, out):
  """check_build's HIL record of `board` (CI's docker image, or cmake with CI's arm-gcc) packed as out/<board>."""
  ht.load_board(cb.ROOT / roster, board)
  dest = out / board
  if dest.exists():
    raise ht.Refused(f'{dest} exists')
  r = subprocess.run([sys.executable, str(Path(cb.__file__)), '--board', board, '--shared', '--hil-config', roster],
                     cwd=cb.ROOT, capture_output=True, text=True)
  try:
    rec = json.loads(r.stdout.strip().splitlines()[-1])
  except (ValueError, IndexError):
    raise ht.Refused(f'check_build printed no record (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}')
  rows = [x for x in rec.get('boards', []) if x.get('board') == board]
  if not rec.get('pass') or len(rows) != 1 or rows[0].get('removed'):
    echo_log_tails(rows)
    raise ht.Refused(f'check_build failed (exit {r.returncode}): {rec.get("firstError") or rec.get("error")}')
  row = rows[0]
  if row.get('buildDir') != build_dir(board):
    raise ht.Refused(f'the record names build dir {row.get("buildDir")}, not {build_dir(board)}')
  if row.get('backend') == 'cmake':
    check_toolchain(f'check_build\'s record of {board}', row)
  record = (json.dumps(rec) + '\n').encode()
  files = {record_name(board): record}
  for rel in row['sha256']:
    files[f'{BUILD}/{rel}'] = ht.recorded_bytes(build_root(board), rel, row)
  for rel, data in files.items():
    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
    (dest / rel).write_bytes(data)
  provenance = {'version': VERSION, 'board': board,
                'roster': {'path': str(roster), 'sha256': sha256((cb.ROOT / roster).read_bytes())}}
  (dest / PROVENANCE).write_text(json.dumps(provenance, indent=1) + '\n')
  return {'pass': True, 'artifact': str(dest), 'provenance': provenance}


def echo_log_tails(rows):
  for row in rows:
    try:
      lines = (cb.ROOT / row['log']).read_text(errors='replace').splitlines()[-LOG_TAIL:]
    except (KeyError, TypeError, OSError):
      continue
    print(f'--- {row["log"]}: last {len(lines)} lines', *lines, sep='\n', file=sys.stderr)


def inventory(artifact):
  """{posix path: bytes} of every file under `artifact` but provenance.json; anything else there refuses."""
  found = {}
  for p in sorted(Path(artifact).rglob('*')):
    rel = p.relative_to(artifact).as_posix()
    if p.is_symlink() or not (p.is_dir() or p.is_file()):
      raise ht.Refused(f'{artifact}: {rel} is not a regular file')
    if p.is_file() and rel != PROVENANCE:
      found[rel] = p.read_bytes()
  return found


def admit(artifact, board, roster, out):
  """The hosted artifact of `board` admitted as a record of this checkout: returns its record path in `out`."""
  artifact = Path(artifact)
  b = ht.load_board(cb.ROOT / roster, board)
  try:
    prov = json.loads((artifact / PROVENANCE).read_text())
  except (OSError, ValueError, RecursionError) as e:
    raise ht.Refused(f'{artifact}: no readable {PROVENANCE}: {e}')
  if not isinstance(prov, dict) or set(prov) != {'version', 'board', 'roster'} or prov['version'] != VERSION or \
     not isinstance(prov['roster'], dict):
    raise ht.Refused(f'{artifact}/{PROVENANCE}: not a version {VERSION} provenance')
  if prov['board'] != board:
    raise ht.Refused(f'{artifact}: built for {prov["board"]}, not {board}')
  here = {'path': str(roster), 'sha256': sha256((cb.ROOT / roster).read_bytes())}
  if prov['roster'] != here:
    raise ht.Refused(f'{artifact}: built against roster {prov["roster"]}, not this checkout\'s {here}')
  files = inventory(artifact)
  name = record_name(board)
  if name not in files:
    raise ht.Refused(f'{artifact}: no {name}')
  out.mkdir(parents=True, exist_ok=True)
  record, incoming = out / name, out / f'{name}.incoming'   # the bytes checked are the bytes admitted
  incoming.write_bytes(files.pop(name))
  try:
    # the runner's own admission: identity, clean, IDF image, board, backend
    _, row, root, be = ht.record_row(incoming, b)
    if row['buildDir'] != build_dir(board):   # the root replaced below is the record's: never another dir
      raise ht.Refused(f'{incoming}: build dir {row["buildDir"]}, not {build_dir(board)}')
    if be == 'cmake':
      check_toolchain(incoming, row)
    built = {rel[len(BUILD) + 1:]: data for rel, data in files.items() if rel.startswith(f'{BUILD}/')}
    # inventory paths are normalised, so a record hashing a path outside its build dir never matches
    if set(files) != {f'{BUILD}/{rel}' for rel in built} or \
       {rel: sha256(data) for rel, data in built.items()} != row.get('sha256'):
      raise ht.Refused(f'{incoming}: the artifact\'s files are not exactly the ones its record hashes')
    # bound to this roster's flasher, checked on the artifact's copy before the build dir is replaced
    ht.admit_flash(incoming, row, artifact / BUILD, b)
  except (AttributeError, KeyError, TypeError, RecursionError) as e:   # these checks assume check_build's shape
    raise ht.Refused(f'{incoming}: its checks stopped on {type(e).__name__}: {e} '
                     '(a record not of check_build\'s shape, or a checkout or tooling fault)')
  else:
    with cb.build_lock(root):
      shutil.rmtree(root, ignore_errors=True)
      for rel, data in built.items():   # the bytes hashed above
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    os.replace(incoming, record)
  finally:
    incoming.unlink(missing_ok=True)
  shutil.copyfile(artifact / PROVENANCE, out / f'{board}.{PROVENANCE}')
  return record


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
  sub = ap.add_subparsers(dest='cmd', required=True)
  sub.add_parser('image', help="CI's ESP-IDF image, which an Espressif board's `build` needs pulled")
  for name in ('build', 'admit'):
    p = sub.add_parser(name)
    p.add_argument('--board', required=True)
    p.add_argument('--roster', required=True, help='checkout-relative, as the rig names it (test/hil/ci.json)')
    p.add_argument('--out', required=True, type=Path)
    if name == 'admit':
      p.add_argument('--artifact', required=True, type=Path, help="the hosted build's <dir>/<board>")
  args = ap.parse_args(argv)
  try:
    if args.cmd == 'image':
      print(image())
      return 0
    if args.cmd == 'build':
      print(json.dumps(build(args.board, args.roster, args.out)))
      return 0
    record = admit(args.artifact, args.board, args.roster, args.out)
    print(json.dumps({'pass': True, 'record': str(record)}))
    return 0
  except (ht.Refused, cb.Fail, OSError) as e:
    print(json.dumps({'pass': False, 'error': str(e)}))
    return 2


if __name__ == '__main__':
  sys.exit(main())
