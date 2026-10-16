#!/usr/bin/env python3
"""Build TinyUF2 for the boards a change affects, or for named boards: the project's build contract.

  check_build.py (--scope PATH... | --base REF [--worktree] | --board B...) [-D VAR=VAL]... [--shared] [--idf docker|local] [-v]
  check_build.py --board B --shared --hil-config ROSTER [--backend cmake]   (a HIL record: binds the flash target)
  check_build.py --select-only (--scope PATH... | --base REF [--worktree] | --diff-file FILE) [--hil-config ROSTER]

Each board builds the way .github/workflows/build.yml builds its port (make, cmake or ESP-IDF)
into its own build root, cmake-build/cmake-build-agent-<pid>-<board> (--shared:
cmake-build/cmake-build-<board>), and must produce its expected artifacts. A ghostfat input
also builds and runs the native ghostfat self-test of every ports/test_ghostfat config.

stdout ends with one JSON line (SKILL.md). Exit 0 pass, 1 a build or test failed, 2 usage,
resolution or a missing prerequisite ("error" names the remedy), 3 uncovered paths.
"""

import argparse
import contextlib
import fcntl
import functools
import hashlib
import json
import os
import re
import runpy
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUILD_YML = ROOT / '.github' / 'workflows' / 'build.yml'
BUILD_DIR = ROOT / 'cmake-build'

# Backend of every port CI builds, as build.yml's jobs build it; test_build.py holds the two equal.
BACKENDS = {
  'espressif': 'idf',
  'kinetis_k32l2': 'make',
  'lpc55': 'cmake',
  'maxim': 'cmake',
  'mimxrt10xx': 'cmake',
  'samd51': 'cmake',
  'stm32f3': 'cmake',
  'stm32f4': 'cmake',
  'stm32h5': 'cmake',
  'stm32h7': 'make',
  'stm32l4': 'make',
}
# Boards that stand in for their port: rig boards first; espressif covers every IDF target,
# mimxrt10xx both the RT10xx and RT1170 boot layouts.
REPRESENTATIVES = {
  'espressif': ['espressif_esp32s3_devkitm_1', 'espressif_esp32s2_devkitc_1', 'espressif_p4_function_ev',
                'espressif_esp32s31_func_core'],
  'kinetis_k32l2': ['frdm_k32l2b'],
  'lpc55': ['lpcxpresso55s69'],
  'maxim': ['max32666fthr'],
  'mimxrt10xx': ['imxrt1064_evk', 'imxrt1170_evk'],
  'samd51': ['intech_grid'],
  'stm32f3': ['stm32f303disco'],
  'stm32f4': ['stm32f411ve_discovery', 'feather_stm32f405_express'],
  'stm32h5': ['stm32h563_nucleo'],
  'stm32h7': ['daisy_seed'],
  'stm32l4': ['swan_r5'],
}
# Ports no CI job builds: a change there is uncovered; --board may still build one explicitly.
UNBUILT = {
  'ch32v20x': ('make', 'its riscv job is disabled in build.yml'),
  'template_port': (None, 'a template no build compiles'),
}
# compiler a port's make/cmake build needs, when not arm-none-eabi-gcc
COMPILER = {'ch32v20x': 'riscv-none-elf-gcc'}
# ports whose make self-update target only echoes "not implemented yet"
NO_SELF_UPDATE = {'ch32v20x', 'kinetis_k32l2', 'stm32h7', 'stm32l4'}
GHOSTFAT = 'test_ghostfat'
GHOSTFAT_INPUTS = ('src/ghostfat.c', 'src/favicon/', 'src/board_api.h', 'src/compile_date.h', 'src/uf2.h',
                   'lib/uf2', 'ports/family_support.cmake', 'ports/test_ghostfat/',
                   '.github/workflows/build_ghostfat.yml')
CORE = ('src/', 'lib/', 'ports/family_support.cmake', 'CMakeLists.txt', 'cmake/', 'tools/get_deps.py')
# make files every Makefile port includes: read by the make ports' builds and CodeQL's
MAKE_SHARED = ('ports/make.mk', 'ports/rules.mk')
CONTRACT_TESTS = ('.claude/test/test_build', '.claude/test/test_hil')
# the HIL contract's runner, its lock helper's pin and rosters: a change there re-runs the battery on every roster board
HIL_CONTROL = ('.claude/skills/hil-contract/scripts/', 'test/hil/', 'lib/agentrc', '.github/workflows/hil.yml')
# hil_test.py imports these: the identity, artifacts and build dirs the battery trusts
HIL_IMPORTS = '.claude/skills/build/scripts/'
BUILD_CONTROL = (HIL_IMPORTS, '.github/workflows/build.yml',
                 '.github/workflows/build_util.yml', '.github/workflows/ci_set_matrix.py', '.github/actions/')
NOTHING = ('.claude/', '.github/', '.idea/', 'tools/codespell/', 'tools/gen_boards.py', 'tools/touch1200.py',
           'ports/build_all.py', 'CLAUDE.md', 'AGENTS.md', '.agents', 'LICENSE', '.gitignore', '.gitmodules',
           '.pre-commit-config.yaml', '.codespellrc', '.clang-format')
CODEQL = '.github/workflows/codeql-buildscript.sh'
# one board per backend for a change to how boards build
SMOKE = {'make': 'frdm_k32l2b', 'cmake': 'feather_stm32f405_express', 'idf': 'espressif_esp32s3_devkitm_1'}


# What a roster flasher runs to install TinyUF2: the build's own flash target, and the build-tree files that
# target reads, which a HIL record pins so the runner can check them before it flashes.
FLASH = {'jlink': ('tinyuf2-jlink', ('tinyuf2.jlink', 'tinyuf2.hex')), 'stlink': ('tinyuf2-stlink', ('tinyuf2.hex',)),
         'esptool': ('flash', ('flash_args', 'bootloader/bootloader.bin', 'partition_table/partition-table.bin',
                               'ota_data_initial.bin', 'tinyuf2.bin'))}
# a roster flasher's args, whose one group is the device or chip its flash target must name
FLASHER_ARGS = {'jlink': r'-device (\S+)', 'stlink': r'-device (\S+)', 'esptool': r'--chip (\w+)'}
# a further install route of an Espressif board (tinyuf2.routes): the chip's built-in USB-Serial/JTAG through agentrc's
# openocd_esp, which programs the esptool binding's segments; uid is the USJ serial
ROUTE_ARGS = {'openocd_esp': r'-f board/(esp32[a-z0-9]*)-builtin\.cfg'}
NINJA_STEP = re.compile(r'\[\d+/\d+\] ')   # ninja's progress prefix
NINJA_QUERY_TIMEOUT = 30   # s for one ninja query
DOCKER_TIMEOUT, CONTAINER_GONE_WAIT = 30, 10   # s for one docker call; s a killed query's container may linger
CONTAINER_SETTLE = 2   # s docker must list no container before a killed client's pending create counts as never landing
# configure variables that select a probe or port: a HIL record sets them from the roster, never from -D
SELECTION = ('JLINK_OPTION', 'STLINK_SERIAL', 'OPENOCD_SERIAL', 'OPENOCD_OPTION', 'ESPPORT')


class Fail(Exception):
  pass


def git(*args):
  r = subprocess.run(['git', *args], capture_output=True, text=True, cwd=ROOT)
  if r.returncode != 0:
    raise Fail(f'git {" ".join(args)} failed: {r.stderr.strip()}')
  return r.stdout


def ports_dir(port):
  return ROOT / 'ports' / port


def boards_of(port):
  d = ports_dir(port) / 'boards'
  return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


def port_of(board):
  hits = sorted(p.parent.parent.name for p in (ROOT / 'ports').glob(f'*/boards/{board}') if p.is_dir())
  hits = [h for h in hits if h != GHOSTFAT]
  if len(hits) != 1:
    raise Fail(f'board {board!r} matches {hits or "no"} port')
  return hits[0]


def ci_idf_version():
  m = re.search(r"toolchain:\s*'esp-idf'\s*\n\s*toolchain_version:\s*'([^']+)'", BUILD_YML.read_text())
  if not m:
    raise Fail(f'no esp-idf toolchain_version in {BUILD_YML.relative_to(ROOT)}')
  return m.group(1)


def app_boards(app_dir):
  """Boards an app's Makefile builds for: None for every board, [] for a stub that builds
  nothing (no make.mk or app.mk include, only an echo)."""
  mk = app_dir / 'Makefile'
  if not mk.is_file():
    return None
  text = mk.read_text()
  if not re.search(r'^\s*include\s+\S*(make|app)\.mk', text, re.M):
    return []
  return re.findall(r'ifeq\s*\(\$\(BOARD\),\s*(\w+)\)', text) or None


@functools.cache
def codeql_build():
  """(port, board) codeql-buildscript.sh builds with make `all` on every pull request."""
  text = (ROOT / CODEQL).read_text()
  ports = set(re.findall(r'(?:cd|-C)\s+ports/(\w+)', text))
  boards = set(re.findall(r'^\s*make\b[^\n]*\bBOARD=(\w+)[^\n]*\ball\b', text, re.M))
  if len(ports) != 1 or len(boards) != 1:
    raise Fail(f'cannot read one port and one `make ... all` board from {CODEQL}: update codeql_build()')
  return ports.pop(), boards.pop()


def build_file_kind(name):
  """'make' for a Makefile or *.mk, 'cmake' for a CMakeLists.txt or *.cmake, else None."""
  if name == 'Makefile' or name.endswith('.mk'):
    return 'make'
  if name == 'CMakeLists.txt' or name.endswith('.cmake'):
    return 'cmake'
  return None


def read_by_backend(path, backend):
  """Whether CI's backend for the port reads this build file: a make port never reads CMake
  files, a cmake or idf port never reads Makefiles. Sources and headers are read by both."""
  kind = build_file_kind(path.rsplit('/', 1)[-1])
  return kind is None or (kind == 'make') == (backend == 'make')


def code_lines(f):
  return '\n'.join(l for l in f.read_text(errors='replace').splitlines() if not l.lstrip().startswith('#'))


def espressif_apps():
  """Apps ports/espressif/CMakeLists.txt builds as ExternalProjects."""
  return re.findall(r'SOURCE_DIR\s+\$\{CMAKE_CURRENT_LIST_DIR\}/apps/(\w+)', code_lines(ports_dir('espressif') / 'CMakeLists.txt'))


def cmake_app_calls(port):
  """The family_add_app() calls of a cmake port's CMakeLists.txt as (name, source dir, boards): boards
  None for every board, else those its BOARDS argument names."""
  calls = []
  for m in re.finditer(r'^\s*family_add_app\(\s*([\w-]+)\s+([^\s)]+)([^)]*)\)',
                       code_lines(ports_dir(port) / 'CMakeLists.txt'), re.M):
    boards = re.search(r'\bBOARDS\s+([^)]*)', m.group(3))
    calls.append((m.group(1), m.group(2), boards.group(1).split() if boards else None))
  return calls


def cmake_apps(port, board):
  """Apps a cmake port builds for the board, each named after the app's target and so its <name>.uf2."""
  return [name for name, _, boards in cmake_app_calls(port) if boards is None or board in boards]


def port_app_selection(port, path):
  """Boards that compile a change under ports/<port>/apps/: the app's own enabled boards, or for
  a file shared by the port's apps (app.mk) those of every app that includes it; and CI's scope."""
  parts = path.split('/')
  apps_dir = ports_dir(port) / 'apps'
  if BACKENDS[port] == 'idf':
    if len(parts) >= 4 and parts[3] not in espressif_apps():
      return None, f'ports/espressif/CMakeLists.txt builds no ExternalProject for apps/{parts[3]}', {}
    return (rep_selection([port], f'builds {"/".join(parts[2:4])}'), f'{port} {"/".join(parts[2:4])}',
            whole_ports([port]))
  if BACKENDS[port] == 'cmake':
    calls = [c for c in cmake_app_calls(port) if c[1].endswith(f'/apps/{parts[3]}')] if len(parts) >= 5 else []
    if not calls:
      return None, f'ports/{port}/CMakeLists.txt adds no app that reads {path}', {}
    boards, ci = {}, {}
    for name, _, enabled in calls:
      boards.update(rep_selection([port], f'builds {name}') if enabled is None else
                    {(b, 'cmake'): f'enables {name}' for b in enabled})
      ci = merge_ci(ci, whole_ports([port]) if enabled is None else {port: enabled})
    return boards, f'{port} apps: {", ".join(sorted(c[0] for c in calls))}', ci
  if len(parts) >= 5 and (apps_dir / parts[3]).is_dir():
    apps = [apps_dir / parts[3]]
  else:
    apps = [m.parent for m in apps_dir.glob('*/Makefile') if re.search(rf'^\s*include\s+\S*\b{re.escape(parts[-1])}\b',
                                                                     m.read_text(), re.M)]
  boards, ci = {}, {}
  for app in apps:
    enabled = app_boards(app)
    if enabled is None:
      boards.update(rep_selection([port], f'builds apps/{app.name}'))
    for b in enabled or []:
      boards[(b, BACKENDS[port])] = f'enables apps/{app.name}'
    ci = merge_ci(ci, whole_ports([port]) if enabled is None else {port: enabled})
  if not boards:
    return None, f'no {port} board builds an app that reads {path}', {}
  return boards, f'{port} apps: {", ".join(sorted(a.name for a in apps))}', ci


def ports_using_app(app):
  """CI-built ports whose build, in the backend CI uses, compiles sources of the top-level apps/<app>."""
  hits = []
  for port, backend in sorted(BACKENDS.items()):
    kind = 'make' if backend == 'make' else 'cmake'
    ref = re.compile(rf'(?<![\w/])apps/{app}/\S+\.c\b' if kind == 'make' else rf'\$\{{TOP\}}/apps/{app}\b')
    files = [f for f in ports_dir(port).rglob('*') if f.is_file() and build_file_kind(f.name) == kind]
    for f in files:
      if ref.search(code_lines(f)):
        hits.append(port)
        break
  return hits


@functools.cache
def get_deps_table():
  """{dependency path: (pinned commit, [families])} from tools/get_deps.py's deps_all."""
  try:
    # run_path, not an import: no __pycache__ written into tools/
    rows = runpy.run_path(str(ROOT / 'tools' / 'get_deps.py'), run_name='get_deps')['deps_all']
    return {dep: (row[1], row[2].split()) for dep, row in rows.items()}
  except Exception as e:
    raise Fail(f'cannot read deps_all from tools/get_deps.py: {type(e).__name__}: {e}')


def deps_rows():
  """{dependency path: [families]} from tools/get_deps.py's deps_all."""
  return {dep: families for dep, (_, families) in get_deps_table().items()}


def deps_pins():
  return {dep: pin for dep, (pin, _) in get_deps_table().items()}


def deps_families(path):
  """Ports whose dependency rows in tools/get_deps.py cover the dependency directory `path`."""
  for dep, families in deps_rows().items():
    if path == dep or path.startswith(dep + '/'):
      return [p for p in families if p in BACKENDS]
  return None


def rep_selection(ports, why):
  return {(b, BACKENDS[p]): why for p in ports for b in REPRESENTATIVES[p]}


# CI's scope of a path: FULL, or {port: None for every board | [boards]}. CI builds every board a
# change reaches; the representatives only cap a local build.
FULL = 'full'


def whole_ports(ports):
  return {p: None for p in ports}


def merge_ci(a, b):
  if FULL in (a, b):
    return FULL
  out = dict(a)
  for p, boards in b.items():
    out[p] = None if boards is None or out.get(p, ()) is None else sorted({*out.get(p, []), *boards})
  return out


def classify(path):
  """One path's rule: effect none (nothing to build), gap (uncovered), select or core, the boards
  it selects as {(board, backend): reason}, and whether it adds the ghostfat self-test or the
  contract's own tests."""
  def out(rule, effect, reason, boards=None, ghostfat=False, tests=False, hil=False, ci=None):
    return {'path': path, 'rule': rule, 'effect': effect, 'reason': reason, 'boards': boards or {},
            'ghostfat': ghostfat, 'tests': tests, 'hil': hil, 'ci': ci or {}}

  ghostfat = path.startswith(GHOSTFAT_INPUTS)
  parts = path.split('/')
  if path.startswith(CONTRACT_TESTS):
    return out('contract-tests', 'select', "the contract's own tests; a test edit changes no board build", tests=True)
  if path.startswith(HIL_CONTROL):
    return out('hil-control', 'select', 'the HIL runner or a roster changed: its tests and the battery on every '
               'roster board', tests=True, hil=True)
  if path.startswith(BUILD_CONTROL):
    boards = {(b, be): f'{be} smoke build for {path}' for be, b in SMOKE.items()}
    runner = path.startswith(HIL_IMPORTS)
    return out('build-control', 'select', 'how boards build changed: the contract tests and one smoke build '
               'per backend; no firmware build verifies workflow syntax or orchestration' +
               ('; the HIL runner imports it: the battery on every roster board' if runner else ''),
               boards, tests=True, hil=runner, ci=FULL)
  if path.endswith('.md'):
    return out('docs', 'none', 'documentation')
  codeql_port, codeql_board = codeql_build()
  if path == CODEQL:
    return out('codeql', 'select', f'codeql-buildscript.sh builds {codeql_board} with make',
               {(codeql_board, 'make'): 'codeql build'})
  if path.startswith(f'ports/{GHOSTFAT}/') or path == '.github/workflows/build_ghostfat.yml':
    return out('ghostfat', 'select', 'ghostfat self-test input', ghostfat=True)
  if len(parts) >= 2 and parts[0] == 'ports' and parts[1] in UNBUILT:
    return out('unbuilt-port', 'gap', f'ports/{parts[1]}: {UNBUILT[parts[1]][1]}')
  if len(parts) >= 3 and parts[0] == 'ports' and parts[1] in BACKENDS:
    port = parts[1]
    if not read_by_backend(path, BACKENDS[port]):
      if port == codeql_port and parts[2] != 'apps' and (parts[2] != 'boards' or parts[3:4] == [codeql_board]):
        return out('codeql', 'select', f'CodeQL builds {codeql_board} with make on every pull request',
                   {(codeql_board, 'make'): f'reads {path}'})
      return out('other-backend', 'gap', f'CI builds {port} with {BACKENDS[port]}, which never reads {parts[-1]}')
    if parts[2] == 'boards' and len(parts) >= 4 and (ports_dir(port) / 'boards' / parts[3]).is_dir():
      return out('board', 'select', f'board {parts[3]} changed',
                 {(parts[3], BACKENDS[port]): f'{path} is its own'}, ghostfat, ci={port: [parts[3]]})
    if parts[2] == 'apps':
      boards, reason, ci = port_app_selection(port, path)
      return out('port-app', 'select' if boards else 'gap', reason, boards, ci=ci)
    return out('port', 'select', f'{port} port file', rep_selection([port], f'{port} representative'), ghostfat,
               ci=whole_ports([port]))
  if len(parts) >= 2 and parts[0] == 'ports' and len(parts) >= 3 and (ROOT / 'ports' / parts[1]).is_dir():
    raise Fail(f'ports/{parts[1]} has no backend in check_build.py: add it to BACKENDS or UNBUILT')
  if parts[0] == 'apps' and len(parts) >= 2:
    users = ports_using_app(parts[1])
    if not users:
      return out('app', 'gap', f'no CI-built port builds apps/{parts[1]}')
    return out('app', 'select', f'apps/{parts[1]} is built by {", ".join(users)}',
               rep_selection(users, f'builds apps/{parts[1]}'), ci=whole_ports(users))
  if path.startswith(('lib/mcu/', 'lib/sct_neopixel')):
    families = deps_families(path)
    if families is not None:
      if not families:
        return out('dep', 'gap', f'{path}: no CI-built port uses this dependency')
      return out('dep', 'select', f'dependency of {", ".join(families)}', rep_selection(families, f'uses {path}'),
                 ci=whole_ports(families))
  if path in MAKE_SHARED:
    make_ports = [p for p, be in BACKENDS.items() if be == 'make']
    return out('make-shared', 'select', 'every make port and the CodeQL build read it',
               {**rep_selection(make_ports, f'make reads {path}'),
                (codeql_board, 'make'): f'codeql build reads {path}'}, ci=whole_ports(make_ports))
  if path.startswith(NOTHING):
    return out('nothing', 'none', 'no firmware build reads this path')
  if path.startswith(CORE):
    return out('core', 'core', 'shared by every port', ghostfat=ghostfat, ci=FULL)
  return out('unclassified', 'core', 'unclassified path: every port', ghostfat=ghostfat, ci=FULL)


def repo_path(p):
  """A path as git spells it, relative to the checkout: ./src/x.c and /abs/.../src/x.c are src/x.c."""
  # lexical, not resolve(): a worktree's dependency symlinks point into the primary checkout
  p = os.path.relpath(os.path.abspath(p), ROOT) if os.path.isabs(p) else os.path.normpath(p)
  if p.startswith('..'):
    raise Fail(f'{p} is outside the checkout')
  return p


def changed_paths(base=None, worktree=False, scope=None, diff_file=None):
  if diff_file:
    try:
      lines = Path(diff_file).read_text().splitlines()
    except OSError as e:
      raise Fail(f'cannot read --diff-file: {e}')
    return [repo_path(l.strip()) for l in lines if l.strip()], {'mode': 'diff-file'}
  if scope:
    paths = []
    for p in scope:
      p = repo_path(p)
      if (ROOT / p).is_dir() and not (ROOT / p / '.git').exists():
        files = [f for f in git('ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', p).split('\0') if f]
        if not files:
          raise Fail(f'{p} is a directory with no files git reports')
        paths += files
      elif (ROOT / p).exists() or subprocess.run(['git', 'cat-file', '-e', f'HEAD:{p}'], cwd=ROOT,
                                                  capture_output=True).returncode == 0:
        paths.append(p)
      else:
        raise Fail(f'{p} does not exist and is not tracked at HEAD')
    return paths, {'mode': 'paths'}
  merge_base = git('merge-base', base, 'HEAD').strip()
  paths = git('diff', '--name-only', '--no-renames', merge_base, 'HEAD').split()
  info = {'mode': 'worktree' if worktree else 'base', 'base': base, 'merge_base': merge_base,
          'head': git('rev-parse', 'HEAD').strip()}
  if worktree:
    paths += git('diff', '--name-only', '--no-renames', 'HEAD').split()
    paths += git('ls-files', '--others', '--exclude-standard').split()
  return sorted(set(paths)), info


def own_checkout(path):
  """Whether `path` is a git checkout of its own: git -C on a plain or empty directory (an
  uninitialised submodule, an unpacked dependency) silently answers for the parent repository."""
  r = subprocess.run(['git', '-C', str(ROOT / path), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
  return r.returncode == 0 and os.path.realpath(r.stdout.strip()) == os.path.realpath(ROOT / path)


def git_in(path, *args):
  r = subprocess.run(['git', '-C', str(ROOT / path), *args], capture_output=True, text=True)
  if r.returncode != 0:
    raise Fail(f'git -C {path} {" ".join(args)} failed: {r.stderr.strip()}')
  return r.stdout


def dirty_inputs(paths):
  return [p for p in paths if git_in(p, 'status', '--porcelain', '--untracked-files=all').strip()]


def identity(ports=()):
  """What a result was built from: HEAD, whether the tree differs from it, the submodule commits, the
  commits of the get_deps dependencies `ports` use, and which of those inputs cannot be trusted:
  local changes, not a checkout of its own, or a dependency off its get_deps pin."""
  subs = {}
  for line in git('submodule', 'status').splitlines():
    sha, path = line[1:].split()[:2]
    subs[path] = sha
  used = [dep for dep, families in sorted(deps_rows().items()) if any(p in families for p in ports)]
  # worktree deps are symlinks into the primary checkout, invisible to this checkout's status
  missing = [p for p in [*subs, *used] if not own_checkout(p)]
  deps = {dep: git_in(dep, 'rev-parse', 'HEAD').strip() for dep in used if dep not in missing}
  pins = deps_pins()
  info = {'head': git('rev-parse', 'HEAD').strip(), 'dirty': bool(git('status', '--porcelain').strip()),
          'submodules': subs, 'deps': deps, 'missingInputs': missing,
          'depsOffPin': [d for d, sha in deps.items() if sha != pins[d]]}
  info['dirtyInputs'] = dirty_inputs(own_inputs(info))
  return info


def own_inputs(info):
  """The submodules and dependencies `identity` could check, i.e. those that are checkouts of their own."""
  return [p for p in [*info['submodules'], *info['deps']] if p not in info['missingInputs']]


def moved_inputs(before, after):
  """Inputs whose identity differs between two `identity` records: '.' for the checkout's HEAD or dirty
  state, else each submodule or dependency whose commit or checkout changed."""
  moved = {'.'} if (before['head'], before['dirty']) != (after['head'], after['dirty']) else set()
  commits = [{**i['submodules'], **i['deps']} for i in (before, after)]
  moved |= {p for p in commits[0].keys() | commits[1].keys() if commits[0].get(p) != commits[1].get(p)}
  return moved | (set(before['missingInputs']) ^ set(after['missingInputs']))


def select(paths):
  records = [classify(p) for p in paths]
  full = any(r['effect'] == 'core' for r in records)
  boards = rep_selection(sorted(REPRESENTATIVES), 'core: shared by every port') if full else {}
  for r in records:
    for k, why in r['boards'].items():
      boards.setdefault(k, why)
  return {
    'full': full,
    'boards': boards,
    'ghostfat': any(r['ghostfat'] for r in records),
    'tests': any(r['tests'] for r in records),
    'records': records,
  }


def ci_selection(sel):
  """What CI builds: every board of every port when full (ghostfat too), else each reached board."""
  ci = {}
  for r in sel['records']:
    ci = merge_ci(ci, r['ci'])
  if ci == FULL:
    return {'full': True, 'ports': {}, 'ghostfat': True}
  return {'full': False, 'ports': {p: boards_of(p) if b is None else b for p, b in sorted(ci.items())},
          'ghostfat': sel['ghostfat']}


def path_view(records, effect=None, keys=('path', 'rule', 'effect', 'reason')):
  return [{k: r[k] for k in keys} for r in records if effect in (None, r['effect'])]


HIL_APP = 'dfu_runtime'   # the app hil_test.py's Espressif battery copies through TinyUF2


def hil_selection(sel, config):
  """Roster boards the selection puts under the HIL battery. A board's own change reaches that board,
  an app change none, any other change every roster board of the ports it selects, a core or HIL-control
  change the whole roster; what no roster board on this host can run is uncovered, whatever else was
  selected."""
  try:
    entries = json.loads((ROOT / config).read_text())['boards']
    roster = sorted({b['name'] for b in entries})   # TinyUF2 names
    espressif = {b['name'] for b in entries if b['name'] in boards_of('espressif')}   # whatever installs them
  except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
    raise Fail(f'cannot read boards from {config}: {e}')
  by_port = {}
  for name in roster:
    by_port.setdefault(port_of(name), []).append(name)
  def kind(parts):   # the HIL builds with cmake whatever CI uses: its build files decide, not CI's
    if parts[0] == 'ports' and (len(parts) == 2 or parts[1] in BACKENDS):
      return build_file_kind(parts[-1])
    return None
  records = [(r, parts, kind(parts)) for r in sel['records'] for parts in [r['path'].split('/')]]
  full = any(r['effect'] == 'core' and k != 'make' for r, _, k in records)
  boards, uncovered = set(), {}
  if full:
    boards.update(roster)
    for p in sorted(set(BACKENDS) - set(by_port)):
      uncovered[p] = f'core change: no {config} board for {p}'
  for r, parts, k in records:
    if r['hil']:
      boards.update(roster)
    elif k == 'make':
      uncovered[r['path']] = f'the HIL builds with cmake, which never reads {r["path"]}'
    # the battery builds no port app, and a core file reaches every roster board above
    elif k == 'cmake' and len(parts) >= 3 and r['effect'] != 'core' and parts[2] != 'apps':
      if parts[2] == 'boards' and len(parts) >= 5:
        own = [parts[3]] if parts[3] in roster else []
      else:
        own = by_port.get(parts[1], [])
      if own:
        boards.update(own)
      else:
        uncovered[r['path']] = f'no {config} board builds {r["path"]}'
    elif r['effect'] == 'gap':   # firmware no build covers is no HIL board's either
      uncovered[r['path']] = r['reason']
    elif r['rule'] in ('app', 'port-app'):
      app = parts[1] if r['rule'] == 'app' else parts[3] if len(parts) > 3 else None
      ports = {port_of(b) for b, _ in r['boards']} if r['rule'] == 'app' else {parts[1]}
      if app != HIL_APP:
        uncovered[r['path']] = f'the battery runs the bootloader and {HIL_APP} on Espressif boards, never {r["path"]}'
        continue
      # a port that builds the app but has no Espressif roster board: its battery never runs it
      for p in sorted(ports):
        own = [b for b in espressif if port_of(b) == p]
        if own:
          boards.update(own)
        else:
          uncovered[f'{r["path"]} on {p}'] = f'no {config} Espressif board of {p} runs {HIL_APP}'
    elif r['rule'] == 'board':
      (b, _), = r['boards']
      if b in roster:
        boards.add(b)
      else:
        uncovered[b] = f'{r["path"]}: {b} is not in {config}'
    else:
      for p in sorted({port_of(b) for b, _ in r['boards']}):
        if p in by_port:
          boards.update(by_port[p])
        else:
          uncovered[p] = f'{r["path"]}: no {config} board for {p}'
  return {'config': config, 'full': full or any(r['hil'] for r in sel['records']), 'boards': sorted(boards),
          'uncovered': [{'target': t, 'reason': why} for t, why in sorted(uncovered.items())]}


def manifest(sel, info, hil_config=None):
  ports = {}
  for (b, backend) in sel['boards']:
    ports.setdefault(port_of(b), []).append(b)
  out = {
    'version': 1,
    'input': info,
    'build': {
      'full': sel['full'],
      'needed': bool(sel['boards'] or sel['ghostfat'] or sel['tests']),
      'ports': {p: sorted(set(v)) for p, v in sorted(ports.items())},
      'builds': [{'board': b, 'backend': backend} for (b, backend) in sel['boards']],
      'ghostfat': sel['ghostfat'],
      'tests': sel['tests'],
      'paths': path_view(sel['records']),
      'ci': ci_selection(sel),
    },
  }
  if hil_config:
    out['hil'] = hil_selection(sel, hil_config)
  return out


# ------------------------------------------------------------------ building

def first_error(log):
  lines = log.splitlines()
  # a compiler, linker or CMake diagnostic names the cause; ninja's FAILED line only the object
  for pattern in (r':\d+(:\d+)?: (fatal )?error:|undefined reference|region .* overflowed|multiple definition|'
                  r'^CMake Error\b',
                  r'\berror\b|Error \d|FAILED|No rule to make|not found'):
    for i, line in enumerate(lines):
      if NINJA_STEP.match(line):   # e.g. "Building ... error.c.obj"
        continue
      if re.search(pattern, line, re.I) and 'warning' not in line:
        if re.match(r'CMake Error\b.*:$', line):   # its message is on the next indented line
          nxt = next((l for l in lines[i + 1:] if l.strip()), '')
          if nxt[:1].isspace():
            line = f'{line} {nxt.strip()}'
        return line.strip()[:400]
  tail = [l for l in lines if l.strip()]
  return tail[-1].strip()[:400] if tail else ''


def run(cmd, log, verbose, cwd=ROOT):
  with open(log, 'a') as f:
    f.write('$ ' + ' '.join(map(str, cmd)) + '\n')
    f.flush()
    p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors='replace')
    for line in p.stdout:
      f.write(line)
      if verbose:
        sys.stderr.write(line)
    return p.wait()


def check_deps(port):
  """Remedy for a missing submodule or family dependency, None when all are present."""
  missing = [s for s in ('lib/tinyusb', 'lib/uf2', 'lib/agentrc') if not (ROOT / s).is_dir() or not any((ROOT / s).iterdir())]
  if missing:
    return f'empty submodule {", ".join(missing)}: git submodule update --init {" ".join(missing)}'
  for dep, families in deps_rows().items():
    if port in families:
      d = ROOT / dep
      if not d.is_dir() or not any(d.iterdir()):
        return (f'{dep} missing: in a worktree symlink it from the primary checkout (CLAUDE.md), '
                f'else python3 tools/get_deps.py {port}')
  return None


def check_tools(port, backend, idf_mode):
  cc = COMPILER.get(port, 'arm-none-eabi-gcc')
  need = {'make': ['make', cc], 'cmake': ['cmake', 'ninja', cc],
          'idf': ['docker'] if idf_mode == 'docker' else ['idf.py']}[backend]
  missing = [t for t in need if not shutil.which(t)]
  if missing:
    return f'{", ".join(missing)} not on PATH' + (' (export ESP-IDF first)' if 'idf.py' in missing else '')
  return None


def expected_artifacts(port, board, backend, root):
  bin_dir = root / '_bin'
  if backend == 'make':
    exp = [bin_dir / f'tinyuf2-{board}.bin', bin_dir / f'tinyuf2-{board}.hex']
    if port not in NO_SELF_UPDATE:
      exp.append(bin_dir / 'apps' / f'update-tinyuf2-{board}.uf2')
    return exp
  if backend == 'cmake':
    exp = [bin_dir / 'tinyuf2.bin', bin_dir / 'tinyuf2.hex']
    cml = (ports_dir(port) / 'CMakeLists.txt').read_text()
    exp += [bin_dir / 'apps' / f'{app}.uf2' for app in cmake_apps(port, board)]
    exp += [bin_dir / a for a in re.findall(r'\$\{ARTIFACT_PATH\}/(apps/[\w.-]+\.uf2)', cml)]
    return exp
  return [bin_dir / f for f in ('tinyuf2.bin', 'bootloader.bin', 'partition-table.bin', 'ota_data_initial.bin',
                                'flash_args', 'combined.bin', 'apps/update-tinyuf2.uf2', 'apps/blinky.uf2',
                                f'apps/{HIL_APP}.uf2')]


# what an IDF build's flash layout also depends on: the HIL admits its segments only against these
IDF_CONFIG = ('sdkconfig',)


def build_make(port, board, root, defines, log, verbose, rec):
  base = ['make', '-C', ports_dir(port), f'BOARD={board}', f'BUILD_ROOT={root}', *defines]
  # copy-artifact runs after self-update, never beside it under -j
  if run(base + [f'-j{os.cpu_count()}', 'all', 'self-update'], log, verbose) or run(base + ['copy-artifact'], log, verbose):
    return False, []
  apps = []
  for app in sorted((ports_dir(port) / 'apps').glob('*/Makefile')):
    if app.parent.name == 'self_update':
      continue
    enabled = app_boards(app.parent)
    if run(['make', '-C', app.parent, f'BOARD={board}', f'BUILD_ROOT={root}', f'-j{os.cpu_count()}', *defines,
            'all'], log, verbose):
      return False, apps
    if enabled is None or board in enabled:
      apps.append(root / 'ports' / port / 'apps' / app.parent.name)
    elif enabled == []:
      rec.setdefault('notImplemented', []).append(f'apps/{app.parent.name}')
  return True, apps


def build_cmake(port, board, root, defines, log, verbose):
  cfg = ['cmake', '-B', root, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=MinSizeRel', f'-DBOARD={board}',
         f'-DARTIFACT_PATH={root / "_bin"}', *[f'-D{d}' for d in defines], ports_dir(port)]
  return not (run(cfg, log, verbose) or run(['cmake', '--build', root], log, verbose)), []


def build_idf(board, root, defines, log, verbose, idf_mode, image):
  idf = ['idf.py', '-C', 'ports/espressif', '-B', str(root), f'-DBOARD={board}',
         f'-DARTIFACT_PATH={root / "_bin"}', *[f'-D{d}' for d in defines], 'build']
  if idf_mode == 'local':
    return not run(idf, log, verbose), []
  inner = "git config --global --add safe.directory '*' && " + shlex.join(idf)
  return not run(idf_docker(root) + [image, 'bash', '-c', inner], log, verbose), []


def idf_docker(root, name=None):
  """`docker run` with the checkout, its git dir and the build dir mounted at their own paths, image last."""
  common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir').strip())
  cmd = ['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/tmp', '-w', str(ROOT)]
  if name:
    cmd += ['--name', name]
  for m in sorted({ROOT, common, root.parent}):
    cmd += ['-v', f'{m}:{m}']
  return cmd


def ninja_in(backend, idf_mode, image, root, args):
  """Runs ninja on `root` with the ninja that built it: the host's, or the IDF image's (whose build log and
  generator a host ninja would rewrite). Callers bind the build's own backend, mode and image. The query runs here,
  its process killed past NINJA_QUERY_TIMEOUT or on an interruption (only that process: `ninja -t commands` starts
  nothing, though a docker client may), and it stays in this process group, so a kill of the group reaches it too.
  stdout and stderr come back apart."""
  cmd = ['ninja', '-C', str(root), *args]
  container = None
  if backend == 'idf' and idf_mode == 'docker':
    container = f'tinyuf2-query-{os.getpid()}-{uuid.uuid4().hex}'
    cmd = idf_docker(root, name=container) + [image, *cmd]   # the entrypoint sources export.sh, then runs cmd
  try:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=NINJA_QUERY_TIMEOUT)
  except BaseException as e:   # subprocess.run has killed the query
    left = container_left(container) if container else ''
    if isinstance(e, subprocess.TimeoutExpired):
      raise Fail(f'{root.name}: ninja {shlex.join(args)} timed out after {NINJA_QUERY_TIMEOUT}s{left}') from None
    if left:
      print(f'{root.name}: interrupted ninja {shlex.join(args)}{left}', file=sys.stderr)
    raise


def container_left(name):
  """'' once docker has listed no `name` for CONTAINER_SETTLE, `docker rm -f` before each look, so a create still
  pending when the client was killed is removed when it lands; else why, naming it, for an error message."""
  end, absent_since = time.monotonic() + CONTAINER_GONE_WAIT, None
  try:
    while True:
      subprocess.run(['docker', 'rm', '-f', name], capture_output=True, text=True, timeout=DOCKER_TIMEOUT)
      r = subprocess.run(['docker', 'ps', '-aq', '-f', f'name=^{name}$'], capture_output=True, text=True,
                         timeout=DOCKER_TIMEOUT)
      if r.returncode:
        return f'; docker ps failed ({r.stderr.strip()[-200:]}), so container {name} may be left: docker rm -f {name}'
      now = time.monotonic()
      if r.stdout.strip():
        absent_since = None
      elif absent_since is None:
        absent_since = now
      if absent_since is not None and now - absent_since >= CONTAINER_SETTLE:
        return ''
      if now > end:
        return (f'; container {name} still exists: docker rm -f {name}' if absent_since is None else
                f'; container {name} was listed within {CONTAINER_SETTLE}s, so it may be left: docker rm -f {name}')
      time.sleep(0.2)
  except (OSError, subprocess.SubprocessError) as e:
    return f'; docker failed ({e}), so container {name} may be left: docker rm -f {name}'


def backend_of(port):
  """The backend CI builds a port with, or an unbuilt port's on-request backend (None for none)."""
  if port not in BACKENDS and port not in UNBUILT:
    raise Fail(f'ports/{port} has no backend in check_build.py: add it to BACKENDS or UNBUILT')
  return BACKENDS.get(port) or UNBUILT[port][0]


def roster_flasher(config, board):
  """The board's roster flasher, and the configure defines that bind the build's flash target to its probe.
  ESP-IDF takes the bridge's tty at flash time (ESPPORT), which the runner resolves from the serial."""
  try:
    entry = next((b for b in json.loads((ROOT / config).read_text())['boards'] if b['name'] == board), None)
    if entry is None:
      raise Fail(f'{board} is not on {config}')
    name, uid, fargs = (entry['flasher'][k] for k in ('name', 'uid', 'args'))
  except (OSError, ValueError, KeyError, TypeError) as e:
    raise Fail(f'cannot read {board} from {config}: {e}')
  form = FLASHER_ARGS.get(name)
  if form is None:
    raise Fail(f'{board}: flasher {name!r} has no HIL flash target (jlink, stlink or esptool)')
  m = re.fullmatch(form, fargs)
  if not m or not re.fullmatch(r'[\w-]+', uid):
    raise Fail(f'{board}: flasher args {fargs!r} or uid {uid!r} is not the roster form')
  flasher = {'name': name, 'uid': uid, 'device': m[1]}
  defines = {'jlink': [f'JLINK_OPTION=-USB {uid} -ExitOnError 1 -NoGui 1'], 'stlink': [f'STLINK_SERIAL={uid}']}
  return flasher, defines.get(name, [])


def roster_routes(config, board):
  """The board's further install routes (tinyuf2.routes), each {name, uid, device} as a record binds it."""
  try:
    entry = next(b for b in json.loads((ROOT / config).read_text())['boards'] if b['name'] == board)
    routes = [(r['flasher']['name'], r['flasher']['uid'], r['flasher']['args'])
              for r in (entry.get('tinyuf2') or {}).get('routes', [])]
  except (OSError, ValueError, KeyError, TypeError, StopIteration, AttributeError) as e:
    raise Fail(f'cannot read {board}\'s routes from {config}: {e}')
  out = []
  for name, uid, fargs in routes:
    m = re.fullmatch(ROUTE_ARGS.get(name, r'(?!)'), fargs) if isinstance(fargs, str) else None
    if not m or not isinstance(uid, str) or not re.fullmatch(r'[\w.:+-]+', uid):
      raise Fail(f'{board}: route {name!r} args {fargs!r} or uid {uid!r} is not the roster form')
    out.append({'name': name, 'uid': uid, 'device': m[1]})
  return out


def flash_routes(rec, routes):
  """A passing IDF build's further routes, each bound to the files its esptool binding hashed: the segments
  openocd_esp programs as they are, without esptool's header rewrite."""
  fl = rec.get('flash') or {}
  for r in routes:
    if (fl.get('flasher') or {}).get('name') != 'esptool' or fl['flasher']['device'] != r['device']:
      raise Fail(f'{rec["board"]}: route {r["name"]} for {r["device"]} needs the esptool binding of that chip')
  return {r['name']: {'flasher': r, 'inputs': list(fl['inputs'])} for r in routes}


def flash_binding(flasher, root, ninja):
  """The generated flash target's own command, checked token for token against the roster flasher: the probe,
  device and image it names, not CMakeCache, which need not hold JLINK_DEVICE. `ninja(dir, args)` runs ninja in the
  build's environment."""
  target, inputs = FLASH[flasher['name']]
  r = ninja(root, ['-t', 'commands', target])
  tool = {'jlink': 'JLinkExe', 'stlink': 'STM32_Programmer_CLI'}.get(flasher['name'], 'run_serial_tool.cmake')
  cmds = [l for l in r.stdout.splitlines() if tool in l] if r.returncode == 0 else []
  ok = len(cmds) == 1
  if ok and flasher['name'] == 'jlink':
    cd, _, cmd = cmds[0].partition(' && ')
    argv = shlex.split(cmd)
    ok = cd == f'cd {root}' and Path(argv[0]).name == 'JLinkExe' and argv[1:] == [
      '-device', flasher['device'], '-USB', flasher['uid'], '-ExitOnError', '1', '-NoGui', '1', '-if', 'swd',
      '-JTAGConf', '-1,-1', '-speed', 'auto', '-CommandFile', str(root / inputs[0])] and \
      (root / inputs[0]).is_file() and (root / inputs[0]).read_text() == f'halt\nloadfile {root / inputs[1]}\nr\ngo\nexit'
  elif ok and flasher['name'] == 'stlink':
    # the device is the roster's to name: the CLI identifies the chip itself, which the runner checks every session
    cd, _, cmd = cmds[0].partition(' && ')
    argv = shlex.split(cmd)
    ok = cd == f'cd {root}' and Path(argv[0]).name == 'STM32_Programmer_CLI' and argv[1:] == [
      '--connect', 'port=swd', f'sn={flasher["uid"]}', '--write', str(root / inputs[0]), '--go']
  elif ok:
    argv = shlex.split(cmds[0].partition(' && ')[2])
    defs = dict(v.split('=', 1) for k, v in zip(argv[1:-2], argv[2:-2]) if k == '-D' and '=' in v)
    tool_argv = defs.get('SERIAL_TOOL', '').split(';')
    ok = len(argv) == 1 + 2 * len(defs) + 2 and argv[-2] == '-P' and Path(argv[-1]).name == 'run_serial_tool.cmake' and \
      defs.keys() == {'IDF_PATH', 'SERIAL_TOOL', 'SERIAL_TOOL_ARGS', 'SERIAL_TOOL_IS_WRITE_FLASH',
                      'SERIAL_TOOL_FLASH_ARGS_FILE', 'WORKING_DIRECTORY'} and \
      tool_argv[1:] == ['-m', 'esptool', '--chip', flasher['device']] and \
      defs['SERIAL_TOOL_ARGS'].split(';') == ['--before=default-reset', '--after=hard-reset', 'write-flash', '@flash_args'] and \
      defs['SERIAL_TOOL_IS_WRITE_FLASH'] == '1' and defs['SERIAL_TOOL_FLASH_ARGS_FILE'] == 'flash_args' and \
      defs['WORKING_DIRECTORY'] == str(root)
    # flash_args: one settings line, then "<offset> <file>" per segment
    segs = (root / 'flash_args').read_text().splitlines()[1:] if (root / 'flash_args').is_file() else []
    ok = ok and sorted(l.split()[1] for l in segs if l.strip()) == sorted(inputs[1:])
  if not ok:
    raise Fail(f'{root.name}: target {target} does not flash {flasher} with the build\'s image: '
               f'{cmds if cmds else (r.stderr or r.stdout).strip()[-200:]}')
  return {'target': target, 'flasher': flasher, 'command': cmds[0], 'inputs': list(inputs)}


def build_lock_file(root):
  return root.with_name(root.name + '.lock')


@contextlib.contextmanager
def build_lock(root, wait=True):
  """Excludes a rebuild of a shared build dir while another build or a HIL flash uses it; without `wait`, a held
  lock raises BlockingIOError."""
  root.parent.mkdir(parents=True, exist_ok=True)
  with open(build_lock_file(root), 'a') as f:
    fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    yield


def build_board(board, backend, args, idf, flasher=None):
  port = port_of(board)
  # a board built with another backend than its port's (codeql's make) gets its own root
  name = board if backend == backend_of(port) else f'{board}-{backend}'
  root = BUILD_DIR / (f'cmake-build-{name}' if args.shared else f'cmake-build-agent-{os.getpid()}-{name}')
  rec = {'board': board, 'port': port, 'backend': backend, 'buildDir': str(root.relative_to(ROOT)),
         'status': 'ok', 'firstError': '', 'artifacts': []}
  if port in UNBUILT:
    rec['note'] = f'ports/{port}: {UNBUILT[port][1]}'
  if backend == 'make' and port in NO_SELF_UPDATE or backend == 'cmake' and \
     'update-tinyuf2.uf2' not in {p.name for p in expected_artifacts(port, board, backend, root)}:
    rec['notImplemented'] = ['self-update']
  problem = check_tools(port, backend, args.idf) or check_deps(port)
  if backend == 'idf' and args.idf == 'docker' and not problem:
    if subprocess.run(['docker', 'image', 'inspect', idf['image']], capture_output=True).returncode:
      problem = f'docker image {idf["image"]} missing: docker pull {idf["image"]}'
  if problem:
    rec.update(status='error', firstError=problem)
    return rec
  with build_lock(root) if args.shared else contextlib.nullcontext():
    return build_root(board, port, backend, root, rec, args, idf, flasher)


def build_root(board, port, backend, root, rec, args, idf, flasher):
  defines = args.define
  if flasher:
    flasher, extra = flasher
    defines = defines + extra
  # always from clean: make cannot see a changed define or flag, so a reused root could pass stale firmware
  shutil.rmtree(root, ignore_errors=True)
  root.mkdir(parents=True)
  log = root / 'check_build.log'
  try:
    if backend == 'make':
      ok, apps = build_make(port, board, root, defines, log, args.verbose, rec)
    elif backend == 'cmake':
      ok, apps = build_cmake(port, board, root, defines, log, args.verbose)
    else:
      ok, apps = build_idf(board, root, defines, log, args.verbose, args.idf, idf['image'])
  except OSError as e:
    rec.update(status='error', firstError=f'{type(e).__name__}: {e}', log=str(log.relative_to(ROOT)))
    return rec
  if not ok:
    rec.update(status='failed', firstError=first_error(log.read_text(errors='replace')), log=str(log.relative_to(ROOT)))
    return rec
  missing = [p for p in expected_artifacts(port, board, backend, root) if not p.is_file()]
  if backend == 'idf':
    missing += [root / c for c in IDF_CONFIG if not (root / c).is_file()]
  missing += [a for a in apps if not list(a.glob('*.elf'))]
  if missing:
    rec.update(status='failed', log=str(log.relative_to(ROOT)), firstError='missing expected artifact(s): ' +
               ', '.join(str(p.relative_to(root)) for p in missing))
    return rec
  rec['artifacts'] = sorted(str(p.relative_to(root)) for p in (root / '_bin').rglob('*') if p.is_file())
  rec['artifacts'] += sorted(str(e.relative_to(root)) for a in apps for e in a.glob('*.elf'))
  if backend == 'idf':
    rec['artifacts'] += list(IDF_CONFIG)
  if flasher:
    try:
      rec['flash'] = flash_binding(flasher, root, functools.partial(ninja_in, backend, args.idf, idf.get('image')))
    except (Fail, OSError) as e:
      rec.update(status='failed', firstError=str(e), log=str(log.relative_to(ROOT)))
      return rec
    rec['flash']['defines'] = extra
    rec['artifacts'] += [a for a in rec['flash']['inputs'] if a not in rec['artifacts']]
  if args.shared:
    rec['sha256'] = {a: hashlib.sha256((root / a).read_bytes()).hexdigest() for a in rec['artifacts']}
  else:
    shutil.rmtree(root)
    rec['removed'] = True
  return rec


def keep_only_log(root, log):
  for p in root.iterdir():
    if p != log:
      shutil.rmtree(p) if p.is_dir() else p.unlink()


def run_ghostfat(verbose):
  """Build and run the native self-test (its CMake `selftest` target) of every ports/test_ghostfat config,
  one at a time: the `huge` image is about 1.5 GiB, twice over with its known-good copy."""
  missing = [t for t in ('cmake', 'ninja', 'gcc', 'gzip') if not shutil.which(t)]
  if missing:
    return [{'config': cfg, 'status': 'error', 'firstError': f'{", ".join(missing)} not on PATH'}
            for cfg in boards_of(GHOSTFAT)]
  results = []
  for cfg in boards_of(GHOSTFAT):
    root = BUILD_DIR / f'cmake-build-agent-{os.getpid()}-ghostfat-{cfg}'
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    log = root / 'check_build.log'
    rec = {'config': cfg, 'status': 'ok', 'firstError': ''}
    try:
      if run(['cmake', '-B', root, '-G', 'Ninja', f'-DBOARD={cfg}', ports_dir(GHOSTFAT)], log, verbose) or \
         run(['cmake', '--build', root, '--target', 'selftest'], log, verbose):
        out = log.read_text(errors='replace')
        rec.update(status='failed', firstError=(re.findall(r'^FAIL.*$', out, re.M) or [first_error(out)])[-1])
    except OSError as e:
      rec.update(status='error', firstError=f'{type(e).__name__}: {e}')
    finally:
      if rec['status'] == 'ok':
        shutil.rmtree(root, ignore_errors=True)
      else:
        keep_only_log(root, log)
        rec['log'] = str(log.relative_to(ROOT))
    results.append(rec)
  return results


def run_tests():
  """The .claude script tests, for a change to how boards build or to the HIL contract."""
  r = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', '.claude/test', '-p', 'test_*.py'],
                     capture_output=True, text=True, cwd=ROOT)
  last = [l for l in r.stderr.splitlines() if l.strip()]
  return {'status': 'ok' if r.returncode == 0 else 'failed', 'summary': last[-1] if last else '',
          'firstError': '' if r.returncode == 0 else unittest_first_error(r.stderr)}


def unittest_first_error(log):
  """The first failed test's id (without the docstring line unittest may print under it) and its exception's first
  line: the first unindented line after the last traceback header, since an assertion's message (a diff) or a chained
  exception may follow or precede it."""
  failure = re.search(r'^={70}\n((?:FAIL|ERROR): [^\n]+)\n(?:[^\n]*\n)?-{70}\n(.*?)(?=^={70}\n|^-{70}\nRan \d+ test)',
                      log, re.M | re.S)
  if not failure:
    return first_error(log)
  frames = failure.group(2).split('Traceback (most recent call last):\n')[-1].splitlines()
  exc = next((line for line in frames if line.strip() and not line[0].isspace()), '')
  return (failure.group(1) + (f': {exc}' if exc else ''))[:400]


class Parser(argparse.ArgumentParser):
  def error(self, message):
    print(json.dumps({'pass': False, 'error': f'usage: {message}'}))
    sys.exit(2)


def main(argv=None):
  ap = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  src = ap.add_mutually_exclusive_group(required=True)
  src.add_argument('--scope', nargs='+', metavar='PATH', help='changed paths or directories')
  src.add_argument('--base', metavar='REF', help='the branch diff against REF')
  src.add_argument('--board', action='append', metavar='B', help='build named boards (repeatable)')
  src.add_argument('--diff-file', metavar='FILE', help='changed paths, one per line (--select-only)')
  ap.add_argument('--worktree', action='store_true', help='with --base: add uncommitted and untracked files')
  ap.add_argument('--select-only', action='store_true', help='print the selection manifest and stop')
  ap.add_argument('--hil-config', metavar='ROSTER', help="the host's HIL roster: with --select-only adds `hil`; with --board --shared binds the flash target (a HIL record)")
  ap.add_argument('-D', '--define', action='append', default=[], metavar='VAR=VAL',
                  help="passed to the board's backend: make VAR=VAL, cmake/idf -DVAR=VAL")
  ap.add_argument('--shared', action='store_true', help='build into cmake-build/cmake-build-<board> and keep it')
  ap.add_argument('--backend', choices=('cmake',),
                  help="with --board and --shared: build with cmake whatever CI uses (the HIL's receipt)")
  ap.add_argument('--idf', choices=('docker', 'local'), default='docker',
                  help="ESP-IDF: CI's pinned docker image (default) or the exported local IDF")
  ap.add_argument('-v', '--verbose', action='store_true', help='stream build output to stderr')
  args = ap.parse_args(argv)
  if args.worktree and not args.base:
    ap.error('--worktree needs --base')
  if args.diff_file and not args.select_only:
    ap.error('--diff-file is for --select-only')
  if args.hil_config and not (args.select_only or (args.board and args.shared)):
    ap.error('--hil-config is for --select-only, or a HIL record with --board and --shared')
  if args.hil_config and args.board and any(d.split('=', 1)[0].split(':', 1)[0] in SELECTION for d in args.define):
    ap.error(f'a HIL record takes {", ".join(SELECTION)} from the roster, not -D')
  if args.backend and not (args.board and args.shared):
    ap.error('--backend needs --board and --shared')
  if args.select_only and args.board:
    ap.error('--select-only takes --scope, --base or --diff-file')

  result = {'pass': False}
  try:
    if args.board:
      boards = {}
      for b in args.board:
        port = port_of(b)
        backend = args.backend or backend_of(port)
        if not backend:
          raise Fail(f'ports/{port}: {UNBUILT[port][1]}')
        if backend == 'cmake' and (backend_of(port) == 'idf' or not (ports_dir(port) / 'CMakeLists.txt').is_file()):
          raise Fail(f'ports/{port} has no cmake build')
        boards[(b, backend)] = 'named'
      sel = {'full': False, 'boards': boards, 'ghostfat': False, 'tests': False, 'records': []}
      info = {'mode': 'boards'}
    else:
      paths, info = changed_paths(args.base, args.worktree, args.scope, args.diff_file)
      sel = select(paths)
    if args.select_only:
      print(json.dumps(manifest(sel, info, args.hil_config)))
      return 0
    ports = {port_of(b) for b, _ in sel['boards']}
    info.update(identity(ports))
    result['input'] = info
    idf = {}
    if any(backend == 'idf' for _, backend in sel['boards']):
      ci = ci_idf_version()
      idf = {'mode': args.idf, 'ciVersion': ci, 'image': f'espressif/idf:{ci}'}
      if args.idf == 'local' and shutil.which('idf.py'):
        v = subprocess.run(['idf.py', '--version'], capture_output=True, text=True)
        idf['version'] = (v.stdout or v.stderr).strip()
        idf['matchesCi'] = ci in idf['version']
    flashers = {b: roster_flasher(args.hil_config, b) for b, _ in sel['boards']} if args.hil_config else {}
    routes = {b: roster_routes(args.hil_config, b) for b, _ in sel['boards']} if args.hil_config else {}
    records = [build_board(b, backend, args, idf, flashers.get(b)) for (b, backend) in sel['boards']]
    for r in records:
      if routes.get(r['board']) and r['status'] == 'ok':
        r['flashRoutes'] = flash_routes(r, routes[r['board']])
    for r in records:
      r['selectedBy'] = sel['boards'][(r['board'], r['backend'])]
    # an input that moved while building, even if restored before the HIL checks it, leaves firmware
    # the record cannot vouch for; hil_test.py refuses any entry here
    now = identity(ports)
    info['inputsDirtiedByBuild'] = sorted((set(now['dirtyInputs']) - set(info['dirtyInputs'])) | moved_inputs(info, now))
    ghostfat = run_ghostfat(args.verbose) if sel['ghostfat'] else []
    tests = run_tests() if sel['tests'] else None
    nothing = path_view(sel['records'], 'none', ('path', 'reason'))
    uncovered = path_view(sel['records'], 'gap', ('path', 'reason'))
    checks = records + ghostfat + ([tests] if tests else [])
    statuses = [c['status'] for c in checks]
    code = 2 if 'error' in statuses else 1 if 'failed' in statuses else 3 if uncovered else 0
    result.update({
      'pass': code == 0,
      'boards': records,
      'ghostfat': ghostfat,
      'built': [f"{r['buildDir']}/{a}" for r in records if not r.get('removed') for a in r['artifacts']],
      'resolution': 'full' if sel['full'] else 'boards' if args.board else 'selected',
      'defines': args.define,
      'paths': path_view(sel['records']),
      'nothingToBuild': nothing,
      'uncovered': uncovered,
    })
    if tests:
      result['tests'] = tests
    if idf:
      result['idf'] = idf
    first = next((c['firstError'] for c in checks if c['status'] != 'ok'), '')
    if first:
      result['firstError'] = first
    print(json.dumps(result))
    return code
  except (Fail, OSError) as e:
    result['error'] = str(e)
    print(json.dumps(result))
    return 2


if __name__ == '__main__':
  sys.exit(main())
