"""apps/dfu_runtime's nonce parser, compiled for the host and called through ctypes."""
import ctypes
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'apps' / 'dfu_runtime' / 'src'
spec = importlib.util.spec_from_file_location('hil_test', ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts' / 'hil_test.py')
ht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ht)
STRING_SIZE = len('HIL ') + 1 + 2 * 16


def block(nonce=b'\x01\x23\x45\x67\x89\xab\xcd\xef\x10\x32\x54\x76\x98\xba\xdc\xfe', length=None, magic=b'TUF2NONC'):
  n = len(nonce) if length is None else length
  head = magic + n.to_bytes(4, 'little') + nonce
  return bytearray(head + bytes(i & 0xff for i in range(len(head), 256)))


class NonceBlock(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.tmp = tempfile.TemporaryDirectory()
    lib = Path(cls.tmp.name) / 'nonce.so'
    subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Werror', '-I', SRC, '-o', lib, SRC / 'nonce.c'], check=True)
    cls.fn = ctypes.CDLL(str(lib)).nonce_block_to_string
    cls.fn.restype = ctypes.c_bool

  @classmethod
  def tearDownClass(cls):
    cls.tmp.cleanup()

  def parse(self, blk):
    self.assertEqual(len(blk), 256)
    out = ctypes.create_string_buffer(b'\xaa' * (STRING_SIZE + 8), STRING_SIZE + 8)   # guard bytes past the string
    ok = self.fn((ctypes.c_uint8 * 256).from_buffer_copy(bytes(blk)), out)
    return ok, out.raw

  def test_valid_lengths(self):
    for nonce in (b'\x5a', bytes(range(0xf0, 0x100))):
      ok, raw = self.parse(block(nonce))
      self.assertTrue(ok)
      text = 'HIL ' + nonce.hex()
      self.assertEqual(raw[:len(text) + 1], text.encode() + b'\0')
      self.assertEqual(raw[len(text) + 1:], b'\xaa' * (len(raw) - len(text) - 1))

  def test_the_runner_block_parses(self):
    nonce = os.urandom(16)
    ok, raw = self.parse(ht.nonce_block(nonce))
    self.assertTrue(ok)
    self.assertEqual(raw[:37], f'HIL {nonce.hex()}'.encode() + b'\0')

  def test_invalid_blocks_leave_the_string(self):
    bad_pad = block()
    bad_pad[200] ^= 1
    erased = bytearray(b'\xff' * 256)
    cases = {'length 0': block(b'', 0), 'length 17': block(bytes(17)), 'large LE length': block(length=0x01000010),
             'bad magic': block(magic=b'TUF2NONX'), 'bad padding': bad_pad, 'erased': erased}
    for what, blk in cases.items():
      with self.subTest(what):
        ok, raw = self.parse(blk)
        self.assertFalse(ok)
        self.assertEqual(raw, b'\xaa' * len(raw))


if __name__ == '__main__':
  unittest.main()
