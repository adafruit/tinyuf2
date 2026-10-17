#!/usr/bin/env python3
"""TinyUF2 HIL battery and the probe operations debug sessions share with it.

  hil_test.py run -b BOARD --build-record FILE CONFIG [--fail-at STEP] [--try-reentry METHOD]
  hil_test.py install -b BOARD --build-record FILE --under-hold REASON [--try-reentry METHOD] CONFIG
  hil_test.py restore -b BOARD --build-record FILE (--under-hold REASON [--try-reentry METHOD] | --recover-holder PID --report FILE) CONFIG

The last stdout line is JSON. Exit 0 every board passed and was cleaned up, 1 a board failed or did not
run (cleaned up or never touched), 2 refused before any hardware access, 4 cleanup failed (the board is
held when `cleanup.heldAfter`; not under HIL_NO_BOARD_LOCK), a manual operation left `survivors`, or a
`restore` failed after it began writing.
SKILL.md beside this script is the contract; this file is its mechanics.
"""
import argparse
import contextlib
import fcntl
import functools
import glob
import hashlib
import importlib.util
import json
import os
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'build' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True   # nothing the runner imports may write into a checkout it binds
import check_build as cb  # noqa: E402
import hil_esp as esp  # noqa: E402

# [floor, ceiling) the runner ever programs, per J-Link device, independent of roster and source:
# LPC55S69 PFR starts at 0x9DE00 and a bad CMPA write can lock the part (UM11126 Table 173, Table 1064);
# 0x9D800-0x9DDFF is reserved and undocumented. MIMXRT1062: FlexSPI XIP at 0x60000000 (IMXRT1060RM
# Table 3-1) holding the EVK's 8 MiB IS25WP064A (EVK hardware user's guide 2.7). MIMXRT1011: FlexSPI XIP at
# 0x60000000 (IMXRT1010RM Table 3-1) holding the Metro M7 1011's W25Q64JV (Metro M7 RT1011 SD revA schematic), 8 MiB.
# STM32F303VC: 256 KiB main flash at 0x08000000 (RM0316 Rev 10 Table 2); option bytes at 0x1FFFF800 stay outside.
# STM32F411VE: 512 KiB main flash at 0x08000000 (RM0383 Rev 4 Table 4); option bytes at 0x1FFFC000 stay outside.
# STM32H563ZI: 2 MiB main flash, banks at 0x08000000 and 0x08100000 (RM0481 Rev 5 Table 51); OTP at 0x08FFF000 and
# system memory at 0x0BF80000 stay outside, and its option bytes have no memory address (RM0481 7.4.1).
FLASH_LIMITS = {'LPC55S69_M33_0': (0, 0x9D800), 'MIMXRT1062xxx6A': (0x60000000, 0x60800000),
                'MIMXRT1011DAE5A': (0x60000000, 0x60800000), 'stm32f303vc': (0x08000000, 0x08040000),
                'stm32f411ve': (0x08000000, 0x08080000), 'stm32h563zi': (0x08000000, 0x08200000)}
STEPS = {'jlink': ('install', 'dfu', 'copy', 'app-ran', 'reenter')}
STEPS['stlink'] = STEPS['jlink']
STEPS['esptool'] = STEPS['jlink'] + ('recopy',)
REENTRY = {'jlink': ('retained-register',), 'stlink': ('retained-register',), 'esptool': ('dfu-detach',)}
REENTRY_METHODS = sorted({m for v in REENTRY.values() for m in v})
PROTECTED = {'hil_test.py', 'pool_check'}   # hil_lock.PROTECTED_REASONS, checked at load
# the board-lock helper is the submodule's at its pinned commit, never an operator's installed agentrc
AGENTRC = 'lib/agentrc'
LOCK_HELPER = ROOT / AGENTRC / 'skills' / 'hil' / 'scripts' / 'hil_lock.py'
HOLDER_ROLE = 'cleanup-holder'
SCB_VTOR, SCB_AIRCR = 0xE000ED08, 0xE000ED0C
AIRCR_SYSRESETREQ = 0x05FA0004
UF2_MAGIC = (0x0A324655, 0x9E5D5157, 0x0AB16F30)
UF2_FLAG_FAMILY = 0x2000
PROBE_TIMEOUT, USB_TIMEOUT, QUIET_TIME, KILL_WAIT, UDEV_TIMEOUT = 120, 20, 3, 5, 5
JLINK_RETRY_DELAY = 2
ESPTOOL_VERSION = '5.2.0'   # the CLI and API the esptool session helper is written and bench-checked against
ESP_BAUD, ESP_TIMEOUT = 921600, 300
ESP_SESSION = Path(__file__).resolve().parent / 'esp_session.py'
USB_DFU = Path(__file__).resolve().parent / 'usb_dfu.py'
NONCE_MAGIC, NONCE_BLOCK = b'TUF2NONC', 256   # apps/dfu_runtime/src/dfu_runtime.h
JLINK_IF, JLINK_SPEED = 'SWD', '4000'
STM32_PROGRAMMER_CLI = 'STM32_Programmer_CLI'
# what STM32CubeProgrammer prints at every connect to the roster's device: its Device ID and NVM size (bench, v2.23.0);
# 0x484 names the H56x/573 family only, so the size pins the part
STLINK_CHIPS = {'stm32h563zi': ('0x484', '2 MBytes')}
ANSI = re.compile(r'\x1b\[[0-9;]*m')
# each script operation's success line, by its first word (bench, v2.23.0)
STLINK_DONE = {'-halt': 'Core halted', '-run': 'Core run', '-rst': 'Software reset is performed',
               '-coreReg': 'XPSR     = 0x', '-r32': 'Reading 32-bit memory content', '-w32': '32-bit data download complete',
               '-u': 'Data read successfully', '#Delay': 'The system go to sleep for'}
CMAKE_RECORD_FILES = ('_bin/tinyuf2.bin', '_bin/apps/blinky.uf2')   # besides the flash target's inputs
JLINK_ERRORS = (r'Verify failed|Could not|Cannot connect|ERROR|ResetTarget failed|Failed to halt|CPU is not halted|'
                r'Failed to unlock|Can not attach')
UDEV_RULES = ('/etc/udev/rules.d', '/run/udev/rules.d')
# J-Link notes that are not failures, per device, each with the line that shows the operation completed
# (bench: every MIMXRT1062 reset with an invalid app vector, then the reset halts as usual; every MIMXRT1011 reset
# of a TinyUF2 image, which then boots; STM32F303VC: the connect that removes TinyUF2's write protection, SKILL.md
# Limits)
_RESET_VECTOR_NOTE = r'(?m)^Could not find valid reset vector\.\nTarget halted on flash header read\.$'
_F3_UNPROTECT_NOTE = (r'(?m)^Active write protection detected\.\nDevice will be unsecured now\.\nFailed to unlock device\.\n'
                      r'Can not attach to CPU\. Trying connect under reset\.$')
BENIGN = {'MIMXRT1062xxx6A': _RESET_VECTOR_NOTE, 'MIMXRT1011DAE5A': _RESET_VECTOR_NOTE, 'stm32f303vc': _F3_UNPROTECT_NOTE}
# runner sessions connect as the core: J-Link's stm32f411ve connect resets the chip to unprotect it (SKILL.md Limits)
SESSION_DEVICE = {'stm32f411ve': 'Cortex-M4'}
# ms the install's verify session waits before its halt after the flash target's unlock, empirical (SKILL.md Limits)
INSTALL_SETTLE_MS = {'stm32f411ve': 1000}


class Refused(Exception):
  """Exit 2: nothing on the board was touched."""


class StepFail(Exception):
  def __init__(self, msg, evidence=None):
    super().__init__(msg)
    self.evidence = evidence or {}


class NotEnumerated(StepFail):
  """The DFU device never appeared: the only failure after an install that re-entry may follow."""


class Interrupted(Exception):
  pass


# ------------------------------------------------------------------ roster and source facts

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
    raise Refused(f'{name}: flasher must be jlink or stlink with args exactly "-device NAME", or esptool with args '
                  f'exactly "--chip CHIP", with a string uid')
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
    raise Refused(f'{name}: no programming limits known for J-Link device {m.group(1)}')
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
          'if': JLINK_IF, 'speed': JLINK_SPEED, 'port': port,
          'reentry': t.get('reentry'), 'usbPower': power}


def has_define(path, name):
  return bool(re.search(rf'^\s*#\s*define\s+{name}\b', (ROOT / path).read_text(), re.M))


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


def cmake_var(path, name):
  """The value of the one `set(NAME value)` in a CMake file, ${TOP}/ read as the checkout; nothing else."""
  hits = re.findall(rf'\bset\s*\(\s*{name}\b([^)]*)\)', cb.code_lines(ROOT / path), re.I)
  if len(hits) != 1:
    raise Refused(f'{path}: expected one set({name} ...), found {len(hits)}')
  v = hits[0].strip().removeprefix('${TOP}/')
  if not v or re.search(r'[\s$"]', v):
    raise Refused(f'{path}: set({name} {hits[0].strip()}) is not one plain value')
  return v


STM32_DEVICE = {'stm32f3': ('STM32F3', r'STM32F3\d\dx[A-Z]'), 'stm32f4': ('STM32F4', r'STM32F4\d\dx[A-Z]'),
                'stm32h5': ('STM32H5', r'STM32H5\d\dxx')}


def port_sources(port, bdir):
  """(CMSIS device header, the bootloader's linker script, FLASH_BASE, where the BIN starts in flash, RAM origin, the
  link's --defsym values) of a port the HIL supports, read from the CMake files the HIL's build uses."""
  if port in STM32_DEVICE:
    ld = cmake_script(f'ports/{port}/CMakeLists.txt')
    series, form = STM32_DEVICE[port]
    mcus = set(re.findall(rf'\b{form}\b', cb.code_lines(ROOT / bdir / 'board.cmake')))
    if len(mcus) != 1:
      raise Refused(f'{bdir}/board.cmake: expected one {series} device define, found {sorted(mcus)}')
    header = f'{cmake_var(f"ports/{port}/family.cmake", "ST_CMSIS")}/Include/{mcus.pop().lower()}.h'
    syms = defsyms(port, bdir, ld) if port == 'stm32h5' else {}
    flash_base, ram = ld_memory(ld, 'FLASH', syms)[0], ld_memory(ld, 'RAM', syms)[0]
    return header, ld, flash_base, flash_base, ram, syms
  if port != 'mimxrt10xx':
    raise Refused(f'ports/{port}: the HIL runner has no source facts for this port')
  sdk = cmake_var(f'ports/{port}/family.cmake', 'SDK_DIR')
  mcu = cmake_var(f'{bdir}/board.cmake', 'MCU_VARIANT')
  ld = f'ports/{port}/linker/{mcu}_ram.ld'   # where family.cmake takes FLASH_BASE and FCFB_ORIGIN from
  vals = {}
  for name in ('_flash_base', '_fcfb_origin'):
    m = re.search(rf'^\s*{name}\s*=\s*(0x[0-9a-fA-F]+)\s*;', (ROOT / ld).read_text(), re.M)
    if not m:
      raise Refused(f'{ld}: no {name}')
    vals[name] = int(m.group(1), 16)
  flash_base = vals['_flash_base']
  # family.cmake FLASH_FCFB_ADDR: the BIN starts at the FCB, 0x400 into flash on RT1010 (IMXRT1010RM Table 9-8)
  bin_base = flash_base + (vals['_fcfb_origin'] & 0xFFF)
  return (f'{sdk}/devices/{mcu}/{mcu}.h', ld, flash_base, bin_base,
          ram_origin(f'{sdk}/devices/{mcu}/gcc/{mcu}xxxxx_flexspi_nor.ld'), {})


# the stm32h5 link's --defsym symbols, each from the board's set() of this variable
DEFSYMS = {'__flash_boot_size': 'LD_FLASH_BOOT_SIZE', '__ram_size': 'LD_RAM_SIZE'}


def defsyms(port, bdir, ld):
  """The values family.cmake passes the linker for DEFSYMS, from the board.cmake's one set() each, in the exact
  forms the port uses: one `-Wl,--defsym=SYM=${VAR}` each, the script's one `SYM = DEFINED(SYM) ? SYM : <default>;`,
  and family.cmake setting a variable only for Debug builds, which a HIL record (MinSizeRel) is not."""
  fam = cb.code_lines(ROOT / f'ports/{port}/family.cmake')
  text, syms = ld_text(ld), {}
  for sym, var in DEFSYMS.items():
    sets = re.findall(rf'\bset\s*\(\s*{var}\b', fam, re.I)
    debug = re.findall(rf'if\s*\(\s*CMAKE_BUILD_TYPE\s+STREQUAL\s+"Debug"\s*\)\s*set\s*\(\s*{var}\s+\w+\s*\)\s*endif\s*\(\s*\)',
                       fam, re.I)
    if fam.count('--defsym=') != len(DEFSYMS) or fam.count(f'-Wl,--defsym={sym}=${{{var}}}') != 1 or \
       len(sets) != len(debug) or \
       len(re.findall(rf'(?<![\w.]){sym}\s*(<<|>>|[-+*/|&]?)=(?!=)', text)) != 1 or \
       len(re.findall(rf'(?<![\w.]){sym}\s*=\s*DEFINED\(\s*{sym}\s*\)\s*\?\s*{sym}\s*:\s*\w+\s*;', text)) != 1:
      raise Refused(f'ports/{port}: {sym} does not reach {ld} as -Wl,--defsym={sym}=${{{var}}} over a DEFINED() default')
    syms[sym] = ld_expr(cmake_var(f'{bdir}/board.cmake', var), f'{bdir}/board.cmake {var}')
  return syms


def cmake_script(path):
  """The one linker script a port's CMakeLists.txt passes with --script=${CMAKE_CURRENT_LIST_DIR}/..."""
  hits = re.findall(r'--script=\$\{CMAKE_CURRENT_LIST_DIR\}/([\w./-]+\.ld)(?=["\s)])', cb.code_lines(ROOT / path))
  if len(hits) != 1:
    raise Refused(f'{path}: expected one --script=${{CMAKE_CURRENT_LIST_DIR}}/<script>.ld, found {hits}')
  return f'{Path(path).parent}/{hits[0]}'


def ld_text(ld, syms=None):
  """The script without comments; with `syms`, each one's DEFINED() default dropped and its uses replaced by its
  value (defsyms checked the form)."""
  text = re.sub(r'/\*.*?\*/', ' ', (ROOT / ld).read_text(), flags=re.S)
  for sym, v in (syms or {}).items():
    text = re.sub(rf'(?<![\w.]){sym}\s*=\s*DEFINED\([^;]*;', ' ', text)
    text = re.sub(rf'(?<![\w.]){sym}(?!\w)', hex(v), text)
  return text


def ld_expr(expr, what):
  """A sum or difference of literals, each with an optional K or M suffix, e.g. 40K - 4; nothing else."""
  term = r'(0x[0-9a-fA-F]+|\d+)([KM]?)'
  if not re.fullmatch(rf'\s*{term}(\s*[+-]\s*{term})*\s*', expr):
    raise Refused(f'{what}: {expr!r} is not a sum of literals')
  v = 0
  for sign, n, unit in re.findall(rf'([+-]?)\s*{term}', expr):
    v += (-1 if sign == '-' else 1) * int(n, 0) * {'': 1, 'K': 1 << 10, 'M': 1 << 20}[unit]
  return v


def ld_memory(ld, region, syms=None):
  """(ORIGIN, LENGTH) of a MEMORY region."""
  hits = re.findall(rf'^\s*{region}\s*\(\w+\)\s*:\s*ORIGIN\s*=\s*([^,]+),\s*LENGTH\s*=\s*([^\n]+?)\s*$', ld_text(ld, syms),
                    re.M)
  if len(hits) != 1:
    raise Refused(f'{ld}: expected one {region} memory region, found {len(hits)}')
  return ld_expr(hits[0][0], f'{ld} {region} ORIGIN'), ld_expr(hits[0][1], f'{ld} {region} LENGTH')


def ld_symbol(ld, name, depth=0, syms=None):
  """A symbol the script assigns once: a literal sum, ORIGIN(R) + LENGTH(R), or another such symbol."""
  hits = re.findall(rf'(?<![\w.]){name}\s*(<<|>>|[-+*/|&]?)=(?!=)\s*([^;]+);', ld_text(ld, syms))
  if len(hits) != 1 or hits[0][0]:
    raise Refused(f'{ld}: expected one plain {name} = ...;, found {[op + "=" for op, _ in hits]}')
  rhs = hits[0][1].strip()
  if re.fullmatch(r'[A-Za-z_]\w*', rhs) and depth < 2:
    return ld_symbol(ld, rhs, depth + 1, syms)
  m = re.fullmatch(r'ORIGIN\((\w+)\)\s*\+\s*LENGTH\(\1\)', rhs)
  if m:
    return sum(ld_memory(ld, m.group(1), syms))
  return ld_expr(rhs, f'{ld} {name}')


def vector_count(header):
  """NUMBER_OF_INT_VECTORS, else the 16 system vectors plus IRQ 0 to the highest IRQn_Type value."""
  if has_define(header, 'NUMBER_OF_INT_VECTORS'):
    return num(define(header, 'NUMBER_OF_INT_VECTORS'), 'NUMBER_OF_INT_VECTORS')
  text = re.sub(r'/\*.*?\*/|//[^\n]*', ' ', (ROOT / header).read_text(), flags=re.S)
  enums = re.findall(r'typedef\s+enum\s*\{([^}]*)\}\s*IRQn_Type\s*;', text)
  items = [i.strip() for i in enums[0].split(',') if i.strip()] if len(enums) == 1 else []
  vals = [re.fullmatch(r'\w+\s*=\s*(-?\d+)', i) for i in items]
  irqs = [int(v.group(1)) for v in vals] if items and all(vals) else []
  if not irqs or max(irqs) < 0:
    raise Refused(f'{header}: neither NUMBER_OF_INT_VECTORS nor one IRQn_Type enum of NAME = decimal entries')
  return 16 + max(irqs) + 1


def source_facts(board):
  """What the candidate's source says about this board."""
  port = board['port']
  bdir = f'ports/{port}/boards/{board["name"]}'
  if not (ROOT / bdir).is_dir():
    raise Refused(f'{bdir} does not exist')
  if board.get('flasher') == 'esptool':
    return esp_source_facts(board, bdir)
  header, ld, flash_base, bin_base, ram, syms = port_sources(port, bdir)
  if has_define(f'{bdir}/board.h', 'BOARD_FLASH_APP_START'):
    raise Refused(f'{bdir}/board.h overrides BOARD_FLASH_APP_START; the runner reads the port default only')
  size = define(f'{bdir}/board.h', 'BOARD_FLASH_SIZE')
  floor, ceiling = FLASH_LIMITS.get(board.get('device'), (0, 0))
  facts = {
    'flashBase': flash_base,
    'binBase': bin_base,
    'appStart': app_start(port, flash_base, syms),
    # FLASH_SIZE is CMSIS's read of the chip's size register: the roster device's flash, which INFO_UF2.TXT reports
    'flashSize': ceiling - floor if size == 'FLASH_SIZE' and ceiling else product(size, 'BOARD_FLASH_SIZE'),
    'vid': num(define(f'{bdir}/board.h', 'USB_VID'), 'USB_VID'),
    'pid': num(define(f'{bdir}/board.h', 'USB_PID'), 'USB_PID'),
    'boardId': define(f'{bdir}/board.h', 'UF2_BOARD_ID').strip('"'),
    'family': int(cmake_var(f'ports/{port}/family.cmake', 'UF2_FAMILY_ID'), 16),
    'vectors': vector_count(header),
    'ram': ram,
    'dblTapDelayMs': num(define('src/board_api.h', 'TINYUF2_DBL_TAP_DELAY'), 'TINYUF2_DBL_TAP_DELAY'),
  }
  if has_define(f'ports/{port}/boards.h', 'TINYUF2_DBL_TAP_REG'):
    reg = define(f'ports/{port}/boards.h', 'TINYUF2_DBL_TAP_REG')
    m = re.fullmatch(r'(\w+)->(\w+)\[(\d+)\]', reg)
    if not m:
      raise Refused(f'TINYUF2_DBL_TAP_REG {reg!r} is not PERIPH->ARRAY[N]')
    base, offset, step = register_layout(header, m.group(1), m.group(2))
    facts['dblTapReg'] = base + offset + step * int(m.group(3))
  else:   # board_api.h's default: the word the bootloader's linker script places
    facts['dblTapReg'] = ld_symbol(ld, '_board_dfu_dbl_tap', syms=syms)
  facts['dblTapMagic'] = 0xf01669ef   # board_api.h DBL_TAP_MAGIC at TINYUF2_DBL_TAP_REG_SIZE 32
  if 'TINYUF2_DBL_TAP_REG_SIZE' in (ROOT / f'ports/{port}/boards.h').read_text():
    raise Refused(f'ports/{port} overrides TINYUF2_DBL_TAP_REG_SIZE: the magic would need its shift')
  return facts


def app_start(port, flash_base, syms):
  """BOARD_FLASH_APP_START: a literal or FLASH_BASE + literal, or the stm32h5 form, the flash base plus the link's
  __flash_boot_size."""
  expr = define(f'ports/{port}/boards.h', 'BOARD_FLASH_APP_START')
  if not re.fullmatch(r'\(\s*BOARD_FLASH_ADDR_ZERO\s*\+\s*\(uint32_t\)\s*__flash_boot_size\s*\)', expr):
    return flash_addr(expr, flash_base, 'BOARD_FLASH_APP_START')
  zero = num(define(f'ports/{port}/boards.h', 'BOARD_FLASH_ADDR_ZERO'), 'BOARD_FLASH_ADDR_ZERO')
  if '__flash_boot_size' not in syms or zero != flash_base:
    raise Refused(f'ports/{port}: BOARD_FLASH_APP_START {expr!r} needs the link\'s __flash_boot_size and '
                  f'BOARD_FLASH_ADDR_ZERO at the flash base')
  return zero + syms['__flash_boot_size']


def esp_source_facts(board, bdir):
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


def apply_layout(board, facts):
  """The install and app spans, from the candidate's source: the bootloader from the flash base up to the app
  start, the app from there to the end of the board's flash, all inside the device's programming limits."""
  if board.get('flasher') == 'esptool':
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
CONTAINERS = []   # docker containers a flash started, by name: outside every child's session
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


def spawn(cmd, log, timeout, cwd=None):
  """Run a child in its own process group with a bound; a child that survives SIGKILL (D state on a
  stuck USB device) is left in CHILDREN for cleanup to see. Children spawned during cleanup inherit its
  blocked SIGTERM and SIGINT, so only SIGKILL (reap) may be relied on to end them."""
  with open(log, 'a') as f:
    f.write('$ ' + ' '.join(map(str, cmd)) + '\n')
    f.flush()
    with registering():
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
  return left


def proc_start(pid):
  """The start time of a live `pid` in clock ticks (proc(5) stat field 22), which tells a reused pid apart."""
  st = proc_stat(pid)
  return int(st[19]) if st and len(st) > 19 else None


def container_present(name):
  r = subprocess.run(['docker', 'ps', '-aq', '-f', f'name=^{name}$'], capture_output=True, text=True, timeout=30)
  if r.returncode:
    raise StepFail(f'docker ps failed: {r.stderr.strip()[-200:]}')
  return bool(r.stdout.strip())


def container_gone(name):
  """`docker rm -f` (a running, created or exited container alike), then whether docker no longer lists it; a
  docker error is not an answer, so it counts as still there."""
  try:
    subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
    end = time.monotonic() + 2 * KILL_WAIT
    while (left := container_present(name)) and time.monotonic() < end:
      time.sleep(0.2)
    return not left
  except (StepFail, OSError, subprocess.SubprocessError):
    return False


def stuck_children():
  """Processes of the children's sessions, and containers a flash created, that survived SIGKILL, identified so
  a later recovery can tell they are still alive. The launchers go first, so no `docker` child can create or start
  a container after its name is checked."""
  stuck = []
  for p in list(CHILDREN):
    for pid in reap(p):
      try:
        cmd = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:3]
      except OSError:
        cmd = []
      stuck.append({'pid': pid, 'start': proc_start(pid), 'cmd': [c.decode(errors='replace') for c in cmd]})
  for name in list(CONTAINERS):
    if container_gone(name):
      CONTAINERS.remove(name)
    else:
      stuck.append({'container': name})
  return stuck


def still_alive(survivors):
  return [s for s in survivors if (not container_gone(s['container']) if 'container' in s else
                                   s.get('start') is not None and proc_start(s['pid']) == s['start'])]


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


def judge_jlink_target(code, out, board, hex_path):
  """The tinyuf2-jlink transcript, through CMake and Ninja: JLinkExe can exit 0 with every command FAILED (no probe
  with the serial), so success is read from the transcript: this HEX downloaded, programmed or already matching,
  then O.K. and the script completed, with no failure line anywhere."""
  judged = re.sub(BENIGN[board['device']], '', out) if board['device'] in BENIGN else out
  m = re.search(rf'^Downloading file \[{re.escape(str(hex_path))}\]\.\.\.$(?:\n.*)*?\nJ-Link: Flash download: Bank \d+ @ '
                r'0x[0-9A-F]+: (Skipped\. Contents already match|\d+ ranges? affected \(\d+ bytes\))$(?:\n.*)*?\nO\.K\.$',
                judged, re.M)
  if code or not m or 'Script processing completed.' not in judged or re.search(JLINK_ERRORS + '|FAILED', judged):
    raise StepFail(f'tinyuf2-jlink failed (exit {code})', jlink_failure(code, out, board['probe']))
  return {'flashDownload': m[1]}


def judge_esp_target(code, out, segments):
  """ESP-IDF's flash target, through CMake and Ninja in CI's image: esptool's write of every segment at its offset,
  each hash-verified, then the hard reset (bench transcript, esptool v5.3.1 in espressif/idf:v6.1)."""
  wrote = sorted(int(a, 16) for a in re.findall(r'^Wrote \d+ bytes \(\d+ compressed\) at 0x([0-9a-f]{8}) in ', out, re.M))
  if code or wrote != sorted(off for off, _ in segments) or out.count('Hash of data verified.') != len(segments) or \
     'Hard resetting via RTS pin' not in out:
    raise StepFail(f'the flash target failed (exit {code})', {'tail': out.strip().splitlines()[-5:]})
  return {'wrote': [hex(a) for a in wrote]}


class Probe:
  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log
    self.retried = []

  def run(self, commands, judge=True):
    """One JLinkExe session. judge=False is for a last `w4` that resets the target, which may drop the
    connection mid-transaction: only its issue on a connected target is judged (J-Link's "Writing VALUE ->
    ADDR" with no failure before it), and the caller's observation is the evidence."""
    script = self.dir / f'jlink-{time.monotonic_ns()}.jlink'
    script.write_text('\n'.join(list(commands) + ['exit']) + '\n')
    device = SESSION_DEVICE.get(self.b['device'], self.b['device'])
    cmd = ['JLinkExe', '-USB', self.b['probe'], '-device', device, '-if', self.b['if'], '-speed',
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
    if code < 0 or judge and (code or re.search(JLINK_ERRORS, judged)):
      raise StepFail(f'JLinkExe failed (exit {code})', jlink_failure(code, out, self.b['probe']))
    if not judge and commands[-1].startswith('w4 '):
      _, addr, value = commands[-1].split()
      head, issued, _ = judged.partition(f'Writing {value} -> {addr}')
      if not issued or re.search(JLINK_ERRORS, head):
        raise StepFail(f'the reset write was not issued on a connected target (exit {code})',
                       jlink_failure(code, out, self.b['probe']))
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
  """The tinyuf2-stlink transcript, through CMake and Ninja (bench, STM32CubeProgrammer v2.23.0): the roster's chip,
  the HEX downloaded and the start command's success, with no error line; the binding fixed the command."""
  out = ANSI.sub('', out)
  m = re.search(r'^Opening and parsing file: tinyuf2\.hex$(?:\n.*)*?\nErasing internal memory sectors? \[?([\d ]+)\]?$'
                r'(?:\n.*)*?\nFile download complete$(?:\n.*)*?\nStart operation achieved successfully$', out, re.M)
  if code or not m or not chip_reported(out, board) or re.search(r'^Error', out, re.M):
    raise StepFail(f'tinyuf2-stlink failed (exit {code})', stlink_failure(out))
  return {'flashDownload': 'File download complete', 'erasedSectors': m[1].split()}


class StlinkProbe:
  """One STM32CubeProgrammer CLI connection per session: a script that connects to the roster's ST-LINK without a
  reset (HOTPLUG), then runs `ops` in order. The CLI stops at the first failed operation and exits 1 (bench, v2.23.0);
  success is read from the transcript too: the roster's chip, every operation echoed in order with its success line,
  no error line, the script's end."""

  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log
    self.retried = []   # the report's jlinkRetried: a CLI session is never retried

  def run(self, ops):
    """Each operation's output, in order."""
    script = self.dir / f'stlink-{time.monotonic_ns()}.prg'
    lines = [f'-c port=SWD sn={self.b["probe"]} mode=HOTPLUG', *ops]
    script.write_text('\n'.join(lines) + '\n')
    code, out = spawn([STM32_PROGRAMMER_CLI, '-script', script], self.log, PROBE_TIMEOUT)
    out = ANSI.sub('', out)
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
  """The tty of the USB-UART bridge with this serial: exactly one, never a guessed /dev/ttyUSBn."""
  hits = sorted(glob.glob(f'/dev/serial/by-id/*_{glob.escape(uid)}-if*'))
  if len(hits) != 1:
    raise StepFail(f'{len(hits)} serial ports for bridge {uid}: {hits}')
  return os.path.realpath(hits[0])


def child_json(cmd, log, timeout, what):
  """The JSON last line of a helper child (esp_session.py, usb_dfu.py, fat-read); a missing line, a non-zero
  exit or an `ok` other than true fails the step with the helper's `reason` (else `error`) and the output tail."""
  code, out = spawn(cmd, log, timeout)
  tail = out.strip().splitlines()[-5:]
  try:
    res = json.loads(tail[-1])
  except (IndexError, ValueError):
    res = None
  if not isinstance(res, dict):
    raise StepFail(f'{what} ended without its JSON (exit {code})', {'tail': tail})
  if code or res.get('ok') is not True:
    raise StepFail(f'{what}: {res.get("reason") or res.get("error")}', {'tail': tail, 'error': res.get('error')})
  return res


class Esptool:
  """esptool sessions on one board, each one connection in its own child (esp_session.py)."""
  def __init__(self, board, workdir, log):
    self.b, self.dir, self.log = board, workdir, log

  def run(self, ops, after):
    spec = self.dir / f'esp-{time.monotonic_ns()}.json'
    spec.write_text(json.dumps(ops))
    return child_json([sys.executable, '-B', ESP_SESSION, '--port', esp_port(self.b['probe']), '--chip', self.b['device'],
                       '--baud', str(ESP_BAUD), '--after', after, spec], self.log, ESP_TIMEOUT, 'esptool session')['results']


def preserved_ops(regions):
  return [{'op': 'md5', 'addr': lo, 'size': hi - lo} for lo, hi in regions.values()]


def preserved_md5(regions, results):
  md5 = [r['md5'] for r in results if r['op'] == 'md5']
  return dict(zip(regions, md5))


def check_preserved(before, after, by):
  if before != after:
    raise StepFail(f'a preserved region changed by the end of the {by}', {'before': before, 'after': after})


def esp_verify(tool, board, segments, workdir, snapshot):
  """After the flash target: every segment read back byte for byte in one connection of the runner's, then one
  reset. The preserved regions' MD5s must equal `snapshot`, taken before the install."""
  reads = [(off, path, workdir / f'readback-{off:x}.bin') for off, path in segments]
  keep = board['regions']['preserved']
  ops = [{'op': 'read', 'addr': off, 'size': path.stat().st_size, 'file': str(rb)} for off, path, rb in reads] + \
        preserved_ops(keep)
  after = preserved_md5(keep, tool.run(ops, 'hard-reset'))
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
  """The roster's usbPower (SKILL.md Roster): while DFU is awaited, the hub port's sysfs `disable` is written 1 then 0
  once the port sat in state "default" for STUCK s of this wait, at most once per GAP s."""
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
      if not done:   # an interruption or failure past the off write must not leave the port without VBUS
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
    raise StepFail(f'{dev} has no UDISKS_IGNORE=1: desktop automount could race the raw I/O (SKILL.md, Commissioning)')
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
    self.dev, self.fd = dev, os.open(dev, os.O_RDONLY)
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


def fat_read(dev, name, length, log, offset=0):
  """{'entries': {...}, 'data': bytes} of `name` on `dev`, read by a bounded child process."""
  try:
    r = child_json([sys.executable, '-B', __file__, 'fat-read', '--dev', dev, '--file', name, '--length', str(length),
                    '--offset', str(offset)], log, USB_TIMEOUT, name)
  except StepFail as e:
    e.evidence['dev'] = dev
    raise
  return {'entries': r['entries'], 'data': bytes.fromhex(r['data']), 'size': r['size']}


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
  """Refuse unless lib/agentrc is checked out, clean, at the commit HEAD pins."""
  init = f'git submodule update --init {AGENTRC}'
  if not LOCK_HELPER.is_file() or not cb.own_checkout(AGENTRC):
    raise Refused(f'lock helper {LOCK_HELPER} is not checked out: {init}')
  try:
    want = cb.git('rev-parse', f'HEAD:{AGENTRC}').strip()
    have = cb.git_in(AGENTRC, 'rev-parse', 'HEAD').strip()
  except cb.Fail as e:
    raise Refused(f'cannot read the {AGENTRC} pin: {e}')
  if have != want:
    # submodule update checks out the index's gitlink, so a staged pin change would defeat the hint
    try:
      staged = cb.git('rev-parse', f':{AGENTRC}').strip()
    except cb.Fail as e:
      raise Refused(f'cannot read the staged {AGENTRC} pin: {e}')
    if staged != want:
      raise Refused(f'{AGENTRC} is at {have}; HEAD pins {want} but {staged} is staged: commit or unstage that '
                    f'{AGENTRC} pin change')
    raise Refused(f'{AGENTRC} is at {have}; HEAD pins {want}: {init}')
  try:
    dirty = cb.dirty_inputs([AGENTRC])
  except cb.Fail as e:
    raise Refused(f'cannot read the {AGENTRC} checkout state: {e}')
  if dirty:
    raise Refused(f'{AGENTRC} checkout is dirty at the pinned {want}: discard its local changes')


def load_helper():
  check_lock_pin()
  path = LOCK_HELPER
  spec = importlib.util.spec_from_file_location('hil_lock', path)
  if not spec or not path.is_file():
    raise Refused(f'lock helper {path} not found')
  mod = importlib.util.module_from_spec(spec)
  try:
    spec.loader.exec_module(mod)
  except Exception as e:
    raise Refused(f'lock helper {path} failed to load: {e}')
  lu = getattr(mod, 'LockUnavailable', None)
  if set(getattr(mod, 'PROTECTED_REASONS', ())) != PROTECTED or getattr(mod, 'CI_REASON', None) != 'hil_test.py' or \
     getattr(mod, 'CLEANUP_ROLE', None) != HOLDER_ROLE or not (isinstance(lu, type) and issubclass(lu, RuntimeError)):
    raise Refused(f'lock helper {path}: protected reasons are not {sorted(PROTECTED)}, its cleanup role is not '
                  f'{HOLDER_ROLE!r} or it has no LockUnavailable; recheck this contract')
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


def manual_holder(helper, board, reason):
  if reason in PROTECTED:
    raise Refused(f'{reason!r} is a protected holder; --under-hold takes the reason of your own manual hold')
  rec = helper.read_record(board)
  pid = rec.get('pid') if isinstance(rec, dict) else None
  if not isinstance(pid, int):
    raise Refused(f'{board}: no lock record; hold it first with {helper.__file__} hold {board} --reason ...')
  prove_hold(helper, board, pid, reason=reason)


def probe_users(board):
  """Processes using this board's probe: for J-Link one opened by serial (a JLinkExe or GDB server from an
  earlier session), for ST-LINK any STM32CubeProgrammer CLI (its script names the probe, not its command line), for
  esptool any process holding the bridge's tty open."""
  if board['flasher'] == 'esptool':
    return tty_users(esp_port(board['probe']))
  probe, users = board['probe'].encode(), []
  for d in Path('/proc').iterdir():
    try:
      cmd = (d / 'cmdline').read_bytes().split(b'\0')
    except OSError:
      continue
    if not d.name.isdigit() or int(d.name) == os.getpid():
      continue
    if board['flasher'] == 'stlink' and Path(cmd[0].decode(errors='replace')).name == STM32_PROGRAMMER_CLI or \
       board['flasher'] == 'jlink' and any(b'JLink' in c for c in cmd[:1]) and any(probe in c for c in cmd):
      users.append(int(d.name))
  return users


def tty_users(dev):
  users = []
  for d in Path('/proc').iterdir():
    if not d.name.isdigit() or int(d.name) == os.getpid():
      continue
    try:
      fds = list((d / 'fd').iterdir())
    except OSError:
      continue
    if any(readlink(fd) == dev for fd in fds):
      users.append(int(d.name))
  return users


def readlink(fd):
  """A /proc fd's target, or None once it has closed: one closing fd must not hide the process's others."""
  try:
    return os.readlink(fd)
  except OSError:
    return None


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
  are ignored: an operator's timeout kill must not free a board that was never cleaned up."""
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
      for sig in (signal.SIGTERM, signal.SIGINT):   # before the ack: the caller may be killed right after it
        signal.signal(sig, signal.SIG_IGN)
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

def verify_record(record_path, board, facts, workdir):
  try:
    rec = json.loads(Path(record_path).read_text())
  except (OSError, ValueError) as e:
    raise Refused(f'cannot read build record {record_path}: {e}')
  rows = [r for r in rec.get('boards', []) if r.get('board') == board['name']]
  if not rec.get('pass') or len(rows) != 1 or rows[0].get('status') != 'ok' or rows[0].get('removed'):
    raise Refused(f'{record_path}: not a passing --shared build of {board["name"]}')
  row, info = rows[0], rec.get('input', {})
  want = 'idf' if board.get('flasher') == 'esptool' else 'cmake'
  if row.get('backend') != want:
    raise Refused(f'{record_path}: a {row.get("backend")} build; the HIL takes {want} builds only for this board '
                  f'(check_build.py --board {board["name"]}{" --backend cmake" if want == "cmake" else ""} --shared '
                  f'--hil-config <roster>)')
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
  root = cb.ROOT / row['buildDir']
  flash = admit_flash(record_path, rec, row, root, board)
  # the runner reads its own copies of the BIN, segments and blinky: the build dir's lock covers the flash target
  # only, and a rebuild may replace the dir after it
  copy = workdir / 'record'
  if want == 'idf':
    bin_rel = 'tinyuf2.bin'
    copied(root, (*esp.RECORD_FILES, *flash['sha256']), row, copy)
    files = esp_record(record_path, copy, board, facts)
  else:
    bin_rel, blinky_rel = CMAKE_RECORD_FILES
    copies = copied(root, CMAKE_RECORD_FILES, row, copy)
    files = dict(check_blinky(copies[blinky_rel], board['app'], facts), bin=copies[bin_rel], hex=root / 'tinyuf2.hex')
  files['flash'] = flash
  return files, {'path': str(root / bin_rel), 'sha256': sha256(files['bin']), 'buildRecord': str(record_path),
                 'defines': rec.get('defines', []), 'version': embedded_version(files['bin'])}


def admit_flash(record_path, rec, row, root, board):
  """The record's flash target, bound by check_build --hil-config to this roster flasher, with every file it reads
  hash-checked; the install runs that target, under the build dir's lock."""
  fl = row.get('flash') or {}
  target, inputs = cb.FLASH[board['flasher']]
  want = {'name': board['flasher'], 'uid': board['probe'], 'device': board['device']}
  if (fl.get('flasher'), fl.get('target'), fl.get('inputs')) != (want, target, list(inputs)):
    raise Refused(f'{record_path}: its flash target is not bound to this roster flasher {want} (rebuild it with '
                  f'check_build.py --board {board["name"]} ... --shared --hil-config <roster>)')
  idf = rec.get('idf') or {}
  return {'root': root, 'binding': fl, 'sha256': recorded(root, inputs, row), 'image': idf.get('image'),
          'ninja': functools.partial(cb.ninja_in, row['backend'], idf.get('mode'), idf.get('image'))}


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
  return {'segments': segments, 'bin': root / 'tinyuf2.bin', **esp_app_chunks(root / esp.APP_UF2, facts, board),
          **check_blinky(root / esp.BLINKY_UF2, (0, board['app'][1] - board['app'][0]), facts)}


def sha256(p):
  try:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
  except OSError:
    return None


def check_bootloader_bin(bin_path, board, facts, what):
  """The BIN from its flash address (`binBase`) inside `install`, within the device's flash limits, and this
  board's (its UF2_BOARD_ID)."""
  start, size = facts['binBase'], Path(bin_path).stat().st_size
  check_ranges({start: 0, start + size - 1: 0}, [board['install']], FLASH_LIMITS[board['device']], what)
  if facts['boardId'].encode() not in Path(bin_path).read_bytes():
    raise Refused(f'{what}: {bin_path} does not carry board id {facts["boardId"]!r}; not this board\'s bootloader')


class Battery:
  def __init__(self, board, facts, workdir, fail_at=None, commissioning=False):
    self.b, self.f, self.dir, self.fail_at, self.commissioning = board, facts, workdir, fail_at, commissioning
    self.log = workdir / 'hil.log'
    self.probe = Probe(board, workdir, self.log)
    self.power = PortPower(board.get('usbPower'), self.log)
    self.steps, self.usb_path, self.touched, self.at = [], None, False, 'setup'
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

  def flash_target(self, flash, cmd, timeout, judge):
    """The record's flash target, under its build dir's lock: the inputs still hash as recorded and a dry run shows
    the target runs nothing but its flasher (cb.flash_ready); after it, the inputs are hashed again. Touched from the
    target's start; only a transcript recognised as ending before any target connect leaves the board as it was."""
    root, fl = flash['root'], flash['binding']
    with contextlib.ExitStack() as held:
      try:
        held.enter_context(cb.build_lock(root, wait=False))
      except BlockingIOError:
        raise StepFail(f'{root.name} is in use by a build or another flash; nothing was flashed')
      self.check_inputs(flash, 'before the flash')
      try:
        cb.flash_ready(root, fl, flash['ninja'])
      except cb.Fail as e:
        raise StepFail(str(e))
      was, self.touched = self.touched, True
      code, out = spawn(cmd, self.log, timeout)
      try:
        ev = judge(code, out)
      except StepFail as e:
        if e.evidence.get('beforeTarget'):
          self.touched = was
        raise
      self.check_inputs(flash, 'while flashing', ev)
    return ev

  @staticmethod
  def check_inputs(flash, when, ev=None):
    changed = [rel for rel, digest in flash['sha256'].items() if sha256(flash['root'] / rel) != digest]
    if changed:
      raise StepFail(f'flash inputs changed {when}: {changed}', ev or {})

  def dfu_after_install(self, version):
    """DFU after an install: on the RT boards J-Link's download erased the bootloader's whole 64 KiB block on the
    bench, the app start with it (SKILL.md Limits), so DFU comes up; should enumeration time out instead, as when a
    valid app boots (the F303's install keeps the app; there the verify session's reset may land in TinyUF2's
    double-tap window instead, SKILL.md Limits), the board's commissioned retained-register re-entry brings DFU up.
    Any other failure fails as it is."""
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
    return self.probe.run([f'w4 {SCB_AIRCR:08X} {AIRCR_SYSRESETREQ:08X}'], judge=False)

  def dfu(self, version):
    f = self.f
    self.power.start()
    path = wait_for(lambda: self.power.poll() or usb_device(f['vid'], f['pid'], self.b['uid']), USB_TIMEOUT,
                    f'{f["vid"]:04x}:{f["pid"]:04x} serial {self.b["uid"]}', NotEnumerated)
    if self.usb_path and path != self.usb_path:
      raise StepFail('came back on another USB port', {'usb': path, 'expected': self.usb_path})
    self.usb_path = path
    dev = wait_for(lambda: block_device(path), USB_TIMEOUT, f'the block device of USB {path}')
    udev_wait = check_exclusive(dev)
    info = fat_read(dev, 'INFO_UF2.TXT', 512, self.log)
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

  def copy(self, uf2, blocks, nonce=None):
    dev = block_device(self.usb_path)
    code, out = spawn(['mcopy', '-o', '-i', dev, uf2, '::APP.UF2'], self.log, 60)
    if code:
      raise StepFail('mcopy failed', {'tail': out.strip().splitlines()[-5:]})
    spawn(['sync'], self.log, 60)
    f = self.f
    wait_for(lambda: usb_device(f['vid'], f['pid'], self.b['uid']) is None, USB_TIMEOUT, 'the DFU device leaving')
    return {'blocks': blocks, **({'nonce': nonce.hex()} if nonce else {})}

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

  def restore(self, files, version):
    """Cleanup: the record's TinyUF2 installed again and its blinky copied through the drive; the board must
    leave DFU and stay out of it."""
    self.install(files)
    ev = {'dfu': self.dfu_after_install(version)['usb'], 'copy': self.copy(files['blinky'], files['blinkyBlocks'])}
    ev.update(self.after_copy())
    stays_away(lambda: usb_device(self.f['vid'], self.f['pid'], self.b['uid']), QUIET_TIME,
               'the DFU device came back after the blinky copy', ev)
    return {'pass': True, 'state': 'blinky copied', 'evidence': ev}

  def report_fields(self):
    # the cleanup's retries and cycles land here too: the same lists
    return {'jlinkRetried': self.probe.retried, **({'portCycles': self.power.cycles} if self.power.cfg else {})}

  def install(self, files):
    """The record's tinyuf2-jlink target, then the BIN verified at its flash address in a session of the runner's."""
    fl = files['flash']
    ev = self.flash_target(fl, ['cmake', '--build', fl['root'], '--target', fl['binding']['target']], PROBE_TIMEOUT,
                           lambda code, out: judge_jlink_target(code, out, self.b, files['hex']))
    settle = INSTALL_SETTLE_MS.get(self.b['device'])
    verify = ['h', f'verifybin {files["bin"]},{self.f["binBase"]:#x}', 'r', 'g']
    self.probe.run(([f'sleep {settle}'] if settle else []) + verify)
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
    chunks = after(out, 'regs')
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

  def __init__(self, board, facts, workdir, fail_at=None, commissioning=False):
    super().__init__(board, facts, workdir, fail_at, commissioning)
    self.probe = StlinkProbe(board, workdir, self.log)

  def readback(self, addr, want):
    return self.dir / f'readback-{time.monotonic_ns()}.bin', f'-u 0x{addr:08X} {len(want):#x}'

  def install(self, files):
    """The record's tinyuf2-stlink target, then the BIN read back from its flash address in a session of the runner's,
    which ends in a system reset (bench: the core runs after `-rst`)."""
    fl = files['flash']
    ev = self.flash_target(fl, ['cmake', '--build', fl['root'], '--target', fl['binding']['target']], PROBE_TIMEOUT,
                           lambda code, out: judge_stlink_target(code, out, self.b))
    want = Path(files['bin']).read_bytes()
    path, op = self.readback(self.f['binBase'], want)
    self.probe.run(['-halt', f'{op} {path}', '-rst'])
    if not uploaded(path, want):
      raise StepFail('the BIN does not read back from its flash address', ev)
    return dict(ev, verified=True)

  def sysreset(self):
    """SYSRESETREQ without the CLI's read-back, which the reset would fail (bench: `-nv` writes and exits 0, the host
    sees the device re-enumerate); issued only once the write is reported done."""
    body = self.probe.run([f'-w32 0x{SCB_AIRCR:08X} 0x{AIRCR_SYSRESETREQ:08X} -nv'])[0]
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
           '-halt', '-coreReg', f'{op} {path}', '-run']
    out = self.probe.run(ops)
    if not uploaded(path, want):
      raise StepFail('the fixture image does not read back from the app start')
    first, second = (core_regs(body) for o, body in zip(ops, out) if o == '-coreReg')
    return self.app_evidence(first, second, r32_value(out[ops.index(vtor)], SCB_VTOR))


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
  try:
    blocks = parse_uf2(Path(uf2_path).read_bytes())
  except (OSError, ValueError) as e:
    raise Refused(f'{uf2_path}: {e}')
  for i, bl in enumerate(blocks):
    if (bl['no'], bl['total'], bl['addr'], bl['size'], bl['family']) != (i, len(blocks), 256 * i, 256, facts['family']) \
       or not bl['flags'] & UF2_FLAG_FAMILY:
      raise Refused(f'{uf2_path}: block {i} is not block {i} of {len(blocks)} at {256 * i:#x} for family {facts["family"]:#x}')
  size, cache = board['app'][1] - board['app'][0], facts['flashCache']
  off = size - NONCE_BLOCK
  if not blocks or off < 256 * len(blocks) or off % 256 or off // cache * cache + cache > size:
    raise Refused(f'{uf2_path}: the app [0, {256 * len(blocks):#x}) and the nonce block at {off:#x} (in a {cache:#x} '
                  f'cache window) do not both fit in the {size:#x} app partition in order')
  return {'appChunks': [bl['data'] for bl in blocks], 'nonceOffset': off}


class EspBattery(Battery):
  """The battery on an esptool board. TinyUF2 copies apps/dfu_runtime with this run's nonce block past the
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
    check_preserved(self.preserved, preserved_md5(keep, self.tool.run(preserved_ops(keep), 'hard-reset')), 'restore')
    return {'preserved': 'unchanged since the snapshot before the install'}

  def install(self, files):
    """The preserved regions' snapshot first, in a session of its own, which the report keeps however the run ends:
    a recovery's restore checks against it. A restore reuses the run's snapshot, or a recovery's. Then ESP-IDF's
    flash target in CI's image, given only the bridge's tty, in a container named for the board so a survivor is
    found and ended by name (cleanup, recovery); then the runner's own read-back."""
    tty = esp_port(self.b['probe'])   # no bridge fails here, untouched; any session may leave the chip in its ROM loader
    name = f'tinyuf2-hil-{self.b["name"]}'
    if container_present(name):
      raise StepFail(f'container {name} from an earlier flash still exists: check what it runs, then docker rm -f {name}')
    fl = files['flash']
    # created, not run: the container exists, and its name is tracked, before anything can start it; cleanup
    # removes it by name however the run ends. IDF_FLASH_FULL: v6's fast reflash skips segments already in
    # flash, and judge_esp_target needs every segment written and verified
    CONTAINERS.append(name)
    code, out = spawn(cb.idf_docker(fl['root'], 'create') + [
      '--name', name, '--device', tty, '--group-add', str(os.stat(tty).st_gid), '-e', f'ESPPORT={tty}',
      '-e', 'IDF_FLASH_FULL=1', fl['image'],
      'cmake', '--build', str(fl['root']), '--target', fl['binding']['target']], self.log, 60)
    if code:
      raise StepFail(f'docker create {name} failed (exit {code})', {'tail': out.strip().splitlines()[-3:]})
    self.touched = True
    if self.preserved is None:
      keep = self.b['regions']['preserved']
      self.preserved = preserved_md5(keep, self.tool.run(preserved_ops(keep), 'no-reset'))
    ev = self.flash_target(fl, ['docker', 'start', '-a', name], ESP_TIMEOUT,
                           lambda code, out: judge_esp_target(code, out, files['segments']))
    if container_gone(name):
      CONTAINERS.remove(name)
    ev.update(esp_verify(self.tool, self.b, files['segments'], self.dir, self.preserved))
    return {'wrote': ev['wrote'], 'writes': ev['writes'], 'readBack': True}

  def report_fields(self):
    keep = self.b['regions']['preserved']
    return {'snapshot': self.preserved and {'preserved': self.preserved,
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


BATTERIES = {'jlink': Battery, 'stlink': StlinkBattery, 'esptool': EspBattery}


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


def check_esptool():
  import importlib.metadata
  try:
    v = importlib.metadata.version('esptool')
  except importlib.metadata.PackageNotFoundError:
    v = None
  if v != ESPTOOL_VERSION:
    raise Refused(f'esptool {v} is installed for {sys.executable}; the runner needs esptool {ESPTOOL_VERSION}')


def check_pyusb():
  try:
    import usb.backend.libusb1
  except ImportError:
    raise Refused(f'pyusb is not installed for {sys.executable}; usb_dfu.py needs it')
  if usb.backend.libusb1.get_backend() is None:
    raise Refused('pyusb finds no libusb-1.0; usb_dfu.py needs it')


def check_flasher(board):
  {'esptool': check_esptool, 'stlink': check_stlink}.get(board['flasher'], check_jlink)()
  if board.get('usbPower'):
    try:
      disable = port_dir(board['usbPower']) / 'disable'
    except StepFail as e:
      raise Refused(f'{board["name"]}: usbPower: {e}')
    if not os.access(disable, os.W_OK):
      raise Refused(f'{board["name"]}: usbPower: {disable} is not writable (SKILL.md, Commissioning: Port power)')


def reentry_decision(row):
  """The re-entry method a commissioning run establishes (SKILL.md, Commissioning), or None: every
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
  if board['flasher'] in ('jlink', 'stlink'):
    data = parse_hex(files['hex'])
    check_ranges(data, [board['install']], FLASH_LIMITS[board['device']], files['hex'])
    if not hex_matches_bin(data, files['bin'], facts['binBase']):
      raise Refused(f'{files["hex"]} and {files["bin"]} do not hold the same bytes')
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
  if method not in REENTRY[board['flasher']]:
    raise Refused(f'{board["name"]}: a {board["flasher"]} board re-enters by one of {REENTRY[board["flasher"]]}')
  return dict(board, reentry=method)


def run_board(args, board, facts, helper, workdir):
  row = {'board': board['name'], 'lock': board['lock'], 'ran': False, 'pass': False, 'locked': False,
         'lockBypassed': False, 'steps': [], 'cleanup': None, 'detail': ''}
  methods = REENTRY[board['flasher']]
  if args.fail_at and args.fail_at not in (*STEPS[board['flasher']], 'cleanup'):
    raise Refused(f'{board["name"]}: the {board["flasher"]} battery has no step {args.fail_at}')
  if args.try_reentry:
    board = trial_reentry(board, args.try_reentry)
    row.update(commissioning=True, tried=args.try_reentry)
  elif board['reentry'] not in methods:
    raise Refused(f'{board["name"]}: tinyuf2.reentry must be one of {methods} (set from commissioning)')
  files, row['firmware'] = admit_record(args.build_record, board, facts, workdir)
  if board['flasher'] == 'esptool':
    check_pyusb()
  # blocked from here until the process exits or becomes the holder (keep_held): a signal acts only
  # inside the battery, and the report and any hold are settled first
  signal.pthread_sigmask(signal.SIG_BLOCK, TERM_SIGNALS)
  try:
    fh = helper.acquire_board_lock(board['lock'])
  except helper.LockUnavailable as e:
    raise Refused(f'{board["name"]}: {e}; refusing to run unlocked')
  except RuntimeError as e:
    row.update(locked=True, detail=str(e))
    return deferred(row), 1
  row['lockBypassed'] = fh is None
  bat = BATTERIES[board['flasher']](board, facts, workdir, args.fail_at, row.get('commissioning', False))
  code = 0
  try:
    row['ran'] = True
    with signals(signal.SIG_UNBLOCK):
      bat.run(files, row['firmware']['version'])
    row['pass'] = True
  except BaseException as e:   # anything after admission still cleans up below
    row['detail'] = f'{bat.at}: {e}' if isinstance(e, StepFail) else f'{bat.at}: {type(e).__name__}: {e}'
    code = 1
  row['steps'] = bat.steps
  code = clean_up(row, code, bat, fh, board, helper, files)
  row.update(bat.report_fields())   # after the cleanup, whose install may take the snapshot a recovery needs
  if row.get('commissioning'):
    row['reentryDecision'] = reentry_decision(row)
  return deferred(row), code


def deferred(row):
  pending = sorted(signal.Signals(s).name for s in signal.sigpending() & TERM_SIGNALS)
  if pending:
    row['detail'] = '; '.join(filter(None, (row['detail'], f'{", ".join(pending)} deferred until the board was settled')))
  return row


def clean_up(row, code, bat, fh, board, helper, files):
  """Restore a touched board to the record's TinyUF2 with blinky copied, then release it. A child that survived
  SIGKILL, or any unsuccessful cleanup, leaves the board held (exit 4), touched or not."""
  stuck = []
  try:
    stuck = stuck_children()
    if stuck:
      raise StepFail('children survived SIGKILL; no flash may overlap them')   # their pids are in survivors
    if bat.touched:
      if bat.fail_at == 'cleanup':
        raise StepFail('--fail-at cleanup: injected cleanup failure (acceptance only)')
      row['cleanup'] = dict(bat.restore(files, row['firmware']['version']), heldAfter=False)
    else:
      row['cleanup'] = {'pass': True, 'state': 'untouched', 'evidence': {}, 'heldAfter': False}
  except BaseException as e:
    stuck += [x for x in stuck_children() if x not in stuck]
    row['cleanup'] = {'pass': False, 'state': 'unknown' if bat.touched else 'untouched',
                       'evidence': getattr(e, 'evidence', {}), 'detail': f'{type(e).__name__}: {e}',
                       'survivors': stuck, 'heldAfter': fh is not None}
    row['pass'] = False
    if fh is not None:
      row['cleanup']['holder'] = hand_off(fh, board['lock'], row['cleanup']['detail'], stuck)
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
  r.add_argument('--build-record', required=True, help='check_build.py --board B [--backend cmake] --shared --hil-config ROSTER '
                 'JSON, under cmake-build/')
  r.add_argument('--fail-at', choices=(*STEPS['esptool'], 'cleanup'), help='acceptance only: fail this step, or the cleanup, '
                 'to exercise cleanup and its holder')
  r.add_argument('--try-reentry', choices=REENTRY_METHODS, help="commissioning only, while the roster's reentry is unset")
  r.add_argument('config')
  i = sub.add_parser('install', help='program a bootloader under your own manual hold')
  i.add_argument('-b', '--board', required=True)
  i.add_argument('--build-record', required=True, help="the HIL build record whose TinyUF2 is installed")
  i.add_argument('--under-hold', required=True, metavar='REASON')
  i.add_argument('--try-reentry', choices=REENTRY_METHODS,
                 help="commissioning only, while the roster's reentry is unset: DFU's fallback after the install")
  i.add_argument('config')
  s = sub.add_parser('restore', help="install the record's TinyUF2 and copy its blinky, under your hold or to "
                     'recover a holder')
  s.add_argument('-b', '--board', required=True)
  s.add_argument('--build-record', required=True, help='the build record whose TinyUF2 and apps/blinky.uf2 are installed')
  g = s.add_mutually_exclusive_group(required=True)
  g.add_argument('--under-hold', metavar='REASON')
  g.add_argument('--recover-holder', type=int, metavar='PID')
  s.add_argument('--report', help="the failed run's hil_report.json (with --recover-holder)")
  s.add_argument('--try-reentry', choices=REENTRY_METHODS,
                 help="commissioning only, under your hold, while the roster's reentry is unset")
  s.add_argument('config')
  fr = sub.add_parser('fat-read')
  fr.add_argument('--dev', required=True)
  fr.add_argument('--file', required=True)
  fr.add_argument('--length', type=int, required=True)
  fr.add_argument('--offset', type=int, default=0)
  args = ap.parse_args(argv)
  if args.cmd == 'fat-read':
    return fat_read_main(args)
  for sig in TERM_SIGNALS:
    signal.signal(sig, on_signal)
  run_dir = cb.BUILD_DIR / 'hil' / f'run-{time.strftime("%Y%m%d-%H%M%S")}-{os.getpid()}'
  result = {'pass': False, 'caveat': '', 'results': [], 'reportPath': str(run_dir / 'hil_report.json')}
  code, recovery, bat = 2, None, None
  try:
    run_dir.mkdir(parents=True)
    board = load_board(args.config, args.board)
    facts = source_facts(board)
    apply_layout(board, facts)
    helper = load_helper()
    if args.cmd == 'run':
      row, code = run_board(args, board, facts, helper, run_dir)
      result['results'].append(row)
      result['pass'] = code == 0 and row['pass']
    elif args.cmd == 'install':
      board = trial_reentry(board, args.try_reentry)
      manual_holder(helper, board['lock'], args.under_hold)
      files, fw = admit_record(args.build_record, board, facts, run_dir)
      bat = BATTERIES[board['flasher']](board, facts, run_dir)
      try:
        ev = bat.install(files)
        ev['dfu'] = bat.dfu_after_install(fw['version'])
      finally:
        result['survivors'] = stuck_children()
      result['results'].append({'board': board['name'], 'installed': fw, 'evidence': ev})
      result['pass'], code = True, 0
    else:
      files, fw = admit_record(args.build_record, board, facts, run_dir)
      rec = snapshot = None
      if args.recover_holder is not None:
        if args.try_reentry:
          raise Refused('--try-reentry is for a restore under your own hold, not a recovery')
        if not args.report:
          raise Refused("--recover-holder needs --report, the failed run's report naming that holder")
        try:
          rows = json.loads(Path(args.report).read_text())['results']
        except (OSError, ValueError, KeyError, TypeError) as e:
          raise Refused(f'cannot read {args.report}: {e}')
        failed = [x for x in rows if ((x.get('cleanup') or {}).get('holder') or {}).get('pid')
                  == args.recover_holder and x.get('board') == board['name']]
        if len(failed) != 1:
          raise Refused(f'{args.report} names no cleanup holder {args.recover_holder} of {board["name"]}')
        held = [failed[0]['cleanup']]
        if board['flasher'] == 'esptool':
          snapshot = report_snapshot(failed[0], board['regions']['preserved'])
        recovery = recovery_lock(helper, board['lock'])
        rec = prove_hold(helper, board['lock'], args.recover_holder, reason='hil_test.py', role=HOLDER_ROLE)
        cmdline = Path(f'/proc/{args.recover_holder}/cmdline').read_bytes()
        if b'hil_test.py' not in cmdline:
          raise Refused(f'pid {args.recover_holder} is not a hil_test.py cleanup holder')
        alive = still_alive(held[0].get('survivors', []) + rec.get('survivors', []))
        if alive:
          raise Refused(f'the failed run\'s children {alive} are still alive; recovery may not overlap them')
      else:
        board = trial_reentry(board, args.try_reentry)
        manual_holder(helper, board['lock'], args.under_hold)
      users = probe_users(board)
      if users:
        raise Refused(f'probe {board["probe"]} is still in use by pids {users}; recovery may not overlap them')
      bat = BATTERIES[board['flasher']](board, facts, run_dir)
      try:
        if snapshot:
          bat.preserved = snapshot
        cleanup = bat.restore(files, fw['version'])
      finally:
        result['survivors'] = stuck_children()
      if result['survivors']:
        raise StepFail('restore left children that survived SIGKILL')
      if args.recover_holder is not None:
        os.kill(args.recover_holder, signal.SIGUSR1)
        wait_for(lambda: flock_free(helper.lock_path(board['lock'])), 10,
                 f'cleanup holder {args.recover_holder} releasing {board["name"]}')
        cleanup['recovered'] = {'holder': args.recover_holder, 'record': rec}
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
  if recovery:
    recovery.close()
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
