"""board_facts.py over hand-built ELF32 artifacts: the facts a build gives, and every refusal."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'))
import board_facts as bf  # noqa: E402

ABS, ARM, RISCV = 0xFFF1, 40, 243


def elf(sections, symbols=(), segments=(), relocs=None, machine=ARM, etype=2):
  """An ELF32 LE file. sections: (name, addr, data, flags[, NOBITS size]); symbols: (name, value, size, section name,
  'ABS' or None for undefined); segments: PT_LOAD (vaddr, paddr, filesz); relocs: {section: [(offset, symbol, type,
  addend or None)]}, REL for ARM and RELA for RISC-V."""
  rela = machine == RISCV
  secs = [dict(name=n, addr=a, data=d, flags=f, type=8 if d is None else 1, size=s[0] if s else len(d or b''))
          for n, a, d, f, *s in sections]
  index = {s['name']: i + 1 for i, s in enumerate(secs)}
  syms = [b'\0' * 16]
  strtab = bytearray(b'\0')
  symidx = {}
  for name, value, size, sec in symbols:
    symidx[name] = len(syms)
    shndx = 0 if sec is None else ABS if sec == 'ABS' else index[sec]
    syms.append(struct.pack('<IIIBBH', len(strtab), value, size, 0x10, 0, shndx))
    strtab += name.encode() + b'\0'
  n_user = len(secs)
  rel_secs = []
  for target, rows in (relocs or {}).items():
    body = b''
    for off, sym, typ, addend in rows:
      body += struct.pack('<IIi' if rela else '<II', off, (symidx[sym] << 8) | typ, *([addend] if rela else []))
    rel_secs.append(dict(name=('.rela' if rela else '.rel') + target, addr=0, data=body, flags=0, type=4 if rela else 9,
                         size=len(body), info=index[target], entsize=12 if rela else 8))
  symtab_i = n_user + len(rel_secs) + 1
  for r in rel_secs:
    r['link'] = symtab_i
  secs += rel_secs
  secs.append(dict(name='.symtab', addr=0, data=b''.join(syms), flags=0, type=2, size=16 * len(syms),
                   link=symtab_i + 1, entsize=16))
  secs.append(dict(name='.strtab', addr=0, data=bytes(strtab), flags=0, type=3, size=len(strtab)))
  shstr = bytearray(b'\0')
  for s in secs:
    s['nameoff'] = len(shstr)
    shstr += s['name'].encode() + b'\0'
  secs.append(dict(name='.shstrtab', addr=0, data=bytes(shstr), flags=0, type=3, size=len(shstr), nameoff=len(shstr)))
  shstr += b'.shstrtab\0'
  secs[-1]['data'] = bytes(shstr)
  secs[-1]['size'] = len(shstr)
  phoff = 52
  body = bytearray(b'\0' * (phoff + 32 * len(segments)))
  for i, (vaddr, paddr, filesz) in enumerate(segments):
    struct.pack_into('<8I', body, phoff + 32 * i, 1, 0, vaddr, paddr, filesz, filesz, 5, 4)
  for s in secs:
    s['offset'] = len(body)
    body += s['data'] or b''
  shoff = len(body)
  body += b'\0' * 40
  for s in secs:
    body += struct.pack('<10I', s['nameoff'], s['type'], s['flags'], s['addr'], s['offset'], s['size'],
                        s.get('link', 0), s.get('info', 0), 4, s.get('entsize', 0))
  struct.pack_into('<4sBBBB8xHHIIIIIHHHHHH', body, 0, b'\x7fELF', 1, 1, 1, 0, etype, machine, 1, 0, phoff, shoff, 0,
                   52, 32, len(segments), 40, len(secs) + 1, len(secs))
  return bytes(body)


def ihex(data, base):
  out = [f':02000004{base >> 16:04X}{(-(6 + (base >> 24) + (base >> 16 & 0xFF))) & 0xFF:02X}']
  for off in range(0, len(data), 16):
    chunk, a = data[off:off + 16], (base + off) & 0xFFFF
    rec = bytes([len(chunk), a >> 8, a & 0xFF, 0]) + chunk
    out.append(':' + rec.hex().upper() + f'{-sum(rec) & 0xFF:02X}')
  return '\n'.join(out + [':00000001FF']) + '\n'


ALLOC, WRITE = 0x2, 0x1
BOOT, APP, RAM = 0x08000000, 0x08010000, 0x20000000
DESC = struct.pack('<BBHBBBBHHHBBBB', 18, 1, 0x200, 0, 0, 0, 64, 0x239A, 0x0057, 0x100, 1, 2, 3, 1)
INFO = b'Board-ID: STM32F407-Discovery-revD\r\n'


def words(**kw):
  return {f'hil_{k}': struct.pack('<I', v) for k, v in kw.items()}


FACT_WORDS = dict(flash_addr_zero=BOOT, flash_app_start=APP, flash_size_constant=1, flash_size=0x100000, usb_vid=0x239A,
                  usb_pid=0x0057, family=0x57755a57, dbl_tap_delay=500, dbl_tap_size=32, dbl_tap_magic=0xf01669ef,
                  dbl_tap_reg=0)


class Build:
  """A consistent build's artifacts under `root`, each overridable before write()."""

  def __init__(self, root):
    self.root = Path(root)
    self.vectors = b'\0' * (98 * 4)
    self.text = INFO + b'\0' * 12
    self.data = DESC + b'\0\0'
    self.facts = dict(words(**FACT_WORDS), hil_board_id=b'STM32F407-Discovery-revD\0')
    self.boot_syms = [('desc_device', RAM, 18, '.data'), ('_board_dfu_dbl_tap', 0x2000fffc, 0, 'ABS'),
                      ('_flash_cache', RAM + 0x100, 0x1000, '.bss'), ('g_pfnVectors', BOOT, 0, '.isr_vector')]
    self.obj_relocs = {'.rodata.hil_dbl_tap_reg': [(0, '_board_dfu_dbl_tap', 2, None)]}
    self.app_base, self.regions = APP, 'RAM              0x20000000         0x0000fffc         xrw\n' \
                                       'FLASH            0x08010000         0x00020000         xr\n'
    self.bin, self.hex_base = None, BOOT

  def boot_elf(self):
    text_at = BOOT + len(self.vectors)
    data_lma = text_at + len(self.text)
    return elf([('.isr_vector', BOOT, self.vectors, ALLOC), ('.text', text_at, self.text, ALLOC),
                ('.data', RAM, self.data, ALLOC | WRITE), ('.bss', RAM + 0x100, None, ALLOC | WRITE, 0x1000)],
               self.boot_syms, [(BOOT, BOOT, len(self.vectors) + len(self.text)), (RAM, data_lma, len(self.data))])

  def image(self):
    return self.vectors + self.text + self.data

  def write(self):
    (self.root / '_bin').mkdir(parents=True, exist_ok=True)
    (self.root / 'apps/blinky').mkdir(parents=True, exist_ok=True)
    (self.root / 'tinyuf2.elf').write_bytes(self.boot_elf())
    secs = [(f'.rodata.{k}', 0, v, ALLOC) for k, v in self.facts.items()]
    (self.root / 'board_facts.o').write_bytes(
      elf(secs, [(k, 0, len(v), f'.rodata.{k}') for k, v in self.facts.items()] +
          [(s, 0, 0, None) for s in {r[1] for rows in self.obj_relocs.values() for r in rows}],
          relocs=self.obj_relocs, etype=1))
    (self.root / 'apps/blinky/blinky.elf').write_bytes(
      elf([('.isr_vector', self.app_base, b'\0' * 0x188, ALLOC), ('.data', RAM, b'\1' * 8, ALLOC | WRITE)],
          [('g_pfnVectors', self.app_base, 0, '.isr_vector')],
          segments=[(self.app_base, self.app_base, 0x188), (RAM, self.app_base + 0x188, 8)]))
    (self.root / 'apps/blinky/blinky.elf.map').write_text(
      f'Memory Configuration\n\nName             Origin             Length             Attributes\n{self.regions}'
      '*default*        0x00000000         0xffffffff\n\nLinker script and memory map\n')
    img = self.image() if self.bin is None else self.bin
    (self.root / '_bin/tinyuf2.bin').write_bytes(img)
    (self.root / '_bin/tinyuf2.hex').write_text(ihex(img, self.hex_base))
    return self.root


class Read(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.b = Build(t.name)

  def read(self, limits=(BOOT, BOOT + 0x100000)):
    return bf.read(self.b.write(), limits)

  def refused(self, pattern):
    with self.assertRaisesRegex(bf.Refused, pattern):
      self.read()

  def test_a_consistent_build_gives_its_facts(self):
    self.assertEqual(self.read(), {
      'flashBase': BOOT, 'binBase': BOOT, 'appStart': APP, 'flashSize': 0x100000, 'vid': 0x239A, 'pid': 0x0057,
      'boardId': 'STM32F407-Discovery-revD', 'family': 0x57755a57, 'vectors': 98, 'ram': RAM, 'dblTapDelayMs': 500,
      'dblTapReg': 0x2000fffc, 'dblTapMagic': 0xf01669ef, 'flashCache': 0x1000})

  def test_a_relocated_word_adds_its_in_place_addend(self):
    self.b.facts.update(words(flash_app_start=BOOT))   # BOOT + __flash_boot_size, the addend in place (REL)
    self.b.boot_syms.append(('__flash_boot_size', 0x10000, 0, 'ABS'))
    self.b.obj_relocs['.rodata.hil_flash_app_start'] = [(0, '__flash_boot_size', 2, None)]
    self.assertEqual(self.read()['appStart'], APP)

  def test_a_riscv_object_takes_its_rela_addend(self):
    obj = elf([('.rodata.hil_x', 0, b'\0' * 4, ALLOC)], [('hil_x', 0, 4, '.rodata.hil_x'), ('sym', 0, 0, None)],
              relocs={'.rodata.hil_x': [(0, 'sym', 1, 8)]}, machine=RISCV, etype=1)
    boot = elf([('.text', 0, b'\0' * 4, ALLOC)], [('sym', 0x100, 0, 'ABS')], [(0, 0, 4)])
    with tempfile.TemporaryDirectory() as d:
      (Path(d) / 'o').write_bytes(obj)
      (Path(d) / 'e').write_bytes(boot)
      self.assertEqual(bf.object_values(bf.Elf(Path(d) / 'o'), bf.Elf(Path(d) / 'e')), {'hil_x': 0x108})

  def test_a_bootloader_for_another_architecture_refuses(self):
    self.b.boot_elf = lambda: elf([('.text', BOOT, self.b.image(), ALLOC)], self.b.boot_syms[1:2], [(BOOT, BOOT, 0x200)],
                                  machine=RISCV)
    self.refused('not Arm')

  def test_a_relocation_the_bootloader_cannot_resolve_or_of_another_type_refuses(self):
    self.b.obj_relocs['.rodata.hil_dbl_tap_reg'] = [(0, 'nowhere', 2, None)]
    self.refused('one defined symbol nowhere')
    self.b.obj_relocs['.rodata.hil_dbl_tap_reg'] = [(0, '_board_dfu_dbl_tap', 3, None)]   # R_ARM_REL32
    self.refused('relocation type 3')

  def test_the_bin_must_be_the_image_the_elf_lays_out(self):
    self.b.bin = self.b.image() + b'\0'
    self.refused('is not the image tinyuf2.elf lays out')

  def test_a_section_outside_any_file_backed_segment_refuses(self):
    self.b.data += b'\0' * 4
    self.b.boot_elf = lambda: elf(
      [('.isr_vector', BOOT, self.b.vectors, ALLOC), ('.text', BOOT + 392, self.b.text, ALLOC),
       ('.data', RAM, self.b.data, ALLOC | WRITE)],
      self.b.boot_syms[:2], [(BOOT, BOOT, 392 + len(self.b.text)), (RAM, BOOT + 392 + len(self.b.text), 18)])
    self.refused(r'\.data .* is in 0 file-backed segments')   # its last 4 bytes are past the segment's file

  def test_a_section_after_its_segment_start_maps_through_it(self):
    pad = elf([('.isr_vector', BOOT + 0x400, self.b.vectors, ALLOC)], [], [(BOOT, BOOT + 0x1000, 0x400 + 392)])
    with tempfile.TemporaryDirectory() as d:
      (Path(d) / 'e').write_bytes(pad)
      self.assertEqual(bf.Elf(Path(d) / 'e').image(), (BOOT + 0x1400, self.b.vectors))

  def test_the_flash_base_is_the_bins_or_a_ram_images_flash_base_before_its_fcb(self):
    self.b.facts.update(words(flash_addr_zero=0x60000000))
    self.refused('the BIN starts at 0x8000000, not BOARD_FLASH_ADDR_ZERO')
    self.b.boot_syms += [('_flash_base', 0x60000000, 0, 'ABS'), ('_fcfb_origin', BOOT, 0, 'ABS')]
    self.b.hex_base = 0x60000400   # the FCB's offset in its page is 0
    self.refused('whose BIN does not start at its _fcfb_origin')
    self.b.hex_base = 0x60000000
    self.assertEqual((self.read()['flashBase'], self.read()['binBase']), (0x60000000, 0x60000000))
    self.b.boot_syms[-1] = ('_fcfb_origin', BOOT + 0x400, 0, 'ABS')   # not where the image starts
    self.refused('whose BIN does not start at its _fcfb_origin')

  def test_the_descriptor_must_carry_vid_and_pid(self):
    self.b.facts.update(words(usb_pid=0x0058))
    self.refused('desc_device does not carry')

  def test_the_bin_must_carry_its_board_id_once(self):
    self.b.facts['hil_board_id'] = b'Other\0'
    self.refused('does not carry INFO_UF2')

  def test_ram_is_the_one_region_holding_the_apps_data(self):
    self.b.regions = 'RAM 0x20000000 0x00000800 xrw\n'
    self.refused('not one of at least 0x1000 bytes')
    self.b.regions = 'RAM 0x20000000 0x00010000 xrw\nRAM2 0x20000000 0x00010000 xrw\n'
    self.refused('in 2 memory regions')

  def test_a_runtime_flash_size_is_taken_only_as_cmsis_flash_size(self):
    self.b.facts.update(words(flash_size_constant=0, flash_size=0), hil_flash_size_expr=b'(FLASH_SIZE)\0')
    self.assertEqual(self.read(limits=(BOOT, BOOT + 0x80000))['flashSize'], 0x80000)
    self.b.facts['hil_flash_size_expr'] = b'(FLASH_SIZE & 0x5A5A5A5AU)\0'
    self.refused('not a constant')
    del self.b.facts['hil_flash_size_expr']
    self.refused('not a constant')

  def test_a_narrow_double_tap_register_refuses(self):
    self.b.facts.update(words(dbl_tap_size=16))
    self.refused('TINYUF2_DBL_TAP_REG_SIZE is not 32')

  def test_a_vector_count_from_the_device_header_wins_over_the_table(self):
    self.b.facts.update(words(vectors=76))
    self.assertEqual(self.read()['vectors'], 76)

  def test_a_missing_fact_or_a_truncated_object_refuses(self):
    del self.b.facts['hil_usb_vid']
    self.refused('no hil_usb_vid')
    self.b.write()
    (self.b.root / 'board_facts.o').write_bytes((self.b.root / 'board_facts.o').read_bytes()[:200])
    with self.assertRaisesRegex(bf.Refused, 'truncated or malformed'):
      bf.read(self.b.root, (BOOT, BOOT + 0x100000))

  def test_a_flash_cache_of_no_power_of_two_size_refuses(self):
    self.b.boot_syms[2] = ('_flash_cache', RAM + 0x100, 0x300, '.bss')
    self.refused('_flash_cache is not an object of a power-of-two size')

  def test_a_vector_count_must_fit_the_startups_table(self):
    self.b.facts.update(words(vectors=99))
    self.refused('99 vectors do not fit its 392-byte vector table')
    self.b.facts.update(words(vectors=15))
    self.refused('15 vectors do not fit')

  def test_without_a_count_or_a_sized_table_the_vectors_refuse(self):
    self.b.boot_syms[3] = ('__isr_vector', BOOT + 4, 0, '.isr_vector')   # unsized, and no .isr_vector there
    self.refused('no vector count in the device header and no sized vector table')

  def test_blinkys_vector_table_must_sit_at_the_app_start(self):
    self.b.app_base = APP + 0x1000
    self.refused('blinky.elf starts at 0x8011000')

  def test_two_definitions_of_a_fact_refuse(self):
    obj = elf([('.rodata.a', 0, struct.pack('<I', 1), ALLOC), ('.rodata.b', 0, struct.pack('<I', 2), ALLOC)],
              [('hil_x', 0, 4, '.rodata.a'), ('hil_x', 0, 4, '.rodata.b')], etype=1)
    with tempfile.TemporaryDirectory() as d:
      (Path(d) / 'o').write_bytes(obj)
      with self.assertRaisesRegex(bf.Refused, 'two symbols hil_x'):
        bf.object_values(bf.Elf(Path(d) / 'o'), None)

  def test_a_table_section_of_the_wrong_entry_size_refuses(self):
    obj = bytearray(elf([('.rodata.a', 0, b'\0' * 4, ALLOC)], [('hil_x', 0, 4, '.rodata.a')], etype=1))
    shoff = struct.unpack_from('<I', obj, 32)[0]
    for i in range(struct.unpack_from('<H', obj, 48)[0]):   # the symtab's sh_entsize to 0
      if struct.unpack_from('<I', obj, shoff + 40 * i + 4)[0] == 2:
        struct.pack_into('<I', obj, shoff + 40 * i + 36, 0)
    with tempfile.TemporaryDirectory() as d:
      (Path(d) / 'o').write_bytes(obj)
      with self.assertRaisesRegex(bf.Refused, 'not a whole table of its entries'):
        bf.Elf(Path(d) / 'o')


if __name__ == '__main__':
  unittest.main()
