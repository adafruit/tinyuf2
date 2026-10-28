#!/usr/bin/env python3
"""TinyUF2 HIL battery and the probe operations debug sessions share with it.

  hil_test.py run -b BOARD --build-record FILE CONFIG [--fail-at STEP] [--try-reentry METHOD] [--ci-state-root DIR]
  hil_test.py run -b BOARD --build-record FILE --update-record VARIANT CONFIG [--fail-at STEP]
  hil_test.py install -b BOARD --build-record FILE --under-hold REASON [--try-reentry METHOD] CONFIG
  hil_test.py restore -b BOARD --build-record FILE (--under-hold REASON [--try-reentry METHOD] | --recover-holder PID --report FILE
                      | --recover-takeover TOKEN [--report FILE]) CONFIG

The last stdout line is JSON. Exit 0 every board passed and was cleaned up, 1 a board failed or did not
run (cleaned up or never touched), 2 refused before any hardware access, 4 cleanup failed (the board is
held when `cleanup.heldAfter`; not under HIL_NO_BOARD_LOCK), a manual operation left `survivors`, or a
`restore` failed after it began writing.
SKILL.md beside this script is the contract; this file is its mechanics.
"""
import argparse
import contextlib
import errno
import fcntl
import fnmatch
import functools
import hashlib
import json
import mmap
import os
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'build' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True   # nothing the runner imports may write into a checkout it binds
import board_facts as bf  # noqa: E402
import check_build as cb  # noqa: E402
import hil_ci  # noqa: E402   CI's state directory: unfinished()
import hil_esp as esp  # noqa: E402
import hil_run_report as run_report  # noqa: E402

# [floor, ceiling) the runner ever programs, per J-Link device, independent of roster and source:
# LPC55S69 PFR starts at 0x9DE00 and a bad CMPA write can lock the part (UM11126 Table 173, Table 1064);
# 0x9D800-0x9DDFF is reserved and undocumented. MIMXRT1062: FlexSPI XIP at 0x60000000 (IMXRT1060RM
# Table 3-1) holding the EVK's 8 MiB IS25WP064A (EVK hardware user's guide 2.7). MIMXRT1011: FlexSPI XIP at
# 0x60000000 (IMXRT1010RM Table 3-1) holding the Metro M7 1011's W25Q64JV (Metro M7 RT1011 SD revA schematic), 8 MiB.
# MIMXRT1064: FlexSPI2 at 0x70000000 (IMXRT1064RM Rev 2 Table 3-1) holding the 4 MB on-chip flash (IMXRT1064IEC Rev 3, 1.1).
# STM32F303VC: 256 KiB main flash at 0x08000000 (RM0316 Rev 10 Table 2); option bytes at 0x1FFFF800 stay outside.
# STM32F407VG: 1 MiB main flash at 0x08000000 (RM0090 Rev 22 Table 5); OTP at 0x1FFF7800 and option bytes at
# 0x1FFFC000 stay outside.
# STM32F411VE: 512 KiB main flash at 0x08000000 (RM0383 Rev 4 Table 4); option bytes at 0x1FFFC000 stay outside.
# STM32H563ZI: 2 MiB main flash, banks at 0x08000000 and 0x08100000 (RM0481 Rev 5 Table 51); OTP at 0x08FFF000 and
# system memory at 0x0BF80000 stay outside, and its option bytes have no memory address (RM0481 7.4.1).
# STM32H743ZI: 2 MiB main flash, banks at 0x08000000 and 0x08100000 (RM0433 Rev 8 Table 15); system memory at
# 0x1FF00000 stays outside, and its option bytes are registers only.
# MAX32665/6: 1 MiB internal flash at 0x10000000, two 512 KiB blocks (MAX32665/MAX32666 UG Rev 3, 3.3.1); the
# information block at 0x10800000 stays outside.
FLASH_LIMITS = {'LPC55S69_M33_0': (0, 0x9D800), 'MIMXRT1062xxx6A': (0x60000000, 0x60800000),
                'MIMXRT1011DAE5A': (0x60000000, 0x60800000), 'MIMXRT1064xxx6A': (0x70000000, 0x70400000),
                'stm32f303vc': (0x08000000, 0x08040000), 'stm32f407vg': (0x08000000, 0x08100000),
                'stm32f411ve': (0x08000000, 0x08080000), 'stm32h563zi': (0x08000000, 0x08200000),
                'stm32h743zi': (0x08000000, 0x08200000), 'max32665': (0x10000000, 0x10100000)}
# by a board's kind, its firmware and battery: a J-Link, ST-LINK or openocd Cortex-M board, or an Espressif one whatever
# transport installs it (board['flasher'])
STEPS = {'jlink': ('install', 'dfu', 'copy', 'app-ran', 'reenter')}
STEPS['stlink'] = STEPS['openocd'] = STEPS['jlink']
STEPS['esp'] = STEPS['jlink'] + ('recopy',)
# run --update-record: the update battery (SKILL.md Execution, Update), J-Link boards of UPDATE_PORTS only
STEPS['update'] = ('install', 'dfu', 'update-variant', 'update', 'interrupt', 'recover')
REENTRY = {'jlink': ('retained-register',), 'stlink': ('retained-register',), 'openocd': ('retained-register',),
           'esp': ('dfu-detach',)}
REENTRY_METHODS = sorted({m for v in REENTRY.values() for m in v})
PROTECTED = {'hil_test.py', 'farm_check'}   # hil_lock.PROTECTED_REASONS, checked at load
# the board-lock helper is the submodule's at its pinned commit, never an operator's installed agentrc
AGENTRC = 'lib/agentrc'
LOCK_HELPER = ROOT / AGENTRC / 'skills' / 'hil' / 'scripts' / 'hil_lock.py'
# the flash provider beside it (agentrc `hil` Flashers): every install, probe session and reset runs through it
FLASH_PROVIDER = LOCK_HELPER.with_name('hil_flash.py')
OPENOCD_ESP = LOCK_HELPER.with_name('hil_openocd_esp.py')   # an Espressif board's JTAG route (tinyuf2.routes)
OPENOCD_TIMEOUT = 300   # s for one openocd_esp flash: every segment programmed, verified and read back
CMSIS_DAP_TIMEOUT = 300   # s for one CMSIS-DAP program at the max32665 cfg's 100 kHz (untimed on the rig)
HOLDER_ROLE = 'cleanup-holder'
LOCK_POLL = 15   # s between tries at a held board within run's --lock-wait
SCB_VTOR, SCB_AIRCR = 0xE000ED08, 0xE000ED0C
AIRCR_SYSRESETREQ = 0x05FA0004
UF2_MAGIC = (0x0A324655, 0x9E5D5157, 0x0AB16F30)
UF2_FLAG_FAMILY = 0x2000
PROBE_TIMEOUT, USB_TIMEOUT, QUIET_TIME, KILL_WAIT, UDEV_TIMEOUT = 120, 20, 3, 5, 5
JLINK_RETRY_DELAY = 2
FLUSH_GONE = 3   # `flush`'s exit when its open found the device gone
ESP_BAUD, ESP_TIMEOUT = 921600, 300
# the provider's children an Espressif battery spawns, at the pin (agentrc `hil`); admission refuses without them
ESP_SESSION = LOCK_HELPER.with_name('esptool_session.py')
USB_DFU = LOCK_HELPER.with_name('usb_dfu.py')
REPORT_CORE = LOCK_HELPER.with_name('hil_report_core.py')   # the report document (agentrc `hil` Reporting)
NONCE_MAGIC, NONCE_BLOCK = b'TUF2NONC', 256   # apps/dfu_runtime/src/dfu_runtime.h
JLINK_IF, JLINK_SPEED = 'SWD', '4000'
STM32_PROGRAMMER_CLI = 'STM32_Programmer_CLI'
# what STM32CubeProgrammer prints at every connect to the roster's device: its Device ID and NVM size (bench, v2.23.0);
# 0x484 names the H56x/573 family only, so the size pins the part; 0x450 names STM32H742/743/753/750 (RM0433 Rev 8
# DBGMCU_IDC) and 2 MBytes their xI parts, which share the H743ZI's flash map (RM0433 Rev 8 Table 15)
STLINK_CHIPS = {'stm32h563zi': ('0x484', '2 MBytes'), 'stm32h743zi': ('0x450', '2 MBytes')}
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')   # any CSI sequence: esptool 5.2.0 and 5.3.1 move the cursor off a TTY too
# each script operation's success line, by its first word (bench, v2.23.0)
STLINK_DONE = {'-halt': 'Core halted', '-run': 'Core run', '-rst': 'Software reset is performed',
               '-coreReg': 'XPSR     = 0x', '-r32': 'Reading 32-bit memory content', '-w32': '32-bit data download complete',
               '-u': 'Data read successfully', '#Delay': 'The system go to sleep for'}
CMAKE_RECORD_FILES = ('_bin/tinyuf2.bin', '_bin/apps/blinky.uf2')   # besides the flash's inputs
UPDATE_UF2 = '_bin/apps/update-tinyuf2.uf2'
# ports whose update-tinyuf2.uf2 is the bootloader BIN itself, written in place (ports/mimxrt10xx/CMakeLists.txt); the
# sector board_flash.c erases and programs is its _flash_cache's size (flashCache); every other port's is a self_update app
UPDATE_PORTS = {'mimxrt10xx'}
# the interrupt's raw write (SKILL.md Update, step 5): its alternating passes, its byte offset on the drive (TinyUF2
# takes a UF2 block anywhere: src/ghostfat.c uf2_write_block) and the child's bound in s
INTERRUPT_PASSES, INTERRUPT_OFFSET, INTERRUPT_TIMEOUT = 25, 0x100000, 120
# every block reaches the device before the write returns (O_DIRECT is Linux's, as is the runner)
WRITE_FLAGS = os.O_WRONLY | getattr(os, 'O_DIRECT', 0) | os.O_SYNC
JLINK_CONNECTED = r'(?m)^Cortex-M\w+ identified\.$'
UDEV_RULES = ('/etc/udev/rules.d', '/run/udev/rules.d')
# J-Link devices whose connect as the chip resets it to unprotect it (bench-history.md, stm32f411ve_discovery,
# stm32f407disco): (the core runner sessions connect as instead, ms the install's verify session waits before its halt
# after the flash's unlock, empirical)
JLINK_CONNECT_UNLOCKS = {'stm32f411ve': ('Cortex-M4', 1000), 'stm32f407vg': ('Cortex-M4', 1000)}


class Refused(Exception):
  """Exit 2: nothing on the board was touched."""


class StepFail(Exception):
  def __init__(self, msg, evidence=None):
    super().__init__(msg)
    self.evidence = evidence or {}


class NotInterrupted(StepFail):
  """The update battery's reset did not overlap its write: the board is still recovered before the run fails."""


class NotEnumerated(StepFail):
  """The DFU device never appeared: the only failure after an install that re-entry may follow."""


class Interrupted(Exception):
  interrupted = True   # what the flash provider reads to record an attempt as interrupted, not an error


class SpawnTimeout(StepFail):
  """A spawned child killed on its bound: its output so far and what of its session outlived SIGKILL."""
  def __init__(self, msg, output, survivors):
    super().__init__(msg)
    self.output, self.survivors = output, survivors


# ------------------------------------------------------------------ roster and board facts

def load_board(config, name):
  try:
    cfg = json.loads(Path(config).read_text())
    boards = [b for b in cfg['boards'] if b.get('name') == name]
  except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
    raise Refused(f'cannot read {config}: {e}')
  if len(boards) != 1:
    raise Refused(f'{config} has {len(boards)} entries named {name!r}')
  b = boards[0]
  fl, t = b.get('flasher') or {}, b.get('tinyuf2') or {}
  m = re.fullmatch(cb.FLASHER_ARGS.get(fl.get('name'), r'(?!)'), fl.get('args') or '')
  if not isinstance(fl.get('uid'), str) or not m:
    raise Refused(f'{name}: flasher must be jlink or stlink with args exactly "-device NAME", openocd with args exactly '
                  f'"-f interface/cmsis-dap.cfg -f target/TARGET.cfg", or esptool with args exactly "--chip CHIP", with a '
                  f'string uid')
  if not (cb.ROSTER_UID.fullmatch(fl['uid']) or fl['name'] == 'esptool' and cb.USJ_SERIAL.fullmatch(fl['uid'])):
    raise Refused(f'{name}: flasher uid {fl["uid"]!r} is neither a probe or bridge serial (letters, digits, _ and -) '
                  f'nor, for esptool, a USJ serial in its MAC form (AA:BB:CC:DD:EE:FF, upper case)')
  if fl['name'] == 'openocd' and not (isinstance(fl.get('vid_pid'), str) and re.fullmatch(cb.VID_PID, fl['vid_pid'])):
    raise Refused(f'{name}: an openocd flasher needs its probe\'s "vid_pid": "0xVVVV 0xPPPP"; unpinned, CMSIS-DAP '
                  f'discovery opens every USB device on the host')
  if not isinstance(b.get('uid'), str) or not b['uid']:
    raise Refused(f'{name}: uid (the bootloader USB serial) is required')
  lock = t.get('lock', name)   # tinyusb's name for the board when it differs: both runners take one lock
  if not (isinstance(lock, str) and re.fullmatch(r'[\w.-]+', lock)):
    raise Refused(f'{name}: tinyuf2.lock must be the board lock name')
  try:
    port = cb.port_of(name)
  except cb.Fail as e:
    raise Refused(f'{name}: the roster names a board by its TinyUF2 name: {e}')
  if fl['name'] == 'esptool':
    if m.group(1) not in esp.BOOTLOADER_OFFSET or port != 'espressif':
      raise Refused(f'{name}: esptool is supported for espressif chips {sorted(esp.BOOTLOADER_OFFSET)} only')
  elif m.group(1) not in FLASH_LIMITS:
    raise Refused(f'{name}: no programming limits known for {fl["name"]} device {m.group(1)}')
  elif fl['name'] == 'stlink' and m.group(1) not in STLINK_CHIPS:
    raise Refused(f'{name}: no chip identity known for ST-LINK device {m.group(1)}')
  power = t.get('usbPower')
  if power is not None:
    if not (isinstance(power, dict) and set(power) == {'hub', 'port'} and isinstance(power['hub'], str) and
            re.fullmatch(r'[\w-]+', power['hub']) and type(power['port']) is int and 1 <= power['port'] <= 15):
      raise Refused(f'{name}: tinyuf2.usbPower must be {{"hub": "<hub serial>", "port": <1-15>}}')
    if fl['name'] != 'jlink':
      raise Refused(f'{name}: tinyuf2.usbPower is for J-Link boards only')
  return {'name': name, 'lock': lock, 'uid': b['uid'], 'flasher': fl['name'], 'probe': fl['uid'], 'device': m.group(1),
          'kind': 'esp' if port == 'espressif' else fl['name'], 'if': JLINK_IF, 'speed': JLINK_SPEED, 'port': port,
          'reentry': t.get('reentry'), 'usbPower': power, 'routes': board_routes(name, port, m.group(1), t), 'route': None,
          **({'args': fl['args'], 'vid_pid': fl['vid_pid']} if fl['name'] == 'openocd' else {})}


def board_routes(name, port, chip, t):
  """tinyuf2.routes: an Espressif board's further install routes, [{"flasher": {name, uid, args}, "commissioning":
  "pending"}], each under the board's own lock. Only openocd_esp, for the chip the roster flasher names; a route
  still pending commissioning installs and restores only."""
  routes = t.get('routes', [])
  if not isinstance(routes, list):
    raise Refused(f'{name}: tinyuf2.routes must be a list')
  out = {}
  for r in routes:
    fl = r.get('flasher') if isinstance(r, dict) else None
    rname = fl.get('name') if isinstance(fl, dict) else None
    if port != 'espressif' or rname not in cb.ROUTE_ARGS or rname in out or set(r) - {'flasher', 'commissioning'} or \
       r.get('commissioning', 'pending') != 'pending' or not re.fullmatch(cb.ROUTE_ARGS[rname], fl.get('args') or ''):
      raise Refused(f'{name}: a tinyuf2.routes entry must be {{"flasher": {{"name": "openocd_esp", "uid": "<USJ serial>", '
                    f'"args": "-f board/<chip>-builtin.cfg"}}}}, optionally "commissioning": "pending", on an Espressif '
                    f'board, one per route: {r!r}')
    try:
      route_chip, _ = openocd_esp().admit(fl)
    except ValueError as e:
      raise Refused(f'{name}: route {rname}: {e}')
    if route_chip != chip:
      raise Refused(f'{name}: route {rname} reaches an {route_chip}; the roster flasher names {chip}')
    if route_chip not in openocd_esp().SECURITY_CHIPS:   # its security state is never read, so nothing is programmed
      raise Refused(f'{name}: route {rname}: the provider reads the security state of {openocd_esp().SECURITY_CHIPS} '
                    f'only, not {route_chip}')
    out[rname] = {'flasher': dict(fl), 'pending': r.get('commissioning') == 'pending'}
  return out


def select_route(board, route, run=False):
  """The board as `route` installs it, chosen before any board access and never switched after a failure: its
  roster flasher, or one of tinyuf2.routes, whose USJ serial then also selects the esptool sessions' tty. A route
  pending commissioning installs and restores only."""
  if route in (None, board['flasher']):
    return board
  r = board['routes'].get(route)
  if r is None:
    raise Refused(f'{board["name"]}: no install route {route} (roster flasher {board["flasher"]}, tinyuf2.routes '
                  f'{sorted(board["routes"])})')
  if run and r['pending']:
    raise Refused(f'{board["name"]}: route {route} is pending commissioning: install and restore only')
  refuse_openocd(route)
  return dict(board, flasher=route, probe=r['flasher']['uid'], route=r['flasher'])


def refuse_openocd(route):
  """The provider's refusal of an openocd_esp session, or of board access preparing one; this runner keeps the board
  lock through a session left pending (its cleanup holder), so it declares retains_lock."""
  if route == 'openocd_esp' and (why := openocd_esp().refusal(retains_lock=True)):
    raise Refused(why)


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


def cmake_var(path, name):
  """The value of the one `set(NAME value)` in a CMake file, ${TOP}/ read as the checkout; nothing else."""
  hits = re.findall(rf'\bset\s*\(\s*{name}\b([^)]*)\)', cb.code_lines(ROOT / path), re.I)
  if len(hits) != 1:
    raise Refused(f'{path}: expected one set({name} ...), found {len(hits)}')
  v = hits[0].strip().removeprefix('${TOP}/')
  if not v or re.search(r'[\s${}"]', v):
    raise Refused(f'{path}: set({name} {hits[0].strip()}) is not one plain value')
  return v


def record_facts(record_path, board, workdir):
  """The board's facts: an Espressif board's from the candidate's source (esp_source_facts), any other's from its
  build record, board_facts.read over hash-checked copies of the files it reads."""
  if board.get('kind') == 'esp':
    return esp_source_facts(board)
  _, row, root, _ = record_row(record_path, board)
  rels = (*cb.FACTS_FILES, CMAKE_RECORD_FILES[0], '_bin/tinyuf2.hex')
  if not all(r in row.get('sha256', {}) for r in rels):
    raise Refused(f'{record_path}: no board facts in the record (rebuild it: check_build.py --board {board["name"]} '
                  f'--shared --hil-config <roster>)')
  copied(root, rels, row, workdir / 'facts')
  try:
    return bf.read(workdir / 'facts', FLASH_LIMITS[board['device']])
  except (bf.Refused, OSError) as e:
    raise Refused(f'{record_path}: {e}')


def esp_source_facts(board):
  bdir = f'ports/{board["port"]}/boards/{board["name"]}'
  if not (ROOT / bdir).is_dir():
    raise Refused(f'{bdir} does not exist')
  try:
    facts = esp.facts(ROOT, board)
  except (esp.Refused, OSError, ValueError) as e:
    raise Refused(str(e))
  delay = re.search(r'^\s*#\s*define\s+UF2_DETECTION_DELAY_MS\s+(\d+)', (ROOT / bdir / 'board.h').read_text(), re.M)
  facts.update(vid=num(define(f'{bdir}/board.h', 'USB_VID'), 'USB_VID'),
               pid=num(define(f'{bdir}/board.h', 'USB_PID'), 'USB_PID'),
               boardId=define(f'{bdir}/board.h', 'UF2_BOARD_ID').strip('"'),
               detectionDelayMs=int(delay.group(1)) if delay else
               num(define('ports/espressif/bootloader_components/main/bootloader_start.c', 'UF2_DETECTION_DELAY_MS'),
                   'UF2_DETECTION_DELAY_MS'),
               appVid=num(define(f'apps/{cb.HIL_APP}/src/usb_descriptors.c', 'APP_USB_VID'), 'APP_USB_VID'),
               appPid=num(define(f'apps/{cb.HIL_APP}/src/usb_descriptors.c', 'APP_USB_PID'), 'APP_USB_PID'),
               family=int(cmake_var('ports/espressif/family.cmake', f'UF2_FAMILY_ID_{board["device"]}'), 16),
               flashCache=product(define('ports/espressif/boards/board_flash.c', 'FLASH_CACHE_SIZE'), 'FLASH_CACHE_SIZE'))
  return facts


def apply_layout(board, facts):
  """The install and app spans, from the candidate's facts: the bootloader from the flash base up to the app
  start, the app from there to the end of the board's flash, all inside the device's programming limits."""
  if board.get('kind') == 'esp':
    try:
      lay = esp.layout(facts, board['device'])
    except esp.Refused as e:
      raise Refused(str(e))
    board.update(regions=lay, app=lay['app'])
    return
  base, start, end = facts['flashBase'], facts['appStart'], facts['flashBase'] + facts['flashSize']
  floor, ceiling = FLASH_LIMITS[board['device']]
  if not floor <= base < start < end <= ceiling:
    raise Refused(f'{board["name"]}: flash [{base:#x}, {end:#x}) with app start {start:#x} leaves the '
                  f'{board["device"]} flash [{floor:#x}, {ceiling:#x}) or is out of order')
  board.update(install=(base, start), app=(start, end))


# ------------------------------------------------------------------ images

def parse_hex(path):
  """{address: bytes} of an Intel HEX file; checksums verified."""
  try:
    return bf.parse_hex(path)
  except bf.Refused as e:
    raise Refused(str(e))


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
  """Whether a bootloader BIN is its HEX laid out from `base`: the HEX fixes the base the BIN lacks."""
  return bf.hex_matches_bin(data, Path(bin_path).read_bytes(), base)


def verify_images(data, workdir):
  """[(address, file)] reading back what the HEX programs: one file per contiguous run, since a gap the BIN fills
  with zeros keeps the flash's erased state (lpc55: [0x130, 0x200))."""
  runs = []
  for a in sorted(data):
    if runs and runs[-1][0] + len(runs[-1][1]) == a:
      runs[-1][1].append(data[a])
    else:
      runs.append((a, bytearray([data[a]])))
  for a, run in runs:
    (Path(workdir) / f'hex-{a:x}.bin').write_bytes(run)
  return [(a, Path(workdir) / f'hex-{a:x}.bin') for a, _ in runs]


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
  vectors = [facts['ram'] + bf.STACK, handler | 1] + [fault | 1] * (table // 4 - 2)
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


def contiguous_uf2(uf2_path, family, base, what):
  """The blocks of `uf2_path`: one family, numbered under one numBlocks, 256 bytes each, contiguous from `base`."""
  try:
    blocks = parse_uf2(Path(uf2_path).read_bytes())
  except (OSError, ValueError) as e:
    raise Refused(f'{what}: {uf2_path}: {e}')
  for i, bl in enumerate(blocks):
    if (bl['no'], bl['total'], bl['family'], bl['addr'], bl['size']) != (i, len(blocks), family, base + 256 * i, 256) \
       or not bl['flags'] & UF2_FLAG_FAMILY:
      raise Refused(f'{what}: {uf2_path} block {i} is not block {i} of {len(blocks)} for family {family:#x} at '
                    f'{base + 256 * i:#x}')
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
REGISTERING = {'on': False, 'signum': None}


@contextlib.contextmanager
def registering():
  """Defer an interrupt until the block ends: Popen's child is in CHILDREN before Interrupted can
  unwind, so cleanup sees it. Deferring, not masking, leaves the child's inherited signal mask as is."""
  REGISTERING.update(on=True, signum=None)
  try:
    yield
  finally:
    REGISTERING['on'] = False
    signum, REGISTERING['signum'] = REGISTERING['signum'], None
    if signum:
      raise Interrupted(f'interrupted by {signal.Signals(signum).name}')


def spawn(cmd, log, timeout, cwd=None, stderr_to_log=False, env=None):
  """Run a child in its own process group with a bound; a child that survives SIGKILL (D state on a
  stuck USB device) is left in CHILDREN for cleanup to see. Children spawned during cleanup inherit its
  blocked SIGTERM and SIGINT, so only SIGKILL (reap) may be relied on to end them. With `stderr_to_log`, the
  child's stderr goes to the log only and the output returned is its stdout. `env` adds to the environment.
  A timeout raises SpawnTimeout and an interruption Interrupted, each carrying the output so far."""
  return collect(launch(cmd, log, cwd, stderr_to_log, env), cmd, log, timeout)


def launch(cmd, log, cwd=None, stderr_to_log=False, env=None):
  """spawn()'s child started, tracked in CHILDREN, not waited for: collect() ends it."""
  with open(log, 'a') as f:
    f.write('$ ' + ' '.join([f'{k}={v}' for k, v in (env or {}).items()] + list(map(str, cmd))) + '\n')
    f.flush()
    with registering():
      p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                           stderr=f if stderr_to_log else subprocess.STDOUT, text=True, errors='replace',
                           start_new_session=True, cwd=cwd, env=env and {**os.environ, **env})
      CHILDREN.append(p)
  return p


def collect(p, cmd, log, timeout):
  """spawn()'s wait for a launch()ed child: (exit, output), within `timeout`."""
  with open(log, 'a') as f:
    try:
      out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as e:
      left = reap(p)
      partial = text(e.output, p.stdout.encoding)
      f.write(partial)
      raise SpawnTimeout(f'{Path(str(cmd[0])).name} timed out after {timeout}s', partial, left)
    except Interrupted as e:   # left for cleanup's reap; what communicate read so far is only in its own buffer
      e.stdout = text(b''.join(getattr(p, '_fileobj2output', {}).get(p.stdout, [])), p.stdout.encoding)
      f.write(e.stdout)
      raise
    f.write(out)
    if not session(p.pid):   # else a process it started lives on, tracked for cleanup's reap
      CHILDREN.remove(p)
    return p.returncode, out


def proc_stat(pid):
  """proc(5) stat fields from the third (state) on, or None for a process that is gone or a zombie."""
  try:
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
  except (OSError, IndexError):
    return None
  return fields if fields and fields[0] != 'Z' else None


def session(sid):
  """The live processes of session `sid` (stat field 6): a child started with start_new_session and everything it
  started, a process ninja moved into a group of its own included."""
  return [int(d.name) for d in Path('/proc').iterdir()
          if d.name.isdigit() and (st := proc_stat(d.name)) and st[3] == str(sid)]


def reap(p):
  """SIGKILL to the child's whole session; the members still alive after KILL_WAIT (D state on a stuck USB
  device), empty once the session is gone."""
  for pid in session(p.pid):
    with contextlib.suppress(ProcessLookupError):
      os.kill(pid, signal.SIGKILL)
  with contextlib.suppress(subprocess.TimeoutExpired):
    p.wait(KILL_WAIT)
  end = time.monotonic() + KILL_WAIT
  while (left := session(p.pid)) and time.monotonic() < end:
    time.sleep(0.1)
  if not left and p in CHILDREN:   # tracked while any of its session lives, for cleanup to see
    CHILDREN.remove(p)
  if p.stdout:   # nothing more is read from a killed child
    with contextlib.suppress(OSError):
      p.stdout.close()
  return left


def proc_start(pid):
  """The start time of a live `pid` in clock ticks (proc(5) stat field 22), which tells a reused pid apart."""
  st = proc_stat(pid)
  return int(st[19]) if st and len(st) > 19 else None


def still_alive(survivors):
  """The survivors still alive: a process by its pid and start time; a container, which only a report from a runner
  that still ran the IDF flash target or its dry runs names, unless docker has listed it no more for check_build's
  settle (cb.container_left), and never while a process of the same report lives, which may still create it (#580)."""
  sessions = [s for s in survivors if 'receipt' in s and session_state(s) in ('running', 'unreadable')]
  procs = [s for s in survivors if 'container' not in s and 'receipt' not in s and s.get('start') is not None
           and proc_start(s['pid']) == s['start']]
  return procs + sessions + [s for s in survivors if 'container' in s and (procs or cb.container_left(s['container']))]


class CleanupPending(StepFail):
  """A flash left a child or an openocd_esp session running: no session may follow or overlap it, and the board and
  build locks stay held until it ends (a session: until recovery ends it by its receipt)."""


OPENOCD_SESSIONS = 'hil_openocd_esp_*/receipt.json'   # flash_openocd_esp's session dirs under the run dir
PROTECTED_SESSIONS = []   # every receipt an openocd_esp operation of this process returned, by path or record
# the board's pending-session record, <lock>.tinyuf2-openocd-pending.json beside its lock (hil_lock.PendingSessions):
# sessions no later invocation may overlap
PENDING_KIND = 'tinyuf2-openocd'
MARK_ERRORS = []   # every failure to write the mark this process met, for the report


def session_entry(receipt):
  """A survivor entry for one openocd_esp receipt: its path, or the record itself when the provider could not write
  it; its pid and start time for the report only, as session_state (the provider's) alone decides liveness."""
  rec = receipt if isinstance(receipt, dict) else read_receipt(receipt) or {}
  e = {'cmd': 'openocd', 'receipt': receipt if isinstance(receipt, dict) else str(receipt)}
  with contextlib.suppress(KeyError, TypeError, ValueError):
    e.update(pid=rec['pid'], start=int(rec['startTime']))
  return e


def read_receipt(path):
  try:
    rec = json.loads(Path(path).read_text())
  except (OSError, ValueError):
    return None
  return rec if isinstance(rec, dict) else None


def session_state(e):
  """An openocd_esp session's state from its receipt, the provider's session_state reread on every call, and
  'unreadable' while the provider cannot be loaded: every hold stays."""
  try:
    oe = openocd_esp()
  except Refused:
    return 'unreadable'
  return oe.session_state(e['receipt'])


def merge_sessions(old, new):
  """`old`, then each entry of `new` whose receipt no earlier entry has; compared by equality, as a receipt may be
  the provider's record itself."""
  merged = list(old)
  for e in new:
    if all(e['receipt'] != m['receipt'] for m in merged):
      merged.append(e)
  return merged


def protect(op):
  """Keep every receipt an openocd_esp operation reports, on disk or in memory, whatever the run dir holds."""
  PROTECTED_SESSIONS[:] = merge_sessions(PROTECTED_SESSIONS, [session_entry(a.receipt) for a in
                                                              getattr(op, 'attempts', ()) if a.receipt is not None])


def outstanding_sessions(workdir):
  """The openocd_esp sessions of this run not ended by the reviewed end: the receipts under `workdir`, which the
  provider writes before an interrupt can be acted on, and every receipt an operation returned (protect()), the
  record itself when the provider could not write it. Never children to reap: a killed openocd can leave the chip
  in its Breakpoint boot loop."""
  found = merge_sessions([session_entry(r) for r in sorted(Path(workdir).glob(OPENOCD_SESSIONS))], PROTECTED_SESSIONS)
  return [e for e in found if session_state(e) != 'ended']


def pending_mark(helper, lock):
  """A board's pending mark, the lock helper's pending-session record of this runner's openocd_esp sessions."""
  return helper.PendingSessions(lock, PENDING_KIND)


def mark_pending(mark, sessions):
  """Record sessions not ended beside the board's lock, so another invocation, in another run dir, refuses too.
  Never raises: a failure, an unreadable mark included (kept as it is), is returned and kept in MARK_ERRORS for the
  report, and the caller's survivor reporting and lock ownership go on as without a mark."""
  if not mark or not sessions:
    return None
  try:
    mark.add(sessions)
    return None
  except Exception as e:   # PendingRefused (unreadable), ValueError (a malformed session) or OSError
    err = f'the pending mark {mark} could not be written: {type(e).__name__}: {e}'
    MARK_ERRORS.append(err)
    return err


def clear_pending_mark(mark, note=None, hold=None):
  """Remove the mark once every session it lists reads ended (as `hil_openocd_esp.py end` leaves its receipt), or,
  given the note of a separately reviewed recovery, whatever it holds, the note and `hold` logged first. Refuses
  otherwise, naming the receipts. Returns what was cleared."""
  ended = lambda e: session_state(e) == 'ended'   # noqa: E731
  try:
    return mark.clear(ended) if note is None else mark.clear(ended, note=note, hold=hold)
  except RuntimeError as e:   # PendingRefused: kept as it is
    raise Refused(f'{e}: end each openocd_esp session with `hil_openocd_esp.py end --receipt <receipt>`, or clear the '
                  'mark after a separately reviewed recovery (SKILL.md Recovery)') from None
  except OSError as e:
    raise Refused(f'the pending mark {mark} could not be checked: {e}') from None


def reviewed_receipts(mark):
  """Every receipt a reviewed recovery's clear-pending recorded in the mark's cleared log: the mark's sessions and the
  survivors of the cleanup holder it proved."""
  try:
    entries = mark.cleared()
  except OSError as e:
    raise Refused(f'the cleared log of {mark} could not be read: {e}') from None
  found = []
  for x in entries:
    with contextlib.suppress(TypeError, AttributeError):
      found += [e['receipt'] for e in (x.get('sessions') or []) + ((x.get('hold') or {}).get('survivors') or [])
                if isinstance(e, dict) and 'receipt' in e]
  return found


def refuse_pending(workdir, mark=None):
  left = outstanding_sessions(workdir)
  err = mark_pending(mark, left)
  if left:
    raise CleanupPending(f'openocd_esp session {[s["receipt"] for s in left]} is still running: cleanup pending, no '
                         'session may overlap it', {'survivors': left, **({'markError': err} if err else {})})


# ------------------------------------------------------------------ the flash provider

PROVIDER = []   # the one hil_flash module this process loads (provider())
PROVIDER_API = ('flash_jlink', 'flash_stlink', 'flash_openocd', 'run_jlink_commands', 'run_stlink_commands',
                'run_openocd_commands', 'sysresetreq_jlink', 'sysresetreq_stlink', 'sysresetreq_openocd', 'Operation',
                'Attempt')
OPENOCD = []    # and its openocd_esp module (openocd_esp())
OPENOCD_API = ('admit', 'find_openocd', 'usj_tty', 'usj_node', 'session_state', 'security_evidence', 'admit_security',
               'SECURITY_CHIPS', 'flash_openocd_esp', 'refusal')
OBSERVE = []    # and its bounded USB observation (usb_observe())
OBSERVE_API = ('usb_devices', 'usb_node_serial', 'udev_serial', 'read_sysfs', 'enumeration_id')
USB_OBSERVE = LOCK_HELPER.with_name('usb_observe.py')
CORE = []       # and the report core (report_core())
CORE_API = ('BodySchema', 'READABLE', 'ReportError', 'read_document', 'start_attempt', 'make_meta', 'publish', 'table',
            'roster_identity')


def load_pinned(path, name, api, what='flash provider'):
  """A lib/agentrc module at the commit HEAD pins, loaded by path, never an installed agentrc's; Refused when the
  submodule is off its pin or the module lacks what the runner calls."""
  check_lock_pin()
  try:
    mod = run_report.load_agentrc(path, name)
  except Exception as e:
    raise Refused(f'{what} {path} failed to load: {e}')
  missing = [n for n in api if not hasattr(mod, n)]
  if missing:
    raise Refused(f'{what} {path}: lacks {missing}; recheck this contract')
  return mod


def provider():
  """hil_flash.py, once per process."""
  if not PROVIDER:
    mod = load_pinned(FLASH_PROVIDER, 'agentrc_hil_flash', PROVIDER_API)
    if (getattr(mod, 'SCB_AIRCR', None), getattr(mod, 'AIRCR_SYSRESETREQ', None)) != (SCB_AIRCR, AIRCR_SYSRESETREQ):
      raise Refused(f'flash provider {FLASH_PROVIDER} writes another SYSRESETREQ; recheck this contract')
    PROVIDER.append(mod)
  return PROVIDER[0]


def openocd_esp():
  """hil_openocd_esp.py, once per process, only for a board with a route through it."""
  if not OPENOCD:
    OPENOCD.append(load_pinned(OPENOCD_ESP, 'agentrc_hil_openocd_esp', OPENOCD_API))
  return OPENOCD[0]


def usb_observe():
  """usb_observe.py, once per process: a probe found by serial without a read that can hang on a wedged peer."""
  if not OBSERVE:
    OBSERVE.append(load_pinned(USB_OBSERVE, 'agentrc_usb_observe', OBSERVE_API, 'USB observation'))
  return OBSERVE[0]


def report_core():
  """hil_report_core.py, once per process: every report this runner writes or a recovery reads goes through it."""
  if not CORE:
    CORE.append(load_pinned(REPORT_CORE, 'agentrc_hil_report_core', CORE_API, 'report core'))
  return CORE[0]


def command_argv(cmd):
  """A provider command's argv: every command is an argv list (`hil` Flashers); a shell string is refused, as no shell
  runs it."""
  if isinstance(cmd, (str, bytes)):
    raise TypeError(f'a provider command is an argv list, not a shell string: {cmd!r}')
  return [str(c) for c in cmd]


def tool_runner(log):
  """The flash provider's `run=`: each command one tracked spawn child, its transcript in `log`, `env` added to the
  environment, its session killed on the bound and a survivor kept in CHILDREN for cleanup. A timeout returns rc 124
  with the output so far (the provider records the attempt as timed out); an interruption raises Interrupted carrying
  it. Cleanup is 'done' only when nothing of the child's session is left, else 'unknown' (cleanup reaps it).
  Executed directly, a tool that dies by a signal reports -N."""
  def run(cmd, cwd=None, *, env=None, timeout):
    argv = command_argv(cmd)
    tracked = len(CHILDREN)
    try:
      code, out = spawn(argv, log, timeout, cwd=cwd, env=env)
    except SpawnTimeout as e:
      code, out = 124, e.output
    r = subprocess.CompletedProcess(argv, code, out, None)
    r.cleanup = 'done' if len(CHILDREN) == tracked else 'unknown'   # 'done': nothing of its session is left
    return r
  return run


def text(out, encoding='utf-8'):
  return out.decode(encoding, 'replace') if isinstance(out, bytes) else out or ''


def operation_record(op):
  """What the report keeps of a provider operation: each attempt's kind and exit, never their output joined (the
  transcripts are in hil.log), its cleanup and any outstanding session's receipt."""
  return {'attempts': [{'kind': a.kind, 'exit': a.result.returncode} for a in op.attempts], 'cleanup': op.cleanup,
          **({'receipts': [str(r) for r in op.receipts]} if op.receipts else {})}


def before_target(attempts, before):
  """Every attempt ended before any target connect (before(code, out)); a timed-out one never did, since its output
  so far does not show how far it got."""
  return all(not a.timed_out and before(a.result.returncode, text(a.result.stdout)) for a in attempts)


def judged(op, judge, before, what, timeout):
  """judge(code, out) of the operation's last attempt. A failure's `beforeTarget` holds only when every attempt ended
  before any target connect (before(code, out)); a timed-out one never does, since its output so far does not show
  how far it got."""
  attempts = op.attempts
  out = text(attempts[-1].result.stdout)
  timed_out = any(a.timed_out for a in attempts)
  try:
    if timed_out:
      raise StepFail(f'{what} timed out after {timeout}s', {'tail': out.strip().splitlines()[-5:]})
    ev = judge(attempts[-1].result.returncode, out)
  except StepFail as e:
    e.evidence.update(beforeTarget=before_target(attempts, before), operation=operation_record(op))
    raise
  return dict(ev, operation=operation_record(op))


# ------------------------------------------------------------------ build locks

BUILD_LOCK_WAIT = 2   # s a flash waits for a build dir's lock: a keeper (keep_build_lock) polls every KEEPER_POLL
KEEPER_POLL = 1
HELD_BUILD = []   # (lock file, survivors) this process keeps itself when no keeper could start


def take_build_lock(root):
  """check_build's lock of the build dir `root`, as an open file held until it is closed or kept; StepFail when a
  build, another flash or a keeper still holds it after BUILD_LOCK_WAIT."""
  path = cb.build_lock_file(root)
  path.parent.mkdir(parents=True, exist_ok=True)
  fh = open(path, 'a')
  end = time.monotonic() + BUILD_LOCK_WAIT
  while True:
    try:
      fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
      return fh
    except BlockingIOError:
      if time.monotonic() >= end:
        fh.close()
        raise StepFail(f'{root.name} is in use by a build or another flash; nothing was flashed')
      time.sleep(0.2)


def survivor(pid):
  try:
    cmd = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:3]
  except OSError:
    cmd = []
  return {'pid': pid, 'start': proc_start(pid), 'cmd': [c.decode(errors='replace') for c in cmd]}


def settle_children(started=()):
  """Reap every child started since `started` (CHILDREN then; by default every one) that is still tracked: an
  interrupted one, or what of a timed-out one outlived its kill. Returns the processes still alive after SIGKILL,
  identified so a later recovery can tell they are still alive."""
  left = []
  for p in [p for p in CHILDREN if p not in started]:
    left += [survivor(pid) for pid in reap(p)]
  return left


def keep_build_lock(fh, survivors):
  """Hand a build dir's lock to a detached keeper while processes that may still read the tree survive (#579): it
  shares the open file description, re-executes itself as `keep-build` without the job tracking variable (as
  exec_holder), ignores SIGTERM and SIGINT, and exits, releasing the lock, once none of `survivors` lives. Its
  acknowledgement comes only once it runs; without one this process keeps the lock and waits for them before it
  exits (main)."""
  try:
    r, w = os.pipe()
    pid = os.fork()
  except OSError:
    pid = None
  if pid == 0:
    try:
      for sig in TERM_SIGNALS:
        signal.signal(sig, signal.SIG_IGN)
      os.close(r)
      os.setsid()
      for fd in (fh.fileno(), w):
        os.set_inheritable(fd, True)
      env = {k: v for k, v in os.environ.items() if k != JOB_TRACKING}
      with contextlib.suppress(OSError):
        os.execve(sys.executable, [sys.executable, '-B', str(HOLDER_SCRIPT), 'keep-build', str(fh.fileno()), str(w),
                                   json.dumps(survivors)], env)
    finally:
      os._exit(1)
  if pid:
    os.close(w)
    ready, _, _ = select.select([r], [], [], 10)
    ack = os.read(r, 16) if ready else b''
    os.close(r)
    if ack == b'ok':
      fh.close()   # the keeper's description now; never LOCK_UN
      return {'pid': pid}
    with contextlib.suppress(ProcessLookupError):
      os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(ChildProcessError):
      os.waitpid(pid, 0)
  HELD_BUILD.append((fh, survivors))
  return {'pid': os.getpid(), 'inProcess': True}


def release_ended_builds():
  """Close each build lock this process keeps (HELD_BUILD) once none of its survivors lives; the ones still kept."""
  for kept in [k for k in HELD_BUILD if not still_alive(k[1])]:
    kept[0].close()
    HELD_BUILD.remove(kept)
  return HELD_BUILD


def keep_build(survivors):
  """The keeper's wait (keep_build_lock): its stdio closed, it polls until no survivor lives, then exits, which
  releases the lock it inherited."""
  for std in (0, 1, 2):
    with contextlib.suppress(OSError):
      os.close(std)
  while still_alive(survivors):
    time.sleep(KEEPER_POLL)
  os._exit(0)


# ------------------------------------------------------------------ probe

def died_at_probe_connect(code, out, probe):
  """libjlinkarm's crash at the probe connect (SKILL.md, Limits): SIGSEGV or SIGABRT with this probe's
  serial as the last J-Link line, before any target connect, so the session changed nothing and may run again.
  Any other death leaves the target's state unknown."""
  lines = [x.strip() for x in out.splitlines() if x.strip() and not re.match(r'(double free|free\(\)|malloc|corrupted )', x)]
  last = re.fullmatch(r'S/N: (\d+)', lines[-1]) if lines else None
  return code in (-signal.SIGSEGV, -signal.SIGABRT) and bool(last) and int(last.group(1)) == int(probe) and \
    'Connecting to target' not in out


def stopped_before_target(code, out, probe):
  """A session recognised as ending before any target connect, so it changed nothing: no probe with the serial
  (bench: "Connecting to J-Link ...FAILED", then nothing more), or the crash at the probe connect. Any other
  failure, an empty transcript included, may have reached the target."""
  no_probe = re.search(r'^Connecting to J-Link \.\.\.FAILED', out, re.M) and 'Connecting to target' not in out
  return bool(no_probe) or died_at_probe_connect(code, out, probe)


def jlink_failure(code, out, probe):
  return {'tail': out.strip().splitlines()[-5:], 'beforeTarget': stopped_before_target(code, out, probe)}


def judge_jlink_target(op, board, hex_path):
  """The provider's J-Link flash (the record's tinyuf2-jlink script), judged by its jlink_problem, and this HEX
  downloaded, programmed or already matching, then O.K., in the output of the script's own `loadfile`."""
  code, out = op.attempts[-1].result.returncode, text(op.attempts[-1].result.stdout)
  load = f'loadfile {hex_path}'
  m = re.search(rf'^Downloading file \[{re.escape(str(hex_path))}\]\.\.\.$(?:\n.*)*?\nJ-Link: Flash download: Bank \d+ @ '
                r'0x[0-9A-F]+: (Skipped\. Contents already match|\d+ ranges? affected \(\d+ bytes\))$(?:\n.*)*?\nO\.K\.$',
                next(iter(provider().jlink_after(out, load)), ''), re.M)
  if problem := provider().jlink_problem(op) or ('' if m else f'no download of {hex_path} in its {load!r}'):
    raise StepFail(f'the J-Link flash failed (exit {code})', {**jlink_failure(code, out, board['probe']), 'problem': problem})
  return {'flashDownload': m[1]}


def judge_esp_target(code, out, segments):
  """The provider's esptool flash, judged by its esptool_flash_judgment over every segment's offset."""
  judged = provider().esptool_flash_judgment(out, [off for off, _ in segments])
  if code or not judged['ok']:
    raise StepFail(f'the esptool flash failed (exit {code})', {'tail': ANSI.sub('', out).strip().splitlines()[-5:],
                                                              'problem': judged['problem']})
  return {'wrote': [hex(a) for a in sorted(judged['wrote'])]}


class Probe:
  """J-Link sessions of the runner's, each through the flash provider's run_jlink_commands with tinyuf2's session
  profile, judged here."""
  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log
    self.retried = []
    self.flasher = {'name': 'jlink', 'uid': board['probe'], 'args': f'-device {board["device"]}'}
    # SWD at 4000 kHz, autoconnect, and the core for a device whose own connect resets the chip (JLINK_CONNECT_UNLOCKS)
    unlocks = JLINK_CONNECT_UNLOCKS.get(board['device'])
    self.profile = {'interface': board['if'], 'speed': board['speed'], 'autoconnect': True,
                    'device': unlocks[0] if unlocks else board['device'], 'timeout': PROBE_TIMEOUT, 'workdir': workdir}

  def run(self, commands, judge=True):
    """One JLinkExe session, each command judged from its own output (jlink_problem). judge=False is for a
    lone `w4` that resets the target, which may drop the connection mid-transaction: only its issue on a connected
    target is judged (the core identified, then J-Link's "Writing VALUE -> ADDR", with no failure before it), and
    the caller's observation is the evidence."""
    return self.session(lambda **kw: provider().run_jlink_commands(self.flasher, list(commands), **kw, **self.profile),
                        commands, judge)

  def sysreset(self):
    """The provider's SYSRESETREQ session (the AIRCR write), judged on its issue."""
    return self.session(lambda **kw: provider().sysresetreq_jlink(self.flasher, **kw, **self.profile),
                        [f'w4 {SCB_AIRCR:08X} {AIRCR_SYSRESETREQ:08X}'], judge=False)

  def failure(self, op):
    """jlink_failure over every attempt: before the target only when each one ended there; a rerun the provider
    refused names why."""
    return {'tail': text(op.attempts[-1].result.stdout).strip().splitlines()[-5:],
            'beforeTarget': before_target(op.attempts, lambda code, out: stopped_before_target(code, out, self.b['probe'])),
            **({'retryRefused': op.retry_refused} if op.retry_refused else {})}

  def session(self, op, commands, judge):
    """One provider session, rerun once, JLINK_RETRY_DELAY later, when it died at the probe connect
    (died_at_probe_connect); the provider refuses that rerun unless the runner proved the attempt's session ended."""
    def crashed(a):
      code = a.result.returncode
      if not died_at_probe_connect(code, text(a.result.stdout), self.b['probe']):
        return False
      with open(self.log, 'a') as f:
        f.write(f'# JLinkExe died (exit {code}) at the probe connect, before the target; retrying once\n')
      return True
    res = op(run=tool_runner(self.log), retry_if=crashed, retry_delay=JLINK_RETRY_DELAY)
    self.retried += [{'exit': a.result.returncode, 'commands': list(commands)} for a in res.retried]
    code, out = res.attempts[-1].result.returncode, text(res.attempts[-1].result.stdout)
    if res.attempts[-1].timed_out:
      raise StepFail(f'JLinkExe timed out after {PROBE_TIMEOUT}s', self.failure(res))
    # a crash fails even a reset session (judge=False): its commands may not have run
    if code < 0:
      raise StepFail(f'JLinkExe failed (exit {code})', self.failure(res))
    if judge and (problem := provider().jlink_problem(res)):
      raise StepFail(f'JLinkExe failed (exit {code})', {**self.failure(res), 'problem': problem})
    if not judge and commands[-1].startswith('w4 '):
      _, addr, value = commands[-1].split()
      head, issued, _ = next(iter(provider().jlink_after(out, commands[-1])), '').partition(f'Writing {value} -> {addr}')
      if not issued or not re.search(JLINK_CONNECTED, head) or re.search(provider().JLINK_ERRORS, head):
        raise StepFail(f'the reset write was not issued on a connected target (exit {code})', self.failure(res))
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


def chip_reported(out, board):
  dev, nvm = STLINK_CHIPS[board['device']]
  return bool(re.search(rf'^Device ID\s*: {dev}$', out, re.M) and re.search(rf'^NVM size\s*: {nvm}$', out, re.M))


def stlink_failure(out):
  """A session recognised as ending before any target connect: no ST-LINK with the serial (bench: "Error: Serial
  number not found", before any device line). Any other failure may have reached the target."""
  before = re.search(r'^Error: Serial number not found', out, re.M) and not re.search(r'^Device ID', out, re.M)
  return {'tail': out.strip().splitlines()[-5:], 'beforeTarget': bool(before)}


def judge_stlink_target(code, out, board):
  """The provider's ST-LINK flash transcript, the record's tinyuf2-stlink command (bench, STM32CubeProgrammer
  v2.23.0): the roster's chip, the HEX downloaded and the start command's success, with no error line."""
  out = ANSI.sub('', out)
  m = re.search(r'^Opening and parsing file: tinyuf2\.hex$(?:\n.*)*?\nErasing internal memory sectors? \[?([\d ]+)\]?$'
                r'(?:\n.*)*?\nFile download complete$(?:\n.*)*?\nStart operation achieved successfully$', out, re.M)
  if code or not m or not chip_reported(out, board) or re.search(r'^Error', out, re.M):
    raise StepFail(f'the ST-LINK flash failed (exit {code})', stlink_failure(out))
  return {'flashDownload': 'File download complete', 'erasedSectors': m[1].split()}


class StlinkProbe:
  """One STM32CubeProgrammer CLI connection per session, through the flash provider's run_stlink_commands: a script
  that connects to the roster's ST-LINK without a reset (HOTPLUG), then runs `ops` in order. The CLI stops at the
  first failed operation and exits 1 (bench, v2.23.0); success is read from the transcript too: the roster's chip,
  every script line echoed in order with its success line, no error line, the script's end."""

  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log
    self.retried = []   # the report's jlinkRetried: a CLI session is never retried
    self.flasher = {'name': 'stlink', 'uid': board['probe'], 'args': f'-device {board["device"]}'}
    self.profile = {'connect_mode': 'HOTPLUG', 'timeout': PROBE_TIMEOUT, 'workdir': workdir}

  def run(self, ops):
    """Each operation's output, in order."""
    return self.judge(provider().run_stlink_commands(self.flasher, list(ops), run=tool_runner(self.log),
                                                     **self.profile), ops)

  def sysreset(self):
    """The provider's SYSRESETREQ session: `-w32` with `-nv`."""
    op = provider().sysresetreq_stlink(self.flasher, run=tool_runner(self.log), **self.profile)
    return self.judge(op, op.attempts[-1].script.splitlines()[1:])

  def judge(self, op, ops):
    a = op.attempts[-1]
    code, out, lines = a.result.returncode, ANSI.sub('', text(a.result.stdout)), a.script.splitlines()
    if a.timed_out:
      raise StepFail(f'STM32_Programmer_CLI timed out after {PROBE_TIMEOUT}s', dict(stlink_failure(out), beforeTarget=False))
    parts = re.split(r'(?m)^Operation \[(\d+)\]: (.*?) *$', out)
    if code or list(zip(parts[1::3], parts[2::3])) != [(str(i), x) for i, x in enumerate(lines, 1)] or \
       re.search(r'^Error', out, re.M) or not chip_reported(parts[3] if len(parts) > 3 else '', self.b) or \
       '=== Script Manager END ===' not in parts[-1] or \
       any(STLINK_DONE[re.split(r'[ (]', op)[0]] not in body for op, body in zip(ops, parts[6::3])):
      raise StepFail(f'STM32_Programmer_CLI failed (exit {code})', stlink_failure(out))
    return parts[6::3]

  def mem32(self, addrs):
    return {a: r32_value(body, a) for a, body in zip(addrs, self.run([f'-r32 0x{a:08X} 1' for a in addrs]))}

  def write32(self, addr, value):
    """Halt, write, read back, resume: only the read-back proves the write."""
    got = r32_value(self.run(['-halt', f'-w32 0x{addr:08X} 0x{value:08X}', f'-r32 0x{addr:08X} 1', '-run'])[2], addr)
    if got != value:
      raise StepFail(f'{addr:#010x} reads back {got:08X}, not {value:#010x}')
    return hex(value)


def r32_value(body, addr):
  m = re.findall(rf'^0x{addr:08X} : ([0-9A-F]{{8}})$', body, re.M)
  if len(m) != 1:
    raise StepFail(f'-r32 gave no single value for {addr:#x}')
  return int(m[0], 16)


def uploaded(path, want):
  """Whether an `-u` operation's file holds exactly `want`."""
  return path.is_file() and path.read_bytes() == want


def core_regs(body):
  def one(name):
    m = re.findall(rf'^{name}\s*= 0x([0-9A-F]{{8}})$', body, re.M)
    if len(m) != 1:
      raise StepFail(f'no single {name} in the -coreReg output')
    return int(m[0], 16)
  return {'pc': one('PC'), 'r0': one('R0'), 'msp': one('MSP'), 'ipsr': one('XPSR') & 0x1FF}


def esp_port(uid):
  """The provider's esptool_port: exactly one tty for this serial, never a guessed /dev/ttyUSBn."""
  try:
    return provider().esptool_port(uid)
  except (RuntimeError, OSError) as e:
    raise StepFail(str(e))


def child_json(cmd, log, timeout, what):
  """The JSON last line of a helper child (esptool_session.py, usb_dfu.py, fat-read); a missing line, a non-zero
  exit or an `ok` other than true fails the step with the helper's `reason` (else `error`) and the output tail."""
  code, out = spawn(cmd, log, timeout)
  tail, res = out.strip().splitlines()[-5:], last_json(out)
  if res is None:
    raise StepFail(f'{what} ended without its JSON (exit {code})', {'tail': tail})
  if code or res.get('ok') is not True:
    raise StepFail(f'{what}: {res.get("reason") or res.get("error")}', {'tail': tail, 'error': res.get('error')})
  return res


class Esptool:
  """esptool sessions on one board, each one connection in its own child (esptool_session.py)."""
  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log

  def run(self, ops, after):
    refuse_pending(self.dir, self.b.get('pendingMark'))
    spec = self.dir / f'esp-{time.monotonic_ns()}.json'
    spec.write_text(json.dumps(ops))
    return child_json([esptool_runtime()['python'], '-B', ESP_SESSION, '--port', esp_port(self.b['probe']), '--chip',
                       self.b['device'], '--baud', str(ESP_BAUD), '--after', after, spec], self.log, ESP_TIMEOUT,
                      'esptool session')


def preserved_ops(regions):
  return [{'op': 'md5', 'addr': lo, 'size': hi - lo} for lo, hi in regions.values()]


def preserved_md5(regions, results):
  md5 = [r['md5'] for r in results if r['op'] == 'md5']
  return dict(zip(regions, md5))


def check_preserved(before, after, by):
  if before != after:
    raise StepFail(f'a preserved region changed by the end of the {by}', {'before': before, 'after': after})


def esp_verify(tool, board, segments, workdir, snapshot):
  """After the flash: every segment read back byte for byte in one connection of the runner's, then one
  reset. The preserved regions' MD5s must equal `snapshot`, taken before the install."""
  reads = [(off, path, workdir / f'readback-{off:x}.bin') for off, path in segments]
  keep = board['regions']['preserved']
  ops = [{'op': 'read', 'addr': off, 'size': path.stat().st_size, 'file': str(rb)} for off, path, rb in reads] + \
        preserved_ops(keep)
  after = preserved_md5(keep, tool.run(ops, 'hard-reset')['results'])
  check_preserved(snapshot, after, 'install')
  for off, path, rb in reads:
    if rb.read_bytes() != path.read_bytes():
      raise StepFail(f'{path.name} does not read back as written', {'addr': hex(off)})
  return {'preserved': after, 'writes': [write_span(path.name, off, path.stat().st_size) for off, path in segments]}


def write_span(what, addr, length, block=0x1000):
  """A write's payload span and the `block`-aligned span covering it."""
  lo, hi = addr // block * block, -(-(addr + length) // block) * block
  return {'what': what, 'span': [hex(addr), hex(addr + length)], 'blocks': [hex(lo), hex(hi)]}


def report_snapshot(row, keep):
  """The preserved-region MD5s a failed esptool run took before its install wrote, from its report row, over the
  regions `keep` this checkout preserves. A board whose flash was written always has them (the snapshot precedes
  the writes), so a touched row without them is refused, never recovered blind."""
  ev = row.get('snapshot') or {}
  regions, md5 = ev.get('preservedRegions'), ev.get('preserved')
  if regions is None and md5 is None and (row.get('cleanup') or {}).get('state') == 'untouched':
    return None
  if regions is None or md5 is None:
    raise Refused('the failed run touched the board but its report has no preserved-region snapshot to check')
  ok = isinstance(regions, dict) and isinstance(md5, dict) and regions and set(regions) == set(md5) and all(
    isinstance(r, list) and len(r) == 2 and all(type(v) is int for v in r) and 0 <= r[0] < r[1] < 1 << 32 and
    isinstance(md5[n], str) and re.fullmatch(r'[0-9a-f]{32}', md5[n]) for n, r in regions.items())
  if not ok:
    raise Refused(f'the failed run\'s preserved-region snapshot is malformed: {regions} {md5}')
  if {n: tuple(r) for n, r in regions.items()} != keep:
    raise Refused(f'the failed run preserved {regions}; this checkout preserves {keep}')
  return md5


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


def hub_location(serial):
  """uhubctl's location (the sysfs name) of the one USB hub with this serial: it follows the hub when it is
  plugged elsewhere."""
  hits = []
  for d in Path('/sys/bus/usb/devices').iterdir():
    try:
      if (d / 'bDeviceClass').read_text().strip() == '09' and (d / 'serial').read_text().strip() == serial:
        hits.append(d.name)
    except OSError:
      continue
  if len(hits) != 1:
    raise StepFail(f'{len(hits)} USB hubs with serial {serial}: {hits}')
  return hits[0]


def port_dir(cfg):
  hub = hub_location(cfg['hub'])
  return Path('/sys/bus/usb/devices') / hub / f'{hub}:1.0' / f'{hub}-port{cfg["port"]}'


class PortPower:
  """The roster's usbPower (SKILL.md Hosts/rosters): while DFU is awaited, the hub port's sysfs `disable` is written 1
  then 0 once the port sat in state "default" for STUCK s of this wait, at most once per GAP s."""
  STUCK, GAP, OFF, TIMEOUT = 2.0, 10.0, 1, 15
  RESTORED = {True: 'restored', False: 'NOT restored', None: 'not attempted: a cycle child survived'}
  # each write and its read-back in a bounded child: both take the hub's lock and talk to the hub
  SET = 'echo "$2" > "$1" && [ "$(cat "$1")" = "$2" ]'

  def __init__(self, cfg, log):
    self.cfg, self.log, self.since, self.last, self.cycles = cfg, log, None, None, []

  def start(self):
    """A new wait: what the port did between waits was not observed."""
    self.since = None

  def poll(self):
    if not self.cfg:
      return
    port = port_dir(self.cfg)
    try:
      state = (port / 'state').read_text().strip()
    except OSError as e:
      raise StepFail(f'cannot read {port / "state"}: {e}')
    now = time.monotonic()
    if state != 'default':
      self.since = None
    elif self.since is None:
      self.since = now
    if self.since is None or now - self.since < self.STUCK or self.last is not None and now - self.last < self.GAP:
      return
    self.since, disable, done = None, port / 'disable', False
    try:
      off = self.set(disable, '1')
      if off:
        time.sleep(self.OFF)
      on = self.set(disable, '0')
      done = off and on
    finally:
      self.last = time.monotonic()
      if not done:   # an interruption or failure from the off write on must not leave the port without VBUS
        restored = self.restore(disable)
        with open(self.log, 'a') as f:
          f.write(f'# power-cycle of {port} failed; power-on {self.RESTORED[restored]}\n')
    if not done:
      raise StepFail(f'could not power-cycle {port}', {'off': off, 'on': on, 'restored': restored})
    self.cycles.append(port.name)

  def restore(self, disable):
    """Power on after a failed cycle: True or False as the write and read-back went, None when a cycle child an
    interruption or timeout left behind survives SIGKILL, since it could still write after the restore."""
    ours = [p for p in CHILDREN if list(p.args[:3]) == ['sh', '-c', self.SET] and p.args[3:5] == ['sh', str(disable)]]
    if any([reap(p) for p in ours]):
      return None
    try:
      return self.set(disable, '0')
    except StepFail:
      return False

  def set(self, disable, value):
    code, out = spawn(['sh', '-c', self.SET, 'sh', disable, value], self.log, self.TIMEOUT)
    return code == 0 and not out.strip()


def wait_for(fn, timeout, what, fail=None):
  end = time.monotonic() + timeout
  while time.monotonic() < end:
    v = fn()
    if v:
      return v
    time.sleep(0.2)
  raise (fail or StepFail)(f'{what} not seen within {timeout}s')


def stays_away(fn, seconds, what, ev):
  end = time.monotonic() + seconds
  while True:
    if fn():
      raise StepFail(what, ev)
    if time.monotonic() >= end:   # sampled once more after the last sleep: the window's end is checked too
      return
    time.sleep(min(0.2, max(0.0, end - time.monotonic())))


def exclusion_configured(facts, serial):
  """A udev rule in exactly commissioning.md's form sets UDISKS_IGNORE=1 on this bootloader's VID, PID and
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
  raise Refused(f'no udev rule in the required form sets ENV{{UDISKS_IGNORE}}="1" on idVendor '
                f'{want[("ATTRS{idVendor}", "==")]}, idProduct {want[("ATTRS{idProduct}", "==")]} and serial {serial} '
                '(commissioning.md: 99-tinyuf2-hil.rules)')


def udisks_ignored(dev):
  props = subprocess.run(['udevadm', 'info', '--query=property', f'--name={dev}'], capture_output=True, text=True)
  return 'UDISKS_IGNORE=1' in props.stdout.split()


def check_exclusive(dev, timeout=UDEV_TIMEOUT):
  # the block node shows in sysfs before udev has run its rules on it (bench: RT1060 re-entry), so the
  # property gets a bounded wait; the mount check still catches a rule that did not apply
  start = time.monotonic()
  try:
    wait_for(lambda: udisks_ignored(dev), timeout, f'UDISKS_IGNORE=1 on {dev}')
  except StepFail:
    raise StepFail(f'{dev} has no UDISKS_IGNORE=1: desktop automount could race the raw I/O '
                   '(commissioning.md: 99-tinyuf2-hil.rules)')
  mounted = [l.split()[0] for l in Path('/proc/mounts').read_text().splitlines()]
  if any(os.path.realpath(m) == dev for m in mounted):
    raise StepFail(f'{dev} is mounted; refusing raw I/O')
  return round(time.monotonic() - start, 2)


class Fat:
  """Read-only FAT12/16 reader for the ghostfat volume. Its geometry and chains come from the firmware
  under test, so every one is bounded; it runs in its own process (fat_read) so a stuck USB read cannot
  hold the process that owns cleanup. It keeps one descriptor for its life: the device's last close drops its
  page cache (Linux block/bdev.c blkdev_put_whole -> kill_bdev), so a reader that reopened it per read would
  cost a USB read per cluster (bench: the nonce block 4 MiB into CURRENT.UF2 took >20s)."""
  def __init__(self, dev):
    self.dev, self.fd, self._entries = dev, os.open(dev, os.O_RDONLY), None
    try:
      self._geometry()
    except BaseException:
      os.close(self.fd)
      raise

  def __enter__(self):
    return self

  def __exit__(self, *exc):
    os.close(self.fd)

  def _geometry(self):
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
    self.fat = self.read(self.res * self.bps, self.spf * self.bps)   # the first FAT, walked in memory

  def read(self, off, n):
    b = os.pread(self.fd, n, off)
    if len(b) != n:
      raise ValueError(f'short read at {off:#x}: {len(b)} of {n} bytes')
    return b

  def entries(self):
    """The root directory, read once per Fat as the FAT is."""
    if self._entries is None:
      out = {}
      raw = self.read(self.root, self.roots * 32)
      for i in range(0, len(raw), 32):
        e = raw[i:i + 32]
        if e[0] in (0, 0xE5) or e[11] & 0x08:
          continue
        name = (e[:8].decode('ascii', 'replace').strip() + '.' + e[8:11].decode('ascii', 'replace').strip())
        out[name.rstrip('.')] = (struct.unpack_from('<H', e, 26)[0], struct.unpack_from('<I', e, 28)[0])
      self._entries = out
    return self._entries

  def next_cluster(self, c):
    if self.fat16:
      return struct.unpack_from('<H', self.fat, 2 * c)[0]
    v = struct.unpack_from('<H', self.fat, c * 3 // 2)[0]
    return v >> 4 if c & 1 else v & 0xFFF

  def file(self, name, length=None, offset=0):
    """`length` bytes of `name` from `offset`, a whole number of clusters in; the clusters before it are
    walked in the FAT, not read."""
    ents = self.entries()
    if name not in ents:
      raise ValueError(f'{name} not on the volume (found {sorted(ents)})')
    c, size = ents[name]
    csize, seen = self.spc * self.bps, set()
    if offset % csize or offset > size:
      raise ValueError(f'{name}: offset {offset:#x} is not a cluster boundary inside its {size} bytes')
    want, out, skip = min(size - offset, length or size), b'', offset // csize
    while len(out) < want:
      if not 2 <= c < (0xFFF8 if self.fat16 else 0xFF8) or c in seen:
        raise ValueError(f'{name}: cluster chain broken at {c:#x} after {len(out)} of {want} bytes')
      seen.add(c)
      if skip:
        skip -= 1
      else:
        out += self.read(self.data + (c - 2) * csize, min(csize, want - len(out)))
      c = self.next_cluster(c)
    return out, size


def flush_evidence(code, out):
  """The flush child's exit with its phase and errno name, from its JSON last line when it printed one."""
  res = last_json(out) or {}
  if not res.get('phase'):
    return {'exit': code, 'tail': out.strip().splitlines()[-5:]}
  return {'exit': code, 'phase': res['phase'], 'errno': res.get('errno')}


def last_json(out):
  """A child's JSON last line as a dict, None when it printed none."""
  try:
    res = json.loads(out.strip().splitlines()[-1])
  except (IndexError, ValueError):
    return None
  return res if isinstance(res, dict) else None


def fat_read(dev, name, length, log, offset=0, timeout=USB_TIMEOUT):
  """{'entries': {...}, 'data': bytes} of `name` on `dev`, read by a child process bounded by `timeout`."""
  try:
    r = child_json([sys.executable, '-B', __file__, 'fat-read', '--dev', dev, '--file', name, '--length', str(length),
                    '--offset', str(offset)], log, timeout, name)
  except StepFail as e:
    e.evidence['dev'] = dev
    raise
  return {'entries': r['entries'], 'data': bytes.fromhex(r['data']), 'size': r['size']}


def clear_pending_main(args):
  """`clear-pending`: remove a board's pending mark once each session it lists is ended, or after a separately
  reviewed recovery whose note is recorded (SKILL.md Recovery). Exit 0 cleared or none, 2 refused."""
  note, recovery = args.after_reviewed_recovery, None
  try:
    if note is not None and not note.strip():
      raise Refused('--after-reviewed-recovery needs the note of the reviewed recovery')
    if note is not None and (args.under_hold is None) == (args.recover_holder is None):
      raise Refused("--after-reviewed-recovery needs proof of the board's hold: --under-hold <reason> or "
                    '--recover-holder <cleanup holder pid>')
    lock = load_board(args.config, args.board)['lock']
    helper = load_helper()
    hold = None
    if note is not None:   # the note alone proves nothing: the board's existing hold does, never a new flock
      recovery = recovery_lock(helper, lock)
      if args.recover_holder is not None:
        hold = prove_cleanup_holder(helper, lock, args.recover_holder)
      else:
        manual_holder(helper, lock, args.under_hold)
        hold = helper.read_record(lock)
    cleared = clear_pending_mark(pending_mark(helper, lock), note, hold)
  except Refused as e:
    print(json.dumps({'pass': False, 'error': str(e)}), flush=True)
    return 2
  finally:
    if recovery:
      recovery.close()
  print(json.dumps({'pass': True, 'cleared': cleared}), flush=True)
  return 0


def flush_main(args):
  """`flush`: fsync of one block device node, opened as coreutils `sync FILE` opens it. Exit 0 flushed,
  FLUSH_GONE when the open found no node (ENOENT) or no live disk (ENXIO), 1 on any other failure."""
  def failed(phase, e, code=1):
    print(json.dumps({'ok': False, 'phase': phase, 'errno': errno.errorcode.get(e.errno, str(e.errno)),
                      'error': str(e)}))
    return code
  try:
    fd = os.open(args.dev, os.O_RDONLY | os.O_NONBLOCK)
  except OSError as e:
    return failed('open', e, FLUSH_GONE if e.errno in (errno.ENOENT, errno.ENXIO) else 1)
  phase = 'fcntl'
  try:
    fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK)
    phase = 'fsync'
    os.fsync(fd)
  except OSError as e:
    return failed(phase, e)
  finally:
    os.close(fd)
  print(json.dumps({'ok': True}))
  return 0


def uf2_write_main(args):
  """`uf2-write`: the file's bytes in one write to the device at `--offset`, opened with WRITE_FLAGS from a
  page-aligned buffer (O_DIRECT); the JSON says how it ended, and when the write call itself started and returned
  (`writeStart`, `writeEnd`: CLOCK_MONOTONIC, shared with the runner)."""
  data = Path(args.file).read_bytes()
  buf = mmap.mmap(-1, len(data))
  buf.write(data)
  res, phase = {'ok': False}, 'open'
  try:
    fd = os.open(args.dev, WRITE_FLAGS)
    phase = 'write'
    try:
      res['writeStart'] = time.monotonic()
      try:
        n = os.pwrite(fd, buf, args.offset)
      finally:
        res['writeEnd'] = time.monotonic()
      res.update(ok=n == len(data), written=n)
    finally:
      os.close(fd)
  except OSError as e:
    res.update(errno=errno.errorcode.get(e.errno, str(e.errno)), error=str(e))
  res.update(phase=phase, bytes=len(data), end=time.monotonic())
  print(json.dumps(res))
  return 0 if res['ok'] else 1


def fat_read_main(args):
  try:
    with Fat(args.dev) as fat:
      entries = fat.entries()
      data, size = fat.file(args.file, args.length, args.offset) if args.length else (b'', entries[args.file][1])
    print(json.dumps({'ok': True, 'entries': entries, 'data': data.hex(), 'size': size}))
  except (OSError, ValueError, KeyError, struct.error) as e:
    # reason: the same failure reads the same in every run; an OSError's text names the device node
    reason = f'{type(e).__name__}: {e.strerror}' if isinstance(e, OSError) and e.strerror else f'{type(e).__name__}: {e}'
    print(json.dumps({'ok': False, 'error': f'{type(e).__name__}: {e}', 'reason': reason}))
  return 0


# ------------------------------------------------------------------ locks

def check_lock_pin():
  """Refuse unless lib/agentrc is checked out, clean, at the commit HEAD pins (check_build's check)."""
  if not LOCK_HELPER.is_file():
    raise Refused(f'lock helper {LOCK_HELPER} is not checked out: git submodule update --init {AGENTRC}')
  try:
    cb.check_agentrc_pin()
  except cb.Fail as e:
    raise Refused(str(e))


def load_helper():
  mod = load_pinned(LOCK_HELPER, 'hil_lock', (), 'lock helper')
  errors = [getattr(mod, e, None) for e in ('LockUnavailable', 'RecoveryBlocked', 'ReleaseRefused')]
  if getattr(mod, 'PROTECTED_REASONS', None) != PROTECTED or getattr(mod, 'CI_REASON', None) != 'hil_test.py' or \
     getattr(mod, 'CLEANUP_ROLE', None) != HOLDER_ROLE or not isinstance(getattr(mod, 'HOLD_KIND', None), str) or \
     not all(isinstance(e, type) and issubclass(e, RuntimeError) for e in errors) or \
     not (isinstance(getattr(mod, 'PendingRefused', None), type) and issubclass(mod.PendingRefused, RuntimeError)) or \
     not all(callable(getattr(mod, f, None)) for f in ('PendingSessions', 'takeover_predecessor', 'release_token',
                                                        'write_record', 'proc_start', 'is_recovery_blocker')):
    raise Refused(f'lock helper {LOCK_HELPER}: protected reasons are not {sorted(PROTECTED)}, its CI reason is not '
                  f"'hil_test.py', its cleanup role is not {HOLDER_ROLE!r}, it has no LockUnavailable, RecoveryBlocked or "
                  'ReleaseRefused, no pending-session record, no takeover journal, hold kind and token release, or no '
                  'recovery-blocker check; recheck this contract')
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


def recovery_lock(helper, board):
  """An exclusive flock on `<lock file>.recover`, kept until the caller drops it: one recovery per board, so
  none releases the holder while another is still between its probe sessions. The lock helper lists `*.lock`
  only, so it never reports this file as a holder."""
  path = helper.lock_path(board) + '.recover'
  try:
    fh = os.fdopen(os.open(path, os.O_RDONLY | os.O_CREAT, 0o666))
  except OSError as e:
    raise Refused(f'cannot open {path}: {e}')
  try:
    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except OSError as e:
    fh.close()
    raise Refused(f'{board}: another recovery holds {path}: {e}')
  return fh


def prove_cleanup_holder(helper, board, pid):
  rec = prove_hold(helper, board, pid, reason='hil_test.py', role=HOLDER_ROLE)
  try:
    cmdline = Path(f'/proc/{pid}/cmdline').read_bytes()
  except OSError as e:
    raise Refused(f'pid {pid}: {e}') from None
  if b'hil_test.py' not in cmdline:
    raise Refused(f'pid {pid} is not a hil_test.py cleanup holder')
  return rec


def manual_holder(helper, board, reason):
  if reason in PROTECTED:
    raise Refused(f'{reason!r} is a protected holder; --under-hold takes the reason of your own manual hold')
  rec = helper.read_record(board)
  pid = rec.get('pid') if isinstance(rec, dict) else None
  if not isinstance(pid, int):
    raise Refused(f'{board}: no lock record; hold it first with {helper.__file__} hold {board} --reason ...')
  prove_hold(helper, board, pid, reason=reason)


def takeover_predecessor(helper, board, token):
  """The battery record that `token`'s live takeover holder replaced (`hil_lock.py hold --take-over`), from the
  board's journal chain: refused unless the holder is proven and that record is this runner's, a battery's
  protected record or its cleanup holder's, left on this board alone."""
  rec = helper.read_record(board)
  if not isinstance(rec, dict) or rec.get('token') != token or rec.get('holder') != helper.HOLD_KIND:
    raise Refused(f'{board}: lock record {rec} is not the takeover holder of token {token}')
  if rec.get('locks') != [board]:
    raise Refused(f'{board}: takeover {token} covers {rec.get("locks")}, not this board alone')
  prove_hold(helper, board, rec.get('pid'), role=HOLDER_ROLE)
  if helper.proc_start(rec['pid']) != rec.get('start'):
    raise Refused(f'{board}: pid {rec["pid"]} is not the takeover holder that wrote the record')
  try:   # the oldest journal's: a takeover of a dead taker names the original holder
    _, pred = helper.takeover_predecessor(board, token)
  except LookupError as e:
    raise Refused(f'{board}: {e}: the record it replaced is unknown') from None
  if not isinstance(pred, dict) or pred.get('reason') != 'hil_test.py' or \
     not helper.is_recovery_blocker(pred) or \
     pred.get('role') == HOLDER_ROLE and pred.get('board') != board:
    raise Refused(f'{board}: the takeover replaced {pred!r}, not a battery record of this runner on {board}: recover '
                  'it by hand')
  return pred


def run_dir_sessions(run_dir):
  """The openocd_esp sessions a dead battery's run dir holds (OPENOCD_SESSIONS), every listing's error raised: a
  run dir or session dir that cannot be listed, a session dir without its receipt or a receipt that cannot be read
  hides what the battery left."""
  pattern, receipt = OPENOCD_SESSIONS.split('/')
  found = []
  for name in sorted(os.listdir(run_dir)):
    if fnmatch.fnmatchcase(name, pattern):
      path = Path(run_dir) / name
      if receipt not in os.listdir(path):
        raise OSError(errno.ENOENT, f'{path} holds no {receipt}')
      found.append(session_entry(path / receipt))
  return found


def predecessor_evidence(pred, reported, reviewed):
  """What a battery that died left on the host: a cleanup holder's survivors, from its record and its report's row
  (`reported`), or a protected record's run dir with its openocd_esp receipts. Refused while any lives or is not
  ended, and when the record names neither or its run dir cannot be read: missing evidence keeps the blocker."""
  if pred.get('role') == HOLDER_ROLE:
    survivors = pred.get('survivors')
    survivors = survivors + reported if isinstance(survivors, list) else None
  elif isinstance(pred.get('runDir'), str):
    try:
      survivors = run_dir_sessions(pred['runDir'])
    except OSError as e:
      raise Refused(f"the dead battery's run dir {pred['runDir']} cannot be read: {e}; what it left is unknown")
  else:
    survivors = None
  if not isinstance(survivors, list):
    raise Refused(f'the replaced record {pred} names neither survivors nor a run dir: what the battery left is unknown')
  refuse_live(survivors, reviewed, "the dead battery's")
  return survivors


def refuse_live(survivors, reviewed, whose):
  """Refused while any of `whose` openocd_esp sessions is not ended, outside the `reviewed` receipts, or any of its
  children lives: recovery never overlaps them."""
  pending = [s['receipt'] for s in survivors
             if 'receipt' in s and session_state(s) != 'ended' and s['receipt'] not in reviewed]
  if pending:
    raise Refused(f'{whose} openocd_esp sessions {pending} are not ended: end each with '
                  '`hil_openocd_esp.py end --receipt <receipt>`, or clear-pending after a separately reviewed '
                  'recovery (SKILL.md Recovery)')
  alive = still_alive(survivors)
  if alive:
    raise Refused(f'{whose} children {alive} are still alive; recovery may not overlap them')


def read_report(report):
  """A failed run's hil_report.json, read through the report core before any recovery lock or probe: a legacy one
  (no `_hil`) by this runner's adapter; a missing or corrupt one, or an unknown `_hil` or body version, is refused."""
  core = report_core()
  reading = core.read_document(report, run_report.schema(core))
  if reading.outcome not in core.READABLE:
    raise Refused(f'cannot read {report}: {reading.outcome}: {reading.detail}')
  return reading.body


def failed_row(body, report, board, holder):
  """The row of `body` (read_report of `report`) whose cleanup holder is pid `holder` on `board`."""
  failed = [x for x in body['results'] if isinstance(x.get('cleanup'), dict) and
            ((x['cleanup'].get('holder') or {}).get('pid') == holder and x.get('board') == board['name'])]
  if len(failed) != 1:
    raise Refused(f'{report} names no cleanup holder {holder} of {board["name"]}')
  return failed[0]


def probe_users(board):
  """Processes using this board's probe: for J-Link one opened by serial (a JLinkExe or GDB server from an
  earlier session), for ST-LINK any STM32CubeProgrammer CLI (its script names the probe, not its command line), for
  openocd any holding the CMSIS-DAP probe's usbfs node open and any openocd naming its serial, which may not have
  opened it yet, for esptool any process holding its tty open, for openocd_esp or an esptool USJ also any holding
  the USJ's usbfs node. Devices are resolved first, then one /proc walk."""
  if board['flasher'] in ('esptool', 'openocd_esp'):
    usj = board['flasher'] == 'openocd_esp' or cb.USJ_SERIAL.fullmatch(board['probe'])
    devs = [esp_port(board['probe'])] + ([usj_node(board['probe'])] if usj else [])
    return tty_users(*devs)
  node = probe_node(board) if board['flasher'] == 'openocd' else None
  probe, users = board['probe'].encode(), []
  for d in Path('/proc').iterdir():
    if not d.name.isdigit() or int(d.name) == os.getpid():
      continue
    try:   # bytes: an argument need not decode, and must still name the probe
      cmd = (d / 'cmdline').read_bytes().split(b'\0')
    except OSError:
      cmd = [b'']
    name = Path(cmd[0].decode(errors='replace')).name
    if board['flasher'] == 'stlink' and name == STM32_PROGRAMMER_CLI or \
       board['flasher'] == 'jlink' and b'JLink' in cmd[0] and any(probe in c for c in cmd) or \
       board['flasher'] == 'openocd' and (name == 'openocd' and any(probe in c for c in cmd) or
                                          node is not None and holds_open(d, (node,))):
      users.append(int(d.name))
  return users


PROBE_SERIAL_TIMEOUT = 2   # s for one bounded `serial` read of a device of the probe's USB ID that udev has no record of


def probe_node(board):
  """The usbfs node of the CMSIS-DAP probe with the roster's serial and USB ID, or None when none is enumerated. Each
  device of that USB ID is named by udev's record, else a bounded read of `serial`, which the kernel serves under the
  device lock a stuck usbfs ioctl holds (usb_observe): a peer whose serial does not answer is a StepFail unless this
  probe was found, since it may be this probe. A device that re-enumerated while it was named may have handed its
  bus and device number to another: the walk runs once more, and a second change is a StepFail."""
  for _ in range(2):
    node, moved = probe_scan(board)
    if not moved:
      return node
  raise StepFail(f'probe {board["probe"]}: {moved} re-enumerated while their serial was read, in two walks')


def probe_scan(board):
  """One walk of probe_node: (the node, the devices whose enumeration changed across their serial's lookup)."""
  obs, (vid, pid) = usb_observe(), (x.removeprefix('0x').lower() for x in board['vid_pid'].split())
  mine, silent, moved = [], [], []
  for dev in obs.usb_devices(vid_pid=(vid, pid)):
    bus, num = dev['busnum'], dev['devnum']
    # without its numbers a device is named through its directory, still refused below when its serial matches
    sn = obs.usb_node_serial(usbfs_node(bus, num), PROBE_SERIAL_TIMEOUT) if None not in (bus, num) else \
        obs.read_sysfs(os.path.join(dev['dir'], 'serial'), PROBE_SERIAL_TIMEOUT)
    if obs.enumeration_id(dev['dir']) != dev['ino']:   # the serial, or the numbers it was found by, may be another's
      moved.append(dev['busport'])
    elif sn is None:
      silent.append(dev['busport'])
    elif sn.lower() == board['probe'].lower():
      mine.append(dev)
  if moved:
    return None, moved
  if len(mine) > 1 or not mine and silent:
    raise StepFail(f'probe {board["probe"]}: {len(mine)} devices {vid}:{pid} with its serial, and {silent} did not '
                   'answer for theirs')
  if mine and None in (mine[0]['busnum'], mine[0]['devnum']):
    raise StepFail(f'probe {board["probe"]} at {mine[0]["busport"]}: no bus or device number')
  return usbfs_node(mine[0]['busnum'], mine[0]['devnum']) if mine else None, []


def usbfs_node(bus, num):
  return f'/dev/bus/usb/{bus:03d}/{num:03d}'


def usj_node(serial):
  """The USJ's usbfs node, which an openocd from an earlier session holds open, the provider's (usj_node)."""
  try:
    return openocd_esp().usj_node(serial)
  except (RuntimeError, OSError) as e:
    raise StepFail(f'USJ {serial}: {e}')


def tty_users(*devs):
  """Processes holding any of `devs` open, each once."""
  return [int(d.name) for d in Path('/proc').iterdir()
          if d.name.isdigit() and int(d.name) != os.getpid() and holds_open(d, devs)]


def holds_open(proc, devs):
  """Whether the /proc/<pid> `proc` holds any of `devs` open; False once its fds cannot be listed."""
  try:
    return any(readlink(fd) in devs for fd in list((proc / 'fd').iterdir()))
  except OSError:
    return False


def readlink(fd):
  """A /proc fd's target, or None once it has closed: one closing fd must not hide the process's others."""
  try:
    return os.readlink(fd)
  except OSError:
    return None


def holder_record(helper, fh, board, detail, survivors):
  """The cleanup holder's record over the battery's, through the helper's interruption-safe rewrite: a death
  midway leaves the protected record or an unreadable one, a recovery blocker either way, never an empty one."""
  helper.write_record(fh, 'hil_test.py', role=HOLDER_ROLE, board=board, detail=detail, survivors=survivors)


HELD_IN_PROCESS = []
# the GitHub Actions runner kills every process whose environment carries the job's tracking id when the job
# ends (actions/runner JobExtension.FinalizeJob), so a holder forked under it would free a board that was
# never cleaned up: the holder re-executes itself without that variable
JOB_TRACKING = 'RUNNER_TRACKING_ID'
HOLDER_SCRIPT = Path(__file__).resolve()


def exec_holder(fh, ack):
  """Replace this process with `hil_test.py keep-held <fd> <ack>`: the same open file description (and its
  flock) and the acknowledgement pipe passed on, the job tracking variable dropped. The replacement
  acknowledges only once it runs, so a holder that dies at startup is never acknowledged. Returns only
  when the exec itself fails, to keep holding in this process."""
  for fd in (fh.fileno(), ack):
    os.set_inheritable(fd, True)
  env = {k: v for k, v in os.environ.items() if k != JOB_TRACKING}
  with contextlib.suppress(OSError):
    os.execve(sys.executable, [sys.executable, str(HOLDER_SCRIPT), 'keep-held', str(fh.fileno()), str(ack)], env)


def keep_held(fh):
  """Hold until recovery's SIGUSR1, taken by sigwait with SIGUSR1 blocked since hand_off: a handler and
  pause() lose a signal that lands between the interpreter's check and the syscall. SIGTERM and SIGINT
  are ignored: an operator's timeout kill must not free a board that was never cleaned up. Meanwhile each build lock
  this process kept (HELD_BUILD) is released once its survivors end, as restore() needs it before recovery signals."""
  for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, signal.SIG_IGN)
  signal.pthread_sigmask(signal.SIG_SETMASK, {signal.SIGUSR1})
  for std in (0, 1, 2):   # closed, not reopened on /dev/null: holding must not need a free descriptor
    with contextlib.suppress(OSError):
      os.close(std)
  signalled = False
  with contextlib.suppress(Exception):   # a failed look keeps the build locks, never frees the board
    while not signalled and release_ended_builds():
      signalled = signal.sigtimedwait({signal.SIGUSR1}, KEEPER_POLL) is not None
  if not signalled:
    signal.sigwait({signal.SIGUSR1})
  fh.truncate(0)
  os._exit(0)


def hand_off(fh, board, detail, survivors=(), *, helper):
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
      for sig in (signal.SIGTERM, signal.SIGINT):   # before the ack: the caller may be killed right after it
        signal.signal(sig, signal.SIG_IGN)
      os.close(r)
      os.setsid()
      holder_record(helper, fh, board, detail, survivors)
      exec_holder(fh, w)   # the replacement acknowledges once it runs; a failed exec acknowledges here
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
  holder_record(helper, fh, board, detail, survivors)
  HELD_IN_PROCESS.append(fh)
  return {'pid': os.getpid(), 'reason': 'hil_test.py', 'ready': True, 'inProcess': True}


# ------------------------------------------------------------------ the battery

def verify_record(record_path, board, facts, workdir):
  rec, row, root, want = record_row(record_path, board)
  flash = admit_flash(record_path, row, root, board)
  # the runner reads its own copies of the BIN, segments and blinky: the build dir's lock covers the flash
  # only, and a rebuild may replace the dir after it
  copy = workdir / 'record'
  if want == 'idf':
    bin_rel = 'tinyuf2.bin'
    copied(root, (*esp.RECORD_FILES, *flash['sha256']), row, copy)
    files = esp_record(record_path, copy, board, facts)
  else:
    bin_rel, blinky_rel = CMAKE_RECORD_FILES
    update = (UPDATE_UF2,) if UPDATE_UF2 in row.get('sha256', {}) else ()   # the update battery's, when built
    copies = copied(root, (*CMAKE_RECORD_FILES, *update), row, copy)
    files = dict(check_blinky(copies[blinky_rel], board['app'], facts), bin=copies[bin_rel], hex=root / 'tinyuf2.hex')
    if update:
      files['updater'] = copies[UPDATE_UF2]
  files['flash'] = flash
  return files, firmware_fields(record_path, rec, root / bin_rel, files['bin'])


def firmware_fields(record_path, rec, built, copy):
  """The reported identity of a record's bootloader: its build path `built`, hashed and versioned from the runner's
  `copy` of it."""
  return {'path': str(built), 'sha256': sha256(copy), 'buildRecord': str(record_path), 'defines': rec.get('defines', []),
          'version': embedded_version(copy)}


RECORDS = {}   # main's build records, by the path it was given: each admitted once, so facts and images share one


def pin_records(*paths):
  """Admit each of these build records once for the rest of main (record_row)."""
  RECORDS.clear()
  RECORDS.update(dict.fromkeys(os.path.abspath(p) for p in paths if p))


def record_row(record_path, board):
  """(record, its row of this board, build dir, backend) of a passing --shared build of this board on the checkout
  now, clean, in the backend the HIL takes for it; a pinned record's first admission."""
  key = os.path.abspath(record_path)
  if RECORDS.get(key) is None:
    admitted = read_record_row(record_path, board)
    if key not in RECORDS:
      return admitted
    RECORDS[key] = admitted
  return RECORDS[key]


def read_record_row(record_path, board):
  try:
    rec = json.loads(Path(record_path).read_text())
  except (OSError, ValueError) as e:
    raise Refused(f'cannot read build record {record_path}: {e}')
  rows = [r for r in rec.get('boards', []) if r.get('board') == board['name']]
  if not rec.get('pass') or len(rows) != 1 or rows[0].get('status') != 'ok' or rows[0].get('removed'):
    raise Refused(f'{record_path}: not a passing --shared build of {board["name"]}')
  row, info = rows[0], rec.get('input', {})
  want = 'idf' if board.get('kind') == 'esp' else 'cmake'
  if row.get('backend') != want:
    raise Refused(f'{record_path}: a {row.get("backend")} build; the HIL takes {want} builds only for this board '
                  f'(check_build.py --board {board["name"]} --shared --hil-config <roster>)')
  if want == 'idf':
    try:
      image = f'espressif/idf:{cb.ci_idf_version()}'
    except cb.Fail as e:
      raise Refused(str(e))
    idf = rec.get('idf') or {}
    if idf.get('mode') != 'docker' or idf.get('image') != image:
      raise Refused(f'{record_path}: an IDF build from {idf.get("mode")} {idf.get("image")}; the HIL takes CI\'s {image} only')
  try:
    now = cb.identity({board['port']})
  except (cb.Fail, OSError) as e:
    raise Refused(f'cannot establish the checkout identity: {e}')
  for key in ('head', 'submodules', 'deps'):
    if info.get(key) != now[key]:
      raise Refused(f'{record_path}: {key} {info.get(key)} differs from the checkout now ({now[key]})')
  for state in (info, now):
    bad = state.get('dirty') or state.get('dirtyInputs') or state.get('missingInputs') or state.get('depsOffPin') \
          or state.get('inputsDirtiedByBuild')
    if bad:
      raise Refused(f'build inputs are not clean: {bad} (commit, or rebuild from a clean checkout)')
  return rec, row, cb.ROOT / row['buildDir'], want


def admit_flash(record_path, row, root, board):
  """The record's flash binding (check_build --hil-config: its flash target checked against this roster flasher at
  the build), with every file the install reads hash-checked; the install reads them under the build dir's lock,
  through the provider, never the target."""
  want = {'name': board['flasher'], 'uid': board['probe'], 'device': board['device'],
          **({'vid_pid': board['vid_pid']} if board['flasher'] == 'openocd' else {})}
  if board['flasher'] in cb.ROUTE_ARGS:   # a further route: the esptool binding's segments, bound to this route
    fl, (target, inputs) = (row.get('flashRoutes') or {}).get(board['flasher']) or {}, cb.FLASH['esptool']
    bound = (fl.get('flasher'), fl.get('inputs')) == (want, list(inputs))
  else:
    fl, (target, inputs) = row.get('flash') or {}, cb.FLASH[board['flasher']]
    bound = (fl.get('flasher'), fl.get('target'), fl.get('inputs')) == (want, target, list(inputs))
  if not bound:
    raise Refused(f'{record_path}: its flash target is not bound to this roster flasher {want} (rebuild it with '
                  f'check_build.py --board {board["name"]} ... --shared --hil-config <roster>)')
  return {'root': root, 'binding': fl, 'sha256': recorded(root, inputs, row)}


def recorded(root, rels, row):
  """Each file's sha256, which must be the build record's."""
  for rel in rels:
    recorded_bytes(root, rel, row)
  return {rel: row['sha256'][rel] for rel in rels}


def recorded_bytes(root, rel, row):
  try:
    data = (root / rel).read_bytes()
  except OSError:
    data = None
  if data is None or row.get('sha256', {}).get(rel) != hashlib.sha256(data).hexdigest():
    raise Refused(f'{root / rel}: missing, unreadable or changed since the build record')
  return data


def copied(root, rels, row, dest):
  """Each file copied to the same relative path under `dest`, from bytes that hash as the build record's."""
  out = {}
  for rel in rels:
    data = recorded_bytes(root, rel, row)
    out[rel] = dest / rel
    out[rel].parent.mkdir(parents=True, exist_ok=True)
    out[rel].write_bytes(data)
  return out


def check_blinky(path, span, facts):
  """The record's apps/blinky.uf2, which cleanup copies through TinyUF2: one family, numbered under one
  numBlocks, every block inside `span` (the app region, in the UF2's own addresses)."""
  try:
    blocks = parse_uf2(Path(path).read_bytes())
  except (OSError, ValueError) as e:
    raise Refused(f'{path}: {e}')
  for i, bl in enumerate(blocks):
    if (bl['no'], bl['total'], bl['family']) != (i, len(blocks), facts['family']) or not bl['flags'] & UF2_FLAG_FAMILY \
       or not span[0] <= bl['addr'] <= bl['addr'] + bl['size'] <= span[1]:
      raise Refused(f'{path}: block {i} is not block {i} of {len(blocks)} for family {facts["family"]:#x} '
                    f'inside [{span[0]:#x}, {span[1]:#x})')
  if not blocks:
    raise Refused(f'{path}: no UF2 blocks')
  return {'blinky': Path(path), 'blinkyBlocks': len(blocks)}


def esp_record(record_path, root, board, facts):
  """An IDF record's segments, from `root`, the run's copy of every file the record binds."""
  try:
    segments = esp.admit(root, board, facts, board['regions'])
  except (esp.Refused, OSError, ValueError) as e:
    raise Refused(f'{record_path}: {e}')
  # the build's flash target writes without the flasher stub where the build disables it (check_build flash_binding)
  no_stub = esp.sdkconfig((root / 'sdkconfig').read_text()).get('CONFIG_ESPTOOLPY_NO_STUB') == 'y'
  return {'segments': segments, 'bin': root / 'tinyuf2.bin', 'noStub': no_stub,
          **esp_app_chunks(root / esp.APP_UF2, facts, board),
          **check_blinky(root / esp.BLINKY_UF2, (0, board['app'][1] - board['app'][0]), facts)}


def sha256(p):
  try:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
  except OSError:
    return None


def check_bootloader_bin(bin_path, board, facts, what):
  """The BIN from its flash address (`binBase`) inside `install`, within the device's flash limits; board_facts
  checked it is this board's (its Board-ID)."""
  start, size = facts['binBase'], Path(bin_path).stat().st_size
  check_ranges({start: 0, start + size - 1: 0}, [board['install']], FLASH_LIMITS[board['device']], what)


def updater_image(uf2_path, bin_path, facts, what):
  """An in-place updater's blocks (UPDATE_PORTS), contiguous from the BIN's flash address (binBase) and laying out
  exactly `bin_path`, zero padding after it."""
  blocks = contiguous_uf2(uf2_path, facts['family'], facts['binBase'], what)
  try:
    img = Path(bin_path).read_bytes()
  except OSError as e:
    raise Refused(f'{what}: {e}')
  laid = b''.join(bl['data'] for bl in blocks)
  if len(blocks) != -(-len(img) // 256) or laid[:len(img)] != img or laid[len(img):].strip(b'\0'):
    raise Refused(f'{what}: {uf2_path} does not lay out {bin_path} at {facts["binBase"]:#x}')
  return blocks


def admit_update(record_path, board, facts, workdir, files, fw):
  """The update battery's two updaters: the candidate record's own update-tinyuf2.uf2 and a variant record's (the
  same checkout built with check_build --variant and a define that changes the image), each laying out its BIN in
  place, the two BINs differing in a flash cache sector the interrupt's passes flush."""
  sector = facts.get('flashCache')
  if board['kind'] != 'jlink' or board['port'] not in UPDATE_PORTS:
    raise Refused(f'{board["name"]}: no update battery for ports/{board["port"]} on a {board["flasher"]} board; '
                  f'self-update and an interrupted update stay uncovered there (it runs on J-Link boards of '
                  f'{", ".join(sorted(UPDATE_PORTS))})')
  if sector is None:
    raise Refused(f'{fw["buildRecord"]}: tinyuf2.elf has no _flash_cache, so the update sector is unknown')
  if 'updater' not in files:
    raise Refused(f'{fw["buildRecord"]}: no {UPDATE_UF2} in the record (notImplemented: self-update)')
  if record_facts(record_path, board, workdir / 'variant-facts') != facts:
    raise Refused(f'{record_path}: its board facts are not the candidate\'s')
  rec, row, root, _ = record_row(record_path, board)
  if UPDATE_UF2 not in row.get('sha256', {}):
    raise Refused(f'{record_path}: no {UPDATE_UF2} in the record')
  copies = copied(root, (CMAKE_RECORD_FILES[0], UPDATE_UF2), row, workdir / 'variant')
  vbin = copies[CMAKE_RECORD_FILES[0]]
  check_bootloader_bin(vbin, board, facts, 'update variant')
  variant = firmware_fields(record_path, rec, root / CMAKE_RECORD_FILES[0], vbin)
  imgs = {}
  for name, (uf2, bin_path, version) in (('candidate', (files['updater'], files['bin'], fw['version'])),
                                         ('variant', (copies[UPDATE_UF2], vbin, variant['version']))):
    blocks = updater_image(uf2, bin_path, facts, f'{name} updater')
    imgs[name] = {'uf2': Path(uf2), 'bin': Path(bin_path), 'blocks': blocks, 'version': version}
  if imgs['variant']['version'] == fw['version']:
    raise Refused(f'{record_path}: its version is the candidate\'s ({fw["version"]}): the drive could not tell which '
                  'bootloader came back (build the variant with -D \'CFLAGS_CLI=-UUF2_VERSION -DUF2_VERSION="..."\')')
  # the interrupt's passes write both images' blocks but the last, and flush every sector a later pass leaves: only
  # an address both write, holding different bytes, makes a pass erase and program
  c, v = (b''.join(bl['data'] for bl in imgs[k]['blocks'][:-1]) for k in ('candidate', 'variant'))
  base = facts['binBase']
  differ = sorted({(base + i) & ~(sector - 1) for i in range(min(len(c), len(v))) if c[i] != v[i]})
  if not differ:
    raise Refused(f'{record_path}: its bootloader and the candidate\'s hold the same bytes wherever both write but '
                  'the last block: the interrupt\'s passes would program nothing')
  report = {'variant': variant, 'updater': {k: sha256(imgs[k]['uf2']) for k in imgs},
            'differingSectors': [hex(a) for a in differ]}
  return dict(imgs, sector=sector), report


def interleaved(imgs, passes):
  """The interrupt's payload: `passes` alternating passes, variant first and last, over each updater's own bytes but
  its last block, so TinyUF2 never sees a whole image and never resets on its own."""
  body = {k: imgs[k]['uf2'].read_bytes()[:-512] for k in ('variant', 'candidate')}
  return b''.join(body['variant' if i % 2 == 0 else 'candidate'] for i in range(passes))


def inflight_writes(dev):
  """Writes the block layer has issued to `dev` and not completed (sysfs block/<dev>/inflight), 0 when unreadable."""
  try:
    return int(Path(f'/sys/block/{Path(dev).name}/inflight').read_text().split()[1])
  except (OSError, ValueError, IndexError):
    return 0


def usb_at(path):
  """'vid:pid serial' of the device enumerated at USB port `path`, or None."""
  d = Path('/sys/bus/usb/devices') / path
  try:
    ident = f'{d.joinpath("idVendor").read_text().strip()}:{d.joinpath("idProduct").read_text().strip()}'
  except OSError:
    return None
  with contextlib.suppress(OSError):
    ident += ' ' + d.joinpath('serial').read_text().strip()
  return ident


class UsbWatch:
  """What USB port `path` shows, sampled by a thread from construction until stop(): whether it was ever empty
  (`left`) and each distinct device seen, in order."""
  def __init__(self, path, period=0.05):
    self.path, self.period, self.seen, self.left = path, period, [], False
    self.done = threading.Event()
    self.thread = threading.Thread(target=self.sample, daemon=True)
    self.thread.start()

  def sample(self):
    while True:
      now = usb_at(self.path)
      self.left = self.left or now is None
      if now is not None and (not self.seen or self.seen[-1] != now):
        self.seen.append(now)
      if self.done.wait(self.period):
        return

  def stop(self):
    self.done.set()
    self.thread.join()
    return {'left': self.left, 'seen': self.seen}


class Battery:
  def __init__(self, board, facts, workdir, fail_at=None, commissioning=False):
    self.b, self.f, self.dir, self.fail_at, self.commissioning = board, facts, workdir, fail_at, commissioning
    self.log = workdir / 'hil.log'
    self.probe = Probe(board, workdir, self.log)
    self.power = PortPower(board.get('usbPower'), self.log)
    self.steps, self.usb_path, self.touched, self.at, self.kept = [], None, False, 'setup', []
    # where CURRENT.UF2 starts and the flash size INFO_UF2.TXT reports
    self.app_start, self.dfu_flash = facts.get('appStart'), facts['flashSize']
    self.dfu_claim = 'DFU observed after the install'

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

  def flash_target(self, flash, op, judge, before, what, timeout):
    """The record's image through the flash provider, `op(run)` with tool_runner's run, under its build dir's lock:
    the inputs still hash as recorded before it, and again after it; judged(). Touched from
    the tool's start; only attempts that all ended before any target connect leave the board as it was. The lock
    is released only once every child the operation started has ended, reaped here when interrupted; one that
    survives SIGKILL keeps it through a keeper (#579), and the board through cleanup's; so does an openocd_esp
    session left running. The flash then fails however it went, so nothing follows it while either lives."""
    refuse_pending(self.dir, self.b.get('pendingMark'))
    started, lock = list(CHILDREN), take_build_lock(flash['root'])
    flashed = False
    try:
      self.check_inputs(flash, 'before the flash')
      was, self.touched = self.touched, True
      try:
        ev = judged(op(tool_runner(self.log)), judge, before, what, timeout)
      except StepFail as e:
        if e.evidence.get('beforeTarget'):
          self.touched = was
        raise
      self.check_inputs(flash, 'while flashing', ev)
      flashed = True
      return ev
    finally:
      with signals(signal.SIG_BLOCK):
        left = settle_children(started) + outstanding_sessions(self.dir)
        if left:
          self.kept.append({'buildDir': flash['root'].name, 'survivors': left, 'keeper': keep_build_lock(lock, left)})
        else:
          lock.close()
      if left and flashed:
        raise CleanupPending(f'{what}: children survived SIGKILL or a session still runs; the build lock stays with a '
                             'keeper and the board with cleanup', {'survivors': left})

  @staticmethod
  def check_inputs(flash, when, ev=None):
    changed = [rel for rel, digest in flash['sha256'].items() if sha256(flash['root'] / rel) != digest]
    if changed:
      raise StepFail(f'flash inputs changed {when}: {changed}', ev or {})

  def dfu_after_install(self, version):
    """DFU after an install: on the RT boards J-Link's download erased the bootloader's whole 64 KiB block on the
    bench, the app start with it (bench-history.md, RT boards), so DFU comes up; should enumeration time out
    instead, as when a valid app boots (the F303's install keeps the app; there the verify session's reset may land
    in TinyUF2's double-tap window instead, bench-history.md, stm32f303disco), the board's commissioned
    retained-register re-entry brings DFU up. Any other failure fails as it is."""
    try:
      return self.dfu(version)
    except NotEnumerated as e:
      if self.b['reentry'] != 'retained-register':
        raise StepFail(f'{e}, and {self.b["name"]} has no retained-register re-entry to try', e.evidence)
    return self.retained_reentry(version, 'DFU did not enumerate after the install; the retained-register re-entry '
                                          'brought it up')

  def retained_reentry(self, version, claim):
    f = self.f
    self.probe.write32(f['dblTapReg'], f['dblTapMagic'])
    # no probe session opens again until DFU is observed
    tail = self.sysreset()
    ev = dict(self.dfu(version), dfuCameUp=True, resetTail=tail.strip().splitlines()[-3:], claim=claim)
    try:
      left = self.probe.mem32([f['dblTapReg']])[f['dblTapReg']]
    except StepFail as e:
      e.evidence = {**ev, **e.evidence}
      raise
    ev.update(dblTapRegAfter=hex(left), magicConsumed=not left)
    if left:
      raise StepFail('the double-tap register was not consumed', ev)
    return ev

  def sysreset(self):
    """SYSRESETREQ from the probe. It may drop the debug connection mid-write: its exit is not judged, its issue is;
    the caller's observation is the evidence."""
    return self.probe.sysreset()

  def dfu(self, version, timeout=USB_TIMEOUT):
    """DFU naming `version` within `timeout` in all: each wait and the read in turn gets only what is left."""
    f = self.f
    end = time.monotonic() + timeout

    def left():
      remaining = end - time.monotonic()
      if remaining <= 0:
        raise StepFail(f'the DFU checks ran past their {timeout}s bound')
      return remaining
    self.power.start()
    path = wait_for(lambda: self.power.poll() or usb_device(f['vid'], f['pid'], self.b['uid']), left(),
                    f'{f["vid"]:04x}:{f["pid"]:04x} serial {self.b["uid"]}', NotEnumerated)
    if self.usb_path and path != self.usb_path:
      raise StepFail('came back on another USB port', {'usb': path, 'expected': self.usb_path})
    self.usb_path = path
    dev = wait_for(lambda: block_device(path), left(), f'the block device of USB {path}')
    udev_wait = check_exclusive(dev, min(UDEV_TIMEOUT, left()))
    info = fat_read(dev, 'INFO_UF2.TXT', 512, self.log, timeout=left())
    lines = info['data'].decode('ascii', 'replace').splitlines()
    want = f'TinyUF2 Bootloader {version}'
    if not lines or lines[0] != want or f'Board-ID: {f["boardId"]}' not in lines or \
       f'Flash Size: 0x{self.dfu_flash:08X} bytes' not in lines:
      raise StepFail('INFO_UF2.TXT does not match this build', {'info': lines, 'want': want})
    size = (info['entries'].get('CURRENT.UF2') or [None, None])[1]
    if size != self.dfu_flash // 256 * 512:
      raise StepFail(f'CURRENT.UF2 is {size} bytes, not {self.dfu_flash // 256 * 512}')
    return {'usb': path, 'dev': dev, 'udevWaitS': udev_wait, 'info': lines[0], 'currentUf2': size,
            'claim': self.dfu_claim}

  def current_uf2(self, length, offset=0):
    """CURRENT.UF2's blocks from byte `offset`, each checked for its place: block i maps to app_start + 256*i."""
    dev = block_device(self.usb_path)
    data = fat_read(dev, 'CURRENT.UF2', length, self.log, offset)['data']
    try:
      blocks = parse_uf2(data)
    except ValueError as e:
      raise StepFail(f'CURRENT.UF2 is not UF2: {e}', {'head': data[:32].hex()})
    for i, bl in enumerate(blocks, offset // 512):
      if (bl['no'], bl['addr'], bl['size']) != (i, self.app_start + 256 * i, 256):
        raise StepFail(f'CURRENT.UF2 block {i} is {bl["no"]} at {bl["addr"]:#x}, not at {self.app_start + 256 * i:#x}')
    return b''.join(bl['data'] for bl in blocks)

  def copy(self, uf2, blocks, nonce=None, leaves=True):
    """`leaves` False is an in-place update's copy (update_to): its flush is evidence only, and the drive's version
    read back afterwards, never DFU leaving, is the criterion."""
    dev = block_device(self.usb_path)
    code, out = spawn(['mcopy', '-o', '-i', dev, uf2, '::APP.UF2'], self.log, 60)
    if code:
      raise StepFail('mcopy failed', {'tail': out.strip().splitlines()[-5:]})
    # fsync of this node waits on this device's writeback only; a host-wide sync waits on every drive's (#552)
    code, out = spawn([sys.executable, '-B', __file__, 'flush', '--dev', dev], self.log, 60)
    flush = flush_evidence(code, out)
    gone = code == FLUSH_GONE and flush.get('phase') == 'open' and flush.get('errno') in ('ENOENT', 'ENXIO')
    if not leaves:
      return {'blocks': blocks, 'flush': flush}
    if code and not gone:
      raise StepFail(f'flushing {dev} failed', {'flush': flush})
    f = self.f
    # TinyUF2 resets within ms of the last WRITE10 (src/msc.c), so the flush's open can find the device gone; that
    # alone passes, and only once DFU has left
    try:
      wait_for(lambda: usb_device(f['vid'], f['pid'], self.b['uid']) is None, USB_TIMEOUT, 'the DFU device leaving')
    except StepFail as e:
      if code:
        raise StepFail(f'{dev} disappeared before its flush and {e}', {'flush': flush}) from None
      raise
    if code:
      flush['detail'] = 'device disappeared before flush'
    return {'blocks': blocks, **({'nonce': nonce.hex()} if nonce else {}), **({'flush': flush} if code else {})}

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
    self.step('install', lambda: self.install(files))
    # cleared once the bootloader has run board_init (the register's clock), so a magic a failed reenter left
    # cannot send the copied app back to DFU
    self.step('dfu', lambda: dict(self.dfu_after_install(version), dblTapReg=self.probe.write32(f['dblTapReg'], 0)))

    self.step('copy', lambda: self.copy(app_uf2, len(blocks), nonce))

    def app_ran():
      # the bootloader writes DBL_TAP_MAGIC as it boots: a probe connect that resets inside that window
      # would send the next boot to DFU, so the first connect waits it out
      window = 2 * f['dblTapDelayMs'] / 1000 + 0.5
      time.sleep(window)
      ev = dict(self.observe_app(app_bin), waitedS=window)
      stays_away(lambda: usb_device(f['vid'], f['pid'], self.b['uid']), QUIET_TIME,
                 'the DFU device came back while the app should run', ev)
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
      if self.commissioning:
        ev.update(self.control(app_bin))
      ev.update(self.retained_reentry(version, 'the write/reset sequence re-entered DFU (register retention inferred)'))
      expect = self.fix['image']
      n = -(-len(expect) // 256)
      try:
        got = self.current_uf2(n * 512)
        if got[:len(expect)] != expect:
          raise StepFail('CURRENT.UF2 does not read back the fixture from the app start')
      except StepFail as e:
        e.evidence = {**ev, **e.evidence, 'failedAt': 'readback', 'appIntact': 'unshown'}
        raise
      ev['appIntact'] = True
      return ev
    self.step('reenter', reenter)

  def run_update(self, files, version):
    """The update battery (run --update-record): the candidate installed by the probe, each updater copied through the
    drive in turn, the variant's first so the candidate's replaces a different bootloader, then an update interrupted
    by a probe reset while its write is in flight, then the candidate installed again by the battery's own install."""
    u = files['update']
    self.step('install', lambda: self.install(files))
    self.step('dfu', lambda: dict(self.dfu_after_install(version), dblTapReg=self.probe.write32(self.f['dblTapReg'], 0)))
    self.step('update-variant', lambda: self.update_to(u['variant']))
    self.step('update', lambda: self.update_to(u['candidate']))
    missed = None
    try:
      self.step('interrupt', lambda: self.interrupt(u))
    except NotInterrupted as e:   # the board is recovered all the same; the run still fails
      missed = e
    self.step('recover', lambda: dict(self.install(files), dfu=self.dfu_after_install(version)['info']))
    if missed:
      self.at = 'interrupt'
      raise missed

  def update_to(self, img):
    """An updater copied through the drive, observed by the drive naming its version, never by DFU leaving (SKILL.md
    Update, step 3); the probe then verifies its BIN and resets, and the drive must name it again."""
    ev = {'copy': self.copy(img['uf2'], len(img['blocks']), leaves=False)}
    ev['dfu'] = self.await_version(img['version'])
    self.verify_flash([(self.f['binBase'], img['bin'])])
    ev.update(verified=True, verifybin=Path(img['bin']).name)
    ev['dfuAfterReset'] = self.await_version(img['version'])
    return ev

  def await_version(self, version):
    """INFO_UF2.TXT's first line once the drive names `version`, read again until it does within 2 * USB_TIMEOUT: the
    old bootloader's drive, or one mid-reset, is read first. Each attempt gets only what is left of the bound, and a
    name read after it is no pass. A DFU that never enumerates or a stuck read is final."""
    bound = 2 * USB_TIMEOUT
    end, last = time.monotonic() + bound, None
    while (left := end - time.monotonic()) > 0:
      try:
        info = self.dfu(version, left)['info']
      except (NotEnumerated, SpawnTimeout):
        raise
      except StepFail as e:
        last = e
      else:
        if time.monotonic() <= end:
          return info
        break
      time.sleep(min(1, max(0, end - time.monotonic())))
    raise StepFail(f'the drive did not name {version} within {bound}s' + (f': {last}' if last else ''),
                   last.evidence if last else {})

  def interrupt(self, u):
    """An update interrupted mid-write (SKILL.md Update, step 5): interleaved() written raw by a bounded child, the
    probe's SYSRESETREQ session started once inflight_writes shows it in flight. `writeInFlight` is their host-side
    overlap, without which the step fails as NotInterrupted; the USB port (UsbWatch) is recorded, never required."""
    dev = block_device(self.usb_path)
    payload = self.dir / 'interrupt.uf2'
    data = interleaved(u, INTERRUPT_PASSES)
    payload.write_bytes(data)
    cmd = [sys.executable, '-B', __file__, 'uf2-write', '--dev', dev, '--file', payload, '--offset', str(INTERRUPT_OFFSET)]
    ev = {'passes': INTERRUPT_PASSES, 'blocks': len(data) // 512, 'dev': dev}
    watch = UsbWatch(self.usb_path)
    try:   # the watcher ends however the step does; every exit's evidence is `ev` itself
      return self.interrupted(ev, cmd, dev)
    finally:
      ev['usb'] = watch.stop()

  def interrupted(self, ev, cmd, dev):
    p = launch(cmd, self.log)
    try:
      ev['trigger'] = wait_for(lambda: 'write in flight' if inflight_writes(dev) else
                               'write ended' if p.poll() is not None else None, USB_TIMEOUT, f'a write in flight on {dev}')
      ev['resetStart'] = time.monotonic()
      ev['resetTail'] = self.sysreset().strip().splitlines()[-3:]
      ev['resetEnd'] = time.monotonic()
    finally:
      try:
        code, out = collect(p, cmd, self.log, INTERRUPT_TIMEOUT)
      except SpawnTimeout as e:
        ev['survivors'] = e.survivors
        raise StepFail(str(e), ev) from None
    res = last_json(out) or {}
    ev['write'] = dict(res, exit=code)
    ev['writeInFlight'] = res.get('phase') == 'write' and isinstance(res.get('writeStart'), (int, float)) and \
      isinstance(res.get('writeEnd'), (int, float)) and res['writeStart'] < ev['resetStart'] and \
      res['writeEnd'] > ev['resetEnd']
    try:
      ev['afterReset'] = wait_for(lambda: usb_at(self.usb_path), USB_TIMEOUT, f'a device at {self.usb_path}')
    except StepFail:
      ev['afterReset'] = None
    ev['claim'] = 'host-side overlap of the write and the reset session; NOR erase/program at the reset inferred'
    if not ev['writeInFlight']:
      raise NotInterrupted('the reset session did not overlap the write: no mid-write interruption', ev)
    return ev

  def verify_flash(self, images, settle=None):
    """`images` ([(address, file)]) verified at their flash addresses in a session of the runner's, `settle` ms after
    its connect, then a reset, which reboots TinyUF2 whatever the verify's flash access left in RAM."""
    verify = ['h', *(f'verifybin {path},{addr:#x}' for addr, path in images), 'r', 'g']
    self.probe.run(([f'sleep {settle}'] if settle else []) + verify)

  def restore(self, files, version):
    """Cleanup: the record's TinyUF2 installed again and its blinky copied through the drive; the board must
    leave DFU and stay out of it."""
    self.install(files)
    ev = {'dfu': self.dfu_after_install(version)['usb'], 'copy': self.copy(files['blinky'], files['blinkyBlocks'])}
    if 'flush' in ev['copy']:
      ev['copy']['flush']['detail'] += '; restored image not independently verified'
    ev.update(self.after_copy())
    stays_away(lambda: usb_device(self.f['vid'], self.f['pid'], self.b['uid']), QUIET_TIME,
               'the DFU device came back after the blinky copy', ev)
    return {'pass': True, 'state': 'blinky copied', 'evidence': ev}

  def report_fields(self):
    # the cleanup's retries and cycles land here too: the same lists
    return {'jlinkRetried': self.probe.retried, **({'portCycles': self.power.cycles} if self.power.cfg else {}),
            **({'buildLocksKept': self.kept} if self.kept else {})}

  def install(self, files):
    """The record's HEX through the provider's J-Link flash (the script the record's tinyuf2-jlink target runs), then
    what it programs verified in a session of the runner's (verify_images)."""
    ops = []

    def flash(run):
      ops.append(provider().flash_jlink(self.probe.flasher, str(files['hex']), timeout=PROBE_TIMEOUT, run=run,
                                        workdir=str(self.dir)))
      return ops[0]

    def judge(code, out):
      return judge_jlink_target(ops[0], self.b, files['hex'])
    ev = self.flash_target(files['flash'], flash, judge,
                           lambda code, out: stopped_before_target(code, out, self.b['probe']), 'JLinkExe', PROBE_TIMEOUT)
    unlocks = JLINK_CONNECT_UNLOCKS.get(self.b['device'])
    self.verify_flash(files['verify'], unlocks and unlocks[1])
    return dict(ev, verified=True)

  def readback(self, addr, want):
    """A read of `want`'s length at `addr` into a file of the run dir in the tool's READ form: (the file, the
    command). The file is the evidence, never the tool's printed result."""
    path = self.dir / f'readback-{time.monotonic_ns()}.bin'
    return path, self.READ.format(path=path, addr=addr, n=len(want))

  def read_back_install(self, ev, files, halt, end):
    """What the install programmed read back (verify_images) in one session of the runner's, `halt`, the reads,
    then `end`, and compared byte for byte."""
    reads = []
    for addr, p in files['verify']:
      want = Path(p).read_bytes()
      reads.append((want, *self.readback(addr, want)))
    self.probe.run([halt, *(op for _, _, op in reads), end])
    if not all(uploaded(path, want) for want, path, _ in reads):
      raise StepFail('the HEX does not read back from its flash addresses', ev)
    return dict(ev, verified=True)

  def after_copy(self):
    return {}

  def observe_app(self, app_bin):
    """The fixture running from the bootloader handoff: two halts in one session, the counter moving,
    PC at its handler in thread mode, VTOR and MSP from its vector table, and its image intact. The
    in-script wait covers a connect that resets the core and so restarts the double-tap window."""
    f = self.f
    out = self.probe.run(['h', 'g', f'sleep {2 * f["dblTapDelayMs"] + 200}', 'h', 'regs', f'mem32 {SCB_VTOR:08X} 1',
                          'g', 'sleep 10', 'h', 'regs', f'verifybin {app_bin},{f["appStart"]:#x}', 'g'])
    chunks = provider().jlink_after(out, 'regs')
    if len(chunks) != 2:
      raise StepFail(f'expected two regs dumps, got {len(chunks)}', {'tail': out.strip().splitlines()[-8:]})
    first, second = regs(chunks[0]), regs(chunks[1])
    m = re.search(rf'^{SCB_VTOR:08X} = ([0-9A-F]{{8}})', out, re.M)
    if not m:
      raise StepFail('no VTOR read in the transcript')
    return self.app_evidence(first, second, int(m.group(1), 16))

  def app_evidence(self, first, second, vtor):
    """The fixture's two samples: the counter moving, PC at its handler in thread mode, VTOR and MSP from its vector
    table; its image was verified in the same session."""
    f = self.f
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
    self.sysreset()
    watch = 2 * f['dblTapDelayMs'] / 1000 + USB_TIMEOUT
    stays_away(lambda: usb_device(f['vid'], f['pid'], self.b['uid']), watch, 'the reset without the magic entered DFU',
               {'controlBootedApp': False})
    return {'control': self.observe_app(app_bin), 'controlWatchedS': watch, 'controlBootedApp': True}


class StlinkBattery(Battery):
  """The J-Link battery's steps on an ST-LINK board, each probe session one STM32CubeProgrammer script."""

  READ = '-u 0x{addr:08X} {n:#x} {path}'

  def __init__(self, board, facts, workdir, fail_at=None, commissioning=False):
    super().__init__(board, facts, workdir, fail_at, commissioning)
    self.probe = StlinkProbe(board, workdir, self.log)

  def install(self, files):
    """The record's HEX through the provider's ST-LINK flash (the command the record's tinyuf2-stlink target runs,
    without the CLI's verify), then what it programs read back (verify_images) in a session of the runner's, which
    ends in a system reset (bench: the core runs after `-rst`)."""
    ev = self.flash_target(files['flash'], lambda run: provider().flash_stlink(self.probe.flasher, str(files['hex']),
                                                                              timeout=PROBE_TIMEOUT, run=run),
                           lambda code, out: judge_stlink_target(code, out, self.b),
                           lambda code, out: stlink_failure(ANSI.sub('', out))['beforeTarget'], 'STM32_Programmer_CLI',
                           PROBE_TIMEOUT)
    return self.read_back_install(ev, files, '-halt', '-rst')

  def sysreset(self):
    """SYSRESETREQ without the CLI's read-back, which the reset would fail (bench: `-nv` writes and exits 0, the host
    sees the device re-enumerate); issued only once the write is reported done."""
    body = self.probe.sysreset()[0]
    if f'w @0x{SCB_AIRCR:08x}:  0x{AIRCR_SYSRESETREQ:08x}' not in body:
      raise StepFail('the reset write was not reported done', {'tail': body.strip().splitlines()[-3:]})
    return body

  def observe_app(self, app_bin):
    """observe_app's session as one script: two halts in one connection, the image read back in it."""
    f = self.f
    want = Path(app_bin).read_bytes()
    path, op = self.readback(f['appStart'], want)
    vtor = f'-r32 0x{SCB_VTOR:08X} 1'
    ops = ['-halt', '-run', f'#Delay({2 * f["dblTapDelayMs"] + 200})', '-halt', '-coreReg', vtor, '-run', '#Delay(10)',
           '-halt', '-coreReg', op, '-run']
    out = self.probe.run(ops)
    if not uploaded(path, want):
      raise StepFail('the fixture image does not read back from the app start')
    first, second = (core_regs(body) for o, body in zip(ops, out) if o == '-coreReg')
    return self.app_evidence(first, second, r32_value(out[ops.index(vtor)], SCB_VTOR))


# openocd 0.12.0+dev-g0ce743125 (the rig's build): what its CMSIS-DAP driver logs with no probe of the serial and USB ID,
# what `program ... reset exit` (startup.tcl) and the closing `shutdown` echo, and a debug port read
OPENOCD_NO_PROBE = 'unable to find a matching CMSIS-DAP device'
OPENOCD_SHUTDOWN = 'shutdown command invoked'
OPENOCD_PROGRAM = ('** Programming Started **', '** Programming Finished **', '** Resetting Target **', OPENOCD_SHUTDOWN)


def openocd_error(out):
  """Whether an openocd transcript has an error line."""
  return re.search(r'^\s*Error', out, re.M) is not None


def openocd_failure(out):
  """A session recognised as ending before any target connect: no probe with the serial and USB ID, and no debug port
  read (a DPIDR line). Any other failure may have reached the target."""
  return {'tail': out.strip().splitlines()[-5:], 'beforeTarget': OPENOCD_NO_PROBE in out and 'DPIDR' not in out}


def judge_openocd_target(code, out, cmd, hex_path):
  """The provider's openocd flash of the record's HEX (`program <hex> reset exit`, without program's verify: the
  runner reads the image back itself): openocd exits 0 once the proc's own shutdown ran, so success is read from the
  transcript too: each of program's phases echoed in order and no error line."""
  seen = iter(l.strip() for l in out.splitlines())
  if code or f'program {hex_path} reset exit' not in str(cmd) or not all(p in seen for p in OPENOCD_PROGRAM) or \
     openocd_error(out):
    raise StepFail(f'the openocd flash failed (exit {code})', openocd_failure(out))
  return {'flashDownload': '** Programming Finished **'}


class OpenocdProbe:
  """openocd sessions on a CMSIS-DAP probe, each through the flash provider's run_openocd_commands: init, the commands,
  shutdown, from a script in the run dir. openocd stops at the first failing command and exits 1; success is read from
  the transcript too: the closing shutdown and no error line."""

  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log
    self.retried = []   # the report's jlinkRetried: an openocd session is never retried
    self.flasher = {'name': 'openocd', 'uid': board['probe'], 'args': board['args'], 'vid_pid': board['vid_pid']}

  def run(self, commands):
    return self.judge(provider().run_openocd_commands(self.flasher, list(commands), timeout=PROBE_TIMEOUT,
                                                      run=tool_runner(self.log), workdir=str(self.dir)))

  def sysreset(self):
    """The provider's SYSRESETREQ session (the AIRCR write). Bench: the write and the shutdown after it complete
    cleanly, so it is judged as any session; the caller's observation is the evidence of the reset."""
    return self.judge(provider().sysresetreq_openocd(self.flasher, timeout=PROBE_TIMEOUT, run=tool_runner(self.log),
                                                     workdir=str(self.dir)))

  def judge(self, op):
    a = op.attempts[-1]
    code, out = a.result.returncode, text(a.result.stdout)
    if a.timed_out:
      raise StepFail(f'openocd timed out after {PROBE_TIMEOUT}s', dict(openocd_failure(out), beforeTarget=False))
    if code or OPENOCD_SHUTDOWN not in out or openocd_error(out):
      raise StepFail(f'openocd failed (exit {code})', openocd_failure(out))
    return out

  def mem32(self, addrs):
    out = self.run([shown(f'mdw 0x{a:08x}') for a in addrs])
    return {a: mdw_value(out, a) for a in addrs}

  def write32(self, addr, value):
    """Halt, write, read back, resume: only the read-back proves the write."""
    got = mdw_value(self.run(['halt', f'mww 0x{addr:08x} 0x{value:08x}', shown(f'mdw 0x{addr:08x}'), 'resume']), addr)
    if got != value:
      raise StepFail(f'{addr:#010x} reads back {got:08X}, not {value:#010x}')
    return hex(value)


def shown(command):
  """A command whose result the runner parses: from a script, openocd prints a command's result only when it is echoed
  (rig, openocd 0ce743125: a bare `mdw` in a -f script printed nothing, `echo [mdw ...]` its value)."""
  return f'echo [{command}]'


def mdw_value(out, addr):
  m = re.findall(rf'^0x{addr:08x}: ([0-9a-f]{{8}}) *$', out, re.M)
  if len(m) != 1:
    raise StepFail(f'mdw gave no single value for {addr:#x}')
  return int(m[0], 16)


# armv7m's register names (rig: `reg xPSR` is "not found in current target"); `reg NAME` gives "NAME (/32): 0x%08x"
OPENOCD_REGS = ('pc', 'r0', 'msp', 'xpsr')


def openocd_regs(out):
  """The two samples of OPENOCD_REGS a session read, in order."""
  vals = {r: re.findall(rf'^{r} \(/32\): 0x([0-9a-f]{{8}})$', out, re.M) for r in OPENOCD_REGS}
  if any(len(v) != 2 for v in vals.values()):
    raise StepFail(f'expected two samples of {list(OPENOCD_REGS)}, got {[len(v) for v in vals.values()]}',
                   {'tail': out.strip().splitlines()[-8:]})
  return [{'pc': int(vals['pc'][i], 16), 'r0': int(vals['r0'][i], 16), 'msp': int(vals['msp'][i], 16),
           'ipsr': int(vals['xpsr'][i], 16) & 0x1FF} for i in (0, 1)]


class OpenocdBattery(Battery):
  """The J-Link battery's steps on a CMSIS-DAP board, each probe session one openocd script."""

  READ = 'dump_image {{{path}}} 0x{addr:08x} {n:#x}'

  def __init__(self, board, facts, workdir, fail_at=None, commissioning=False):
    super().__init__(board, facts, workdir, fail_at, commissioning)
    self.probe = OpenocdProbe(board, workdir, self.log)

  def install(self, files):
    """The record's HEX through the provider's openocd flash (`program` with reset, without its verify, as the
    ST-LINK install drops the CLI's: the file the record's tinyuf2-openocd target programs), then what it programs
    read back (verify_images) and compared in a session of the runner's, which ends in `reset run`."""
    hexp, ops, flasher = str(files['hex']), [], dict(self.probe.flasher, verify=False)
    ev = self.flash_target(files['flash'], lambda run: ops.append(provider().flash_openocd(
                             flasher, hexp, timeout=CMSIS_DAP_TIMEOUT, run=run)) or ops[-1],
                           lambda code, out: judge_openocd_target(code, out, ops[-1].attempts[-1].cmd, hexp),
                           lambda code, out: openocd_failure(out)['beforeTarget'], 'openocd', CMSIS_DAP_TIMEOUT)
    return self.read_back_install(ev, files, 'halt', 'reset run')

  def sysreset(self):
    return self.probe.sysreset()

  def observe_app(self, app_bin):
    """observe_app's session as one script: two halts in one connection, the image read back in it."""
    f = self.f
    want = Path(app_bin).read_bytes()
    path, dump = self.readback(f['appStart'], want)
    regs_ = [shown(f'reg {r}') for r in OPENOCD_REGS]
    out = self.probe.run(['halt', 'resume', f'sleep {2 * f["dblTapDelayMs"] + 200}', 'halt', *regs_,
                          shown(f'mdw 0x{SCB_VTOR:08x}'), 'resume', 'sleep 10', 'halt', *regs_, dump, 'resume'])
    if not uploaded(path, want):
      raise StepFail('the fixture image does not read back from the app start')
    first, second = openocd_regs(out)
    return self.app_evidence(first, second, mdw_value(out, SCB_VTOR))


def nonce_block(nonce):
  """apps/dfu_runtime's nonce block (dfu_runtime.h): magic, LE length, the nonce, then each byte its offset."""
  head = NONCE_MAGIC + len(nonce).to_bytes(4, 'little') + nonce
  return head + bytes(i & 0xff for i in range(len(head), NONCE_BLOCK))


def pack_uf2(chunks, family):
  """A UF2 of [(addr, 256 bytes)], numbered in order under one numBlocks."""
  return b''.join(struct.pack('<8I', UF2_MAGIC[0], UF2_MAGIC[1], UF2_FLAG_FAMILY, addr, 256, i, len(chunks), family) +
                  data + bytes(476 - len(data)) + struct.pack('<I', UF2_MAGIC[2]) for i, (addr, data) in enumerate(chunks))


def esp_app_chunks(uf2_path, facts, board):
  """The 256-byte chunks of the record's apps/dfu_runtime.uf2 (one family, contiguous from address 0: espressif
  UF2 addresses are ota_0 offsets) and the nonce block's offset, ota_0's last 256 bytes, where the app reads it.
  The image must end before it, and TinyUF2's flash cache window over it must lie inside ota_0
  (board_flash.c reads and rewrites the whole FLASH_CACHE_SIZE-aligned window)."""
  blocks = contiguous_uf2(uf2_path, facts['family'], 0, 'the app')
  size, cache = board['app'][1] - board['app'][0], facts['flashCache']
  off = size - NONCE_BLOCK
  if not blocks or off < 256 * len(blocks) or off % 256 or off // cache * cache + cache > size:
    raise Refused(f'{uf2_path}: the app [0, {256 * len(blocks):#x}) and the nonce block at {off:#x} (in a {cache:#x} '
                  f'cache window) do not both fit in the {size:#x} app partition in order')
  return {'appChunks': [bl['data'] for bl in blocks], 'nonceOffset': off}


def security_evidence(res, chip, source):
  """The `security` the provider requires: its reading of the esptool_session security op (security_evidence), admitted
  by its admit_security; anything else refuses the JTAG flash before it starts."""
  try:
    return openocd_esp().admit_security(openocd_esp().security_evidence(res, chip=chip, source=source))
  except ValueError as e:
    raise StepFail(f'flash encryption or secure boot is not read off on this chip: {e}; openocd_esp writes plaintext, '
                   'so nothing was programmed', {'security': res}) from None


def judge_openocd_esp(op):
  """flash_openocd_esp's own record: every segment written, its bank hash verified and read back byte for byte,
  then the reviewed end (reset run, shutdown, exit confirmed), so cleanup done."""
  segs = [{'offset': hex(s['offset']), 'verified': bool((s.get('program') or {}).get('verified')),
           'readBack': bool((s.get('readBack') or {}).get('match'))} for s in getattr(op, 'segments', ())]
  if op.returncode != 0 or op.cleanup != 'done' or not segs or not all(s['verified'] and s['readBack'] for s in segs):
    raise StepFail(f'the openocd_esp flash failed (exit {op.returncode}): {op.session.get("failure")}',
                   {'segments': segs, 'cleanup': op.cleanup, 'log': op.session.get('log')})
  return {'wrote': [s['offset'] for s in segs], 'jtag': {k: op.session.get(k) for k in ('openocd', 'location', 'log')}}


class EspBattery(Battery):
  """The battery on an Espressif board. TinyUF2 copies apps/dfu_runtime with this run's nonce block past the
  image; the app reports the nonce in its DFU runtime interface string and returns to DFU on DFU_DETACH."""
  def __init__(self, board, facts, workdir, fail_at=None, commissioning=False):
    super().__init__(board, facts, workdir, fail_at, commissioning)
    self.tool, self.preserved = Esptool(board, workdir, self.log), None
    # TinyUF2 takes espressif UF2 addresses as ota_0 offsets and reports ota_0 as its flash
    self.app_start, self.dfu_flash = 0, board['app'][1] - board['app'][0]
    self.dfu_claim = 'DFU observed'

  def after_copy(self):
    """The preserved regions checked again once blinky is copied, against the snapshot."""
    keep = self.b['regions']['preserved']
    after = self.tool.run(preserved_ops(keep), 'hard-reset')['results']
    check_preserved(self.preserved, preserved_md5(keep, after), 'restore')
    return {'preserved': 'unchanged since the snapshot before the install'}

  def install(self, files):
    """The preserved regions' snapshot first, in a session of its own, which the report keeps however the run ends:
    a recovery's restore checks against it. A restore reuses the run's snapshot, or a recovery's. Then the record's
    segments through the provider's esptool flash, the runner's own esptool on the transport's tty, from the build
    dir under its lock as flash_args names them; then the runner's own read-back. The openocd_esp route: jtag()."""
    if self.b['flasher'] == 'openocd_esp':
      return self.jtag(files)
    tty = esp_port(self.b['probe'])   # no tty fails here, untouched; any session may leave the chip in its ROM loader
    self.touched = True
    if self.preserved is None:
      keep = self.b['regions']['preserved']
      self.preserved = preserved_md5(keep, self.tool.run(preserved_ops(keep), 'no-reset')['results'])
    fl = files['flash']

    def flash(run):   # under the build dir's lock, its inputs checked: flash_args from bytes that hash as recorded
      raw = (fl['root'] / 'flash_args').read_bytes()
      if hashlib.sha256(raw).hexdigest() != fl['sha256']['flash_args']:
        raise StepFail('flash_args changed after the inputs were checked; nothing was flashed')
      # the settings line, then one "OFFSET FILE" per segment, relative to the build dir
      args = '--no-stub' if files.get('noStub') else ''   # as the record's flash target runs it
      return provider().flash_esptool({'name': 'esptool', 'uid': self.b['probe'], 'args': args}, chip=self.b['device'],
                                      port=tty, flash_args=' '.join(raw.decode().split()), cwd=str(fl['root']),
                                      timeout=ESP_TIMEOUT, run=run, esptool=esptool_runtime()['exe'])
    ev = self.flash_target(fl, flash,
                           lambda code, out: judge_esp_target(code, out, files['segments']), lambda code, out: False,
                           'esptool', ESP_TIMEOUT)
    ev.update(esp_verify(self.tool, self.b, files['segments'], self.dir, self.preserved))
    return {'wrote': ev['wrote'], 'writes': ev['writes'], 'readBack': True, **esptool_evidence(),
            'operation': ev['operation']}

  def jtag(self, files):
    """The JTAG route under the one board lock, each step only after the previous one's cleanup completed: an esptool
    session over the USJ's tty reads the security state on the ROM loader, takes the snapshot (a restore reuses
    the run's) and hard-resets the chip out of the loader; agentrc's flash_openocd_esp programs the record's segments with verify, reads each back and ends
    with reset run and a confirmed shutdown; then the runner's esptool read-back and preservation check. A session
    left running is cleanup pending, and nothing follows it."""
    refuse_openocd(self.b['flasher'])   # before the security and snapshot session, as the provider before its own
    tty = esp_port(self.b['probe'])
    self.touched = True
    keep = self.b['regions']['preserved']
    # hard-reset: a chip left in the ROM loader faults openocd's flash stub after its reset init (PMP Load access fault);
    # the provider starts openocd no earlier than its BOOT_SETTLE after the flash call, so no wait of the runner's
    ops = [{'op': 'security'}] + (preserved_ops(keep) if self.preserved is None else [])
    session = self.tool.run(ops, 'hard-reset')
    res = session['results']
    security = security_evidence(res[0], self.b['device'],
                                 f'esptool {session["esptool"]} on {tty}, USJ {self.b["probe"]}, ROM loader')
    if self.preserved is None:
      self.preserved = preserved_md5(keep, res[1:])
    recorded = files['flash']['sha256']   # the provider admits only bytes that hash as the build record says
    segments = [{'offset': off, 'file': str(p), 'size': p.stat().st_size, 'sha256': recorded[esp.NATIVE[p.name]]}
                for off, p in files['segments']]
    seen = []

    def flash(run):   # the provider runs its own server, never a tracked child: run is unused
      op = None
      try:
        op = openocd_esp().flash_openocd_esp(self.b['route'], segments, security=security, workdir=str(self.dir),
                                             timeout=OPENOCD_TIMEOUT, retains_lock=True)
      except BaseException as e:
        op = getattr(e, 'operation', None)
        if isinstance(e, Interrupted) or not isinstance(e, Exception):
          raise
        if op is None:
          raise StepFail(f'openocd_esp refused the flash before starting: {e}') from None
      finally:   # before anything propagates: every receipt kept and marked
        protect(op)
        left = outstanding_sessions(self.dir)
        mark_pending(self.b.get('pendingMark'), left)
      seen.append(op)
      if op.cleanup == 'pending' or left:
        raise CleanupPending(f'the openocd_esp session is not ended ({op.session.get("failure")}): cleanup pending, '
                             f'receipt {op.session["receipt"]}', {'operation': operation_record(op)})
      return op
    ev = self.flash_target(files['flash'], flash, lambda code, out: judge_openocd_esp(seen[-1]), lambda code, out: False,
                           'openocd_esp', OPENOCD_TIMEOUT)
    ev.update(esp_verify(self.tool, self.b, files['segments'], self.dir, self.preserved))
    return {'route': 'openocd_esp', 'wrote': ev['wrote'], 'writes': ev['writes'], 'readBack': True, 'security': security,
            'jtag': ev['jtag'], **esptool_evidence(), 'operation': ev['operation']}

  def report_fields(self):
    keep = self.b['regions']['preserved']
    return {**({'buildLocksKept': self.kept} if self.kept else {}),
            'snapshot': self.preserved and {'preserved': self.preserved,
                                            'preservedRegions': {n: list(r) for n, r in keep.items()}}}

  def usb_dfu(self, op):
    f = self.f
    return child_json([sys.executable, '-B', USB_DFU, '--vid', hex(f['appVid']), '--pid', hex(f['appPid']),
                       '--serial', self.b['uid'], '--path', self.usb_path, op], self.log, USB_TIMEOUT, f'usb_dfu.py {op}')

  def app(self):
    return usb_device(self.f['appVid'], self.f['appPid'], self.b['uid'])

  def copy_app(self, step):
    self.nonce, cache = os.urandom(16), self.f['flashCache']
    image = 256 * len(self.chunks)
    uf2 = self.dir / f'{step}.uf2'
    uf2.write_bytes(pack_uf2([(256 * i, c) for i, c in enumerate(self.chunks)] +
                             [(self.nonce_off, nonce_block(self.nonce))], self.f['family']))
    return dict(self.copy(uf2, len(self.chunks) + 1, self.nonce),
                writes=[write_span('app image', 0, image, cache), write_span('nonce block', self.nonce_off, NONCE_BLOCK, cache)])

  def app_ran(self):
    f = self.f
    path = wait_for(self.app, USB_TIMEOUT, f'the app {f["appVid"]:04x}:{f["appPid"]:04x} serial {self.b["uid"]}')
    ev = {'usb': path}
    if path != self.usb_path:
      raise StepFail('the app came up on another USB port than DFU', dict(ev, expected=self.usb_path))
    ev['string'] = self.usb_dfu('string')['string']
    if ev['string'] != f'HIL {self.nonce.hex()}':
      raise StepFail('the app does not report this copy\'s nonce', ev)
    stays_away(lambda: usb_device(f['vid'], f['pid'], self.b['uid']), QUIET_TIME,
               'the DFU device came back while the app should run', ev)
    if self.app() != path:
      raise StepFail('the app left the bus', ev)
    return ev

  def reenter(self, version):
    ev = {'path': self.b['reentry']}
    try:
      self.usb_dfu('detach')
      ev['detachAcked'] = True
      wait_for(lambda: self.app() is None, USB_TIMEOUT, 'the app leaving the bus')
      ev['appLeft'] = True
      ev.update(self.dfu(version), dfuCameUp=True, claim='DFU_DETACH to the app re-entered DFU')
    except StepFail as e:
      e.evidence = {**ev, **e.evidence}
      raise
    try:
      if self.current_uf2(512 * len(self.chunks)) != b''.join(self.chunks):
        raise StepFail('CURRENT.UF2 does not read back the app image')
      off = self.nonce_off
      if self.current_uf2(512, off // 256 * 512) != nonce_block(self.nonce):
        raise StepFail(f'CURRENT.UF2 does not read back the nonce block at {off:#x}')
    except StepFail as e:
      e.evidence = {**ev, **e.evidence, 'failedAt': 'readback', 'appIntact': 'unshown'}
      raise
    ev['appIntact'] = True
    return ev

  def run(self, files, version):
    self.chunks, self.nonce_off = files['appChunks'], files['nonceOffset']
    self.step('install', lambda: self.install(files))
    self.step('dfu', lambda: self.dfu(version))
    self.step('copy', lambda: self.copy_app('copy'))
    self.step('app-ran', self.app_ran)
    self.step('reenter', lambda: self.reenter(version))
    self.step('recopy', lambda: dict(self.copy_app('recopy'), **self.app_ran(),
                                     claim='a fresh copy boots the app after re-entry'))


BATTERIES = {'jlink': Battery, 'stlink': StlinkBattery, 'openocd': OpenocdBattery, 'esp': EspBattery}


TERM_SIGNALS = {signal.SIGTERM, signal.SIGINT}
INTERRUPTS = []   # every signal on_signal took: the run ended `aborted` (report `_hil.termination`)


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
  INTERRUPTS.append(signum)
  if REGISTERING['on']:
    REGISTERING['signum'] = REGISTERING['signum'] or signum
    return
  raise Interrupted(f'interrupted by {signal.Signals(signum).name}')


def check_jlink():
  if shutil.which('JLinkExe') is None:
    raise Refused('JLinkExe must be on PATH')


def check_stlink():
  if shutil.which(STM32_PROGRAMMER_CLI) is None:
    raise Refused(f'{STM32_PROGRAMMER_CLI} must be on PATH')


def check_openocd():
  """openocd on PATH, and the bounded USB observation the probe check needs (probe_node), loaded before the lock."""
  if shutil.which('openocd') is None:
    raise Refused('openocd must be on PATH')
  usb_observe()


@functools.cache
def esptool_runtime():
  """The provider's esptool_runtime of `esptool` first on PATH, checked once for this process, so every Espressif
  flash and esptool_session.py session runs one esptool, whose version the evidence records. Refused otherwise."""
  try:
    return provider().esptool_runtime()
  except RuntimeError as e:
    raise Refused(f'no esptool runtime: {e}; the runner needs esptool first on PATH (SKILL.md Limits)') from None


def esptool_evidence():
  return {'esptool': esptool_runtime()['version'], 'esptoolPath': esptool_runtime()['exe']}


def check_openocd_esp():
  """The verified openocd-esp32 the provider runs, and the runner's esptool for the sessions over the USJ's tty."""
  esptool_runtime()
  try:
    openocd_esp().find_openocd()
  except RuntimeError as e:
    raise Refused(str(e))


def check_pyusb():
  try:
    import usb.backend.libusb1
  except ImportError:
    raise Refused(f'pyusb is not installed for {sys.executable}; usb_dfu.py needs it')
  if usb.backend.libusb1.get_backend() is None:
    raise Refused('pyusb finds no libusb-1.0; usb_dfu.py needs it')


def check_children():
  missing = [p.name for p in (ESP_SESSION, USB_DFU) if not p.is_file()]
  if missing:
    raise Refused(f'{AGENTRC} at its pin has no {", ".join(missing)} in {LOCK_HELPER.parent}: an Espressif battery '
                  "needs the `hil` provider's children")


def check_flasher(board):
  if board['kind'] == 'esp':
    check_children()
  {'esptool': esptool_runtime, 'stlink': check_stlink, 'openocd': check_openocd,
   'openocd_esp': check_openocd_esp}.get(board['flasher'], check_jlink)()
  if board.get('usbPower'):
    try:
      disable = port_dir(board['usbPower']) / 'disable'
    except StepFail as e:
      raise Refused(f'{board["name"]}: usbPower: {e}')
    if not os.access(disable, os.W_OK):
      raise Refused(f'{board["name"]}: usbPower: {disable} is not writable '
                  '(commissioning.md: 52-tinyuf2-hil-uhubctl.rules)')


def reentry_decision(row):
  """The re-entry method a commissioning run establishes (commissioning.md, Re-entry), or None: every
  observation of the tried method held, the board was cleaned up and released, and the run passed or failed
  only at reenter's CURRENT.UF2 readback."""
  cleanup = row.get('cleanup') or {}
  if not row.get('commissioning') or not cleanup.get('pass') or cleanup.get('heldAfter'):
    return None
  steps = row.get('steps', [])
  failed = [x for x in steps if not x['pass']]
  reenter = [x for x in steps if x['step'] == 'reenter']
  if len(reenter) != 1 or failed not in ([], reenter) or (not failed and not row.get('pass')) or \
     (failed and reenter[0]['evidence'].get('failedAt') != 'readback'):
    return None
  need = {'retained-register': ('controlBootedApp', 'dfuCameUp', 'magicConsumed'),
          'dfu-detach': ('detachAcked', 'appLeft', 'dfuCameUp')}[row['tried']]
  return row['tried'] if all(reenter[0]['evidence'].get(k) is True for k in need) else None


def admit_record(record_path, board, facts, workdir):
  """A build record the battery and restore may install, with what they need on this host."""
  files, fw = verify_record(record_path, board, facts, workdir)
  if board['kind'] != 'esp':
    data = parse_hex(files['hex'])
    check_ranges(data, [board['install']], FLASH_LIMITS[board['device']], files['hex'])
    if not hex_matches_bin(data, files['bin'], facts['binBase']):
      raise Refused(f'{files["hex"]} and {files["bin"]} do not hold the same bytes')
    files['verify'] = verify_images(data, workdir)
    check_bootloader_bin(files['bin'], board, facts, 'candidate')
  exclusion_configured(facts, board['uid'])
  if shutil.which('mcopy') is None:
    raise Refused('mcopy must be on PATH')
  check_flasher(board)
  return files, fw


def trial_reentry(board, method):
  """The board with `method` as its re-entry, for commissioning: refused once the roster's reentry is set."""
  if not method:
    return board
  if board['reentry'] is not None:
    raise Refused(f'{board["name"]}: reentry is already commissioned; --try-reentry is for commissioning only')
  if method not in REENTRY[board['kind']]:
    raise Refused(f'{board["name"]}: its battery re-enters by one of {REENTRY[board["kind"]]}')
  return dict(board, reentry=method)


def keep_blocker(helper, fh, workdir, detail):
  """Leave this run's protected record on the board as a recovery blocker naming why: closed, never cleared. A
  failed rewrite leaves the old record or an unreadable one, a blocker either way."""
  with contextlib.suppress(OSError):
    helper.write_record(fh, 'hil_test.py', protected=True, runDir=str(workdir), detail=detail)
  fh.close()


def release(helper, fh):
  if fh is not None:
    helper.clear_record(fh)
    fh.close()


def release_finished(helper, fh, row, code, done):
  """Release the board, touching CI's `done` marker (hil_ci.py's `<board>.done`) first when the row is no blocker:
  a run that takes the lock next never sees CI's finished battery as unfinished. hil_ci.py touches it again after
  its own verdict."""
  if done is not None and not MARK_ERRORS and \
     run_report.verdict(code, {'results': [row]}, row['board'])[0] != 'blocker':
    with contextlib.suppress(OSError):
      done.touch()
  release(helper, fh)


def run_board(args, board, facts, helper, workdir):
  row = {'board': board['name'], 'lock': board['lock'], 'ran': False, 'pass': False, 'locked': False,
         'lockBypassed': False, 'steps': [], 'cleanup': None, 'detail': ''}
  if board['route']:
    row['route'] = board['flasher']
  methods = REENTRY[board['kind']]
  update = args.update_record
  if update and args.try_reentry:
    raise Refused('--update-record runs on a commissioned board, never with --try-reentry')
  if args.fail_at and args.fail_at not in (*STEPS['update' if update else board['kind']], 'cleanup'):
    raise Refused(f'{board["name"]}: its battery has no step {args.fail_at}')
  if args.try_reentry:
    board = trial_reentry(board, args.try_reentry)
    row.update(commissioning=True, tried=args.try_reentry)
  elif board['reentry'] not in methods:
    raise Refused(f'{board["name"]}: tinyuf2.reentry must be one of {methods} (set from commissioning)')
  files, row['firmware'] = admit_record(args.build_record, board, facts, workdir)
  if update:
    files['update'], row['update'] = admit_update(update, board, facts, workdir, files, row['firmware'])
  if board['kind'] == 'esp':
    check_pyusb()
  # blocked from here until the process exits or becomes the holder (keep_held): a signal acts only
  # inside the battery, and the report and any hold are settled first
  signal.pthread_sigmask(signal.SIG_BLOCK, TERM_SIGNALS)
  deadline = time.monotonic() + args.lock_wait
  while True:
    try:
      # protected: a battery that dies holding the board leaves this record as a recovery blocker (SKILL.md Recovery)
      fh = helper.acquire_board_lock(board['lock'], protected=True, runDir=str(workdir))
      break
    except helper.LockUnavailable as e:
      raise Refused(f'{board["name"]}: {e}; refusing to run unlocked')
    except helper.RecoveryBlocked as e:   # a cleanup holder, a stale record or a takeover journal (SKILL.md Recovery)
      row.update(locked=True, recoveryBlocker=True, detail=str(e))
      return deferred(row), 1
    except RuntimeError as e:
      held, left = str(e), deadline - time.monotonic()
      if left <= 0:
        row.update(locked=True, recoveryBlocker=False, detail=held)
        return deferred(row), 1
    try:
      with signals(signal.SIG_UNBLOCK):
        time.sleep(min(LOCK_POLL, left))
    except Interrupted as e:   # nothing taken yet: the board's row is a locked one
      row.update(locked=True, recoveryBlocker=False, detail=f'{held}; {e} while waiting for the lock')
      return deferred(row), 1
    if time.monotonic() >= deadline:   # no try past the budget, whatever the lock does meanwhile
      row.update(locked=True, recoveryBlocker=False, detail=held)
      return deferred(row), 1
  row['lockBypassed'] = fh is None
  try:
    if args.started_marker is not None:   # under the lock: a run waiting on the board is never seen started
      try:
        args.started_marker.touch()
      except OSError as e:
        raise Refused(f'started marker {args.started_marker} cannot be written: {e}')
    # a transition check for the remote driver: CI's markers name a battery an older driver started without this lock
    try:
      earlier = [] if args.ci_state_root is None else hil_ci.unfinished(args.ci_state_root, board['name'])
    except OSError as e:
      raise Refused(f'CI state root {args.ci_state_root} cannot be read: {e}')
    if earlier:
      detail = (f'CI run {", ".join(earlier)} under {args.ci_state_root} started a battery on {board["name"]} and has '
                'no .done: an unfinished attempt')
      if fh is not None:
        keep_blocker(helper, fh, workdir, detail)
      row.update(recoveryBlocker=True, unfinishedAttempts=earlier, detail=detail)
      return deferred(row), 1
    try:
      users = probe_users(board)
    except StepFail as e:   # an Espressif board without exactly one tty: not run, nothing touched
      row['detail'] = f'probe check: {e}'
      release_finished(helper, fh, row, 1, args.done_marker)
      return deferred(row), 1
    if users:   # a session from an earlier run, left on this probe: nothing may overlap it (SKILL.md Recovery)
      row.update(probeUsers=users, detail=f'probe {board["probe"]} is still in use by pids {users}; no session may overlap them')
      release(helper, fh)
      return deferred(row), 2
    bat = BATTERIES[board['kind']](board, facts, workdir, args.fail_at, row.get('commissioning', False))
  except BaseException:   # nothing touched yet: no recovery blocker
    if fh is not None and not fh.closed:
      release(helper, fh)
    raise
  code = 0
  try:
    row['ran'] = True
    with signals(signal.SIG_UNBLOCK):
      (bat.run_update if update else bat.run)(files, row['firmware']['version'])
    row['pass'] = True
  except BaseException as e:   # anything after admission still cleans up below
    row['detail'] = f'{bat.at}: {e}' if isinstance(e, StepFail) else f'{bat.at}: {type(e).__name__}: {e}'
    code = 1
  row['steps'] = bat.steps
  code = clean_up(row, code, bat, fh, board, helper, files, args.done_marker)
  row.update(bat.report_fields())   # after the cleanup, whose install may take the snapshot a recovery needs
  if row.get('commissioning'):
    row['reentryDecision'] = reentry_decision(row)
  return deferred(row), code


def deferred(row):
  pending = sorted(signal.Signals(s).name for s in signal.sigpending() & TERM_SIGNALS)
  if pending:
    row['detail'] = '; '.join(filter(None, (row['detail'], f'{", ".join(pending)} deferred until the board was settled')))
  return row


def clean_up(row, code, bat, fh, board, helper, files, done=None):
  """Restore a touched board to the record's TinyUF2 with blinky copied, then release it (release_finished(), `done`
  CI's marker). A child that survived SIGKILL, or any unsuccessful cleanup, leaves the board held (exit 4), touched or
  not."""
  stuck = []
  try:
    refuse_pending(bat.dir, board.get('pendingMark'))
    stuck = settle_children()
    if stuck:
      raise StepFail('children survived SIGKILL; no flash may overlap them')   # their pids are in survivors
    if bat.touched:
      if bat.fail_at == 'cleanup':
        raise StepFail('--fail-at cleanup: injected cleanup failure (acceptance only)')
      release_ended_builds()   # the restore's flash would block on a build lock this process still keeps
      row['cleanup'] = dict(bat.restore(files, row['firmware']['version']), heldAfter=False)
      stuck = settle_children()   # the restore's own children, before the lock is released
      if stuck:
        raise StepFail('the restore left children that survived SIGKILL')
    else:
      row['cleanup'] = {'pass': True, 'state': 'untouched', 'evidence': {}, 'heldAfter': False}
  except BaseException as e:
    pending = outstanding_sessions(bat.dir)   # kept, never reaped: recovery ends each by its receipt
    mark_pending(board.get('pendingMark'), pending)   # contained: a failure must not cost the hand-off below
    stuck += [x for x in settle_children() + pending if x not in stuck]
    row['cleanup'] = {'pass': False, 'state': 'pending' if pending else 'unknown' if bat.touched else 'untouched',
                       'evidence': getattr(e, 'evidence', {}), 'detail': f'{type(e).__name__}: {e}',
                       'survivors': stuck, 'heldAfter': fh is not None,
                       **({'receipts': [s['receipt'] for s in pending]} if pending else {}),
                       **({'markErrors': MARK_ERRORS[:]} if MARK_ERRORS else {})}
    row['pass'] = False
    if fh is not None:
      row['cleanup']['holder'] = hand_off(fh, board['lock'], row['cleanup']['detail'], stuck, helper=helper)
      fh = None
    return 4
  release_finished(helper, fh, row, code, done)
  return code


def settle_manual(result, bat, board, run_dir):
  """A manual install's or restore's survivors however it went: children left, sessions not ended (marked for later
  invocations) and the build locks a keeper holds."""
  result['survivors'] = settle_children() + outstanding_sessions(run_dir)
  mark_pending(board['pendingMark'], [x for x in result['survivors'] if 'receipt' in x])
  result.update(bat.kept and {'buildLocksKept': bat.kept} or {})


def build_provenance(result):
  """The admitted record's firmware, as the report's rows name it, or {} when no row does: never filled in."""
  for r in result['results']:
    fw = r.get('firmware') or r.get('installed')
    if isinstance(fw, dict):
      return {k: fw[k] for k in ('buildRecord', 'path', 'sha256', 'version') if fw.get(k) is not None}
  return {}


def publish_report(result, run_dir, args, argv):
  """`result` as the run dir's hil_report.json and .md through the report core (`hil` Reporting): `_hil` beside
  the native fields, attempt id the run dir's own unique name. A failure never raises: it sets `reportError`, and
  `reportPath` to None unless the JSON was written, for the stdout report and the holder that follow."""
  try:
    core = report_core()
    schema = run_report.schema(core)
    attempt = core.start_attempt(run_dir, schema, False, run_dir.name)
    try:   # {name, sha256}: the same in a checkout and on a rig, where the report chain compares it whole
      roster = core.roster_identity(args.config)
    except OSError:
      roster = {'name': Path(args.config).name}
    meta = core.make_meta(schema, attempt, termination='aborted' if INTERRUPTS else 'completed',
                          invocation=['hil_test.py', *map(str, argv)], selection=[args.board], host=socket.gethostname(),
                          roster=roster,
                          build=build_provenance(result) or None)
    core.publish(run_dir, schema, result, meta)
  except Exception as e:   # the run's own outcome, its stdout report and any hold stand whatever failed here
    if result['reportPath'] not in getattr(e, 'published', ()):
      result['reportPath'] = None
    result['reportError'] = f'report not published: {type(e).__name__}: {e}'


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  sub = ap.add_subparsers(dest='cmd', required=True)
  r = sub.add_parser('run', help='the battery on one board (self-locking)')
  r.add_argument('-b', '--board', required=True)
  r.add_argument('--build-record', required=True, help='check_build.py --board B --shared --hil-config ROSTER '
                 'JSON, under cmake-build/')
  r.add_argument('--fail-at', choices=(*STEPS['esp'], *STEPS['update'][2:], 'cleanup'),
                 help='acceptance only: fail this step, or the cleanup, to exercise cleanup and its holder')
  r.add_argument('--try-reentry', choices=REENTRY_METHODS, help="commissioning only, while the roster's reentry is unset")
  r.add_argument('--update-record', help='the update battery in place of the app battery: the check_build --variant '
                 "record whose updater the board takes before the candidate's (SKILL.md Execution, Update)")
  r.add_argument('--lock-wait', type=int, default=0,
                 help='seconds to keep trying a held board; a cleanup holder or a recovery blocker is never waited for')
  r.add_argument('--run-root', type=Path, help="where this run's directory goes (default cmake-build/hil)")
  r.add_argument('--route', help="an install route from the board's tinyuf2.routes (default its roster flasher)")
  r.add_argument('--ci-state-root', type=Path, help="transition only, from a driver: CI's state directory, whose "
                 'unfinished battery on the board refuses the run and keeps it a recovery blocker')
  r.add_argument('--done-marker', type=Path, help="hil_ci.py's only: its <board>.done, touched before the board is "
                 'released when the run is no blocker')
  r.add_argument('--started-marker', type=Path, help="hil_ci.py's only: its <board>.started, touched once the board "
                 'is locked, before any hardware access; refused, the board released, when it cannot be written')
  r.add_argument('config')
  i = sub.add_parser('install', help='program a bootloader under your own manual hold')
  i.add_argument('-b', '--board', required=True)
  i.add_argument('--build-record', required=True, help="the HIL build record whose TinyUF2 is installed")
  i.add_argument('--under-hold', required=True, metavar='REASON')
  i.add_argument('--try-reentry', choices=REENTRY_METHODS,
                 help="commissioning only, while the roster's reentry is unset: DFU's fallback after the install")
  i.add_argument('--route', help="an install route from the board's tinyuf2.routes (default its roster flasher)")
  i.add_argument('config')
  s = sub.add_parser('restore', help="install the record's TinyUF2 and copy its blinky, under your hold or to "
                     'recover a holder')
  s.add_argument('-b', '--board', required=True)
  s.add_argument('--build-record', required=True, help='the build record whose TinyUF2 and apps/blinky.uf2 are installed')
  g = s.add_mutually_exclusive_group(required=True)
  g.add_argument('--under-hold', metavar='REASON')
  g.add_argument('--recover-holder', type=int, metavar='PID')
  g.add_argument('--recover-takeover', metavar='TOKEN', help='the `hil_lock.py hold --take-over` of a stale battery '
                 'record: restore, then release that token')
  s.add_argument('--report', help="the failed run's hil_report.json (with --recover-holder, or --recover-takeover of a dead cleanup holder)")
  s.add_argument('--try-reentry', choices=REENTRY_METHODS,
                 help="commissioning only, under your hold, while the roster's reentry is unset")
  s.add_argument('--route', help="an install route from the board's tinyuf2.routes (default its roster flasher)")
  s.add_argument('config')
  cp = sub.add_parser('clear-pending', help="remove a board's pending mark: every session it lists ended, or after a "
                      'separately reviewed recovery')
  cp.add_argument('-b', '--board', required=True)
  cp.add_argument('--after-reviewed-recovery', metavar='NOTE',
                  help='the reviewed recovery that ended the sessions some other way; recorded, then the mark removed')
  ch = cp.add_mutually_exclusive_group()
  ch.add_argument('--under-hold', metavar='REASON', help='with --after-reviewed-recovery: your manual hold of the board')
  ch.add_argument('--recover-holder', type=int, metavar='PID',
                  help="with --after-reviewed-recovery: the failed run's cleanup holder")
  cp.add_argument('config')
  fr = sub.add_parser('fat-read')
  fr.add_argument('--dev', required=True)
  fr.add_argument('--file', required=True)
  fr.add_argument('--length', type=int, required=True)
  fr.add_argument('--offset', type=int, default=0)
  fl = sub.add_parser('flush')
  fl.add_argument('--dev', required=True)
  uw = sub.add_parser('uf2-write')
  uw.add_argument('--dev', required=True)
  uw.add_argument('--file', required=True)
  uw.add_argument('--offset', type=int, required=True)
  kh = sub.add_parser('keep-held', help='internal: the re-executed cleanup holder (exec_holder)')
  kh.add_argument('fd', type=int)
  kh.add_argument('ack', type=int)
  kb = sub.add_parser('keep-build', help="internal: the re-executed keeper of a build dir's lock (keep_build_lock)")
  kb.add_argument('fd', type=int)
  kb.add_argument('ack', type=int)
  kb.add_argument('survivors', type=json.loads)
  args = ap.parse_args(argv)
  if args.cmd == 'fat-read':
    return fat_read_main(args)
  if args.cmd == 'flush':
    return flush_main(args)
  if args.cmd == 'uf2-write':
    return uf2_write_main(args)
  if args.cmd == 'clear-pending':
    return clear_pending_main(args)
  if args.cmd == 'keep-held':
    fh = os.fdopen(args.fd, 'r+')
    os.write(args.ack, b'ok')
    os.close(args.ack)
    keep_held(fh)
  if args.cmd == 'keep-build':
    if any('receipt' in x for x in args.survivors):   # its runner checked the pin and loaded it before this exec
      with contextlib.suppress(Exception):   # else session_state loads it, or reads every session unreadable
        OPENOCD.append(run_report.load_agentrc(OPENOCD_ESP, 'agentrc_hil_openocd_esp'))
    os.write(args.ack, b'ok')
    os.close(args.ack)
    keep_build(args.survivors)
  for sig in TERM_SIGNALS:
    signal.signal(sig, on_signal)
  INTERRUPTS.clear()
  # absolute: a provider command file is written in it while the working directory is
  run_dir = ((getattr(args, 'run_root', None) or cb.BUILD_DIR / 'hil') /
             f'run-{time.strftime("%Y%m%d-%H%M%S")}-{os.getpid()}').resolve()
  result = {'pass': False, 'caveat': '', 'results': [], 'reportPath': str(run_dir / 'hil_report.json')}
  code, recovery, bat = 2, None, None
  try:
    run_dir.mkdir(parents=True)
    board = select_route(load_board(args.config, args.board), args.route, run=args.cmd == 'run')
    pin_records(args.build_record, getattr(args, 'update_record', None))
    facts = record_facts(args.build_record, board, run_dir)
    apply_layout(board, facts)
    helper = load_helper()
    provider()
    board['pendingMark'] = pending_mark(helper, board['lock'])
    clear_pending_mark(board['pendingMark'])   # refused while an earlier invocation's session, any run dir, is not ended
    if args.cmd == 'run':
      row, code = run_board(args, board, facts, helper, run_dir)
      result['results'].append(row)
      result['pass'] = code == 0 and row['pass']
    elif args.cmd == 'install':
      board = trial_reentry(board, args.try_reentry)
      manual_holder(helper, board['lock'], args.under_hold)
      files, fw = admit_record(args.build_record, board, facts, run_dir)
      users = probe_users(board)
      if users:
        raise Refused(f'probe {board["probe"]} is still in use by pids {users}; no session may overlap them')
      bat = BATTERIES[board['kind']](board, facts, run_dir)
      try:
        ev = bat.install(files)
        ev['dfu'] = bat.dfu_after_install(fw['version'])
      finally:
        settle_manual(result, bat, board, run_dir)
      result['results'].append({'board': board['name'], 'installed': fw, 'evidence': ev})
      result['pass'], code = True, 0
    else:
      files, fw = admit_record(args.build_record, board, facts, run_dir)
      rec = snapshot = None
      if args.try_reentry and (args.recover_holder is not None or args.recover_takeover):
        raise Refused('--try-reentry is for a restore under your own hold, not a recovery')
      if args.recover_holder is not None:
        if not args.report:
          raise Refused("--recover-holder needs --report, the failed run's report naming that holder")
        failed = failed_row(read_report(args.report), args.report, board, args.recover_holder)
        held = [failed['cleanup']]
        if board['kind'] == 'esp':
          snapshot = report_snapshot(failed, board['regions']['preserved'])
        recovery = recovery_lock(helper, board['lock'])
        rec = prove_cleanup_holder(helper, board['lock'], args.recover_holder)
        # the pending mark may be missing (markErrors); the report still names the sessions
        refuse_live(held[0].get('survivors', []) + rec.get('survivors', []), reviewed_receipts(board['pendingMark']),
                    "the failed run's")
      elif args.recover_takeover:
        body = read_report(args.report) if args.report else None
        recovery = recovery_lock(helper, board['lock'])
        rec = takeover_predecessor(helper, board['lock'], args.recover_takeover)
        reported = []
        if rec.get('role') == HOLDER_ROLE:   # its run's report names it: that run's evidence, snapshot included
          if not args.report:
            raise Refused("a dead cleanup holder's recovery needs --report, the failed run's report naming it")
          failed = failed_row(body, args.report, board, rec.get('pid'))
          reported = failed['cleanup'].get('survivors') or []
          if board['kind'] == 'esp':
            snapshot = report_snapshot(failed, board['regions']['preserved'])
        elif args.report:
          raise Refused('a battery that died holding the board printed no report: --report is for a dead cleanup holder')
        predecessor_evidence(rec, reported, reviewed_receipts(board['pendingMark']))
      else:
        board = trial_reentry(board, args.try_reentry)
        manual_holder(helper, board['lock'], args.under_hold)
      users = probe_users(board)
      if users:
        raise Refused(f'probe {board["probe"]} is still in use by pids {users}; recovery may not overlap them')
      bat = BATTERIES[board['kind']](board, facts, run_dir)
      try:
        if snapshot:
          bat.preserved = snapshot
        cleanup = bat.restore(files, fw['version'])
      finally:
        settle_manual(result, bat, board, run_dir)
      if result['survivors']:
        raise StepFail('restore left children that survived SIGKILL')
      if args.recover_holder is not None:
        os.kill(args.recover_holder, signal.SIGUSR1)
        wait_for(lambda: flock_free(helper.lock_path(board['lock'])), 10,
                 f'cleanup holder {args.recover_holder} releasing {board["name"]}')
        cleanup['recovered'] = {'holder': args.recover_holder, 'record': rec}
      elif args.recover_takeover:
        try:   # its records and journal gone and its flock dropped, or ReleaseRefused
          pid, _ = helper.release_token(args.recover_takeover)
        except helper.ReleaseRefused as e:
          raise StepFail(f'restored, but the takeover holder was not released: {e}')
        wait_for(lambda: flock_free(helper.lock_path(board['lock'])), 10,
                 f'takeover holder {pid} releasing {board["name"]}')
        cleanup['recovered'] = {'takeover': args.recover_takeover, 'holder': pid, 'record': rec}
      result['results'].append({'board': board['name'], 'firmware': fw, 'cleanup': cleanup})
      result['pass'], code = True, 0
  except Refused as e:
    result['error'] = str(e)
    if args.cmd == 'run' and not result['results']:
      result['results'].append({'board': args.board, 'ran': False, 'pass': False, 'locked': False,
                                'detail': str(e)})
    code = 2
  except (StepFail, Interrupted) as e:
    result['error'] = str(e)
    code = 4 if bat is not None and bat.touched else 1   # a failed restore keeps the hold
  RECORDS.clear()
  if recovery:
    recovery.close()
  if result.get('survivors'):   # a manual operation's survivor: keep your hold until it is gone
    result['pass'], code = False, 4
  if MARK_ERRORS:   # the board stays a blocker however the operation went: no later invocation sees its sessions
    result.update(markErrors=MARK_ERRORS[:], **{'pass': False})
    code = max(code, 4)
  result.update(exitCode=code, heldInProcess=bool(HELD_IN_PROCESS))
  publish_report(result, run_dir, args, sys.argv[1:] if argv is None else argv)
  print(json.dumps(result), flush=True)
  if HELD_IN_PROCESS:
    keep_held(HELD_IN_PROCESS[0])
  while release_ended_builds():   # no keeper started: keep them here
    time.sleep(KEEPER_POLL)
  return code


if __name__ == '__main__':
  sys.exit(main())
