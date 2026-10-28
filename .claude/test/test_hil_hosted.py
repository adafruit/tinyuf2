#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# A record built off the rig (a hosted runner, or the dev PC of a remote run) and admitted on the rig (hil_hosted.py):
# the pack, and admission's refusal of a board, roster, record, compiler or file that differs. check_build is stubbed;
# the build is a synthetic IDF or cmake tree.
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts'))
import hil_hosted as hh  # noqa: E402

ht, cb = hh.ht, hh.cb
REAL_RELEASE = cb.ci_arm_gcc_release   # setUp stubs it
BOARD, OTHER = 'espressif_esp32s3_devkitm_1', 'espressif_esp32s3_devkitc_1'
BRIDGE = '3ea619acd1cdeb11a0a0b806e93fd3f1'
NOW = {'head': 'h' * 40, 'submodules': {'lib/tinyusb': 't' * 40}, 'deps': {}, 'dirty': False}
IDF = {'mode': 'docker', 'ciVersion': 'v6.1', 'image': 'espressif/idf:v6.1'}
ARM_GCC = 'arm-none-eabi-gcc (Arm GNU Toolchain 13.3.Rel1 (Build arm-13.24)) 13.3.1 20240614'   # 13.3.Rel1's, measured
# roster flashers of cmake boards: a J-Link board and an ST-LINK one (test/hil/ci.json)
CMAKE_BOARDS = {
  'imxrt1064_evk': {'name': 'jlink', 'uid': '000725299165', 'args': '-device MIMXRT1064xxx6A'},
  'stm32h743nucleo': {'name': 'stlink', 'uid': '004C00343137510F39383538', 'args': '-device stm32h743zi'},
}


def entry(name, uid=BRIDGE, **tinyuf2):
  return {'name': name, 'uid': '84F703C084E4', 'flasher': {'name': 'esptool', 'uid': uid, 'args': '--chip esp32s3'},
          'tinyuf2': tinyuf2}


class Hosted(unittest.TestCase):
  def setUp(self):
    t = tempfile.TemporaryDirectory()
    self.addCleanup(t.cleanup)
    self.tmp = Path(t.name)
    self.roster = self.tmp / 'ci.json'
    self.write_roster()
    self.now, self.idf = json.loads(json.dumps(NOW)), 'v6.1'
    (self.tmp / 'ports').symlink_to(ROOT / 'ports')   # the checkout admission places build dirs in is this one
    mock.patch.object(cb, 'ROOT', self.tmp).start()
    mock.patch.object(cb, 'BUILD_DIR', self.tmp / 'cmake-build').start()
    mock.patch.object(cb, 'identity', lambda ports: self.now).start()
    mock.patch.object(cb, 'ci_idf_version', lambda: self.idf).start()
    mock.patch.object(cb, 'ci_arm_gcc_release', lambda: self.release).start()
    self.release = '13.3.Rel1'
    self.addCleanup(mock.patch.stopall)
    self.hosted = self.tmp / 'hosted'
    self.out = self.tmp / 'out'

  def write_roster(self, uid=BRIDGE):
    cmake = [{'name': b, 'uid': 'U', 'flasher': fl} for b, fl in CMAKE_BOARDS.items()]
    self.roster.write_text(json.dumps({'boards': [entry(BOARD, uid, lock='espressif_s3_devkitm'), entry(OTHER, 'x'),
                                                  *cmake]}))

  def idf_tree(self, board=BOARD):
    """A --shared IDF build dir of `board` and its passing record."""
    root = cb.BUILD_DIR / f'cmake-build-{board}'
    files = {rel: rel.encode() * 3 for rel in cb.FLASH['esptool'][1]}
    files.update({'_bin/apps/dfu_runtime.uf2': b'app', '_bin/apps/blinky.uf2': b'blinky', 'sdkconfig': b'CONFIG=1\n'})
    for rel, data in files.items():
      (root / rel).parent.mkdir(parents=True, exist_ok=True)
      (root / rel).write_bytes(data)
    row = {'board': board, 'port': 'espressif', 'backend': 'idf', 'buildDir': f'cmake-build/cmake-build-{board}',
           'status': 'ok', 'firstError': '', 'artifacts': sorted(files), 'sha256': {r: hh.sha256(d) for r, d in files.items()},
           'flash': {'target': 'flash', 'flasher': {'name': 'esptool', 'uid': BRIDGE, 'device': 'esp32s3'},
                     'command': 'cd /home/runner/work/x && cmake ...', 'inputs': list(cb.FLASH['esptool'][1]), 'defines': []}}
    return {'pass': True, 'input': dict(NOW, missingInputs=[], depsOffPin=[], dirtyInputs=[], inputsDirtiedByBuild=[]),
            'boards': [row], 'idf': dict(IDF), 'built': []}

  def cmake_tree(self, board, compiler=ARM_GCC):
    """A --shared cmake build dir of `board` (CMAKE_BOARDS) and its passing record."""
    fl = CMAKE_BOARDS[board]
    root = cb.BUILD_DIR / f'cmake-build-{board}'
    target, inputs = cb.FLASH[fl['name']]
    files = {rel: rel.encode() * 3 for rel in (*inputs, *cb.FACTS_FILES, '_bin/tinyuf2.bin', '_bin/tinyuf2.hex',
                                               '_bin/apps/blinky.uf2')}
    for rel, data in files.items():
      (root / rel).parent.mkdir(parents=True, exist_ok=True)
      (root / rel).write_bytes(data)
    (root / 'CMakeCache.txt').write_text('not hashed, not packed\n')
    row = {'board': board, 'port': cb.port_of(board), 'backend': 'cmake', 'buildDir': f'cmake-build/cmake-build-{board}',
           'status': 'ok', 'firstError': '', 'artifacts': sorted(files), 'sha256': {r: hh.sha256(d) for r, d in files.items()},
           'flash': {'target': target, 'flasher': {'name': fl['name'], 'uid': fl['uid'], 'device': fl['args'].split()[-1]},
                     'command': 'cd /home/runner/work/x && JLinkExe ...', 'inputs': list(inputs), 'defines': []},
           'compiler': {'path': '/opt/arm/bin/arm-none-eabi-gcc', 'version': compiler}}
    return {'pass': True, 'input': dict(NOW, missingInputs=[], depsOffPin=[], dirtyInputs=[], inputsDirtiedByBuild=[]),
            'boards': [row], 'built': []}

  def build(self, board=BOARD, rec=None):
    rec = rec or (self.idf_tree(board) if board in (BOARD, OTHER) else self.cmake_tree(board))
    with mock.patch.object(hh.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='log\n' + json.dumps(rec),
                                                                          stderr='')) as run:
      result = hh.build(board, str(self.roster), self.hosted)
    self.assertEqual(run.call_args.args[0][2:], ['--board', board, '--shared', '--hil-config', str(self.roster)])
    return Path(result['artifact'])

  def admit(self, artifact=None, board=BOARD):
    return hh.admit(artifact or self.hosted / BOARD, board, str(self.roster), self.out)

  def refused(self, pattern, artifact=None, board=BOARD):
    with self.assertRaisesRegex(ht.Refused, pattern):
      self.admit(artifact, board)

  def forge(self, artifact, record=None, files=None, name=BOARD):
    """The artifact changed by `record` (a function of the record) and `files` ({rel: bytes or None})."""
    name = hh.record_name(name)
    if record:
      rec = json.loads((artifact / name).read_text())
      record(rec)
      (artifact / name).write_text(json.dumps(rec))
    for rel, data in (files or {}).items():
      if data is None:
        (artifact / rel).unlink()
      else:
        (artifact / rel).parent.mkdir(parents=True, exist_ok=True)
        (artifact / rel).write_bytes(data)

  def test_a_matching_artifact_is_placed_as_the_records_build_dir_and_admitted(self):
    artifact = self.build()
    prov = json.loads((artifact / hh.PROVENANCE).read_text())
    self.assertEqual(prov, {'version': 2, 'board': BOARD,
                            'roster': {'path': str(self.roster), 'sha256': hh.sha256(self.roster.read_bytes())}})
    rec = json.loads((artifact / f'{BOARD}.build.json').read_text())
    self.assertEqual(set(hh.inventory(artifact)),
                     {f'{BOARD}.build.json', *(f'build/{r}' for r in rec['boards'][0]['sha256'])})
    root = cb.BUILD_DIR / f'cmake-build-{BOARD}'
    built = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    hh.shutil.rmtree(root)   # the rig has never built it
    record = self.admit()
    self.assertEqual(record, self.out / f'{BOARD}.build.json')
    self.assertEqual(json.loads(record.read_text()), rec)
    self.assertEqual({p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}, built)
    self.assertEqual((self.out / f'{BOARD}.provenance.json').read_text(), (artifact / hh.PROVENANCE).read_text())

  def test_an_admission_replaces_whatever_the_build_dir_held(self):
    self.build()
    stale = cb.BUILD_DIR / f'cmake-build-{BOARD}' / 'stale.bin'
    stale.write_bytes(b'x')
    self.admit()
    self.assertFalse(stale.exists())

  def test_a_record_the_runner_refuses_or_one_not_matching_the_artifact_refuses(self):
    def row(**over):
      return lambda rec: rec['boards'][0].update(over)
    cases = {
      'commit (record_row)': (lambda: self.now.update(head='0' * 40), None, 'head'),
      'another build dir': (None, row(buildDir='cmake-build/cmake-build-x'), 'build dir'),
      'a recorded hash': (None, lambda rec: rec['boards'][0]['sha256'].update({'sdkconfig': '0' * 64}), 'exactly'),
      'a file the record does not hash': (None, lambda rec: rec['boards'][0]['sha256'].pop('sdkconfig'), 'exactly'),
      'another flasher': (None, lambda rec: rec['boards'][0]['flash']['flasher'].update(uid='other'), 'not bound'),
    }
    for what, (here, record, err) in cases.items():
      with self.subTest(what):
        hh.shutil.rmtree(self.hosted, ignore_errors=True)
        self.now, self.idf = json.loads(json.dumps(NOW)), 'v6.1'
        artifact = self.build()
        if record:
          self.forge(artifact, record)
        if here:
          here()
        self.refused(err)
        self.assertFalse((cb.BUILD_DIR / 'cmake-build-x').exists(), 'only the expected build dir is ever placed')

  def test_a_refused_admission_leaves_the_admitted_record_and_build_dir_as_they_were(self):
    artifact = self.build()
    self.admit()
    root = cb.BUILD_DIR / f'cmake-build-{BOARD}'
    kept = {p: p.read_bytes() for p in [*self.out.iterdir(), *root.rglob('*')] if p.is_file()}
    self.forge(artifact, lambda rec: rec['boards'][0]['flash']['flasher'].update(uid='other'))
    self.refused('not bound')
    self.assertEqual({p: p.read_bytes() for p in [*self.out.iterdir(), *root.rglob('*')] if p.is_file()}, kept)

  def test_a_malformed_record_or_provenance_refuses_that_board_in_the_ci_batch_and_the_cli(self):
    import hil_ci
    name = hh.record_name(BOARD)
    artifact = self.build()
    good = {p: (artifact / p).read_bytes() for p in (name, hh.PROVENANCE)}
    self.admit()
    root = cb.BUILD_DIR / f'cmake-build-{BOARD}'
    kept = {p: p.read_bytes() for p in [*self.out.iterdir(), *root.rglob('*')] if p.is_file()}
    rec = json.loads(good[name])
    cases = {
      'a record that is an array': (name, b'[]\n'),
      'boards not a list': (name, b'{"boards": 5}'),
      'a board row not an object': (name, b'{"boards": [1]}'),
      'idf not an object': (name, json.dumps(dict(rec, idf='docker')).encode()),
      'a row without its build dir': (name, json.dumps(dict(rec, boards=[{k: v for k, v in rec['boards'][0].items()
                                                                          if k != 'buildDir'}])).encode()),
      'a record nested too deep': (name, b'[' * 100000),
      'a provenance nested too deep': (hh.PROVENANCE, b'[' * 100000),
    }
    for what, (rel, data) in cases.items():
      with self.subTest(what):
        for p, d in good.items():
          (artifact / p).write_bytes(d)
        (artifact / rel).write_bytes(data)
        record, ok, why = hil_ci.hosted_record(BOARD, str(self.roster), self.out, self.hosted)
        self.assertEqual((record, ok), (self.out / name, False))
        self.assertRegex(why, '^hosted build refused: .*(its checks stopped on|no readable provenance.json)')
        with mock.patch.object(sys, 'stdout', new_callable=io.StringIO) as out:
          self.assertEqual(hh.main(['admit', '--artifact', str(artifact), '--board', BOARD, '--roster',
                                    str(self.roster), '--out', str(self.out)]), 2)
        self.assertFalse(json.loads(out.getvalue().splitlines()[-1])['pass'])
        self.assertEqual({p: p.read_bytes() for p in [*self.out.iterdir(), *root.rglob('*')] if p.is_file()}, kept)

  def test_a_roster_or_board_other_than_the_artifacts_refuses(self):
    artifact = self.build()
    self.write_roster(uid='replugged')   # the roster changed after the build
    self.refused('roster')
    self.write_roster()
    self.refused('built for espressif_esp32s3_devkitm_1, not espressif_esp32s3_devkitc_1', board=OTHER)
    prov = json.loads((artifact / hh.PROVENANCE).read_text())
    prov['roster']['path'] = 'test/hil/local.json'
    (artifact / hh.PROVENANCE).write_text(json.dumps(prov))
    self.refused('roster')

  def test_a_missing_extra_or_changed_file_refuses(self):
    rel = 'build/tinyuf2.bin'
    for what, files in (('missing', {rel: None}), ('extra', {'extra.bin': b'x'}), ('changed', {rel: b'other'})):
      with self.subTest(what):
        hh.shutil.rmtree(self.hosted, ignore_errors=True)
        artifact = self.build()
        for r, data in files.items():
          (artifact / r).unlink() if data is None else (artifact / r).write_bytes(data)
        self.refused('not exactly the ones its record hashes')

  def test_a_file_the_record_does_not_hash_or_one_outside_its_build_dir_refuses(self):
    artifact = self.build()
    self.forge(artifact, files={'build/extra.bin': b'x'})
    self.refused('not exactly the ones its record hashes')
    hh.shutil.rmtree(self.hosted)
    artifact = self.build()
    self.forge(artifact, lambda rec: rec['boards'][0]['sha256'].update({'../escape': hh.sha256(b'x')}), {'escape': b'x'})
    self.refused('not exactly the ones its record hashes')
    self.assertFalse((cb.BUILD_DIR / 'escape').exists())

  def test_an_artifact_without_its_provenance_or_with_a_link_refuses(self):
    self.refused('no readable provenance.json')   # never downloaded
    artifact = self.build()
    (artifact / 'link').symlink_to(artifact / 'build' / 'tinyuf2.bin')
    self.refused('link is not a regular file')
    (artifact / 'link').unlink()
    prov = json.loads((artifact / hh.PROVENANCE).read_text())
    (artifact / hh.PROVENANCE).write_text(json.dumps(dict(prov, version=1, files={})))   # the earlier format
    self.refused('not a version 2 provenance')

  def test_a_cmake_board_is_built_with_cmake_and_admitted_as_its_records_build_dir(self):
    for board in CMAKE_BOARDS:
      with self.subTest(board):
        artifact = self.build(board)
        rec = json.loads((artifact / f'{board}.build.json').read_text())
        row = rec['boards'][0]
        self.assertEqual(row['buildDir'], f'cmake-build/cmake-build-{board}')
        # every file the battery reads from the build dir travels: the install's, the board facts', blinky's
        self.assertLessEqual({*cb.FLASH[row['flash']['flasher']['name']][1], *cb.FACTS_FILES, *ht.CMAKE_RECORD_FILES,
                              '_bin/tinyuf2.hex'}, set(row['sha256']))
        self.assertEqual(set(hh.inventory(artifact)), {f'{board}.build.json', *(f'build/{r}' for r in row['sha256'])})
        root = cb.BUILD_DIR / f'cmake-build-{board}'
        built = {r: (root / r).read_bytes() for r in row['sha256']}
        hh.shutil.rmtree(root)   # the rig has never built it
        record = self.admit(self.hosted / board, board)
        self.assertEqual(json.loads(record.read_text()), rec)
        self.assertEqual({p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}, built)

  def test_a_cmake_record_not_compiled_by_cis_arm_gcc_refuses(self):
    board = 'imxrt1064_evk'
    others = {'another release': 'arm-none-eabi-gcc (Arm GNU Toolchain 14.2.Rel1 (Build arm-14.52)) 14.2.1 20241119',
              'a later point release': 'arm-none-eabi-gcc (Arm GNU Toolchain 13.3.Rel10 (Build arm-13.99)) 13.3.1',
              'another vendor': 'arm-none-eabi-gcc (xPack GNU Arm Embedded GCC x86_64) 13.3.1 20240614',
              'no version': None}
    for what, version in others.items():
      with self.subTest(what):
        hh.shutil.rmtree(self.hosted, ignore_errors=True)
        with self.assertRaisesRegex(ht.Refused, 'compiled by .*a hosted record takes CI\'s Arm GNU Toolchain 13.3.Rel1 only'):
          self.build(board, self.cmake_tree(board, version))
        self.assertFalse((self.hosted / board).exists(), 'nothing packed')
        artifact = self.build(board)
        self.forge(artifact, lambda rec: rec['boards'][0]['compiler'].update(version=version), name=board)
        with self.assertRaisesRegex(ht.Refused, 'compiled by'):
          self.admit(self.hosted / board, board)
    hh.shutil.rmtree(self.hosted)
    artifact = self.build(board)
    self.forge(artifact, lambda rec: rec['boards'][0].pop('compiler'), name=board)
    with self.assertRaisesRegex(ht.Refused, 'an unrecorded compiler'):
      self.admit(self.hosted / board, board)
    # the pin is setup_toolchain's release, matched whatever its case (13.2 prints rel1, 13.3 and 14.2 Rel1)
    self.release = '14.2.Rel1'
    self.forge(artifact, lambda rec: rec['boards'][0].update(compiler={'version': others['another release'].lower()}),
               name=board)
    self.admit(self.hosted / board, board)

  def test_the_pin_is_the_release_the_hosted_build_installs(self):
    """hil.yml's hosted build sets up arm-gcc through setup_toolchain, whose release admission reads."""
    self.assertRegex(REAL_RELEASE(), r'^\d+\.\d+\.Rel\d+$')
    job = (ROOT / '.github' / 'workflows' / 'hil.yml').read_text().split('\n  hosted-build:\n')[1].split('\n  ci-lan:\n')[0]
    self.assertRegex(job, r"uses: \./\.github/actions/setup_toolchain\n\s+with:\n\s+toolchain: arm-gcc\n")

  def test_an_espressif_record_needs_no_compiler(self):
    artifact = self.build()
    self.assertNotIn('compiler', json.loads((artifact / f'{BOARD}.build.json').read_text())['boards'][0])
    self.admit()

  def test_a_failed_hosted_build_packs_nothing(self):
    rec = dict(self.idf_tree(), **{'pass': False, 'firstError': 'boom'})
    with mock.patch.object(hh.subprocess, 'run', return_value=mock.Mock(returncode=1, stdout=json.dumps(rec), stderr='')), \
         self.assertRaisesRegex(ht.Refused, 'check_build failed .*boom'):
      hh.build(BOARD, str(self.roster), self.hosted)
    self.assertFalse(self.hosted.exists())

  def test_a_failed_hosted_build_echoes_its_log_tail_to_stderr(self):
    log = self.tmp / 'cmake-build' / f'cmake-build-agent-1-{BOARD}' / 'check_build.log'
    log.parent.mkdir(parents=True)
    log.write_text(''.join(f'line {i}\n' for i in range(hh.LOG_TAIL + 5)) + 'error: boom\n')
    rec = self.idf_tree()
    rec.update({'pass': False, 'firstError': 'boom'})
    rec['boards'][0].update(status='failed', log=os.path.relpath(log, cb.ROOT))   # checkout-relative, as check_build's
    with mock.patch.object(sys, 'stderr', new_callable=io.StringIO) as err, \
         mock.patch.object(hh.subprocess, 'run', return_value=mock.Mock(returncode=1, stdout=json.dumps(rec), stderr='')), \
         self.assertRaisesRegex(ht.Refused, 'check_build failed .*boom'):
      hh.build(BOARD, str(self.roster), self.hosted)
    tail = err.getvalue().splitlines()
    self.assertEqual(tail[-1], 'error: boom')
    self.assertIn(f'line {hh.LOG_TAIL + 4}', tail)
    self.assertNotIn('line 0', tail)

  def test_the_cli_prints_json_and_exits_2_on_a_refusal(self):
    with mock.patch.object(sys, 'stdout') as out:
      self.assertEqual(hh.main(['admit', '--artifact', str(self.hosted / BOARD), '--board', BOARD, '--roster',
                                str(self.roster), '--out', str(self.out)]), 2)
    self.assertFalse(json.loads(out.write.call_args_list[0].args[0])['pass'])


if __name__ == '__main__':
  unittest.main()
