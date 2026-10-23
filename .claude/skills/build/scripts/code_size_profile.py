#!/usr/bin/env python3
"""TinyUF2's profile for agentrc's code-size engine (its module docstring is the contract), run by
code_size.py beside it. A board builds the way the build contract builds it, through each tree's
own check_build.py: `--build-dir` where that tree has it, else `--shared` inside the base worktree,
which only that worktree sees. No CI snapshots: the base is always built here."""
import glob
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_build  # noqa: E402

ROOT = str(check_build.ROOT)
NAME = 'TinyUF2'
OUT_DIR = os.path.join(ROOT, 'cmake-build', 'code-size')
BASE_BRANCH = 'origin/master'
DEFAULT_ENGINE = 'sections'
CHECK_BUILD = os.path.relpath(HERE / 'check_build.py', ROOT)
BUILD_TIMEOUT = 1800  # s: an ESP-IDF board in docker takes 10+ min
engine = None  # the code-size engine; its main() sets it before any hook runs
_boards = None  # the boards check() last passed; None: every dependency counts


def filters(checkout):
  return [engine.filter_arg(os.path.realpath(os.path.join(checkout, d)) + os.sep) for d in ('src', 'ports')]


def check(command, boards, examples, sha, base_local):
  global _boards
  errors = []
  if examples:
    errors.append(f'{NAME} has no examples: -b sizes a board\'s bootloader')
  for board in boards:
    try:
      check_build.port_of(board)
    except check_build.Fail as e:
      errors.append(str(e))
  _boards = boards
  return errors


def _has_build_dir(tree):
  """Whether `tree`'s check_build.py takes --build-dir; an older one builds only --shared."""
  with open(os.path.join(tree, CHECK_BUILD)) as f:
    return '--build-dir' in f.read()


def _dep_checkout(src):
  """(git common dir, HEAD) of the dependency dir `src`; None when it is not a git checkout of its own."""
  r = subprocess.run(['git', '-C', src, 'rev-parse', '--show-toplevel', '--git-common-dir', 'HEAD'],
                     capture_output=True, text=True)
  out = r.stdout.split('\n')
  if r.returncode or len(out) < 3 or os.path.realpath(out[0]) != os.path.realpath(src):
    return None
  return os.path.join(src, out[1]), out[2]


def _dep_clean(src):
  """Whether the checkout `src` is clean, counting untracked and ignored files too: a build can test a file's
  existence (imxrt family.mk's fsl_dcdc.c)."""
  status = subprocess.run(['git', '--no-optional-locks', '-C', src, 'status', '--porcelain', '--ignored',
                           '--untracked-files=all'], capture_output=True, text=True)
  return status.returncode == 0 and not status.stdout


def _checkout_borrowing(common, dst, pin, rel, src):
  """`dst` a checkout of `pin` borrowing the objects, shallow boundary included, of the repository at `common`:
  get_deps.py and a --depth 1 submodule fetch shallow, and git ignores clone --shared from a shallow repository,
  cloning only what its refs reach, so a pin fetched by SHA is missing. Its refs are copied too: the build embeds
  the submodule's `git describe`, which a tagless copy would shorten."""
  shallow = os.path.isfile(os.path.join(common, 'shallow'))
  if os.path.islink(dst):  # a reused base's link: git init would reach the checkout it points at
    os.remove(dst)
  ret = engine.run(['git', 'init', '-q', dst])
  if ret.returncode == 0:
    with open(os.path.join(dst, '.git', 'objects', 'info', 'alternates'), 'w') as f:
      f.write(os.path.realpath(os.path.join(common, 'objects')) + '\n')
    if shallow:
      shutil.copyfile(os.path.join(common, 'shallow'), os.path.join(dst, '.git', 'shallow'))
    ret = engine.run(['git', '-C', dst, 'checkout', '-q', '--detach', pin])
  if ret.returncode == 0:  # after the checkout: a ref HEAD names would make it start from that ref's tree
    ret = subprocess.run(['git', '-C', src, 'for-each-ref', '--format=update %(refname) %(objectname)'],
                         capture_output=True, text=True)
  if ret.returncode == 0:
    ret = subprocess.run(['git', '-C', dst, 'update-ref', '--stdin'], input=ret.stdout, capture_output=True, text=True)
  if ret.returncode != 0:
    depth = '--depth 1 ' if shallow else ''  # --depth would make a full clone shallow, cutting its describe's tags
    sys.exit(f'Error: the base pins {rel} at {pin[:10]}, which {src} cannot give ({ret.stderr.strip()}): '
             f'fetch it there (git -C {rel} fetch {depth}origin {pin})')


def prepare_base(main_root, worktree):
  """Give the base worktree its submodules at the base's pins, each a checkout borrowing this checkout's objects
  (git refuses a symlinked submodule path), so a submodule bump's own size change is in the diff; and
  the dependency dirs its own get_deps.py lists: linked from this checkout's where that is a clean checkout
  of the base's pin, else a checkout of the base's pin borrowing its objects; one that is no git checkout is refused.
  A dependency neither mandatory nor of a port the base keeps a sized board in is linked as it is: no sized build
  reads it. The base's own ports count, so a port renamed since leaves no dependency of the base's unchecked."""
  if check_build.fcntl is None and not _has_build_dir(worktree):
    sys.exit('Error: the base\'s check_build.py predates --build-dir, and its --shared build needs a POSIX lock: '
             'diff against a base with --build-dir')
  for rel in check_build.SUBMODULES:
    r = subprocess.run(['git', '-C', worktree, 'rev-parse', f'HEAD:{rel}'], capture_output=True, text=True)
    if r.returncode != 0:
      continue
    pin, src, dst = r.stdout.strip(), os.path.join(main_root, rel), os.path.join(worktree, rel)
    dep = _dep_checkout(src)
    if dep is None:
      sys.exit(f'Error: the base pins {rel} at {pin[:10]}, and {src} is no git checkout to give it: '
               f'git submodule update --init {rel}')
    _checkout_borrowing(dep[0], dst, pin, rel, src)
  linked = []
  ports = None if _boards is None else {p.parent.parent.name for b in _boards
                                         for p in Path(worktree, 'ports').glob(f'*/boards/{b}')}
  get_deps = runpy.run_path(os.path.join(worktree, 'tools', 'get_deps.py'))
  for rel, (_url, pin, families) in get_deps['deps_all'].items():
    src = os.path.join(main_root, rel)
    used = ports is None or rel in get_deps.get('deps_mandatory', {}) or not ports.isdisjoint(families.split())
    if not used or not os.path.isdir(src):  # unfetched: link_deps skips it
      linked.append(rel)
      continue
    dep = _dep_checkout(src)
    if dep is None:
      sys.exit(f'Error: {src} is no git checkout, so whether it holds the base\'s pin {pin[:10]} of {rel} is unknown: '
               f'move it aside and fetch it as get_deps.py does (python3 tools/get_deps.py {families})')
    if dep[1] == pin and _dep_clean(src):
      linked.append(rel)
    else:
      _checkout_borrowing(dep[0], os.path.join(worktree, rel), pin, rel, src)
  engine.link_deps(main_root, worktree, linked)


def _remove_containers(mount):
  """None once docker has listed no container bind-mounting `mount` for check_build's CONTAINER_SETTLE, removing each
  it lists: check_build's docker build of this run, which a stopped docker client leaves building in what the engine
  removes next, and whose create may land after the stop. Else why some may be left."""
  left = f'a container mounting {mount} may be left: docker ps -a --filter volume={mount}'
  end, absent_since = time.monotonic() + check_build.CONTAINER_GONE_WAIT, None
  while True:
    ps = engine.run(['docker', 'ps', '-aq', '--filter', f'volume={mount}'], timeout=check_build.DOCKER_TIMEOUT)
    if ps.returncode:
      return f'docker ps failed, so {left}'
    ids = ps.stdout.split()
    if ids:
      engine.run(['docker', 'rm', '-f', *ids], timeout=check_build.DOCKER_TIMEOUT)
    now = time.monotonic()
    absent_since = None if ids else absent_since or now
    if absent_since is not None and now - absent_since >= check_build.CONTAINER_SETTLE:
      return None
    if now > end:
      return left
    time.sleep(0.2)


def build(src_dir, build_dir, board, example):
  """`board` built by `src_dir`'s own check_build.py into `build_dir`; a failure is a
  CompletedProcess whose stdout is the contract's firstError and its log."""
  has_build_dir = _has_build_dir(src_dir)
  idf_local = bool(shutil.which('idf.py'))   # the exported ESP-IDF, else CI's docker image
  cmd = [sys.executable, os.path.join(src_dir, CHECK_BUILD), '--board', board]
  cmd += ['--idf', 'local'] if idf_local else []
  cmd += ['--build-dir', build_dir] if has_build_dir else ['--shared']
  ret, left = None, None
  try:
    ret = engine.run(cmd, timeout=BUILD_TIMEOUT)
  finally:
    if (ret is None or ret.returncode == 124) and not idf_local and shutil.which('docker'):
      # check_build mounts the build dir's parent, and a --shared build's checkout: each this run's alone
      mount = os.path.dirname(os.path.realpath(build_dir)) if has_build_dir else os.path.realpath(src_dir)
      base = os.path.realpath(src_dir) != os.path.realpath(ROOT)
      try:
        left = _remove_containers(mount)
      except BaseException as e:
        if base:
          raise engine.BaseInUse(f'removing them was cut short ({e!r}), '
                                 f'so a container mounting {mount} may be left') from e
        raise
      if left and base:
        raise engine.BaseInUse(left)
      if left and ret is None:
        print(f'Error: {left}', file=sys.stderr)
  lines = ret.stdout.strip().splitlines()
  try:
    result = json.loads(lines[-1]) if lines else {}
  except ValueError:
    result = {}
  if ret.returncode == 0 and result.get('pass'):
    if not has_build_dir:  # a base before --build-dir: its --shared root, moved where the engine sizes
      os.rmdir(build_dir)
      shutil.move(os.path.join(src_dir, result['boards'][0]['buildDir']), build_dir)
    return None
  rec = (result.get('boards') or [{}])[0]
  error = result.get('error') or result.get('firstError') or rec.get('firstError')
  if ret.returncode == 124:   # run()'s "Command timed out after ..." line, shown once
    error, ret.stderr = ret.stderr.strip().splitlines()[-1], ''
  log = f'log: {os.path.join(src_dir, rec["log"])}' if rec.get('log') else ''
  out = '\n'.join(x for x in (error, log, left) if x) or ret.stdout
  return subprocess.CompletedProcess(cmd, ret.returncode or 1, out + '\n', ret.stderr)


def first_error(text):
  """build()'s failure output leads with the contract's firstError."""
  return text.strip().splitlines()[0] if text.strip() else None


def elfs(build_dir, example):
  """The bootloader's elf: make's ports/<port>/tinyuf2-<board>.elf, cmake's and ESP-IDF's tinyuf2.elf."""
  root = glob.escape(build_dir)
  return glob.glob(f'{root}/tinyuf2.elf') + glob.glob(f'{root}/ports/*/tinyuf2-*.elf')
