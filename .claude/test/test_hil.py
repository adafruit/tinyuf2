#!/usr/bin/env python3
"""Tests of the HIL contract's runner. Stubs prove the plumbing only: every probe and USB path here is
unverified until a real run on the rig (SKILL.md, commissioning)."""
import contextlib
import importlib.util
import io
import json
import os
import signal
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '.claude' / 'skills' / 'hil' / 'scripts' / 'hil_test.py'
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('hil_test', SCRIPT)
ht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ht)
BOARD = 'lpcxpresso55s69'

# the API hil_test.py uses from tinyusb's test/hil/helper/hil_lock.py, with the same flock and record
# semantics; set TINYUSB_HIL_LOCK to the real helper to run the lock tests against it instead
FAKE_HELPER = '''
import fcntl, json, os, time
BOARD_LOCK_DIR = {dir!r}
CI_REASON = 'hil_test.py'
PROTECTED_REASONS = {{CI_REASON, 'pool_check'}}
def lock_path(board): return os.path.join(BOARD_LOCK_DIR, f'{{board}}.lock')
def flock_nb(board):
  fh = os.fdopen(os.open(lock_path(board), os.O_RDWR | os.O_CREAT, 0o666), 'r+')
  try:
    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except OSError:
    fh.close(); raise
  return fh
def write_record(fh, reason):
  fh.truncate(0); fh.seek(0)
  json.dump({{'pid': os.getpid(), 'reason': reason, 'since': ''}}, fh); fh.flush(); return True
def clear_record(fh): fh.truncate(0)
def read_record(board):
  try:
    with open(lock_path(board)) as f: return json.load(f)
  except (OSError, ValueError): return None
def acquire_board_lock(board, reason=CI_REASON):
  if os.environ.get('HIL_NO_BOARD_LOCK') == '1': return None
  try:
    os.makedirs(BOARD_LOCK_DIR, exist_ok=True)
    fh = os.fdopen(os.open(lock_path(board), os.O_RDWR | os.O_CREAT, 0o666), 'r+')
  except OSError:
    return None
  try:
    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
  except OSError:
    info = fh.read(500).strip(); fh.close(); raise RuntimeError(f'board locked: {{info}}')
  write_record(fh, reason); return fh
'''

HOLDER = '''
import fcntl, json, os, sys, time
fh = os.fdopen(os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o666), 'r+')
if sys.argv[3] == 'lock':
  fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
fh.truncate(0); fh.seek(0); json.dump({'pid': os.getpid(), 'reason': sys.argv[2]}, fh); fh.flush()
print('ready', flush=True)
time.sleep(60)
'''


def roster(tmp, host='testhost', **over):
  t = {'port': 'lpc55', 'jlink': {'if': 'SWD', 'speed': '4000'},
       'layout': {'install': ['0x0', '0x10000'], 'app': ['0x10000', '0x98000'], 'pageSize': 512},
       'reentry': 'retained-register',
       'restore': {'bin': str(tmp / 'restore.bin'), 'sha256': 'x', 'version': '0.35.0',
                   'layout': {'install': ['0x0', '0x10000'], 'appStart': '0x10000'}}}
  t.update(over.pop('tinyuf2', {}))
  b = {'name': BOARD, 'uid': 'UID', 'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0'},
       'tinyuf2': t}
  b.update(over)
  cfg = tmp / 'local.json'
  cfg.write_text(json.dumps({'host': host, 'lock': {'helper': str(tmp / 'hil_lock.py')}, 'boards': [b]}))
  return cfg


class Tmp(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)


class Roster(Tmp):
  def test_a_valid_entry_loads(self):
    b = ht.load_board(roster(self.tmp), BOARD)
    self.assertEqual((b['install'], b['app'], b['device']), ((0, 0x10000), (0x10000, 0x98000), 'LPC55S69_M33_0'))

  def test_refusals(self):
    cases = {
      'args': {'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0 -if SWD'}},
      'int uid': {'flasher': {'name': 'jlink', 'uid': 1, 'args': '-device LPC55S69_M33_0'}},
      'ceiling': {'tinyuf2': {'layout': {'install': ['0x0', '0x10000'], 'app': ['0x10000', '0x9E000'],
                                         'pageSize': 512}}},
      'unknown device': {'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device NRF52840_XXAA'}},
      'no host': {'host': None},
      'no speed': {'tinyuf2': {'jlink': {'if': 'SWD'}}},
      'bad range': {'tinyuf2': {'layout': {'install': ['0x10000', '0x0'], 'app': ['0x10000', '0x98000'],
                                           'pageSize': 512}}},
    }
    for what, over in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.load_board(roster(self.tmp, **over), BOARD)

  def test_helper_path_is_required_and_absolute(self):
    cfg = roster(self.tmp)
    d = json.loads(cfg.read_text())
    d['lock']['helper'] = 'hil_lock.py'
    cfg.write_text(json.dumps(d))
    with self.assertRaises(ht.Refused):
      ht.load_board(cfg, BOARD)

  def test_the_committed_roster_is_well_formed_but_waits_for_commissioning(self):
    b = ht.load_board(ROOT / 'test' / 'hil' / 'local.json', BOARD)
    self.assertEqual((b['host'], b['reentry']), ('htpc', None))
    ht.check_layout(b, ht.source_facts(b))


def bootloader_bin(path, size=0x5824, board_id=b'LPC55S69-Xpresso-revA', version=b'0.35.0 - tinyusb (x)'):
  body = b'TinyUF2 Bootloader ' + version + b'\r\nModel: x\r\nBoard-ID: ' + board_id + b'\r\n'
  path.write_bytes(body + b'\xff' * (size - len(body)))
  return path


class Admission(Tmp):
  """Every span a bootloader install or a restore writes is checked before the lock is taken."""

  def setUp(self):
    super().setUp()
    self.board = ht.load_board(roster(self.tmp), BOARD)
    self.facts = ht.source_facts(self.board)

  def restore_profile(self, **over):
    r = self.board['restore']
    r.update(bin=str(bootloader_bin(self.tmp / 'restore.bin')), version='0.35.0 - tinyusb (x)')
    r.update(over)
    r.setdefault('sha256', None)
    r['sha256'] = ht.sha256(r['bin'])
    return r

  def test_a_good_candidate_and_restoration_image_pass(self):
    ht.check_bootloader_bin(bootloader_bin(self.tmp / 'c.bin'), self.board['install'], self.board['app'],
                            self.board, self.facts, 'candidate')
    self.restore_profile()
    ht.check_restore(self.board, self.facts)

  def test_candidate_refusals(self):
    cases = {'too big for the install range': bootloader_bin(self.tmp / 'a.bin', size=0x10001),
             'another board': bootloader_bin(self.tmp / 'b.bin', board_id=b'OTHER')}
    for what, path in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.check_bootloader_bin(path, self.board['install'], self.board['app'], self.board, self.facts, 'c')

  def test_restoration_refusals(self):
    cases = {
      'zero page in CMPA': {'appStart': 0x9E400, 'install': (0, 0x9E400)},   # Codex's reproduction
      'zero page over the ceiling': {'appStart': 0x9D700, 'install': (0, 0x9D700)},
      'install not ending at its app start': {'install': (0, 0x8000)},
      'image bigger than its install range': {'appStart': 0x4000, 'install': (0, 0x4000)},
    }
    for what, over in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        self.restore_profile(**over)
        ht.check_restore(self.board, self.facts)

  def test_a_restoration_image_without_its_version_or_hash_is_refused(self):
    r = self.restore_profile(version='0.36.0')
    with self.assertRaisesRegex(ht.Refused, 'version'):
      ht.check_restore(self.board, self.facts)
    r.update(version='0.35.0 - tinyusb (x)', sha256='0' * 64)
    with self.assertRaisesRegex(ht.Refused, 'sha256'):
      ht.check_restore(self.board, self.facts)


class SourceFacts(unittest.TestCase):
  def test_lpc55_facts_come_from_the_source(self):
    f = ht.source_facts({'port': 'lpc55', 'name': BOARD})
    self.assertEqual((f['appStart'], f['flashSize'], f['vid'], f['pid'], f['family']),
                     (0x10000, 0x98000, 0x1fc9, 0x0094, 0x2abc77ec))
    self.assertEqual((f['dblTapReg'], f['spareReg']), (0x4002C05C, 0x4002C058))   # RTC (non-secure) GPREG[7], [6]
    self.assertEqual(f['vectors'], 76)

  def test_a_layout_that_disagrees_with_the_source_is_refused(self):
    b = ht.load_board(roster(Path(tempfile.mkdtemp()), tinyuf2={'layout': {
      'install': ['0x0', '0x8000'], 'app': ['0x8000', '0x98000'], 'pageSize': 512}}), BOARD)
    with self.assertRaises(ht.Refused):
      ht.check_layout(b, ht.source_facts(b))


def ihex(records):
  lines = []
  for kind, addr, data in records:
    rec = bytes([len(data)]) + addr.to_bytes(2, 'big') + bytes([kind]) + data
    lines.append(':' + (rec + bytes([(-sum(rec)) & 0xFF])).hex().upper())
  return '\n'.join(lines + [':00000001FF']) + '\n'


class Images(Tmp):
  def test_hex_extended_address_and_range_checks(self):
    p = self.tmp / 'a.hex'
    p.write_text(ihex([(4, 0, b'\x00\x01'), (0, 0x0000, b'\xaa\xbb')]))   # 0x10000
    data = ht.parse_hex(p)
    self.assertEqual(data, {0x10000: 0xaa, 0x10001: 0xbb})
    self.assertEqual(ht.check_ranges(data, [(0x10000, 0x98000)], 0x9D800, 'x'), (0x10000, 0x10002))
    with self.assertRaises(ht.Refused):
      ht.check_ranges(data, [(0, 0x10000)], 0x9D800, 'x')
    with self.assertRaises(ht.Refused):
      ht.check_ranges({0x9D7FF: 1, 0x9D800: 1}, [(0, 0x9E000)], 0x9D800, 'x')   # one byte over the ceiling
    self.assertEqual(ht.check_ranges({0x9D7FF: 1}, [(0, 0x9E000)], 0x9D800, 'x'), (0x9D7FF, 0x9D800))

  def test_a_bad_checksum_is_refused(self):
    p = self.tmp / 'a.hex'
    p.write_text(':0100000000FE\n')
    with self.assertRaises(ht.Refused):
      ht.parse_hex(p)

  def test_bin_must_be_the_hex_laid_out_from_zero(self):
    p, b = self.tmp / 'a.hex', self.tmp / 'a.bin'
    p.write_text(ihex([(0, 0, b'\x01\x02'), (0, 4, b'\x05')]))
    b.write_bytes(b'\x01\x02\xff\xff\x05')
    self.assertTrue(ht.hex_matches_bin(ht.parse_hex(p), b))
    b.write_bytes(b'\x01\x02\xff\xff\x06')
    self.assertFalse(ht.hex_matches_bin(ht.parse_hex(p), b))

  def test_embedded_version(self):
    b = self.tmp / 'a.bin'
    b.write_bytes(b'\0junk TinyUF2 Bootloader 0.35.0-1-gabc - tinyusb (x)\r\nModel')
    self.assertEqual(ht.embedded_version(b), '0.35.0-1-gabc - tinyusb (x)')


class Exclusion(Tmp):
  def test_a_udev_rule_must_ignore_this_bootloader_by_serial(self):
    facts = {'vid': 0x1fc9, 'pid': 0x0094}
    rule = self.tmp / '99-tinyuf2-hil.rules'
    with mock.patch.object(ht, 'UDEV_RULES', (str(self.tmp),)):
      for text, ok in (('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="UID", '
                        'ENV{UDISKS_IGNORE}="1"', True),
                       ('# ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="UID", '
                        'ENV{UDISKS_IGNORE}="1"', False),
                       ('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="OTHER", '
                        'ENV{UDISKS_IGNORE}="1"', False),
                       ('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}!="UID", '
                        'ENV{UDISKS_IGNORE}="1"', False),
                       ('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="OTHERUID", '
                        'ENV{UDISKS_IGNORE}="1"', False),
                       ('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="UID", '
                        'ENV{UDISKS_IGNORE}="0"', False),
                       ('SUBSYSTEM=="block", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", '
                        'ATTRS{serial}=="UID", ENV{UDISKS_IGNORE}="1"', True),
                       ('ACTION=="remove", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", '   # Codex's case
                        'ATTRS{serial}=="UID", ENV{UDISKS_IGNORE}="1"', False),
                       ('SUBSYSTEM=="usb", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", '
                        'ATTRS{serial}=="UID", ENV{UDISKS_IGNORE}="1"', False),
                       ('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="UID", '
                        'ATTRS{serial}=="X", ENV{UDISKS_IGNORE}="1"', False),
                       ('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="UID", '
                        'ENV{UDISKS_IGNORE}="1", GOTO="end"', False),
                       ('ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="UID", '
                        'ENV{UDISKS_IGNORE}="1" junk', False)):
        rule.write_text(text + '\n')
        with self.subTest(text):
          if ok:
            self.assertEqual(ht.exclusion_configured(facts, 'UID'), str(rule))
          else:
            self.assertRaises(ht.Refused, ht.exclusion_configured, facts, 'UID')


class Fixture(Tmp):
  def setUp(self):
    super().setUp()
    self.facts = ht.source_facts({'port': 'lpc55', 'name': BOARD})
    self.fx = ht.fixture(self.facts, b'n' * 16)

  def test_vector_table_covers_every_vector_and_no_code_sits_inside_it(self):
    fx, img = self.fx, self.fx['image']
    self.assertEqual(fx['table'], 0x200)   # 76 vectors * 4 = 0x130, rounded up to a power of two
    self.assertGreaterEqual(fx['handler'] - self.facts['appStart'], 76 * 4)
    vec = struct.unpack_from(f'<{fx["table"] // 4}I', img)
    self.assertEqual((vec[0], vec[1]), (fx['sp'], fx['handler'] | 1))
    self.assertTrue(all(v == fx['fault'] | 1 for v in vec[2:]))
    self.assertEqual(struct.unpack_from('<HHH', img, fx['table']), (0x3001, 0xE7FD, 0xE7FE))

  def test_the_branch_returns_to_the_handler(self):
    imm11 = 0xE7FD & 0x7FF
    offset = ((imm11 - 0x800 if imm11 & 0x400 else imm11) << 1)
    self.assertEqual(self.fx['handler'] + 2 + 4 + offset, self.fx['handler'])   # b at handler+2, PC reads +4

  def test_a_new_nonce_changes_the_payload(self):
    self.assertNotEqual(ht.fixture(self.facts, b'm' * 16)['image'], self.fx['image'])

  def test_uf2_stays_in_the_app_range_and_writes_nothing_into_lib_uf2(self):
    _, uf2 = ht.make_uf2(self.fx['image'], self.facts['appStart'], self.facts['family'], self.tmp)
    blocks = ht.parse_uf2(uf2.read_bytes())
    self.assertTrue(all(b['family'] == self.facts['family'] for b in blocks))
    payload = {b['addr'] + i: x for b in blocks for i, x in enumerate(b['data'])}
    self.assertEqual(ht.check_ranges(payload, [(0x10000, 0x98000)], 0x9D800, 'uf2')[0], 0x10000)
    status = subprocess.run(['git', '-C', str(ROOT / 'lib' / 'uf2'), 'status', '--porcelain', '--untracked-files=all'],
                            capture_output=True, text=True, env={k: v for k, v in os.environ.items()
                                                                 if not k.startswith('GIT_')})
    self.assertEqual(status.stdout, '')


def fat_image():
    img = bytearray(64 * 512)
    struct.pack_into('<HBHB', img, 11, 512, 1, 1, 2)
    struct.pack_into('<H', img, 17, 16)
    struct.pack_into('<H', img, 22, 1)
    img[54:62] = b'FAT16   '
    root = (1 + 2 * 1) * 512
    data = root + 16 * 32
    img[root:root + 11] = b'INFO_UF2TXT'
    struct.pack_into('<HI', img, root + 26, 2, 5)
    img[root + 32:root + 43] = b'CURRENT UF2'
    struct.pack_into('<HI', img, root + 32 + 26, 3, 1024)
    img[data:data + 5] = b'hello'
    struct.pack_into('<HHH', img, 512 + 4, 0xFFFF, 4, 0xFFFF)   # FAT16: cluster 2 ends, 3 -> 4 -> end
    img[data + 512:data + 1024] = b'a' * 512
    img[data + 1024:data + 1536] = b'b' * 512
    return img


class Fat(Tmp):
  def vol(self, img):
    dev = self.tmp / 'vol'
    dev.write_bytes(bytes(img))
    return str(dev)

  def test_reads_entries_and_a_file_prefix(self):
    fat = ht.Fat(self.vol(fat_image()))
    self.assertEqual(fat.entries(), {'INFO_UF2.TXT': (2, 5), 'CURRENT.UF2': (3, 1024)})
    self.assertEqual(fat.file('INFO_UF2.TXT'), (b'hello', 5))
    self.assertEqual(fat.file('CURRENT.UF2', 600)[0], b'a' * 512 + b'b' * 88)

  def test_malformed_geometry_is_refused(self):
    for what, (off, fmt, v) in {'no sectors per cluster': (13, '<B', 0), 'odd sector size': (11, '<H', 100),
                                'no root entries': (17, '<H', 0), 'three FATs': (16, '<B', 3)}.items():
      img = fat_image()
      struct.pack_into(fmt, img, off, v)
      with self.subTest(what), self.assertRaisesRegex(ValueError, 'geometry'):
        ht.Fat(self.vol(img))

  def test_a_cyclic_or_broken_chain_and_a_short_read_are_errors(self):
    img = fat_image()
    struct.pack_into('<H', img, 512 + 8, 3)   # cluster 4 -> 3: a loop, read until the file's 4 KiB
    struct.pack_into('<I', img, (1 + 2 * 1) * 512 + 32 + 28, 4096)
    with self.assertRaisesRegex(ValueError, 'chain broken'):
      ht.Fat(self.vol(img)).file('CURRENT.UF2')
    img = fat_image()
    struct.pack_into('<H', img, 512 + 6, 0)   # cluster 3 -> free
    with self.assertRaisesRegex(ValueError, 'chain broken'):
      ht.Fat(self.vol(img)).file('CURRENT.UF2')
    with self.assertRaisesRegex(ValueError, 'short read'):
      ht.Fat(self.vol(fat_image()[:3 * 512])).entries()   # the root dir is cut off

  def test_fat_read_runs_in_a_bounded_child_and_reports_errors_as_step_failures(self):
    log = self.tmp / 'log'
    r = ht.fat_read(self.vol(fat_image()), 'CURRENT.UF2', 600, log)
    self.assertEqual((r['data'], r['size'], r['entries']['INFO_UF2.TXT']), (b'a' * 512 + b'b' * 88, 1024, [2, 5]))
    with self.assertRaisesRegex(ht.StepFail, 'not on the volume'):
      ht.fat_read(self.vol(fat_image()), 'NOPE.TXT', 10, log)
    self.assertEqual(ht.CHILDREN, [])


class Locks(Tmp):
  def setUp(self):
    super().setUp()
    real = os.environ.get('TINYUSB_HIL_LOCK')
    lockdir = self.tmp / 'locks'
    lockdir.mkdir()
    if real:
      self.helper = ht.load_helper(real)
      patch = mock.patch.object(self.helper, 'BOARD_LOCK_DIR', str(lockdir))
      patch.start()
      self.addCleanup(patch.stop)
    else:
      (self.tmp / 'hil_lock.py').write_text(FAKE_HELPER.format(dir=str(lockdir)))
      self.helper = ht.load_helper(self.tmp / 'hil_lock.py')
    self.lock = self.helper.lock_path(BOARD)

  def holder(self, reason, lock=True):
    p = subprocess.Popen([sys.executable, '-c', HOLDER, self.lock, reason, 'lock' if lock else 'nolock'],
                         stdout=subprocess.PIPE, text=True)
    self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close()))
    self.assertEqual(p.stdout.readline().strip(), 'ready')
    return p

  def test_a_real_manual_hold_is_proven(self):
    p = self.holder('debug session 7')
    ht.manual_holder(self.helper, BOARD, 'debug session 7')
    self.assertTrue(ht.holds_flock(p.pid, self.lock))

  def test_a_live_record_without_the_flock_is_refused(self):
    self.holder('debug session 7', lock=False)
    with self.assertRaisesRegex(ht.Refused, 'no flock'):
      ht.manual_holder(self.helper, BOARD, 'debug session 7')

  def test_another_reason_or_a_protected_one_is_refused(self):
    self.holder('someone else')
    with self.assertRaises(ht.Refused):
      ht.manual_holder(self.helper, BOARD, 'debug session 7')
    with self.assertRaises(ht.Refused):
      ht.manual_holder(self.helper, BOARD, 'hil_test.py')

  def test_cleanup_handoff_keeps_the_board_held_across_exec_and_recovery_can_end_it(self):
    fh = self.helper.acquire_board_lock(BOARD)
    holder = ht.hand_off(fh, BOARD, 'restore failed', [{'pid': 99, 'start': 1, 'cmd': ['mcopy']}])
    self.addCleanup(lambda: _kill(holder['pid']))
    self.assertTrue(holder['ready'])
    self.assertNotIn('inProcess', holder)
    with self.assertRaises(OSError):
      self.helper.flock_nb(BOARD)
    rec = ht.prove_hold(self.helper, BOARD, holder['pid'], reason='hil_test.py', role=ht.HOLDER_ROLE)
    self.assertEqual((rec['detail'], rec['survivors'][0]['pid']), ('restore failed', 99))
    self.assertFalse(ht.flock_free(self.lock))
    for sig in (signal.SIGTERM, signal.SIGINT):   # an operator's timeout kill does not free the board
      os.kill(holder['pid'], sig)
    time.sleep(0.3)
    self.assertFalse(ht.flock_free(self.lock))
    os.kill(holder['pid'], signal.SIGUSR1)
    ht.wait_for(lambda: ht.flock_free(self.lock), 5, 'release')
    self.helper.flock_nb(BOARD).close()
    self.assertIsNone(self.helper.read_record(BOARD))


  def test_a_holder_that_never_starts_leaves_the_lock_held_in_process(self):
    parent = os.getpid()
    real = ht.holder_record

    def dies_in_the_child(*a):
      if os.getpid() != parent:
        raise OSError('child died before its ack')
      return real(*a)
    for what, patch in (('fork fails', mock.patch.object(ht.os, 'fork', side_effect=OSError(11, 'EAGAIN'))),
                        ('pipe fails', mock.patch.object(ht.os, 'pipe', side_effect=OSError(24, 'EMFILE'))),
                        ('no ack', mock.patch.object(ht, 'holder_record', dies_in_the_child))):
      with self.subTest(what):
        fh = self.helper.acquire_board_lock(BOARD)
        with patch:
          holder = ht.hand_off(fh, BOARD, 'restore failed')
        self.assertEqual((holder['pid'], holder.get('inProcess')), (parent, True))
        with self.assertRaises(OSError):
          self.helper.flock_nb(BOARD)
        rec = ht.prove_hold(self.helper, BOARD, parent, reason='hil_test.py', role=ht.HOLDER_ROLE)
        self.assertEqual(rec['detail'], 'restore failed')
        ht.HELD_IN_PROCESS.pop().close()

  def test_with_no_descriptor_left_the_runner_itself_holds_and_releases_only_on_sigusr1(self):
    script = textwrap.dedent(f'''
      import importlib.util, json, os, resource, signal, sys
      spec = importlib.util.spec_from_file_location('ht', {str(SCRIPT)!r}); ht = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(ht)
      helper = ht.load_helper({str(self.helper.__file__)!r})
      helper.BOARD_LOCK_DIR = {str(Path(self.lock).parent)!r}
      fh = helper.acquire_board_lock({BOARD!r})
      signal.pthread_sigmask(signal.SIG_BLOCK, ht.TERM_SIGNALS)
      resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
      hog = []
      try:
        while True:
          hog.append(os.open(os.devnull, os.O_RDONLY))
      except OSError:
        pass
      holder = ht.hand_off(fh, {BOARD!r}, 'restore failed')
      print(json.dumps(holder), flush=True)
      ht.keep_held(ht.HELD_IN_PROCESS[0])
    ''')
    p = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True)
    self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close()))
    holder = json.loads(p.stdout.readline())
    self.assertEqual((holder['pid'], holder['inProcess']), (p.pid, True))
    self.assertEqual(p.stdout.read(), '')   # stdio closed: the caller's read ends while the hold stays
    for sig in (signal.SIGTERM, signal.SIGINT):
      p.send_signal(sig)
    time.sleep(0.3)
    self.assertIsNone(p.poll())
    ht.prove_hold(self.helper, BOARD, p.pid, reason='hil_test.py', role=ht.HOLDER_ROLE)
    p.send_signal(signal.SIGUSR1)
    self.assertEqual(p.wait(5), 0)
    self.helper.flock_nb(BOARD).close()

  def test_a_holder_handed_off_during_cleanup_still_ends_on_sigusr1(self):
    fh = self.helper.acquire_board_lock(BOARD)
    with ht.signals(signal.SIG_BLOCK):   # cleanup blocks SIGTERM and SIGINT; the holder must not care
      holder = ht.hand_off(fh, BOARD, 'restore failed')
    self.addCleanup(lambda: _kill(holder['pid']))
    os.kill(holder['pid'], signal.SIGUSR1)
    ht.wait_for(lambda: ht.flock_free(self.lock), 5, 'release')

  def test_survivors_are_identified_against_pid_reuse(self):
    me = {'pid': os.getpid(), 'start': ht.proc_start(os.getpid())}
    self.assertEqual(ht.still_alive([me, dict(me, start=me['start'] + 1), {'pid': 2 ** 22 + 1, 'start': 5}]), [me])

  def test_the_holder_keeps_none_of_the_callers_stdio(self):
    fh = self.helper.acquire_board_lock(BOARD)
    holder = ht.hand_off(fh, BOARD, 'x')
    self.addCleanup(lambda: _kill(holder['pid']))
    ht.wait_for(lambda: not any(Path(f'/proc/{holder["pid"]}/fd/{std}').exists() for std in (0, 1, 2)), 5,
                'the holder closing its stdio')


def _kill(pid):
  try:
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
  except (ProcessLookupError, ChildProcessError):
    pass


class RunBoard(Tmp):
  """The state machine around the battery: who restores, and what is left held."""

  def setUp(self):
    super().setUp()
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    handlers = {sig: signal.getsignal(sig) for sig in ht.TERM_SIGNALS}

    def unblock():   # run_board leaves the signals blocked until exit; drop what is pending, then restore
      for sig in ht.TERM_SIGNALS:
        signal.signal(sig, signal.SIG_IGN)
      signal.pthread_sigmask(signal.SIG_SETMASK, mask)
      for sig, h in handlers.items():
        signal.signal(sig, h)
    self.addCleanup(unblock)
    (self.tmp / 'hil_lock.py').write_text(FAKE_HELPER.format(dir=str(self.tmp / 'locks')))
    self.helper = ht.load_helper(self.tmp / 'hil_lock.py')
    self.board = ht.load_board(roster(self.tmp), BOARD)
    self.facts = ht.source_facts(self.board)
    self.args = mock.Mock(build_record='rec.json', fail_at=None)
    for p in (mock.patch.object(ht, 'verify_record', lambda *a: ({'hex': 'x.hex', 'bin': 'x.bin'}, {'version': 'v'})),
              mock.patch.object(ht, 'parse_hex', lambda p: {0: 1}),
              mock.patch.object(ht, 'hex_matches_bin', lambda d, b: True),
              mock.patch.object(ht, 'check_bootloader_bin', lambda *a: None),
              mock.patch.object(ht, 'check_restore', lambda *a: None),
              mock.patch.object(ht, 'exclusion_configured', lambda *a: None),
              mock.patch.object(ht.socket, 'gethostname', lambda: 'testhost'),
              mock.patch.object(ht.shutil, 'which', lambda t: '/usr/bin/' + t)):
      p.start()
      self.addCleanup(p.stop)

  def run_board(self, battery_run, restore=None):
    restored = []

    def fake_restore(*a, **k):
      restored.append(True)
      if restore:
        raise restore
      return {'pass': True, 'state': 'restoration bootloader in DFU', 'evidence': {}}
    with mock.patch.object(ht.Battery, 'run', battery_run), mock.patch.object(ht, 'restore', fake_restore):
      row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
    return row, code, restored

  def test_pass_restores_and_releases(self):
    def ok(bat, files, version):
      bat.touched = True
    row, code, restored = self.run_board(ok)
    self.assertEqual((code, row['pass'], restored, row['restored']['heldAfter']), (0, True, [True], False))
    self.helper.flock_nb(BOARD).close()

  def test_a_failed_step_after_touching_restores_and_is_exit_1(self):
    def fail(bat, files, version):
      bat.touched = True
      bat.steps.append({'step': 'app-ran', 'pass': False})
      raise ht.StepFail('pc not in the loop')
    row, code, restored = self.run_board(fail)
    self.assertEqual((code, row['pass'], restored), (1, False, [True]))
    self.assertIn('app-ran', row['detail'])

  def test_an_untouched_board_is_not_restored(self):
    def fail(bat, files, version):
      raise ht.StepFail('probe not found')
    row, code, restored = self.run_board(fail)
    self.assertEqual((code, restored, row['restored']), (1, [], None))

  def test_any_failed_restore_hands_the_lock_to_a_holder_and_is_exit_4(self):
    def fail(bat, files, version):
      bat.touched = True
      raise ht.StepFail('x')
    for err in (ht.StepFail('verify failed'), ht.Refused('range'), ValueError('parse'), ht.Interrupted('TERM')):
      with self.subTest(type(err).__name__), \
           mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1, 'reason': 'hil_test.py'})[1]):
        row, code, _ = self.run_board(fail, restore=err)
        self.assertEqual((code, row['pass'], row['restored']['heldAfter'], row['restored']['holder']['pid']),
                         (4, False, True, 1))

  def test_another_host_or_an_uncommissioned_board_is_refused_before_the_lock(self):
    with mock.patch.object(ht.socket, 'gethostname', lambda: 'ci'), self.assertRaisesRegex(ht.Refused, 'host'):
      self.run_board(lambda *a: self.fail('ran'))
    self.board['reentry'] = None
    with self.assertRaisesRegex(ht.Refused, 'commissioning'):
      self.run_board(lambda *a: self.fail('ran'))
    self.assertFalse(Path(self.helper.lock_path(BOARD)).exists())

  def test_a_signal_during_cleanup_waits_for_it(self):
    def ok(bat, files, version):
      bat.touched = True

    def restore_then_signalled(*a, **k):
      os.kill(os.getpid(), signal.SIGTERM)   # blocked until cleanup has ended
      return {'pass': True, 'state': 's', 'evidence': {}}

    signal.signal(signal.SIGTERM, ht.on_signal)
    with mock.patch.object(ht.Battery, 'run', ok), mock.patch.object(ht, 'restore', restore_then_signalled):
      row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
    self.assertEqual((code, row['pass'], row['restored']['heldAfter']), (0, True, False))
    self.assertIn('SIGTERM deferred', row['detail'])
    self.helper.flock_nb(BOARD).close()

  def test_a_signal_pending_at_a_locked_board_still_gives_its_row(self):
    held = self.helper.acquire_board_lock(BOARD, reason='someone')
    self.addCleanup(held.close)
    signal.signal(signal.SIGTERM, ht.on_signal)
    real = self.helper.acquire_board_lock

    def signalled_while_locking(board):
      os.kill(os.getpid(), signal.SIGTERM)
      return real(board)
    with mock.patch.object(self.helper, 'acquire_board_lock', signalled_while_locking):
      row, code, _ = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['locked'], row['ran']), (1, True, False))
    self.assertIn('SIGTERM deferred', row['detail'])

  def test_a_stuck_child_is_a_cleanup_failure_with_no_restore(self):
    def fail(bat, files, version):
      bat.touched = True
      raise ht.StepFail('x')
    stuck = [{'pid': 99, 'start': 7, 'cmd': ['JLinkExe']}]
    with mock.patch.object(ht, 'stuck_children', lambda: list(stuck)), \
         mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1, 'survivors': s})[1]):
      row, code, restored = self.run_board(fail)
    self.assertEqual((code, restored, row['restored']['survivors']), (4, [], stuck))
    self.assertIn('99', row['restored']['detail'])

  def test_a_survivor_on_an_untouched_board_still_keeps_it_held(self):
    def fail(bat, files, version):
      raise ht.StepFail('identity: probe hung')
    with mock.patch.object(ht, 'stuck_children', lambda: [{'pid': 99, 'start': 7, 'cmd': ['JLinkExe']}]), \
         mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1})[1]):
      row, code, restored = self.run_board(fail)
    self.assertEqual((code, restored, row['restored']['state'], row['restored']['heldAfter']),
                     (4, [], 'untouched', True))

  def test_repeated_signals_interrupt_the_battery_but_never_the_cleanup(self):
    signal.signal(signal.SIGTERM, ht.on_signal)

    def interrupted(bat, files, version):
      bat.touched = True
      os.kill(os.getpid(), signal.SIGTERM)
      self.fail('the signal did not interrupt the battery')

    def restore_under_fire(*a, **k):
      for _ in range(3):
        os.kill(os.getpid(), signal.SIGTERM)
      return {'pass': True, 'state': 's', 'evidence': {}}
    with mock.patch.object(ht.Battery, 'run', interrupted), mock.patch.object(ht, 'restore', restore_under_fire):
      row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
    self.assertEqual((code, row['restored']['pass'], row['restored']['heldAfter']), (1, True, False))
    self.assertIn('interrupted by SIGTERM', row['detail'])
    self.assertIn('SIGTERM deferred', row['detail'])
    self.helper.flock_nb(BOARD).close()

  def test_a_locked_board_is_not_touched(self):
    held = self.helper.acquire_board_lock(BOARD, reason='someone')
    self.addCleanup(held.close)
    row, code, restored = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['locked'], row['ran'], restored), (1, True, False, []))

  def test_an_unusable_lock_dir_is_refused_not_run_unlocked(self):
    with mock.patch.object(self.helper, 'acquire_board_lock', lambda b: None), \
         mock.patch.dict(os.environ, {'HIL_NO_BOARD_LOCK': ''}):
      with self.assertRaises(ht.Refused):
        self.run_board(lambda *a: self.fail('ran'))

  def test_fail_at_injects_a_criterion_failure(self):
    bat = ht.Battery(self.board, self.facts, self.tmp, 'dfu')
    bat.step('identity', lambda: {})
    with self.assertRaisesRegex(ht.StepFail, 'injected'):
      bat.step('dfu', lambda: {})


class FakeRig:
  """A probe and a UF2 drive that behave as the battery expects; each test breaks one thing."""

  def __init__(self, bat, reentry):
    self.bat, self.reentry, self.scripts, self.present = bat, reentry, [], True
    self.r0 = 5

  def probe(self, commands, judge=True):
    self.scripts.append(list(commands))
    f, out = self.bat.f, ''
    for c in commands:
      if c == 'regs':
        self.r0 += 7
        fx = self.bat.fix
        out += (f'J-Link>regs\nPC = {fx["handler"]:08X}, CycleCnt = 0\nR0 = {self.r0:08X}, R1 = 00000000\n'
                f'SP(R13)= {fx["sp"]:08X}, MSP= {fx["sp"]:08X}, PSP= 00000000\nIPSR = 000 (NoException)\n')
      elif c.startswith('mem32 '):
        a = int(c.split()[1], 16)
        v = f['appStart'] if a == ht.SCB_VTOR else 0
        out += f'J-Link>{c}\n{a:08X} = {v:08X} \n'
      elif c.startswith(f'w4 {ht.SCB_AIRCR:08X}') or (c == 'r' and self.reentry == 'app-invalidate'):
        self.present = True
    return out

  def spawn(self, cmd, log, timeout, cwd=None):
    if cmd[0] == 'mcopy':
      self.present = False
    return 0, ''

  def fat_read(self, dev, name, length, log):
    f = self.bat.f
    if name == 'INFO_UF2.TXT':
      data = (f'TinyUF2 Bootloader v1\r\nModel: x\r\nBoard-ID: {f["boardId"]}\r\nDate: d\r\n'
              f'Flash Size: 0x{f["flashSize"]:08X} bytes').encode()
    else:
      data = ht.make_uf2(bytes(self.current), f['appStart'], f['family'], self.bat.dir / 'cur')[1].read_bytes()[:length]
    return {'entries': {'CURRENT.UF2': [9, f['flashSize'] // 256 * 512]}, 'data': data, 'size': len(data)}


class BatteryRun(Tmp):
  """Battery.run end to end over a fake probe transcript and a fake drive: the plumbing, not the rig."""

  def battery(self, reentry='retained-register', corrupt=None):
    board = ht.load_board(roster(self.tmp, tinyuf2={'reentry': reentry}), BOARD)
    facts = ht.source_facts(board)
    bat = ht.Battery(board, facts, self.tmp)
    rig = FakeRig(bat, reentry)
    (self.tmp / 'cur').mkdir()
    bat.probe.run = rig.probe

    def fat_read(*a):
      rig.current = bytearray(bat.fix['image'])
      if reentry == 'app-invalidate':
        rig.current[:board['page']] = bytes(board['page'])
      if corrupt:
        corrupt(rig.current)
      return rig.fat_read(*a)
    for p in (mock.patch.object(ht, 'usb_device', lambda *a: '1-2' if rig.present else None),
              mock.patch.object(ht, 'block_device', lambda p: '/dev/sdz'),
              mock.patch.object(ht, 'check_exclusive', lambda d: None),
              mock.patch.object(ht, 'fat_read', fat_read),
              mock.patch.object(ht, 'spawn', rig.spawn),
              mock.patch.object(ht.time, 'sleep', lambda s: None)):
      p.start()
      self.addCleanup(p.stop)
    return bat, rig

  def test_every_step_passes_and_resumes_only_after_a_halt(self):
    for reentry in ht.REENTRY:
      with self.subTest(reentry):
        self.tmp = Path(tempfile.mkdtemp(dir=self.tmp))
        bat, rig = self.battery(reentry)
        bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
        self.assertEqual([x['step'] for x in bat.steps if x['pass']], list(ht.STEPS))
        self.assertEqual(rig.scripts[1][:3], ['h', f'loadbin {self.tmp / "c.bin"},0x0',
                                              f'loadbin {bat.zero},0x10000'])
        self.assertIn(f'sleep {2 * bat.f["dblTapDelayMs"] + 200}', rig.scripts[2])
        for script in rig.scripts:
          if 'g' in script:
            self.assertEqual(script[0], 'h', script)
        if reentry == 'retained-register':
          self.assertIn([f'w4 {ht.SCB_AIRCR:08X} {ht.AIRCR_SYSRESETREQ:08X}'], rig.scripts)

  def test_the_whole_fixture_is_read_back_including_its_last_partial_block(self):
    bat, _ = self.battery(corrupt=lambda img: img.__setitem__(len(img) - 1, img[-1] ^ 1))
    with self.assertRaisesRegex(ht.StepFail, 'read back the fixture'):
      bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
    self.assertEqual(bat.steps[-1]['step'], 'reenter')

  def test_a_wrong_version_on_the_drive_fails_dfu(self):
    bat, _ = self.battery()
    with self.assertRaisesRegex(ht.StepFail, 'INFO_UF2'):
      bat.run({'bin': self.tmp / 'c.bin'}, 'v2')


class AppRan(Tmp):
  """The probe transcript the app-ran step reads; its exact shape is bench-checked at commissioning."""

  def transcript(self, pc, r0s, ipsr=0, vtor=0x10000, msp=0x20001000):
    dump = lambda r0: textwrap.dedent(f'''\
      PC = {pc:08X}, CycleCnt = 00000000
      R0 = {r0:08X}, R1 = 00000000, R2 = 00000000, R3 = 00000000
      SP(R13)= {msp:08X}, MSP= {msp:08X}, PSP= 00000000, R14(LR) = FFFFFFFF
      XPSR = 01000000: APSR = nzcvq, EPSR = 01000000, IPSR = {ipsr:03X} (NoException)
      ''')
    return (f'J-Link>regs\n{dump(r0s[0])}J-Link>mem32 E000ED08 1\nE000ED08 = {vtor:08X} \n'
            f'J-Link>regs\n{dump(r0s[1])}')

  def test_regs_parse_two_dumps(self):
    out = self.transcript(0x10200, [5, 9])
    first, second = (ht.regs(c) for c in ht.after(out, 'regs'))
    self.assertEqual((first['pc'], first['r0'], second['r0'], first['ipsr'], first['msp']),
                     (0x10200, 5, 9, 0, 0x20001000))


class Main(Tmp):
  def test_manual_install_needs_no_reentry_and_programs_the_bin_with_a_zero_page(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    fw = bootloader_bin(self.tmp / 'fw.bin')
    programmed = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp), \
         mock.patch.object(ht, 'load_helper', lambda p: None), mock.patch.object(ht, 'manual_holder', lambda *a: None), \
         mock.patch.object(ht, 'exclusion_configured', lambda *a: None), \
         mock.patch.object(ht.Battery, 'program', lambda bat, b, a: programmed.append((b, a))):
      code = ht.main(['install', '-b', BOARD, '--firmware', str(fw), '--sha256', ht.sha256(fw),
                      '--under-hold', 'debug 7', str(cfg)])
    self.assertEqual((code, programmed), (0, [(str(fw), 0x10000)]))


  def test_a_refusal_is_a_ran_false_row_and_exit_2(self):
    cfg = roster(self.tmp, flasher={'name': 'jlink', 'uid': '1', 'args': '-device NOPE'})
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp):
      code = ht.main(['run', '-b', BOARD, '--build-record', 'r.json', str(cfg)])
    r = json.loads(out.getvalue().splitlines()[-1])
    self.assertEqual((code, r['pass'], r['results'][0]['ran']), (2, False, False))
    self.assertTrue(Path(r['reportPath']).is_file())


if __name__ == '__main__':
  unittest.main()
