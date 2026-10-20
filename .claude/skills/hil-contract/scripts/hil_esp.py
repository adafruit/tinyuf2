"""Espressif facts and build-record admission for hil_test.py: what an IDF build of a TinyUF2 board
writes where, read from the candidate's source and checked against the generated build files."""
import csv
import hashlib
import io
import re
import struct

from pathlib import Path

from check_build import FLASH, HIL_APP, IDF_CONFIG

# 2nd-stage bootloader offset per chip, independent of the build: the ROM loads it from here (IDF v6.1
# esp_rom/<chip>/esp_rom_caps.h ESP_ROM_BOOTLOADER_OFFSET_FLASH, esptool 5.2.0 targets/<chip>.py; no checked TRM states it)
BOOTLOADER_OFFSET = {'esp32s3': 0x0, 'esp32p4': 0x2000}
PARTITION_TABLE = (0x8000, 0x1000)   # ports/espressif/sdkconfig.defaults CONFIG_PARTITION_TABLE_OFFSET; one sector
APP, DATA = 0x00, 0x01
SUBTYPE = {(APP, 'factory'): 0x00, (APP, 'ota_0'): 0x10, (APP, 'ota_1'): 0x11, (DATA, 'ota'): 0x00,
           (DATA, 'nvs'): 0x02, (DATA, 'fat'): 0x81}
TYPE = {'app': APP, 'data': DATA}
# the IDF build's own segments, the flash's inputs after flash_args: build-dir path -> the segment's name
# (its roster region)
SEGMENT_PATHS = {p: Path(p).name for p in FLASH['esptool'][1][1:]}
SEGMENTS = tuple(SEGMENT_PATHS.values())
NATIVE = {v: k for k, v in SEGMENT_PATHS.items()}
APP_UF2 = f'_bin/apps/{HIL_APP}.uf2'   # the battery's app, copied through TinyUF2
BLINKY_UF2 = '_bin/apps/blinky.uf2'   # what cleanup leaves running
RECORD_FILES = (APP_UF2, BLINKY_UF2, *IDF_CONFIG)   # besides the flash's inputs, which admit_flash checks
IMAGE_MAGIC = 0xE9


class Refused(Exception):
  pass


def size_of(text):
  m = re.fullmatch(r'(\d+)([KM]?)', text.strip())
  if not m:
    raise Refused(f'{text!r} is not a partition size')
  return int(m.group(1)) * {'': 1, 'K': 1024, 'M': 1024 * 1024}[m.group(2)]


def parse_csv(text, what):
  """[(label, type, subtype, offset, size)] of an IDF partition CSV with explicit offsets only."""
  rows = []
  for row in csv.reader(io.StringIO(text)):
    row = [c.strip() for c in row]
    if not row or not row[0] or row[0].startswith('#'):
      continue
    if len(row) < 5 or row[1] not in TYPE or (TYPE[row[1]], row[2]) not in SUBTYPE or not row[3]:
      raise Refused(f'{what}: unsupported row {row}')
    rows.append((row[0], TYPE[row[1]], SUBTYPE[TYPE[row[1]], row[2]], int(row[3], 0), size_of(row[4])))
  return rows


def parse_table(blob, what):
  """[(label, type, subtype, offset, size)] of a generated partition-table.bin, its MD5 entry checked."""
  rows, md5 = [], None
  for i in range(0, len(blob), 32):
    e = blob[i:i + 32]
    if e[:2] == b'\xaa\x50':
      t, st, off, size = struct.unpack_from('<BBII', e, 2)
      rows.append((e[12:28].rstrip(b'\0').decode('ascii', 'replace'), t, st, off, size))
    elif e[:2] == b'\xeb\xeb':
      md5 = e[16:32]
      if hashlib.md5(blob[:i]).digest() != md5:
        raise Refused(f'{what}: MD5 entry does not match the table')
    elif e == b'\xff' * 32:
      break
    else:
      raise Refused(f'{what}: entry {i // 32} is neither a partition, an MD5 nor the end')
  if md5 is None:
    raise Refused(f'{what}: no MD5 entry')
  return rows


def sdkconfig(text):
  return dict(re.findall(r'^(CONFIG_\w+)=(.*)$', text, re.M))


def facts(root, board):
  """What the candidate's source says about an espressif board's chip, flash size and partitions."""
  bdir = f'ports/espressif/boards/{board["name"]}'
  m = re.search(r'^\s*set\s*\(\s*IDF_TARGET\s+"?(\w+)"?\s*\)', (root / bdir / 'board.cmake').read_text(), re.M)
  if not m or m.group(1) != board['device']:
    raise Refused(f'{bdir}/board.cmake: IDF_TARGET {m.group(1) if m else None} is not the roster chip {board["device"]}')
  cfg = sdkconfig((root / bdir / 'sdkconfig').read_text())
  sizes = [int(k[len('CONFIG_ESPTOOLPY_FLASHSIZE_'):-2]) for k, v in cfg.items()
           if re.fullmatch(r'CONFIG_ESPTOOLPY_FLASHSIZE_\d+MB', k) and v == 'y']
  name = cfg.get('CONFIG_PARTITION_TABLE_CUSTOM_FILENAME', '').strip('"')
  if len(sizes) != 1 or not re.fullmatch(r'partitions-[\w-]+\.csv', name):
    raise Refused(f'{bdir}/sdkconfig: expected one CONFIG_ESPTOOLPY_FLASHSIZE_<N>MB=y and a partitions-*.csv')
  return {'flashSize': sizes[0] * 1024 * 1024, 'partitionCsv': name,
          'partitions': parse_csv((root / 'ports/espressif' / name).read_text(), name)}


def layout(f, chip):
  """Where the runner may write, from the partitions: each install segment's region, the app (ota_0, which
  only TinyUF2 writes, through copy), and every other partition, preserved."""
  parts = {p[0]: p for p in f['partitions']}
  by_kind = {(p[1], p[2]): p for p in f['partitions']}
  need = {'otadata': (DATA, 0x00), 'app': (APP, 0x10), 'factory': (APP, 0x00)}
  missing = [k for k, v in need.items() if v not in by_kind]
  if missing:
    raise Refused(f'{f["partitionCsv"]}: no {", ".join(missing)} partition')
  span = lambda p: (p[3], p[3] + p[4])
  install = {'bootloader.bin': (BOOTLOADER_OFFSET[chip], PARTITION_TABLE[0]),
             'partition-table.bin': (PARTITION_TABLE[0], sum(PARTITION_TABLE)),
             'ota_data_initial.bin': span(by_kind[need['otadata']]), 'tinyuf2.bin': span(by_kind[need['factory']])}
  spans = sorted([(*install['bootloader.bin'], 'bootloader'), (*install['partition-table.bin'], 'partition table')] +
                 [(*span(p), p[0]) for p in f['partitions']])
  for (s0, e0, a), (s1, e1, b) in zip(spans, spans[1:]):
    if e0 > s1:
      raise Refused(f'{f["partitionCsv"]}: {a} [{s0:#x},{e0:#x}) overlaps {b} at {s1:#x}')
  if spans[-1][1] > f['flashSize']:
    raise Refused(f'{f["partitionCsv"]}: {spans[-1][2]} ends at {spans[-1][1]:#x}, past the {f["flashSize"]:#x} flash')
  owned = {by_kind[v][0] for v in need.values()}
  return {'install': install, 'app': span(by_kind[need['app']]),
          'preserved': {n: span(p) for n, p in parts.items() if n not in owned}}


def read_flash_args(text, what):
  """(settings, {offset: basename}) of an IDF flash_args file."""
  lines = [l.split() for l in text.splitlines() if l.strip()]
  if not lines:
    raise Refused(f'{what}: empty')
  opts = lines[0]
  if len(opts) % 2 or not all(o.startswith('--') for o in opts[::2]):
    raise Refused(f'{what}: first line is not --option value pairs: {opts}')
  settings = {o[2:]: v for o, v in zip(opts[::2], opts[1::2])}
  segs = {}
  for l in lines[1:]:
    if len(l) != 2 or not re.fullmatch(r'0x[0-9a-fA-F]+', l[0]):
      raise Refused(f'{what}: {" ".join(l)!r} is not "OFFSET FILE"')
    off = int(l[0], 16)
    if off in segs:
      raise Refused(f'{what}: two segments at {off:#x}')
    if l[1] not in SEGMENT_PATHS:
      raise Refused(f'{what}: {l[1]!r} is not one of the IDF build\'s segments {sorted(SEGMENT_PATHS)}')
    segs[off] = SEGMENT_PATHS[l[1]]
  return settings, segs


def admit(root, board, f, lay):
  """The segments an install writes, [(offset, path)], from an IDF build dir already hash-checked against
  its record: flash_args, the generated sdkconfig and partition table must agree with the candidate's
  source, and every segment must sit inside its own region. Paths are the build tree's own files, which
  the flash writes, not the _bin copies."""
  gen = sdkconfig((root / 'sdkconfig').read_text())
  want = {'CONFIG_IDF_TARGET': f'"{board["device"]}"', 'CONFIG_PARTITION_TABLE_OFFSET': hex(PARTITION_TABLE[0]),
          'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME': f'"{f["partitionCsv"]}"',
          'CONFIG_ESPTOOLPY_FLASHSIZE': f'"{f["flashSize"] // (1024 * 1024)}MB"'}
  bad = {k: gen.get(k) for k, v in want.items() if gen.get(k) != v}
  if bad:
    raise Refused(f'generated sdkconfig differs from the candidate source: {bad}')
  settings, segs = read_flash_args((root / 'flash_args').read_text(), 'flash_args')
  for k, v in (('flash-mode', gen.get('CONFIG_ESPTOOLPY_FLASHMODE')), ('flash-freq', gen.get('CONFIG_ESPTOOLPY_FLASHFREQ')),
               ('flash-size', gen.get('CONFIG_ESPTOOLPY_FLASHSIZE'))):
    if f'"{settings.get(k)}"' != v:
      raise Refused(f'flash_args --{k} {settings.get(k)} differs from the generated sdkconfig {v}')
  if sorted(segs.values()) != sorted(SEGMENTS):
    raise Refused(f'flash_args names {sorted(segs.values())}, not exactly {sorted(SEGMENTS)}')
  table = parse_table((root / NATIVE['partition-table.bin']).read_bytes(), 'partition-table.bin')
  if table != f['partitions']:
    raise Refused(f'partition-table.bin {table} differs from {f["partitionCsv"]} {f["partitions"]}')
  out = []
  for off, name in sorted(segs.items()):
    path = root / NATIVE[name]
    lo, hi = lay['install'][name]
    size = path.stat().st_size
    if off != lo or off + size > hi:
      raise Refused(f'{name} [{off:#x},{off + size:#x}) is not at the start of its region [{lo:#x},{hi:#x})')
    with open(path, 'rb') as fh:
      magic = fh.read(1)
    if name in ('bootloader.bin', 'tinyuf2.bin') and magic != bytes([IMAGE_MAGIC]):
      raise Refused(f'{name} is not an ESP image (no 0xE9 magic)')
    out.append((off, path))
  return out
