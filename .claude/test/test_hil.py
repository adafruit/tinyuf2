#!/usr/bin/env python3
"""Tests of the HIL contract's runner. Stubs prove the plumbing only: every probe and USB path here is
unverified until a real run on the rig (commissioning.md)."""
import contextlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts' / 'hil_test.py'
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('hil_test', SCRIPT)
ht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ht)
# lib/agentrc's flash provider, loaded once as main() loads it; its pin check is Roster's to test, against the real
# checkout and a git hook's environment
with mock.patch.object(ht, 'check_lock_pin'), contextlib.suppress(ht.Refused):
  ht.provider()
  ht.openocd_esp()
BOARD = 'lpcxpresso55s69'
RT = {'port': 'mimxrt10xx', 'name': 'imxrt1060_evk', 'lock': 'mimxrt1060_evk'}

HOLDER = '''
import fcntl, json, os, sys, time
fh = os.fdopen(os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o666), 'r+')
if sys.argv[3] == 'lock':
  fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
fh.truncate(0); fh.seek(0); json.dump({'pid': os.getpid(), 'reason': sys.argv[2]}, fh); fh.flush()
print('ready', flush=True)
time.sleep(60)
'''


def pinned_helper(test, lockdir):
  """lib/agentrc's hil_lock.py, the helper the runner takes its locks through, with its locks under `lockdir`."""
  if not ht.LOCK_HELPER.is_file():
    test.fail('lib/agentrc not checked out: git submodule update --init lib/agentrc')
  helper = ht.load_helper()
  helper.BOARD_LOCK_DIR = str(lockdir)
  return helper


MARK_HELPER = []
PENDING_MARK = ht.PendingMark   # the class, which Tmp patches with one over the test's helper


def stat_mode(path):
  return os.stat(path).st_mode & 0o777


def mark_helper(test, lockdir):
  """One pinned hil_lock for every test's pending marks (the pin is checked once), its dir `lockdir` for this test."""
  if not MARK_HELPER:
    with mock.patch.object(ht, 'check_lock_pin'):   # the pin's own tests check it, outside a commit's git env
      MARK_HELPER.append(pinned_helper(test, lockdir))
  p = mock.patch.object(MARK_HELPER[0], 'BOARD_LOCK_DIR', str(lockdir))
  p.start()
  test.addCleanup(p.stop)
  return MARK_HELPER[0]


def end_child(pid):
  """SIGKILL and reap `pid` only while it is still this process's unreaped child, so its number cannot have been
  reused; one already reaped, or not a child, is skipped. True when it was still running."""
  try:
    if os.waitpid(pid, os.WNOHANG)[0]:   # it had exited: now reaped
      return False
  except ChildProcessError:
    return False
  os.kill(pid, signal.SIGKILL)
  os.waitpid(pid, 0)
  return True


def reap_detached(test):
  """End every build-lock keeper and cleanup holder the test forks, before its temp dirs go: a keeper over a pending
  session's receipt waits for ever once that receipt is deleted (unreadable keeps the lock, by design)."""
  forked, keep, hand = [], ht.keep_build_lock, ht.hand_off

  def recorded(fn):
    def call(*a, **k):
      r = fn(*a, **k)
      if isinstance(r, dict) and not r.get('inProcess'):
        forked.append(r['pid'])
      return r
    return call
  test.addCleanup(lambda: [end_child(pid) for pid in forked])   # after the patches stop, before the temp dirs go
  for p in (mock.patch.object(ht, 'keep_build_lock', recorded(keep)), mock.patch.object(ht, 'hand_off', recorded(hand))):
    p.start()
    test.addCleanup(p.stop)


def tearDownModule():
  """No `hil_test.py keep-build` or `keep-held` child of this process outlives the suite."""
  mine = []
  for d in Path('/proc').iterdir():
    try:
      ppid = re.search(r'^PPid:\s*(\d+)', (d / 'status').read_text(), re.M)
      cmd = (d / 'cmdline').read_bytes().split(b'\0')
    except (OSError, ValueError):
      continue
    if ppid and int(ppid.group(1)) == os.getpid() and any(c.endswith(b'hil_test.py') for c in cmd) and \
       {b'keep-build', b'keep-held'} & set(cmd):
      mine.append(int(d.name))
  left = [pid for pid in mine if end_child(pid)]
  if left:
    raise AssertionError(f'keep-build or keep-held children {left} outlived the suite')


def no_ci_job(test):
  """This process outside a CI job, as the openocd_esp route requires (ci_refusal): the suite may run in one."""
  env = {k: v for k, v in os.environ.items() if k not in ht.openocd_esp().CI_JOB_ENV}
  test.enterContext(mock.patch.dict(os.environ, env, clear=True))


def roster(tmp, **over):
  t = {'reentry': 'retained-register'}
  t.update(over.pop('tinyuf2', {}))
  b = {'name': BOARD, 'uid': 'UID', 'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0'},
       'tinyuf2': t}
  b.update(over)
  cfg = tmp / 'local.json'
  cfg.write_text(json.dumps({'boards': [b]}))
  return cfg


# the runner reads no source facts for lpc55; most tests keep its layout as synthetic facts
LPC_FACTS = {'flashBase': 0, 'binBase': 0, 'appStart': 0x10000, 'flashSize': 0x98000, 'vid': 0x1fc9, 'pid': 0x0094,
             'boardId': 'LPC55S69-Xpresso-revA', 'family': 0x2abc77ec, 'vectors': 76, 'ram': 0x20000000,
             'dblTapDelayMs': 500, 'dblTapReg': 0x4002C05C, 'dblTapMagic': 0xF01669EF}
# stm32h563_nucleo's source facts, which StlinkSourceFacts checks against the source: the pre-commit job does not fetch
# the stm32h5 CMSIS header its vector count needs
H563_FACTS = {'flashBase': 0x08000000, 'binBase': 0x08000000, 'appStart': 0x08008000, 'flashSize': 0x200000,
              'vid': 0x239a, 'pid': 0x0163, 'boardId': 'STM32H563-Nucleo', 'family': 0x4e8f1c5d, 'vectors': 147,
              'ram': 0x20000000, 'dblTapDelayMs': 500, 'dblTapReg': 0x2009FFFC, 'dblTapMagic': 0xF01669EF}
SYNTHETIC_FACTS = {'lpc55': LPC_FACTS, 'stm32h5': H563_FACTS}
real_source_facts = ht.source_facts


def source_facts(board):
  return dict(SYNTHETIC_FACTS[board['port']]) if board['port'] in SYNTHETIC_FACTS else real_source_facts(board)


class Tmp(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    reap_detached(self)
    self.mark_helper = mark_helper(self, self.tmp / 'marks')
    for p in (mock.patch.object(ht, 'source_facts', source_facts), mock.patch.object(ht, 'PROTECTED_SESSIONS', []),
              mock.patch.object(ht, 'PendingMark', lambda helper, lock: PENDING_MARK(self.mark_helper, lock))):
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
    self.assertEqual((b['install'], b['app'], b['device'], b['if'], b['speed']),
                     ((0, 0x10000), (0x10000, 0x98000), 'LPC55S69_M33_0', 'SWD', '4000'))

  def test_refusals(self):
    cases = {
      'args': {'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device LPC55S69_M33_0 -if SWD'}},
      'int uid': {'flasher': {'name': 'jlink', 'uid': 1, 'args': '-device LPC55S69_M33_0'}},
      'unknown device': {'flasher': {'name': 'jlink', 'uid': '1', 'args': '-device NRF52840_XXAA'}},
      'bad lock name': {'tinyuf2': {'lock': '../x'}},
      'usbPower without a port': {'tinyuf2': {'usbPower': {'hub': 'PA40004'}}},
      'usbPower port out of range': {'tinyuf2': {'usbPower': {'hub': 'PA40004', 'port': 16}}},
      'usbPower port as text': {'tinyuf2': {'usbPower': {'hub': 'PA40004', 'port': '3'}}},
      'usbPower hub path': {'tinyuf2': {'usbPower': {'hub': '../x', 'port': 3}}},
      'not a TinyUF2 board': {'name': 'no_such_board'},
    }
    for what, over in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.load_board(roster(self.tmp, **over), over.get('name', BOARD))

  def test_usb_power_is_for_jlink_boards_only(self):
    with self.assertRaisesRegex(ht.Refused, 'usbPower is for J-Link boards only'):
      ht.load_board(s3_roster(self.tmp, tinyuf2={'reentry': 'dfu-detach', 'usbPower': {'hub': 'PA40004', 'port': 3}}), S3)

  def test_a_missing_lock_helper_submodule_is_refused(self):
    for what, file, checkout in (('no file', False, True), ('not a checkout', True, False)):
      helper = self.tmp / 'hil_lock.py'
      helper.unlink(missing_ok=True)
      if file:
        helper.write_text('')
      with self.subTest(what), mock.patch.object(ht, 'LOCK_HELPER', helper), \
           mock.patch.object(ht.cb, 'own_checkout', lambda p: checkout), \
           self.assertRaisesRegex(ht.Refused, 'git submodule update --init lib/agentrc'):
        ht.check_lock_pin()

  def test_a_lock_helper_off_its_pin_is_refused(self):
    helper = self.tmp / 'hil_lock.py'
    helper.write_text('')
    pin, other = 'a' * 40, 'b' * 40
    cases = {'off its pin': (other, pin, [], f'lib/agentrc is at {other}; HEAD pins {pin}: git submodule update'),
             'off its pin with the pin change staged': (other, other, [], f'but {other} is staged: commit or unstage'),
             'dirty at its pin': (pin, pin, ['lib/agentrc'], f'lib/agentrc checkout is dirty at the pinned {pin}'),
             'clean at its pin': (pin, pin, [], None)}
    for what, (have, staged, dirty, refusal) in cases.items():
      pinned = {('rev-parse', 'HEAD:lib/agentrc'): pin + '\n', ('rev-parse', ':lib/agentrc'): staged + '\n'}
      checked_out = {('lib/agentrc', 'rev-parse', 'HEAD'): have + '\n'}
      with self.subTest(what), mock.patch.object(ht, 'LOCK_HELPER', helper), \
           mock.patch.object(ht.cb, 'own_checkout', lambda p: p == 'lib/agentrc'), \
           mock.patch.object(ht.cb, 'git', lambda *a: pinned[a]), \
           mock.patch.object(ht.cb, 'git_in', lambda *a: checked_out[a]), \
           mock.patch.object(ht.cb, 'dirty_inputs', lambda paths: [p for p in paths if p in dirty]):
        if refusal:
          with self.assertRaisesRegex(ht.Refused, refusal):
            ht.check_lock_pin()
        else:
          ht.check_lock_pin()

  def test_a_git_failure_reading_the_pin_is_refused(self):
    helper = self.tmp / 'hil_lock.py'
    helper.write_text('')
    pin, other = 'a' * 40, 'b' * 40

    def fail(*a):
      raise ht.cb.Fail('git failed')

    def git_staged_fails(*a):
      return fail() if a == ('rev-parse', ':lib/agentrc') else pin + '\n'

    cases = {'git': (fail, lambda *a: pin + '\n', lambda p: []),
             'git_in': (lambda *a: pin + '\n', fail, lambda p: []),
             'git reading the staged pin': (git_staged_fails, lambda *a: other + '\n', lambda p: []),
             'dirty_inputs': (lambda *a: pin + '\n', lambda *a: pin + '\n', fail)}
    for what, (git, git_in, dirty_inputs) in cases.items():
      with self.subTest(what), mock.patch.object(ht, 'LOCK_HELPER', helper), \
           mock.patch.object(ht.cb, 'own_checkout', lambda p: True), mock.patch.object(ht.cb, 'git', git), \
           mock.patch.object(ht.cb, 'git_in', git_in), mock.patch.object(ht.cb, 'dirty_inputs', dirty_inputs), \
           self.assertRaisesRegex(ht.Refused, 'git failed'):
        ht.check_lock_pin()

  def test_this_checkout_passes_the_real_pin_check(self):
    if not ht.LOCK_HELPER.is_file():
      self.fail('lib/agentrc not checked out: git submodule update --init lib/agentrc')
    # a git hook exports these, which would point git -C lib/agentrc at the superproject
    env = {k: v for k, v in os.environ.items() if k not in ('GIT_DIR', 'GIT_WORK_TREE')}
    if 'GIT_INDEX_FILE' in env:
      # commit -a and commit <path> run the hook on a temporary index that holds the pin being committed
      env['GIT_INDEX_FILE'] = str(ht.ROOT / env['GIT_INDEX_FILE'])
    self.enterContext(mock.patch.dict(os.environ, env, clear=True))
    git_in = ht.cb.git_in

    def git_in_own_index(*a):
      with mock.patch.dict(os.environ):
        os.environ.pop('GIT_INDEX_FILE', None)
        return git_in(*a)

    self.enterContext(mock.patch.object(ht.cb, 'git_in', git_in_own_index))
    want, staged = (ht.cb.git('rev-parse', ref).strip() for ref in ('HEAD:lib/agentrc', ':lib/agentrc'))
    if staged != want:
      # a commit bumping the pin runs this hook with the new pin staged over HEAD's: the other tests load
      # whatever is checked out, so that must be the staged pin, clean, or they test the wrong helper
      have = ht.cb.git_in('lib/agentrc', 'rev-parse', 'HEAD').strip()
      self.assertEqual((have, ht.cb.dirty_inputs(['lib/agentrc'])), (staged, []),
                       f'lib/agentrc is not checked out clean at the staged pin {staged}: git submodule update --init lib/agentrc')
      with self.assertRaisesRegex(ht.Refused, 'is staged: commit or unstage'):
        ht.check_lock_pin()
    else:
      ht.check_lock_pin()

  def test_the_pinned_lock_helper_checks_its_pin_and_passes_the_contract(self):
    with mock.patch.object(ht, 'check_lock_pin') as pin:
      helper = pinned_helper(self, self.tmp / 'locks')
    pin.assert_called_once_with()
    self.assertEqual((helper.PROTECTED_REASONS, helper.CI_REASON, helper.CLEANUP_ROLE),
                     (ht.PROTECTED, 'hil_test.py', ht.HOLDER_ROLE))
    self.assertTrue(issubclass(helper.LockUnavailable, RuntimeError))

  def test_a_lock_helper_off_the_contract_is_refused(self):
    if not ht.LOCK_HELPER.is_file():
      self.fail('lib/agentrc not checked out: git submodule update --init lib/agentrc')
    text = ht.LOCK_HELPER.read_text()
    for what, old, new in (('cleanup role', "CLEANUP_ROLE = 'cleanup-holder'", "CLEANUP_ROLE = 'other'"),
                           ('protected reasons', "{CI_REASON, 'pool_check'}", '{CI_REASON}'),
                           ('LockUnavailable not a RuntimeError', 'class LockUnavailable(RuntimeError)', 'class LockUnavailable(OSError)'),
                           ('LockUnavailable not a class', 'class LockUnavailable(RuntimeError):',
                            'LockUnavailable = 1\nclass _LockUnavailable(RuntimeError):'),
                           ('protected reasons not iterable', "PROTECTED_REASONS = {CI_REASON, 'pool_check'}",
                            'PROTECTED_REASONS = 1'),
                           ('protected reasons unhashable', "PROTECTED_REASONS = {CI_REASON, 'pool_check'}",
                            'PROTECTED_REASONS = [[CI_REASON]]')):
      self.assertIn(old, text)
      off = self.tmp / 'off.py'
      off.write_text(text.replace(old, new))
      with self.subTest(what), mock.patch.object(ht, 'LOCK_HELPER', off), mock.patch.object(ht, 'check_lock_pin'), \
           self.assertRaisesRegex(ht.Refused, 'recheck this contract'):
        ht.load_helper()

  def test_the_lock_defaults_to_the_board_name_and_the_port_comes_from_it(self):
    b = ht.load_board(roster(self.tmp), BOARD)
    self.assertEqual((b['lock'], b['port']), (BOARD, 'lpc55'))
    b = ht.load_board(roster(self.tmp, tinyuf2={'lock': 'other'}), BOARD)
    self.assertEqual((b['name'], b['lock']), (BOARD, 'other'))

  def test_layout_refusals(self):
    b = ht.load_board(roster(self.tmp), BOARD)
    cases = {'app start at the flash base': {'appStart': 0},
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
    f3 = self.load(ROOT / 'test' / 'hil' / 'local.json', 'stm32f303disco')
    self.assertEqual((f3['reentry'], f3['usbPower'], f3['install'], f3['app']),
                     ('retained-register', {'hub': 'PA40004', 'port': 3}, (0x08000000, 0x08004000), (0x08004000, 0x08040000)))
    self.assertIsNone(b['usbPower'])
    f4 = self.load(ROOT / 'test' / 'hil' / 'local.json', 'stm32f411ve_discovery')
    self.assertEqual((f4['lock'], f4['reentry'], f4['usbPower'], f4['install'], f4['app']),
                     ('stm32f411disco', 'retained-register', None, (0x08000000, 0x08010000), (0x08010000, 0x08080000)))
    ci = self.load(ROOT / 'test' / 'hil' / 'ci.json', 'imxrt1064_evk')
    self.assertEqual((ci['lock'], ci['reentry'], ci['usbPower'], ci['install'], ci['app']),
                     ('mimxrt1064_evk', 'retained-register', None, (0x70000000, 0x7000C000), (0x7000C000, 0x70400000)))
    facts = ht.source_facts(f4)
    for what, over in (('flash past the F411VE\'s 512 KiB', {'flashSize': 0x100000}),
                       ('flash below 0x08000000', {'flashBase': 0x07FF0000})):
      with self.subTest(what), self.assertRaisesRegex(ht.Refused, 'leaves the stm32f411ve flash'):
        ht.apply_layout(dict(f4), dict(facts, **over))


class PortPowerCase(Tmp):
  """A stuck port is cycled through its sysfs disable, in bounded children, only after STUCK s in "default" within
  one wait, at most once per GAP s, and never left off."""

  def setUp(self):
    super().setUp()
    self.sys = self.tmp / 'sys'
    for name, cls, serial in (('5-3', '09', 'PA40004'), ('5-3.3', '00', 'x'), ('5-1', '09', 'OTHER')):
      (self.sys / name).mkdir(parents=True)
      (self.sys / name / 'bDeviceClass').write_text(cls + '\n')
      (self.sys / name / 'serial').write_text(serial + '\n')
    self.port = self.sys / '5-3' / '5-3:1.0' / '5-3-port3'
    self.port.mkdir(parents=True)
    (self.port / 'disable').write_text('0\n')
    self.clock, self.writes, self.fail = [0.0], [], {}
    real_path = ht.Path

    def spawn(cmd, log, timeout, cwd=None, **k):
      self.assertEqual((cmd[:3], timeout), (['sh', '-c', ht.PortPower.SET], ht.PortPower.TIMEOUT))
      value = cmd[-1]
      self.writes.append((self.clock[0], value))
      outcome = self.fail.pop(len(self.writes), None)
      if isinstance(outcome, BaseException):
        raise outcome
      if outcome is None:
        cmd[-2].write_text(value + '\n')
        return 0, ''
      return outcome
    for p in (mock.patch.object(ht, 'Path', lambda *a: self.sys if a == ('/sys/bus/usb/devices',) else real_path(*a)),
              mock.patch.object(ht, 'spawn', spawn),
              mock.patch.object(ht.time, 'monotonic', lambda: self.clock[0]),
              mock.patch.object(ht.time, 'sleep', lambda t: self.clock.__setitem__(0, self.clock[0] + t))):
      p.start()
      self.addCleanup(p.stop)
    self.power = ht.PortPower({'hub': 'PA40004', 'port': 3}, self.tmp / 'hil.log')

  def poll_at(self, t, state):
    self.clock[0] = t
    (self.port / 'state').write_text(state + '\n')
    self.power.poll()

  def disable(self):
    return (self.port / 'disable').read_text().strip()

  def test_the_hub_is_found_by_its_serial_and_cycled_after_two_stuck_seconds(self):
    for t, state in ((0, 'default'), (1.9, 'default'), (2.0, 'configured'), (2.1, 'default'), (4.0, 'default')):
      self.poll_at(t, state)
    self.assertEqual(self.writes, [])   # the configured sample restarted the 2 s
    self.poll_at(4.2, 'default')
    self.assertEqual(self.writes, [(4.2, '1'), (5.2, '0')])   # VBUS off for 1 s
    for t in (7.3, 9.4, 15.1):   # stuck again, but within GAP of the last cycle
      self.poll_at(t, 'default')
    self.assertEqual(len(self.writes), 2)
    self.poll_at(15.3, 'default')
    self.assertEqual((len(self.writes), self.power.cycles, self.disable()), (4, ['5-3-port3', '5-3-port3'], '0'))

  def test_a_new_wait_forgets_the_stuck_time_it_did_not_observe(self):
    self.poll_at(0, 'default')
    self.power.start()
    self.poll_at(100, 'default')
    self.assertEqual(self.writes, [])
    self.poll_at(102, 'default')
    self.assertEqual(len(self.writes), 2)

  def test_power_is_restored_after_a_failure_or_an_interruption_past_the_off_write(self):
    for what, fail, exc in (('interrupted while off', {2: ht.Interrupted()}, ht.Interrupted),
                            ('the on write timed out', {2: ht.StepFail('sh timed out after 15s')}, ht.StepFail),
                            ('the on read-back failed', {2: (1, '')}, ht.StepFail)):
      with self.subTest(what):
        self.writes.clear()
        self.fail.update(fail)
        self.power = ht.PortPower({'hub': 'PA40004', 'port': 3}, self.tmp / 'hil.log')
        self.poll_at(100, 'default')
        with self.assertRaises(exc):
          self.poll_at(102, 'default')
        self.assertEqual([v for _, v in self.writes][-1], '0')
        self.assertEqual((self.disable(), self.power.cycles), ('0', []))
    self.assertIn('power-on restored', (self.tmp / 'hil.log').read_text())

  def test_no_restore_while_an_interrupted_cycle_child_survives(self):
    disable = self.port / 'disable'
    child = mock.Mock(args=['sh', '-c', ht.PortPower.SET, 'sh', str(disable), '1'])
    for survivors, restored in (([4242], 'not attempted: a cycle child survived'), ([], 'power-on restored')):
      with self.subTest(survivors=survivors), mock.patch.object(ht, 'CHILDREN', [child]), \
           mock.patch.object(ht, 'reap', lambda p, s=survivors: s) as _:
        self.writes.clear()
        self.fail[1] = ht.Interrupted()   # the off write's child is left behind, as spawn leaves it
        self.power = ht.PortPower({'hub': 'PA40004', 'port': 3}, self.tmp / 'hil.log')
        self.poll_at(200, 'default')
        with self.assertRaises(ht.Interrupted):
          self.poll_at(202, 'default')
        self.assertEqual([v for _, v in self.writes], ['1'] if survivors else ['1', '0'])
        self.assertIn(restored, (self.tmp / 'hil.log').read_text().splitlines()[-1])

  def test_no_config_does_nothing_and_a_failed_restore_or_a_missing_hub_fails(self):
    ht.PortPower(None, None).poll()
    self.fail.update({1: (0, ''), 2: (1, ''), 3: (1, '')})   # off, on fails, the restore fails too
    self.poll_at(0, 'default')
    with self.assertRaisesRegex(ht.StepFail, 'could not power-cycle') as e:
      self.poll_at(2.0, 'default')
    self.assertIs(e.exception.evidence['restored'], False)
    self.assertIn('power-on NOT restored', (self.tmp / 'hil.log').read_text())
    with self.assertRaisesRegex(ht.StepFail, '0 USB hubs with serial GONE'):
      ht.PortPower({'hub': 'GONE', 'port': 3}, None).poll()

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
    for rel, data in (('tinyuf2.hex', b'hex'), ('tinyuf2.jlink', b'halt')):
      (build / rel).write_bytes(data)
      rows[rel] = ht.sha256(build / rel)
    (build / '_bin' / 'apps').mkdir()
    blinky = build / '_bin' / 'apps' / 'blinky.uf2'
    blinky.write_bytes(ht.pack_uf2([(0x6000C000, bytes(256)), (0x6000C100, bytes(256))], self.facts['family']))
    rows['_bin/apps/blinky.uf2'] = ht.sha256(blinky)
    now = {'head': 'h', 'submodules': {}, 'deps': {}, 'dirty': False}
    rec = self.tmp / 'rec.json'
    row = {'board': 'imxrt1060_evk', 'status': 'ok', 'backend': 'cmake', 'buildDir': str(build), 'sha256': rows,
           'flash': {'target': 'tinyuf2-jlink', 'flasher': {'name': 'jlink', 'uid': '2', 'device': 'MIMXRT1062xxx6A'},
                     'inputs': ['tinyuf2.jlink', 'tinyuf2.hex']}}
    rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [row]}))
    work = self.tmp / 'run'
    with mock.patch.object(ht.cb, 'identity', lambda ports: now):   # an absolute buildDir ignores cb.ROOT
      files, fw = ht.verify_record(rec, self.board, self.facts, work)
      self.assertEqual((files['bin'], fw['path'], fw['version']),
                       (work / 'record/_bin/tinyuf2.bin', str(build / '_bin/tinyuf2.bin'), '1.0'))
      self.assertEqual((files['hex'], files['flash']['root'], files['flash']['sha256']['tinyuf2.hex']),
                       (build / 'tinyuf2.hex', build, rows['tinyuf2.hex']))   # the HEX the target loads, not a copy
      self.assertNotIn('ninja', files['flash'])   # the install runs the provider's flash, never the target or a dry run
      for what, flash in (('another probe', dict(row['flash'], flasher={'name': 'jlink', 'uid': '9', 'device': 'MIMXRT1062xxx6A'})),
                          ('no binding', None)):
        with self.subTest(what), self.assertRaisesRegex(ht.Refused, 'not bound to this roster flasher'):
          rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [dict(row, flash=flash)]}))
          ht.verify_record(rec, self.board, self.facts, work)
      rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [row]}))
      self.assertEqual((files['blinky'], files['blinkyBlocks']), (work / 'record/_bin/apps/blinky.uf2', 2))
      good = blinky.read_bytes()
      for what, data in (('outside the app', ht.pack_uf2([(0x60000000, bytes(256))], self.facts['family'])),
                         ('another family', ht.pack_uf2([(0x6000C000, bytes(256))], 0x1234))):
        with self.subTest(what):
          blinky.write_bytes(data)
          rows['_bin/apps/blinky.uf2'] = ht.sha256(blinky)
          rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [dict(row, sha256=rows)]}))
          with self.assertRaisesRegex(ht.Refused, 'blinky.uf2: block 0'):
            ht.verify_record(rec, self.board, self.facts, work)
      blinky.write_bytes(good)
      rows['_bin/apps/blinky.uf2'] = ht.sha256(blinky)
      rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [dict(row, backend='make')]}))
      with self.assertRaisesRegex(ht.Refused, 'cmake builds only .*--backend cmake --shared'):
        ht.verify_record(rec, self.board, self.facts, work)
      rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [row]}))
      (build / '_bin' / 'tinyuf2.bin').unlink()
      with self.assertRaisesRegex(ht.Refused, 'tinyuf2.bin: missing'):
        ht.verify_record(rec, self.board, self.facts, work)
      self.assertEqual(files['bin'].read_bytes(), b'TinyUF2 Bootloader 1.0\r\n')   # verifybin's copy outlives a rebuild
    with mock.patch.object(ht.cb, 'identity', side_effect=ht.cb.Fail('git rev-parse HEAD failed')), \
         self.assertRaisesRegex(ht.Refused, 'cannot establish the checkout identity: git rev-parse'):
      ht.verify_record(rec, self.board, self.facts, work)


class EndChild(unittest.TestCase):
  def test_only_a_still_unreaped_child_is_signalled(self):
    gone = subprocess.Popen(['sleep', '30'])
    gone.kill()
    gone.wait()   # reaped, as a test's own cleanup may already have done: its number may be reused
    with mock.patch.object(os, 'kill') as kill:
      self.assertEqual((end_child(gone.pid), end_child(1)), (False, False))   # reaped; not a child
    kill.assert_not_called()
    live = subprocess.Popen(['sleep', '30'])
    self.assertTrue(end_child(live.pid))
    live.returncode = -signal.SIGKILL   # reaped by end_child


class SourceFacts(unittest.TestCase):
  def test_a_port_the_runner_has_no_facts_for_is_refused(self):
    with self.assertRaisesRegex(ht.Refused, 'ports/lpc55: the HIL runner has no source facts'):
      ht.source_facts({'port': 'lpc55', 'name': BOARD})

  def test_rt1060_facts_come_from_the_source(self):
    f = ht.source_facts(RT)
    self.assertEqual((f['flashBase'], f['appStart'], f['flashSize'], f['vid'], f['pid'], f['boardId']),
                     (0x60000000, 0x6000C000, 0x800000, 0x239a, 0x0083, 'MIMXRT1060-EVK-revA'))
    self.assertEqual((f['dblTapReg'], f['ram'], f['vectors']), (0x400D410C, 0x20000000, 174))   # SNVS LPGPR[3]
    self.assertEqual(f['family'], 0x4fb2d5bd)

  def test_rt1011_facts_put_the_bin_at_the_fcb(self):
    f = ht.source_facts({'port': 'mimxrt10xx', 'name': 'metro_m7_1011'})
    self.assertEqual((f['flashBase'], f['binBase'], f['appStart'], f['flashSize'], f['pid'], f['boardId']),
                     (0x60000000, 0x60000400, 0x6000C000, 0x800000, 0x00e1, 'MIMXRT1011-Metro-revA'))
    self.assertEqual((f['dblTapReg'], f['ram']), (0x400D410C, 0x20000000))
    self.assertEqual(ht.source_facts(RT)['binBase'], 0x60000000)

  def test_stm32f303disco_facts_come_from_the_source(self):
    f = ht.source_facts({'port': 'stm32f3', 'name': 'stm32f303disco'})
    self.assertEqual((f['flashBase'], f['binBase'], f['appStart'], f['flashSize'], f['vid'], f['pid'], f['boardId']),
                     (0x08000000, 0x08000000, 0x08004000, 0x40000, 0xcafe, 0xffff, 'STM32F303-Discovery-MB1035D'))
    # _board_dfu_dbl_tap = _estack, the last word of the 40K SRAM; FPU_IRQn = 81 is the highest IRQ
    self.assertEqual((f['dblTapReg'], f['ram'], f['vectors'], f['family']), (0x20009FFC, 0x20000000, 98, 0x6b846188))

  def test_stm32f411ve_discovery_facts_come_from_the_source(self):
    f = ht.source_facts({'port': 'stm32f4', 'name': 'stm32f411ve_discovery'})
    self.assertEqual((f['flashBase'], f['binBase'], f['appStart'], f['flashSize'], f['vid'], f['pid'], f['boardId']),
                     (0x08000000, 0x08000000, 0x08010000, 0x80000, 0x239a, 0x005d, 'STM32F411-Discovery-revA'))
    # _board_dfu_dbl_tap = _estack, the last word of the boot script's 64K RAM; SPI5_IRQn = 85 is the highest IRQ
    self.assertEqual((f['dblTapReg'], f['ram'], f['vectors'], f['family']), (0x2000FFFC, 0x20000000, 102, 0x57755a57))

  def test_an_stm32_board_needs_exactly_one_device_define_of_its_series(self):
    real = ht.cb.code_lines
    for port, board, text in (('stm32f4', 'stm32f411ve_discovery', 'STM32F411xE STM32F407xG'),
                              ('stm32f4', 'stm32f411ve_discovery', 'STM32F303xC'),
                              ('stm32f3', 'stm32f303disco', 'STM32F411xE')):
      fake = lambda path, text=text: text if Path(path).name == 'board.cmake' else real(path)
      with self.subTest(port=port, text=text), mock.patch.object(ht.cb, 'code_lines', side_effect=fake), \
           self.assertRaisesRegex(ht.Refused, f'expected one {port.upper()} device define'):
        ht.source_facts({'port': port, 'name': board})

  def test_linker_values_are_literal_sums_and_symbols_resolve_once(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    (Path(t.name) / 'a.ld').write_text(textwrap.dedent('''\
      _estack = ORIGIN(RAM) + LENGTH(RAM);   /* end of RAM */
      _board_dfu_dbl_tap = _estack;
      _loop = _loop2; _loop2 = _loop;
      _twice = 1; _twice = 2;
      _moved = 0x20009FFC; _moved -= 4;
      _shifted = 0x20009FFC; _shifted >>= 1;
      _shift = 1 << 4;
      MEMORY
      {
        FLASH (rx)  : ORIGIN = 0x8000000, LENGTH = 16K
        RAM (xrw)   : ORIGIN = 0x20000000, LENGTH = 40K - 4    /* reserve 4 bytes */
        RAM2 (xrw)  : ORIGIN = 0x10000000, LENGTH = 8K * 2
      }
      '''))
    with mock.patch.object(ht, 'ROOT', Path(t.name)):
      self.assertEqual(ht.ld_memory('a.ld', 'RAM'), (0x20000000, 40 * 1024 - 4))
      self.assertEqual(ht.ld_symbol('a.ld', '_board_dfu_dbl_tap'), 0x20009FFC)
      for what, call in (('product', lambda: ht.ld_memory('a.ld', 'RAM2')), ('no region', lambda: ht.ld_memory('a.ld', 'CCM')),
                         ('cycle', lambda: ht.ld_symbol('a.ld', '_loop')), ('twice', lambda: ht.ld_symbol('a.ld', '_twice')),
                         ('compound', lambda: ht.ld_symbol('a.ld', '_moved')), ('shift', lambda: ht.ld_symbol('a.ld', '_shift')),
                         ('compound shift', lambda: ht.ld_symbol('a.ld', '_shifted'))):
        with self.subTest(what), self.assertRaises(ht.Refused):
          call()

  def test_the_vector_count_takes_decimal_irqn_entries_only(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    enum = 'typedef enum {{\n  NonMaskableInt_IRQn = -14, /* = 200 */\n  USB_IRQn = 42,\n  {last}\n}} IRQn_Type;\n'
    with mock.patch.object(ht, 'ROOT', Path(t.name)):
      (Path(t.name) / 'ok.h').write_text(enum.format(last='FPU_IRQn = 81,   // last'))
      self.assertEqual(ht.vector_count('ok.h'), 98)
      for what, last in (('hex', 'FPU_IRQn = 0x51'), ('expression', 'FPU_IRQn = 80 + 1'), ('implicit', 'FPU_IRQn')):
        (Path(t.name) / 'bad.h').write_text(enum.format(last=last))
        with self.subTest(what), self.assertRaises(ht.Refused):
          ht.vector_count('bad.h')

  def test_the_linker_script_is_the_whole_script_argument(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    with mock.patch.object(ht, 'ROOT', Path(t.name)):
      (Path(t.name) / 'ok.txt').write_text('target_link_options(t PUBLIC "LINKER:--script=${CMAKE_CURRENT_LIST_DIR}/linker/a.ld")\n')
      self.assertEqual(ht.cmake_script('ok.txt'), './linker/a.ld')
      for what, arg in (('a longer name', 'a.ld.backup'), ('a variable suffix', 'a.ld${X}')):
        (Path(t.name) / 'bad.txt').write_text(f'target_link_options(t PUBLIC "LINKER:--script=${{CMAKE_CURRENT_LIST_DIR}}/{arg}")\n')
        with self.subTest(what), self.assertRaises(ht.Refused):
          ht.cmake_script('bad.txt')

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


def idf_build(root, parts=S3_PARTS, flash_args=None, sdk=None, board=S3, device='esp32s3',
              board_id='ESP32S3-DevKitC-v1.1', family=0xc47e5767):
  """A synthetic IDF build of the S3 DevKitC (or another board) as the port's CMakeLists lays it out, and its
  record row."""
  (root / '_bin').mkdir(parents=True)
  files = {'_bin/bootloader.bin': b'\xe9' + b'\0' * 0x5000,
           '_bin/tinyuf2.bin': b'\xe9' + b'TinyUF2 Bootloader 1.0\r\nBoard-ID: ' + board_id.encode() + b'\r\n' + b'\0' * 0x100,
           '_bin/partition-table.bin': partition_table(parts), '_bin/ota_data_initial.bin': b'\xff' * 0x2000,
           '_bin/flash_args': flash_args or ('--flash-mode dio --flash-freq 80m --flash-size 8MB\n0x0 bootloader/bootloader.bin\n'
                                             '0x410000 tinyuf2.bin\n0x8000 partition_table/partition-table.bin\n'
                                             '0xe000 ota_data_initial.bin\n'),
           'sdkconfig': sdk or ('CONFIG_IDF_TARGET="esp32s3"\nCONFIG_ESPTOOLPY_FLASHMODE="dio"\nCONFIG_ESPTOOLPY_FLASHFREQ="80m"\n'
                                'CONFIG_ESPTOOLPY_FLASHSIZE="8MB"\nCONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-8MB.csv"\n'
                                'CONFIG_PARTITION_TABLE_OFFSET=0x8000\n'),
           '_bin/apps/dfu_runtime.uf2': ht.pack_uf2([(256 * i, bytes([i]) * 256) for i in range(3)], family),
           '_bin/apps/blinky.uf2': ht.pack_uf2([(256 * i, bytes([0xb0 + i]) * 256) for i in range(2)], family)}
  (root / '_bin' / 'apps').mkdir()
  for rel in ht.cb.FLASH['esptool'][1]:   # what the flash target reads, as the build leaves it
    files[rel] = files['_bin/' + Path(rel).name]
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
  for rel, data in files.items():
    (root / rel).write_bytes(data if isinstance(data, bytes) else data.encode())
  return {'board': board, 'status': 'ok', 'backend': 'idf', 'buildDir': str(root),
          'sha256': {rel: ht.sha256(root / rel) for rel in files},
          'flash': {'target': 'flash', 'flasher': {'name': 'esptool', 'uid': 'cp2102n', 'device': device},
                    'inputs': list(ht.cb.FLASH['esptool'][1])}}


class EspCase(Tmp):
  """An esptool roster entry (`roster` overrides to s3_roster, board `name`) with its IDF record checks."""
  name, roster = S3, {}

  def setUp(self):
    super().setUp()
    self.board = self.load(s3_roster(self.tmp, **self.roster), self.name)
    self.facts = ht.source_facts(self.board)
    self.now = {'head': 'h', 'submodules': {}, 'deps': {}, 'dirty': False}

  def record(self, row, idf=None):
    rec = self.tmp / 'rec.json'
    rec.write_text(json.dumps({'pass': True, 'input': self.now, 'boards': [row],
                               'idf': idf or {'mode': 'docker', 'image': 'espressif/idf:v6.1'}}))
    return rec

  def verify(self, rec):
    with mock.patch.object(ht.cb, 'identity', lambda ports: self.now), \
         mock.patch.object(ht.cb, 'ci_idf_version', lambda: 'v6.1'):
      return ht.verify_record(rec, self.board, self.facts, self.tmp / 'run')


class Esp(EspCase):
  """The S3 DevKitC entry: esptool by the CP2102N's serial, facts from the IDF port's own files."""

  def test_the_facts_come_from_the_idf_port(self):
    f = self.facts
    self.assertEqual((f['flashSize'], f['partitionCsv'], f['partitions']), (0x800000, 'partitions-8MB.csv', S3_PARTS))
    self.assertEqual((f['vid'], f['pid'], f['boardId'], f['family'], f['detectionDelayMs']),
                     (0x239a, 0x00a5, 'ESP32S3-DevKitC-v1.1', 0xc47e5767, 500))
    self.assertEqual(f['flashCache'], 0x10000)
    self.assertEqual((self.board['flasher'], self.board['probe'], self.board['device']), ('esptool', 'cp2102n', 'esp32s3'))

  def test_the_layout_names_what_an_install_writes_and_what_is_preserved(self):
    lay = self.board['regions']
    self.assertEqual(lay['install'], {'bootloader.bin': (0, 0x8000), 'partition-table.bin': (0x8000, 0x9000),
                                      'ota_data_initial.bin': (0xe000, 0x10000), 'tinyuf2.bin': (0x410000, 0x450000)})
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
    build = self.tmp / 'b'
    row = idf_build(build)
    files, fw = self.verify(self.record(row))
    self.assertEqual([(off, p.name) for off, p in files['segments']],
                     [(0, 'bootloader.bin'), (0x8000, 'partition-table.bin'), (0xe000, 'ota_data_initial.bin'),
                      (0x410000, 'tinyuf2.bin')])
    self.assertEqual((fw['version'], fw['path']), ('1.0', str(build / 'tinyuf2.bin')))
    shutil.rmtree(build)   # a rebuild once the flash target's lock is released: the read-back and cleanup read copies
    for p in [p for _, p in files['segments']] + [files['blinky']]:
      rel = str(p.relative_to(self.tmp / 'run' / 'record'))
      self.assertEqual(ht.sha256(p), row['sha256'][rel])

  def test_idf_record_refusals(self):
    fa = ('--flash-mode dio --flash-freq 80m --flash-size 8MB\n0x0 bootloader/bootloader.bin\n0x410000 tinyuf2.bin\n'
          '0x8000 partition_table/partition-table.bin\n')
    cases = {
      'a local IDF': ({}, {'mode': 'local', 'image': 'espressif/idf:v6.1'}, 'CI\'s espressif/idf:v6.1 only'),
      'another image': ({}, {'mode': 'docker', 'image': 'espressif/idf:v5.4'}, 'only'),
      'a cmake build': ({'backend': 'cmake'}, None, 'idf builds only'),
      'a segment moved': ({'flash_args': fa.replace('0x410000', '0x400000') + '0xe000 ota_data_initial.bin\n'}, None,
                          'tinyuf2.bin .* is not at the start of its region \\[0x410000,0x450000\\)'),
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
    with self.assertRaisesRegex(ht.Refused, 'sdkconfig: missing, unreadable or changed'):
      self.verify(self.record(row))
    row = idf_build(self.tmp / 'c')
    (self.tmp / 'c' / 'tinyuf2.bin').write_bytes(b'changed')   # read by the flash target, not a _bin copy
    with self.assertRaisesRegex(ht.Refused, 'tinyuf2.bin: missing, unreadable or changed'):
      self.verify(self.record(row))

  def test_a_record_not_bound_to_the_roster_flasher_is_refused(self):
    for what, flash in (('no binding', None),
                        ('another bridge', {'flasher': {'name': 'esptool', 'uid': 'other', 'device': 'esp32s3'}}),
                        ('another target', {'target': 'combined-flash'})):
      with self.subTest(what), self.assertRaisesRegex(ht.Refused, 'not bound to this roster flasher'):
        row = idf_build(Path(tempfile.mkdtemp(dir=self.tmp)) / 'b')
        row['flash'] = flash and dict(row['flash'], **flash)
        self.verify(self.record(row))


P4 = 'espressif_p4_function_ev'
P4_PARTS = S3_PARTS[:5] + [('ffat', 1, 0x81, 0x450000, 0xbb0000)]
P4_FLASH_ARGS = ('--flash-mode dio --flash-freq 80m --flash-size 16MB\n0x2000 bootloader/bootloader.bin\n'
                 '0x410000 tinyuf2.bin\n0x8000 partition_table/partition-table.bin\n0xe000 ota_data_initial.bin\n')
P4_SDK = ('CONFIG_IDF_TARGET="esp32p4"\nCONFIG_ESPTOOLPY_FLASHMODE="dio"\nCONFIG_ESPTOOLPY_FLASHFREQ="80m"\n'
          'CONFIG_ESPTOOLPY_FLASHSIZE="16MB"\nCONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-16MB.csv"\n'
          'CONFIG_PARTITION_TABLE_OFFSET=0x8000\n')


class EspP4(EspCase):
  """The P4 Function EV entry: its 2nd-stage bootloader sits at 0x2000, below the partition table."""
  name = P4
  roster = {'name': P4, 'uid': '30EDA0E0C902', 'flasher': {'name': 'esptool', 'uid': 'cp2102n', 'args': '--chip esp32p4'}}

  def build(self, root, flash_args=P4_FLASH_ARGS):
    return idf_build(root, P4_PARTS, flash_args, P4_SDK, board=P4, device='esp32p4', board_id='ESP32P4-FunctionEV-v1.4',
                     family=0x3d308e94)

  def test_the_facts_come_from_the_idf_port(self):
    f = self.facts
    self.assertEqual((f['flashSize'], f['partitionCsv'], f['partitions']), (0x1000000, 'partitions-16MB.csv', P4_PARTS))
    self.assertEqual((f['vid'], f['pid'], f['boardId'], f['family']),
                     (0x239a, 0x00a5, 'ESP32P4-FunctionEV-v1.4', 0x3d308e94))
    self.assertEqual(self.board['device'], 'esp32p4')

  def test_the_layout_names_what_an_install_writes_and_what_is_preserved(self):
    lay = self.board['regions']
    self.assertEqual(lay['install'], {'bootloader.bin': (0x2000, 0x8000), 'partition-table.bin': (0x8000, 0x9000),
                                      'ota_data_initial.bin': (0xe000, 0x10000), 'tinyuf2.bin': (0x410000, 0x450000)})
    self.assertEqual(lay['preserved'], {'nvs': (0x9000, 0xe000), 'ota_1': (0x210000, 0x410000),
                                        'ffat': (0x450000, 0x1000000)})

  def test_an_idf_record_gives_the_four_segments_at_their_regions(self):
    files, _ = self.verify(self.record(self.build(self.tmp / 'b')))
    self.assertEqual([(off, p.name) for off, p in files['segments']],
                     [(0x2000, 'bootloader.bin'), (0x8000, 'partition-table.bin'), (0xe000, 'ota_data_initial.bin'),
                      (0x410000, 'tinyuf2.bin')])

  def test_a_bootloader_at_the_s3_offset_is_refused(self):
    row = self.build(self.tmp / 'b', P4_FLASH_ARGS.replace('0x2000 bootloader', '0x0 bootloader'))
    with self.assertRaisesRegex(ht.Refused, 'bootloader.bin .* is not at the start of its region \\[0x2000,0x8000\\)'):
      self.verify(self.record(row))


FAKE_ESP = textwrap.dedent('''
  import hashlib, json, os, sys
  args, ops = sys.argv[1:-1], json.load(open(sys.argv[-1]))
  img = os.environ['FAKE_ESP_FLASH']
  data = bytearray(open(img, 'rb').read())
  if os.environ.get('FAKE_ESP_FAIL'):
    print(json.dumps({'ok': False, 'error': os.environ['FAKE_ESP_FAIL'], 'results': []})); sys.exit(1)
  out = []
  for op in ops:
    k, r = op['op'], {'op': op['op']}
    if k == 'read': open(op['file'], 'wb').write(bytes(data[op['addr']:op['addr'] + op['size']]))
    elif k == 'md5': r['md5'] = hashlib.md5(bytes(data[op['addr']:op['addr'] + op['size']])).hexdigest()
    elif k == 'security': r.update(json.loads(os.environ.get('FAKE_ESP_SECURITY', json.dumps(
      {'flags': 0, 'flashCryptCnt': 0, 'rom': {'flashEncryption': 'off', 'secureBoot': 'off'},
       'efuse': {'flashEncryption': 'off', 'secureBoot': 'off'}}))))
    out.append(r)
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
    self.row = idf_build(self.tmp / 'b')
    self.segments = ht.esp.admit(self.tmp / 'b', self.board, self.facts, self.board['regions'])
    tty = self.tmp / 'ttyUSB0'
    tty.touch()
    real = ht.spawn
    self.targets = []
    for p in (mock.patch.object(ht, 'ESP_SESSION', fake), mock.patch.object(ht, 'esp_port', lambda uid: str(tty)),
              mock.patch.object(ht, 'spawn', lambda cmd, *a, **k: self.esptool(cmd, k) if cmd[0] == 'esptool'
                                else real(cmd, *a, **k)),
              mock.patch.dict(os.environ, {'FAKE_ESP_FLASH': str(self.flash)})):
      p.start()
      self.addCleanup(p.stop)
    self.work = self.tmp / 'run'
    self.work.mkdir()

  def sessions(self):
    return [json.loads(l) for l in (self.tmp / 'flash.img.sessions').read_text().splitlines()]

  def esptool(self, cmd, k):
    self.targets.append(([str(c) for c in cmd], k.get('cwd'), k.get('env')))
    return self.target(cmd)

  def target(self, cmd):
    """The provider's `esptool write_flash`: every segment written, FAKE_ESP_CORRUPT corrupting the segment at that
    offset and FAKE_ESP_SPILL a preserved byte, and the transcript's shape from the bench, CSI codes and the underscore
    spellings' warnings included (esptool 5.2.0 logger.py, cli_util.py)."""
    img, out = bytearray(self.flash.read_bytes()), ("\x1b[0;33mWarning:\x1b[0m Deprecated: Command 'write_flash' is "
                                                    "deprecated. Use 'write-flash' instead.\n")
    for off, path in self.segments:
      blob = path.read_bytes()
      if os.environ.get('FAKE_ESP_CORRUPT') == hex(off):
        blob = blob[:-1] + bytes([blob[-1] ^ 0xff])
      img[off:off + len(blob)] = blob
      if os.environ.get('FAKE_ESP_SPILL') and off == 0:
        img[0x9000] ^= 0xff
      out += (f'Writing at 0x{off:08x} [====] 100.0% \x1b[1A\x1b[2K\nWrote {len(blob)} bytes (9 compressed) at '
              f'0x{off:08x} in 0.1 seconds (100.0 kbit/s).\nHash of data verified.\n')
    self.flash.write_bytes(img)
    return 0, out + '\nHard resetting via RTS pin...\n'

  def files(self):
    root = self.tmp / 'b'
    return {'segments': self.segments,
            'flash': {'root': root, 'binding': {'target': 'flash'},
                      'sha256': {rel: ht.sha256(root / rel) for rel in ht.cb.FLASH['esptool'][1]}}}


class EspFlash(EspFake):
  """The esptool install."""

  def install(self):
    self.bat = ht.EspBattery(self.board, self.facts, self.work)
    return self.bat.install(self.files())

  def test_install_writes_the_segments_reads_them_back_and_keeps_the_preserved_regions(self):
    before = self.flash.read_bytes()
    ev = self.install()
    img = self.flash.read_bytes()
    for off, path in self.segments:
      self.assertEqual(img[off:off + path.stat().st_size], path.read_bytes())
    for lo, hi in self.board['regions']['preserved'].values():
      self.assertEqual(img[lo:hi], before[lo:hi])
    self.assertEqual(set(self.bat.preserved), {'nvs', 'ota_1', 'ffat'})
    snap, check = self.sessions()
    self.assertEqual((snap['ops'], snap['args'][-1]), (['md5'] * 3, 'no-reset'))
    self.assertEqual((check['ops'], check['args'][-1]), (['read'] * 4 + ['md5'] * 3, 'hard-reset'))
    self.assertIn('--chip', check['args'])
    # the runner's own esptool on the bridge's tty, from the build dir as flash_args names the segments; no container
    (argv, cwd, env), = self.targets
    root, tty = self.tmp / 'b', str(self.tmp / 'ttyUSB0')
    self.assertEqual(argv, ['esptool', '--chip', 'esp32s3', '-p', tty, '--before=default_reset', '--after=hard_reset',
                            'write_flash', *(root / 'flash_args').read_text().split()])
    self.assertEqual((cwd, env), (str(root), {'NO_COLOR': '1'}))
    self.assertEqual((ev['wrote'], ev['operation']), (['0x0', '0x8000', '0xe000', '0x410000'],
                                                     {'attempts': [{'kind': 'exited', 'exit': 0}], 'cleanup': 'done'}))
    self.assertEqual(ev['esptool'], ht.ESPTOOL_VERSION)

  def test_flash_args_are_read_under_the_build_lock_from_bytes_that_hash_as_recorded(self):
    fa, files = self.tmp / 'b' / 'flash_args', self.files()
    good = fa.read_text()
    fa.write_text(good.replace('0x410000', '0x400000'))   # a writer that finishes as the lock is taken
    take = ht.take_build_lock

    def taken(root):
      fa.write_text(good)
      return take(root)
    with mock.patch.object(ht, 'take_build_lock', taken):
      ht.EspBattery(self.board, self.facts, self.work).install(files)
    self.assertEqual(self.targets[0][0][8:], good.split())

  def test_flash_args_changed_after_the_hash_check_are_not_flashed(self):
    fa = self.tmp / 'b' / 'flash_args'
    check = ht.Battery.check_inputs

    def changed(flash, when, ev=None):
      check(flash, when, ev)
      if when == 'before the flash':
        fa.write_text(fa.read_text().replace('0x410000', '0x400000'))
    with mock.patch.object(ht.Battery, 'check_inputs', staticmethod(changed)), \
         self.assertRaisesRegex(ht.StepFail, 'flash_args changed'):
      self.install()
    self.assertEqual(self.targets, [])

  def test_a_session_that_fails_to_connect_writes_nothing(self):
    before = self.flash.read_bytes()
    with mock.patch.dict(os.environ, {'FAKE_ESP_FAIL': 'No serial data received.'}), \
         self.assertRaisesRegex(ht.StepFail, 'No serial data'):
      self.install()
    self.assertEqual((self.flash.read_bytes(), self.targets), (before, []))

  def test_no_tty_fails_before_any_session_and_leaves_the_board_untouched(self):
    def gone(uid):
      raise ht.StepFail('0 serial ports')
    with mock.patch.object(ht, 'esp_port', gone), self.assertRaisesRegex(ht.StepFail, '0 serial ports'):
      self.install()
    self.assertEqual((self.bat.touched, (self.tmp / 'flash.img.sessions').exists(), self.targets), (False, False, []))

  def test_a_bad_read_back_or_a_touched_preserved_region_fails_the_install(self):
    for env, err in (({'FAKE_ESP_CORRUPT': '0x410000'}, 'tinyuf2.bin does not read back as written'),
                     ({'FAKE_ESP_SPILL': '1'}, 'preserved region changed by the end of the install')):
      with self.subTest(err), mock.patch.dict(os.environ, env), self.assertRaisesRegex(ht.StepFail, err):
        self.install()

  def test_a_failed_or_timed_out_flash_fails_touched_with_its_operation(self):
    for what, result, err in (('exit 2', (2, 'A fatal error occurred: Failed to connect\n'), 'the esptool flash failed'),
                              ('timeout', ht.SpawnTimeout('esptool timed out', 'Writing at 0x00000000', []),
                               f'esptool timed out after {ht.ESP_TIMEOUT}s')):
      def esptool(cmd, k):
        self.targets.append(cmd)
        if isinstance(result, Exception):
          raise result
        return result
      with self.subTest(what), mock.patch.object(self, 'esptool', esptool), \
           self.assertRaisesRegex(ht.StepFail, err) as cm:
        self.install()
      self.assertTrue(self.bat.touched)
      self.assertEqual((cm.exception.evidence['beforeTarget'], cm.exception.evidence['operation']['attempts'][0]['kind']),
                       (False, 'exited' if what == 'exit 2' else 'timed_out'))

  def test_the_read_back_compares_the_preserved_regions_with_the_snapshot(self):
    tool, keep = ht.Esptool(self.board, self.work, self.work / 'hil.log'), self.board['regions']['preserved']
    snap = ht.preserved_md5(keep, tool.run(ht.preserved_ops(keep), 'no-reset'))
    self.target(['esptool'])
    ev = ht.esp_verify(tool, self.board, self.segments, self.work, snapshot=snap)
    self.assertEqual(ev['preserved'], snap)
    self.assertEqual(ev['writes'][-1], {'what': 'tinyuf2.bin', 'span': ['0x410000', hex(0x410000 + self.segments[-1][1].stat().st_size)],
                                        'blocks': ['0x410000', ev['writes'][-1]['blocks'][1]]})
    self.assertEqual(self.sessions()[-1]['ops'], ['read'] * 4 + ['md5'] * 3)
    with self.assertRaisesRegex(ht.StepFail, 'preserved region changed by the end of the install'):
      ht.esp_verify(tool, self.board, self.segments, self.work, snapshot=dict(snap, nvs='x'))

  def test_the_flash_transcript_must_show_every_segment_written_and_verified(self):
    out = self.target(['esptool'])[1]
    self.assertIn('\x1b[1A', out)
    self.assertEqual(ht.judge_esp_target(0, out, self.segments)['wrote'], ['0x0', '0x8000', '0xe000', '0x410000'])
    # a CSI code at a line's start would hide a write from a judge that strips only colour codes
    csi = out.replace('Wrote', '\x1b[2K\x1b[1AWrote')
    self.assertEqual(ht.judge_esp_target(0, csi, self.segments)['wrote'], ['0x0', '0x8000', '0xe000', '0x410000'])
    cases = (('a nonzero exit', 1, out), ('a segment missing', 0, out.replace('at 0x00008000 in', 'at 0x00009000 in')),
             ('a hash not verified', 0, out.replace('Hash of data verified.\n', '', 1)),
             ('no reset', 0, out.replace('Hard resetting via RTS pin...', '')), ('nothing', 0, ''))
    for what, code, text in cases:
      with self.subTest(what), self.assertRaisesRegex(ht.StepFail, 'the esptool flash failed'):
        ht.judge_esp_target(code, text, self.segments)

  def admitted(self):
    now = {'head': 'h', 'submodules': {}, 'deps': {}, 'dirty': False}
    rec = self.tmp / 'rec.json'
    rec.write_text(json.dumps({'pass': True, 'input': now, 'boards': [self.row],
                               'idf': {'mode': 'docker', 'image': 'espressif/idf:v6.1'}}))
    with mock.patch.object(ht.cb, 'identity', lambda ports: now), mock.patch.object(ht.cb, 'ci_idf_version', lambda: 'v6.1'):
      return ht.verify_record(rec, self.board, self.facts, self.work)[0]

  def test_an_admitted_record_installs_from_its_build_dir_without_a_container_or_a_dry_run(self):
    files = self.admitted()
    self.assertEqual(set(files['flash']), {'root', 'binding', 'sha256'})
    spawned = []
    real = ht.spawn
    self.bat = ht.EspBattery(self.board, self.facts, self.work)
    with mock.patch.object(ht, 'spawn', lambda cmd, *a, **k: (spawned.append(cmd[0]), real(cmd, *a, **k))[1]):
      self.assertTrue(self.bat.install(files)['readBack'])
    self.assertNotIn('docker', spawned)
    self.assertNotIn('ninja', spawned)
    self.assertEqual(self.targets[0][1], str(files['flash']['root']))

  def test_the_install_snapshot_round_trips_through_the_report(self):
    keep = self.board['regions']['preserved']
    md5 = ht.preserved_md5(keep, ht.Esptool(self.board, self.work, self.work / 'hil.log').run(ht.preserved_ops(keep), 'no-reset'))
    row = {'snapshot': {'preserved': md5, 'preservedRegions': {n: list(r) for n, r in keep.items()}},
           'cleanup': {'state': 'unknown'}}
    self.assertEqual(ht.report_snapshot(json.loads(json.dumps(row)), keep), md5)
    with self.assertRaisesRegex(ht.Refused, 'this checkout preserves'):
      ht.report_snapshot(json.loads(json.dumps(row)), {'nvs': (0x9000, 0xe000)})

  def test_a_malformed_snapshot_is_refused_not_coerced(self):
    good = {'nvs': [0x9000, 0xe000]}, {'nvs': 'ab' * 16}
    cases = {'empty': ({}, {}), 'zero length': ({'nvs': [0x9000, 0x9000]}, good[1]),
             'reversed': ({'nvs': [0xe000, 0x9000]}, good[1]), 'fractional': ({'nvs': [0x9000, 57344.5]}, good[1]),
             'a bool': ({'nvs': [False, 0xe000]}, good[1]), 'short md5': (good[0], {'nvs': 'ab'}),
             'upper-case md5': (good[0], {'nvs': 'AB' * 16}), 'names differ': (good[0], {'ffat': 'ab' * 16}),
             'past 4 GiB': ({'nvs': [0x9000, 1 << 32]}, good[1])}
    for what, (regions, md5) in cases.items():
      row = {'snapshot': {'preserved': md5, 'preservedRegions': regions},
             'cleanup': {'state': 'unknown'}}
      with self.subTest(what), self.assertRaisesRegex(ht.Refused, 'malformed'):
        ht.report_snapshot(json.loads(json.dumps(row)), good[0])

  def test_a_touched_run_without_a_snapshot_is_not_recovered(self):
    for state, want in (('unknown', ht.Refused), ('untouched', None)):
      row = {'snapshot': None, 'cleanup': {'state': state}}
      with self.subTest(state):
        if want:
          with self.assertRaisesRegex(ht.Refused, 'no preserved-region snapshot'):
            ht.report_snapshot(row, {})
        else:
          self.assertIsNone(ht.report_snapshot(row, {}))

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
    self.assertEqual(ht.tty_users(str(self.tmp / 'other'), str(dev)).count(p.pid), 1)   # either device, listed once

  def test_a_closing_fd_does_not_hide_the_process_others(self):
    dev = self.tmp / 'tty'
    dev.write_text('')
    p = subprocess.Popen([sys.executable, '-c', f'f = open({str(dev)!r}); import time; time.sleep(30)'])
    self.addCleanup(lambda: (p.kill(), p.wait()))
    readlink = os.readlink

    def closing(fd):   # stdin closes under the scan
      if str(fd) == f'/proc/{p.pid}/fd/0':
        raise FileNotFoundError(fd)
      return readlink(fd)
    with mock.patch.object(ht.os, 'readlink', closing):
      ht.wait_for(lambda: p.pid in ht.tty_users(str(dev)), 5, 'the holder')

  def main(self, *argv):
    out = io.StringIO()
    with mock.patch.object(ht, 'load_helper', mock.Mock), mock.patch.object(ht, 'manual_holder', mock.Mock()), \
         mock.patch.object(ht.cb, 'BUILD_DIR', Path(tempfile.mkdtemp(dir=self.tmp))), contextlib.redirect_stdout(out):
      code = ht.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])

  def test_an_esptool_install_takes_a_build_record_and_a_run_only_esptool_steps_and_methods(self):
    cfg = str(s3_roster(self.tmp))
    code, res = self.main('run', '-b', S3, '--build-record', 'rec.json', cfg)
    self.assertEqual(code, 2)
    self.assertIn('cannot read build record', res['error'])
    unset = str(s3_roster(self.tmp, tinyuf2={}))
    code, res = self.main('run', '-b', S3, '--build-record', 'rec.json', '--try-reentry', 'retained-register', unset)
    self.assertEqual(code, 2)
    self.assertIn("re-enters by one of ('dfu-detach',)", res['error'])

  def test_a_run_refuses_a_route_pending_commissioning_or_unknown_before_any_board_access(self):
    cfg = str(s3_roster(self.tmp, tinyuf2={'reentry': 'dfu-detach', 'routes': [{'flasher': {
      'name': 'openocd_esp', 'uid': 'AA:BB:CC:DD:EE:FF', 'args': '-f board/esp32s3-builtin.cfg'}, 'commissioning': 'pending'}]}))
    for route, err in (('openocd_esp', 'pending commissioning'), ('pyocd', 'no install route pyocd')):
      with self.subTest(route), mock.patch.object(ht, 'run_board', side_effect=AssertionError('board access')):
        code, res = self.main('run', '-b', S3, '--build-record', 'rec.json', '--route', route, cfg)
      self.assertEqual(code, 2)
      self.assertIn(err, res['error'])

  def test_the_esptool_version_and_the_command_the_provider_runs_are_gated(self):
    def missing(name):
      raise importlib.metadata.PackageNotFoundError(name)
    for what, version in (('wrong version', lambda name: '4.8.1'), ('absent', missing)):
      with self.subTest(what), mock.patch('importlib.metadata.version', version), \
           self.assertRaisesRegex(ht.Refused, 'the runner needs esptool 5.2.0'):
        ht.check_esptool()
    bindir = self.tmp / 'bin'
    bindir.mkdir()
    venv = self.tmp / 'venv' / 'bin'
    venv.mkdir(parents=True)
    (venv / 'python3').symlink_to(sys.executable)   # a venv's python links out of the venv
    script = bindir / 'esptool'
    cases = (('this python', f'#!{sys.executable}\n', None), ('another python', f'#!{venv / "python3"}\n', 'does not run under'),
             ('another python in its directory', f'#!{Path(sys.executable).with_name("python-other")}\n', 'does not run under'),
             ('no shebang', 'import esptool\n', 'does not run under'), ('not on PATH', None, 'does not run under'))
    for what, head, err in cases:
      if head is None:
        script.unlink(missing_ok=True)
      else:
        script.write_text(head)
        script.chmod(0o755)
      with self.subTest(what), mock.patch('importlib.metadata.version', lambda name: '5.2.0'), \
           mock.patch.object(ht.shutil, 'which', lambda n: str(script) if script.exists() else None):
        if err:
          with self.assertRaisesRegex(ht.Refused, err):
            ht.check_esptool()
        else:
          ht.check_esptool()


USJ = 'AA:BB:CC:DD:EE:FF'
ROUTE = {'flasher': {'name': 'openocd_esp', 'uid': USJ, 'args': '-f board/esp32s3-builtin.cfg'}, 'commissioning': 'pending'}
# agentrc's own openocd-esp32 stand-in and fake sysfs bus, from the pinned checkout's tests of the provider
_ag = importlib.util.spec_from_file_location('agentrc_test_openocd_esp', ROOT / 'lib/agentrc/tests/test_hil_openocd_esp.py')
AG = importlib.util.module_from_spec(_ag)
_ag.loader.exec_module(AG)


def route_roster(tmp, **route):
  return s3_roster(tmp, tinyuf2={'reentry': 'dfu-detach', 'routes': [dict(ROUTE, **route)]})


class RouteRoster(Tmp):
  """tinyuf2.routes: an Espressif board's openocd_esp route, under the board's own lock, chosen before board access."""

  def setUp(self):
    super().setUp()
    no_ci_job(self)

  def test_the_route_is_refused_under_a_ci_job_before_any_board_access(self):
    b = self.load(route_roster(self.tmp), S3)
    for var, value in (('RUNNER_TRACKING_ID', ''), ('GITHUB_ACTIONS', 'true')):
      with self.subTest(var), mock.patch.dict(os.environ, {var: value}):
        with self.assertRaisesRegex(ht.Refused, rf'under a CI job \({var} set\)'):
          ht.select_route(b, 'openocd_esp')
        self.assertIs(ht.select_route(b, 'esptool'), b)   # not an openocd_esp session
    self.assertEqual(ht.select_route(b, 'openocd_esp')['flasher'], 'openocd_esp')

  def test_a_route_loads_and_a_chosen_one_selects_the_flash_and_the_esptool_tty(self):
    b = self.load(route_roster(self.tmp), S3)
    self.assertEqual(b['routes'], {'openocd_esp': {'flasher': ROUTE['flasher'], 'pending': True}})
    self.assertIs(ht.select_route(b, None), b)
    self.assertIs(ht.select_route(b, 'esptool'), b)
    r = ht.select_route(b, 'openocd_esp')
    self.assertEqual((r['flasher'], r['probe'], r['route'], r['kind'], r['lock']),
                     ('openocd_esp', USJ, ROUTE['flasher'], 'esp', b['lock']))   # one lock for both routes
    with self.assertRaisesRegex(ht.Refused, 'pending commissioning: install and restore only'):
      ht.select_route(b, 'openocd_esp', run=True)
    commissioned = self.load(s3_roster(self.tmp, tinyuf2={'reentry': 'dfu-detach', 'routes': [{'flasher': ROUTE['flasher']}]}), S3)
    self.assertEqual(ht.select_route(commissioned, 'openocd_esp', run=True)['flasher'], 'openocd_esp')
    with self.assertRaisesRegex(ht.Refused, 'no install route jlink'):
      ht.select_route(b, 'jlink')

  def test_route_refusals(self):
    fl = ROUTE['flasher']
    cases = {'not espressif': (roster(self.tmp, tinyuf2={'reentry': 'retained-register', 'routes': [ROUTE]}), BOARD),
             'another chip': (route_roster(self.tmp, flasher=dict(fl, args='-f board/esp32p4-builtin.cfg')), S3),
             'a selector in args': (route_roster(self.tmp, flasher=dict(fl, args='-f board/esp32s3-builtin.cfg -c init')), S3),
             'another backend': (route_roster(self.tmp, flasher=dict(fl, name='openocd')), S3),
             'a vid_pid': (route_roster(self.tmp, flasher=dict(fl, vid_pid='0x303a 0x1001')), S3),
             'an odd uid': (route_roster(self.tmp, flasher=dict(fl, uid='x;shutdown')), S3),
             'another state': (route_roster(self.tmp, commissioning='done'), S3),
             'an unknown key': (route_roster(self.tmp, lock='x'), S3),
             'twice': (s3_roster(self.tmp, tinyuf2={'reentry': 'dfu-detach', 'routes': [ROUTE, ROUTE]}), S3),
             'not a list': (s3_roster(self.tmp, tinyuf2={'reentry': 'dfu-detach', 'routes': ROUTE}), S3)}
    for what, (cfg, name) in cases.items():
      with self.subTest(what), self.assertRaises(ht.Refused):
        ht.load_board(cfg, name)

  def test_the_p4_roster_entry_is_a_commissioned_openocd_esp_route_of_its_board(self):
    b = ht.load_board(ROOT / 'test/hil/local.json', 'espressif_p4_function_ev')
    self.assertEqual(b['routes'], {'openocd_esp': {'flasher': {'name': 'openocd_esp', 'uid': '30:ED:A0:E0:C9:02',
                                                               'args': '-f board/esp32p4-builtin.cfg'}, 'pending': False}})

  def test_the_route_needs_the_verified_openocd_and_the_runners_esptool(self):
    b = ht.select_route(self.load(route_roster(self.tmp), S3), 'openocd_esp')
    with mock.patch.object(ht, 'check_esptool'), \
         mock.patch.object(ht.openocd_esp(), 'find_openocd', side_effect=RuntimeError('openocd not found')), \
         self.assertRaisesRegex(ht.Refused, 'openocd not found'):
      ht.check_flasher(b)

  def test_the_probe_check_sees_the_usj_tty_and_usbfs_node_users(self):
    with mock.patch.object(AG, 'oe', ht.openocd_esp()):
      AG.FakeBus(self).add('5-3.4', USJ, bus=5, dev=14)
    b = ht.select_route(self.load(route_roster(self.tmp), S3), 'openocd_esp')
    seen = []
    with mock.patch.object(ht, 'esp_port', lambda uid: f'/dev/tty-{uid}'), \
         mock.patch.object(ht, 'tty_users', lambda *devs: seen.append(devs) or [7]):
      self.assertEqual(ht.probe_users(b), [7])
    self.assertEqual(seen, [(f'/dev/tty-{USJ}', '/dev/bus/usb/005/014')])   # one walk for both


class JtagAdmission(EspCase):
  """A record binds the openocd_esp route to the segments its esptool binding hashed (check_build flashRoutes)."""
  roster = {'tinyuf2': {'reentry': 'dfu-detach', 'routes': [ROUTE]}}

  def setUp(self):
    super().setUp()
    no_ci_job(self)
    self.board = ht.select_route(self.board, 'openocd_esp')

  def row(self, root, **binding):
    row = idf_build(root)
    row['flashRoutes'] = {'openocd_esp': dict({'flasher': {'name': 'openocd_esp', 'uid': USJ, 'device': 'esp32s3'},
                                                'inputs': list(ht.cb.FLASH['esptool'][1])}, **binding)}
    return row

  def test_a_bound_record_gives_the_hashed_segments(self):
    files, _ = self.verify(self.record(self.row(self.tmp / 'b')))
    self.assertEqual(files['flash']['binding']['flasher']['name'], 'openocd_esp')
    self.assertEqual(sorted(files['flash']['sha256']), sorted(ht.cb.FLASH['esptool'][1]))
    self.assertEqual([off for off, _ in files['segments']], [0, 0x8000, 0xe000, 0x410000])

  def test_a_record_not_bound_to_this_route_is_refused(self):
    fl = {'name': 'openocd_esp', 'uid': USJ, 'device': 'esp32s3'}
    for i, (what, over) in enumerate((('another USJ', {'flasher': dict(fl, uid='00:11:22:33:44:55')}),
                                      ('another chip', {'flasher': dict(fl, device='esp32p4')}),
                                      ('a segment missing', {'inputs': list(ht.cb.FLASH['esptool'][1])[:-1]}),
                                      ('no route', None))):
      with self.subTest(what), self.assertRaisesRegex(ht.Refused, 'not bound to this roster flasher'):
        row = self.row(self.tmp / f'b{i}', **(over or {}))
        if over is None:
          del row['flashRoutes']   # an esptool binding alone
        self.verify(self.record(row))

  def test_a_stale_segment_is_refused(self):
    row = self.row(self.tmp / 'b')
    (self.tmp / 'b' / 'tinyuf2.bin').write_bytes(b'rebuilt')
    with self.assertRaisesRegex(ht.Refused, 'tinyuf2.bin: missing, unreadable or changed'):
      self.verify(self.record(row))


class JtagRoute(EspFake):
  """The JTAG route's install over agentrc's flash_openocd_esp and its openocd-esp32 stand-in, the esptool sessions
  over the fake session helper, both on one flash image and one event log: plumbing only, never a live session."""

  def setUp(self):
    super().setUp()
    no_ci_job(self)
    self.board = ht.select_route(self.load(route_roster(self.tmp), S3), 'openocd_esp')
    self.mark = self.board['pendingMark'] = ht.PendingMark(None, 'b')
    exe, _ = AG.fake_install(self.tmp / 'oocd', chips=('esp32s3',), tool=AG.FAKE_OPENOCD)
    with mock.patch.object(AG, 'oe', ht.openocd_esp()):
      AG.FakeBus(self).add('5-3.4', USJ)
    for p in (mock.patch.dict(os.environ, {'HIL_OPENOCD_ESP': str(exe), 'FAKE_BANNER': AG.BANNER,
                                           'FAKE_EVENTS': str(self.flash) + '.sessions', 'FAKE_FLASH': str(self.flash),
                                           'FAKE_BANK_SIZE': hex(0x800000)}),
              mock.patch.object(ht, 'OPENOCD_TIMEOUT', 3), mock.patch.object(ht, 'OPENOCD_BOOT_SETTLE', 0),
              mock.patch.object(ht.openocd_esp(), 'CLEANUP_TIMEOUT', 3)):
      p.start()
      self.addCleanup(p.stop)
    self.addCleanup(self.kill_fakes)
    # the provider leaves a pending session's Popen unwaited, by design; the stand-in is ended at cleanup
    self.enterContext(warnings.catch_warnings())
    warnings.simplefilter('ignore', ResourceWarning)

  def kill_fakes(self):   # the stand-in ignores SIGTERM, as the runner must never signal openocd; the test ends it
    for e in self.events():
      if 'pid' in e:
        with contextlib.suppress(ProcessLookupError):
          os.kill(e['pid'], signal.SIGKILL)

  def events(self):
    path = self.tmp / 'flash.img.sessions'
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

  def install(self):
    self.bat = ht.EspBattery(self.board, self.facts, self.work)
    return self.bat.install(self.files())

  def test_security_and_snapshot_then_jtag_program_and_read_back_then_esptool_preservation_check(self):
    before = self.flash.read_bytes()
    ev = self.install()
    log = self.events()
    order = ['esptool' if 'ops' in e else e['tcl'].split()[0] for e in log if 'ops' in e or e.get('tcl', 'token?') != 'token?']
    cpus = ['esp32p4.hp.cpu0'] * 2 + ['esp32p4.hp.cpu1'] * 2   # each -work-area-backup saved, then cleared
    self.assertEqual(order, ['esptool', 'init', 'reset', 'flash', 'flash', 'target', *cpus, 'esp', 'esp', 'esp',
                             *['check_image_revision', 'flash', 'esp'] * 4, 'esp32p4.hp.cpu0', 'esp32p4.hp.cpu1',
                             'flash', 'flash', 'flash', 'flash', 'reset', 'shutdown', 'esptool'])
    snap, check = [e for e in log if 'ops' in e]
    self.assertEqual((snap['ops'], snap['args'][-1]), (['security'] + ['md5'] * 3, 'hard-reset'))   # one ROM-loader session
    self.assertEqual((check['ops'], check['args'][-1]), (['read'] * 4 + ['md5'] * 3, 'hard-reset'))
    self.assertFalse([e for e in log if 'signal' in e])
    img = self.flash.read_bytes()
    for off, path in self.segments:
      self.assertEqual(img[off:off + path.stat().st_size], path.read_bytes())
    for lo, hi in self.board['regions']['preserved'].values():
      self.assertEqual(img[lo:hi], before[lo:hi])
    self.assertEqual((ev['route'], ev['wrote'], ev['readBack'], ev['operation']['cleanup']),
                     ('openocd_esp', ['0x0', '0x8000', '0xe000', '0x410000'], True, 'done'))
    self.assertEqual((ev['security']['flashEncryption'], ev['security']['secureBoot']), ('off', 'off'))
    self.assertIn('ROM loader', ev['security']['source'])
    self.assertEqual(ht.outstanding_sessions(self.work), [])

  def test_security_not_read_off_or_a_failed_snapshot_programs_nothing(self):
    on = {'flags': 1, 'flashCryptCnt': 1, 'rom': {'flashEncryption': 'on', 'secureBoot': 'on'},
          'efuse': {'flashEncryption': 'on', 'secureBoot': 'on'}}
    disagree = dict(on, flags=0, flashCryptCnt=0, rom={'flashEncryption': 'off', 'secureBoot': 'off'},
                    efuse={'flashEncryption': 'off', 'secureBoot': 'on'})
    for what, env, err in (('on', {'FAKE_ESP_SECURITY': json.dumps(on)}, 'not read off'),
                           ('sources disagree', {'FAKE_ESP_SECURITY': json.dumps(disagree)}, 'not read off'),
                           ('snapshot fails', {'FAKE_ESP_FAIL': 'No serial data received.'}, 'No serial data')):
      before = self.flash.read_bytes()
      with self.subTest(what), mock.patch.dict(os.environ, env), self.assertRaisesRegex(ht.StepFail, err):
        self.install()
      self.assertEqual((self.flash.read_bytes(), [e for e in self.events() if 'argv' in e]), (before, []))
      self.assertTrue(self.bat.touched)

  def pending(self, err, **env):
    root = self.files()['flash']['root']
    with mock.patch.dict(os.environ, env), self.assertRaisesRegex(ht.CleanupPending, err) as cm:
      self.install()
    left = ht.outstanding_sessions(self.work)
    self.assertEqual(len(left), 1)
    self.assertIsNotNone(ht.proc_stat(left[0]['pid']))   # never signalled, never reaped
    self.assertEqual(ht.settle_children(), [])
    self.assertIsNotNone(ht.proc_stat(left[0]['pid']))
    self.assertFalse([e for e in self.events() if 'signal' in e])
    # the build dir stays locked, by a keeper, while the session runs (#579)
    self.assertEqual([k['survivors'] for k in self.bat.kept], [left])
    with self.assertRaises(BlockingIOError), ht.cb.build_lock(root, wait=False):
      pass
    # no later session: read-back, restore and retry are refused
    for later in (lambda: self.bat.tool.run(ht.preserved_ops(self.board['regions']['preserved']), 'hard-reset'),
                  lambda: self.bat.install(self.files())):
      with self.assertRaisesRegex(ht.CleanupPending, 'no session may overlap it'):
        later()
    # another invocation, in a run dir of its own, refuses before any session (#2)
    with self.assertRaisesRegex(ht.Refused, 'not ended'):
      ht.clear_pending_mark(self.mark)
    os.kill(left[0]['pid'], signal.SIGKILL)   # stands for the server exiting
    ht.wait_for(lambda: ht.flock_free(Path(str(root) + '.lock')), 10, 'the keeper releasing the build lock')
    # gone without the reviewed end: still not ended, for a separately reviewed recovery
    self.assertEqual([ht.session_state(e) for e in ht.outstanding_sessions(self.work)], ['unresolved'])
    with self.assertRaisesRegex(ht.Refused, 'not ended'):
      ht.clear_pending_mark(self.mark)
    if isinstance(left[0]['receipt'], str):   # what `hil_openocd_esp.py end` leaves: closed after the reviewed end
      rec = json.loads(Path(left[0]['receipt']).read_text())
      Path(left[0]['receipt']).write_text(json.dumps(dict(rec, closed=True, cleanup='done')))
      self.assertEqual(ht.outstanding_sessions(self.work), [])
      ht.clear_pending_mark(self.mark)
      self.assertFalse(Path(self.mark).exists())
    return cm.exception

  def test_the_provider_starts_at_least_the_settle_time_after_the_esptool_session(self):
    ended, started = [], []
    run, flash = ht.Esptool.run, ht.openocd_esp().flash_openocd_esp
    with mock.patch.object(ht.Esptool, 'run', lambda *a: (run(*a), ended.append(time.monotonic()))[0]), \
         mock.patch.object(ht.openocd_esp(), 'flash_openocd_esp',
                           lambda *a, **k: (started.append(time.monotonic()), flash(*a, **k))[1]), \
         mock.patch.object(ht, 'OPENOCD_BOOT_SETTLE', 0.2):
      self.install()
      self.assertGreaterEqual(started[0] - ended[0], ht.OPENOCD_BOOT_SETTLE)

  def test_a_ci_job_is_refused_before_the_security_and_snapshot_session(self):
    with mock.patch.dict(os.environ, {'GITHUB_ACTIONS': ''}), mock.patch.object(ht.Esptool, 'run') as run, \
         self.assertRaisesRegex(ht.Refused, 'under a CI job'):
      self.install()
    self.assertEqual((run.call_count, self.bat.touched, self.events()), (0, False, []))

  def test_a_timeout_while_programming_leaves_cleanup_pending(self):
    with mock.patch.object(ht, 'OPENOCD_TIMEOUT', 0.7), mock.patch.object(ht.openocd_esp(), 'CLEANUP_TIMEOUT', 0.7):
      e = self.pending('cleanup pending', FAKE_SCRIPT=json.dumps({'flash#3': 'hang'}))   # the first write; each bound expires
    self.assertEqual(e.evidence['operation']['cleanup'], 'pending')

  def test_a_server_answering_another_token_is_never_driven_and_is_left_pending(self):
    self.pending('cleanup pending', FAKE_OTHER_TOKEN='f00f')
    self.assertFalse([e for e in self.events() if e.get('tcl') not in (None, 'token?')])

  def test_a_session_whose_receipt_could_not_be_written_is_still_protected(self):
    es = ht.openocd_esp().esp_session   # the provider writes every receipt through it
    write = es.write_receipt

    def failing(path, rec):
      if not rec.get('closed') and rec.get('submitted') == 0:
        raise OSError(28, 'No space left on device')
      return write(path, rec)
    with mock.patch.object(es, 'write_receipt', failing):
      e = self.pending('cleanup pending')
    self.assertEqual(ht.outstanding_sessions(self.work)[0]['receipt']['tool'], 'hil_openocd_esp')   # the record
    self.assertFalse(list(self.work.glob(ht.OPENOCD_SESSIONS)))
    self.assertEqual(e.evidence['operation']['cleanup'], 'pending')

  def test_a_failed_shutdown_leaves_cleanup_pending(self):
    with mock.patch.object(ht.openocd_esp(), 'CLEANUP_TIMEOUT', 0.7):   # the bound the ignored shutdown expires
      self.pending('cleanup pending', FAKE_IGNORE_SHUTDOWN='1')

  def test_a_failed_program_ends_the_session_in_order_and_fails_the_install(self):
    # esp#5: after the three esp setup commands and the first verify, the second segment's verify
    with mock.patch.dict(os.environ, {'FAKE_SCRIPT': json.dumps({'esp#5': 'err:hash mismatch'})}), \
         self.assertRaisesRegex(ht.StepFail, 'the openocd_esp flash failed') as cm:
      self.install()
    self.assertNotIsInstance(cm.exception, ht.CleanupPending)
    self.assertEqual([e['tcl'] for e in self.events() if e.get('tcl') in ('reset run', 'shutdown')], ['reset run', 'shutdown'])
    self.assertEqual((ht.outstanding_sessions(self.work), self.bat.kept), ([], []))

  def test_only_a_clean_exit_with_every_segment_verified_and_read_back_passes(self):
    seg = {'offset': 0, 'program': {'verified': True}, 'readBack': {'match': True}}
    op = mock.Mock(returncode=0, cleanup='done', segments=(seg,), session={'openocd': 'o', 'location': '5-3.4', 'log': 'l'})
    self.assertEqual(ht.judge_openocd_esp(op)['wrote'], ['0x0'])
    for what, over in (('raised after the start', {'returncode': None}), ('cleanup unknown', {'cleanup': 'unknown'}),
                       ('no segments', {'segments': ()}),
                       ('a read-back mismatch', {'segments': (dict(seg, readBack={'match': False}),)})):
      with self.subTest(what), self.assertRaisesRegex(ht.StepFail, 'the openocd_esp flash failed'):
        ht.judge_openocd_esp(mock.Mock(**dict(dict(returncode=0, cleanup='done', segments=(seg,), session={}), **over)))

  def test_an_interrupt_while_programming_unwinds_with_the_session_kept_for_cleanup(self):
    handler = signal.signal(signal.SIGTERM, ht.on_signal)
    mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, ht.TERM_SIGNALS)
    self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, mask)
    self.addCleanup(signal.signal, signal.SIGTERM, handler)
    real = ht.openocd_esp().flash_openocd_esp

    def signalled(*a, **k):
      sessions = self.tmp / 'flash.img.sessions'
      sigterm_when(lambda: sessions.exists() and 'write_image' in sessions.read_text(), 'the hanging write')
      return real(*a, **k)
    with mock.patch.dict(os.environ, {'FAKE_SCRIPT': json.dumps({'flash#3': 'hang'})}), \
         mock.patch.object(ht, 'OPENOCD_TIMEOUT', 30), mock.patch.object(ht.openocd_esp(), 'flash_openocd_esp', signalled), \
         self.assertRaises(ht.Interrupted) as cm:
      self.install()
    self.assertEqual(cm.exception.operation.cleanup, 'pending')
    left = ht.outstanding_sessions(self.work)
    self.assertEqual(([k['survivors'] for k in self.bat.kept], len(left)), ([left], 1))
    self.assertFalse([e for e in self.events() if 'signal' in e])

  def test_an_interrupt_while_the_server_registers_still_leaves_its_receipt(self):
    handler = signal.signal(signal.SIGTERM, ht.on_signal)
    mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, ht.TERM_SIGNALS)
    self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, mask)
    self.addCleanup(signal.signal, signal.SIGTERM, handler)
    oe = ht.openocd_esp()
    start_time = oe.esp_session.start_time

    def signal_at_registration(pid):   # inside the provider's hold, between the spawn and the receipt
      os.kill(os.getpid(), signal.SIGTERM)
      return start_time(pid)
    with mock.patch.object(oe.esp_session, 'start_time', signal_at_registration), self.assertRaises(ht.Interrupted):
      self.install()
    left = ht.outstanding_sessions(self.work)
    self.assertEqual(len(left), 1)
    self.assertEqual([k['survivors'] for k in self.bat.kept], [left])


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
      def change_baud(self, b): log('baud', b)
      def read_flash(self, addr, size):
        if os.environ.get('STUB_FAIL_READ'): raise IOError('timed out')
        return bytes([addr & 0xff]) * size
      def flash_md5sum(self, addr, size): return f'md5-{addr:x}-{size:x}'
      IS_STUB = bool(os.environ.get('STUB_IS_STUB'))
      SEC = json.loads(os.environ.get('STUB_SECURITY', '[0, 0, 0, 0]'))   # flags, flash_crypt_cnt, eFuse FE, eFuse SB
      def get_security_info(self, cache=True):
        log('security', cache)
        return {'flags': self.SEC[0], 'flash_crypt_cnt': self.SEC[1], 'parsed_flags': {'SECURE_BOOT_EN': bool(self.SEC[0] & 1)}}
      def get_flash_encryption_enabled(self): log('efuse'); return bin(self.SEC[2]).count('1') % 2 == 1
      def get_secure_boot_enabled(self): return self.SEC[3] << 20
    def detect_chip(port, connect_mode):
      log('connect', port, connect_mode); return Esp()
    def run_stub(esp): log('stub'); return esp
    def attach_flash(esp): log('attach')
    def reset_chip(esp, mode): log('reset', mode)
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

  def spawn(self, cmd, log, timeout, cwd=None, **k):
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
      blk = self.stale or self.app.get(self.bat.nonce_off, b'')
      return 0, json.dumps({'ok': True, 'interface': 0, 'string': f'HIL {blk[12:28].hex()}'})
    code, out = self.real_spawn(cmd, log, timeout, cwd, **k)
    if cmd[0] == 'esptool':
      self.on = 'dfu'   # esptool's hard reset; blank otadata boots the factory app: TinyUF2
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
    files = {**self.files(), **ht.esp_app_chunks(self.tmp / 'b' / ht.esp.APP_UF2, self.facts, self.board),
             **ht.check_blinky(self.tmp / 'b' / ht.esp.BLINKY_UF2, (0, 0x200000), self.facts)}
    return bat, rig, files

  def test_every_step_passes_with_a_fresh_nonce_per_copy(self):
    bat, rig, files = self.battery()
    bat.run(files, 'v1')
    self.assertEqual([x['step'] for x in bat.steps if x['pass']], list(ht.STEPS['esp']))
    ev = {x['step']: x['evidence'] for x in bat.steps}
    self.assertEqual(ev['app-ran']['string'], f'HIL {ev["copy"]["nonce"]}')
    self.assertEqual(ev['recopy']['string'], f'HIL {ev["recopy"]["nonce"]}')
    self.assertNotEqual(ev['copy']['nonce'], ev['recopy']['nonce'])
    self.assertTrue(all(ev['reenter'][k] is True for k in ('detachAcked', 'appLeft', 'dfuCameUp', 'appIntact')))
    self.assertEqual(ev['dfu']['claim'], 'DFU observed')
    for blocks in rig.copied:
      self.assertEqual([(b['no'], b['total']) for b in blocks], [(i, len(blocks)) for i in range(len(blocks))])
      self.assertEqual((blocks[-1]['addr'], blocks[-1]['data'][:8]), (0x1fff00, b'TUF2NONC'))
    self.assertEqual(ev['copy']['writes'][1], {'what': 'nonce block', 'span': ['0x1fff00', '0x200000'],
                                               'blocks': ['0x1f0000', '0x200000']})
    self.assertEqual(ev['copy']['writes'][0]['blocks'][0], '0x0')
    self.assertEqual(set(bat.report_fields()['snapshot']['preserved']), {'nvs', 'ota_1', 'ffat'})
    self.assertTrue(bat.touched)
    snap, prog = self.sessions()[:2]
    self.assertEqual((snap['ops'], snap['args'][-1]), (['md5'] * 3, 'no-reset'))
    self.assertEqual(prog['ops'], ['read'] * 4 + ['md5'] * 3)

  def test_a_failed_or_interrupted_install_keeps_its_snapshot_for_recovery(self):
    def interrupt(*a, **k):
      raise ht.Interrupted('SIGTERM')
    for what, ctx, err in (('read-back', mock.patch.dict(os.environ, {'FAKE_ESP_CORRUPT': '0x410000'}), ht.StepFail),
                           ('interrupted', mock.patch.object(ht, 'esp_verify', interrupt), ht.Interrupted)):
      bat, rig, files = self.battery()
      with self.subTest(what), ctx, self.assertRaises(err):
        bat.run(files, 'v1')
      row = dict(bat.report_fields(), cleanup={'state': 'unknown'})
      self.assertTrue(bat.touched)
      self.assertEqual(ht.report_snapshot(json.loads(json.dumps(row)), self.board['regions']['preserved']), bat.preserved)

  def test_no_bridge_is_untouched_but_a_failed_snapshot_session_is_not(self):
    def no_bridge(uid):
      raise ht.StepFail(f'0 serial ports for bridge {uid}: []')
    for what, patch, touched in (('no bridge', mock.patch.object(ht, 'esp_port', no_bridge), False),
                                 ('session failed', mock.patch.dict(os.environ, {'FAKE_ESP_FAIL': 'No serial data received.'}), True)):
      bat, rig, files = self.battery()
      with self.subTest(what), patch, self.assertRaises(ht.StepFail):
        bat.run(files, 'v1')
      self.assertEqual((bat.touched, bat.report_fields()['snapshot']), (touched, None))

  def test_an_app_on_another_port_keeps_the_paths_out_of_the_detail(self):
    bat, rig, files = self.battery()
    real = rig.usb_device
    rig.usb_device = lambda vid, pid, serial: real(vid, pid, serial) and ('1-3' if rig.on == 'app' else '1-2')
    with mock.patch.object(ht, 'usb_device', rig.usb_device), self.assertRaises(ht.StepFail):
      bat.run(files, 'v1')
    last = bat.steps[-1]
    self.assertEqual((last['step'], last['detail']), ('app-ran', 'the app came up on another USB port than DFU'))
    self.assertEqual((last['evidence']['usb'], last['evidence']['expected']), ('1-3', '1-2'))

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
        rig.app[0x1fff00] = ht.nonce_block(bytes(16))
      return real(dev, name, length, log, offset)
    with mock.patch.object(ht, 'fat_read', fat_read), self.assertRaisesRegex(ht.StepFail, 'nonce block at 0x1fff00'):
      bat.run(files, 'v1')
    self.assertEqual(bat.steps[-1]['evidence']['failedAt'], 'readback')

  def test_cleanup_reinstalls_against_the_run_snapshot_and_leaves_dfu_after_blinky(self):
    bat, rig, files = self.battery()
    bat.run(files, 'v1')
    out = bat.restore(files, 'v1')
    self.assertEqual((out['state'], out['evidence']['preserved'], out['evidence']['copy']),
                     ('blinky copied', 'unchanged since the snapshot before the install', {'blocks': 2}))
    self.assertEqual([(b['addr'], b['data'][:1]) for b in rig.copied[-1]], [(0, b'\xb0'), (0x100, b'\xb1')])
    install, check = self.sessions()[-2:]
    self.assertEqual(install['ops'], ['read'] * 4 + ['md5'] * 3)
    self.assertEqual((check['ops'], check['args'][-1]), (['md5'] * 3, 'hard-reset'))

  def test_a_preserved_region_changed_by_the_blinky_copy_fails_the_restore(self):
    bat, rig, files = self.battery()
    bat.run(files, 'v1')
    def spill(cmd, *a, **k):
      if cmd[0] == 'mcopy':
        img = bytearray(self.flash.read_bytes())
        img[0x9000] ^= 0xff
        self.flash.write_bytes(img)
      return rig.spawn(cmd, *a, **k)
    with mock.patch.object(ht, 'spawn', spill), self.assertRaisesRegex(ht.StepFail, 'changed by the end of the restore'):
      bat.restore(files, 'v1')

  def test_a_restore_without_a_run_checks_the_preserved_regions_across_its_install(self):
    bat, rig, files = self.battery()
    out = bat.restore(files, 'v1')
    self.assertEqual(out['evidence']['preserved'], 'unchanged since the snapshot before the install')
    self.assertEqual([x['ops'] for x in self.sessions()],
                     [['md5'] * 3, ['read'] * 4 + ['md5'] * 3, ['md5'] * 3])

  def test_a_restore_fails_when_dfu_comes_back_after_blinky(self):
    bat, rig, files = self.battery()
    seen, polls = rig.usb_device, []
    def blip(*a):   # DFU shows again on the third poll of the quiet period
      if polls is not None and rig.on != 'dfu':
        polls.append(1)
        if len(polls) == 3:
          rig.on = 'dfu'
      return seen(*a)
    with mock.patch.object(ht, 'usb_device', blip), self.assertRaisesRegex(ht.StepFail, 'came back after the blinky copy'):
      bat.restore(files, 'v1')
    self.assertEqual(len(polls), 3)

  def test_app_chunks_refusals(self):
    uf2 = self.tmp / 'a.uf2'
    fam = self.facts['family']
    cases = {'a gap': [(0, bytes(256)), (0x200, bytes(256))], 'another family': None,
             'reaching the nonce block': [(256 * i, bytes(256)) for i in range(0x2000)]}
    for what, chunks in cases.items():
      with self.subTest(what):
        uf2.write_bytes(ht.pack_uf2(chunks or [(0, bytes(256))], fam if chunks else 0x1234))
        with self.assertRaises(ht.Refused):
          ht.esp_app_chunks(uf2, self.facts, self.board)

  def test_the_nonce_block_ends_the_app_partition_inside_one_cache_window(self):
    uf2 = self.tmp / 'a.uf2'
    uf2.write_bytes(ht.pack_uf2([(0, bytes(256))], self.facts['family']))
    for size, off in ((0x200000, 0x1fff00), (0x160000, 0x15ff00), (0x151000, None), (0x8000, None)):
      with self.subTest(hex(size)):
        board = dict(self.board, app=(0x10000, 0x10000 + size))
        if off is None:
          with self.assertRaisesRegex(ht.Refused, 'cache window'):
            ht.esp_app_chunks(uf2, self.facts, board)
        else:
          self.assertEqual(ht.esp_app_chunks(uf2, self.facts, board)['nonceOffset'], off)


class EspSession(Tmp):
  """esp_session.py itself, over stub esptool and pyserial packages: its dispatch, arguments, guard and reset
  order."""

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
    code, out, calls = self.session([{'op': 'read', 'addr': 0x10, 'size': 4, 'file': str(self.tmp / 'r.bin')},
                                     {'op': 'md5', 'addr': 0x9000, 'size': 0x5000}])
    self.assertEqual(code, 0, out)
    self.assertEqual([r['op'] for r in out['results']], ['read', 'md5'])
    self.assertEqual(out['results'][1]['md5'], 'md5-9000-5000')
    self.assertEqual((self.tmp / 'r.bin').read_bytes(), b'\x10' * 4)
    self.assertEqual([c[0] for c in calls], ['connect', 'stub', 'baud', 'attach', 'reset', 'close'])
    self.assertEqual(calls[0][2], 'default-reset')
    self.assertEqual(calls[-2], ['reset', 'hard-reset'])

  def test_a_write_is_refused(self):
    code, out, calls = self.session([{'op': 'write', 'addr': 0x8000, 'file': str(self.tmp / 'seg.bin')}])
    self.assertEqual((code, out['ok']), (1, False))
    self.assertIn("unknown op 'write'", out['error'])

  def test_no_reset_leaves_the_chip_alone(self):
    code, out, calls = self.session([{'op': 'md5', 'addr': 0, 'size': 0x1000}], after='no-reset')
    self.assertEqual(code, 0)
    self.assertNotIn('reset', [c[0] for c in calls])

  def test_another_chip_and_a_failing_op_are_reported_and_the_port_closed(self):
    code, out, calls = self.session([{'op': 'md5', 'addr': 0, 'size': 0x1000}], STUB_CHIP='ESP32-S2')
    self.assertEqual(code, 1)
    self.assertIn('not an esp32s3', out['error'])
    code, out, calls = self.session([{'op': 'md5', 'addr': 0, 'size': 0x1000}, {'op': 'read', 'addr': 0, 'size': 1, 'file': str(self.tmp / 'x')}],
                                    STUB_FAIL_READ='1')
    self.assertEqual((code, [r['op'] for r in out['results']]), (1, ['md5']))
    self.assertIn('timed out', out['error'])
    self.assertEqual(calls[-1], ['close'])
    self.assertNotIn('reset', [c[0] for c in calls])

  def test_the_security_state_is_read_first_on_the_rom_loader_from_two_sources(self):
    off = {'flashEncryption': 'off', 'secureBoot': 'off'}
    code, out, calls = self.session([{'op': 'security'}, {'op': 'md5', 'addr': 0, 'size': 0x1000}], after='no-reset')
    self.assertEqual(code, 0, out)
    self.assertEqual(out['results'][0], {'op': 'security', 'flags': 0, 'flashCryptCnt': 0, 'rom': off, 'efuse': off})
    self.assertEqual([c[0] for c in calls][:4], ['connect', 'security', 'efuse', 'stub'])   # before the stub
    self.assertEqual(calls[1], ['security', False])   # never esptool's cached connect-time answer
    for sec, rom, efuse in (([1, 0, 0, 0], {'secureBoot': 'on'}, {}), ([0, 3, 7, 0], {}, {'flashEncryption': 'on'}),
                            ([0, 1, 1, 1], {'flashEncryption': 'on'}, {'flashEncryption': 'on', 'secureBoot': 'on'})):
      code, out, _ = self.session([{'op': 'security'}], after='no-reset', STUB_SECURITY=json.dumps(sec))
      self.assertEqual((out['results'][0]['rom'], out['results'][0]['efuse']), (dict(off, **rom), dict(off, **efuse)))
    code, out, _ = self.session([{'op': 'security'}], after='no-reset', STUB_IS_STUB='1')
    self.assertEqual(code, 1)
    self.assertIn('ROM loader', out['error'])
    code, out, calls = self.session([{'op': 'md5', 'addr': 0, 'size': 0x1000}, {'op': 'security'}], after='no-reset')
    self.assertEqual((code, calls), (1, []))
    self.assertIn('comes first', out['error'])


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


class Citations(unittest.TestCase):
  CONTRACT = SCRIPT.parent.parent
  CITE = re.compile(r'\b(SKILL|commissioning|bench-history)\.md(?:[,:]\s+([^,;:)\n]+?)\s*[),;:]| ([A-Z][\w/-]*))')

  def unresolved(self, text):
    """Citations in text whose label is no heading, bold item label or file name of the page they name."""
    bad = []
    for m in self.CITE.finditer(text):
      page, label = f'{m[1]}.md', (m[2] or m[3]).strip()
      doc = (self.CONTRACT / page).read_text()
      labels = {h.strip() for h in re.findall(r'(?m)^#{2,}\s+(.+)$', doc)}
      labels |= {b.strip().rstrip(':,') for b in re.findall(r'(?m)^\s*(?:[-*]|\d+\.)\s+\*\*(.+?)\*\*', doc)}
      if label not in labels and not ('.' in label and label in doc):
        bad.append(f'{page}: {label}')
    return bad

  def test_every_citation_of_a_contract_page_names_a_section_it_has(self):
    self.assertEqual(self.unresolved('(SKILL.md, Commissioning) (SKILL.md, Commissioning: Port power) (SKILL.md Roster)'),
                     ['SKILL.md: Commissioning', 'SKILL.md: Commissioning', 'SKILL.md: Roster'])
    for f in sorted(self.CONTRACT.rglob('*')):
      if f.suffix in ('.py', '.md'):
        with self.subTest(f.relative_to(self.CONTRACT)):
          self.assertEqual(self.unresolved(f.read_text()), [])


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


class ChildJson(Tmp):
  """A helper child succeeds only with exit 0 and a last-line JSON object whose ok is true."""

  def child(self, line, code=0):
    return [sys.executable, '-c', f'import sys; print({line!r}); sys.exit({code})']

  def test_only_ok_true_with_exit_0_passes(self):
    log = self.tmp / 'log'
    self.assertEqual(ht.child_json(self.child('{"ok": true, "x": 1}'), log, 30, 'h')['x'], 1)
    for line, code in (('{}', 0), ('{"ok": 0}', 0), ('{"ok": null}', 0), ('{"error": "transfer failed"}', 0),
                       ('[true]', 0), ('not json', 0), ('{"ok": true}', 1)):
      with self.subTest(line=line, code=code), self.assertRaises(ht.StepFail):
        ht.child_json(self.child(line, code), log, 30, 'h')


class Fat(Tmp):
  def setUp(self):
    super().setUp()
    fds = os.listdir('/proc/self/fd')
    self.addCleanup(lambda: self.assertEqual(len(os.listdir('/proc/self/fd')), len(fds), 'a Fat left its descriptor open'))

  def vol(self, img):
    dev = self.tmp / 'vol'
    dev.write_bytes(bytes(img))
    return str(dev)

  def test_reads_entries_and_a_file_prefix(self):
    with ht.Fat(self.vol(fat_image())) as fat:
      self.assertEqual(fat.entries(), {'INFO_UF2.TXT': (2, 5), 'CURRENT.UF2': (3, 1024)})
      self.assertEqual(fat.file('INFO_UF2.TXT'), (b'hello', 5))
      self.assertEqual(fat.file('CURRENT.UF2', 600)[0], b'a' * 512 + b'b' * 88)

  def test_an_offset_skips_whole_clusters_unread(self):
    fat = self.enterContext(ht.Fat(self.vol(fat_image())))
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
      with ht.Fat(self.vol(img)) as fat:
        fat.file('CURRENT.UF2')
    img = fat_image()
    struct.pack_into('<H', img, 512 + 6, 0)   # cluster 3 -> free
    with self.assertRaisesRegex(ValueError, 'chain broken'):
      with ht.Fat(self.vol(img)) as fat:
        fat.file('CURRENT.UF2')
    with self.assertRaisesRegex(ValueError, 'short read'):
      with ht.Fat(self.vol(fat_image()[:3 * 512])) as fat:   # the root dir is cut off
        fat.entries()

  def test_fat_read_runs_in_a_bounded_child_and_reports_errors_as_step_failures(self):
    log = self.tmp / 'log'
    r = ht.fat_read(self.vol(fat_image()), 'CURRENT.UF2', 600, log)
    self.assertEqual((r['data'], r['size'], r['entries']['INFO_UF2.TXT']), (b'a' * 512 + b'b' * 88, 1024, [2, 5]))
    with self.assertRaisesRegex(ht.StepFail, 'not on the volume'):
      ht.fat_read(self.vol(fat_image()), 'NOPE.TXT', 10, log)
    for missing in (self.tmp / 'sdy', self.tmp / 'sdz'):
      with self.assertRaises(ht.StepFail) as cm:
        ht.fat_read(str(missing), 'CURRENT.UF2', 10, log)
      self.assertEqual(str(cm.exception), 'CURRENT.UF2: FileNotFoundError: No such file or directory')   # no node name
      self.assertIn(str(missing), cm.exception.evidence['error'])
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
    self.addCleanup(lambda: [(ht.reap(p), p.wait()) for p in launched])   # reap closes our end of its pipe

    def popen_then_signalled(*a, **k):
      launched.append(real(*a, **k))
      os.kill(os.getpid(), signal.SIGTERM)
      return launched[-1]
    with mock.patch.object(ht.subprocess, 'Popen', popen_then_signalled), \
         self.assertRaisesRegex(ht.Interrupted, 'SIGTERM'):
      ht.spawn([sys.executable, '-c', 'import time; time.sleep(30)'], self.tmp / 'log', 5)
    self.assertEqual(ht.CHILDREN, launched)
    self.assertEqual(ht.settle_children(), [])   # reaped by SIGKILL, not left running
    self.assertIsNotNone(launched[0].poll())
    self.assertEqual(ht.CHILDREN, [])

  def test_a_spawned_childs_stderr_can_go_to_the_log_only(self):
    log = self.tmp / 'log'
    code, out = ht.spawn([sys.executable, '-c', 'import sys; print("out"); print("err", file=sys.stderr)'], log, 5,
                         stderr_to_log=True)
    self.assertEqual((code, out), (0, 'out\n'))
    self.assertIn('err\n', log.read_text())
    self.assertIn('out\n', log.read_text())

  def test_a_kill_reaches_a_grandchild_in_a_process_group_of_its_own(self):
    # as ninja runs JLinkExe: setpgid moves it out of the child's group, not out of its session
    pidfile = self.tmp / 'grandchild'
    code = ('import os, subprocess, sys, time\n'
            'g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], process_group=0)\n'
            f'open({str(pidfile)!r}, "w").write(str(g.pid)); time.sleep(60)')
    with self.assertRaisesRegex(ht.StepFail, 'timed out'):
      ht.spawn([sys.executable, '-c', code], self.tmp / 'log', 2)
    stat = Path(f'/proc/{pidfile.read_text()}/stat')
    self.assertFalse(stat.exists() and stat.read_text().rsplit(')', 1)[1].split()[0] != 'Z')   # gone, or a zombie
    self.assertEqual(ht.CHILDREN, [])

  def test_a_grandchild_that_outlives_the_kill_stays_tracked_until_it_is_gone(self):
    pidfile = self.tmp / 'grandchild'
    code = ('import subprocess, sys, time\n'
            'g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], process_group=0)\n'
            f'open({str(pidfile)!r}, "w").write(str(g.pid)); time.sleep(60)')
    kill = os.kill
    spared = lambda pid, sig: None if pidfile.exists() and pid == int(pidfile.read_text()) else kill(pid, sig)   # noqa: E731
    with mock.patch.object(ht.os, 'kill', spared), mock.patch.object(ht, 'KILL_WAIT', 0.5), \
         self.assertRaisesRegex(ht.StepFail, 'timed out'):
      ht.spawn([sys.executable, '-c', code], self.tmp / 'log', 2)
    grandchild = int(pidfile.read_text())

    def end():
      with contextlib.suppress(ProcessLookupError):
        kill(grandchild, signal.SIGKILL)
    self.addCleanup(end)
    with mock.patch.object(ht.os, 'kill', spared), mock.patch.object(ht, 'KILL_WAIT', 0.5):
      stuck = ht.settle_children()   # as cleanup asks after the failed step
    self.assertEqual([x['pid'] for x in stuck], [grandchild])
    self.assertEqual(ht.still_alive(stuck), stuck)
    kill(grandchild, signal.SIGKILL)
    self.assertEqual((ht.settle_children(), ht.CHILDREN), ([], []))

  def test_a_zombie_is_not_a_live_survivor(self):
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    self.addCleanup(p.wait)
    start = ht.proc_start(p.pid)
    while ht.proc_stat(p.pid):   # exited, not yet waited for
      time.sleep(0.01)
    self.assertTrue(Path(f'/proc/{p.pid}').exists())
    self.assertEqual(ht.still_alive([{'pid': p.pid, 'start': start}]), [])

  def test_a_legacy_reports_container_is_gone_only_once_docker_settles_on_none_and_its_launchers_are_gone(self):
    """#580: no runner makes a container any more, but a report from one that did may name one. A create still in
    flight when that runner died may land after the first empty listing; the name is gone only once docker has listed
    it no more for CONTAINER_SETTLE, and never while a process of the same report lives."""
    name, listings, calls = 'tinyuf2-hil-b', [], []

    def run(cmd, **k):
      calls.append(cmd[:2])
      out = listings.pop(0) if cmd[1] == 'ps' and listings else ''
      return subprocess.CompletedProcess(cmd, 0, out, '')
    launcher = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    self.addCleanup(lambda: (launcher.kill(), launcher.wait()))
    live = {'pid': launcher.pid, 'start': ht.proc_start(launcher.pid), 'cmd': 'docker start -a ' + name}
    with mock.patch.object(ht.cb.subprocess, 'run', run), mock.patch.object(ht.cb, 'CONTAINER_SETTLE', 0.3), \
         mock.patch.object(ht.cb, 'CONTAINER_GONE_WAIT', 5):
      listings[:] = ['', 'c0ffee\n']   # absent once, then the delayed create lands
      self.assertEqual(ht.still_alive([{'container': name}]), [])
      self.assertGreaterEqual(calls.count(['docker', 'rm']), 3)   # removed again once it landed, then settled
      self.assertEqual(listings, [])
      calls.clear()
      self.assertEqual(ht.still_alive([live, {'container': name}]), [live, {'container': name}])
      self.assertEqual(calls, [])   # not even looked at while its launcher lives
    with mock.patch.object(ht.cb, 'container_left', lambda n: f'; container {n} still exists: docker rm -f {n}'):
      self.assertEqual(ht.still_alive([{'container': name}]), [{'container': name}])

  def test_cleanup_tracks_no_container(self):
    p = mock.Mock(pid=1, args=['esptool'])
    with mock.patch.object(ht, 'CHILDREN', [p]), mock.patch.object(ht, 'reap', lambda q: ht.CHILDREN.remove(q) or []), \
         mock.patch.object(ht.subprocess, 'run', mock.Mock(side_effect=AssertionError('no docker in cleanup'))):
      self.assertEqual(ht.settle_children(), [])
    self.assertFalse(hasattr(ht, 'CONTAINERS'))

  def test_a_timed_out_childs_output_so_far_is_in_the_log(self):
    log = self.tmp / 'log'
    with self.assertRaisesRegex(ht.StepFail, f'^{re.escape(Path(sys.executable).name)} timed out after 2s$'):
      ht.spawn([sys.executable, '-c', 'import time; print("partial", flush=True); time.sleep(30)'], log, 2)
    self.assertIn('partial\n', log.read_text())

  def test_an_interrupted_childs_output_so_far_is_in_the_log(self):
    log, ready = self.tmp / 'log', self.tmp / 'ready'
    self.addCleanup(lambda: [ht.reap(p) for p in list(ht.CHILDREN)])

    def signal_once_printed():
      end = time.monotonic() + 10
      while not ready.exists() and time.monotonic() < end:
        time.sleep(0.01)
      time.sleep(0.5)   # for communicate to read it
      os.kill(os.getpid(), signal.SIGTERM)
    signaller = threading.Thread(target=signal_once_printed)
    signaller.start()
    self.addCleanup(signaller.join)
    with self.assertRaisesRegex(ht.Interrupted, 'SIGTERM'):
      ht.spawn([sys.executable, '-c', f'import time; print("partial", flush=True); open({str(ready)!r}, "w"); '
                'time.sleep(30)'], log, 20)
    self.assertEqual(len(ht.CHILDREN), 1)   # left for cleanup's reap, as before
    self.assertIn('partial\n', log.read_text())

  def test_registering_leaves_the_childs_signal_mask_alone(self):
    code, out = ht.spawn(['grep', 'SigBlk', '/proc/self/status'], self.tmp / 'log', 5)
    self.assertEqual(code, 0, out)
    self.assertFalse(int(out.split()[1], 16) & (1 << (signal.SIGTERM - 1)), out)


def sigterm_when(ready, what):
  """SIGTERM this process from a thread once ready() holds: the interruption lands where the test means it to, with
  no fixed delay to outwait."""
  def go():
    with contextlib.suppress(ht.StepFail):
      ht.wait_for(ready, 10, what)
      os.kill(os.getpid(), signal.SIGTERM)
  threading.Thread(target=go, daemon=True).start()


class FlashProvider(Tmp):
  """The runner's use of agentrc's flash provider: its loading, the run= adapter over spawn, the one J-Link flash
  script, and sessions and resets through its primitives."""

  def test_the_pinned_provider_loads_once_and_a_missing_or_incomplete_one_is_refused(self):
    self.assertIs(ht.provider(), ht.provider())
    self.assertEqual(Path(ht.provider().__file__), ht.FLASH_PROVIDER)
    for what, path, api in (('missing', self.tmp / 'none.py', ht.PROVIDER_API),
                            ('incomplete', ht.FLASH_PROVIDER, ht.PROVIDER_API + ('flash_everything',))):
      with self.subTest(what), mock.patch.object(ht, 'PROVIDER', []), mock.patch.object(ht, 'FLASH_PROVIDER', path), \
           mock.patch.object(ht, 'PROVIDER_API', api), self.assertRaises(ht.Refused):
        ht.provider()
    with mock.patch.object(ht, 'PROVIDER', []), \
         mock.patch.object(ht, 'check_lock_pin', side_effect=ht.Refused('lib/agentrc is at x; HEAD pins y')), \
         self.assertRaisesRegex(ht.Refused, 'HEAD pins'):
      ht.provider()

  def test_a_shell_string_runs_as_argv_with_its_assignments_as_environment(self):
    self.assertEqual(ht.command_argv("NO_COLOR=1 esptool --chip esp32s3 -p /dev/ttyACM0 write_flash 0x0 'a b.bin'"),
                     (['esptool', '--chip', 'esp32s3', '-p', '/dev/ttyACM0', 'write_flash', '0x0', 'a b.bin'],
                      {'NO_COLOR': '1'}))
    self.assertEqual(ht.command_argv(['JLinkExe', '-USB', 1]), (['JLinkExe', '-USB', '1'], None))
    for cmd in ('a | b', 'a; b', 'a && b', 'echo $HOME', 'a > f', 'echo `x`'):
      with self.subTest(cmd), self.assertRaises(ValueError):
        ht.command_argv(cmd)

  def test_the_adapter_returns_exit_output_and_a_timeouts_transcript_so_far(self):
    run, log = ht.tool_runner(self.tmp / 'hil.log'), self.tmp / 'hil.log'
    r = run('FOO=bar printenv FOO', timeout=10)
    self.assertEqual((r.returncode, r.stdout), (0, 'bar\n'))
    self.assertEqual(run([sys.executable, '-c', 'import sys; sys.exit(3)'], timeout=10).returncode, 3)
    r = run([sys.executable, '-c', 'import os, signal; os.kill(os.getpid(), signal.SIGSEGV)'], timeout=10)
    self.assertEqual(r.returncode, -signal.SIGSEGV)   # executed directly: a crash keeps its signal
    r = run([sys.executable, '-c', 'import time; print("so far", flush=True); time.sleep(30)'], timeout=1)
    self.assertEqual((r.returncode, r.stdout, ht.CHILDREN), (124, 'so far\n', []))
    op = ht.provider().Operation([ht.provider().Attempt(r.args, None, r, None, 'unknown', None)])
    self.assertEqual(op.attempts[0].kind, 'timed_out')
    self.assertIn('so far', log.read_text())

  def test_the_adapter_reports_cleanup_done_only_once_nothing_of_the_tools_session_is_left(self):
    run = ht.tool_runner(self.tmp / 'hil.log')
    self.assertEqual(run([sys.executable, '-c', 'pass'], timeout=10).cleanup, 'done')
    self.assertEqual(run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=1).cleanup, 'done')   # reaped
    # a process the tool started, its stdout closed, outlives the tool: tracked for cleanup, never called done
    bg = 'import subprocess, sys; subprocess.Popen(["sleep", "30"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)'
    self.addCleanup(ht.settle_children)
    r = run([sys.executable, '-c', bg], timeout=10)
    self.assertEqual((r.returncode, r.cleanup, len(ht.CHILDREN)), (0, 'unknown', 1))
    self.assertEqual(ht.settle_children(), [])
    self.assertEqual(ht.CHILDREN, [])
    op = ht.provider().flash_esptool({'args': ''}, chip='esp32s3', port='/dev/null', flash_args='0x0 a.bin', cwd=str(self.tmp),
                                     timeout=5, run=lambda cmd, cwd, timeout: run([sys.executable, '-c', 'pass'], timeout=5))
    self.assertEqual(op.cleanup, 'done')

  def test_an_interrupted_tool_is_recorded_interrupted_with_its_output_and_left_for_cleanup(self):
    handler = signal.signal(signal.SIGTERM, ht.on_signal)
    mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, ht.TERM_SIGNALS)
    self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, mask)
    self.addCleanup(signal.signal, signal.SIGTERM, handler)
    self.addCleanup(ht.settle_children)
    # ready once the tracked child's output reached communicate's own buffer, not once spawn logged its command line
    sigterm_when(lambda: any(b'hi\n' in b''.join(getattr(p, '_fileobj2output', {}).get(p.stdout, []))
                             for p in list(ht.CHILDREN)), "the tool's output captured")
    with self.assertRaises(ht.Interrupted) as e:
      ht.provider().run_jlink_commands({'uid': '1'}, ['h'], interface='SWD', speed='4000', autoconnect=True, device='d',
                                        timeout=10, workdir=self.tmp, run=lambda cmd, timeout: ht.tool_runner(
                                          self.tmp / 'log')([sys.executable, '-c', 'import time; print("hi", flush=True); '
                                                             'time.sleep(30)'], timeout=timeout))
    a = e.exception.operation.attempts[-1]
    self.assertEqual((a.kind, a.result.stdout, len(ht.CHILDREN)), ('interrupted', 'hi\n', 1))

  def test_the_providers_jlink_flash_script_is_the_record_targets(self):
    # option B: one script for both projects; the CMake target's (check_build's flash_binding fixture) must not drift
    hexp, seen = '/b/tinyuf2.hex', []
    op = ht.provider().flash_jlink({'uid': '000801012283', 'args': '-device MIMXRT1011DAE5A'}, hexp, timeout=5,
                                   run=lambda cmd, timeout: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0, '', ''))
    self.assertEqual(op.attempts[0].script, JLINK_TARGET_SCRIPT.format(hex=hexp) + '\n')
    argv = ht.command_argv(seen[0])[0]
    pairs = lambda a: sorted(zip(a[1:-2:2], a[2:-2:2]))   # noqa: E731   flag, value
    self.assertEqual((argv[0], argv[-2], pairs(argv)), ('JLinkExe', '-CommandFile', pairs(JLINK_TARGET_ARGV)))

  def test_sessions_and_resets_go_through_the_providers_primitives_with_tinyuf2s_profile(self):
    seen = []

    def spawn(cmd, log, timeout, cwd=None, **k):
      seen.append((list(cmd), Path(cmd[-1]).read_text(), timeout))
      return 0, f'J-Link>w4 E000ED0C 05FA0004\nWriting 05FA0004 -> E000ED0C\n'
    probe = ht.Probe({'probe': '7', 'device': 'stm32f411ve', 'if': 'SWD', 'speed': '4000'}, self.tmp, self.tmp / 'log')
    with mock.patch.object(ht, 'spawn', spawn):
      probe.sysreset()
    self.assertEqual(seen[0][0][:-1], ['JLinkExe', '-USB', '7', '-device', 'Cortex-M4', '-if', 'SWD', '-speed', '4000',
                                       '-autoconnect', '1', '-NoGui', '1', '-ExitOnError', '1', '-CommandFile'])
    self.assertEqual(seen[0][1:], ('w4 E000ED0C 05FA0004\nexit\n', ht.PROBE_TIMEOUT))
    self.assertEqual(Path(seen[0][0][-1]).parent, self.tmp)
    cube, scripts = FakeCube(), []
    cube.on_reset = lambda: None
    stlink = ht.StlinkProbe({'probe': '0023', 'device': 'stm32h563zi'}, self.tmp, self.tmp / 'log')
    with mock.patch.object(ht, 'spawn', lambda cmd, *a, **k: scripts.append(Path(cmd[2]).read_text()) or cube.run(cmd[2])):
      stlink.sysreset()
    self.assertEqual(scripts, ['-c port=SWD sn=0023 mode=HOTPLUG\n-w32 0xE000ED0C 0x05FA0004 -nv\n'])

  def test_before_target_holds_only_when_every_attempt_ended_before_the_target(self):
    probe = ht.Probe({'probe': '000726129165', 'device': 'd', 'if': 'SWD', 'speed': '4000'}, self.tmp, self.tmp / 'hil.log')
    crash = (-11, 'Connecting to J-Link ...O.K.\nS/N: 726129165\n')
    for what, second, before in (('no probe on the rerun', (1, JLINK_NO_PROBE), True),
                                 ('the rerun reached the target', (1, 'Connecting to target via SWD\nCannot connect to target.\n'),
                                  False)):
      calls = iter([crash, second])
      with self.subTest(what), mock.patch.object(ht, 'JLINK_RETRY_DELAY', 0), \
           mock.patch.object(ht, 'spawn', lambda *a, **k: next(calls)), self.assertRaises(ht.StepFail) as e:
        probe.run(['h'])
      self.assertEqual(e.exception.evidence['beforeTarget'], before)
    self.assertEqual(probe.retried[-1], {'exit': -11, 'commands': ['h']})


# the CMake target's J-Link command and script, as check_build's flash_binding requires them (test_build.jlink_tree)
JLINK_TARGET_ARGV = ['JLinkExe', '-device', 'MIMXRT1011DAE5A', '-USB', '000801012283', '-ExitOnError', '1', '-NoGui', '1',
                     '-if', 'swd', '-JTAGConf', '-1,-1', '-speed', 'auto', '-CommandFile', '/b/tinyuf2.jlink']
JLINK_TARGET_SCRIPT = 'halt\nloadfile {hex}\nr\ngo\nexit'

CONTENDER = """
import fcntl, json, os, sys, time
with open(sys.argv[1], 'a') as f:
  print('waiting', flush=True)
  fcntl.flock(f, fcntl.LOCK_EX)
  pid = int(open(sys.argv[2]).read()) if os.path.exists(sys.argv[2]) else None
  alive = pid is not None and os.path.exists(f'/proc/{pid}') and open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[0] != 'Z'
  print(json.dumps({'at': time.monotonic(), 'childAlive': alive}), flush=True)
"""


class BuildLockLifetime(Tmp):
  """#579: a flash keeps its build dir's lock until every child it started has ended, against a real contender."""

  def setUp(self):
    super().setUp()
    board = self.load(roster(self.tmp))
    self.bat = ht.Battery(board, ht.source_facts(board), self.tmp)
    self.root = self.tmp / 'build'
    self.root.mkdir()
    self.flash = {'root': self.root, 'sha256': {}}
    self.pidfile = self.tmp / 'child.pid'
    self.addCleanup(ht.settle_children)

  def child(self, body):
    return [sys.executable, '-c', f'import os, sys, time; open({str(self.pidfile)!r}, "w").write(str(os.getpid())); {body}']

  def contender(self):
    c = subprocess.Popen([sys.executable, '-c', CONTENDER, str(ht.cb.build_lock_file(self.root)), str(self.pidfile)],
                         stdout=subprocess.PIPE, text=True)
    self.addCleanup(lambda: (c.kill(), c.wait(), c.stdout.close()))
    self.assertEqual(c.stdout.readline().strip(), 'waiting')
    return c

  def flash_with(self, body, timeout=10):
    def op(run):
      self.contended = self.contender()   # started while the tool runs, the lock already held
      return one_attempt(run(self.child(body), timeout=timeout))
    return self.bat.flash_target(self.flash, op, lambda code, out: {'exit': code}, lambda code, out: False, 'tool', timeout)

  def acquired(self):
    got = json.loads(self.contended.stdout.readline())
    return got, time.monotonic()

  def test_success_releases_the_lock_once_the_tool_has_exited(self):
    self.assertEqual(self.flash_with('time.sleep(0.5)')['exit'], 0)
    got, _ = self.acquired()
    self.assertFalse(got['childAlive'])

  def test_a_timeout_kills_the_tool_before_the_lock_goes(self):
    with self.assertRaisesRegex(ht.StepFail, 'timed out after 1s'):
      self.flash_with('time.sleep(30)', timeout=1)
    self.assertFalse(self.acquired()[0]['childAlive'])

  def test_an_interruption_reaps_the_tool_inside_the_lock(self):
    handler = signal.signal(signal.SIGTERM, ht.on_signal)
    mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, ht.TERM_SIGNALS)
    self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, mask)
    self.addCleanup(signal.signal, signal.SIGTERM, handler)
    sigterm_when(lambda: self.pidfile.exists() and self.pidfile.read_text(), 'the tool running under the lock')
    with self.assertRaises(ht.Interrupted):
      self.flash_with('time.sleep(30)')
    self.assertEqual(ht.CHILDREN, [])
    self.assertFalse(self.acquired()[0]['childAlive'])

  def outlived(self, late):
    """reap as if `late` were a member of the child's session that outlived SIGKILL: the child stays tracked."""
    real = ht.reap

    def reap(p):
      left = real(p) + [late.pid]
      if p not in ht.CHILDREN:
        ht.CHILDREN.append(p)
      return left
    return mock.patch.object(ht, 'reap', reap)

  def test_a_survivor_keeps_the_lock_through_a_keeper_until_it_exits(self):
    late = subprocess.Popen(['sleep', '30'], start_new_session=True)   # stands for a child that outlived SIGKILL
    self.addCleanup(lambda: (late.kill(), late.wait()))
    with self.outlived(late), \
         self.assertRaisesRegex(ht.StepFail, 'timed out'):
      self.flash_with('time.sleep(30)', timeout=1)
    kept, = self.bat.kept
    self.assertEqual(([s['pid'] for s in kept['survivors']], kept['buildDir']), ([late.pid], 'build'))
    self.assertNotIn('inProcess', kept['keeper'])
    keeper = kept['keeper']['pid']
    self.addCleanup(lambda: end_child(keeper))
    with open(ht.cb.build_lock_file(self.root), 'a') as f, self.assertRaises(OSError):
      ht.fcntl.flock(f, ht.fcntl.LOCK_EX | ht.fcntl.LOCK_NB)   # the keeper holds it after this process let go
    ready, _, _ = select.select([self.contended.stdout], [], [], 0.3)
    self.assertFalse(ready, 'the contender got the lock while the survivor lived')
    late.kill()
    late.wait()
    self.acquired()   # once the survivor is gone
    ht.wait_for(lambda: ht.proc_stat(keeper) is None, 5, 'the keeper exiting')

  def test_a_flash_that_succeeded_but_left_a_survivor_fails_after_handing_the_lock_to_its_keeper(self):
    late = subprocess.Popen(['sleep', '3'], start_new_session=True)
    self.addCleanup(lambda: (late.kill(), late.wait()))
    left = [ht.survivor(late.pid)]
    with mock.patch.object(ht, 'settle_children', lambda started: list(left)), \
         self.assertRaisesRegex(ht.StepFail, 'children survived SIGKILL') as cm:
      self.flash_with('pass')
    self.assertEqual((cm.exception.evidence['survivors'], self.bat.kept[0]['survivors']), (left, left))
    self.addCleanup(lambda: end_child(self.bat.kept[0]['keeper']['pid']))
    with open(ht.cb.build_lock_file(self.root), 'a') as f, self.assertRaises(OSError):
      ht.fcntl.flock(f, ht.fcntl.LOCK_EX | ht.fcntl.LOCK_NB)

  def test_a_keeper_that_never_starts_leaves_the_lock_with_this_process(self):
    late = subprocess.Popen(['sleep', '30'], start_new_session=True)
    self.addCleanup(lambda: (late.kill(), late.wait()))
    self.addCleanup(lambda: ([fh.close() for fh, _ in ht.HELD_BUILD], ht.HELD_BUILD.clear()))
    with self.outlived(late), \
         mock.patch.object(ht, 'HOLDER_SCRIPT', self.tmp / 'missing.py'), \
         self.assertRaisesRegex(ht.StepFail, 'timed out'):
      self.flash_with('time.sleep(30)', timeout=1)
    self.assertEqual((self.bat.kept[0]['keeper'], len(ht.HELD_BUILD)), ({'pid': os.getpid(), 'inProcess': True}, 1))
    with open(ht.cb.build_lock_file(self.root), 'a') as f, self.assertRaises(OSError):
      ht.fcntl.flock(f, ht.fcntl.LOCK_EX | ht.fcntl.LOCK_NB)


class Locks(Tmp):
  def setUp(self):
    super().setUp()
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())   # hand_off blocks SIGUSR1 in this process
    self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, mask)
    lockdir = self.tmp / 'locks'
    lockdir.mkdir()
    with mock.patch.object(ht, 'check_lock_pin'):
      self.helper = pinned_helper(self, lockdir)
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
    with mock.patch.dict(os.environ, {ht.JOB_TRACKING: 'job-7'}):
      holder = ht.hand_off(fh, BOARD, 'cleanup failed', [{'pid': 99, 'start': 1, 'cmd': ['mcopy']}])
    self.addCleanup(lambda: end_child(holder['pid']))
    self.assertTrue(holder['ready'])
    self.assertNotIn('inProcess', holder)
    # the holder is the re-executed `keep-held`, outside the Actions job's process tracking
    proc = Path('/proc') / str(holder['pid'])
    ht.wait_for(lambda: b'keep-held' in (proc / 'cmdline').read_bytes(), 5, 'holder exec')
    self.assertNotIn(ht.JOB_TRACKING.encode(), (proc / 'environ').read_bytes())
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
                        ('no ack', mock.patch.object(ht, 'holder_record', dies_in_the_child)),
                        # the exec succeeds but the replacement dies at startup: never acknowledged
                        ('exec dies', mock.patch.object(ht, 'HOLDER_SCRIPT', self.tmp / 'missing.py'))):
      with self.subTest(what):
        fh = self.helper.acquire_board_lock(BOARD)
        with patch:
          holder = ht.hand_off(fh, BOARD, 'cleanup failed')
        self.assertEqual((holder['pid'], holder.get('inProcess')), (parent, True))
        with self.assertRaises(OSError):
          self.helper.flock_nb(BOARD)
        rec = ht.prove_hold(self.helper, BOARD, parent, reason='hil_test.py', role=ht.HOLDER_ROLE)
        self.assertEqual(rec['detail'], 'cleanup failed')
        held = ht.HELD_IN_PROCESS.pop()
        self.helper.clear_record(held)   # a cleanup holder's record left on a free flock is a recovery blocker
        held.close()

  def test_with_no_descriptor_left_the_runner_itself_holds_and_releases_only_on_sigusr1(self):
    script = textwrap.dedent(f'''
      import importlib.util, json, os, resource, signal, sys
      spec = importlib.util.spec_from_file_location('ht', {str(SCRIPT)!r}); ht = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(ht)
      ht.check_lock_pin = lambda: None
      helper = ht.load_helper()
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

  def test_with_both_handoffs_failed_the_holding_runner_releases_the_build_lock_once_its_survivor_ends(self):
    late = subprocess.Popen(['sleep', '30'], start_new_session=True)
    self.addCleanup(lambda: (late.kill(), late.wait()))
    root = self.tmp / 'build'
    script = textwrap.dedent(f'''
      import importlib.util, json, signal
      from pathlib import Path
      spec = importlib.util.spec_from_file_location('ht', {str(SCRIPT)!r}); ht = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(ht)
      ht.check_lock_pin = lambda: None
      ht.HOLDER_SCRIPT = Path({str(self.tmp / 'missing.py')!r})   # neither the keeper nor the holder starts
      helper = ht.load_helper()
      helper.BOARD_LOCK_DIR = {str(Path(self.lock).parent)!r}
      fh = helper.acquire_board_lock({BOARD!r})
      signal.pthread_sigmask(signal.SIG_BLOCK, ht.TERM_SIGNALS)
      survivors = {json.dumps([ht.survivor(late.pid)])}
      keeper = ht.keep_build_lock(ht.take_build_lock(Path({str(root)!r})), survivors)
      holder = ht.hand_off(fh, {BOARD!r}, 'cleanup failed', survivors)
      print(json.dumps([keeper, holder]), flush=True)
      ht.keep_held(ht.HELD_IN_PROCESS[0])
    ''')
    p = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True)
    self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close()))
    keeper, holder = json.loads(p.stdout.readline())
    self.assertEqual([(r['pid'], r['inProcess']) for r in (keeper, holder)], [(p.pid, True)] * 2)
    build_lock = ht.cb.build_lock_file(root)
    time.sleep(0.3)
    self.assertFalse(ht.flock_free(build_lock), 'the build lock went while its survivor lived')
    late.kill()
    late.wait()
    ht.wait_for(lambda: ht.flock_free(build_lock), 5, 'the build lock released')
    self.assertIsNone(p.poll())
    ht.prove_hold(self.helper, BOARD, p.pid, reason='hil_test.py', role=ht.HOLDER_ROLE)   # the board stays held
    p.send_signal(signal.SIGUSR1)
    self.assertEqual(p.wait(5), 0)
    self.helper.flock_nb(BOARD).close()

  def test_a_holder_handed_off_during_cleanup_still_ends_on_sigusr1(self):
    fh = self.helper.acquire_board_lock(BOARD)
    with ht.signals(signal.SIG_BLOCK):   # cleanup blocks SIGTERM and SIGINT; the holder must not care
      holder = ht.hand_off(fh, BOARD, 'cleanup failed')
    self.addCleanup(lambda: end_child(holder['pid']))
    os.kill(holder['pid'], signal.SIGUSR1)
    ht.wait_for(lambda: ht.flock_free(self.lock), 5, 'release')

  def test_one_recovery_per_board_and_the_helper_never_lists_it_as_a_holder(self):
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
    self.addCleanup(lambda: end_child(holder['pid']))
    ht.wait_for(lambda: not any(Path(f'/proc/{holder["pid"]}/fd/{std}').exists() for std in (0, 1, 2)), 5,
                'the holder closing its stdio')


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
    with mock.patch.object(ht, 'check_lock_pin'):
      self.helper = pinned_helper(self, self.tmp / 'locks')
    self.board = self.load(roster(self.tmp))
    self.facts = ht.source_facts(self.board)
    self.args = mock.Mock(build_record='rec.json', fail_at=None, try_reentry=None, lock_wait=0)
    for p in (mock.patch.object(ht, 'verify_record', lambda *a: ({'hex': 'x.hex', 'bin': 'x.bin'}, {'version': 'v'})),
              mock.patch.object(ht, 'parse_hex', lambda p: {0: 1}),
              mock.patch.object(ht, 'hex_matches_bin', lambda d, b, base: True),
              mock.patch.object(ht, 'check_jlink', lambda: None),
              mock.patch.object(ht, 'check_bootloader_bin', lambda *a: None),
              mock.patch.object(ht, 'exclusion_configured', lambda *a: None),
              mock.patch.object(ht, 'probe_users', lambda b: []),   # not the host's J-Link tools: tests patch their own
              mock.patch.object(ht.shutil, 'which', lambda t: '/usr/bin/' + t)):
      p.start()
      self.addCleanup(p.stop)

  def run_board(self, battery_run, cleanup_error=None):
    cleaned = []

    def fake_restore(*a, **k):
      cleaned.append(True)
      if cleanup_error:
        raise cleanup_error
      return {'pass': True, 'state': 'blinky copied', 'evidence': {}}
    with mock.patch.object(ht.Battery, 'run', battery_run), mock.patch.object(ht.Battery, 'restore', fake_restore):
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
    self.assertEqual((code, cleaned, row['cleanup']), (1, [], {'pass': True, 'state': 'untouched', 'evidence': {},
                                                               'heldAfter': False}))

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

  def test_a_snapshot_the_cleanups_install_took_reaches_the_report_when_the_cleanup_fails(self):
    def no_snapshot(bat, files, version):   # the run's snapshot session failed after touching the board
      bat.touched = True
      raise ht.StepFail('snapshot session failed')

    def snapshot_then_fail(bat, *a):
      bat.snap = {'nvs': '0' * 32}
      raise ht.StepFail('read-back failed')
    with mock.patch.object(ht.Battery, 'report_fields', lambda bat: {'snapshot': getattr(bat, 'snap', None)}), \
         mock.patch.object(ht.Battery, 'run', no_snapshot), mock.patch.object(ht.Battery, 'restore', snapshot_then_fail), \
         mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1, 'reason': 'hil_test.py'})[1]):
      row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
    self.assertEqual((code, row['cleanup']['pass'], row['snapshot']), (4, False, {'nvs': '0' * 32}))

  def test_a_step_or_method_of_the_other_flasher_is_refused_before_the_lock(self):
    for attr, val, err in (('fail_at', 'recopy', 'has no step recopy'), ('try_reentry', 'dfu-detach', 're-enters by one of')):
      with self.subTest(val), mock.patch.object(self.args, attr, val), self.assertRaisesRegex(ht.Refused, err):
        ht.run_board(self.args, dict(self.board, reentry=None), self.facts, self.helper, self.tmp)

  def test_fail_at_cleanup_skips_the_restore_and_hands_the_board_to_a_holder(self):
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

    def restore_then_signalled(*a, **k):
      os.kill(os.getpid(), signal.SIGTERM)   # blocked until cleanup has ended
      return {'pass': True, 'state': 's', 'evidence': {}}

    signal.signal(signal.SIGTERM, ht.on_signal)
    with mock.patch.object(ht.Battery, 'run', ok), mock.patch.object(ht.Battery, 'restore', restore_then_signalled):
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

  def test_a_stuck_child_is_a_cleanup_failure_with_no_restore(self):
    def fail(bat, files, version):
      bat.touched = True
      raise ht.StepFail('x')
    stuck = [{'pid': 99, 'start': 7, 'cmd': ['JLinkExe']}]
    with mock.patch.object(ht, 'settle_children', lambda started=(): list(stuck)), \
         mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1, 'survivors': s})[1]):
      row, code, cleaned = self.run_board(fail)
    self.assertEqual((code, cleaned, row['cleanup']['survivors']), (4, [], stuck))
    self.assertEqual(row['cleanup']['detail'], 'StepFail: children survived SIGKILL; no flash may overlap them')

  def test_the_restore_reflashes_through_a_build_lock_this_process_kept_once_its_survivor_ended(self):
    root = self.tmp / 'build'
    self.addCleanup(lambda: ([fh.close() for fh, _ in ht.HELD_BUILD], ht.HELD_BUILD.clear()))

    def restore(*a, **k):   # as flash_target, on the build dir the run's flash used
      ht.take_build_lock(root).close()
      return {'pass': True, 'state': 'blinky copied', 'evidence': {}}
    for ended in (True, False):
      with self.subTest(ended=ended):
        late = subprocess.Popen(['sleep', '30'], start_new_session=True)
        self.addCleanup(lambda p=late: (p.kill(), p.wait()))

        def flashed_with_a_survivor(bat, files, version):   # its keeper never started: the lock stays in process
          bat.touched = True
          with mock.patch.object(ht, 'HOLDER_SCRIPT', self.tmp / 'missing.py'):
            ht.keep_build_lock(ht.take_build_lock(root), [ht.survivor(late.pid)])
          if ended:
            late.kill()
            late.wait()
          raise ht.StepFail('children survived SIGKILL')
        with mock.patch.object(ht.Battery, 'run', flashed_with_a_survivor), \
             mock.patch.object(ht.Battery, 'restore', restore), mock.patch.object(ht, 'BUILD_LOCK_WAIT', 0.3), \
             mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (fh.close(), {'pid': 1})[1]):
          row, code = ht.run_board(self.args, self.board, self.facts, self.helper, self.tmp)
        if ended:
          self.assertEqual((code, row['cleanup']['pass'], ht.HELD_BUILD), (1, True, []))
          self.helper.flock_nb(BOARD).close()
        else:   # its survivor alive: the lock stays kept, the restore cannot flash and the board stays held
          self.assertEqual((code, row['cleanup']['heldAfter'], len(ht.HELD_BUILD)), (4, True, 1))
          self.assertIn('is in use by a build or another flash', row['cleanup']['detail'])
          self.assertFalse(ht.flock_free(ht.cb.build_lock_file(root)))

  def test_a_session_left_running_is_cleanup_pending_never_reaped_and_keeps_the_board(self):
    server = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
    self.addCleanup(lambda: (server.kill(), server.wait()))
    receipt = self.tmp / 'hil_openocd_esp_x' / 'receipt.json'

    def fail(bat, files, version):   # as flash_openocd_esp leaves it: its receipt open, its server alive
      bat.touched = True
      receipt.parent.mkdir()
      receipt.write_text(json.dumps({'pid': server.pid, 'startTime': str(ht.proc_start(server.pid)), 'closed': False,
                                     'argv': ['openocd'], 'ports': [None, None, 1], 'token': 't', 'log': 'l'}))
      raise ht.CleanupPending('the openocd_esp session is still running: cleanup pending')
    handed = []
    with mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (handed.append(s), fh.close(), {'pid': 1})[2]):
      row, code, cleaned = self.run_board(fail)
    want = [{'pid': server.pid, 'start': ht.proc_start(server.pid), 'cmd': 'openocd', 'receipt': str(receipt)}]
    self.assertEqual((code, cleaned, row['cleanup']['state'], row['cleanup']['receipts'], handed),
                     (4, [], 'pending', [str(receipt)], [want]))   # no restore, the board held
    self.assertEqual((server.poll(), ht.still_alive(want)), (None, want))   # recovery refuses while it runs
    good = receipt.read_text()
    receipt.write_text('{')   # an unreadable receipt blocks recovery and keeps a build lock's keeper, reread each check
    self.assertEqual(ht.still_alive(want), want)
    receipt.write_text(json.dumps(dict(json.loads(good), closed=True, cleanup='done')))   # ended by `end`
    self.assertEqual((ht.still_alive(want), ht.outstanding_sessions(self.tmp)), ([], []))

  def test_a_pending_mark_that_cannot_be_written_never_costs_the_hand_off_or_the_report(self):
    server = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
    self.addCleanup(lambda: (server.kill(), server.wait()))
    receipt = self.tmp / 'hil_openocd_esp_x' / 'receipt.json'
    self.board['pendingMark'] = ht.PendingMark(None, 'b')

    def fail(bat, files, version):
      bat.touched = True
      receipt.parent.mkdir()
      receipt.write_text(json.dumps({'pid': server.pid, 'startTime': str(ht.proc_start(server.pid)), 'closed': False}))
      raise ht.CleanupPending('the openocd_esp session is still running: cleanup pending')
    handed = []

    def enospc(*a):
      raise OSError(28, 'No space left on device')
    with mock.patch.object(ht, 'write_mark', enospc), mock.patch.object(ht, 'MARK_ERRORS', []), \
         mock.patch.object(ht, 'hand_off', lambda fh, b, d, s: (handed.append(s), fh.close(), {'pid': 1})[2]):
      row, code, cleaned = self.run_board(fail)
    self.assertEqual((code, row['cleanup']['state'], row['cleanup']['receipts'], len(handed)),
                     (4, 'pending', [str(receipt)], 1))   # held by its holder, the session reported
    self.assertIn('could not be written', row['cleanup']['markErrors'][0])
    self.assertFalse(Path(self.board['pendingMark']).exists())

  def test_a_survivor_on_an_untouched_board_still_keeps_it_held(self):
    def fail(bat, files, version):
      raise ht.StepFail('install: probe hung')
    with mock.patch.object(ht, 'settle_children', lambda started=(): [{'pid': 99, 'start': 7, 'cmd': ['JLinkExe']}]), \
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

    def restore_under_fire(*a, **k):
      for _ in range(3):
        os.kill(os.getpid(), signal.SIGTERM)
      return {'pass': True, 'state': 's', 'evidence': {}}
    with mock.patch.object(ht.Battery, 'run', interrupted), mock.patch.object(ht.Battery, 'restore', restore_under_fire):
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

  def test_a_held_board_is_tried_again_within_lock_wait(self):
    held = self.helper.acquire_board_lock(BOARD, reason='someone')
    self.args.lock_wait = 5
    threading.Timer(0.1, lambda: (self.helper.clear_record(held), held.close())).start()
    with mock.patch.object(ht, 'LOCK_POLL', 0.02):
      row, code, cleaned = self.run_board(lambda bat, f, v: setattr(bat, 'touched', True))
    self.assertEqual((code, row['locked'], row['pass'], cleaned), (0, False, True, [True]))

  def test_a_signal_during_the_lock_wait_still_gives_a_locked_row(self):
    held = self.helper.acquire_board_lock(BOARD, reason='someone')
    self.addCleanup(held.close)
    self.args.lock_wait = 100
    signal.signal(signal.SIGTERM, ht.on_signal)
    real_sleep = time.sleep

    def signalled(s):
      os.kill(os.getpid(), signal.SIGTERM)
      real_sleep(1)
      self.fail('the signal did not interrupt the wait')
    with mock.patch.object(ht.time, 'sleep', signalled):
      row, code, cleaned = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['ran'], row['locked'], row['recoveryBlocker'], cleaned), (1, False, True, False, []))
    self.assertIn('interrupted by SIGTERM while waiting for the lock', row['detail'])
    self.assertTrue(self.helper.is_locked(BOARD))
    self.assertEqual(self.helper.read_record(BOARD)['reason'], 'someone')

  def test_a_failed_probe_check_is_not_run_and_released(self):
    def no_bridge(board):
      raise ht.StepFail('0 serial ports for bridge cp2102n: []')
    with mock.patch.object(ht, 'probe_users', no_bridge):
      row, code, cleaned = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['ran'], row['locked'], cleaned), (1, False, False, []))
    self.assertEqual(row['detail'], 'probe check: 0 serial ports for bridge cp2102n: []')
    self.assertFalse(self.helper.is_locked(BOARD))
    self.helper.flock_nb(BOARD).close()

  def test_a_failed_probe_check_without_the_board_lock_is_not_run(self):
    def no_bridge(board):
      raise ht.StepFail('0 serial ports for bridge cp2102n: []')
    with mock.patch.object(ht, 'probe_users', no_bridge), mock.patch.dict(os.environ, {'HIL_NO_BOARD_LOCK': '1'}):
      row, code, cleaned = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['ran'], row['lockBypassed'], cleaned), (1, False, True, []))
    self.assertEqual(row['detail'], 'probe check: 0 serial ports for bridge cp2102n: []')

  def test_a_cleanup_holder_is_not_waited_for(self):
    held = self.helper.acquire_board_lock(BOARD, reason='someone')
    self.addCleanup(held.close)
    rec = json.loads(Path(self.helper.lock_path(BOARD)).read_text())
    Path(self.helper.lock_path(BOARD)).write_text(json.dumps(dict(rec, role=ht.HOLDER_ROLE)))
    self.args.lock_wait = 100
    t0 = time.monotonic()
    row, code, _ = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['locked'], row['recoveryBlocker']), (1, True, True))
    self.assertIn(ht.HOLDER_ROLE, row['detail'])
    self.assertLess(time.monotonic() - t0, 5)

  def test_the_lock_wait_ends_at_its_budget_even_when_the_board_frees_meanwhile(self):
    held = self.helper.acquire_board_lock(BOARD, reason='someone')
    self.args.lock_wait = 1
    threading.Timer(0.5, lambda: (self.helper.clear_record(held), held.close())).start()
    t0 = time.monotonic()
    with mock.patch.object(ht, 'LOCK_POLL', 5):   # one sleep, capped to the budget, waking after the release
      row, code, _ = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['locked'], row['recoveryBlocker']), (1, True, False))
    self.assertLess(time.monotonic() - t0, 3)

  def test_a_probe_still_in_use_is_refused_after_the_lock_and_released(self):
    with mock.patch.object(ht, 'probe_users', lambda b: [101]):
      row, code, cleaned = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['ran'], row['probeUsers'], cleaned), (2, False, [101], []))
    self.assertFalse(self.helper.is_locked(BOARD))
    self.helper.flock_nb(BOARD).close()

  def test_the_board_is_locked_and_reported_under_its_lock_name(self):
    self.board = self.load(roster(self.tmp, tinyuf2={'lock': 'tinyusb_name'}))
    held = self.helper.acquire_board_lock('tinyusb_name', reason='someone')
    self.addCleanup(held.close)
    row, code, _ = self.run_board(lambda *a: self.fail('ran'))
    self.assertEqual((code, row['board'], row['lock'], row['locked']), (1, BOARD, 'tinyusb_name', True))

  def test_an_unusable_lock_dir_is_refused_not_run_unlocked(self):
    (self.tmp / 'file').write_text('')
    with mock.patch.object(self.helper, 'BOARD_LOCK_DIR', str(self.tmp / 'file' / 'locks')), \
         mock.patch.dict(os.environ, {'HIL_NO_BOARD_LOCK': ''}):
      with self.assertRaisesRegex(ht.Refused, 'board lock unavailable.*refusing to run unlocked'):
        self.run_board(lambda *a: self.fail('ran'))

  def test_fail_at_injects_a_criterion_failure(self):
    bat = ht.Battery(self.board, self.facts, self.tmp, 'dfu')
    bat.step('install', lambda: {})
    with self.assertRaisesRegex(ht.StepFail, 'injected'):
      bat.step('dfu', lambda: {})


def one_attempt(result):
  """A provider Operation of the one run `result`, for a test's flash op."""
  return ht.provider().Operation([ht.provider().Attempt(result.args, None, result, None, 'unknown', None)])


def FLASHED(hex_path):   # noqa: N802   FakeRig's record of the provider's J-Link flash script
  return ['flash', 'halt', f'loadfile {hex_path}', 'r', 'go', 'exit']


def jlink_target(hex_path, download='1 range affected (65536 bytes)', tail='O.K.\n'):
  """The J-Link flash script's transcript, in the shape the bench recorded on metro_m7_1011."""
  return (f'J-Link>halt\nConnecting to J-Link ...O.K.\nS/N: 1\nConnecting to target via SWD\n'
          f'Cortex-M7 identified.\nJ-Link>loadfile {hex_path}\nResetTarget() start\n'
          f'ResetTarget() end - Took 117ms\nDownloading file [{hex_path}]...\n'
          f'Comparing flash   [000%]100%] Done.\nJ-Link: Flash download: Bank 0 @ 0x60000000: {download}\n{tail}'
          f'J-Link>r\nJ-Link>go\nJ-Link>exit\n\nScript processing completed.\n')


JLINK_NO_PROBE = ('J-Link>halt\nJ-Link connection not established yet but required for command.\n'
                  'Connecting to J-Link ...FAILED: Cannot connect to J-Link.\n')


# J-Link's connect to an STM32F303VC with TinyUF2's write protection set, as the bench recorded it
F3_UNPROTECT = ('Active write protection detected.\nDevice will be unsecured now.\nFailed to unlock device.\n'
                'Can not attach to CPU. Trying connect under reset.\n')

class FakeRig:
  """A probe and a UF2 drive that behave as the battery expects; each test breaks one thing."""

  def __init__(self, bat):
    self.bat, self.scripts, self.present = bat, [], True
    self.r0, self.mem, self.double_reset = 5, {}, False
    self.hex, self.app_survives = None, False   # the install erases the app start (bench), so DFU follows it

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
      elif c.startswith('w4 '):
        _, a, v = c.split()
        self.mem[int(a, 16)] = int(v, 16)
    return out

  def spawn(self, cmd, log, timeout, cwd=None, **k):
    if cmd[0] == 'mcopy':
      self.present = False
    if cmd[0] == 'JLinkExe':
      script = Path(cmd[cmd.index('-CommandFile') + 1]).read_text().splitlines()
      assert any(c.startswith('loadfile ') for c in script), script   # sessions go through FakeRig.probe
      self.scripts.append(['flash'] + script)
      self.present = not self.app_survives
      return 0, jlink_target(self.hex)
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

  def battery(self, reentry='retained-register', corrupt=None, commissioning=False, device=None):
    board = self.load(roster(self.tmp, tinyuf2={'reentry': reentry}))
    facts = ht.source_facts(board)
    if device:
      board['device'] = device
    bat = ht.Battery(board, facts, self.tmp, commissioning=commissioning)
    bootloader_bin(self.tmp / 'c.bin')
    rig = FakeRig(bat)
    build = self.tmp / 'build'
    build.mkdir(exist_ok=True)
    rig.hex = build / 'tinyuf2.hex'
    rig.hex.write_text(':00000001FF\n')
    self.files = {'bin': self.tmp / 'c.bin', 'hex': rig.hex,
                  'flash': {'root': build, 'binding': {'target': 'tinyuf2-jlink'},
                            'sha256': {'tinyuf2.hex': ht.sha256(rig.hex)}}}
    (self.tmp / 'cur').mkdir()
    bat.probe.run = rig.probe
    bat.probe.sysreset = lambda: rig.probe([f'w4 {ht.SCB_AIRCR:08X} {ht.AIRCR_SYSRESETREQ:08X}'], judge=False)
    clock = [0.0]   # time passes only when the battery sleeps

    def fat_read(*a):
      if a[1] == 'CURRENT.UF2':
        rig.current = bytearray(bat.fix['image'])
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

  def test_the_f411_install_verify_waits_out_the_option_byte_rewrite_before_its_halt(self):
    bat, rig = self.battery(device='stm32f411ve')
    bat.install(self.files)
    self.assertEqual(rig.scripts[1][:2], ['sleep 1000', 'h'])

  def test_the_install_is_the_providers_jlink_flash_of_the_record_hex_and_runs_no_ninja(self):
    bat, rig = self.battery(device='stm32f411ve')   # the flash connects as the roster device; only sessions connect as the core
    calls, spawn = [], rig.spawn
    with mock.patch.object(ht, 'spawn', lambda cmd, *a, **k: calls.append((list(cmd), k.get('cwd'))) or spawn(cmd, *a, **k)):
      ev = bat.install(self.files)
    (argv, cwd), = calls
    path = argv[-1]
    self.assertEqual((argv[:-1], cwd), (['JLinkExe', '-USB', '1', '-device', 'stm32f411ve', '-if', 'swd', '-JTAGConf',
                                         '-1,-1', '-speed', 'auto', '-NoGui', '1', '-ExitOnError', '1', '-CommandFile'], None))
    self.assertEqual((Path(path).parent, Path(path).exists()), (self.tmp, False))   # in the run dir, removed after
    self.assertEqual(rig.scripts[0], FLASHED(self.files['hex']))
    self.assertEqual(ev['operation'], {'attempts': [{'kind': 'exited', 'exit': 0}], 'cleanup': 'done'})

  def test_a_timed_out_flash_fails_touched_with_its_transcript_so_far(self):
    bat, rig = self.battery()

    def hangs(cmd, log, timeout, **k):
      raise ht.SpawnTimeout(f'JLinkExe timed out after {timeout}s', 'Connecting to J-Link ...FAILED: x\n', [])
    with mock.patch.object(ht, 'spawn', hangs), \
         self.assertRaisesRegex(ht.StepFail, f'^JLinkExe timed out after {ht.PROBE_TIMEOUT}s$') as e:
      bat.install(self.files)
    ev = e.exception.evidence
    # what a killed tool printed so far is no proof it never reached the target
    self.assertEqual((ev['tail'], ev['beforeTarget'], bat.touched), (['Connecting to J-Link ...FAILED: x'], False, True))
    self.assertEqual(ev['operation']['attempts'], [{'kind': 'timed_out', 'exit': 124}])

  def test_every_step_passes_and_resumes_only_after_a_halt(self):
    bat, rig = self.battery()
    bat.run(self.files, 'v1')
    self.assertEqual([x['step'] for x in bat.steps if x['pass']], list(ht.STEPS['jlink']))
    self.assertEqual(rig.scripts[:2], [FLASHED(self.files['hex']), ['h', f'verifybin {self.tmp / "c.bin"},0x0', 'r', 'g']])
    self.assertEqual(rig.scripts[2][:2], ['h', f'w4 {bat.f["dblTapReg"]:08X} 00000000'])   # cleared in dfu
    self.assertIn(f'sleep {2 * bat.f["dblTapDelayMs"] + 200}', rig.scripts[3])
    self.assertEqual(bat.steps[0]['evidence'], {'flashDownload': '1 range affected (65536 bytes)', 'verified': True,
                                                'operation': {'attempts': [{'kind': 'exited', 'exit': 0}], 'cleanup': 'done'}})
    for script in rig.scripts:
      if 'g' in script:
        self.assertEqual(script[0], 'h', script)
    self.assertIn([f'w4 {ht.SCB_AIRCR:08X} {ht.AIRCR_SYSRESETREQ:08X}'], rig.scripts)

  def test_the_whole_fixture_is_read_back_including_its_last_partial_block(self):
    bat, _ = self.battery(corrupt=lambda img: img.__setitem__(len(img) - 1, img[-1] ^ 1))
    with self.assertRaisesRegex(ht.StepFail, 'read back the fixture'):
      bat.run(self.files, 'v1')
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
          bat.run(self.files, 'v1')
        last = bat.steps[-1]
        self.assertEqual((last['step'], last['pass'], last['evidence']['failedAt']), ('reenter', False, 'readback'))
        self.assertTrue(last['evidence']['dfuCameUp'] and last['evidence']['magicConsumed'])
        self.assertEqual((last['evidence']['appIntact'], last['evidence']['claim']),
                         ('unshown', 'the write/reset sequence re-entered DFU (register retention inferred)'))

  def test_commissioning_runs_the_control_first_and_no_probe_session_before_dfu(self):
    bat, rig = self.battery(commissioning=True)
    dfu = bat.dfu
    bat.dfu = lambda v: rig.scripts.append('dfu observed') or dfu(v)
    bat.run(self.files, 'v1')
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
      bat.run(self.files, 'v1')
    ev = bat.steps[-1]['evidence']
    self.assertEqual((bat.steps[-1]['step'], ev['controlBootedApp'], 'dfuCameUp' in ev), ('reenter', True, False))

  def test_a_control_that_lands_in_dfu_fails_without_a_decision(self):
    bat, rig = self.battery(commissioning=True)
    rig.double_reset = True
    with self.assertRaisesRegex(ht.StepFail, 'without the magic'):
      bat.run(self.files, 'v1')
    self.assertIs(bat.steps[-1]['evidence']['controlBootedApp'], False)

  def test_restore_reinstalls_the_record_and_leaves_dfu_after_blinky(self):
    bat, rig = self.battery()
    blinky = self.tmp / 'blinky.uf2'
    blinky.write_bytes(ht.pack_uf2([(bat.f['appStart'], bytes(256))], bat.f['family']))
    copies = []
    with mock.patch.object(ht, 'spawn', lambda cmd, *a, **k: copies.append(cmd) or rig.spawn(cmd, *a, **k)):
      out = bat.restore(dict(self.files, blinky=blinky, blinkyBlocks=1), 'v1')
    self.assertEqual((out['state'], out['evidence']['copy']), ('blinky copied', {'blocks': 1}))
    self.assertEqual(rig.scripts, [FLASHED(self.files['hex']), ['h', f'verifybin {self.tmp / "c.bin"},0x0', 'r', 'g']])
    self.assertEqual(copies[1][4], blinky)   # after the target's cmake
    rig.present, polls = True, []
    def blip(*a):   # DFU shows once, mid-way through the quiet period, then is gone again
      if rig.present:
        return '1-2'
      polls.append(1)
      return '1-2' if len(polls) == 3 else None
    with mock.patch.object(ht, 'usb_device', blip), self.assertRaisesRegex(ht.StepFail, 'came back after the blinky copy'):
      bat.restore(dict(self.files, blinky=blinky, blinkyBlocks=1), 'v1')

  def test_the_target_transcript_is_judged_not_its_exit(self):
    bat, _ = self.battery()
    hexp = self.files['hex']
    self.assertEqual(ht.judge_jlink_target(0, jlink_target(hexp), bat.b, hexp),
                     {'flashDownload': '1 range affected (65536 bytes)'})
    skip = 'Skipped. Contents already match'   # an already-matching image is a success
    self.assertEqual(ht.judge_jlink_target(0, jlink_target(hexp, skip), bat.b, hexp)['flashDownload'], skip)
    cases = (('every command FAILED, exit 0', 0, JLINK_NO_PROBE, True), ('no probe, exit 1', 1, JLINK_NO_PROBE, True),
             ('another image', 0, jlink_target(self.tmp / 'other.hex'), False),
             ('no O.K.', 0, jlink_target(hexp, tail=''), False),
             ('a failure line', 0, jlink_target(hexp, tail='O.K.\nCannot connect to target.\n'), False),
             ('cut short', 0, jlink_target(hexp).replace('Script processing completed.\n', ''), False),
             ('a nonzero exit', 2, jlink_target(hexp), False), ('nothing', 0, '', False))
    for what, code, out, before in cases:
      with self.subTest(what), self.assertRaisesRegex(ht.StepFail, 'the J-Link flash failed') as e:
        ht.judge_jlink_target(code, out, bat.b, hexp)
      self.assertEqual(e.exception.evidence['beforeTarget'], before, what)

  def test_the_rt_reset_vector_note_passes_in_the_target_transcript_on_rt_devices_only(self):
    hexp = self.tmp / 'tinyuf2.hex'
    out = jlink_target(hexp).replace('ResetTarget() start\n', 'ResetTarget() start\nCould not find valid reset vector.\n'
                                     'Target halted on flash header read.\n')
    ht.judge_jlink_target(0, out, {'device': 'MIMXRT1011DAE5A', 'probe': '1'}, hexp)
    with self.assertRaises(ht.StepFail):
      ht.judge_jlink_target(0, out, {'device': 'LPC55S69_M33_0', 'probe': '1'}, hexp)

  def test_the_f3_unprotect_note_passes_on_the_f303_only_and_only_whole(self):
    hexp = self.tmp / 'tinyuf2.hex'
    out = jlink_target(hexp).replace('ResetTarget() start\n', 'InitTarget() start\n' + F3_UNPROTECT + 'ResetTarget() start\n')
    f3 = {'device': 'stm32f303vc', 'probe': '1'}
    ht.judge_jlink_target(0, out, f3, hexp)
    for what, board, text in (('another device', {'device': 'MIMXRT1011DAE5A', 'probe': '1'}, out),
                              ('the unlock line alone', f3, out.replace(F3_UNPROTECT, 'Failed to unlock device.\n')),
                              ('no connect under reset', f3, out.replace('Can not attach to CPU. Trying connect under reset.\n', ''))):
      with self.subTest(what), self.assertRaises(ht.StepFail):
        ht.judge_jlink_target(0, text, board, hexp)

  def test_the_flash_runs_under_the_build_lock_between_two_input_checks(self):
    bat, rig = self.battery()
    fl, hexp = self.files['flash'], self.files['hex']
    judge = lambda code, out: ht.judge_jlink_target(code, out, bat.b, hexp)   # noqa: E731
    before = lambda code, out: ht.stopped_before_target(code, out, bat.b['probe'])   # noqa: E731

    def flash(run):
      return one_attempt(run(['JLinkExe', '-CommandFile', str(self.tmp / 'x.jlink')], timeout=5))
    (self.tmp / 'x.jlink').write_text(f'halt\nloadfile {hexp}\nr\ngo\nexit\n')
    with self.subTest('a build holds the dir'), ht.cb.build_lock(fl['root']), \
         self.assertRaisesRegex(ht.StepFail, 'in use by a build or another flash'):
      bat.flash_target(fl, flash, judge, before, 'JLinkExe', 5)
    good = hexp.read_text()
    hexp.write_text('changed')
    with self.subTest('an input changed'), self.assertRaisesRegex(ht.StepFail, 'changed before the flash'):
      bat.flash_target(fl, flash, judge, before, 'JLinkExe', 5)
    hexp.write_text(good)
    self.assertEqual((rig.scripts, bat.touched), ([], False))   # none of these ran the tool
    for what, result, touched in (('no probe', (1, JLINK_NO_PROBE), False),
                                  ('the target reached', (1, jlink_target(hexp, tail='Cannot connect to target.\n')), True)):
      bat.touched = False
      with self.subTest(what), mock.patch.object(ht, 'spawn', lambda *a, r=result, **k: r), \
           self.assertRaisesRegex(ht.StepFail, 'the J-Link flash failed'):
        bat.flash_target(fl, flash, judge, before, 'JLinkExe', 5)
      self.assertEqual(bat.touched, touched, what)
    bat.touched = False
    spawn = rig.spawn
    with self.subTest('rebuilt while flashing'), \
         mock.patch.object(ht, 'spawn', lambda cmd, *a, **k: (hexp.write_text('rebuilt'), spawn(cmd, *a, **k))[1]), \
         self.assertRaisesRegex(ht.StepFail, 'changed while flashing') as e:
      bat.flash_target(fl, flash, judge, before, 'JLinkExe', 5)
    self.assertEqual((bat.touched, e.exception.evidence['flashDownload']), (True, '1 range affected (65536 bytes)'))

  def test_dfu_after_an_install_reenters_only_when_dfu_never_enumerates(self):
    aircr = [f'w4 {ht.SCB_AIRCR:08X} {ht.AIRCR_SYSRESETREQ:08X}']
    for what, reentry, survives, version, err in (
        ('a valid app booted', 'retained-register', True, 'v1', None),
        ('uncommissioned', None, True, 'v1', 'has no retained-register re-entry'),
        ('another failure', 'retained-register', False, 'v2', 'INFO_UF2')):
      with self.subTest(what):
        self.tmp = Path(tempfile.mkdtemp(dir=self.tmp))
        bat, rig = self.battery(reentry=reentry)
        rig.app_survives = survives
        bat.install(self.files)
        if err:
          with self.assertRaisesRegex(ht.StepFail, err):
            bat.dfu_after_install(version)
          self.assertNotIn(aircr, rig.scripts)
        else:
          ev = bat.dfu_after_install(version)
          self.assertTrue(ev['dfuCameUp'] and ev['magicConsumed'])
          self.assertIn('did not enumerate after the install', ev['claim'])
          self.assertIn(aircr, rig.scripts)
    rig.app_survives = True   # the last case's rig: a re-entry whose final register read fails keeps what it saw
    bat.install(self.files)
    with mock.patch.object(bat.probe, 'mem32', side_effect=ht.StepFail('mem32 read gave no value')), \
         self.assertRaisesRegex(ht.StepFail, 'no value') as e:
      bat.dfu_after_install('v1')
    self.assertEqual((e.exception.evidence['dfuCameUp'], e.exception.evidence['usb']), (True, '1-2'))

  def test_a_wrong_version_on_the_drive_fails_dfu(self):

    bat, _ = self.battery()
    with self.assertRaisesRegex(ht.StepFail, 'INFO_UF2'):
      bat.run(self.files, 'v2')

  def test_a_left_magic_is_cleared_right_after_dfu_and_read_back(self):
    bat, rig = self.battery()
    reg = bat.f['dblTapReg']
    rig.mem[reg] = bat.f['dblTapMagic']
    dfu = bat.dfu
    bat.dfu = lambda v: rig.scripts.append('dfu observed') or dfu(v)
    bat.run(self.files, 'v1')
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
      bat.run(self.files, 'v1')
    self.assertEqual([(x['step'], x['pass']) for x in bat.steps][-1], ('dfu', False))

  def test_a_write_the_bus_dropped_fails_its_read_back(self):
    bat, rig = self.battery()
    rig.probe = lambda commands, judge=True: 'J-Link>mem32 4002C05C 1\n4002C05C = 00000000 \n'
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

  def test_the_rt1011_missing_reset_vector_note_is_benign(self):
    note = 'J-Link>r\nResetTarget() start\nCould not find valid reset vector.\nTarget halted on flash header read.\nJ-Link>g\n'
    metro = ht.Probe({'probe': '1', 'device': 'MIMXRT1011DAE5A', 'if': 'SWD', 'speed': '4000'}, self.tmp, None)
    with mock.patch.object(ht, 'spawn', lambda *a, **k: (0, note)):
      metro.run(['r', 'g'])
    with mock.patch.object(ht, 'spawn', lambda *a, **k: (0, note + 'Could not read memory.\n')), \
         self.assertRaisesRegex(ht.StepFail, 'JLinkExe failed'):
      metro.run(['r', 'g'])

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

  def test_a_reset_session_passes_only_once_its_write_was_issued_on_a_connected_target(self):
    aircr = [f'w4 {ht.SCB_AIRCR:08X} {ht.AIRCR_SYSRESETREQ:08X}']
    issued = f'J-Link>{aircr[0]}\nCortex-M4 identified.\nWriting 05FA0004 -> E000ED0C\n'
    f3 = ht.Probe({'probe': '1', 'device': 'stm32f303vc', 'if': 'SWD', 'speed': '4000'}, self.tmp, None)
    for what, code, out in (('dropped after the write', 1, issued + 'Cannot read register 15 (R15)\n'),
                            ('after the F3 unprotect note', 0, issued.replace('Cortex-M4', F3_UNPROTECT + 'Cortex-M4'))):
      with self.subTest(what), mock.patch.object(ht, 'spawn', lambda *a, c=code, o=out, **k: (c, o)):
        f3.run(aircr, judge=False)
    for what, code, out in (('never connected', 1, f'J-Link>{aircr[0]}\nError occurred: Could not connect to the target device.\n'),
                            ('unlock alone', 1, f'J-Link>{aircr[0]}\nFailed to unlock device.\nWriting 05FA0004 -> E000ED0C\n'),
                            ('no transcript', 0, '')):
      with self.subTest(what), mock.patch.object(ht, 'spawn', lambda *a, c=code, o=out, **k: (c, o)), \
           self.assertRaisesRegex(ht.StepFail, 'reset write was not issued'):
        f3.run(aircr, judge=False)

  def test_an_f411_session_connects_as_its_core_and_others_as_the_roster_device(self):
    for device, want in (('stm32f411ve', 'Cortex-M4'), ('stm32f303vc', 'stm32f303vc')):
      probe = ht.Probe({'probe': '1', 'device': device, 'if': 'SWD', 'speed': '4000'}, self.tmp, None)
      seen = []
      with self.subTest(device), mock.patch.object(ht, 'spawn', lambda cmd, *a, **k: seen.append(cmd) or (0, 'ok')):
        probe.run(['h'])
      self.assertEqual(seen[0][seen[0].index('-device') + 1], want)

  def test_a_failed_reset_fails_the_session(self):
    out = 'J-Link>r\nResetTarget failed (-1).\nFailed to halt CPU.\nJ-Link>g\n\n****** Error: CPU is not halted\n'
    probe = ht.Probe({'probe': '1', 'device': 'd', 'if': 'SWD', 'speed': '4000'}, self.tmp, None)
    with mock.patch.object(ht, 'spawn', lambda *a, **k: (0, out)), self.assertRaisesRegex(ht.StepFail, 'JLinkExe failed'):
      probe.run(['r', 'g'])


class StaysAway(unittest.TestCase):
  def test_the_window_end_is_sampled_after_the_last_sleep(self):
    clock = [0.0]
    sleep = lambda t: clock.__setitem__(0, clock[0] + t)   # noqa: E731
    with mock.patch.object(ht.time, 'monotonic', lambda: clock[0]), mock.patch.object(ht.time, 'sleep', sleep):
      with self.assertRaisesRegex(ht.StepFail, 'came back'):   # back at 0.9 s, inside a 1 s window
        ht.stays_away(lambda: clock[0] >= 0.9, 1.0, 'came back', {})
      clock[0] = 0.0
      ht.stays_away(lambda: clock[0] > 1.0, 1.0, 'came back', {})   # back only after the window


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
    ev = {'controlBootedApp': True, 'dfuCameUp': True, 'magicConsumed': True,
          'detachAcked': True, 'appLeft': True}
    ev.update(obs)
    if failed_at:
      ev['failedAt'] = failed_at
    steps = [{'step': s, 'pass': True, 'evidence': {}} for s in ht.STEPS['jlink'][:-1]]
    steps.append({'step': 'reenter', 'pass': passed, 'evidence': ev})
    return {'commissioning': True, 'tried': tried, 'pass': passed, 'steps': steps,
            'cleanup': {'pass': cleaned, 'heldAfter': held}}

  def test_the_commissioning_decision(self):
    for method in (*ht.REENTRY['jlink'], *ht.REENTRY['esp']):
      with self.subTest(method):
        self.assertEqual(ht.reentry_decision(self.row(method)), method)
        self.assertEqual(ht.reentry_decision(self.row(method, passed=False, failed_at='readback')), method)
        self.assertIsNone(ht.reentry_decision(self.row(method, passed=False)))            # failed entry
        self.assertIsNone(ht.reentry_decision(self.row(method, dfuCameUp=False)))
        self.assertIsNone(ht.reentry_decision(self.row(method, cleaned=False)))           # failed cleanup
        self.assertIsNone(ht.reentry_decision(self.row(method, held=True)))
    self.assertIsNone(ht.reentry_decision(self.row(controlBootedApp=False)))
    early = self.row(passed=False, failed_at='readback')
    early['steps'][3]['pass'] = False
    self.assertIsNone(ht.reentry_decision(early))                                          # another step failed too
    self.assertIsNone(ht.reentry_decision(dict(self.row(), commissioning=False)))
    self.assertIsNone(ht.reentry_decision(dict(self.row(), **{'pass': False})))   # aborted after every step passed


class PendingMark(Tmp):
  def setUp(self):
    super().setUp()
    self.mark = ht.PendingMark(None, 'b')
    self.ended = self.receipt('ended', closed=True, cleanup='done')
    self.unresolved = self.receipt('unresolved', closed=True, cleanup='pending')

  def receipt(self, name, **rec):
    p = self.tmp / name / 'receipt.json'
    p.parent.mkdir()
    p.write_text(json.dumps({'tool': 'hil_openocd_esp', **rec}))
    return {'cmd': 'openocd', 'receipt': str(p)}

  def racing(self, name, other):
    """Run `other` in a thread the first time `name` runs, inside the caller's critical section, and give it 0.5 s
    to finish there; without the mutex it does."""
    real, done = getattr(ht, name), []

    def hooked(*a):
      if not done:
        t = threading.Thread(target=other)
        t.start()
        t.join(0.5)
        done.append(t)
      return real(*a)
    return mock.patch.object(ht, name, hooked), done

  def test_two_writers_never_lose_a_session(self):
    patch, done = self.racing('read_mark', lambda: ht.mark_pending(self.mark, [self.unresolved]))
    with patch:
      ht.mark_pending(self.mark, [self.ended])
    done[0].join(5)
    self.assertEqual(sorted(e['receipt'] for e in ht.read_mark(self.mark)),
                     sorted([self.ended['receipt'], self.unresolved['receipt']]))

  def test_a_check_never_removes_a_session_written_while_it_checked(self):
    ht.mark_pending(self.mark, [self.ended])
    patch, done = self.racing('session_state', lambda: ht.mark_pending(self.mark, [self.unresolved]))
    with patch:
      ht.clear_pending_mark(self.mark)   # it saw only the ended session
    done[0].join(5)
    with self.assertRaisesRegex(ht.Refused, 'not ended'):
      ht.clear_pending_mark(self.mark)
    self.assertEqual([e['receipt'] for e in ht.read_mark(self.mark)], [self.unresolved['receipt']])

  def test_a_write_makes_its_rename_durable_and_reports_a_failure_to(self):
    real, dirs = os.fsync, []

    def fsync(fd):
      if os.path.isdir(f'/proc/self/fd/{fd}'):
        dirs.append(fd)
        raise OSError(5, 'Input/output error')
      return real(fd)
    with mock.patch.object(ht.os, 'fsync', fsync), mock.patch.object(ht, 'MARK_ERRORS', []):
      self.assertIn('Input/output error', ht.mark_pending(self.mark, [self.ended]))
      self.assertEqual(len(ht.MARK_ERRORS), 1)
    self.assertEqual(len(dirs), 1)

  def test_each_write_has_a_temp_file_of_its_own(self):
    seen, real = [], os.replace
    with mock.patch.object(ht.os, 'replace', lambda a, b, **k: (seen.append(a), real(a, b, **k))[1]):
      ht.mark_pending(self.mark, [self.ended])
      ht.mark_pending(self.mark, [self.unresolved])
    self.assertEqual(len(set(seen)), 2)
    self.assertNotIn(f'{self.mark.name}.tmp', seen)
    self.assertEqual(sorted(p.name for p in (self.tmp / 'marks').iterdir()),
                     [self.mark.name, self.mark.name + ht.MARK_MUTEX])

  def clear(self, *extra):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht, 'load_helper', lambda: self.mark_helper), \
         mock.patch.object(ht, 'PendingMark', lambda helper, lock: self.mark):
      code = ht.main(['clear-pending', '-b', BOARD, *extra, str(cfg)])
    return code, json.loads(out.getvalue())

  def hold(self):
    """This process's own manual hold of the board, as `hil_lock.py hold` leaves it."""
    lock = ht.load_board(roster(self.tmp, tinyuf2={'reentry': None}), BOARD)['lock']
    fh = self.mark_helper.flock_nb(lock)
    self.addCleanup(fh.close)
    self.mark_helper.write_record(fh, 'mine')
    return lock

  def test_a_first_run_creates_the_lock_dir_through_the_helper_and_finds_no_mark(self):
    self.assertFalse((self.tmp / 'marks').exists())
    ht.clear_pending_mark(self.mark)
    self.assertEqual(stat_mode(self.tmp / 'marks'), self.mark_helper.DIR_MODE)

  def test_the_mark_and_its_mutex_are_umask_proof(self):
    old = os.umask(0o077)
    try:
      ht.mark_pending(self.mark, [self.ended])
    finally:
      os.umask(old)
    self.assertEqual((stat_mode(str(self.mark) + ht.MARK_MUTEX), stat_mode(self.mark)), (0o666, 0o644))

  def test_a_malformed_mark_is_kept_reported_and_cleared_only_after_a_reviewed_recovery(self):
    (self.tmp / 'marks').mkdir()
    Path(self.mark).write_text('{"sessions": [{}]}')
    with mock.patch.object(ht, 'MARK_ERRORS', []):
      self.assertIn('malformed', ht.mark_pending(self.mark, [self.unresolved]))
    self.assertEqual(Path(self.mark).read_text(), '{"sessions": [{}]}')
    with self.assertRaisesRegex(ht.Refused, 'malformed'):
      ht.clear_pending_mark(self.mark)
    self.assertEqual(self.clear()[0], 2)
    self.hold()
    code, out = self.clear('--after-reviewed-recovery', 'reviewed in #9', '--under-hold', 'mine')
    self.assertEqual((code, out['cleared']['unreadable']), (0, '{"sessions": [{}]}'))
    self.assertFalse(Path(self.mark).exists())

  def test_clear_pending_refuses_while_a_session_is_not_ended_naming_its_receipt(self):
    ht.mark_pending(self.mark, [self.ended, self.unresolved])
    self.assertIn(self.unresolved['receipt'], self.clear()[1]['error'])
    self.hold()
    for extra, why in (([], 'not ended'), (['--after-reviewed-recovery', ' ', '--under-hold', 'mine'], 'needs the note'),
                       (['--after-reviewed-recovery', 'n'], 'needs proof'),
                       (['--after-reviewed-recovery', 'n', '--under-hold', 'theirs'], "not 'theirs'"),
                       (['--after-reviewed-recovery', 'n', '--recover-holder', str(os.getpid())], "not 'hil_test.py'")):
      with self.subTest(extra):
        code, out = self.clear(*extra)
        self.assertEqual((code, out['pass']), (2, False))
        self.assertIn(why, out['error'])
    self.assertTrue(Path(self.mark).exists())

  def test_a_forced_clear_waits_for_no_recovery_already_running(self):
    ht.mark_pending(self.mark, [self.unresolved])
    lock = self.hold()
    busy = ht.recovery_lock(self.mark_helper, lock)
    self.addCleanup(busy.close)
    code, out = self.clear('--after-reviewed-recovery', 'n', '--under-hold', 'mine')
    self.assertEqual(code, 2)
    self.assertIn('another recovery', out['error'])
    self.assertTrue(Path(self.mark).exists())

  def test_clear_pending_removes_a_mark_once_every_session_ended(self):
    ht.mark_pending(self.mark, [self.ended])
    code, out = self.clear()   # no hold needed: the mark's mutex suffices
    self.assertEqual((code, out['cleared']['notEnded']), (0, []))
    self.assertFalse(Path(self.mark).exists())
    self.assertFalse(Path(str(self.mark) + ht.CLEARED_LOG).exists())
    self.assertEqual(self.clear()[0], 0)   # no mark: nothing to clear

  def test_clear_pending_after_a_reviewed_recovery_records_its_note_and_hold_then_removes_the_mark(self):
    ht.mark_pending(self.mark, [self.ended, self.unresolved])
    self.hold()
    code, out = self.clear('--after-reviewed-recovery', 'server ended by the reviewed recovery in #123',
                           '--under-hold', 'mine')
    self.assertEqual((code, out['cleared']['notEnded']), (0, [self.unresolved['receipt']]))
    self.assertFalse(Path(self.mark).exists())
    log = [json.loads(x) for x in Path(str(self.mark) + ht.CLEARED_LOG).read_text().splitlines()]
    self.assertEqual([(x['note'], x['notEnded'], x['hold']['reason'], x['hold']['pid']) for x in log],
                     [('server ended by the reviewed recovery in #123', [self.unresolved['receipt']], 'mine',
                       os.getpid())])


class Main(Tmp):
  def setUp(self):
    super().setUp()
    p = mock.patch.object(ht, 'probe_users', lambda b: [])   # not the host's J-Link tools
    p.start()
    self.addCleanup(p.stop)

  def test_manual_install_runs_the_record_and_brings_up_dfu_with_reentry_only_on_trial(self):
    for what, reentry, extra, want, calls in (
        ('uncommissioned', None, [], 0, [('install', None), ('dfu', 'v')]),
        ('a trial', None, ['--try-reentry', 'retained-register'], 0, [('install', 'retained-register'), ('dfu', 'v')]),
        ('a trial once commissioned', 'retained-register', ['--try-reentry', 'retained-register'], 2, [])):
      seen = []
      cfg = roster(self.tmp, tinyuf2={'reentry': reentry})
      with self.subTest(what), contextlib.redirect_stdout(io.StringIO()), \
           mock.patch.object(ht.cb, 'BUILD_DIR', Path(tempfile.mkdtemp(dir=self.tmp))), \
           mock.patch.object(ht, 'load_helper', lambda: None), mock.patch.object(ht, 'manual_holder', lambda *a: None), \
           mock.patch.object(ht, 'admit_record', lambda *a: ({'bin': 'b'}, {'version': 'v'})), \
           mock.patch.object(ht.Battery, 'install', lambda bat, f: seen.append(('install', bat.b['reentry'])) or {}), \
           mock.patch.object(ht.Battery, 'dfu_after_install', lambda bat, v: seen.append(('dfu', v)) or {}):
        code = ht.main(['install', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'debug 7', *extra, str(cfg)])
        self.assertEqual((code, seen), (want, calls))

  def test_manual_install_and_restore_flash_the_record_hex_through_the_provider(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    build = self.tmp / 'build'
    build.mkdir()
    hexp = build / 'tinyuf2.hex'
    hexp.write_text(':00000001FF\n')
    blinky = self.tmp / 'blinky.uf2'
    blinky.write_bytes(ht.pack_uf2([(0x10000, bytes(256))], LPC_FACTS['family']))
    files = {'bin': self.tmp / 'c.bin', 'hex': hexp, 'blinky': blinky, 'blinkyBlocks': 1,
             'flash': {'root': build, 'binding': {'target': 'tinyuf2-jlink'}, 'sha256': {'tinyuf2.hex': ht.sha256(hexp)}}}
    flashed, clock = [], [0.0]

    def spawn(cmd, log, timeout, cwd=None, **k):
      if cmd[0] == 'JLinkExe':
        flashed.append(Path(cmd[-1]).read_text())
        return 0, jlink_target(hexp)
      return 0, ''   # mcopy, sync
    for argv in (['install', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x'],
                 ['restore', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x']):
      out = io.StringIO()
      with self.subTest(argv[0]), contextlib.redirect_stdout(out), \
           mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / argv[0]), mock.patch.object(ht, 'load_helper', lambda: None), \
           mock.patch.object(ht, 'manual_holder', lambda *a: None), \
           mock.patch.object(ht, 'admit_record', lambda *a: (files, {'version': 'v'})), mock.patch.object(ht, 'spawn', spawn), \
           mock.patch.object(ht.Probe, 'run', lambda *a, **k: ''), \
           mock.patch.object(ht.Battery, 'dfu_after_install', lambda bat, v: {'usb': '1-2'}), \
           mock.patch.object(ht, 'block_device', lambda p: '/dev/sdz'), mock.patch.object(ht, 'usb_device', lambda *a: None), \
           mock.patch.object(ht.time, 'sleep', lambda t: clock.__setitem__(0, clock[0] + t)), \
           mock.patch.object(ht.time, 'monotonic', lambda: clock[0]):
        self.assertEqual(ht.main(argv + [str(cfg)]), 0, out.getvalue())
    self.assertEqual(flashed, [f'halt\nloadfile {hexp}\nr\ngo\nexit\n'] * 2)

  def test_a_manual_install_overlaps_neither_a_probe_user_nor_an_earlier_invocations_pending_session(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    receipt = self.tmp / 'earlier' / 'receipt.json'
    receipt.parent.mkdir()
    receipt.write_text(json.dumps({'tool': 'hil_openocd_esp', 'closed': False, 'init': 'ok'}))
    for what, users, pending, want in (('a probe user', [101], [], 'still in use by pids'),
                                       ('a pending session', [], [{'cmd': 'openocd', 'receipt': str(receipt)}],
                                        'not ended')):
      installed, out = [], io.StringIO()
      ht.mark_pending(ht.PendingMark(None, ht.load_board(cfg, BOARD)['lock']), pending)
      with self.subTest(what), contextlib.redirect_stdout(out), \
           mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / what), mock.patch.object(ht, 'load_helper', lambda: None), \
           mock.patch.object(ht, 'manual_holder', lambda *a: None), mock.patch.object(ht, 'probe_users', lambda b: users), \
           mock.patch.object(ht, 'admit_record', lambda *a: ({}, {'version': 'v'})), \
           mock.patch.object(ht.Battery, 'install', lambda bat, f: installed.append(1) or {}):
        code = ht.main(['install', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x', str(cfg)])
      self.assertEqual((code, installed), (2, []))
      self.assertIn(want, out.getvalue())

  def test_a_manual_install_whose_pending_mark_cannot_be_written_still_reports_and_keeps_the_hold(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    left = [{'cmd': 'openocd', 'receipt': str(self.tmp / 'r' / 'receipt.json')}]

    def enospc(*a):
      raise OSError(28, 'No space left on device')
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / 'b'), \
         mock.patch.object(ht, 'load_helper', lambda: None), mock.patch.object(ht, 'manual_holder', lambda *a: None), \
         mock.patch.object(ht, 'write_mark', enospc), \
         mock.patch.object(ht, 'MARK_ERRORS', []), mock.patch.object(ht, 'outstanding_sessions', lambda d: left), \
         mock.patch.object(ht, 'admit_record', lambda *a: ({}, {'version': 'v'})), \
         mock.patch.object(ht.Battery, 'install', lambda bat, f: {}), \
         mock.patch.object(ht.Battery, 'dfu_after_install', lambda bat, v: {}):
      code = ht.main(['install', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x', str(cfg)])
    report = json.loads(out.getvalue().splitlines()[-1])
    self.assertEqual((code, report['pass'], report['survivors']), (4, False, left))
    self.assertIn('could not be written', report['markErrors'][0])

  def test_an_install_that_fails_after_touching_the_board_is_exit_4(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    for touched, want in ((True, 4), (False, 1)):
      def fail(bat, files, touched=touched):
        bat.touched = touched
        raise ht.StepFail('the J-Link flash failed (exit 1)')
      with self.subTest(touched), contextlib.redirect_stdout(io.StringIO()), \
           mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / f'i{want}'), mock.patch.object(ht, 'load_helper', lambda: None), \
           mock.patch.object(ht, 'manual_holder', lambda *a: None), \
           mock.patch.object(ht, 'admit_record', lambda *a: ({}, {'version': 'v'})), mock.patch.object(ht.Battery, 'install', fail):
        self.assertEqual(ht.main(['install', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x', str(cfg)]), want)

  def test_a_restore_that_fails_after_touching_the_board_is_exit_4(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    for touched, want in ((True, 4), (False, 1)):
      def fail(bat, files, version, touched=touched):
        bat.touched = touched
        raise ht.StepFail('the DFU device came back after the blinky copy')
      with self.subTest(touched), contextlib.redirect_stdout(io.StringIO()), \
           mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / str(want)), mock.patch.object(ht, 'load_helper', lambda: None), \
           mock.patch.object(ht, 'manual_holder', lambda *a: None), \
           mock.patch.object(ht, 'admit_record', lambda *a: ({}, {'version': 'v'})), mock.patch.object(ht.Battery, 'restore', fail):
        self.assertEqual(ht.main(['restore', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x', str(cfg)]), want)

  def test_a_recovery_while_another_runs_is_refused_before_it_checks_the_holder(self):
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    report = self.tmp / 'failed.json'
    report.write_text(json.dumps({'results': [{'board': BOARD, 'cleanup': {'holder': {'pid': 4242}}}]}))
    busy = mock.Mock(side_effect=ht.Refused(f'{BOARD}: another recovery holds x.lock.recover'))
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp), \
         mock.patch.object(ht, 'load_helper', lambda: None), mock.patch.object(ht, 'check_jlink', lambda: None), \
         mock.patch.object(ht, 'recovery_lock', busy), \
         mock.patch.object(ht, 'prove_hold', side_effect=AssertionError('checked the holder')), \
         mock.patch.object(ht, 'admit_record', lambda *a: ({}, {'version': 'v'})), \
         mock.patch.object(ht.Battery, 'restore', side_effect=AssertionError('probed')):
      code = ht.main(['restore', '-b', BOARD, '--build-record', 'r.json', '--recover-holder', '4242', '--report', str(report),
                      str(cfg)])
    self.assertEqual((code, json.loads(out.getvalue().splitlines()[-1])['error']),
                     (2, f'{BOARD}: another recovery holds x.lock.recover'))
    self.assertEqual(busy.call_count, 1)

  def test_a_recovery_is_refused_while_a_session_of_the_failed_run_is_unresolved_without_a_pending_mark(self):
    holder = self.tmp / 'hil_test.py'
    holder.write_text('import time; time.sleep(30)')
    p = subprocess.Popen([sys.executable, str(holder)])
    self.addCleanup(lambda: (p.kill(), p.wait()))
    end = time.monotonic() + 10
    while b'hil_test.py' not in Path(f'/proc/{p.pid}/cmdline').read_bytes() and time.monotonic() < end:
      time.sleep(0.01)
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    receipt = self.tmp / 'oocd' / 'receipt.json'
    receipt.parent.mkdir()
    receipt.write_text(json.dumps({'tool': 'hil_openocd_esp', 'closed': True, 'cleanup': 'pending'}))
    report = self.tmp / 'failed.json'
    report.write_text(json.dumps({'results': [{'board': BOARD, 'cleanup': {
        'holder': {'pid': p.pid}, 'survivors': [{'cmd': 'openocd', 'receipt': str(receipt)}]}}]}))
    mark = ht.PendingMark(None, ht.load_board(cfg, BOARD)['lock'])
    for what, reviewed, want in (('unreviewed', False, 2), ('cleared after a reviewed recovery', True, 0)):
      if reviewed:
        ht.mark_pending(mark, [{'cmd': 'openocd', 'receipt': str(receipt)}])
        ht.clear_pending_mark(mark, 'server ended by the reviewed recovery in #9', {})
      self.assertFalse(Path(mark).exists())
      killed, out = [], io.StringIO()
      with self.subTest(what), contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / str(want)), \
           mock.patch.object(ht, 'load_helper', mock.Mock), mock.patch.object(ht, 'check_jlink', lambda: None), \
           mock.patch.object(ht, 'admit_record', lambda *a: ({}, {'version': 'v'})), \
           mock.patch.object(ht, 'recovery_lock', lambda *a: mock.Mock()), mock.patch.object(ht, 'prove_hold', lambda *a, **k: {}), \
           mock.patch.object(ht.os, 'kill', lambda *a: killed.append(a)), mock.patch.object(ht, 'wait_for', lambda *a: True), \
           mock.patch.object(ht.Battery, 'restore', lambda bat, f, v: {'pass': True}):
        code = ht.main(['restore', '-b', BOARD, '--build-record', 'r.json', '--recover-holder', str(p.pid), '--report',
                        str(report), str(cfg)])
        self.assertEqual((code, killed), (want, [] if want else [(p.pid, signal.SIGUSR1)]))
        if want:
          self.assertIn(str(receipt), json.loads(out.getvalue().splitlines()[-1])['error'])

  def test_an_esptool_recovery_checks_the_snapshot_in_the_failed_report(self):
    holder = self.tmp / 'hil_test.py'
    holder.write_text('import time; time.sleep(30)')
    p = subprocess.Popen([sys.executable, str(holder)])
    self.addCleanup(lambda: (p.kill(), p.wait()))
    # recovery reads the holder's cmdline, which names hil_test.py only once the child has exec'd
    end = time.monotonic() + 10
    while b'hil_test.py' not in Path(f'/proc/{p.pid}/cmdline').read_bytes() and time.monotonic() < end:
      time.sleep(0.01)
    cfg = s3_roster(self.tmp)
    keep = self.load(cfg, S3)['regions']['preserved']
    md5 = {n: 'ab' * 16 for n in keep}
    report = self.tmp / 'failed.json'
    for what, regions, want in (('the same layout', keep, 0), ('another layout', {'nvs': (0x9000, 0xe000)}, 2)):
      report.write_text(json.dumps({'results': [{'board': S3, 'cleanup': {'holder': {'pid': p.pid}, 'state': 'unknown'},
                                                 'snapshot': {'preserved': {n: md5[n] for n in regions},
                                                              'preservedRegions': {n: list(r) for n, r in regions.items()}}}]}))
      seen = []
      with self.subTest(what), contextlib.redirect_stdout(io.StringIO()), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / str(want)), \
           mock.patch.object(ht, 'load_helper', mock.Mock), \
           mock.patch.object(ht, 'admit_record', lambda *a: ({}, {'version': 'v'})), \
           mock.patch.object(ht, 'recovery_lock', lambda *a: mock.Mock()), mock.patch.object(ht, 'prove_hold', lambda *a, **k: {}), \
           mock.patch.object(ht.os, 'kill', lambda *a: None), \
           mock.patch.object(ht, 'wait_for', lambda *a: True), \
           mock.patch.object(ht.EspBattery, 'restore', lambda bat, f, v: seen.append(bat.preserved) or {'pass': True}):
        code = ht.main(['restore', '-b', S3, '--build-record', 'r.json', '--recover-holder', str(p.pid), '--report',
                        str(report), str(cfg)])
        self.assertEqual(code, want)
        self.assertEqual(seen, [md5] if want == 0 else [])

  def test_no_jlinkexe_programs_nothing_on_any_path(self):
    fw = bootloader_bin(self.tmp / 'fw.bin')
    cfg = roster(self.tmp, tinyuf2={'reentry': None})
    probed = []
    for argv in (['install', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x'],
                 ['restore', '-b', BOARD, '--build-record', 'r.json', '--under-hold', 'x']):
      with self.subTest(argv[0]), contextlib.redirect_stdout(io.StringIO()), \
           mock.patch.object(ht, 'verify_record', lambda *a: ({'hex': 'x.hex', 'bin': fw}, {'version': 'v'})), \
           mock.patch.object(ht, 'parse_hex', lambda p: {0: 1}), mock.patch.object(ht, 'hex_matches_bin', lambda *a: True), \
           mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / argv[0]), mock.patch.object(ht, 'load_helper', lambda: None), \
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

  def test_run_root_places_the_run_directory(self):
    cfg = roster(self.tmp, flasher={'name': 'jlink', 'uid': '1', 'args': '-device NOPE'})
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp / 'unused'):
      ht.main(['run', '-b', BOARD, '--build-record', 'r.json', '--run-root', str(self.tmp / 'here'), str(cfg)])
    r = json.loads(out.getvalue().splitlines()[-1])
    self.assertEqual(Path(r['reportPath']).parent.parent, self.tmp / 'here')
    self.assertFalse((self.tmp / 'unused').exists())

  def test_a_lock_pin_refusal_stops_a_run_before_its_record_and_battery(self):
    cfg = roster(self.tmp)
    admit, battery = mock.Mock(), mock.Mock()
    pin = mock.Mock(side_effect=ht.Refused('lib/agentrc is at b; HEAD pins a'))
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(ht.cb, 'BUILD_DIR', self.tmp), \
         mock.patch.object(ht, 'check_lock_pin', pin), \
         mock.patch.object(ht, 'admit_record', admit), mock.patch.object(ht.Battery, 'run', battery):
      code = ht.main(['run', '-b', BOARD, '--build-record', 'r.json', str(cfg)])
    res = json.loads(out.getvalue().splitlines()[-1])
    self.assertEqual((code, res['error'], [{k: r[k] for k in ('ran', 'pass', 'locked')} for r in res['results']]),
                     (2, 'lib/agentrc is at b; HEAD pins a', [{'ran': False, 'pass': False, 'locked': False}]))
    pin.assert_called_once_with()
    admit.assert_not_called()
    battery.assert_not_called()


H563 = {'port': 'stm32h5', 'name': 'stm32h563_nucleo', 'device': 'stm32h563zi', 'flasher': 'stlink'}
CUBE_CONNECT = ('ST-LINK SN  : 0023\nST-LINK FW  : V3J16M9\nBoard       : NUCLEO-H563ZI\nVoltage     : 3.26V\n'
                'SWD freq    : 8000 KHz\nConnect mode: Hot Plug\nReset mode  : Software reset\nDevice ID   : {dev}\n'
                'Revision ID : Rev Z\nDevice name : STM32H56x/573\nNVM size    : {nvm}\nDevice type : MCU\n'
                'Device CPU  : Cortex-M33\nBL Version  : 0xE3\nSFSP Version: v2.2.0\nDebug in Low Power mode enabled\n')


def stlink_target(error='', start='Start operation achieved successfully\n', nvm='2 MBytes'):
  """tinyuf2-stlink's transcript through CMake and Ninja, as the bench recorded it on stm32h563_nucleo (v2.23.0)."""
  return ('[1/1] cd /b && STM32_Programmer_CLI --connect port=swd sn=0023 --write /b/tinyuf2.hex --go\n'
          '      -------------------------------------------------------------------\n'
          '                        \x1b[01;34mSTM32CubeProgrammer v2.23.0\x1b[0m\n' +
          CUBE_CONNECT.format(dev='0x484', nvm=nvm).replace('Hot Plug', 'Normal') +
          'Opening and parsing file: tinyuf2.hex\nMemory Programming ...\n  File          : tinyuf2.hex\n'
          '  Size          : 15.17 KB \n  Address       : 0x08000000\nErasing memory corresponding to segment 0:\n'
          'Erasing internal memory sectors [0 1]\nDownload in Progress:\n[==================================================] 100% \n'
          f'{error}File download complete\nTime elapsed during download operation: 00:00:00.120\nRUNNING Program ... \n'
          f'  Address:      : 0x8000000\nApplication is running, Please Hold on...\n{start}')


class FakeCube:
  """STM32_Programmer_CLI -script, answering each operation in the shape the bench recorded (v2.23.0)."""

  def __init__(self, dev='0x484', nvm='2 MBytes'):
    self.dev, self.nvm, self.scripts, self.mem, self.flash, self.connects = dev, nvm, [], {}, {}, []
    self.r0, self.pc, self.sp, self.vtor = 5, 0x08008400, 0x20001000, 0x08008000
    self.on_reset, self.break_op = None, None

  def run(self, script):
    lines = Path(script).read_text().splitlines()
    self.scripts.append(lines[1:])
    self.connects.append(lines[0])
    out = '=== Script Manager BEGIN ===\n'
    for i, line in enumerate(lines, 1):
      out += f'Operation [{i}]: {line} \n'
      if self.break_op and self.break_op(line):
        return 1, out + 'Error: failed to read the requested memory content\n'
      if i == 1:
        out += CUBE_CONNECT.format(dev=self.dev, nvm=self.nvm)
      elif line == '-halt':
        out += 'Core halted\n'
      elif line == '-run':
        out += 'Core run\n'
      elif line.startswith('#Delay('):
        out += f'The system go to sleep for {line[7:-1]} ms.\n'
      elif line == '-coreReg':
        self.r0 += 7
        out += (f'R0       = 0x{self.r0:08X}\nR1       = 0x00000001\nSP       = 0x{self.sp:08X}\nLR       = 0x08002DA5\n'
                f'PC       = 0x{self.pc:08X}\nXPSR     = 0x01000000\nMSP      = 0x{self.sp:08X}\nPSP      = 0x00000000\n')
      elif line.startswith('-r32 '):
        a = int(line.split()[1], 16)
        v = self.vtor if a == ht.SCB_VTOR else self.mem.get(a, 0)
        out += f'Reading 32-bit memory content\n  Size          : 4 Bytes\n  Address:      : 0x{a:08X}\n0x{a:08X} : {v:08X}\n'
      elif line.startswith('-w32 '):
        _, a, v, *nv = line.split()
        out += f'Write 32-bit data\nw @{a.lower()}:  {v.lower()}\nDownloading...\n32-bit data download complete\n'
        if int(a, 16) == ht.SCB_AIRCR and self.on_reset:
          self.on_reset()
        else:
          self.mem[int(a, 16)] = int(v, 16)
      elif line.startswith('-u '):
        _, a, n, path = line.split()
        Path(path).write_bytes(self.flash.get(int(a, 16), b'')[:int(n, 16)])
        out += f'UPLOADING ...\n  File          : {Path(path).name}\n  Size          : {int(n, 16)} Bytes\nData read successfully\n'
      elif line == '-rst':
        out += 'MCU Reset\nSoftware reset is performed\n'
    return 0, out + 'Device is disconnected\n=== Script Manager END === \n'


class Stlink(Tmp):
  """The ST-LINK probe sessions over a fake CLI: the plumbing, not the rig."""

  def setUp(self):
    super().setUp()
    self.cube = FakeCube()
    self.board = {'name': 'stm32h563_nucleo', 'probe': '0023', 'device': 'stm32h563zi', 'flasher': 'stlink'}
    self.probe = ht.StlinkProbe(self.board, self.tmp, self.tmp / 'log')
    self.answer = None
    p = mock.patch.object(ht, 'spawn', lambda cmd, log, timeout, **k: self.answer(cmd) if self.answer else
                          self.cube.run(cmd[2]))
    p.start()
    self.addCleanup(p.stop)

  def test_a_session_connects_hotplug_to_the_roster_probe_and_returns_each_operation(self):
    self.cube.mem[0x2009FFFC] = 0xF01669EF
    self.assertEqual(self.probe.mem32([0x2009FFFC, ht.SCB_VTOR]), {0x2009FFFC: 0xF01669EF, ht.SCB_VTOR: 0x08008000})
    self.assertEqual((self.cube.connects[0], self.cube.scripts[0]),
                     ('-c port=SWD sn=0023 mode=HOTPLUG', ['-r32 0x2009FFFC 1', f'-r32 0x{ht.SCB_VTOR:08X} 1']))
    self.assertEqual(list(self.tmp.glob('*.prg')), [])   # the provider's script file, in the run dir, is gone
    self.assertEqual(self.probe.write32(0x20000FFC, 0x12345678), '0x12345678')
    self.assertEqual(self.cube.scripts[-1], ['-halt', '-w32 0x20000FFC 0x12345678', '-r32 0x20000FFC 1', '-run'])

  def test_a_session_fails_unless_the_transcript_shows_the_roster_chip_and_every_operation(self):
    ok, broken = self.cube.run, FakeCube()
    broken.break_op = lambda line: line == '-run'
    for what, answer in (
        ('another family', lambda cmd: FakeCube(dev='0x480').run(cmd[2])),
        ('another size', lambda cmd: FakeCube(nvm='1 MBytes').run(cmd[2])),
        ('exit 0 with an error line', lambda cmd: (0, ok(cmd[2])[1].replace('Core run', 'Error: x'))),
        ('a nonzero exit', lambda cmd: (1, ok(cmd[2])[1])),
        ('no script end', lambda cmd: (0, ok(cmd[2])[1].replace('=== Script Manager END ===', ''))),
        ('an operation missing', lambda cmd: (0, ok(cmd[2])[1].replace('Operation [3]: -run', 'x'))),
        ('no halt result', lambda cmd: (0, ok(cmd[2])[1].replace('Core halted', ''))),
        ('no run result', lambda cmd: (0, ok(cmd[2])[1].replace('Core run', ''))),
        ('a failed operation', lambda cmd: broken.run(cmd[2]))):
      with self.subTest(what):
        self.answer = answer
        with self.assertRaisesRegex(ht.StepFail, 'STM32_Programmer_CLI failed') as e:
          self.probe.run(['-halt', '-run'])
        self.assertFalse(e.exception.evidence['beforeTarget'])

  def test_every_operation_kind_needs_its_success_line(self):
    ok = self.cube.run
    ops = ['-halt', '-coreReg', '-r32 0x2009FFFC 1', '-w32 0x20000FFC 0x00000001', f'-u 0x08000000 0x10 {self.tmp / "u.bin"}',
           '#Delay(10)', '-rst', '-run']
    self.assertEqual(len(self.probe.run(ops)), len(ops))
    for line in ('Core halted', 'XPSR     = 0x', 'Reading 32-bit memory content', '32-bit data download complete',
                 'Data read successfully', 'The system go to sleep for', 'Software reset is performed', 'Core run'):
      with self.subTest(line):
        self.answer = lambda cmd, line=line: (0, ok(cmd[2])[1].replace(line, ''))
        with self.assertRaisesRegex(ht.StepFail, 'STM32_Programmer_CLI failed'):
          self.probe.run(ops)

  def test_only_an_unknown_probe_serial_is_recognised_as_before_the_target(self):
    self.answer = lambda cmd: (1, '=== Script Manager BEGIN ===\nOperation [1]: -c port=SWD sn=0023 mode=HOTPLUG \n'
                                  'Error: Serial number not found. Wrong parameter: sn=0023\n')
    with self.assertRaises(ht.StepFail) as e:
      self.probe.run(['-halt'])
    self.assertTrue(e.exception.evidence['beforeTarget'])

  def test_reads_must_give_exactly_one_value_and_writes_must_read_back(self):
    ok = self.cube.run
    self.answer = lambda cmd: (0, ok(cmd[2])[1].replace('0x2009FFFC : 00000000', 'x'))
    with self.assertRaisesRegex(ht.StepFail, 'no single value'):
      self.probe.mem32([0x2009FFFC])
    self.answer = lambda cmd: (0, ok(cmd[2])[1].replace('0x2009FFFC : 00000000', '0x2009FFFC : 00000000\n0x2009FFFC : 00000001'))
    with self.assertRaisesRegex(ht.StepFail, 'no single value'):
      self.probe.mem32([0x2009FFFC])
    self.answer = lambda cmd: (0, ok(cmd[2])[1].replace('0x20000FFC : 00000001', '0x20000FFC : 00000000'))
    with self.assertRaisesRegex(ht.StepFail, 'reads back 00000000'):
      self.probe.write32(0x20000FFC, 1)

  def test_the_flash_target_is_judged_from_its_transcript(self):
    self.assertEqual(ht.judge_stlink_target(0, stlink_target(), self.board),
                     {'flashDownload': 'File download complete', 'erasedSectors': ['0', '1']})
    for what, out, code in (('no start', stlink_target(start=''), 0), ('an error', stlink_target(error='Error: x\n'), 0),
                            ('another part', stlink_target(nvm='1 MBytes'), 0), ('a nonzero exit', stlink_target(), 1)):
      with self.subTest(what), self.assertRaisesRegex(ht.StepFail, 'the ST-LINK flash failed'):
        ht.judge_stlink_target(code, out, self.board)

  def test_any_programmer_cli_is_a_probe_user(self):
    proc = self.tmp / 'proc'
    for pid, argv in (('101', b'/home/u/bin/STM32_Programmer_CLI\0-script\0x.prg\0'), ('102', b'JLinkExe\0-USB\0000023\0'),
                      ('103', b'python3\0STM32_Programmer_CLI.txt\0')):
      (proc / pid).mkdir(parents=True)
      (proc / pid / 'cmdline').write_bytes(argv)
    real = ht.Path
    with mock.patch.object(ht, 'Path', lambda *a: real(proc) if a == ('/proc',) else real(*a)):
      self.assertEqual(ht.probe_users(self.board), [101])


class StlinkBatteryRun(Tmp):
  """StlinkBattery.run end to end over the fake CLI and a fake drive."""

  def setUp(self):
    super().setUp()
    cfg = self.tmp / 'local.json'
    cfg.write_text(json.dumps({'boards': [{'name': 'stm32h563_nucleo', 'uid': 'UID', 'flasher': {
      'name': 'stlink', 'uid': '0023', 'args': '-device stm32h563zi'}, 'tinyuf2': {'reentry': 'retained-register'}}]}))
    board = self.load(cfg, 'stm32h563_nucleo')
    self.bat = bat = ht.StlinkBattery(board, ht.source_facts(board), self.tmp)
    cube, f = FakeCube(), bat.f
    self.cube, self.present = cube, [True]
    bin_path = bootloader_bin(self.tmp / 'c.bin', board_id=b'STM32H563-Nucleo')
    cube.flash[f['binBase']] = bin_path.read_bytes()

    def reset():   # DFU only with the magic retained
      self.present[0] = cube.mem.pop(f['dblTapReg'], None) == f['dblTapMagic']
    cube.on_reset = reset
    build = self.tmp / 'build'
    build.mkdir()
    (build / 'tinyuf2.hex').write_text(':00000001FF\n')
    self.files = {'bin': bin_path, 'hex': build / 'tinyuf2.hex',
                  'flash': {'root': build, 'binding': {'target': 'tinyuf2-stlink'},
                            'sha256': {'tinyuf2.hex': ht.sha256(build / 'tinyuf2.hex')}}}

    def spawn(cmd, log, timeout, cwd=None, **k):
      if cmd[:2] == [ht.STM32_PROGRAMMER_CLI, '--connect']:   # the provider's flash
        cube.scripts.append(cmd[1:])
        return 0, stlink_target()
      if cmd[0] == 'mcopy':
        self.present[0] = False
        cube.flash[f['appStart']] = bat.fix['image']
        cube.pc, cube.vtor = bat.fix['handler'], f['appStart']
        return 0, ''
      return cube.run(cmd[2]) if cmd[0] == ht.STM32_PROGRAMMER_CLI else (0, '')

    def fat_read(dev, name, length, log, offset=0):
      if name == 'INFO_UF2.TXT':
        data = (f'TinyUF2 Bootloader v1\r\nModel: x\r\nBoard-ID: {f["boardId"]}\r\nDate: d\r\n'
                f'Flash Size: 0x{f["flashSize"]:08X} bytes').encode()
      else:
        data = ht.make_uf2(bat.fix['image'], f['appStart'], f['family'], self.tmp / 'cur')[1].read_bytes()[:length]
      return {'entries': {'CURRENT.UF2': [9, f['flashSize'] // 256 * 512]}, 'data': data, 'size': len(data)}
    (self.tmp / 'cur').mkdir()
    clock = [0.0]
    for p in (mock.patch.object(ht, 'usb_device', lambda *a: '1-2' if self.present[0] else None),
              mock.patch.object(ht, 'block_device', lambda p: '/dev/sdz'),
              mock.patch.object(ht, 'check_exclusive', lambda d: None),
              mock.patch.object(ht, 'fat_read', fat_read),
              mock.patch.object(ht, 'spawn', spawn),
              mock.patch.object(ht.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s)),
              mock.patch.object(ht.time, 'monotonic', lambda: clock[0] + 1e-3)):
      p.start()
      self.addCleanup(p.stop)

  def test_every_step_passes_with_each_probe_session_one_script(self):
    self.bat.run(self.files, 'v1')
    self.assertEqual([x['step'] for x in self.bat.steps if x['pass']], list(ht.STEPS['stlink']))
    s = self.cube.scripts
    self.assertEqual(s[0], ['--connect', 'port=swd', 'sn=0023', '--write', str(self.files['hex']), '--go'])   # no --verify
    self.assertEqual((s[1][0], s[1][2]), ('-halt', '-rst'))
    self.assertRegex(s[1][1], r'^-u 0x08000000 0x5824 \S+readback-\d+\.bin$')
    self.assertEqual(self.bat.steps[0]['evidence'],
                     {'flashDownload': 'File download complete', 'erasedSectors': ['0', '1'], 'verified': True,
                      'operation': {'attempts': [{'kind': 'exited', 'exit': 0}], 'cleanup': 'done'}})
    observe = next(x for x in s if '-coreReg' in x)
    self.assertEqual(observe[:5], ['-halt', '-run', f'#Delay({2 * self.bat.f["dblTapDelayMs"] + 200})', '-halt', '-coreReg'])
    self.assertEqual(observe.count('-coreReg'), 2)
    self.assertIn([f'-w32 0x{ht.SCB_AIRCR:08X} 0x{ht.AIRCR_SYSRESETREQ:08X} -nv'], s)
    ev = self.bat.steps[-1]['evidence']
    self.assertTrue(ev['dfuCameUp'] and ev['magicConsumed'] and ev['appIntact'])

  def test_an_install_whose_bin_does_not_read_back_fails(self):
    self.cube.flash[self.bat.f['binBase']] = b'\xff' * 0x5824
    with self.assertRaisesRegex(ht.StepFail, 'does not read back'):
      self.bat.run(self.files, 'v1')
    self.assertEqual(self.bat.steps[-1]['step'], 'install')

  def test_an_app_image_that_does_not_read_back_fails_app_ran(self):
    spawn = ht.spawn

    def corrupt(cmd, *a, **k):
      out = spawn(cmd, *a, **k)
      if cmd[0] == 'mcopy':
        self.cube.flash[self.bat.f['appStart']] = bytes(len(self.bat.fix['image']))
      return out
    with mock.patch.object(ht, 'spawn', corrupt), self.assertRaisesRegex(ht.StepFail, 'fixture image does not read back'):
      self.bat.run(self.files, 'v1')
    self.assertEqual(self.bat.steps[-1]['step'], 'app-ran')

  def test_a_reset_write_not_reported_done_fails(self):
    run = self.cube.run
    self.cube.run = lambda script: (lambda r: (r[0], r[1].replace('w @0xe000ed0c:  0x05fa0004', 'x')
                                               if '-nv' in Path(script).read_text() else r[1]))(run(script))
    with self.assertRaisesRegex(ht.StepFail, 'reset write was not reported done'):
      self.bat.sysreset()


H563_HEADER = 'lib/mcu/st/cmsis_device_h5/Include/stm32h563xx.h'


class StlinkSourceFacts(unittest.TestCase):
  def test_stm32h563_nucleo_facts_come_from_the_source_and_the_link_defsyms(self):
    with mock.patch.object(ht, 'vector_count', return_value=H563_FACTS['vectors']) as count:
      f = ht.source_facts(H563)
    count.assert_called_once_with(H563_HEADER)
    # __ram_size 640K: _board_dfu_dbl_tap = _estack, the last word of SRAM3
    self.assertEqual(f, H563_FACTS)

  @unittest.skipUnless((ROOT / H563_HEADER).is_file(), f'{H563_HEADER} not fetched (tools/get_deps.py stm32h5)')
  def test_stm32h563_vector_count_comes_from_its_cmsis_header(self):
    self.assertEqual(ht.vector_count(H563_HEADER), H563_FACTS['vectors'])

  def test_a_change_to_how_the_defsyms_reach_the_link_is_refused(self):
    files = {k: (ROOT / k).read_text() for k in ('ports/stm32h5/family.cmake', 'ports/stm32h5/linker/stm32h5_boot.ld',
                                                 'ports/stm32h5/boards/stm32h563_nucleo/board.cmake')}
    fam, ld, _ = files

    def defsyms(**edits):
      t = tempfile.TemporaryDirectory()
      self.addCleanup(t.cleanup)
      for rel, text in files.items():
        (Path(t.name) / rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(t.name) / rel).write_text(edits.get(rel, lambda x: x)(text))
      with mock.patch.object(ht, 'ROOT', Path(t.name)), mock.patch.object(ht.cb, 'ROOT', Path(t.name)):
        return ht.defsyms('stm32h5', 'ports/stm32h5/boards/stm32h563_nucleo', 'ports/stm32h5/linker/stm32h5_boot.ld')
    self.assertEqual(defsyms(), {'__flash_boot_size': 32 * 1024, '__ram_size': 640 * 1024})
    ram = '-Wl,--defsym=__ram_size=${LD_RAM_SIZE}'
    for what, rel, edit in (
        ('another defsym', fam, lambda x: x.replace(ram, '-Wl,--defsym=__ram_size=64K')),
        ('an extra defsym', fam, lambda x: x.replace(ram, ram + ' -Wl,--defsym=__x=1')),
        ('an unconditional set', fam, lambda x: x + '\nset(LD_RAM_SIZE 64K)\n'),
        ('no script default', ld, lambda x: x.replace('__ram_size = DEFINED(__ram_size) ? __ram_size : 32K;', '__ram_size = 32K;')),
        ('a second assignment', ld, lambda x: x + '\n__flash_boot_size += 1K;\n')):
      with self.subTest(what), self.assertRaisesRegex(ht.Refused, 'does not reach'):
        defsyms(**{rel: edit})

  def test_flash_size_from_the_cmsis_register_read_is_the_roster_device_flash(self):
    with self.assertRaisesRegex(ht.Refused, 'BOARD_FLASH_SIZE'):
      ht.source_facts(dict(H563, device='unknown'))


class StlinkRoster(Tmp):
  def test_an_stlink_entry_needs_a_device_with_limits_and_a_chip_identity(self):
    def entry(device):
      cfg = self.tmp / 'local.json'
      cfg.write_text(json.dumps({'boards': [{'name': 'stm32h563_nucleo', 'uid': 'U', 'flasher': {
        'name': 'stlink', 'uid': '0023', 'args': f'-device {device}'}}]}))
      return cfg
    b = self.load(entry('stm32h563zi'), 'stm32h563_nucleo')
    self.assertEqual((b['flasher'], b['install'], b['app']), ('stlink', (0x08000000, 0x08008000), (0x08008000, 0x08200000)))
    with mock.patch.dict(ht.FLASH_LIMITS, {'stm32h503rb': (0x08000000, 0x08020000)}):
      for device, err in (('stm32h503rb', 'no chip identity'), ('stm32h573ii', 'no programming limits')):
        with self.subTest(device), self.assertRaisesRegex(ht.Refused, err):
          ht.load_board(entry(device), 'stm32h563_nucleo')


if __name__ == '__main__':
  unittest.main()
