#!/usr/bin/env python3
"""TinyUF2 HIL battery and the probe operations debug sessions share with it.

  hil_test.py run -b BOARD --build-record FILE CONFIG [--fail-at STEP] [--try-reentry METHOD]
  hil_test.py install -b BOARD --firmware BIN --sha256 HASH --under-hold REASON CONFIG
  hil_test.py restore -b BOARD (--under-hold REASON | --recover-holder PID --report FILE) CONFIG

The last stdout line is JSON. Exit 0 every board passed and was restored, 1 a board failed or did not
run (restored or never touched), 2 refused before any hardware access, 4 cleanup failed (the board is
held when `restored.heldAfter`; not under HIL_NO_BOARD_LOCK) or a manual operation left `survivors`.
SKILL.md beside this script is the contract; this file is its mechanics.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'build' / 'scripts'))
sys.dont_write_bytecode = True   # nothing the runner imports may write into a checkout it binds
import check_build as cb  # noqa: E402

# [floor, ceiling) the runner ever programs, per J-Link device, independent of roster and source:
# LPC55S69 PFR starts at 0x9DE00 and a bad CMPA write can lock the part (UM11126 Table 173, Table 1064);
# 0x9D800-0x9DDFF is reserved and undocumented. MIMXRT1062: FlexSPI XIP at 0x60000000 (IMXRT1060RM
# Table 3-1) holding the EVK's 8 MiB IS25WP064A (EVK hardware user's guide 2.7).
FLASH_LIMITS = {'LPC55S69_M33_0': (0, 0x9D800), 'MIMXRT1062xxx6A': (0x60000000, 0x60800000)}
STEPS = ('identity', 'install', 'dfu', 'copy', 'app-ran', 'reenter')
REENTRY = ('retained-register', 'app-invalidate')
PROTECTED = {'hil_test.py', 'pool_check'}   # tinyusb hil_lock.PROTECTED_REASONS, checked at load
HOLDER_ROLE = 'cleanup-holder'
SCB_VTOR, SCB_AIRCR, SCB_CPUID, DHCSR = 0xE000ED08, 0xE000ED0C, 0xE000ED00, 0xE000EDF0
AIRCR_SYSRESETREQ = 0x05FA0004
UF2_MAGIC = (0x0A324655, 0x9E5D5157, 0x0AB16F30)
UF2_FLAG_FAMILY = 0x2000
PROBE_TIMEOUT, USB_TIMEOUT, QUIET_TIME, KILL_WAIT, UDEV_TIMEOUT = 120, 20, 3, 5, 5
JLINK_RETRY_DELAY = 2
UDEV_RULES = ('/etc/udev/rules.d', '/run/udev/rules.d')
# J-Link notes that are not failures, per device, each with the line that shows the operation completed
# (bench: every MIMXRT1062 reset with an invalid app vector, then the reset halts as usual)
BENIGN = {'MIMXRT1062xxx6A': r'(?m)^Could not find valid reset vector\.\nTarget halted on flash header read\.$'}


class Refused(Exception):
  """Exit 2: nothing on the board was touched."""


class StepFail(Exception):
  def __init__(self, msg, evidence=None):
    super().__init__(msg)
    self.evidence = evidence or {}


class Interrupted(Exception):
  pass


# ------------------------------------------------------------------ roster and source facts

def hexint(v):
  try:
    return int(v, 16) if isinstance(v, str) else None
  except ValueError:
    return None


def rng(v, what):
  if not (isinstance(v, list) and len(v) == 2):
    raise Refused(f'roster: {what} must be [start, end]')
  lo, hi = (hexint(x) for x in v)
  if lo is None or hi is None or not lo < hi:
    raise Refused(f'roster: {what} must be [start, end] hex strings with start < end')
  return lo, hi


def load_board(config, name):
  try:
    cfg = json.loads(Path(config).read_text())
    boards = [b for b in cfg['boards'] if b.get('name') == name]
  except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
    raise Refused(f'cannot read {config}: {e}')
  if len(boards) != 1:
    raise Refused(f'{config} has {len(boards)} entries named {name!r}')
  b = boards[0]
  host = cfg.get('host')
  if not isinstance(host, str) or not host:
    raise Refused(f'{config}: "host" (the hostname this roster describes) is required')
  helper = (cfg.get('lock') or {}).get('helper')
  if not (isinstance(helper, str) and os.path.isabs(helper)):
    raise Refused(f'{config}: lock.helper must be the absolute path of tinyusb hil_lock.py')
  fl, t = b.get('flasher') or {}, b.get('tinyuf2') or {}
  m = re.fullmatch(r'-device (\S+)', fl.get('args') or '')
  if fl.get('name') != 'jlink' or not isinstance(fl.get('uid'), str) or not m:
    raise Refused(f'{name}: flasher must be jlink with a string uid and args exactly "-device NAME"')
  if not isinstance(b.get('uid'), str) or not b['uid']:
    raise Refused(f'{name}: uid (the bootloader USB serial) is required')
  jl = t.get('jlink') or {}
  if not (isinstance(jl.get('if'), str) and isinstance(jl.get('speed'), str)):
    raise Refused(f'{name}: tinyuf2.jlink needs explicit "if" and "speed"')
  src = t.get('board', name)
  if not (isinstance(src, str) and re.fullmatch(r'[\w.-]+', src)):
    raise Refused(f'{name}: tinyuf2.board must be the TinyUF2 board name')
  lay, rest = t.get('layout') or {}, t.get('restore') or {}
  board = {
    'name': name, 'src': src, 'host': host, 'uid': b['uid'], 'probe': fl['uid'], 'device': m.group(1),
    'if': jl['if'], 'speed': jl['speed'], 'port': t.get('port'), 'helper': helper,
    'install': rng(lay.get('install'), 'layout.install'), 'app': rng(lay.get('app'), 'layout.app'),
    'page': lay.get('pageSize'), 'reentry': t.get('reentry'),
    'restore': {'bin': rest.get('bin'), 'sha256': rest.get('sha256'), 'version': rest.get('version'),
                'install': rng((rest.get('layout') or {}).get('install'), 'restore.layout.install'),
                'appStart': hexint((rest.get('layout') or {}).get('appStart'))},
  }
  if board['device'] not in FLASH_LIMITS:
    raise Refused(f'{name}: no programming limits known for J-Link device {board["device"]}')
  if not isinstance(board['page'], int) or board['page'] <= 0:
    raise Refused(f'{name}: tinyuf2.layout.pageSize must be a positive integer')
  r = board['restore']
  if not (isinstance(r['bin'], str) and isinstance(r['sha256'], str) and isinstance(r['version'], str)
          and r['appStart'] is not None):
    raise Refused(f'{name}: tinyuf2.restore needs bin (a bootloader image based at its install start), sha256, '
                  'version and layout')
  floor, ceiling = FLASH_LIMITS[board['device']]
  for what, (lo, hi) in (('install', board['install']), ('app', board['app']), ('restore.install', r['install'])):
    if lo < floor or hi > ceiling:
      raise Refused(f'{name}: layout.{what} [{lo:#x}, {hi:#x}) leaves the {board["device"]} flash '
                    f'[{floor:#x}, {ceiling:#x})')
  return board


def define(path, name):
  m = re.search(rf'^\s*#\s*define\s+{name}\s+(.+?)\s*(//.*|/\*.*)?$', (ROOT / path).read_text(), re.M)
  if not m:
    raise Refused(f'{path}: no #define {name}')
  return m.group(1)


LITERAL = r'(0x[0-9a-fA-F]+|\d+)[uUlL]*'


def num(expr, what):
  m = re.fullmatch(rf'\(?\s*{LITERAL}\s*\)?', expr)
  if not m:
    raise Refused(f'{what}: {expr!r} is not a literal')
  return int(m.group(1), 0)


def product(expr, what):
  """A literal or a product of literals, e.g. (8*1024*1024); nothing else."""
  inner = expr.strip()
  if inner.startswith('(') and inner.endswith(')'):
    inner = inner[1:-1]
  terms = inner.split('*')
  if not all(re.fullmatch(rf'\s*{LITERAL}\s*', t) for t in terms):
    raise Refused(f'{what}: {expr!r} is not a literal or a product of literals')
  v = 1
  for t in terms:
    v *= num(t, what)
  return v


def flash_addr(expr, flash_base, what):
  """A literal, or FLASH_BASE + literal where the port defines FLASH_BASE; nothing else."""
  m = re.fullmatch(rf'\(?\s*FLASH_BASE\s*\+\s*{LITERAL}\s*\)?', expr)
  if not m:
    return num(expr, what)
  if flash_base is None:
    raise Refused(f'{what}: {expr!r} uses FLASH_BASE, which this port does not define')
  return flash_base + int(m.group(1), 0)


def make_var(path, name):
  m = re.search(rf'^\s*{name}\s*[:?]?=\s*(\S+)', (ROOT / path).read_text(), re.M)
  if not m:
    raise Refused(f'{path}: no {name}')
  return m.group(1)


def port_sources(port, bdir):
  """(CMSIS device header, the SDK's flash linker script, FLASH_BASE or None) of a port the HIL supports."""
  sdk = make_var(f'ports/{port}/port.mk', 'SDK_DIR')
  mcu = make_var(f'{bdir}/board.mk', 'MCU')
  if port == 'lpc55':
    core = make_var(f'{bdir}/board.mk', 'MCU_CORE').replace('$(MCU)', mcu)
    return f'{sdk}/devices/{mcu}/{core}.h', f'{sdk}/devices/{mcu}/gcc/{core}_flash.ld', None
  if port == 'mimxrt10xx':
    ld = f'ports/{port}/linker/{mcu}_ram.ld'   # where ports/mimxrt10xx/Makefile takes FLASH_BASE from
    m = re.search(r'^\s*_flash_base\s*=\s*(0x[0-9a-fA-F]+)\s*;', (ROOT / ld).read_text(), re.M)
    if not m:
      raise Refused(f'{ld}: no _flash_base')
    return f'{sdk}/devices/{mcu}/{mcu}.h', f'{sdk}/devices/{mcu}/gcc/{mcu}xxxxx_flexspi_nor.ld', int(m.group(1), 16)
  raise Refused(f'ports/{port}: the HIL runner has no source facts for this port')


def source_facts(board):
  """What the candidate's source says about this board; the roster layout must agree with it."""
  port = board['port']
  bdir = f'ports/{port}/boards/{board["src"]}'
  if not (ROOT / bdir).is_dir():
    raise Refused(f'{bdir} does not exist')
  header, ld, flash_base = port_sources(port, bdir)
  if re.search(r'^\s*#\s*define\s+BOARD_FLASH_APP_START\b', (ROOT / f'{bdir}/board.h').read_text(), re.M):
    raise Refused(f'{bdir}/board.h overrides BOARD_FLASH_APP_START; the runner reads the port default only')
  facts = {
    'flashBase': flash_base or 0,
    'appStart': flash_addr(define(f'ports/{port}/boards.h', 'BOARD_FLASH_APP_START'), flash_base,
                           'BOARD_FLASH_APP_START'),
    'flashSize': product(define(f'{bdir}/board.h', 'BOARD_FLASH_SIZE'), 'BOARD_FLASH_SIZE'),
    'vid': num(define(f'{bdir}/board.h', 'USB_VID'), 'USB_VID'),
    'pid': num(define(f'{bdir}/board.h', 'USB_PID'), 'USB_PID'),
    'boardId': define(f'{bdir}/board.h', 'UF2_BOARD_ID').strip('"'),
    'family': int(make_var(f'ports/{port}/port.mk', 'UF2_FAMILY_ID'), 16),
    'vectors': num(define(header, 'NUMBER_OF_INT_VECTORS'), 'NUMBER_OF_INT_VECTORS'),
    'ram': ram_origin(ld),
    'dblTapDelayMs': num(define('src/board_api.h', 'TINYUF2_DBL_TAP_DELAY'), 'TINYUF2_DBL_TAP_DELAY'),
  }
  reg = define(f'ports/{port}/boards.h', 'TINYUF2_DBL_TAP_REG')
  m = re.fullmatch(r'(\w+)->(\w+)\[(\d+)\]', reg)
  if not m:
    raise Refused(f'TINYUF2_DBL_TAP_REG {reg!r} is not PERIPH->ARRAY[N]')
  base, offset, step = register_layout(header, m.group(1), m.group(2))
  facts['dblTapReg'] = base + offset + step * int(m.group(3))
  facts['dblTapMagic'] = 0xf01669ef   # board_api.h DBL_TAP_MAGIC at TINYUF2_DBL_TAP_REG_SIZE 32
  if 'TINYUF2_DBL_TAP_REG_SIZE' in (ROOT / f'ports/{port}/boards.h').read_text():
    raise Refused(f'ports/{port} overrides TINYUF2_DBL_TAP_REG_SIZE: the magic would need its shift')
  return facts


def ram_origin(ld):
  m = re.search(r'm_data\s*\(RW\)\s*:\s*ORIGIN\s*=\s*(0x[0-9a-fA-F]+)', (ROOT / ld).read_text())
  if not m:
    raise Refused(f'{ld}: no m_data ORIGIN')
  return int(m.group(1), 16)


def register_layout(header, periph, member):
  """(base, array offset, array step) of PERIPH->MEMBER[] from the CMSIS device header; on a TrustZone
  part the base is the non-secure alias, the one a build without -mcmse (tinyuf2's) uses."""
  text = (ROOT / header).read_text()
  end = re.search(r'\}\s*' + periph + r'_Type;', text)
  start = text.rfind('typedef struct {', 0, end.start()) if end else -1
  if start < 0:
    raise Refused(f'{header}: no {periph}_Type')
  f = re.search(rf'\b{member}\[\d+\];.*?array offset:\s*(0x[0-9a-fA-F]+), array step:\s*(0x[0-9a-fA-F]+)',
                text[start:end.start()])
  if not f:
    raise Refused(f'{header}: no {periph}->{member} array offset')
  bases = re.findall(rf'#define {periph}_BASE\s+\((0x[0-9a-fA-F]+)u\)', text)
  if len(bases) not in (1, 2):
    raise Refused(f'{header}: expected one {periph}_BASE, or a secure and a non-secure one, found {bases}')
  return int(bases[-1], 16), int(f.group(1), 16), int(f.group(2), 16)


def check_layout(board, facts):
  install, app = board['install'], board['app']
  base, start = facts['flashBase'], facts['appStart']
  if install != (base, start) or app != (start, base + facts['flashSize']):
    raise Refused(f'{board["name"]}: roster layout install={install} app={app} disagrees with the source '
                  f'(app start {facts["appStart"]:#x}, flash size {facts["flashSize"]:#x})')
  if facts['appStart'] % board['page']:
    raise Refused(f'{board["name"]}: app start {facts["appStart"]:#x} is not page aligned')


# ------------------------------------------------------------------ images

def parse_hex(path):
  """{address: bytes} of an Intel HEX file, contiguous runs merged; checksums verified."""
  data, base = {}, 0
  for n, line in enumerate(Path(path).read_text().splitlines(), 1):
    if not line.strip():
      continue
    try:
      rec = bytes.fromhex(line.strip()[1:])
    except ValueError:
      raise Refused(f'{path}:{n}: not Intel HEX')
    if line[0] != ':' or len(rec) < 5 or len(rec) != rec[0] + 5 or sum(rec) & 0xFF:
      raise Refused(f'{path}:{n}: bad Intel HEX record')
    addr, kind, payload = int.from_bytes(rec[1:3], 'big'), rec[3], rec[4:-1]
    if kind == 0:
      for i, b in enumerate(payload):
        data[base + addr + i] = b
    elif kind == 1:
      break
    elif kind == 2:
      base = int.from_bytes(payload, 'big') << 4
    elif kind == 4:
      base = int.from_bytes(payload, 'big') << 16
    elif kind not in (3, 5):
      raise Refused(f'{path}:{n}: unknown record type {kind}')
  return data


def check_ranges(data, allowed, limits, what):
  if not data:
    raise Refused(f'{what}: no data')
  lo, hi = min(data), max(data) + 1
  if lo < limits[0] or hi > limits[1]:
    raise Refused(f'{what}: data [{lo:#x}, {hi:#x}) leaves the flash limits [{limits[0]:#x}, {limits[1]:#x})')
  for a in (lo, hi - 1):
    if not any(s <= a < e for s, e in allowed):
      raise Refused(f'{what}: address {a:#x} is outside {[(hex(s), hex(e)) for s, e in allowed]}')
  bad = [a for a in data if not any(s <= a < e for s, e in allowed)]
  if bad:
    raise Refused(f'{what}: {len(bad)} bytes outside the allowed ranges, first at {min(bad):#x}')
  return lo, hi


def hex_matches_bin(data, bin_path, base):
  """Whether a bootloader BIN is its HEX laid out from `base`: the HEX fixes the base the BIN lacks. The
  BIN is what gets programmed, so gaps between sections are written and read back as the BIN holds them."""
  img = Path(bin_path).read_bytes()
  return min(data) == base and max(data) + 1 == base + len(img) and all(img[a - base] == b for a, b in data.items())


def embedded_version(bin_path):
  hits = re.findall(rb'TinyUF2 Bootloader ([^\r\n\x00]+)\r\n', Path(bin_path).read_bytes())
  if len(hits) != 1:
    raise Refused(f'{bin_path}: expected one "TinyUF2 Bootloader <version>" string, found {len(hits)}')
  return hits[0].decode()


def fixture(facts, nonce):
  """A Cortex-M image the probe can prove ran: every vector but SP and reset traps in a fault loop,
  the reset handler counts in r0 forever, and a nonce pattern makes an older run's image fail."""
  start = facts['appStart']
  table = 128
  while table < facts['vectors'] * 4:
    table *= 2
  handler, fault = start + table, start + table + 4
  vectors = [facts['ram'] + 0x1000, handler | 1] + [fault | 1] * (table // 4 - 2)
  code = struct.pack('<HHH', 0x3001, 0xE7FD, 0xE7FE)   # adds r0,#1 ; b handler ; b . (fault)
  pattern = b''.join(hashlib.sha256(nonce + i.to_bytes(4, 'little')).digest() for i in range(512))   # 16 KiB
  img = struct.pack(f'<{len(vectors)}I', *vectors) + code
  img += b'\0' * (-len(img) % 4) + pattern
  return {'image': img, 'handler': handler, 'fault': fault, 'sp': vectors[0], 'table': table}


def parse_uf2(blob):
  if len(blob) % 512:
    raise ValueError(f'{len(blob)} bytes is not whole 512-byte blocks')
  blocks = []
  for off in range(0, len(blob), 512):
    m0, m1, flags, addr, size, no, total, family = struct.unpack_from('<8I', blob, off)
    end = struct.unpack_from('<I', blob, off + 508)[0]
    if (m0, m1, end) != UF2_MAGIC:
      raise ValueError(f'block {off // 512}: bad magic')
    blocks.append({'flags': flags, 'addr': addr, 'size': size, 'no': no, 'total': total, 'family': family,
                   'data': blob[off + 32:off + 32 + size]})
  return blocks


def make_uf2(img, base, family, workdir):
  src, out = workdir / 'app.bin', workdir / 'app.uf2'
  src.write_bytes(img)
  # a subprocess with -B, never an import: nothing may land in the lib/uf2 submodule
  r = subprocess.run([sys.executable, '-B', str(ROOT / 'lib/uf2/utils/uf2conv.py'), '-c', '-b', hex(base),
                      '-f', hex(family), '-o', str(out), str(src)], capture_output=True, text=True)
  if r.returncode:
    raise Refused(f'uf2conv failed: {r.stderr.strip() or r.stdout.strip()}')
  return src, out


# ------------------------------------------------------------------ processes

CHILDREN = []


def spawn(cmd, log, timeout, cwd=None):
  """Run a child in its own process group with a bound; a child that survives SIGKILL (D state on a
  stuck USB device) is left in CHILDREN for cleanup to see. Children spawned during cleanup inherit its
  blocked SIGTERM and SIGINT, so only SIGKILL (reap) may be relied on to end them."""
  with open(log, 'a') as f:
    f.write('$ ' + ' '.join(map(str, cmd)) + '\n')
    f.flush()
    p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         errors='replace', start_new_session=True, cwd=cwd)
    CHILDREN.append(p)
    try:
      out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
      reap(p)
      raise StepFail(f'{Path(str(cmd[0])).name} timed out after {timeout}s')
    f.write(out)
    CHILDREN.remove(p)
    return p.returncode, out


def reap(p):
  try:
    os.killpg(p.pid, signal.SIGKILL)
  except ProcessLookupError:
    pass
  try:
    p.wait(KILL_WAIT)
  except subprocess.TimeoutExpired:
    return False
  if p in CHILDREN:
    CHILDREN.remove(p)
  return True


def proc_start(pid):
  """The start time of `pid` in clock ticks (proc(5) stat field 22), which tells a reused pid apart."""
  try:
    return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19])
  except (OSError, IndexError, ValueError):
    return None


def stuck_children():
  """Children that survived SIGKILL, identified so a later recovery can tell they are still alive."""
  return [{'pid': p.pid, 'start': proc_start(p.pid), 'cmd': [str(c) for c in p.args][:3]}
          for p in list(CHILDREN) if not reap(p)]


def still_alive(survivors):
  return [s for s in survivors if s.get('start') is not None and proc_start(s['pid']) == s['start']]


# ------------------------------------------------------------------ probe

def died_at_probe_connect(code, out, probe):
  """libjlinkarm's crash at the probe connect (SKILL.md, Limits): SIGSEGV or SIGABRT with this probe's
  serial as the last J-Link line, before any target connect, so the session changed nothing and may run again.
  Any other death leaves the target's state unknown."""
  lines = [x.strip() for x in out.splitlines() if x.strip() and not re.match(r'(double free|free\(\)|malloc|corrupted )', x)]
  last = re.fullmatch(r'S/N: (\d+)', lines[-1]) if lines else None
  return code in (-signal.SIGSEGV, -signal.SIGABRT) and bool(last) and int(last.group(1)) == int(probe) and \
    'Connecting to target' not in out


class Probe:
  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log
    self.retried = []

  def run(self, commands, judge=True):
    """One JLinkExe session. judge=False is for a command that resets the target, which may drop the
    connection mid-transaction: its exit is recorded, and the caller's observation is the evidence."""
    script = self.dir / f'jlink-{time.monotonic_ns()}.jlink'
    script.write_text('\n'.join(list(commands) + ['exit']) + '\n')
    cmd = ['JLinkExe', '-USB', self.b['probe'], '-device', self.b['device'], '-if', self.b['if'], '-speed',
           self.b['speed'], '-autoconnect', '1', '-NoGui', '1', '-ExitOnError', '1', '-CommandFile', script]
    code, out = spawn(cmd, self.log, PROBE_TIMEOUT)
    if died_at_probe_connect(code, out, self.b['probe']):
      self.retried.append({'exit': code, 'script': script.name})
      with open(self.log, 'a') as f:
        f.write(f'# JLinkExe died (exit {code}) at the probe connect, before the target; retrying once\n')
      time.sleep(JLINK_RETRY_DELAY)
      code, out = spawn(cmd, self.log, PROBE_TIMEOUT)
    judged = re.sub(BENIGN[self.b['device']], '', out) if self.b['device'] in BENIGN else out
    # a crash fails even a reset session (judge=False): its commands may not have run
    if code < 0 or judge and (code or re.search(r'Verify failed|Could not|Cannot connect|ERROR|ResetTarget failed|'
                                                r'Failed to halt|CPU is not halted', judged)):
      raise StepFail(f'JLinkExe failed (exit {code})', {'tail': out.strip().splitlines()[-5:]})
    return out

  def mem32(self, addrs):
    out = self.run([f'mem32 {a:08X} 1' for a in addrs])
    vals = dict((int(a, 16), int(v, 16)) for a, v in re.findall(r'^([0-9A-F]{8}) = ([0-9A-F]{8})', out, re.M))
    missing = [hex(a) for a in addrs if a not in vals]
    if missing:
      raise StepFail(f'mem32 read gave no value for {missing}')
    return vals

  def write32(self, addr, value):
    """Halt, write, read back, resume: J-Link reports a write as done even when the bus rejected it
    (a peripheral with its clock gated), so only the read-back proves it."""
    out = self.run(['h', f'w4 {addr:08X} {value:08X}', f'mem32 {addr:08X} 1', 'g'])
    m = re.search(rf'^{addr:08X} = ([0-9A-F]{{8}})', out, re.M)
    if not m or int(m.group(1), 16) != value:
      raise StepFail(f'{addr:#010x} reads back {m.group(1) if m else "nothing"}, not {value:#010x}')
    return hex(value)


def after(out, command):
  """The output chunks following each echo of `command` in a JLinkExe -CommandFile transcript; the
  transcript shape is bench-checked at commissioning."""
  return re.split(rf'(?m)^J-Link>{re.escape(command)}\s*$', out)[1:]


def regs(out):
  def one(pat):
    m = re.search(pat, out)
    if not m:
      raise StepFail(f'no {pat!r} in J-Link regs output')
    return int(m.group(1), 16)
  return {'pc': one(r'\bPC = ([0-9A-F]{8})'), 'r0': one(r'\bR0 = ([0-9A-F]{8})'),
          'msp': one(r'\bMSP= ([0-9A-F]{8})'), 'ipsr': one(r'\bIPSR = ([0-9A-F]{3})')}


# ------------------------------------------------------------------ USB mass storage

def usb_device(vid, pid, serial):
  hits = []
  for d in Path('/sys/bus/usb/devices').iterdir():
    try:
      if (int((d / 'idVendor').read_text(), 16), int((d / 'idProduct').read_text(), 16)) == (vid, pid) and \
         (d / 'serial').read_text().strip() == serial:
        hits.append(d.name)
    except OSError:
      continue
  if len(hits) > 1:
    raise StepFail(f'{len(hits)} USB devices with {vid:04x}:{pid:04x} serial {serial}: {hits}')
  return hits[0] if hits else None


def block_device(usb_path):
  for blk in Path('/sys/block').iterdir():
    if f'/{usb_path}:' in os.path.realpath(blk):
      return f'/dev/{blk.name}'
  return None


def wait_for(fn, timeout, what):
  end = time.monotonic() + timeout
  while time.monotonic() < end:
    v = fn()
    if v:
      return v
    time.sleep(0.2)
  raise StepFail(f'{what} not seen within {timeout}s')


def exclusion_configured(facts, serial):
  """A udev rule in exactly SKILL.md's form sets UDISKS_IGNORE=1 on this bootloader's VID, PID and
  serial, so desktop automount cannot race the raw I/O: any other predicate could keep it from applying
  when the device appears. Checked before any hardware access; the property on the enumerated device
  (check_exclusive) is the proof."""
  want = {('ATTRS{idVendor}', '=='): f'{facts["vid"]:04x}', ('ATTRS{idProduct}', '=='): f'{facts["pid"]:04x}',
          ('ATTRS{serial}', '=='): serial, ('ENV{UDISKS_IGNORE}', '='): '1'}
  token = r'([A-Za-z_]+(?:\{[^}]*\})?)\s*(==|!=|:=|\+=|-=|=)\s*"([^"]*)"'
  for d in UDEV_RULES:
    for f in sorted(Path(d).glob('*.rules')) if Path(d).is_dir() else ():
      for line in f.read_text(errors='replace').splitlines():
        found = re.findall(token, line)
        rest = re.sub(token, '', line).replace(',', '').strip()
        rule = {(k, op): v for k, op, v in found}
        if rest or len(rule) != len(found) or rule.pop(('SUBSYSTEM', '=='), 'block') != 'block':
          continue
        if rule == want:
          return str(f)
  raise Refused(f'no udev rule in SKILL.md\'s form sets ENV{{UDISKS_IGNORE}}="1" on idVendor '
                f'{want[("ATTRS{idVendor}", "==")]}, idProduct {want[("ATTRS{idProduct}", "==")]} and serial {serial}')


def udisks_ignored(dev):
  props = subprocess.run(['udevadm', 'info', '--query=property', f'--name={dev}'], capture_output=True, text=True)
  return 'UDISKS_IGNORE=1' in props.stdout.split()


def check_exclusive(dev):
  # the block node shows in sysfs before udev has run its rules on it (bench: RT1060 re-entry), so the
  # property gets a bounded wait; the mount check still catches a rule that did not apply
  start = time.monotonic()
  try:
    wait_for(lambda: udisks_ignored(dev), UDEV_TIMEOUT, f'UDISKS_IGNORE=1 on {dev}')
  except StepFail:
    raise StepFail(f'{dev} has no UDISKS_IGNORE=1: desktop automount could race the raw I/O (SKILL.md, host)')
  mounted = [l.split()[0] for l in Path('/proc/mounts').read_text().splitlines()]
  if any(os.path.realpath(m) == dev for m in mounted):
    raise StepFail(f'{dev} is mounted; refusing raw I/O')
  return round(time.monotonic() - start, 2)


class Fat:
  """Read-only FAT12/16 reader for the ghostfat volume. Its geometry and chains come from the firmware
  under test, so every one is bounded; it runs in its own process (fat_read) so a stuck USB read cannot
  hold the process that owns cleanup."""
  def __init__(self, dev):
    self.dev = dev
    bs = self.read(0, 512)
    self.bps, self.spc, self.res, self.nfat = struct.unpack_from('<HBHB', bs, 11)
    self.roots, = struct.unpack_from('<H', bs, 17)
    self.spf, = struct.unpack_from('<H', bs, 22)
    if self.bps not in (512, 1024, 2048, 4096) or self.spc not in (1, 2, 4, 8, 16, 32, 64, 128) or \
       not 1 <= self.nfat <= 2 or not self.res or not self.roots or not self.spf:
      raise ValueError(f'implausible FAT geometry {self.bps, self.spc, self.res, self.nfat, self.roots, self.spf}')
    self.root = (self.res + self.nfat * self.spf) * self.bps
    self.data = self.root + self.roots * 32
    self.fat16 = bs[54:62].startswith(b'FAT16')

  def read(self, off, n):
    fd = os.open(self.dev, os.O_RDONLY)
    try:
      b = os.pread(fd, n, off)
    finally:
      os.close(fd)
    if len(b) != n:
      raise ValueError(f'short read at {off:#x}: {len(b)} of {n} bytes')
    return b

  def entries(self):
    out = {}
    raw = self.read(self.root, self.roots * 32)
    for i in range(0, len(raw), 32):
      e = raw[i:i + 32]
      if e[0] in (0, 0xE5) or e[11] & 0x08:
        continue
      name = (e[:8].decode('ascii', 'replace').strip() + '.' + e[8:11].decode('ascii', 'replace').strip())
      out[name.rstrip('.')] = (struct.unpack_from('<H', e, 26)[0], struct.unpack_from('<I', e, 28)[0])
    return out

  def next_cluster(self, c):
    off = self.res * self.bps
    if self.fat16:
      return struct.unpack('<H', self.read(off + 2 * c, 2))[0]
    v = struct.unpack('<H', self.read(off + c * 3 // 2, 2))[0]
    return v >> 4 if c & 1 else v & 0xFFF

  def file(self, name, length=None):
    ents = self.entries()
    if name not in ents:
      raise ValueError(f'{name} not on the volume (found {sorted(ents)})')
    c, size = ents[name]
    want, out, csize, seen = min(size, length or size), b'', self.spc * self.bps, set()
    while len(out) < want:
      if not 2 <= c < (0xFFF8 if self.fat16 else 0xFF8) or c in seen:
        raise ValueError(f'{name}: cluster chain broken at {c:#x} after {len(out)} of {want} bytes')
      seen.add(c)
      out += self.read(self.data + (c - 2) * csize, min(csize, want - len(out)))
      c = self.next_cluster(c)
    return out, size


def fat_read(dev, name, length, log):
  """{'entries': {...}, 'data': bytes} of `name` on `dev`, read by a bounded child process."""
  code, out = spawn([sys.executable, '-B', __file__, 'fat-read', '--dev', dev, '--file', name,
                     '--length', str(length)], log, USB_TIMEOUT)
  try:
    r = json.loads(out.strip().splitlines()[-1])
  except (ValueError, IndexError):
    raise StepFail(f'fat-read of {name} gave no result (exit {code})', {'tail': out.strip().splitlines()[-3:]})
  if 'error' in r:
    raise StepFail(f'{name} on {dev}: {r["error"]}')
  return {'entries': r['entries'], 'data': bytes.fromhex(r['data']), 'size': r['size']}


def fat_read_main(args):
  try:
    fat = Fat(args.dev)
    data, size = fat.file(args.file, args.length) if args.length else (b'', fat.entries()[args.file][1])
    print(json.dumps({'entries': fat.entries(), 'data': data.hex(), 'size': size}))
  except (OSError, ValueError, KeyError, struct.error) as e:
    print(json.dumps({'error': f'{type(e).__name__}: {e}'}))
  return 0


# ------------------------------------------------------------------ locks

def load_helper(path):
  spec = importlib.util.spec_from_file_location('tinyusb_hil_lock', path)
  if not spec or not Path(path).is_file():
    raise Refused(f'lock helper {path} not found')
  mod = importlib.util.module_from_spec(spec)
  try:
    spec.loader.exec_module(mod)
  except Exception as e:
    raise Refused(f'lock helper {path} failed to load: {e}')
  if set(getattr(mod, 'PROTECTED_REASONS', ())) != PROTECTED or getattr(mod, 'CI_REASON', None) != 'hil_test.py':
    raise Refused(f'lock helper {path}: protected reasons are not {sorted(PROTECTED)}; recheck this contract')
  return mod


def holds_flock(pid, lock_file):
  """Whether process `pid` has an fd on `lock_file` whose open file description holds a FLOCK. The pid
  in /proc/locks and in fdinfo's lock line names whoever took the lock, which after a fork-and-exec
  handoff is the dead runner, so ownership is read through the holder's own fds."""
  st = os.stat(lock_file)
  try:
    fds = os.listdir(f'/proc/{pid}/fd')
  except OSError:
    return False
  for fd in fds:
    try:
      s = os.stat(f'/proc/{pid}/fd/{fd}')
      info = Path(f'/proc/{pid}/fdinfo/{fd}').read_text()
    except OSError:
      continue
    if (s.st_dev, s.st_ino) == (st.st_dev, st.st_ino) and \
       re.search(rf'^lock:.*\bFLOCK\b.*:{st.st_ino}\b', info, re.M):
      return True
  return False


def flock_free(lock_file):
  """No FLOCK on the lock file's inode in /proc/locks. A holder's fd goes before the kernel's deferred
  release of its lock, so recovery waits on this rather than on the holder's fds, without probing."""
  st = os.stat(lock_file)
  dev = f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}'
  return not any(' FLOCK ' in l and l.split()[5] == dev for l in Path('/proc/locks').read_text().splitlines())


def prove_hold(helper, board, pid, reason=None, role=None):
  """Refuse unless `pid` really holds the board's flock under the expected record."""
  path = helper.lock_path(board)
  rec = helper.read_record(board)
  if not isinstance(rec, dict) or rec.get('pid') != pid:
    raise Refused(f'{board}: lock record {rec} does not name pid {pid}')
  if reason is not None and rec.get('reason') != reason:
    raise Refused(f'{board}: held for {rec.get("reason")!r}, not {reason!r}')
  if role is not None and rec.get('role') != role:
    raise Refused(f'{board}: holder role {rec.get("role")!r}, not {role!r}')
  try:
    os.kill(pid, 0)
  except OSError:
    raise Refused(f'{board}: holder pid {pid} is not alive')
  if not holds_flock(pid, path):
    raise Refused(f'{board}: pid {pid} has no flock on {path}')
  try:
    fh = helper.flock_nb(board)
  except OSError:
    return rec
  fh.close()
  raise Refused(f'{board}: the flock on {path} is free')


def manual_holder(helper, board, reason):
  if reason in PROTECTED:
    raise Refused(f'{reason!r} is a protected holder; --under-hold takes the reason of your own manual hold')
  rec = helper.read_record(board)
  pid = rec.get('pid') if isinstance(rec, dict) else None
  if not isinstance(pid, int):
    raise Refused(f'{board}: no lock record; hold it first with {helper.__file__} hold {board} --reason ...')
  prove_hold(helper, board, pid, reason=reason)


def probe_users(probe):
  """Processes that have this probe open by serial (a JLinkExe or GDB server from an earlier session)."""
  users = []
  for d in Path('/proc').iterdir():
    try:
      cmd = (d / 'cmdline').read_bytes().split(b'\0')
    except OSError:
      continue
    if d.name.isdigit() and int(d.name) != os.getpid() and any(b'JLink' in c for c in cmd[:1]) and \
       any(probe.encode() in c for c in cmd):
      users.append(int(d.name))
  return users


def holder_record(fh, board, detail, survivors):
  fh.truncate(0)
  fh.seek(0)
  json.dump({'pid': os.getpid(), 'reason': 'hil_test.py', 'role': HOLDER_ROLE, 'board': board,
             'detail': detail, 'survivors': survivors, 'since': time.strftime('%Y-%m-%dT%H:%M:%S%z')}, fh)
  fh.flush()


HELD_IN_PROCESS = []


def keep_held(fh):
  """Hold until recovery's SIGUSR1, taken by sigwait with SIGUSR1 blocked since hand_off: a handler and
  pause() lose a signal that lands between the interpreter's check and the syscall. SIGTERM and SIGINT
  are ignored: an operator's timeout kill must not free a board that was never restored."""
  for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, signal.SIG_IGN)
  signal.pthread_sigmask(signal.SIG_SETMASK, {signal.SIGUSR1})
  for std in (0, 1, 2):   # closed, not reopened on /dev/null: holding must not need a free descriptor
    with contextlib.suppress(OSError):
      os.close(std)
  signal.sigwait({signal.SIGUSR1})
  fh.truncate(0)
  os._exit(0)


def hand_off(fh, board, detail, survivors=()):
  """Keep the board held after a failed cleanup, by a forked holder that shares the open file
  description, so the flock is never dropped, and keeps none of the caller's stdio, so the caller's
  wait ends with this process. When no holder starts, this process keeps the lock itself and main()
  stays alive holding it after reporting."""
  survivors = list(survivors)
  signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1})   # pending, not lost, until keep_held waits
  try:
    r, w = os.pipe()
    pid = os.fork()
  except OSError:
    pid = None
  if pid == 0:
    try:
      os.close(r)
      os.setsid()
      holder_record(fh, board, detail, survivors)
      os.write(w, b'ok')
      os.close(w)
      keep_held(fh)
    finally:
      os._exit(1)
  if pid:
    os.close(w)
    ready, _, _ = select.select([r], [], [], 10)
    ack = os.read(r, 16) if ready else b''
    os.close(r)
    if ack == b'ok':
      fh.close()   # never LOCK_UN or truncate: the description and its record are the holder's now
      return {'pid': pid, 'reason': 'hil_test.py', 'ready': True}
    with contextlib.suppress(ProcessLookupError):
      os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(ChildProcessError):
      os.waitpid(pid, 0)
  holder_record(fh, board, detail, survivors)
  HELD_IN_PROCESS.append(fh)
  return {'pid': os.getpid(), 'reason': 'hil_test.py', 'ready': True, 'inProcess': True}


# ------------------------------------------------------------------ the battery

def verify_record(record_path, board, facts):
  try:
    rec = json.loads(Path(record_path).read_text())
  except (OSError, ValueError) as e:
    raise Refused(f'cannot read build record {record_path}: {e}')
  rows = [r for r in rec.get('boards', []) if r.get('board') == board['src']]
  if not rec.get('pass') or len(rows) != 1 or rows[0].get('status') != 'ok' or rows[0].get('removed'):
    raise Refused(f'{record_path}: not a passing --shared build of {board["src"]}')
  row, info = rows[0], rec.get('input', {})
  if row.get('backend') != 'make':
    raise Refused(f'{record_path}: {row.get("backend")} artifacts are not supported yet (make only)')
  now = cb.identity({board['port']})
  for key in ('head', 'submodules', 'deps'):
    if info.get(key) != now[key]:
      raise Refused(f'{record_path}: {key} {info.get(key)} differs from the checkout now ({now[key]})')
  for state in (info, now):
    bad = state.get('dirty') or state.get('dirtyInputs') or state.get('missingInputs') or state.get('depsOffPin') \
          or state.get('inputsDirtiedByBuild')
    if bad:
      raise Refused(f'build inputs are not clean: {bad} (commit, or rebuild from a clean checkout)')
  root = cb.ROOT / row['buildDir']
  files, digests = {}, {}
  for p in cb.expected_artifacts(board['port'], board['src'], 'make', root):
    kind = p.suffix[1:]
    if kind not in ('hex', 'bin'):
      continue
    digests[kind] = sha256(p)
    if row.get('sha256', {}).get(str(p.relative_to(root))) != digests[kind]:
      raise Refused(f'{p}: hash differs from the build record')
    files[kind] = p
  return files, {'path': str(files['bin']), 'sha256': digests['bin'], 'buildRecord': str(record_path),
                 'defines': rec.get('defines', []), 'version': embedded_version(files['bin'])}


def sha256(p):
  try:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
  except OSError:
    return None


def check_bootloader_bin(bin_path, install, app, board, facts, what):
  """Every span a bootloader install writes: the BIN from the install start inside `install` and the zero
  page at the start of `app` inside it, both within the device's flash limits; and the BIN is this
  board's (its UF2_BOARD_ID)."""
  size = Path(bin_path).stat().st_size
  limits = FLASH_LIMITS[board['device']]
  check_ranges({install[0]: 0, install[0] + size - 1: 0}, [install], limits, what)
  check_ranges({app[0]: 0, app[0] + board['page'] - 1: 0}, [app], limits, f'{what} zero page')
  if facts['boardId'].encode() not in Path(bin_path).read_bytes():
    raise Refused(f'{what}: {bin_path} does not carry board id {facts["boardId"]!r}; not this board\'s bootloader')


def check_restore(board, facts):
  """The restoration profile, validated at admission: a run never discovers an unusable recovery
  image after it has touched the board."""
  r = board['restore']
  if sha256(r['bin']) != r['sha256']:
    raise Refused(f'restoration image {r["bin"]} does not match its pinned sha256')
  if r['install'] != (facts['flashBase'], r['appStart']):
    raise Refused(f'restoration layout install {r["install"]} must run from the flash base {facts["flashBase"]:#x} '
                  f'to its appStart {r["appStart"]:#x}')
  check_bootloader_bin(r['bin'], r['install'], (r['appStart'], FLASH_LIMITS[board['device']][1]), board, facts,
                       'restoration image')
  if f'TinyUF2 Bootloader {r["version"]}\r\n'.encode() not in Path(r['bin']).read_bytes():
    raise Refused(f'restoration image does not embed version {r["version"]!r}')


class Battery:
  def __init__(self, board, facts, workdir, fail_at=None, commissioning=False):
    self.b, self.f, self.dir, self.fail_at, self.commissioning = board, facts, workdir, fail_at, commissioning
    self.log = workdir / 'hil.log'
    self.probe = Probe(board, workdir, self.log)
    self.steps, self.usb_path, self.touched, self.at = [], None, False, 'setup'
    self.zero = workdir / 'zero.bin'
    self.zero.write_bytes(b'\0' * board['page'])

  def step(self, name, fn):
    self.at = name   # an abort names the step it cut short without recording it as a failing step
    if self.fail_at == name:
      self.steps.append({'step': name, 'pass': False, 'evidence': {}, 'detail': 'injected by --fail-at'})
      raise StepFail(f'--fail-at {name}: injected criterion failure (acceptance only)')
    try:
      ev = fn() or {}
    except StepFail as e:
      self.steps.append({'step': name, 'pass': False, 'evidence': e.evidence, 'detail': str(e)})
      raise
    self.steps.append({'step': name, 'pass': True, 'evidence': ev, 'detail': ''})

  def identity(self):
    v = self.probe.mem32([SCB_CPUID, DHCSR])
    return {'cpuid': f'{v[SCB_CPUID]:#010x}', 'dhcsr': f'{v[DHCSR]:#010x}'}

  def program(self, bin_path, base, app_start):
    """One image from `base`: the bootloader BIN, 0xFF up to app_start, then a zero page, written by a single
    loadbin and read back, so no second write lands in the bootloader's erase block; the zeroed reset vector
    makes the app invalid by construction, so the next boot stays in DFU. No range erase is ever issued.
    Callers have range-checked both spans (check_bootloader_bin)."""
    data = Path(bin_path).read_bytes()
    if base + len(data) > app_start:
      raise StepFail(f'{bin_path} [{base:#x}, {base + len(data):#x}) overlaps the app start {app_start:#x}')
    image = self.dir / 'program.bin'
    image.write_bytes(data + b'\xff' * (app_start - base - len(data)) + bytes(self.b['page']))
    self.touched = True
    self.installed = (bin_path, base)
    self.probe.run(['h', f'loadbin {image},{base:#x}', f'verifybin {image},{base:#x}', 'r', 'g'])

  def dfu(self, version):
    f = self.f
    path = wait_for(lambda: usb_device(f['vid'], f['pid'], self.b['uid']), USB_TIMEOUT,
                    f'{f["vid"]:04x}:{f["pid"]:04x} serial {self.b["uid"]}')
    if self.usb_path and path != self.usb_path:
      raise StepFail(f'came back on USB port {path}, not {self.usb_path}')
    self.usb_path = path
    dev = wait_for(lambda: block_device(path), USB_TIMEOUT, f'the block device of USB {path}')
    udev_wait = check_exclusive(dev)
    info = fat_read(dev, 'INFO_UF2.TXT', 512, self.log)
    lines = info['data'].decode('ascii', 'replace').splitlines()
    want = f'TinyUF2 Bootloader {version}'
    if not lines or lines[0] != want or f'Board-ID: {f["boardId"]}' not in lines or \
       f'Flash Size: 0x{f["flashSize"]:08X} bytes' not in lines:
      raise StepFail('INFO_UF2.TXT does not match this build', {'info': lines, 'want': want})
    size = (info['entries'].get('CURRENT.UF2') or [None, None])[1]
    if size != f['flashSize'] // 256 * 512:
      raise StepFail(f'CURRENT.UF2 is {size} bytes, not {f["flashSize"] // 256 * 512}')
    return {'usb': path, 'dev': dev, 'udevWaitS': udev_wait, 'info': lines[0], 'currentUf2': size,
            'claim': 'app rejected (reset vector 0); DFU observed'}

  def current_uf2(self, length):
    """CURRENT.UF2's first blocks, each checked for its place: block i maps to app_start + 256*i."""
    dev = block_device(self.usb_path)
    data = fat_read(dev, 'CURRENT.UF2', length, self.log)['data']
    try:
      blocks = parse_uf2(data)
    except ValueError as e:
      raise StepFail(f'CURRENT.UF2 is not UF2: {e}', {'head': data[:32].hex()})
    for i, bl in enumerate(blocks):
      if (bl['no'], bl['addr'], bl['size']) != (i, self.f['appStart'] + 256 * i, 256):
        raise StepFail(f'CURRENT.UF2 block {i} is {bl["no"]} at {bl["addr"]:#x}, not at {self.f["appStart"] + 256 * i:#x}')
    return b''.join(bl['data'] for bl in blocks)

  def run(self, files, version):
    f = self.f
    nonce = os.urandom(16)
    self.fix = fixture(f, nonce)
    app_bin, app_uf2 = make_uf2(self.fix['image'], f['appStart'], f['family'], self.dir)
    blocks = parse_uf2(app_uf2.read_bytes())
    payload = {}
    for bl in blocks:
      if bl['family'] != f['family'] or not bl['flags'] & UF2_FLAG_FAMILY:
        raise Refused('generated UF2 has the wrong family')
      payload.update({bl['addr'] + i: x for i, x in enumerate(bl['data'])})
    check_ranges(payload, [self.b['app']], FLASH_LIMITS[self.b['device']], 'fixture UF2')
    self.step('identity', self.identity)
    self.step('install', lambda: self.program(files['bin'], self.b['install'][0], f['appStart']) or
              {'zeroPage': f'{f["appStart"]:#x}', 'verified': True})
    self.step('dfu', lambda: self.dfu(version))

    def copy():
      dev = block_device(self.usb_path)
      code, out = spawn(['mcopy', '-o', '-i', dev, app_uf2, '::APP.UF2'], self.log, 60)
      if code:
        raise StepFail(f'mcopy failed: {out.strip()[-200:]}')
      spawn(['sync'], self.log, 60)
      wait_for(lambda: usb_device(f['vid'], f['pid'], self.b['uid']) is None, USB_TIMEOUT, 'the DFU device leaving')
      return {'blocks': len(blocks), 'nonce': nonce.hex()}
    self.step('copy', copy)

    def app_ran():
      # the bootloader writes DBL_TAP_MAGIC as it boots: a probe connect that resets inside that window
      # would send the next boot to DFU, so the first connect waits it out
      window = 2 * f['dblTapDelayMs'] / 1000 + 0.5
      time.sleep(window)
      ev = dict(self.observe_app(app_bin), waitedS=window)
      time.sleep(QUIET_TIME)
      if usb_device(f['vid'], f['pid'], self.b['uid']):
        raise StepFail('the DFU device came back while the app should run', ev)
      return ev
    self.step('app-ran', app_ran)

    def reenter():
      ev = {'path': self.b['reentry']}
      try:
        return entered(ev)
      except StepFail as e:   # what was observed before the failure stays in the step's evidence
        e.evidence = {**ev, **e.evidence}
        raise

    def entered(ev):
      method = ev['path']
      if method == 'retained-register':
        if self.commissioning:
          ev.update(self.control(app_bin))
        self.probe.write32(f['dblTapReg'], f['dblTapMagic'])
        # SYSRESETREQ may drop the debug connection mid-write: its exit is not judged, enumeration is;
        # no probe session opens again until DFU is observed
        tail = self.probe.run([f'w4 {SCB_AIRCR:08X} {AIRCR_SYSRESETREQ:08X}'], judge=False)
      else:
        bin_path, base = self.installed
        tail = self.probe.run(['h', f'loadbin {self.zero},{f["appStart"]:#x}', f'verifybin {self.zero},{f["appStart"]:#x}',
                               f'verifybin {bin_path},{base:#x}', 'r', 'g'])
        ev['bootloaderVerified'] = True
      ev.update(self.dfu(version), dfuCameUp=True, resetTail=tail.strip().splitlines()[-3:])
      ev['claim'] = 'the write/reset sequence re-entered DFU (register retention inferred)' \
        if method == 'retained-register' else 'invalidate application and enter DFU'
      if method == 'retained-register':
        left = self.probe.mem32([f['dblTapReg']])[f['dblTapReg']]
        ev.update(dblTapRegAfter=hex(left), magicConsumed=not left)
        if left:
          raise StepFail('the double-tap register was not consumed', ev)
      expect = bytearray(self.fix['image'])
      if method == 'app-invalidate':
        expect[:self.b['page']] = bytes(self.b['page'])
      n = -(-len(expect) // 256)
      try:
        got = self.current_uf2(n * 512)
        if got[:len(expect)] != bytes(expect):
          raise StepFail('CURRENT.UF2 does not read back the fixture from the app start')
      except StepFail as e:
        e.evidence = {**ev, **e.evidence, 'failedAt': 'readback', 'appIntact': 'unshown'}
        raise
      ev['appIntact'] = True
      return ev
    self.step('reenter', reenter)

  def observe_app(self, app_bin):
    """The fixture running from the bootloader handoff: two halts in one session, the counter moving,
    PC at its handler in thread mode, VTOR and MSP from its vector table, and its image intact. The
    in-script wait covers a connect that resets the core and so restarts the double-tap window."""
    f = self.f
    out = self.probe.run(['h', 'g', f'sleep {2 * f["dblTapDelayMs"] + 200}', 'h', 'regs', f'mem32 {SCB_VTOR:08X} 1',
                          'g', 'sleep 10', 'h', 'regs', f'verifybin {app_bin},{f["appStart"]:#x}', 'g'])
    chunks = after(out, 'regs')
    if len(chunks) != 2:
      raise StepFail(f'expected two regs dumps, got {len(chunks)}', {'tail': out.strip().splitlines()[-8:]})
    first, second = regs(chunks[0]), regs(chunks[1])
    m = re.search(rf'^{SCB_VTOR:08X} = ([0-9A-F]{{8}})', out, re.M)
    if not m:
      raise StepFail('no VTOR read in the transcript')
    vtor = int(m.group(1), 16)
    ev = {'pc': hex(first['pc']), 'ipsr': first['ipsr'], 'vtor': hex(vtor), 'msp': hex(first['msp']),
          'r0': [hex(first['r0']), hex(second['r0'])], 'verifybin': True,
          'scope': 'executes through bootloader handoff after the observed reset; upload-triggered run unverified'}
    ok = (first['pc'] in (self.fix['handler'], self.fix['handler'] + 2) and first['pc'] != self.fix['fault'] and
          first['ipsr'] == 0 and vtor == f['appStart'] and first['msp'] == self.fix['sp'] and
          first['r0'] != second['r0'])
    if not ok:
      raise StepFail('the fixture is not running from the bootloader handoff', ev)
    return ev

  def control(self, app_bin):
    """Commissioning: the same SYSRESETREQ session without the magic must return to the app. The bootloader
    arms the magic itself for its double-tap window (src/main.c), so a session that reset twice would
    re-enter DFU with no magic written; USB is watched past that window before any probe reconnects."""
    f = self.f
    self.probe.run([f'w4 {SCB_AIRCR:08X} {AIRCR_SYSRESETREQ:08X}'], judge=False)
    watch = 2 * f['dblTapDelayMs'] / 1000 + USB_TIMEOUT
    end = time.monotonic() + watch
    while time.monotonic() < end:
      if usb_device(f['vid'], f['pid'], self.b['uid']):
        raise StepFail('the reset without the magic entered DFU', {'controlBootedApp': False})
      time.sleep(0.2)
    return {'control': self.observe_app(app_bin), 'controlWatchedS': watch, 'controlBootedApp': True}


def restore(board, facts, workdir, battery=None):
  """The pinned known-good bootloader and its zero page, read back, reset, DFU observed with the restoration
  version, then the double-tap register cleared. Its layout is the restoration profile's (check_restore at
  admission), never the candidate's."""
  r = board['restore']
  if sha256(r['bin']) != r['sha256']:
    raise StepFail(f'restoration image {r["bin"]} changed since admission')
  bat = battery or Battery(board, facts, workdir)
  bat.program(r['bin'], r['install'][0], r['appStart'])
  ev = bat.dfu(r['version'])
  # cleared only now: the register is clocked once the bootloader has run board_init, and in DFU for an
  # invalid app it is never read (src/main.c), so a magic left by a failed reenter would outlive restore
  ev['dblTapReg'] = bat.probe.write32(facts['dblTapReg'], 0)
  return {'pass': True, 'state': f'restoration bootloader {r["version"]} in DFU', 'evidence': ev}


TERM_SIGNALS = {signal.SIGTERM, signal.SIGINT}


@contextlib.contextmanager
def signals(how):
  old = signal.pthread_sigmask(how, TERM_SIGNALS)
  try:
    yield
  finally:
    signal.pthread_sigmask(signal.SIG_SETMASK, old)


def on_signal(signum, _):
  # blocked again before raising: no later signal can break into the unwinding or the cleanup
  signal.pthread_sigmask(signal.SIG_BLOCK, TERM_SIGNALS)
  raise Interrupted(f'interrupted by {signal.Signals(signum).name}')


def check_jlink():
  if shutil.which('JLinkExe') is None:
    raise Refused('JLinkExe must be on PATH')


def reentry_decision(row):
  """The re-entry method a commissioning run establishes (SKILL.md, Commissioning), or None: every
  observation of the tried method held, the board was restored and released, and the run passed or failed
  only at reenter's CURRENT.UF2 readback."""
  restored = row.get('restored') or {}
  if not row.get('commissioning') or not restored.get('pass') or restored.get('heldAfter'):
    return None
  steps = row.get('steps', [])
  failed = [x for x in steps if not x['pass']]
  reenter = [x for x in steps if x['step'] == 'reenter']
  if len(reenter) != 1 or failed not in ([], reenter) or (not failed and not row.get('pass')) or \
     (failed and reenter[0]['evidence'].get('failedAt') != 'readback'):
    return None
  need = ('controlBootedApp', 'dfuCameUp', 'magicConsumed') if row['tried'] == 'retained-register' else \
    ('bootloaderVerified', 'dfuCameUp')
  return row['tried'] if all(reenter[0]['evidence'].get(k) is True for k in need) else None


def run_board(args, board, facts, helper, workdir):
  row = {'board': board['name'], 'ran': False, 'pass': False, 'locked': False, 'lockBypassed': False,
         'steps': [], 'restored': None, 'detail': ''}
  if socket.gethostname() != board['host']:
    raise Refused(f'this roster describes host {board["host"]!r}, not {socket.gethostname()!r}')
  if args.try_reentry:
    if board['reentry'] is not None:
      raise Refused(f'{board["name"]}: reentry is already commissioned; --try-reentry is for commissioning only')
    board = dict(board, reentry=args.try_reentry)
    row.update(commissioning=True, tried=args.try_reentry)
  elif board['reentry'] not in REENTRY:
    raise Refused(f'{board["name"]}: tinyuf2.reentry must be one of {REENTRY} (set from commissioning)')
  files, row['firmware'] = verify_record(args.build_record, board, facts)
  data = parse_hex(files['hex'])
  check_ranges(data, [board['install']], FLASH_LIMITS[board['device']], files['hex'])
  if not hex_matches_bin(data, files['bin'], board['install'][0]):
    raise Refused(f'{files["hex"]} and {files["bin"]} do not hold the same bytes')
  check_bootloader_bin(files['bin'], board['install'], board['app'], board, facts, 'candidate')
  check_restore(board, facts)
  exclusion_configured(facts, board['uid'])
  if shutil.which('mcopy') is None:
    raise Refused('mcopy must be on PATH')
  check_jlink()
  bypass = os.environ.get('HIL_NO_BOARD_LOCK') == '1'
  # blocked from here until the process exits or becomes the holder (keep_held): a signal acts only
  # inside the battery, and the report and any hold are settled first
  signal.pthread_sigmask(signal.SIG_BLOCK, TERM_SIGNALS)
  try:
    fh = helper.acquire_board_lock(board['name'])
  except RuntimeError as e:
    row.update(locked=True, detail=str(e))
    return deferred(row), 1
  if fh is None and not bypass:
    raise Refused(f'{board["name"]}: the lock dir is unusable (tinyusb helper fails open); refusing to run unlocked')
  row['lockBypassed'] = fh is None
  bat = Battery(board, facts, workdir, args.fail_at, row.get('commissioning', False))
  code = 0
  try:
    row['ran'] = True
    with signals(signal.SIG_UNBLOCK):
      bat.run(files, row['firmware']['version'])
    row['pass'] = True
  except BaseException as e:   # anything after admission still restores below
    row['detail'] = f'{bat.at}: {e}' if isinstance(e, StepFail) else f'{bat.at}: {type(e).__name__}: {e}'
    code = 1
  row['steps'], row['jlinkRetried'] = bat.steps, bat.probe.retried   # the restore's retries land here too
  code = clean_up(row, code, bat, fh, board, facts, helper, workdir)
  if row.get('commissioning'):
    row['reentryDecision'] = reentry_decision(row)
  return deferred(row), code


def deferred(row):
  pending = sorted(signal.Signals(s).name for s in signal.sigpending() & TERM_SIGNALS)
  if pending:
    row['detail'] = '; '.join(filter(None, (row['detail'], f'{", ".join(pending)} deferred until the board was settled')))
  return row


def clean_up(row, code, bat, fh, board, facts, helper, workdir):
  """Restore a touched board, then release it. A child that survived SIGKILL, or any unsuccessful
  restore, leaves the board held (exit 4), touched or not."""
  stuck = []
  try:
    stuck = stuck_children()
    if stuck:
      raise StepFail(f'children {[x["pid"] for x in stuck]} survived SIGKILL; no flash may overlap them')
    if bat.touched:
      row['restored'] = dict(restore(board, facts, workdir, bat), heldAfter=False)
  except BaseException as e:
    stuck += [x for x in stuck_children() if x not in stuck]
    row['restored'] = {'pass': False, 'state': 'unknown' if bat.touched else 'untouched',
                       'evidence': getattr(e, 'evidence', {}), 'detail': f'{type(e).__name__}: {e}',
                       'survivors': stuck, 'heldAfter': fh is not None}
    row['pass'] = False
    if fh is not None:
      row['restored']['holder'] = hand_off(fh, board['name'], row['restored']['detail'], stuck)
      fh = None
    return 4
  if fh is not None:
    helper.clear_record(fh)
    fh.close()
  return code


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  sub = ap.add_subparsers(dest='cmd', required=True)
  r = sub.add_parser('run', help='the battery on one board (self-locking)')
  r.add_argument('-b', '--board', required=True)
  r.add_argument('--build-record', required=True, help='check_build.py --board B --shared JSON, under cmake-build/')
  r.add_argument('--fail-at', choices=STEPS, help='acceptance only: fail this step to exercise cleanup')
  r.add_argument('--try-reentry', choices=REENTRY, help="commissioning only, while the roster's reentry is unset")
  r.add_argument('config')
  i = sub.add_parser('install', help='program a bootloader BIN under your own manual hold')
  i.add_argument('-b', '--board', required=True)
  i.add_argument('--firmware', required=True,
                 help='a bootloader BIN, programmed at the install start with a zero page at the app start')
  i.add_argument('--sha256', required=True)
  i.add_argument('--under-hold', required=True, metavar='REASON')
  i.add_argument('config')
  s = sub.add_parser('restore', help='restore the pinned bootloader under a hold')
  s.add_argument('-b', '--board', required=True)
  g = s.add_mutually_exclusive_group(required=True)
  g.add_argument('--under-hold', metavar='REASON')
  g.add_argument('--recover-holder', type=int, metavar='PID')
  s.add_argument('--report', help="the failed run's hil_report.json (with --recover-holder)")
  s.add_argument('config')
  fr = sub.add_parser('fat-read')
  fr.add_argument('--dev', required=True)
  fr.add_argument('--file', required=True)
  fr.add_argument('--length', type=int, required=True)
  args = ap.parse_args(argv)
  if args.cmd == 'fat-read':
    return fat_read_main(args)
  for sig in TERM_SIGNALS:
    signal.signal(sig, on_signal)
  run_dir = cb.BUILD_DIR / 'hil' / f'run-{time.strftime("%Y%m%d-%H%M%S")}-{os.getpid()}'
  result = {'pass': False, 'caveat': '', 'results': [], 'reportPath': str(run_dir / 'hil_report.json')}
  code = 2
  try:
    run_dir.mkdir(parents=True)
    board = load_board(args.config, args.board)
    facts = source_facts(board)
    check_layout(board, facts)
    helper = load_helper(board['helper'])
    if args.cmd == 'run':
      row, code = run_board(args, board, facts, helper, run_dir)
      result['results'].append(row)
      result['pass'] = code == 0 and row['pass']
    elif args.cmd == 'install':
      manual_holder(helper, board['name'], args.under_hold)
      if sha256(args.firmware) != args.sha256:
        raise Refused(f'{args.firmware} does not match --sha256')
      check_bootloader_bin(args.firmware, board['install'], board['app'], board, facts, args.firmware)
      exclusion_configured(facts, board['uid'])
      check_jlink()
      try:
        Battery(board, facts, run_dir).program(args.firmware, board['install'][0], facts['appStart'])
      finally:
        result['survivors'] = stuck_children()
      result['results'].append({'board': board['name'], 'installed': {'path': args.firmware, 'sha256': args.sha256}})
      result['pass'], code = True, 0
    else:
      check_restore(board, facts)
      exclusion_configured(facts, board['uid'])
      check_jlink()
      rec = None
      if args.recover_holder is not None:
        if not args.report:
          raise Refused("--recover-holder needs --report, the failed run's report naming that holder")
        try:
          rows = json.loads(Path(args.report).read_text())['results']
        except (OSError, ValueError, KeyError, TypeError) as e:
          raise Refused(f'cannot read {args.report}: {e}')
        held = [x['restored'] for x in rows if ((x.get('restored') or {}).get('holder') or {}).get('pid')
                == args.recover_holder and x.get('board') == board['name']]
        if len(held) != 1:
          raise Refused(f'{args.report} names no cleanup holder {args.recover_holder} of {board["name"]}')
        rec = prove_hold(helper, board['name'], args.recover_holder, reason='hil_test.py', role=HOLDER_ROLE)
        cmdline = Path(f'/proc/{args.recover_holder}/cmdline').read_bytes()
        if b'hil_test.py' not in cmdline:
          raise Refused(f'pid {args.recover_holder} is not a hil_test.py cleanup holder')
        alive = still_alive(held[0].get('survivors', []) + rec.get('survivors', []))
        if alive:
          raise Refused(f'the failed run\'s children {alive} are still alive; recovery may not overlap them')
      else:
        manual_holder(helper, board['name'], args.under_hold)
      users = probe_users(board['probe'])
      if users:
        raise Refused(f'probe {board["probe"]} is still in use by pids {users}; recovery may not overlap them')
      try:
        restored = restore(board, facts, run_dir)
      finally:
        result['survivors'] = stuck_children()
      if result['survivors']:
        raise StepFail('restore left children that survived SIGKILL')
      if args.recover_holder is not None:
        os.kill(args.recover_holder, signal.SIGUSR1)
        wait_for(lambda: flock_free(helper.lock_path(board['name'])), 10,
                 f'cleanup holder {args.recover_holder} releasing {board["name"]}')
        restored['recovered'] = {'holder': args.recover_holder, 'record': rec}
      result['results'].append({'board': board['name'], 'restored': restored})
      result['pass'], code = True, 0
  except Refused as e:
    result['error'] = str(e)
    if args.cmd == 'run' and not result['results']:
      result['results'].append({'board': args.board, 'ran': False, 'pass': False, 'locked': False,
                                'detail': str(e)})
    code = 2
  except (StepFail, Interrupted) as e:
    result['error'] = str(e)
    code = 1
  if result.get('survivors'):   # a manual operation's survivor: keep your hold until it is gone
    result['pass'], code = False, 4
  try:
    Path(result['reportPath']).write_text(json.dumps(result, indent=1))
  except OSError:
    pass
  print(json.dumps(result), flush=True)
  if HELD_IN_PROCESS:
    keep_held(HELD_IN_PROCESS[0])
  return code


if __name__ == '__main__':
  sys.exit(main())
