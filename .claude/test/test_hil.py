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
RT = {'port': 'mimxrt10xx', 'name': 'imxrt1060_evk', 'lock': 'mimxrt1060_evk'}

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


def roster(tmp, **over):
  t = {'reentry': 'retained-register'}
  t.update(over.pop('tinyuf2', {}))
  b = {'name': BOARD, 'uid': 'UID', 'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0'},
       'tinyuf2': t}
  b.update(over)
  cfg = tmp / 'local.json'
  cfg.write_text(json.dumps({'boards': [b]}))
  return cfg


HELPER = Path('test/hil/helper/hil_lock.py')   # under TINYUSB_DIR


# lpc55 has no cmake build, so the runner reads no facts for it; most tests keep its layout as synthetic facts
LPC_FACTS = {'flashBase': 0, 'appStart': 0x10000, 'flashSize': 0x98000, 'vid': 0x1fc9, 'pid': 0x0094,
             'boardId': 'LPC55S69-Xpresso-revA', 'family': 0x2abc77ec, 'vectors': 76, 'ram': 0x20000000,
             'dblTapDelayMs': 500, 'dblTapReg': 0x4002C05C, 'dblTapMagic': 0xF01669EF}
real_source_facts = ht.source_facts


def source_facts(board):
  return dict(LPC_FACTS) if board['port'] == 'lpc55' else real_source_facts(board)


class Tmp(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    for p in (mock.patch.object(ht, 'source_facts', source_facts),
              mock.patch.dict(os.environ, {'TINYUSB_DIR': str(self.tmp)})):
      p.start()
      self.addCleanup(p.stop)

  def load(self, cfg, name=BOARD):
    """A roster entry with its layout applied, as main() admits it."""
    b = ht.load_board(cfg, name)
    ht.apply_layout(b, ht.source_facts(b))
    return b


class Roster(Tmp):
  def test_a_valid_entry_loads_with_its_layout_from_the_source(self):
    b = self.load(roster(self.tmp))
    self.assertEqual((b['install'], b['app'], b['page'], b['device'], b['if'], b['speed']),
                     ((0, 0x10000), (0x10000, 0x98000), 512, 'LPC55S69_M33_0', 'SWD', '4000'))
    self.assertEqual(b['helper'], str(self.tmp / HELPER))

  def test_refusals(self):
    cases = {
      'args': {'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0 -if SWD'}},
      'int uid': {'flasher': {'name': 'jlink', 'uid': 1, 'args': '-device LPC55S69_M33_0'}},
      'unknown device': {'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device NRF52840_XXAA'}},
      'bad lock name': {'tinyuf2': {'lock': '../x'}},
      'not a TinyUF2 board': {'name': 'no_such_board'},
    }
    for what, over in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.load_board(roster(self.tmp, **over), over.get('name', BOARD))

  def test_the_lock_helper_comes_from_an_absolute_tinyusb_dir(self):
    for value in ('', 'tinyusb'):
      with self.subTest(value), mock.patch.dict(os.environ, {'TINYUSB_DIR': value}), \
           self.assertRaisesRegex(ht.Refused, 'TINYUSB_DIR'):
        ht.load_board(roster(self.tmp), BOARD)
    with mock.patch.dict(os.environ), self.assertRaisesRegex(ht.Refused, 'TINYUSB_DIR'):
      del os.environ['TINYUSB_DIR']
      ht.load_board(roster(self.tmp), BOARD)

  def test_the_lock_defaults_to_the_board_name_and_the_port_comes_from_it(self):
    b = ht.load_board(roster(self.tmp), BOARD)
    self.assertEqual((b['lock'], b['port']), (BOARD, 'lpc55'))
    b = ht.load_board(roster(self.tmp, tinyuf2={'lock': 'other'}), BOARD)
    self.assertEqual((b['name'], b['lock']), (BOARD, 'other'))

  def test_layout_refusals(self):
    b = ht.load_board(roster(self.tmp), BOARD)
    cases = {'app start not page aligned': {'appStart': 0x10100},
             'app start at the flash base': {'appStart': 0},
             'app start past the flash end': {'appStart': 0x98000},
             'flash past the ceiling': {'flashSize': 0x9E000},
             'flash below the floor': {'flashBase': 0x100000000 - 0x98000 - 1}}
    for what, over in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.apply_layout(dict(b), dict(LPC_FACTS, **over))

  def test_the_committed_roster_is_well_formed_and_commissioned(self):
    b = self.load(ROOT / 'test' / 'hil' / 'local.json', 'imxrt1060_evk')
    self.assertEqual((b['lock'], b['reentry']), ('mimxrt1060_evk', 'retained-register'))
    self.assertEqual(b['install'], (0x60000000, 0x6000C000))


def bootloader_bin(path, size=0x5824, board_id=b'LPC55S69-Xpresso-revA', version=b'0.35.0 - tinyusb (x)'):
  body = b'TinyUF2 Bootloader ' + version + b'\r\nModel: x\r\nBoard-ID: ' + board_id + b'\r\n'
  path.write_bytes(body + b'\xff' * (size - len(body)))
  return path


class Admission(Tmp):
  """Every span a bootloader install writes is checked before the lock is taken."""

  def setUp(self):
    super().setUp()
    self.board = self.load(roster(self.tmp))
    self.facts = ht.source_facts(self.board)

  def test_a_good_candidate_passes(self):
    ht.check_bootloader_bin(bootloader_bin(self.tmp / 'c.bin'), self.board, self.facts, 'candidate')

  def test_candidate_refusals(self):
    cases = {'too big for the install range': bootloader_bin(self.tmp / 'a.bin', size=0x10001),
             'another board': bootloader_bin(self.tmp / 'b.bin', board_id=b'OTHER')}
    for what, path in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.check_bootloader_bin(path, self.board, self.facts, 'c')

def rt_roster(tmp):
  return roster(tmp, name='imxrt1060_evk', flasher={'name': 'jlink', 'uid': '2', 'args': '-device MIMXRT1062xxx6A'},
                tinyuf2={'lock': 'mimxrt1060_evk'})


class Rt1060(Tmp):
  """The RT1060 entry: board imxrt1060_evk, lock mimxrt1060_evk (tinyusb's name), flash from 0x60000000."""

  def setUp(self):
    super().setUp()
    self.board = self.load(rt_roster(self.tmp), 'imxrt1060_evk')
    self.facts = ht.source_facts(self.board)

  def test_the_layout_comes_from_the_source_and_spans_check_against_the_flash_base(self):
    self.assertEqual((self.board['install'], self.board['app']), ((0x60000000, 0x6000C000), (0x6000C000, 0x60800000)))
    bl = bootloader_bin(self.tmp / 'c.bin', board_id=b'MIMXRT1060-EVK-revA')
    ht.check_bootloader_bin(bl, self.board, self.facts, 'c')
    with self.assertRaises(ht.Refused):   # bigger than the install span at its base
      ht.check_bootloader_bin(bootloader_bin(self.tmp / 'big.bin', size=0xC001, board_id=b'MIMXRT1060-EVK-revA'),
                              self.board, self.facts, 'c')

  def test_the_build_record_is_read_by_board_name_and_must_be_cmake(self):
    build = self.tmp / 'b'
    (build / '_bin').mkdir(parents=True)
    rows = {}
    for kind in ('hex', 'bin'):
      f = build / '_bin' / f'tinyuf2.{kind}'
      f.write_bytes(b'TinyUF2 Bootloader 1.0\r\n')
      rows[f'_bin/{f.name}'] = ht.sha256(f)
    now = {'head': 'h', 'submodules': {}, 'deps': {}, 'dirty': False}
    rec = self.tmp / 'rec.json'
    row = {'board': 'imxrt1060_evk', 'status': 'ok', 'backend': 'cmake', 'buildDir': str(build), 'sha256': rows}
    rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [row]}))
    with mock.patch.object(ht.cb, 'identity', lambda ports: now):   # an absolute buildDir ignores cb.ROOT
      files, fw = ht.verify_record(rec, self.board, self.facts)
      self.assertEqual((files['bin'].name, fw['version']), ('tinyuf2.bin', '1.0'))
      rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [dict(row, backend='make')]}))
      with self.assertRaisesRegex(ht.Refused, 'cmake builds only .*--backend cmake --shared'):
        ht.verify_record(rec, self.board, self.facts)
      rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [row]}))
      (build / '_bin' / 'tinyuf2.bin').unlink()
      with self.assertRaisesRegex(ht.Refused, 'tinyuf2.bin: missing'):
        ht.verify_record(rec, self.board, self.facts)
    with mock.patch.object(ht.cb, 'identity', side_effect=ht.cb.Fail('git rev-parse HEAD failed')), \
         self.assertRaisesRegex(ht.Refused, 'cannot establish the checkout identity: git rev-parse'):
      ht.verify_record(rec, self.board, self.facts)


class SourceFacts(unittest.TestCase):
  def test_a_port_without_a_cmake_build_has_no_facts(self):
    with self.assertRaisesRegex(ht.Refused, 'ports/lpc55 has no cmake build'):
      ht.source_facts({'port': 'lpc55', 'name': BOARD})

  def test_rt1060_facts_come_from_the_source(self):
    f = ht.source_facts(RT)
    self.assertEqual((f['flashBase'], f['appStart'], f['flashSize'], f['vid'], f['pid'], f['boardId']),
                     (0x60000000, 0x6000C000, 0x800000, 0x239a, 0x0083, 'MIMXRT1060-EVK-revA'))
    self.assertEqual((f['dblTapReg'], f['ram'], f['vectors']), (0x400D410C, 0x20000000, 174))   # SNVS LPGPR[3]
    self.assertEqual(f['family'], 0x4fb2d5bd)

  def test_a_cmake_value_is_one_plain_set(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    (Path(t.name) / 'x.cmake').write_text('  # set(SDK_DIR old)\nset(SDK_DIR ${TOP}/lib/sdk)\nset(ID 0x1)\nset(ID 0x2)\nset(V ${OTHER}/x)\n'
                                          'set(Q "a")\nset(F 0x1)\nSET (F 0x2)\nset(E)\n')
    with mock.patch.object(ht, 'ROOT', Path(t.name)):
      self.assertEqual(ht.cmake_var('x.cmake', 'SDK_DIR'), 'lib/sdk')
      for name in ('ID', 'V', 'Q', 'F', 'E', 'NONE'):
        with self.subTest(name), self.assertRaises(ht.Refused):
          ht.cmake_var('x.cmake', name)

  def test_only_literals_and_the_supported_expressions_are_read(self):
    self.assertEqual(ht.product('(8*1024*1024)', 'x'), 0x800000)
    self.assertEqual(ht.product('(0x98000U)', 'x'), 0x98000)
    self.assertEqual(ht.flash_addr('0x10000', None, 'x'), 0x10000)
    self.assertEqual(ht.flash_addr('(FLASH_BASE + 0xC000)', 0x60000000, 'x'), 0x6000C000)
    for expr, base in (('(FLASH_BASE + 0xC000)', None), ('(OTHER + 0xC000)', 0), ('FLASH_BASE - 4', 0), ('(1 << 20)', 0)):
      with self.subTest(expr), self.assertRaises(ht.Refused):
        ht.flash_addr(expr, base, 'x') if 'BASE' in expr or 'OTHER' in expr else ht.product(expr, 'x')

S3 = 'espressif_esp32s3_devkitc_1'
S3_PARTS = [('nvs', 1, 0x02, 0x9000, 0x5000), ('otadata', 1, 0x00, 0xe000, 0x2000), ('ota_0', 0, 0x10, 0x10000, 0x200000),
            ('ota_1', 0, 0x11, 0x210000, 0x200000), ('uf2', 0, 0x00, 0x410000, 0x40000), ('ffat', 1, 0x81, 0x450000, 0x3b0000)]


def s3_roster(tmp, **over):
  b = {'name': S3, 'uid': '84F703C084E4', 'flasher': {'name': 'esptool', 'uid': 'cp2102n', 'args': '--chip esp32s3'},
       'tinyuf2': {'reentry': 'dfu-detach'}}
  b.update(over)
  cfg = tmp / 'esp.json'
  cfg.write_text(json.dumps({'boards': [b]}))
  return cfg


def partition_table(rows):
  body = b''.join(b'\xaa\x50' + struct.pack('<BBII', t, st, off, size) + label.encode().ljust(16, b'\0') +
                  struct.pack('<I', 0) for label, t, st, off, size in rows)
  return body + b'\xeb\xeb' + b'\xff' * 14 + ht.hashlib.md5(body).digest() + b'\xff' * 32


def idf_build(root, parts=S3_PARTS, flash_args=None, sdk=None):
  """A synthetic IDF build of the S3 DevKitC as the port's CMakeLists lays it out, and its record row."""
  (root / '_bin').mkdir(parents=True)
  files = {'_bin/bootloader.bin': b'\xe9' + b'\0' * 0x5000,
           '_bin/tinyuf2.bin': b'\xe9' + b'TinyUF2 Bootloader 1.0\r\nBoard-ID: ESP32S3-DevKitC-v1.0\r\n' + b'\0' * 0x100,
           '_bin/partition-table.bin': partition_table(parts), '_bin/ota_data_initial.bin': b'\xff' * 0x2000,
           '_bin/flash_args': flash_args or ('--flash_mode dio --flash_freq 80m --flash_size 8MB\n0x0 bootloader/bootloader.bin\n'
                                             '0x410000 tinyuf2.bin\n0x8000 partition_table/partition-table.bin\n'
                                             '0xe000 ota_data_initial.bin\n'),
           'sdkconfig': sdk or ('CONFIG_IDF_TARGET="esp32s3"\nCONFIG_ESPTOOLPY_FLASHMODE="dio"\nCONFIG_ESPTOOLPY_FLASHFREQ="80m"\n'
                                'CONFIG_ESPTOOLPY_FLASHSIZE="8MB"\nCONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-8MB.csv"\n'
                                'CONFIG_PARTITION_TABLE_OFFSET=0x8000\n'),
           'flasher_args.json': '{}',
           '_bin/apps/dfu_runtime.uf2': ht.pack_uf2([(256 * i, bytes([i]) * 256) for i in range(3)], 0xc47e5767)}
  (root / '_bin' / 'apps').mkdir()
  for rel, data in files.items():
    (root / rel).write_bytes(data if isinstance(data, bytes) else data.encode())
  return {'board': S3, 'status': 'ok', 'backend': 'idf', 'buildDir': str(root),
          'sha256': {rel: ht.sha256(root / rel) for rel in files}}


class Esp(Tmp):
  """The S3 DevKitC entry: esptool by the CP2102N's serial, facts from the IDF port's own files."""

  def setUp(self):
    super().setUp()
    self.board = self.load(s3_roster(self.tmp), S3)
    self.facts = ht.source_facts(self.board)
    self.now = {'head': 'h', 'submodules': {}, 'deps': {}, 'dirty': False}

  def record(self, row, idf=None):
    rec = self.tmp / 'rec.json'
    rec.write_text(json.dumps({'pass': True, 'input': self.now, 'boards': [row],
                               'idf': idf or {'mode': 'docker', 'image': 'espressif/idf:v5.3.2'}}))
    return rec

  def verify(self, rec):
    with mock.patch.object(ht.cb, 'identity', lambda ports: self.now), \
         mock.patch.object(ht.cb, 'ci_idf_version', lambda: 'v5.3.2'):
      return ht.verify_record(rec, self.board, self.facts)

  def test_the_facts_come_from_the_idf_port(self):
    f = self.facts
    self.assertEqual((f['flashSize'], f['partitionCsv'], f['partitions']), (0x800000, 'partitions-8MB.csv', S3_PARTS))
    self.assertEqual((f['vid'], f['pid'], f['boardId'], f['family'], f['detectionDelayMs']),
                     (0x239a, 0x00a5, 'ESP32S3-DevKitC-v1.0', 0xc47e5767, 500))
    self.assertEqual((self.board['flasher'], self.board['probe'], self.board['device']), ('esptool', 'cp2102n', 'esp32s3'))

  def test_the_layout_names_what_an_install_writes_and_what_is_preserved(self):
    lay = self.board['regions']
    self.assertEqual(lay['install'], {'bootloader': (0, 0x8000), 'partition table': (0x8000, 0x9000),
                                      'otadata': (0xe000, 0x10000), 'factory': (0x410000, 0x450000)})
    self.assertEqual(lay['app'], (0x10000, 0x210000))
    self.assertEqual(lay['preserved'], {'nvs': (0x9000, 0xe000), 'ota_1': (0x210000, 0x410000),
                                        'ffat': (0x450000, 0x800000)})

  def test_layout_refusals(self):
    cases = {'overlap': S3_PARTS[:1] + [('otadata', 1, 0x00, 0xd000, 0x2000)] + S3_PARTS[2:],
             'past the flash': S3_PARTS[:5] + [('ffat', 1, 0x81, 0x450000, 0x400000)],
             'no factory': S3_PARTS[:4] + S3_PARTS[5:],
             'over the partition table': [('nvs', 1, 0x02, 0x8800, 0x5000)] + S3_PARTS[1:]}
    for what, parts in cases.items():
      with self.subTest(what), self.assertRaises(ht.esp.Refused):
        ht.esp.layout(dict(self.facts, partitions=parts), 'esp32s3')

  def test_roster_refusals(self):
    cases = {'not espressif': {'name': 'imxrt1060_evk'},
             'unknown chip': {'flasher': {'name': 'esptool', 'uid': 'x', 'args': '--chip esp32s2'}},
             'args': {'flasher': {'name': 'esptool', 'uid': 'x', 'args': '--chip esp32s3 -b 921600'}}}
    for what, over in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.load_board(s3_roster(self.tmp, **over), over.get('name', S3))

  def test_an_idf_record_gives_the_four_segments_at_their_regions(self):
    files, fw = self.verify(self.record(idf_build(self.tmp / 'b')))
    self.assertEqual([(off, p.name) for off, p in files['segments']],
                     [(0, 'bootloader.bin'), (0x8000, 'partition-table.bin'), (0xe000, 'ota_data_initial.bin'),
                      (0x410000, 'tinyuf2.bin')])
    self.assertEqual(fw['version'], '1.0')

  def test_idf_record_refusals(self):
    fa = ('--flash_mode dio --flash_freq 80m --flash_size 8MB\n0x0 bootloader/bootloader.bin\n0x410000 tinyuf2.bin\n'
          '0x8000 partition_table/partition-table.bin\n')
    cases = {
      'a local IDF': ({}, {'mode': 'local', 'image': 'espressif/idf:v5.3.2'}, 'CI\'s espressif/idf:v5.3.2 only'),
      'another image': ({}, {'mode': 'docker', 'image': 'espressif/idf:v5.4'}, 'only'),
      'a cmake build': ({'backend': 'cmake'}, None, 'idf builds only'),
      'a segment moved': ({'flash_args': fa.replace('0x410000', '0x400000') + '0xe000 ota_data_initial.bin\n'}, None,
                          'not at the start of its factory region'),
      'combined.bin flashed': ({'flash_args': fa + '0xe000 ota_data_initial.bin\n0x0 combined.bin\n'}, None, 'two segments'),
      'another file': ({'flash_args': fa + '0xd000 combined.bin\n'}, None, "'combined.bin' is not one of"),
      'an escaping path': ({'flash_args': fa.replace('0x0 bootloader/', '0x0 ../../x/') + '0xe000 ota_data_initial.bin\n'},
                           None, "'../../x/bootloader.bin' is not one of"),
      'a flat bootloader': ({'flash_args': fa.replace('0x0 bootloader/', '0x0 ') + '0xe000 ota_data_initial.bin\n'},
                            None, "'bootloader.bin' is not one of"),
      'a segment missing': ({'flash_args': fa}, None, 'not exactly'),
      'another flash size': ({'sdk': 'CONFIG_IDF_TARGET="esp32s3"\nCONFIG_ESPTOOLPY_FLASHSIZE="4MB"\n'}, None,
                             'differs from the candidate source'),
      'another partition table': ({'parts': S3_PARTS[:5] + [('ffat', 1, 0x81, 0x450000, 0x300000)]}, None,
                                  'partition-table.bin'),
    }
    for i, (what, (over, idf, err)) in enumerate(cases.items()):
      with self.subTest(what):
        build = {k: v for k, v in over.items() if k in ('flash_args', 'sdk', 'parts')}
        if 'parts' in build:
          build['parts'] = build['parts']
        row = idf_build(self.tmp / f'b{i}', **build)
        row.update({k: v for k, v in over.items() if k == 'backend'})
        with self.assertRaisesRegex(ht.Refused, err):
          self.verify(self.record(row, idf))

  def test_a_bound_file_that_changed_is_refused(self):
    row = idf_build(self.tmp / 'b')
    (self.tmp / 'b' / 'sdkconfig').write_text('changed')
    with self.assertRaisesRegex(ht.Refused, 'sdkconfig: hash differs'):
      self.verify(self.record(row))


FAKE_ESP = textwrap.dedent('''
  import hashlib, json, os, sys
  if '--boot-log' in sys.argv:
    print(json.dumps({'ok': True, 'results': [{'op': 'boot-log', 'text': 'invalid header: 0xffffffff\\n'}]})); sys.exit(0)
  args, ops = sys.argv[1:-1], json.load(open(sys.argv[-1]))
  img = os.environ['FAKE_ESP_FLASH']
  data = bytearray(open(img, 'rb').read())
  if os.environ.get('FAKE_ESP_FAIL'):
    print(json.dumps({'ok': False, 'error': os.environ['FAKE_ESP_FAIL'], 'results': []})); sys.exit(1)
  out = []
  for op in ops:
    k, r = op['op'], {'op': op['op']}
    if k in ('mac', 'expect-mac'):
      r['mac'] = os.environ.get('FAKE_ESP_MAC', '84F703C084E4')
      if k == 'expect-mac' and r['mac'] != op['mac']:
        print(json.dumps({'ok': False, 'error': 'RuntimeError: wrong MAC; nothing written', 'results': out})); sys.exit(1)
    elif k == 'security':
      flags = int(os.environ.get('FAKE_ESP_FLAGS', '0'))
      r.update(flags=flags, parsed={'SECURE_BOOT_EN': bool(flags & 1), 'SECURE_DOWNLOAD_ENABLE': bool(flags & 4)},
               flashCryptCnt=int(os.environ.get('FAKE_ESP_CRYPT', '0')), chipId=9, apiVersion=0)
    elif k == 'flash-size': r['flashSize'] = os.environ.get('FAKE_ESP_SIZE', '8MB')
    elif k == 'write':
      blob = open(op['file'], 'rb').read()
      if os.environ.get('FAKE_ESP_CORRUPT') == hex(op['addr']): blob = blob[:-1] + bytes([blob[-1] ^ 0xff])
      data[op['addr']:op['addr'] + len(blob)] = blob
      if os.environ.get('FAKE_ESP_SPILL') and op['addr'] == 0: data[0x9000] ^= 0xff
    elif k == 'read': open(op['file'], 'wb').write(bytes(data[op['addr']:op['addr'] + op['size']]))
    elif k == 'md5': r['md5'] = hashlib.md5(bytes(data[op['addr']:op['addr'] + op['size']])).hexdigest()
    elif k == 'erase': data[op['addr']:op['addr'] + op['size']] = b'\\xff' * op['size']
    out.append(r)
  if os.environ.get('FAKE_ESP_UNERASE'): data[0] = 0xe9
  open(img, 'wb').write(data)
  with open(img + '.sessions', 'a') as f: f.write(json.dumps({'args': args, 'ops': [o['op'] for o in ops]}) + '\\n')
  print(json.dumps({'ok': True, 'results': out}))
''')


class EspFake(Tmp):
  """A fake esptool session over an 8 MiB image: plumbing only, the rig is the evidence."""

  def setUp(self):
    super().setUp()
    self.board = self.load(s3_roster(self.tmp), S3)
    self.facts = ht.source_facts(self.board)
    self.flash = self.tmp / 'flash.img'
    self.flash.write_bytes(bytes(range(256)) * (0x800000 // 256))
    fake = self.tmp / 'fake_esp.py'
    fake.write_text(FAKE_ESP)
    self.segments = [(off, p) for off, p in ht.esp.admit(self.tmp / 'b', self.board, self.facts, self.board['regions'])] \
      if idf_build(self.tmp / 'b') else None
    for p in (mock.patch.object(ht, 'ESP_SESSION', fake), mock.patch.object(ht, 'esp_port', lambda uid: '/dev/fake'),
              mock.patch.dict(os.environ, {'FAKE_ESP_FLASH': str(self.flash)})):
      p.start()
      self.addCleanup(p.stop)
    self.work = self.tmp / 'run'
    self.work.mkdir()

  def sessions(self):
    return [json.loads(l) for l in (self.tmp / 'flash.img.sessions').read_text().splitlines()]


class EspFlash(EspFake):
  """The esptool install and invalidate."""

  def test_install_writes_the_segments_reads_them_back_and_keeps_the_preserved_regions(self):
    before = self.flash.read_bytes()
    ev = ht.esp_install(self.board, self.facts, self.segments, self.work)
    img = self.flash.read_bytes()
    for off, path in self.segments:
      self.assertEqual(img[off:off + path.stat().st_size], path.read_bytes())
    for lo, hi in self.board['regions']['preserved'].values():
      self.assertEqual(img[lo:hi], before[lo:hi])
    self.assertEqual(ev['mac'], '84F703C084E4')
    self.assertEqual(set(ev['preserved']), {'nvs', 'ota_1', 'ffat'})
    ident, prog = self.sessions()
    self.assertEqual(ident['ops'], ['mac', 'security', 'flash-size'])
    self.assertEqual(prog['ops'], ['expect-mac'] + ['md5'] * 3 + ['write'] * 4 + ['read'] * 4 + ['md5'] * 3)
    self.assertEqual(prog['args'][-1], 'hard-reset')
    self.assertIn('--chip', prog['args'])

  def test_identity_refusals_write_nothing(self):
    cases = {'another board': ({'FAKE_ESP_MAC': '000000000000'}, 'not the roster uid'),
             'secure boot': ({'FAKE_ESP_FLAGS': '1'}, 'security enabled'),
             'flash encryption': ({'FAKE_ESP_CRYPT': '1'}, 'security enabled'),
             'small flash': ({'FAKE_ESP_SIZE': '4MB'}, 'smaller than'),
             'a failed session': ({'FAKE_ESP_FAIL': 'No serial data received.'}, 'No serial data')}
    before = self.flash.read_bytes()
    for what, (env, err) in cases.items():
      with self.subTest(what), mock.patch.dict(os.environ, env), self.assertRaisesRegex(ht.StepFail, err):
        ht.esp_install(self.board, self.facts, self.segments, self.work)
      self.assertEqual(self.flash.read_bytes(), before)

  def test_a_bad_read_back_or_a_touched_preserved_region_fails_the_install(self):
    for env, err in (({'FAKE_ESP_CORRUPT': '0x410000'}, 'tinyuf2.bin at 0x410000 does not read back'),
                     ({'FAKE_ESP_SPILL': '1'}, 'preserved region changed during the install')):
      with self.subTest(err), mock.patch.dict(os.environ, env), self.assertRaisesRegex(ht.StepFail, err):
        ht.esp_install(self.board, self.facts, self.segments, self.work)

  def test_invalidate_erases_the_bootloader_sector_and_rereads_it_from_a_new_session(self):
    bat = mock.Mock(log=self.work / 'hil.log', tool=ht.Esptool(self.board, self.work, self.work / 'hil.log'))
    keep = self.board['regions']['preserved']
    bat.preserved = {'regions': keep, 'md5': ht.preserved_md5(keep, bat.tool.run(ht.preserved_ops(keep), 'no-reset'))}
    out = ht.invalidate(self.board, None, self.work, bat)
    self.assertEqual(self.flash.read_bytes()[:0x1000], b'\xff' * 0x1000)
    self.assertEqual(self.flash.read_bytes()[0x1000:0x2000], (bytes(range(256)) * 16))
    self.assertEqual((out['state'], out['evidence']['preserved']), ('bootloader invalidated', 'unchanged'))
    first, second = self.sessions()[1:]
    self.assertEqual((first['ops'], first['args'][-1]), (['expect-mac', 'erase', 'read'], 'no-reset'))
    self.assertEqual((second['ops'], second['args'][-1]), (['expect-mac', 'read', 'md5', 'md5', 'md5'], 'hard-reset'))
    self.assertEqual(out['evidence']['bootLog'], ['invalid header: 0xffffffff'])

  def test_invalidate_without_a_run_needs_no_layout(self):
    board = dict(self.board)
    del board['regions']
    out = ht.invalidate(board, None, self.work)
    self.assertNotIn('preserved', out['evidence'])
    self.assertEqual(self.sessions()[1]['ops'], ['expect-mac', 'read'])

  def test_invalidate_of_another_board_erases_nothing(self):
    before = self.flash.read_bytes()
    with mock.patch.dict(os.environ, {'FAKE_ESP_MAC': '000000000000'}), self.assertRaisesRegex(ht.StepFail, 'wrong MAC'):
      ht.invalidate(dict(self.board), None, self.work)
    self.assertEqual(self.flash.read_bytes(), before)

  def test_invalidate_fails_when_the_sector_comes_back_or_a_preserved_region_moved(self):
    with mock.patch.dict(os.environ, {'FAKE_ESP_UNERASE': '1'}), self.assertRaisesRegex(ht.StepFail, 'erased'):
      ht.invalidate(dict(self.board), None, self.work)
    bat = mock.Mock(log=self.work / 'hil.log', tool=ht.Esptool(self.board, self.work, self.work / 'hil.log'),
                    preserved={'regions': self.board['regions']['preserved'], 'md5': {'nvs': 'x', 'ota_1': 'y', 'ffat': 'z'}})
    with self.assertRaisesRegex(ht.StepFail, 'preserved region changed during the run'):
      ht.invalidate(self.board, None, self.work, bat)

  def test_a_recovery_checks_the_failed_runs_snapshot_without_a_layout(self):
    keep = self.board['regions']['preserved']
    md5 = ht.preserved_md5(keep, ht.Esptool(self.board, self.work, self.work / 'hil.log').run(ht.preserved_ops(keep), 'no-reset'))
    row = {'steps': [{'step': 'identity', 'pass': True,
                      'evidence': {'preserved': md5, 'preservedRegions': {n: list(r) for n, r in keep.items()}}}],
           'cleanup': {'state': 'unknown'}}
    snap = ht.report_snapshot(json.loads(json.dumps(row)))
    self.assertEqual(snap, {'regions': keep, 'md5': md5})
    board = dict(self.board)
    del board['regions']
    self.assertEqual(ht.invalidate(board, None, self.work, snapshot=snap)['evidence']['preserved'], 'unchanged')
    with self.assertRaisesRegex(ht.StepFail, 'preserved region changed during the run'):
      ht.invalidate(board, None, self.work, snapshot=dict(snap, md5=dict(md5, nvs='0' * 32)))

  def test_a_malformed_snapshot_is_refused_not_coerced(self):
    good = {'nvs': [0x9000, 0xe000]}, {'nvs': 'ab' * 16}
    cases = {'empty': ({}, {}), 'zero length': ({'nvs': [0x9000, 0x9000]}, good[1]),
             'reversed': ({'nvs': [0xe000, 0x9000]}, good[1]), 'fractional': ({'nvs': [0x9000, 57344.5]}, good[1]),
             'a bool': ({'nvs': [False, 0xe000]}, good[1]), 'short md5': (good[0], {'nvs': 'ab'}),
             'upper-case md5': (good[0], {'nvs': 'AB' * 16}), 'names differ': (good[0], {'ffat': 'ab' * 16}),
             'past 4 GiB': ({'nvs': [0x9000, 1 << 32]}, good[1])}
    for what, (regions, md5) in cases.items():
      row = {'steps': [{'step': 'identity', 'pass': True, 'evidence': {'preserved': md5, 'preservedRegions': regions}}],
             'cleanup': {'state': 'unknown'}}
      with self.subTest(what), self.assertRaisesRegex(ht.Refused, 'malformed'):
        ht.report_snapshot(json.loads(json.dumps(row)))

  def test_a_touched_run_without_a_snapshot_is_not_recovered(self):
    for state, want in (('unknown', ht.Refused), ('untouched', None)):
      row = {'steps': [{'step': 'identity', 'pass': False, 'evidence': {}}], 'cleanup': {'state': state}}
      with self.subTest(state):
        if want:
          with self.assertRaisesRegex(ht.Refused, 'no preserved-region snapshot'):
            ht.report_snapshot(row)
        else:
          self.assertIsNone(ht.report_snapshot(row))

  def test_the_bridge_is_found_by_serial_exactly_once(self):
    for hits in ([], ['/dev/serial/by-id/a_x-if00-port0', '/dev/serial/by-id/b_x-if00-port0']):
      with self.subTest(len(hits)), mock.patch.object(ht.glob, 'glob', lambda pat: hits), \
           self.assertRaisesRegex(ht.StepFail, f'{len(hits)} serial ports'):
        real_esp_port('x')

  def test_tty_users_sees_a_process_holding_the_device_open(self):
    dev = self.tmp / 'tty'
    dev.write_text('')
    p = subprocess.Popen([sys.executable, '-c', f'f = open({str(dev)!r}); import time; time.sleep(30)'])
    self.addCleanup(lambda: (p.kill(), p.wait()))
    ht.wait_for(lambda: p.pid in ht.tty_users(str(dev)), 5, 'the holder')

  def main(self, *argv):
    out = io.StringIO()
    with mock.patch.object(ht, 'load_helper', lambda path: mock.Mock()), mock.patch.object(ht, 'manual_holder', mock.Mock()), \
         mock.patch.object(ht.cb, 'BUILD_DIR', Path(tempfile.mkdtemp(dir=self.tmp))), contextlib.redirect_stdout(out):
      code = ht.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])

  def test_an_esptool_install_takes_a_build_record_and_a_run_only_esptool_steps_and_methods(self):
    cfg = str(s3_roster(self.tmp))
    code, res = self.main('install', '-b', S3, '--firmware', 'x.bin', '--sha256', 'y', '--under-hold', 'r', cfg)
    self.assertEqual(code, 2)
    self.assertIn('takes --build-record', res['error'])
    code, res = self.main('run', '-b', S3, '--build-record', 'rec.json', cfg)
    self.assertEqual(code, 2)
    self.assertIn('cannot read build record', res['error'])
    unset = str(s3_roster(self.tmp, tinyuf2={}))
    code, res = self.main('run', '-b', S3, '--build-record', 'rec.json', '--try-reentry', 'retained-register', unset)
    self.assertEqual(code, 2)
    self.assertIn("re-enters by one of ('dfu-detach',)", res['error'])

  def test_an_esptool_invalidate_under_hold_needs_no_candidate_source(self):
    with mock.patch.object(ht, 'source_facts', side_effect=AssertionError('read the source')), \
         mock.patch.object(ht, 'check_esptool', lambda: None), mock.patch.object(ht, 'tty_users', lambda dev: []):
      code, res = self.main('invalidate', '-b', S3, '--under-hold', 'r', str(s3_roster(self.tmp)))
    self.assertEqual(code, 0, res)
    self.assertEqual(res['results'][0]['cleanup']['state'], 'bootloader invalidated')
    self.assertEqual(self.flash.read_bytes()[:0x1000], b'\xff' * 0x1000)

  def test_the_esptool_version_is_gated(self):
    with mock.patch('importlib.metadata.version', lambda name: '4.8.1'), self.assertRaisesRegex(ht.Refused, '5.2.0'):
      ht.check_esptool()


STUB_ESPTOOL = {
  'esptool/__init__.py': "__version__ = '5.2.0'\n",
  'esptool/cmds.py': textwrap.dedent('''
    import json, os
    LOG = os.environ['STUB_LOG']
    def log(*a):
      open(LOG, 'a').write(json.dumps(a) + '\\n')
    class Port:
      def close(self): log('close')
    class Esp:
      CHIP_NAME = os.environ.get('STUB_CHIP', 'ESP32-S3')
      _port = Port()
      def read_mac(self, kind): return (0x7C, 0xDF, 0xA1, 0xE0, 0x6F, 0xD0)
      def get_security_info(self):
        return {'flags': 0, 'parsed_flags': {}, 'flash_crypt_cnt': 0, 'chip_id': 9, 'api_version': 0}
      def change_baud(self, b): log('baud', b)
      def read_flash(self, addr, size):
        if os.environ.get('STUB_FAIL_READ'): raise IOError('timed out')
        return bytes([addr & 0xff]) * size
      def flash_md5sum(self, addr, size): return f'md5-{addr:x}-{size:x}'
    def detect_chip(port, connect_mode):
      log('connect', port, connect_mode); return Esp()
    def run_stub(esp): log('stub'); return esp
    def attach_flash(esp): log('attach')
    def detect_flash_size(esp): return '8MB'
    def write_flash(esp, addr_data, flash_freq, flash_mode, flash_size):
      (addr, f), = addr_data
      log('write', addr, len(f.read()), flash_freq, flash_mode, flash_size)
    def erase_region(esp, addr, size): log('erase', addr, size)
    def reset_chip(esp, mode): log('reset', mode)
  '''),
  'serial/__init__.py': textwrap.dedent('''
    import json, os
    class Serial:
      def __setattr__(self, k, v):
        if k in ('dtr', 'rts', 'port'):
          open(os.environ['STUB_LOG'], 'a').write(json.dumps([k, v, getattr(self, 'opened', False)]) + '\\n')
        object.__setattr__(self, k, v)
      def open(self): self.opened = True
      def reset_input_buffer(self): pass
      def read(self, n): return b'invalid header' if not getattr(self, 'done', False) and not setattr(self, 'done', True) else b''
      def close(self): pass
  '''),
}


class EspRig:
  """TinyUF2 and apps/dfu_runtime as the host sees them: who is on the bus, the app partition TinyUF2
  writes from a copied UF2, and the string and DETACH the app answers."""
  def __init__(self, bat, spawn):
    self.bat, self.real_spawn, self.on, self.app, self.copied = bat, spawn, None, {}, []
    self.detach_leaves, self.stale = True, None

  def usb_device(self, vid, pid, serial):
    f = self.bat.f
    want = {'dfu': (f['vid'], f['pid']), 'app': (f['appVid'], f['appPid'])}.get(self.on)
    return '1-2' if (vid, pid) == want and serial == self.bat.b['uid'] else None

  def spawn(self, cmd, log, timeout, cwd=None):
    if cmd[0] == 'mcopy':
      blocks = ht.parse_uf2(Path(cmd[4]).read_bytes())
      self.copied.append(blocks)
      for bl in blocks:
        self.app[bl['addr']] = bl['data']
      # src/msc.c: the copy completes, and TinyUF2 resets, once every block of one numBlocks is written
      if {bl['total'] for bl in blocks} == {len(blocks)} and {bl['no'] for bl in blocks} == set(range(len(blocks))):
        self.on = 'app'
      return 0, ''
    if cmd[0] == 'sync':
      return 0, ''
    if str(cmd[2]) == str(ht.USB_DFU):
      if cmd[-1] == 'detach':
        self.on = 'dfu' if self.detach_leaves else 'app'
        return 0, json.dumps({'ok': True, 'interface': 0})
      blk = self.stale or self.app.get(self.bat.f['nonceOffset'], b'')
      return 0, json.dumps({'ok': True, 'interface': 0, 'string': f'HIL {blk[12:28].hex()}'})
    code, out = self.real_spawn(cmd, log, timeout, cwd)
    if 'hard-reset' in map(str, cmd) and any(o['op'] == 'write' for o in json.loads(Path(cmd[-1]).read_text())):
      self.on = 'dfu'   # blank otadata boots the factory app: TinyUF2
    return code, out

  def fat_read(self, dev, name, length, log, offset=0):
    f, size = self.bat.f, self.bat.dfu_flash
    if name == 'INFO_UF2.TXT':
      data = (f'TinyUF2 Bootloader v1\r\nModel: x\r\nBoard-ID: {f["boardId"]}\r\nDate: d\r\n'
              f'Flash Size: 0x{size:08X} bytes').encode()
    else:
      first, total = offset // 512, size // 256
      data = b''.join(struct.pack('<8I', *ht.UF2_MAGIC[:2], ht.UF2_FLAG_FAMILY, 256 * i, 256, i, total, f['family']) +
                      self.app.get(256 * i, b'\xff' * 256) + bytes(220) + struct.pack('<I', ht.UF2_MAGIC[2])
                      for i in range(first, first + length // 512))
    return {'entries': {'CURRENT.UF2': [9, size // 256 * 512]}, 'data': data, 'size': len(data)}


class EspBatteryRun(EspFake):
  """EspBattery.run over the fake esptool session and a fake bus and drive: the plumbing, not the rig."""

  def battery(self):
    bat = ht.EspBattery(self.board, self.facts, self.work)
    rig = EspRig(bat, ht.spawn)
    clock = [0.0]
    for p in (mock.patch.object(ht, 'usb_device', rig.usb_device),
              mock.patch.object(ht, 'block_device', lambda p: '/dev/sdz'),
              mock.patch.object(ht, 'check_exclusive', lambda d: None),
              mock.patch.object(ht, 'fat_read', rig.fat_read),
              mock.patch.object(ht, 'spawn', rig.spawn),
              mock.patch.object(ht.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s)),
              mock.patch.object(ht.time, 'monotonic', lambda: clock[0] + 1e-3)):
      p.start()
      self.addCleanup(p.stop)
    files = {'segments': self.segments, 'appChunks': ht.esp_app_chunks(self.tmp / 'b' / ht.esp.APP_UF2, self.facts, self.board)}
    return bat, rig, files

  def test_every_step_passes_with_a_fresh_nonce_per_copy(self):
    bat, rig, files = self.battery()
    bat.run(files, 'v1')
    self.assertEqual([x['step'] for x in bat.steps if x['pass']], list(ht.STEPS['esptool']))
    ev = {x['step']: x['evidence'] for x in bat.steps}
    self.assertEqual(ev['app-ran']['string'], f'HIL {ev["copy"]["nonce"]}')
    self.assertEqual(ev['recopy']['string'], f'HIL {ev["recopy"]["nonce"]}')
    self.assertNotEqual(ev['copy']['nonce'], ev['recopy']['nonce'])
    self.assertTrue(all(ev['reenter'][k] is True for k in ('detachAcked', 'appLeft', 'dfuCameUp', 'appIntact')))
    self.assertEqual(ev['dfu']['claim'], 'DFU observed')
    for blocks in rig.copied:
      self.assertEqual([(b['no'], b['total']) for b in blocks], [(i, len(blocks)) for i in range(len(blocks))])
      self.assertEqual((blocks[-1]['addr'], blocks[-1]['data'][:8]), (self.facts['nonceOffset'], b'TUF2NONC'))
    self.assertEqual(set(ev['identity']['preserved']), {'nvs', 'ota_1', 'ffat'})
    self.assertTrue(bat.touched)
    self.assertEqual(self.sessions()[0]['args'][-1], 'hard-reset')   # identity leaves an untouched board running

  def test_a_stale_nonce_fails_app_ran(self):
    bat, rig, files = self.battery()
    rig.stale = ht.nonce_block(bytes(16))
    with self.assertRaisesRegex(ht.StepFail, "does not report this copy's nonce"):
      bat.run(files, 'v1')
    self.assertEqual(bat.steps[-1]['step'], 'app-ran')

  def test_an_app_that_stays_after_detach_fails_reenter_before_any_readback(self):
    bat, rig, files = self.battery()
    rig.detach_leaves = False
    with self.assertRaisesRegex(ht.StepFail, 'the app leaving the bus'):
      bat.run(files, 'v1')
    ev = bat.steps[-1]['evidence']
    self.assertEqual((bat.steps[-1]['step'], ev.get('detachAcked'), 'failedAt' in ev), ('reenter', True, False))

  def test_a_nonce_block_that_does_not_read_back_fails_at_readback(self):
    bat, rig, files = self.battery()
    real = rig.fat_read
    def fat_read(dev, name, length, log, offset=0):
      if offset:
        rig.app[self.facts['nonceOffset']] = ht.nonce_block(bytes(16))
      return real(dev, name, length, log, offset)
    with mock.patch.object(ht, 'fat_read', fat_read), self.assertRaisesRegex(ht.StepFail, 'nonce block at 0x1f0000'):
      bat.run(files, 'v1')
    self.assertEqual(bat.steps[-1]['evidence']['failedAt'], 'readback')

  def test_app_chunks_refusals(self):
    uf2 = self.tmp / 'a.uf2'
    fam = self.facts['family']
    cases = {'a gap': [(0, bytes(256)), (0x200, bytes(256))], 'another family': None,
             'reaching the nonce block': [(256 * i, bytes(256)) for i in range(0x1F01)]}
    for what, chunks in cases.items():
      with self.subTest(what):
        uf2.write_bytes(ht.pack_uf2(chunks or [(0, bytes(256))], fam if chunks else 0x1234))
        with self.assertRaises(ht.Refused):
          ht.esp_app_chunks(uf2, self.facts, self.board)


class EspSession(Tmp):
  """esp_session.py itself, over stub esptool and pyserial packages: its dispatch, arguments, guard and reset
  order. The write and erase paths are only proven on the rig."""

  def setUp(self):
    super().setUp()
    stub = self.tmp / 'stub'
    for rel, text in STUB_ESPTOOL.items():
      (stub / rel).parent.mkdir(parents=True, exist_ok=True)
      (stub / rel).write_text(text)
    self.log = self.tmp / 'stub.log'
    self.env = dict(os.environ, PYTHONPATH=str(stub), STUB_LOG=str(self.log))

  def session(self, ops, after='hard-reset', **env):
    spec = self.tmp / 'ops.json'
    spec.write_text(json.dumps(ops))
    r = subprocess.run([sys.executable, '-B', ht.ESP_SESSION, '--port', '/dev/x', '--chip', 'esp32s3', '--baud', '921600',
                        '--after', after, spec], capture_output=True, text=True, env=dict(self.env, **env))
    calls = [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []
    self.log.unlink(missing_ok=True)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1]), calls

  def test_ops_run_in_order_in_one_connection_then_one_reset(self):
    blob = self.tmp / 'seg.bin'
    blob.write_bytes(b'\xe9' * 100)
    code, out, calls = self.session([{'op': 'expect-mac', 'mac': '7CDFA1E06FD0'}, {'op': 'security'}, {'op': 'flash-size'},
                                     {'op': 'write', 'addr': 0x8000, 'file': str(blob)},
                                     {'op': 'read', 'addr': 0x10, 'size': 4, 'file': str(self.tmp / 'r.bin')},
                                     {'op': 'md5', 'addr': 0x9000, 'size': 0x5000}, {'op': 'erase', 'addr': 0, 'size': 0x1000}])
    self.assertEqual(code, 0, out)
    self.assertEqual([r['op'] for r in out['results']], ['expect-mac', 'security', 'flash-size', 'write', 'read', 'md5', 'erase'])
    self.assertEqual((out['results'][0]['mac'], out['results'][2]['flashSize'], out['results'][5]['md5']),
                     ('7CDFA1E06FD0', '8MB', 'md5-9000-5000'))
    self.assertEqual((self.tmp / 'r.bin').read_bytes(), b'\x10' * 4)
    self.assertEqual([c[0] for c in calls], ['connect', 'stub', 'baud', 'attach', 'write', 'erase', 'reset', 'close'])
    self.assertEqual(calls[0][2], 'default-reset')
    self.assertEqual(calls[4], ['write', 0x8000, 100, 'keep', 'keep', 'keep'])
    self.assertEqual(calls[-2], ['reset', 'hard-reset'])

  def test_no_reset_leaves_the_chip_alone(self):
    code, out, calls = self.session([{'op': 'mac'}], after='no-reset')
    self.assertEqual(code, 0)
    self.assertNotIn('reset', [c[0] for c in calls])

  def test_a_wrong_mac_stops_before_any_later_op(self):
    code, out, calls = self.session([{'op': 'expect-mac', 'mac': '000000000000'}, {'op': 'erase', 'addr': 0, 'size': 0x1000}])
    self.assertEqual((code, out['ok']), (1, False))
    self.assertIn('not 000000000000; nothing written', out['error'])
    self.assertEqual([c[0] for c in calls], ['connect', 'stub', 'baud', 'attach', 'close'])

  def test_another_chip_and_a_failing_op_are_reported_and_the_port_closed(self):
    code, out, calls = self.session([{'op': 'mac'}], STUB_CHIP='ESP32-S2')
    self.assertEqual(code, 1)
    self.assertIn('not an esp32s3', out['error'])
    code, out, calls = self.session([{'op': 'mac'}, {'op': 'read', 'addr': 0, 'size': 1, 'file': str(self.tmp / 'x')}],
                                    STUB_FAIL_READ='1')
    self.assertEqual((code, [r['op'] for r in out['results']]), (1, ['mac']))
    self.assertIn('timed out', out['error'])
    self.assertEqual(calls[-1], ['close'])
    self.assertNotIn('reset', [c[0] for c in calls])

  def test_the_boot_log_releases_both_lines_before_open_and_pulses_rts(self):
    r = subprocess.run([sys.executable, '-B', ht.ESP_SESSION, '--port', '/dev/x', '--boot-log', '0.3'], capture_output=True,
                       text=True, env=self.env)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    self.assertEqual((r.returncode, out['results'][0]['text']), (0, 'invalid header'))
    lines = [json.loads(l) for l in self.log.read_text().splitlines()]
    self.assertEqual([l for l in lines if l[0] != 'port'], [['dtr', False, False], ['rts', False, False],
                                                             ['rts', True, True], ['rts', False, True]])


STUB_USB = {
  'usb/__init__.py': '',
  'usb/core.py': """import json, os

class Itf:
  def __init__(self, c, sub, proto, num, istr):
    self.bInterfaceClass, self.bInterfaceSubClass, self.bInterfaceProtocol = c, sub, proto
    self.bInterfaceNumber, self.iInterface = num, istr

class Dev:
  def __init__(self, d):
    self.d, self.bus, self.port_numbers, self.serial_number = d, d['bus'], tuple(d['ports']), d['serial']
  def get_active_configuration(self):
    return [Itf(*i) for i in self.d['itfs']]
  def ctrl_transfer(self, *a):
    with open(os.environ['STUB_LOG'], 'a') as f:
      f.write(json.dumps(list(a)) + '\\n')

def find(find_all, idVendor, idProduct):
  return [Dev(d) for d in json.loads(os.environ['STUB_USB']) if (d['vid'], d['pid']) == (idVendor, idProduct)]
""",
  'usb/util.py': """def get_string(dev, index):
  return dev.d['strings'][str(index)]
""",
}


class UsbDfu(Tmp):
  """usb_dfu.py over a stub pyusb: device selection, the interface it picks and the request it sends.
  The DETACH on a real device is proven only on the rig."""

  APP = {'vid': 0xCAFE, 'pid': 0x4000, 'bus': 3, 'ports': [1, 2], 'serial': '7CDFA1E06FD0',
         'itfs': [[0xFE, 1, 1, 2, 4]], 'strings': {'4': 'HIL 00ff'}}

  def call(self, op, devs, path='3-1.2'):
    stub = self.tmp / 'stub'
    for rel, text in STUB_USB.items():
      (stub / rel).parent.mkdir(parents=True, exist_ok=True)
      (stub / rel).write_text(text)
    log = self.tmp / 'usb.log'
    log.unlink(missing_ok=True)
    r = subprocess.run([sys.executable, '-B', ht.USB_DFU, '--vid', '0xcafe', '--pid', '0x4000', '--serial', '7CDFA1E06FD0',
                        '--path', path, op], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=str(stub), STUB_USB=json.dumps(devs), STUB_LOG=str(log)))
    calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1]), calls

  def test_string_and_detach_go_to_the_dfu_runtime_interface(self):
    other = dict(self.APP, ports=[1, 3], strings={'4': 'HIL other'})
    code, out, _ = self.call('string', [other, self.APP])
    self.assertEqual((code, out['string'], out['interface']), (0, 'HIL 00ff', 2))
    code, out, calls = self.call('detach', [self.APP])
    self.assertEqual(code, 0, out)
    self.assertEqual(calls, [[0x21, 0, 1000, 2, None, 1000]])

  def test_no_match_two_matches_or_no_dfu_interface_is_an_error_with_no_request(self):
    cases = {'another path': ([self.APP], '3-1.3', '0 devices'), 'two at one path': ([self.APP, self.APP], '3-1.2', '2 devices'),
             'no dfu interface': ([dict(self.APP, itfs=[[0xFF, 0, 0, 0, 0]])], '3-1.2', '0 DFU runtime interfaces')}
    for what, (devs, path, err) in cases.items():
      with self.subTest(what):
        code, out, calls = self.call('detach', devs, path)
        self.assertEqual((code, out['ok'], calls), (1, False, []))
        self.assertIn(err, out['error'])


real_esp_port = ht.esp_port


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
    lim = (0, 0x9D800)
    self.assertEqual(ht.check_ranges(data, [(0x10000, 0x98000)], lim, 'x'), (0x10000, 0x10002))
    with self.assertRaises(ht.Refused):
      ht.check_ranges(data, [(0, 0x10000)], lim, 'x')
    with self.assertRaises(ht.Refused):
      ht.check_ranges({0x9D7FF: 1, 0x9D800: 1}, [(0, 0x9E000)], lim, 'x')   # one byte over the ceiling
    self.assertEqual(ht.check_ranges({0x9D7FF: 1}, [(0, 0x9E000)], lim, 'x'), (0x9D7FF, 0x9D800))
    with self.assertRaises(ht.Refused):   # one byte under the floor, though inside the allowed span
      ht.check_ranges({0x5FFFFFFF: 1, 0x60000000: 1}, [(0x5FFF0000, 0x60010000)], (0x60000000, 0x60800000), 'x')

  def test_a_bad_checksum_is_refused(self):
    p = self.tmp / 'a.hex'
    p.write_text(':0100000000FE\n')
    with self.assertRaises(ht.Refused):
      ht.parse_hex(p)

  def test_bin_must_be_the_hex_laid_out_from_its_base(self):
    p, b = self.tmp / 'a.hex', self.tmp / 'a.bin'
    p.write_text(ihex([(0, 0, b'\x01\x02'), (0, 4, b'\x05')]))
    b.write_bytes(b'\x01\x02\xff\xff\x05')
    self.assertTrue(ht.hex_matches_bin(ht.parse_hex(p), b, 0))
    self.assertFalse(ht.hex_matches_bin(ht.parse_hex(p), b, 0x60000000))
    b.write_bytes(b'\x01\x02\xff\xff\x06')
    self.assertFalse(ht.hex_matches_bin(ht.parse_hex(p), b, 0))
    p.write_text(ihex([(4, 0, b'\x60\x00'), (0, 0, b'\x01\x02'), (0, 4, b'\x06')]))   # at 0x60000000
    self.assertTrue(ht.hex_matches_bin(ht.parse_hex(p), b, 0x60000000))

  def test_embedded_version(self):
    b = self.tmp / 'a.bin'
    b.write_bytes(b'\0junk TinyUF2 Bootloader 0.35.0-1-gabc - tinyusb (x)\r\nModel')
    self.assertEqual(ht.embedded_version(b), '0.35.0-1-gabc - tinyusb (x)')


class Exclusive(unittest.TestCase):
  def test_the_udev_property_gets_a_bounded_wait(self):
    seen = iter([False, False, True])
    with mock.patch.object(ht, 'udisks_ignored', lambda d: next(seen)), mock.patch.object(ht.time, 'sleep', lambda s: None), \
         mock.patch.object(ht, 'Path', lambda p: mock.Mock(read_text=lambda: '')):
      ht.check_exclusive('/dev/sdz')
    clock = [0.0]
    with mock.patch.object(ht, 'udisks_ignored', lambda d: False), \
         mock.patch.object(ht.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s)), \
         mock.patch.object(ht.time, 'monotonic', lambda: clock[0]), self.assertRaisesRegex(ht.StepFail, 'no UDISKS_IGNORE'):
      ht.check_exclusive('/dev/sdz')


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
    self.facts = dict(LPC_FACTS)
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
    self.assertEqual(ht.check_ranges(payload, [(0x10000, 0x98000)], (0, 0x9D800), 'uf2')[0], 0x10000)
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

  def test_an_offset_skips_whole_clusters_unread(self):
    fat = ht.Fat(self.vol(fat_image()))
    reads = []
    real = fat.read
    with mock.patch.object(fat, 'read', lambda off, n: reads.append(off) or real(off, n)):
      self.assertEqual(fat.file('CURRENT.UF2', 100, 512)[0], b'b' * 100)
    self.assertEqual(reads, [fat.root, fat.data + 1024])   # the directory and the one cluster; the FAT was read once
    for off in (100, 1536):
      with self.subTest(off), self.assertRaisesRegex(ValueError, 'not a cluster boundary'):
        fat.file('CURRENT.UF2', 100, off)

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


class Spawn(Tmp):
  def setUp(self):
    super().setUp()
    handler = signal.signal(signal.SIGTERM, ht.on_signal)
    mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, ht.TERM_SIGNALS)
    self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, mask)
    self.addCleanup(signal.signal, signal.SIGTERM, handler)

  def test_a_signal_right_after_the_child_starts_still_leaves_it_tracked_for_cleanup(self):
    real, launched = subprocess.Popen, []
    self.addCleanup(lambda: [(ht.reap(p), p.communicate()) for p in launched])

    def popen_then_signalled(*a, **k):
      launched.append(real(*a, **k))
      os.kill(os.getpid(), signal.SIGTERM)
      return launched[-1]
    with mock.patch.object(ht.subprocess, 'Popen', popen_then_signalled), \
         self.assertRaisesRegex(ht.Interrupted, 'SIGTERM'):
      ht.spawn([sys.executable, '-c', 'import time; time.sleep(30)'], self.tmp / 'log', 5)
    self.assertEqual(ht.CHILDREN, launched)
    self.assertEqual(ht.stuck_children(), [])   # reaped by SIGKILL, not left running
    self.assertIsNotNone(launched[0].poll())
    self.assertEqual(ht.CHILDREN, [])

  def test_registering_leaves_the_childs_signal_mask_alone(self):
    code, out = ht.spawn(['grep', 'SigBlk', '/proc/self/status'], self.tmp / 'log', 5)
    self.assertEqual(code, 0, out)
    self.assertFalse(int(out.split()[1], 16) & (1 << (signal.SIGTERM - 1)), out)


class Locks(Tmp):
  def setUp(self):
    super().setUp()
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())   # hand_off blocks SIGUSR1 in this process
    self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, mask)
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
    holder = ht.hand_off(fh, BOARD, 'cleanup failed', [{'pid': 99, 'start': 1, 'cmd': ['mcopy']}])
    self.addCleanup(lambda: _kill(holder['pid']))
    self.assertTrue(holder['ready'])
    self.assertNotIn('inProcess', holder)
    with self.assertRaises(OSError):
      self.helper.flock_nb(BOARD)
    rec = ht.prove_hold(self.helper, BOARD, holder['pid'], reason='hil_test.py', role=ht.HOLDER_ROLE)
    self.assertEqual((rec['detail'], rec['survivors'][0]['pid']), ('cleanup failed', 99))
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
          holder = ht.hand_off(fh, BOARD, 'cleanup failed')
        self.assertEqual((holder['pid'], holder.get('inProcess')), (parent, True))
        with self.assertRaises(OSError):
          self.helper.flock_nb(BOARD)
        rec = ht.prove_hold(self.helper, BOARD, parent, reason='hil_test.py', role=ht.HOLDER_ROLE)
        self.assertEqual(rec['detail'], 'cleanup failed')
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
      holder = ht.hand_off(fh, {BOARD!r}, 'cleanup failed')
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
      holder = ht.hand_off(fh, BOARD, 'cleanup failed')
    self.addCleanup(lambda: _kill(holder['pid']))
    os.kill(holder['pid'], signal.SIGUSR1)
    ht.wait_for(lambda: ht.flock_free(self.lock), 5, 'release')

  def test_one_recovery_per_board_and_tinyusb_never_lists_it_as_a_holder(self):
    first = ht.recovery_lock(self.helper, BOARD)
    with self.assertRaisesRegex(ht.Refused, 'another recovery holds'):
      ht.recovery_lock(self.helper, BOARD)
    self.helper.flock_nb(BOARD).close()   # the board lock itself stays free
    self.assertEqual(sorted(os.listdir(Path(self.lock).parent)), [f'{BOARD}.lock', f'{BOARD}.lock.recover'])
    first.close()
    ht.recovery_lock(self.helper, BOARD).close()

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
  """The state machine around the battery: who cleans up, and what is left held."""

  def setUp(self):
    super().setUp()
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    handlers = {sig: signal.getsignal(sig) for sig in ht.TERM_SIGNALS}

    def unblock():   # run_board leaves the signals blocked until exit; drop what is pending, then put the mask back
      for sig in ht.TERM_SIGNALS:
        signal.signal(sig, signal.SIG_IGN)
      signal.pthread_sigmask(signal.SIG_SETMASK, mask)
      for sig, h in handlers.items():
        signal.signal(sig, h)
    self.addCleanup(unblock)
    (self.tmp / 'hil_lock.py').write_text(FAKE_HELPER.format(dir=str(self.tmp / 'locks')))
    self.helper = ht.load_helper(self.tmp / 'hil_lock.py')
    self.board = self.load(roster(self.tmp))
    self.facts = ht.source_facts(self.board)
    self.args = mock.Mock(build_record='rec.json', fail_at=None, try_reentry=None)
    for p in (mock.patch.object(ht, 'verify_record', lambda *a: ({'hex': 'x.hex', 'bin': 'x.bin'}, {'version': 'v'})),
              mock.patch.object(ht, 'parse_hex', lambda p: {0: 1}),
              mock.patch.object(ht, 'hex_matches_bin', lambda d, b, base: True),
              mock.patch.object(ht, 'check_jlink', lambda: None),
              mock.patch.object(ht, 'check_bootloader_bin', lambda *a: None),
              mock.patch.object(ht, 'exclusion_configured', lambda *a: None),
              mock.patch.object(ht.shutil, 'which', lambda t: '/usr/bin/' + t)):
      p.start()
      self.addCleanup(p.stop)

  def run_board(self, battery_run, cleanup_error=None):
    cleaned = []

    def fake_invalidate(*a, **k):
      cleaned.append(True)
      if cleanup_error:
        raise cleanup_error
      return {'pass': True, 'state': 'bootloader invalidated', 'evidence': {}}
    with mock.patch.object(ht.Battery, 'run', battery_run), mock.patch.object(ht, 'invalidate', fake_invalidate):
      row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
    return row, code, cleaned

  def test_pass_cleans_up_and_releases(self):
    def ok(bat, files, version):
      bat.touched = True
    row, code, cleaned = self.run_board(ok)
    self.assertEqual((code, row['pass'], cleaned, row['cleanup']['heldAfter']), (0, True, [True], False))
    self.helper.flock_nb(BOARD).close()

  def test_a_failed_step_after_touching_cleans_up_and_is_exit_1(self):
    def fail(bat, files, version):
      bat.touched = True
      bat.step('app-ran', lambda: (_ for _ in ()).throw(ht.StepFail('pc not in the loop')))
    row, code, cleaned = self.run_board(fail)
    self.assertEqual((code, row['pass'], cleaned), (1, False, [True]))
    self.assertIn('app-ran', row['detail'])

  def test_an_untouched_board_is_not_cleaned_up(self):
    def fail(bat, files, version):
      raise ht.StepFail('probe not found')
    row, code, cleaned = self.run_board(fail)
    self.assertEqual((code, cleaned, row['cleanup']), (1, [], None))

  def test_any_failed_cleanup_hands_the_lock_to_a_holder_and_is_exit_4(self):
    def fail(bat, files, version):
      bat.touched = True
      raise ht.StepFail('x')
    for err in (ht.StepFail('verify failed'), ht.Refused('range'), ValueError('parse'), ht.Interrupted('TERM')):
      with self.subTest(type(err).__name__), \
           mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1, 'reason': 'hil_test.py'})[1]):
        row, code, _ = self.run_board(fail, cleanup_error=err)
        self.assertEqual((code, row['pass'], row['cleanup']['heldAfter'], row['cleanup']['holder']['pid']),
                         (4, False, True, 1))

  def test_a_step_or_method_of_the_other_flasher_is_refused_before_the_lock(self):
    for attr, val, err in (('fail_at', 'recopy', 'has no step recopy'), ('try_reentry', 'dfu-detach', 're-enters by one of')):
      with self.subTest(val), mock.patch.object(self.args, attr, val), self.assertRaisesRegex(ht.Refused, err):
        ht.run_board(self.args, dict(self.board, reentry=None), self.facts, self.helper, self.tmp)

  def test_fail_at_cleanup_skips_the_invalidate_and_hands_the_board_to_a_holder(self):
    def ok(bat, files, version):
      bat.touched = True
    self.args.fail_at = 'cleanup'
    with mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1, 'reason': 'hil_test.py'})[1]):
      row, code, cleaned = self.run_board(ok)
    self.assertEqual((code, cleaned, row['cleanup']['heldAfter']), (4, [], True))
    self.assertIn('--fail-at cleanup', row['cleanup']['detail'])

  def test_try_reentry_is_for_an_uncommissioned_board_only_and_reports_its_decision(self):
    self.args.try_reentry = 'retained-register'
    with self.assertRaisesRegex(ht.Refused, 'already commissioned'):
      self.run_board(lambda *a: self.fail('ran'))
    self.board['reentry'] = None

    def ok(bat, files, version):
      self.assertEqual((bat.b['reentry'], bat.commissioning), ('retained-register', True))
      bat.touched = True
      bat.steps.append({'step': 'reenter', 'pass': True, 'evidence': {
        'controlBootedApp': True, 'dfuCameUp': True, 'magicConsumed': True}})
    row, code, _ = self.run_board(ok)
    self.assertEqual((code, row['commissioning'], row['reentryDecision']), (0, True, 'retained-register'))

  def test_an_uncommissioned_board_is_refused_before_the_lock(self):
    self.board['reentry'] = None
    with self.assertRaisesRegex(ht.Refused, 'commissioning'):
      self.run_board(lambda *a: self.fail('ran'))
    self.assertFalse(Path(self.helper.lock_path(BOARD)).exists())

  def test_a_signal_during_cleanup_waits_for_it(self):
    def ok(bat, files, version):
      bat.touched = True

    def invalidate_then_signalled(*a, **k):
      os.kill(os.getpid(), signal.SIGTERM)   # blocked until cleanup has ended
      return {'pass': True, 'state': 's', 'evidence': {}}

    signal.signal(signal.SIGTERM, ht.on_signal)
    with mock.patch.object(ht.Battery, 'run', ok), mock.patch.object(ht, 'invalidate', invalidate_then_signalled):
      row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
    self.assertEqual((code, row['pass'], row['cleanup']['heldAfter']), (0, True, False))
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

  def test_a_stuck_child_is_a_cleanup_failure_with_no_invalidate(self):
    def fail(bat, files, version):
      bat.touched = True
      raise ht.StepFail('x')
    stuck = [{'pid': 99, 'start': 7, 'cmd': ['JLinkExe']}]
    with mock.patch.object(ht, 'stuck_children', lambda: list(stuck)), \
         mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1, 'survivors': s})[1]):
      row, code, cleaned = self.run_board(fail)
    self.assertEqual((code, cleaned, row['cleanup']['survivors']), (4, [], stuck))
    self.assertIn('99', row['cleanup']['detail'])

  def test_a_survivor_on_an_untouched_board_still_keeps_it_held(self):
    def fail(bat, files, version):
      raise ht.StepFail('identity: probe hung')
    with mock.patch.object(ht, 'stuck_children', lambda: [{'pid': 99, 'start': 7, 'cmd': ['JLinkExe']}]), \
         mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1})[1]):
      row, code, cleaned = self.run_board(fail)
    self.assertEqual((code, cleaned, row['cleanup']['state'], row['cleanup']['heldAfter']),
                     (4, [], 'untouched', True))

  def test_repeated_signals_interrupt_the_battery_but_never_the_cleanup(self):
    signal.signal(signal.SIGTERM, ht.on_signal)

    def interrupted(bat, files, version):
      bat.touched = True
      os.kill(os.getpid(), signal.SIGTERM)
      self.fail('the signal did not interrupt the battery')

    def invalidate_under_fire(*a, **k):
      for _ in range(3):
        os.kill(os.getpid(), signal.SIGTERM)
      return {'pass': True, 'state': 's', 'evidence': {}}
    with mock.patch.object(ht.Battery, 'run', interrupted), mock.patch.object(ht, 'invalidate', invalidate_under_fire):
      row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
    self.assertEqual((code, row['cleanup']['pass'], row['cleanup']['heldAfter']), (1, True, False))
    self.assertIn('interrupted by SIGTERM', row['detail'])
    self.assertIn('SIGTERM deferred', row['detail'])
    self.helper.flock_nb(BOARD).close()

  def test_an_abort_names_the_step_it_cut_short_and_records_no_failing_step(self):
    def cut_short(bat, files, version):
      bat.touched = True
      bat.step('dfu', lambda: {})
      bat.step('copy', lambda: (_ for _ in ()).throw(ht.Interrupted('interrupted by SIGTERM')))
    row, code, cleaned = self.run_board(cut_short)
    self.assertEqual((code, cleaned, [s['pass'] for s in row['steps']]), (1, [True], [True]))
    self.assertTrue(row['detail'].startswith('copy: Interrupted: interrupted by SIGTERM'), row['detail'])

  def test_a_locked_board_is_not_touched(self):
    held = self.helper.acquire_board_lock(BOARD, reason='someone')
    self.addCleanup(held.close)
    row, code, cleaned = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['locked'], row['ran'], cleaned), (1, True, False, []))

  def test_the_board_is_locked_and_reported_under_its_lock_name(self):
    self.board = self.load(roster(self.tmp, tinyuf2={'lock': 'tinyusb_name'}))
    held = self.helper.acquire_board_lock('tinyusb_name', reason='someone')
    self.addCleanup(held.close)
    row, code, _ = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['board'], row['lock'], row['locked']), (1, BOARD, 'tinyusb_name', True))

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
    self.r0, self.mem, self.double_reset, self.flash = 5, {}, False, set()

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
        v = f['appStart'] if a == ht.SCB_VTOR else self.mem.get(a, 0)
        out += f'J-Link>{c}\n{a:08X} = {v:08X} \n'
      elif c.startswith(f'w4 {ht.SCB_AIRCR:08X}'):
        # DFU only with the magic retained, or when a second reset lands in the bootloader's own window
        self.present = self.mem.pop(f['dblTapReg'], None) == f['dblTapMagic'] or self.double_reset
      elif c == 'r' and self.reentry == 'app-invalidate':
        self.present = True
      elif c.startswith('w4 '):
        _, a, v = c.split()
        self.mem[int(a, 16)] = int(v, 16)
      elif c.startswith('loadbin '):
        note = 'Skipped. Contents already match' if c in self.flash else '1 range affected (65536 bytes)'
        self.flash.add(c)
        out += f'J-Link>{c}\nJ-Link: Flash download: Bank 0 @ 0x60000000: {note}\nO.K.\n'
    return out

  def spawn(self, cmd, log, timeout, cwd=None):
    if cmd[0] == 'mcopy':
      self.present = False
    return 0, ''

  def fat_read(self, dev, name, length, log, offset=0):
    f = self.bat.f
    if name == 'INFO_UF2.TXT':
      data = (f'TinyUF2 Bootloader v1\r\nModel: x\r\nBoard-ID: {f["boardId"]}\r\nDate: d\r\n'
              f'Flash Size: 0x{f["flashSize"]:08X} bytes').encode()
    else:
      data = ht.make_uf2(bytes(self.current), f['appStart'], f['family'], self.bat.dir / 'cur')[1].read_bytes()[:length]
    return {'entries': {'CURRENT.UF2': [9, f['flashSize'] // 256 * 512]}, 'data': data, 'size': len(data)}


class BatteryRun(Tmp):
  """Battery.run end to end over a fake probe transcript and a fake drive: the plumbing, not the rig."""

  def battery(self, reentry='retained-register', corrupt=None, commissioning=False):
    board = self.load(roster(self.tmp, tinyuf2={'reentry': reentry}))
    facts = ht.source_facts(board)
    bat = ht.Battery(board, facts, self.tmp, commissioning=commissioning)
    bootloader_bin(self.tmp / 'c.bin')
    rig = FakeRig(bat, reentry)
    (self.tmp / 'cur').mkdir()
    bat.probe.run = rig.probe
    clock = [0.0]   # time passes only when the battery sleeps

    def fat_read(*a):
      if a[1] == 'CURRENT.UF2':
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
              mock.patch.object(ht.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s)),
              mock.patch.object(ht.time, 'monotonic', lambda: clock[0] + 1e-3)):
      p.start()
      self.addCleanup(p.stop)
    return bat, rig

  def test_every_step_passes_and_resumes_only_after_a_halt(self):
    for reentry in ht.REENTRY['jlink']:
      with self.subTest(reentry):
        self.tmp = Path(tempfile.mkdtemp(dir=self.tmp))
        bat, rig = self.battery(reentry)
        bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
        self.assertEqual([x['step'] for x in bat.steps if x['pass']], list(ht.STEPS['jlink']))
        image = self.tmp / 'program.bin'
        self.assertEqual(rig.scripts[1], ['h', f'loadbin {image},0x0', f'verifybin {image},0x0', 'r', 'g'])
        self.assertEqual(rig.scripts[2][:2], ['h', f'w4 {bat.f["dblTapReg"]:08X} 00000000'])   # cleared in dfu
        self.assertIn(f'sleep {2 * bat.f["dblTapDelayMs"] + 200}', rig.scripts[3])
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

  def test_a_readback_failure_keeps_the_reentry_observations(self):
    for what, corrupt, fat in (('mismatch', lambda img: img.__setitem__(0, img[0] ^ 1), None),
                               ('not UF2', None, lambda: bytes(1024)),   # the empty CURRENT.UF2 suspected on RT1060
                               ('truncated', None, lambda: ht.make_uf2(b'x' * 256, 0x10000, 1, self.tmp)[1].read_bytes() + b'x')):
      with self.subTest(what):
        self.tmp = Path(tempfile.mkdtemp(dir=self.tmp))
        bat, rig = self.battery(corrupt=corrupt)
        if fat:
          read = ht.fat_read
          ht.fat_read = lambda *a: dict(read(*a), data=fat()) if a[1] == 'CURRENT.UF2' else read(*a)
          self.addCleanup(setattr, ht, 'fat_read', read)
        with self.assertRaises(ht.StepFail):
          bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
        last = bat.steps[-1]
        self.assertEqual((last['step'], last['pass'], last['evidence']['failedAt']), ('reenter', False, 'readback'))
        self.assertTrue(last['evidence']['dfuCameUp'] and last['evidence']['magicConsumed'])
        self.assertEqual((last['evidence']['appIntact'], last['evidence']['claim']),
                         ('unshown', 'the write/reset sequence re-entered DFU (register retention inferred)'))

  def test_commissioning_runs_the_control_first_and_no_probe_session_before_dfu(self):
    bat, rig = self.battery(commissioning=True)
    dfu = bat.dfu
    bat.dfu = lambda v: rig.scripts.append('dfu observed') or dfu(v)
    bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
    ev = bat.steps[-1]['evidence']
    self.assertTrue(ev['controlBootedApp'] and ev['dfuCameUp'] and ev['magicConsumed'])
    aircr = [f'w4 {ht.SCB_AIRCR:08X} {ht.AIRCR_SYSRESETREQ:08X}']
    reenter = rig.scripts[rig.scripts.index(aircr):]
    self.assertEqual(reenter[0], aircr)                    # the control: no magic written before it
    self.assertIn('regs', reenter[1])                      # the app observed again
    self.assertEqual(reenter[2][1], f'w4 {bat.f["dblTapReg"]:08X} {bat.f["dblTapMagic"]:08X}')
    self.assertEqual(reenter[3:5], [aircr, 'dfu observed'])   # nothing opens the probe in between

  def test_a_failure_after_the_control_keeps_what_was_observed(self):
    bat, rig = self.battery(commissioning=True)
    dfu, calls = bat.dfu, []

    def flaky(v):   # the install's DFU passes; the re-entry's finds no exclusion property
      calls.append(v)
      if len(calls) > 1:
        raise ht.StepFail('/dev/sdz has no UDISKS_IGNORE=1')
      return dfu(v)
    bat.dfu = flaky
    with self.assertRaises(ht.StepFail):
      bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
    ev = bat.steps[-1]['evidence']
    self.assertEqual((bat.steps[-1]['step'], ev['controlBootedApp'], 'dfuCameUp' in ev), ('reenter', True, False))

  def test_a_control_that_lands_in_dfu_fails_without_a_decision(self):
    bat, rig = self.battery(commissioning=True)
    rig.double_reset = True
    with self.assertRaisesRegex(ht.StepFail, 'without the magic'):
      bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
    self.assertIs(bat.steps[-1]['evidence']['controlBootedApp'], False)

  def test_one_image_carries_the_bootloader_ff_padding_and_a_zero_page(self):
    bat, rig = self.battery()
    fw = bootloader_bin(self.tmp / 'fw.bin', size=0x5000)
    bat.program(fw, 0, 0x10000)
    image = (self.tmp / 'program.bin').read_bytes()
    self.assertEqual(image, fw.read_bytes() + b'\xff' * 0xb000 + bytes(512))
    self.assertEqual(rig.scripts, [['h', f'loadbin {self.tmp / "program.bin"},0x0',
                                    f'verifybin {self.tmp / "program.bin"},0x0', 'r', 'g']])
    self.assertEqual(bat.installed, (fw, 0))   # app-invalidate re-verifies the BIN, not the image

  def test_a_bin_that_fills_the_install_span_exactly_has_no_padding(self):
    bat, _ = self.battery()
    fw = bootloader_bin(self.tmp / 'fw.bin', size=0x10000)
    bat.program(fw, 0, 0x10000)
    self.assertEqual((self.tmp / 'program.bin').read_bytes(), fw.read_bytes() + bytes(512))

  def test_a_bin_past_the_app_start_is_refused_before_any_probe_session(self):
    bat, rig = self.battery()
    fw = bootloader_bin(self.tmp / 'fw.bin', size=0x10001)
    with self.assertRaisesRegex(ht.StepFail, 'overlaps the app start'):
      bat.program(fw, 0, 0x10000)
    self.assertEqual((rig.scripts, bat.touched), ([], False))

  def test_cleanup_zeroes_the_device_flash_floor_and_reverifies_it_from_a_new_session(self):
    bat, rig = self.battery()
    b = dict(bat.b, device='MIMXRT1062xxx6A')   # the floor is the device's, never the candidate's layout
    out = ht.invalidate(b, bat.f, self.tmp, bat)
    zero = f'{bat.zero},0x60000000'
    self.assertEqual(rig.scripts, [['h', f'loadbin {zero}', f'verifybin {zero}', 'r', 'g'],
                                   ['h', f'loadbin {zero}', f'verifybin {zero}', 'g']])
    self.assertEqual((out['state'], out['evidence']), ('bootloader invalidated', {'zeroPage': '0x60000000', 'verified': True}))

  def test_cleanup_fails_when_the_new_session_has_to_write_the_zero_page_again(self):
    bat, rig = self.battery()
    b = dict(bat.b, device='MIMXRT1062xxx6A')
    bat.probe.run = lambda commands, judge=True: rig.flash.clear() or rig.probe(commands, judge)
    with self.assertRaisesRegex(ht.StepFail, 'did not persist'):
      ht.invalidate(b, bat.f, self.tmp, bat)

  def test_app_invalidate_reverifies_the_bootloader_before_its_reset(self):
    bat, rig = self.battery('app-invalidate')
    bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
    script = [x for x in rig.scripts if 'r' in x][-1]
    self.assertLess(script.index(f'verifybin {self.tmp / "c.bin"},0x0'), script.index('r'))
    self.assertTrue(bat.steps[-1]['evidence']['bootloaderVerified'])

  def test_a_wrong_version_on_the_drive_fails_dfu(self):
    bat, _ = self.battery()
    with self.assertRaisesRegex(ht.StepFail, 'INFO_UF2'):
      bat.run({'bin': self.tmp / 'c.bin'}, 'v2')

  def test_a_left_magic_is_cleared_right_after_dfu_and_read_back(self):
    bat, rig = self.battery()
    reg = bat.f['dblTapReg']
    rig.mem[reg] = bat.f['dblTapMagic']
    dfu = bat.dfu
    bat.dfu = lambda v: rig.scripts.append('dfu observed') or dfu(v)
    bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
    ev = [x for x in bat.steps if x['step'] == 'dfu'][0]['evidence']
    self.assertEqual(ev['dblTapReg'], '0x0')
    self.assertEqual(rig.scripts[2:4], ['dfu observed', ['h', f'w4 {reg:08X} 00000000', f'mem32 {reg:08X} 1', 'g']])

  def test_a_double_tap_clear_that_does_not_read_back_fails_dfu(self):
    bat, rig = self.battery()
    real = rig.probe
    rig.probe = lambda commands, judge=True: real([c for c in commands if not c.startswith('w4 ')], judge)
    bat.probe.run = rig.probe
    rig.mem[bat.f['dblTapReg']] = bat.f['dblTapMagic']
    with self.assertRaisesRegex(ht.StepFail, 'reads back'):
      bat.run({'bin': self.tmp / 'c.bin'}, 'v1')
    self.assertEqual([(x['step'], x['pass']) for x in bat.steps][-1], ('dfu', False))

  def test_a_write_the_bus_dropped_fails_its_read_back(self):
    bat, rig = self.battery()
    rig.probe = lambda commands, judge=True: f'J-Link>mem32 4002C05C 1\n4002C05C = 00000000 \n'
    bat.probe.run = rig.probe
    with self.assertRaisesRegex(ht.StepFail, 'reads back 00000000'):
      bat.probe.write32(0x4002C05C, 0xF01669EF)

  def test_the_rt1062_missing_reset_vector_note_passes_only_with_its_completed_reset(self):
    note = 'J-Link>r\nResetTarget() start\nCould not find valid reset vector.\nTarget halted on flash header read.\nJ-Link>g\n'
    rt = ht.Probe({'probe': '1', 'device': 'MIMXRT1062xxx6A', 'if': 'SWD', 'speed': '4000'}, self.tmp, None)
    other = ht.Probe({'probe': '1', 'device': 'LPC55S69_M33_0', 'if': 'SWD', 'speed': '4000'}, self.tmp, None)
    with mock.patch.object(ht, 'spawn', lambda *a, **k: (0, note)):
      rt.run(['r', 'g'])
    for probe, out in ((rt, note + 'Could not read memory.\n'),                               # another failure beside it
                       (rt, note.replace('Target halted on flash header read.\n', '')),       # reset not seen completing
                       (other, note)):                                                        # another device
      with self.subTest(out[-40:]), mock.patch.object(ht, 'spawn', lambda *a, o=out, **k: (0, o)), \
           self.assertRaisesRegex(ht.StepFail, 'JLinkExe failed'):
        probe.run(['r', 'g'])

  def test_only_the_probe_connect_crash_is_retried_once_and_any_crash_fails(self):
    probe = ht.Probe({'probe': '000726129165', 'device': 'd', 'if': 'SWD', 'speed': '4000'}, self.tmp, self.tmp / 'hil.log')
    banner = 'Connecting to J-Link ...O.K.\nFirmware: J-Link LPCXpresso V2\nS/N: 726129165\n'
    segv, abort = (-11, banner), (-6, banner + 'double free or corruption (top)\n')
    ok = (0, 'J-Link>exit\n')
    cases = (([segv, ok], True, 1), ([abort, ok], True, 1),
             ([segv, segv], False, 1),                                              # retried once only
             ([(-9, ''), ok], False, 0),                                            # no transcript: state unknown
             ([(-11, banner + 'VTref=3.300V\n'), ok], False, 0),                    # past the probe connect
             ([(-11, banner.replace('726129165', '1')), ok], False, 0),             # another probe's serial
             ([(-11, banner + 'Connecting to target via SWD\n'), ok], False, 0))
    for outcomes, passes, retries in cases:
      for judge in (True, False):
        calls = iter(outcomes)
        probe.retried.clear()
        with self.subTest(outcomes=outcomes, judge=judge), mock.patch.object(ht, 'JLINK_RETRY_DELAY', 0), \
             mock.patch.object(ht, 'spawn', lambda *a, **k: next(calls)):
          if passes:
            probe.run(['h'], judge=judge)
          else:
            with self.assertRaisesRegex(ht.StepFail, r'exit -\d+'):
              probe.run(['h'], judge=judge)
          self.assertEqual(len(probe.retried), retries)

  def test_a_failed_reset_fails_the_session(self):
    out = 'J-Link>r\nResetTarget failed (-1).\nFailed to halt CPU.\nJ-Link>g\n\n****** Error: CPU is not halted\n'
    probe = ht.Probe({'probe': '1', 'device': 'd', 'if': 'SWD', 'speed': '4000'}, self.tmp, None)
    with mock.patch.object(ht, 'spawn', lambda *a, **k: (0, out)), self.assertRaisesRegex(ht.StepFail, 'JLinkExe failed'):
      probe.run(['r', 'g'])


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


class Decision(unittest.TestCase):
  def row(self, tried='retained-register', passed=True, failed_at=None, cleaned=True, held=False, **obs):
    ev = {'controlBootedApp': True, 'dfuCameUp': True, 'magicConsumed': True, 'bootloaderVerified': True,
          'detachAcked': True, 'appLeft': True}
    ev.update(obs)
    if failed_at:
      ev['failedAt'] = failed_at
    steps = [{'step': s, 'pass': True, 'evidence': {}} for s in ht.STEPS['jlink'][:-1]]
    steps.append({'step': 'reenter', 'pass': passed, 'evidence': ev})
    return {'commissioning': True, 'tried': tried, 'pass': passed, 'steps': steps,
            'cleanup': {'pass': cleaned, 'heldAfter': held}}

  def test_the_commissioning_decision(self):
    for method in (*ht.REENTRY['jlink'], *ht.REENTRY['esptool']):
      with self.subTest(method):
        self.assertEqual(ht.reentry_decision(self.row(method)), method)
        self.assertEqual(ht.reentry_decision(self.row(method, passed=False, failed_at='readback')), method)
        self.assertIsNone(ht.reentry_decision(self.row(method, passed=False)))            # failed entry
        self.assertIsNone(ht.reentry_decision(self.row(method, dfuCameUp=False)))
        self.assertIsNone(ht.reentry_decision(self.row(method, cleaned=False)))           # failed cleanup
        self.assertIsNone(ht.reentry_decision(self.row(method, held=True)))
    self.assertIsNone(ht.reentry_decision(self.row(controlBootedApp=False)))
    self.assertEqual(ht.reentry_decision(self.row('app-invalidate', controlBootedApp=False)), 'app-invalidate')
    early = self.row(passed=False, failed_at='readback')
    early['steps'][3]['pass'] = False
    self.assertIsNone(ht.reentry_decision(early))                                          # another step failed too
    self.assertIsNone(ht.reentry_decision(dict(self.row(), commissioning=False)))
    self.assertIsNone(ht.reentry_decision(dict(self.row(), **{'pass': False})))   # aborted after every step passed


class Main(Tmp):
  def test_manual_install_needs_no_reentry_and_programs_the_bin_with_a_zero_page(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    fw = bootloader_bin(self.tmp / 'fw.bin')
    programmed = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp), \
         mock.patch.object(ht, 'load_helper', lambda p: None), mock.patch.object(ht, 'manual_holder', lambda *a: None), \
         mock.patch.object(ht, 'exclusion_configured', lambda *a: None), \
         mock.patch.object(ht, 'check_jlink', lambda: None), \
         mock.patch.object(ht.Battery, 'program', lambda bat, b, base, a: programmed.append((b, base, a))):
      code = ht.main(['install', '-b', BOARD, '--firmware', str(fw), '--sha256', ht.sha256(fw),
                      '--under-hold', 'debug 7', str(cfg)])
    self.assertEqual((code, programmed), (0, [(str(fw), 0, 0x10000)]))

  def test_invalidate_needs_no_candidate_source(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    invalidated = []
    with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp), \
         mock.patch.object(ht, 'source_facts', side_effect=AssertionError('read the candidate source')), \
         mock.patch.object(ht, 'load_helper', lambda p: None), mock.patch.object(ht, 'manual_holder', lambda *a: None), \
         mock.patch.object(ht, 'check_jlink', lambda: None), mock.patch.object(ht, 'probe_users', lambda p: []), \
         mock.patch.object(ht, 'invalidate', lambda b, f, d, **k: invalidated.append(f) or {'pass': True}):
      self.assertEqual(ht.main(['invalidate', '-b', BOARD, '--under-hold', 'x', str(cfg)]), 0)
    self.assertEqual(invalidated, [None])

  def test_a_recovery_while_another_runs_is_refused_before_it_checks_the_holder(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    report = self.tmp / 'failed.json'
    report.write_text(json.dumps({'results': [{'board': BOARD, 'cleanup': {'holder': {'pid': 4242}}}]}))
    busy = mock.Mock(side_effect=ht.Refused(f'{BOARD}: another recovery holds x.lock.recover'))
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp), \
         mock.patch.object(ht, 'load_helper', lambda p: None), mock.patch.object(ht, 'check_jlink', lambda: None), \
         mock.patch.object(ht, 'recovery_lock', busy), \
         mock.patch.object(ht, 'prove_hold', side_effect=AssertionError('checked the holder')), \
         mock.patch.object(ht, 'invalidate', side_effect=AssertionError('probed')):
      code = ht.main(['invalidate', '-b', BOARD, '--recover-holder', '4242', '--report', str(report), str(cfg)])
    self.assertEqual((code, json.loads(out.getvalue().splitlines()[-1])['error']),
                     (2, f'{BOARD}: another recovery holds x.lock.recover'))
    self.assertEqual(busy.call_count, 1)

  def test_an_esptool_recovery_checks_the_snapshot_in_the_failed_report(self):
    holder = self.tmp / 'hil_test.py'
    holder.write_text('import time; time.sleep(30)')
    p = subprocess.Popen([sys.executable, str(holder)])
    self.addCleanup(lambda: (p.kill(), p.wait()))
    regions = {'nvs': [0x9000, 0xe000]}
    report = self.tmp / 'failed.json'
    report.write_text(json.dumps({'results': [{'board': S3, 'cleanup': {'holder': {'pid': p.pid}, 'state': 'unknown'},
                                               'steps': [{'step': 'identity', 'pass': True,
                                                          'evidence': {'preserved': {'nvs': 'ab' * 16}, 'preservedRegions': regions}}]}]}))
    seen = []
    with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp), \
         mock.patch.object(ht, 'load_helper', lambda p: mock.Mock()), mock.patch.object(ht, 'check_esptool', lambda: None), \
         mock.patch.object(ht, 'recovery_lock', lambda *a: mock.Mock()), mock.patch.object(ht, 'prove_hold', lambda *a, **k: {}), \
         mock.patch.object(ht, 'probe_users', lambda b: []), mock.patch.object(ht.os, 'kill', lambda *a: None), \
         mock.patch.object(ht, 'wait_for', lambda *a: True), \
         mock.patch.object(ht, 'invalidate', lambda b, f, d, **k: seen.append(k) or {'pass': True}):
      code = ht.main(['invalidate', '-b', S3, '--recover-holder', str(p.pid), '--report', str(report), str(s3_roster(self.tmp))])
    self.assertEqual(code, 0)
    self.assertEqual(seen, [{'snapshot': {'regions': {'nvs': (0x9000, 0xe000)}, 'md5': {'nvs': 'ab' * 16}}}])

  def test_no_jlinkexe_programs_nothing_on_any_path(self):
    fw = bootloader_bin(self.tmp / 'fw.bin')
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    probed = []
    for argv in (['install', '-b', BOARD, '--firmware', str(fw), '--sha256', ht.sha256(fw), '--under-hold', 'x'],
                 ['invalidate', '-b', BOARD, '--under-hold', 'x']):
      with self.subTest(argv[0]), contextlib.redirect_stdout(io.StringIO()), \
           mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / argv[0]), mock.patch.object(ht, 'load_helper', lambda p: None), \
           mock.patch.object(ht, 'manual_holder', lambda *a: None), mock.patch.object(ht, 'exclusion_configured', lambda *a: None), \
           mock.patch.object(ht.shutil, 'which', lambda t: None if t == 'JLinkExe' else '/usr/bin/' + t), \
           mock.patch.object(ht.Probe, 'run', lambda *a, **k: probed.append(a)):
        self.assertEqual(ht.main(argv + [str(cfg)]), 2)
    self.assertEqual(probed, [])


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
