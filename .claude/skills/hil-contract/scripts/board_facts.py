"""Board facts of a cmake HIL record (hil-contract Build), read from the build's own artifacts: the bootloader ELF and
its map, board_facts.o (board_facts.c compiled with the bootloader's compile command), the blinky app's ELF and map,
and the BIN and HEX they are checked against. Every fact is the build's, never re-derived from source text; a fact
that cannot be established refuses."""
import re
import struct
from pathlib import Path

SHT_SYMTAB, SHT_NOBITS, SHT_REL, SHT_RELA = 2, 8, 9, 4
SHF_ALLOC = 0x2
PT_LOAD = 1
# (ELF machine, relocation section type) -> the one relocation type an absolute 32-bit word carries
EM_ARM, EM_RISCV = 40, 243
ABS32 = {(EM_ARM, SHT_REL): 2, (EM_RISCV, SHT_RELA): 1}   # R_ARM_ABS32, R_RISCV_32
STACK = 0x1000   # the fixture's initial SP is ram + STACK (hil_test.fixture)
VECTOR_NAMES = ('__isr_vector', '__Vectors', 'g_pfnVectors')   # the CMSIS startups' vector table, aliases included
MALFORMED = (struct.error, IndexError, ValueError, UnicodeDecodeError, KeyError)
STRINGS = {'hil_board_id', 'hil_flash_size_expr'}   # board_facts.c's char arrays, bytes whatever their size


class Refused(Exception):
  pass


class Elf:
  """An ELF32 file's sections, PT_LOAD segments and symbols."""

  def __init__(self, path):
    self.path, self.data = Path(path), Path(path).read_bytes()
    try:
      self._parse()
    except MALFORMED as e:
      raise Refused(f'{self.path}: truncated or malformed ELF ({e})')

  def _parse(self):
    d = self.data
    if d[:4] != b'\x7fELF' or d[4] != 1 or d[5] not in (1, 2):
      raise Refused(f'{self.path}: not an ELF32 file')
    self.e = '<' if d[5] == 1 else '>'
    _, self.machine, _, _, phoff, shoff, _, _, phentsize, phnum, shentsize, shnum, shstrndx = \
      struct.unpack_from(self.e + 'HHIIIIIHHHHHH', d, 16)
    self.sections = []
    for i in range(shnum):
      name, typ, flags, addr, off, size, link, info, _, entsize = struct.unpack_from(self.e + '10I', d, shoff + i * shentsize)
      self.sections.append({'nameoff': name, 'type': typ, 'flags': flags, 'addr': addr, 'offset': off, 'size': size,
                            'link': link, 'info': info, 'entsize': entsize})
    names = self.sections[shstrndx]
    for s in self.sections:
      s['name'] = self.cstr(names['offset'] + s['nameoff'])
    self.segments = []
    for i in range(phnum):
      typ, off, vaddr, paddr, filesz, memsz = struct.unpack_from(self.e + '6I', d, phoff + i * phentsize)
      if typ == PT_LOAD:
        self.segments.append({'offset': off, 'vaddr': vaddr, 'paddr': paddr, 'filesz': filesz, 'memsz': memsz})
    self.symbols = []
    if sum(s['type'] == SHT_SYMTAB for s in self.sections) > 1:
      raise Refused(f'{self.path}: more than one symbol table')
    for s in self.sections:
      if s['type'] not in (SHT_SYMTAB, SHT_REL, SHT_RELA):
        continue
      if s['entsize'] != {SHT_SYMTAB: 16, SHT_REL: 8, SHT_RELA: 12}[s['type']] or \
         s['offset'] + s['size'] > len(d) or s['size'] % s['entsize']:
        raise Refused(f'{self.path}: section {s["name"]} is not a whole table of its entries')
      if s['type'] != SHT_SYMTAB:
        continue
      strtab = self.sections[s['link']]['offset']
      for off in range(s['offset'], s['offset'] + s['size'], s['entsize']):
        name, value, size, info, _, shndx = struct.unpack_from(self.e + 'IIIBBH', d, off)
        self.symbols.append({'name': self.cstr(strtab + name), 'value': value, 'size': size, 'bind': info >> 4,
                             'shndx': shndx})

  def cstr(self, off):
    return self.data[off:self.data.index(b'\0', off)].decode()

  def section(self, name):
    hits = [s for s in self.sections if s['name'] == name]
    if len(hits) != 1:
      raise Refused(f'{self.path}: expected one section {name}, found {len(hits)}')
    return hits[0]

  def symbol(self, name, required=True):
    """The one defined symbol `name`; None when it is absent and not required; two refuse."""
    hits = [s for s in self.symbols if s['name'] == name and s['shndx']]
    if len(hits) > 1 or required and not hits:
      raise Refused(f'{self.path}: expected one defined symbol {name}, found {len(hits)}')
    return hits[0] if hits else None

  def contents(self, sec):
    if sec['offset'] + sec['size'] > len(self.data):
      raise Refused(f'{self.path}: section {sec["name"]} runs past the file')
    return self.data[sec['offset']:sec['offset'] + sec['size']]

  def vector_table(self):
    """(address, size or None) of the startup's vector table: its symbols' one address, the size of the sized one, else
    of the .isr_vector section there."""
    hits = [s for s in self.symbols if s['name'] in VECTOR_NAMES and s['shndx']]
    addrs, sizes = {s['value'] for s in hits}, {s['size'] for s in hits if s['size']}
    if len(addrs) != 1 or len(sizes) > 1:
      raise Refused(f'{self.path}: no one vector table among {VECTOR_NAMES}: {sorted(map(hex, addrs))}')
    addr = addrs.pop()
    if sizes:
      return addr, sizes.pop()
    sec = [s for s in self.sections if s['name'] == '.isr_vector' and s['addr'] == addr]
    return addr, sec[0]['size'] if sec else None

  def image(self):
    """(base, bytes) of what objcopy -O binary writes: every allocated section with contents at its load address,
    gaps zero; each section mapped through the one PT_LOAD whose file-backed range holds it whole."""
    parts = []
    for s in self.sections:
      if not s['flags'] & SHF_ALLOC or s['type'] == SHT_NOBITS or not s['size']:
        continue
      parts.append((self.lma(s['addr'], s['size'], s['name']), self.contents(s)))
    if not parts:
      raise Refused(f'{self.path}: no loadable section')
    base = min(a for a, _ in parts)
    img = bytearray(max(a + len(b) for a, b in parts) - base)
    for a, b in parts:
      img[a - base:a - base + len(b)] = b
    return base, bytes(img)

  def lma(self, vma, size, what):
    hits = [g for g in self.segments if g['vaddr'] <= vma and vma + size <= g['vaddr'] + g['filesz']]
    if len(hits) != 1:
      raise Refused(f'{self.path}: {what} [{vma:#x}, {vma + size:#x}) is in {len(hits)} file-backed segments, not one')
    return hits[0]['paddr'] + vma - hits[0]['vaddr']


def memory_regions(map_path):
  """{name: (origin, length)} of a GNU ld map's Memory Configuration, without its *default* catch-all."""
  text = Path(map_path).read_text(errors='replace')
  m = re.search(r'^Memory Configuration\s*\n(.*?)^Linker script and memory map', text, re.S | re.M)
  if not m:
    raise Refused(f'{map_path}: no Memory Configuration')
  rows = re.findall(r'^(\S+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)', m.group(1), re.M)
  return {n: (int(o, 16), int(l, 16)) for n, o, l in rows if n != '*default*'}


def object_values(obj, boot):
  """{name: int or bytes} of board_facts.o's hil_* objects: a STRINGS array or any other non-word as its bytes, a
  word with its one absolute relocation resolved against the bootloader's own symbol; anything else refuses."""
  out = {}
  for sym in obj.symbols:
    if not sym['name'].startswith('hil_') or sym['shndx'] == 0:
      continue
    if sym['name'] in out:
      raise Refused(f'{obj.path}: two symbols {sym["name"]}')
    sec_index = sym['shndx']
    raw = obj.contents(obj.sections[sec_index])[sym['value']:sym['value'] + sym['size']]
    relocs = [r for r in relocations(obj, sec_index) if sym['value'] <= r[0] < sym['value'] + sym['size']]
    if sym['size'] != 4 or sym['name'] in STRINGS:
      if relocs:
        raise Refused(f'{obj.path}: {sym["name"]} is not a word yet has a relocation')
      out[sym['name']] = raw
      continue
    v = struct.unpack(obj.e + 'I', raw)[0]
    if relocs:
      off, name, addend = relocs[0]
      if len(relocs) != 1 or off != sym['value']:
        raise Refused(f'{obj.path}: {sym["name"]} is not one word-wide relocation')
      target = boot.symbol(name)
      v = (target['value'] + (v if addend is None else addend)) & 0xFFFFFFFF
    out[sym['name']] = v
  return out


def relocations(obj, sec_index):
  """[(offset, symbol name, addend or None for REL)] applying to section `sec_index`."""
  out = []
  for s in obj.sections:
    if s['type'] not in (SHT_REL, SHT_RELA) or s['info'] != sec_index:
      continue
    want = ABS32.get((obj.machine, s['type']))
    if obj.sections[s['link']]['type'] != SHT_SYMTAB:
      raise Refused(f'{obj.path}: {s["name"]} does not relocate against the symbol table')
    for off in range(s['offset'], s['offset'] + s['size'], s['entsize']):
      if s['type'] == SHT_REL:
        r_off, info = struct.unpack_from(obj.e + 'II', obj.data, off)
        addend = None
      else:
        r_off, info, addend = struct.unpack_from(obj.e + 'IIi', obj.data, off)
      name = obj.symbols[info >> 8]['name']
      if (info & 0xFF) != want or not name:
        raise Refused(f'{obj.path}: relocation type {info & 0xFF} against {name or "a section"} in {s["name"]}; '
                      'only an absolute word against a named symbol is read')
      out.append((r_off, name, addend))
  return out


def parse_hex(path):
  """{address: byte} of an Intel HEX file."""
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


def hex_matches_bin(data, img, base):
  """Whether a HEX ({address: byte}) is exactly the BIN image `img` laid out from `base`."""
  return min(data) == base and max(data) + 1 == base + len(img) and all(img[a - base] == b for a, b in data.items())


def word(vals, name, what):
  if not isinstance(vals.get(name), int):
    raise Refused(f'board_facts.o: no {name} ({what})')
  return vals[name]


def read(root, limits):
  """The board facts of the build whose artifacts sit under `root` (hil_test's hash-checked copies, the record's
  relative paths), for a device whose programmable flash is `limits` (FLASH_LIMITS)."""
  try:
    return _read(Path(root), limits)
  except MALFORMED as e:
    raise Refused(f'{root}: malformed build artifact ({type(e).__name__}: {e})')


def _read(root, limits):
  boot, blinky = Elf(root / 'tinyuf2.elf'), Elf(root / 'apps/blinky/blinky.elf')
  if boot.machine != EM_ARM:
    raise Refused(f'{boot.path}: machine {boot.machine}, not Arm: the battery\'s fixture is a Cortex-M image')
  vals = object_values(Elf(root / 'board_facts.o'), boot)
  bin_bytes = (root / '_bin/tinyuf2.bin').read_bytes()
  elf_base, img = boot.image()
  if bin_bytes != img:
    raise Refused(f'{root}/_bin/tinyuf2.bin is not the image tinyuf2.elf lays out from {elf_base:#x}')
  hexdata = parse_hex(root / '_bin/tinyuf2.hex')
  if not hexdata:
    raise Refused(f'{root}/_bin/tinyuf2.hex: no data')
  bin_base = min(hexdata)
  if not hex_matches_bin(hexdata, bin_bytes, bin_base):
    raise Refused(f'{root}/_bin/tinyuf2.hex is not tinyuf2.bin laid out from {bin_base:#x}')
  flash_base = word(vals, 'hil_flash_addr_zero', 'BOARD_FLASH_ADDR_ZERO')
  rom_copied = boot.symbol('_flash_base', required=False)
  if rom_copied:   # the boot ROM copies the bootloader to RAM: the BIN is the FCB onward (IMXRT1010RM Table 9-8)
    fcfb = boot.symbol('_fcfb_origin', required=False)
    if rom_copied['value'] != flash_base or not fcfb or fcfb['value'] != elf_base or \
       bin_base != flash_base + (fcfb['value'] & 0xFFF):
      raise Refused(f'tinyuf2.elf: a RAM image whose _flash_base is not BOARD_FLASH_ADDR_ZERO {flash_base:#x}, or '
                    f'whose BIN does not start at its _fcfb_origin, {flash_base:#x} + its offset in a 4 KiB page')
  elif bin_base != flash_base:
    raise Refused(f'the BIN starts at {bin_base:#x}, not BOARD_FLASH_ADDR_ZERO {flash_base:#x}')
  facts = {'flashBase': flash_base, 'binBase': bin_base,
           'appStart': word(vals, 'hil_flash_app_start', 'BOARD_FLASH_APP_START'),
           'flashSize': flash_size(vals, limits),
           'vid': word(vals, 'hil_usb_vid', 'USB_VID'), 'pid': word(vals, 'hil_usb_pid', 'USB_PID'),
           'boardId': board_id(vals, bin_bytes),
           'family': word(vals, 'hil_family', 'BOARD_UF2_FAMILY_ID'),
           'vectors': vectors(vals, boot), 'ram': ram(blinky, root / 'apps/blinky/blinky.elf.map'),
           'dblTapDelayMs': word(vals, 'hil_dbl_tap_delay', 'TINYUF2_DBL_TAP_DELAY')}
  check_descriptor(boot, elf_base, img, facts)
  app_base, _ = blinky.image()
  if app_base != facts['appStart'] or blinky.vector_table()[0] != facts['appStart']:
    raise Refused(f'blinky.elf starts at {app_base:#x} with its vector table at {blinky.vector_table()[0]:#x}, not at '
                  f'BOARD_FLASH_APP_START {facts["appStart"]:#x}')
  if word(vals, 'hil_dbl_tap_size', 'TINYUF2_DBL_TAP_REG_SIZE') != 32:
    raise Refused('TINYUF2_DBL_TAP_REG_SIZE is not 32: the retained-register battery writes a 32-bit magic')
  facts['dblTapReg'] = word(vals, 'hil_dbl_tap_reg', 'TINYUF2_DBL_TAP_REG')
  facts['dblTapMagic'] = word(vals, 'hil_dbl_tap_magic', 'DBL_TAP_MAGIC')
  cache = boot.symbol('_flash_cache', required=False)
  if cache:
    if not cache['size'] or cache['size'] & (cache['size'] - 1):
      raise Refused('tinyuf2.elf: _flash_cache is not an object of a power-of-two size')
    facts['flashCache'] = cache['size']
  return facts


def flash_size(vals, limits):
  """BOARD_FLASH_SIZE when the compiler folds it; when it is exactly CMSIS's FLASH_SIZE, the chip's size register,
  the device's programmable flash (policy: the roster device's, which INFO_UF2.TXT reports)."""
  if word(vals, 'hil_flash_size_constant', '__builtin_constant_p(BOARD_FLASH_SIZE)'):
    return word(vals, 'hil_flash_size', 'BOARD_FLASH_SIZE')
  expr = vals.get('hil_flash_size_expr', b'').rstrip(b'\0').decode()
  if re.sub(r'\s', '', expr) not in ('FLASH_SIZE', '(FLASH_SIZE)') or not limits[1]:
    raise Refused(f'BOARD_FLASH_SIZE is not a constant, nor CMSIS FLASH_SIZE on a device with flash limits: {expr!r}')
  return limits[1] - limits[0]


def board_id(vals, bin_bytes):
  raw = vals.get('hil_board_id')
  if not isinstance(raw, bytes) or not raw.endswith(b'\0'):
    raise Refused('board_facts.o: no UF2_BOARD_ID string')
  bid = raw[:-1]
  if bin_bytes.count(b'Board-ID: ' + bid + b'\r\n') != 1:
    raise Refused(f'tinyuf2.bin does not carry INFO_UF2.TXT\'s "Board-ID: {bid.decode()}" once')
  return bid.decode()


def vectors(vals, boot):
  """The CMSIS vector count (NUMBER_OF_INT_VECTORS, msdk's MXC_IRQ_COUNT), inside the startup's table where its size is
  known; on a device header with neither, that table's entries."""
  _, size = boot.vector_table()
  if 'hil_vectors' in vals:
    count = word(vals, 'hil_vectors', 'NUMBER_OF_INT_VECTORS')
  elif size is None or size % 4:
    raise Refused(f'{boot.path}: no vector count in the device header and no sized vector table')
  else:
    count = size // 4
  if count < 16 or size is not None and count * 4 > size:
    raise Refused(f'{boot.path}: {count} vectors do not fit its {size}-byte vector table')
  return count


def ram(blinky, map_path):
  """The origin of the app link's one memory region holding its .data, with room for the fixture's stack."""
  data = blinky.section('.data')
  if not data['size']:
    raise Refused(f'{blinky.path}: empty .data')
  hits = [(o, n) for o, n in memory_regions(map_path).values() if o <= data['addr'] < o + n]
  if len(hits) != 1 or hits[0][1] < STACK:
    raise Refused(f'{map_path}: .data at {data["addr"]:#x} is in {len(hits)} memory regions, not one of at least '
                  f'{STACK:#x} bytes')
  return hits[0][0]


def check_descriptor(boot, base, img, facts):
  """The bootloader's device descriptor, as programmed, names USB_VID and USB_PID."""
  d = boot.symbol('desc_device')
  if d['size'] != 18:
    raise Refused(f'{boot.path}: desc_device is {d["size"]} bytes, not a device descriptor')
  off = boot.lma(d['value'], 18, 'desc_device') - base
  if struct.unpack_from('<HH', img, off + 8) != (facts['vid'], facts['pid']):
    raise Refused(f'{boot.path}: desc_device does not carry USB_VID {facts["vid"]:#06x} and USB_PID {facts["pid"]:#06x}')
