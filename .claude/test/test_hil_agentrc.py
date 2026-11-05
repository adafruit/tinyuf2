#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The agentrc bootstrap (.claude/skills/hil-contract/scripts/agentrc.py) in a scratch checkout, each case its own
process (the identity is taken once per process): which agentrc it selects (a staged copy, CI's pin, the installed
one), the API check before any agentrc code runs, the closure and drift checks at load, and CI's fetch. The scratch
agentrc is a git copy of the selected agentrc's closure; every GIT_* variable is dropped, as a hook's would aim git at
the checkout under test."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / '.claude' / 'skills' / 'hil-contract' / 'scripts' / 'agentrc.py'
sys.path.insert(0, str(BOOTSTRAP.parent))
import agentrc  # noqa: E402

GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=m']
SOURCE = 'skills/hil/scripts/agentrc_source.py'
CI_VARS = ('CI', 'GITHUB_ACTIONS', 'AGENTRC_DIR')


def git(*args):
  return subprocess.run([*GIT, *args], capture_output=True, text=True, check=True,
                        env={k: v for k, v in os.environ.items() if not k.startswith('GIT_')}).stdout.strip()


class Bootstrap(unittest.TestCase):
  def setUp(self):
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.tmp = Path(tmp.name)
    self.root = self.tmp / 'checkout'   # a consumer checkout holding only the bootstrap and its pin file
    (self.root / BOOTSTRAP.relative_to(ROOT)).parent.mkdir(parents=True)
    shutil.copyfile(BOOTSTRAP, self.root / BOOTSTRAP.relative_to(ROOT))
    self.install = self.tmp / 'agentrc'   # an agentrc checkout holding the closure this checkout loads
    real = agentrc.identity()
    for rel in real['files']:
      (self.install / rel).parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(Path(real['root']) / rel, self.install / rel)
    git('init', '-q', str(self.install))
    git('-C', str(self.install), 'config', 'uploadpack.allowAnySHA1InWant', 'true')
    self.commit = self.commit_install('closure')
    self.pin_to(self.commit)
    self.home = self.tmp / 'home'
    self.home.mkdir()

  def commit_install(self, msg):
    git('-C', str(self.install), 'add', '-A')
    git('-C', str(self.install), 'commit', '-q', '-m', msg)
    return git('-C', str(self.install), 'rev-parse', 'HEAD')

  def pin_to(self, commit, url=None):
    pin = self.root / 'test' / 'hil' / 'agentrc.json'
    pin.parent.mkdir(parents=True, exist_ok=True)
    pin.write_text(json.dumps({'url': url or str(self.install), 'commit': commit}))

  def run_boot(self, code, **env):
    """`code` run after `import agentrc` from the scratch checkout, with `env` over a clean CI-free environment."""
    base = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k not in CI_VARS}
    base.update(HOME=str(self.home), **env)
    script = f'import json, sys; sys.path.insert(0, {str(self.root / BOOTSTRAP.relative_to(ROOT).parent)!r})\n' \
             f'import agentrc\n{code}'
    return subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, env=base,
                          cwd=self.tmp)

  def identity(self, **env):
    """(source, commit, error): the selected agentrc's identity, or the ImportError taking it raised."""
    r = self.run_boot('try:\n  i = agentrc.identity()\n  print(json.dumps([i["source"], i["commit"], ""]))\n'
                      'except ImportError as e:\n  print(json.dumps([None, None, str(e)]))', **env)
    self.assertEqual(r.returncode, 0, r.stderr)
    return tuple(json.loads(r.stdout.splitlines()[-1]))

  def stage(self):
    """The scratch agentrc staged into the checkout as a staging driver writes it (agentrc_source.stage)."""
    helper = agentrc.helper()
    helper.stage(helper.identity('installed', self.install, agentrc.SCRIPTS), self.root)
    return self.root / agentrc.STAGED

  def fetch(self, **env):
    return self.run_boot('try:\n  print(agentrc.fetch())\nexcept ImportError as e:\n  print("error:", e)', **env)

  def test_the_installed_agentrc_is_agentrc_dir_else_home_claude(self):
    self.assertEqual(self.identity(AGENTRC_DIR=str(self.install)), ('installed', self.commit, ''))
    source, _, err = self.identity()
    self.assertEqual(source, None)
    self.assertIn(f'no usable agentrc at {self.home / ".claude"}', err)
    self.assertIn('install agentrc', err)
    (self.home / '.claude').symlink_to(self.install)
    self.assertEqual(self.identity(), ('installed', self.commit, ''))

  def test_ci_takes_the_pin_fetched_into_lib_agentrc_never_the_installed_one(self):
    for var in ('CI', 'GITHUB_ACTIONS'):
      with self.subTest(var):
        source, _, err = self.identity(AGENTRC_DIR=str(self.install), **{var: 'true'})
        self.assertIsNone(source)
        self.assertIn(f'no usable agentrc at {self.root / "lib/agentrc"}', err)
        self.assertIn(agentrc.FETCH, err)
    r = self.fetch(CI='true')
    self.assertEqual(r.stdout.strip(), str(self.root / 'lib/agentrc'), r.stderr)
    self.assertEqual(self.identity(CI='true', AGENTRC_DIR=str(self.install)), ('pin', self.commit, ''))
    self.assertEqual(self.fetch(CI='true').stdout.strip(), str(self.root / 'lib/agentrc'), 'a second fetch is a no-op')
    # off its pin or changed: refused, never fetched over
    (self.root / 'lib/agentrc' / SOURCE).write_text((self.root / 'lib/agentrc' / SOURCE).read_text() + '\n')
    self.assertIn('has local changes', self.identity(CI='true')[2])
    self.assertIn('is not a clean checkout', self.fetch(CI='true').stdout)
    git('-C', str(self.root / 'lib/agentrc'), 'checkout', '-q', '--', SOURCE)
    (self.install / 'NEWER').write_text('x')
    newer = self.commit_install('newer')
    self.pin_to(newer)
    self.assertIn(f'not the pin {newer}', self.identity(CI='true')[2])

  def test_a_malformed_ci_value_or_pin_is_refused(self):
    for value in ('maybe', '2'):
      with self.subTest(value):
        self.assertIn(f"CI={value!r} is neither true nor false", self.identity(CI=value, AGENTRC_DIR=str(self.install))[2])
    for value in ('', '0', 'false', 'no'):
      with self.subTest(value):
        self.assertEqual(self.identity(CI=value, GITHUB_ACTIONS=value, AGENTRC_DIR=str(self.install))[0], 'installed')
    for pin in ('[]', '{"url": "u"}', '{"url": "u", "commit": "abc"}', '{"url": " u", "commit": "%s"}' % ('a' * 40),
                'not json'):
      with self.subTest(pin):
        (self.root / 'test/hil/agentrc.json').write_text(pin)
        self.assertIn('agentrc.json', self.identity(CI='true')[2])

  def test_fetch_runs_in_ci_only(self):
    r = self.fetch(AGENTRC_DIR=str(self.install))
    self.assertIn('error: fetch runs in CI only', r.stdout)
    self.assertFalse((self.root / 'lib/agentrc').exists())
    r = subprocess.run([sys.executable, str(self.root / BOOTSTRAP.relative_to(ROOT)), 'fetch'], capture_output=True,
                       text=True, env={k: v for k, v in os.environ.items() if k not in CI_VARS})
    self.assertEqual((r.returncode, r.stderr.startswith('error: fetch runs in CI only')), (1, True), r.stderr)

  def test_a_staged_copy_wins_over_a_checkout_an_install_and_ci_and_a_corrupt_one_never_falls_back(self):
    git('init', '-q', str(self.root))   # the rig's rebuilt checkout is a git checkout of its own
    staged = self.stage()
    self.assertTrue((self.root / '.git').is_dir())
    everything = {'AGENTRC_DIR': str(self.install), 'CI': 'true', 'GITHUB_ACTIONS': 'true'}
    self.fetch(CI='true')   # CI's pin present too
    self.assertEqual(self.identity(**everything), ('staged', self.commit, ''))
    first = sorted(json.loads((staged / 'manifest.json').read_text())['sha256'])[0]
    for what, corrupt, err in (
        ('a changed file', lambda: (staged / first).write_bytes(b'changed'), 'differ from their manifest'),
        ('a missing file', lambda: (staged / first).unlink(), 'is missing or not a regular file'),
        ('no manifest', lambda: (staged / 'manifest.json').unlink(), 'is not readable JSON'),
        ('an empty dir', lambda: [shutil.rmtree(staged), staged.mkdir()], 'no usable agentrc'),
        ('a file', lambda: [shutil.rmtree(staged), staged.write_text('x')], 'no usable agentrc')):
      with self.subTest(what):
        shutil.rmtree(staged, ignore_errors=True)
        staged.unlink(missing_ok=True)
        self.stage()
        corrupt()
        source, _, why = self.identity(**everything)
        self.assertIsNone(source)
        self.assertIn(err, why)
        self.assertIn('stage the run again', why)

  def test_an_agentrc_of_another_api_is_refused_before_any_of_its_code_runs(self):
    ran = self.tmp / 'ran'
    text = (self.install / SOURCE).read_text()
    self.assertIn('\nAPI = 1 ', text)
    (self.install / SOURCE).write_text(f'open({str(ran)!r}, "w").close()\n' + text.replace('\nAPI = 1 ', '\nAPI = 2 '))
    self.commit_install('api 2')
    source, _, err = self.identity(AGENTRC_DIR=str(self.install))
    self.assertIsNone(source)
    self.assertIn('speaks agentrc_source API 2, this checkout needs 1', err)
    self.assertFalse(ran.exists(), 'agentrc code ran before its API was checked')
    r = self.run_boot('print(sorted(m for m in sys.modules if m.startswith("agentrc_")))', AGENTRC_DIR=str(self.install))
    self.assertEqual(r.stdout.strip(), '[]', 'importing the bootstrap loads no agentrc module')

  def test_only_the_closure_loads_and_a_file_changed_since_the_identity_is_refused(self):
    code = '\n'.join((
      'ident = agentrc.identity()',
      'try:\n  agentrc.load("skills/hil/scripts/hil_tt.py", "x")\nexcept ImportError as e:\n  print("outside:", e)',
      'print("path:", agentrc.path_of("skills/hil/scripts/usb_dfu.py"))',
      'core = agentrc.load_file("skills/hil/scripts/hil_report_core.py")',
      'print("same:", agentrc.load("skills/hil/scripts/hil_report_core.py", "tinyuf2_core") is core)',
      'p = agentrc.Path(ident["root"]) / "skills/hil/scripts/hil_lock.py"',
      'p.write_text(p.read_text() + "\\n")',
      'try:\n  agentrc.load_file("skills/hil/scripts/hil_lock.py")\nexcept ImportError as e:\n  print("drift:", e)',
      'print("drifted:", agentrc.helper().drift(ident))'))
    r = self.run_boot(code, AGENTRC_DIR=str(self.install))
    out = dict(line.split(': ', 1) for line in r.stdout.splitlines())
    self.assertIn('skills/hil/scripts/hil_tt.py is not in the agentrc closure this process took',
                  out.get('outside', r.stderr))
    self.assertEqual((out['path'], out['same']), (str(self.install / 'skills/hil/scripts/usb_dfu.py'), 'True'))
    self.assertIn('agentrc skills/hil/scripts/hil_lock.py changed since this process loaded it (install agentrc',
                  out['drift'])
    self.assertEqual(out['drifted'], "['skills/hil/scripts/hil_lock.py']")

  def test_a_dependency_changed_since_the_identity_is_refused(self):
    # hil_flash loads hil_process by path itself, past the bootstrap: the whole closure is checked first
    code = '\n'.join((
      'ident = agentrc.identity()',
      'p = agentrc.Path(ident["root"]) / "skills/hil/scripts/hil_process.py"',
      'p.write_text(p.read_text() + "raise RuntimeError(\'DRIFT RAN\')\\n")',
      'try:\n  agentrc.load_file("skills/hil/scripts/hil_flash.py")\nexcept ImportError as e:\n  print("drift:", e)'))
    r = self.run_boot(code, AGENTRC_DIR=str(self.install))
    self.assertIn('agentrc skills/hil/scripts/hil_process.py changed since this process loaded it', r.stdout,
                  r.stderr)
    self.assertNotIn('DRIFT RAN', r.stdout + r.stderr)

  def test_a_script_loads_its_own_files_from_the_checkout_never_through_a_retargeted_install_link(self):
    # an install links skill dirs into a checkout: hil_openocd_esp loads target-debug's esp_session by path itself,
    # which must come from the checkout the identity took, not from wherever the link points now
    inst = self.tmp / 'install'
    (inst / 'skills').mkdir(parents=True)
    for skill in (self.install / 'skills').iterdir():
      (inst / 'skills' / skill.name).symlink_to(skill)
    other = self.tmp / 'other' / 'skills' / 'target-debug'
    shutil.copytree(self.install / 'skills' / 'target-debug', other)
    (other / 'scripts' / 'esp_session.py').write_text('raise RuntimeError("OTHER CHECKOUT RAN")\n')
    link = inst / 'skills' / 'target-debug'
    code = '\n'.join((
      'agentrc.identity()',
      f'import os; os.unlink({str(link)!r}); os.symlink({str(other)!r}, {str(link)!r})',
      'mod = agentrc.load_file("skills/hil/scripts/hil_openocd_esp.py")',
      'print("dep:", mod.esp_session.__file__)'))
    r = self.run_boot(code, AGENTRC_DIR=str(inst))
    self.assertNotIn('OTHER CHECKOUT RAN', r.stdout + r.stderr)
    self.assertEqual(r.returncode, 0, r.stderr)
    dep = r.stdout.split('dep: ', 1)[1].strip()
    self.assertEqual(Path(dep).resolve(), (self.install / 'skills/target-debug/scripts/esp_session.py').resolve())

  def test_a_failed_identity_is_never_kept_and_a_taken_one_is(self):
    code = '\n'.join((
      'import os',
      'try:\n  agentrc.identity()\nexcept ImportError as e:\n  print("first:", e)',
      f'os.environ["AGENTRC_DIR"] = {str(self.install)!r}',
      'ident = agentrc.identity()',
      'os.environ["AGENTRC_DIR"] = "/nonexistent"',
      'print("kept:", agentrc.identity() is ident, agentrc.helper().__name__)'))
    r = self.run_boot(code, AGENTRC_DIR=str(self.tmp / 'none'))
    out = dict(line.split(': ', 1) for line in r.stdout.splitlines())
    self.assertIn('no usable agentrc at', out.get('first', r.stderr))
    self.assertEqual(out.get('kept'), 'True agentrc_agentrc_source', r.stderr)
    (self.install / 'skills/hil/scripts/hil_load.py').unlink()   # an install without hil_load: refused, not an OSError
    source, _, err = self.identity(AGENTRC_DIR=str(self.install))
    self.assertIsNone(source)
    self.assertIn(f'no usable agentrc at {self.install}', err)
    self.assertIn('install agentrc', err)

  def test_scripts_cover_every_agentrc_file_tinyuf2_loads_or_runs(self):
    import hil_test as ht
    import hil_ci
    import hil_remote
    used = {ht.LOCK_HELPER, ht.FLASH_PROVIDER, ht.OPENOCD_ESP, ht.BOARD_REGISTRY, ht.USB_OBSERVE, ht.REPORT_CORE,
            ht.ESP_SESSION, ht.USB_DFU, hil_ci.REPORT_CORE, hil_ci.REPORT_NOTICE, hil_remote.REMOTE_CORE,
            'skills/code-size/scripts/code_size.py'}
    self.assertEqual(used, set(agentrc.SCRIPTS))
    self.assertLessEqual(used, set(agentrc.identity()['files']))

  def test_the_cli_prints_the_identity_and_refuses_anything_else(self):
    script = str(self.root / BOOTSTRAP.relative_to(ROOT))
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k not in CI_VARS}
    r = subprocess.run([sys.executable, script, 'check'], capture_output=True, text=True,
                       env=dict(env, AGENTRC_DIR=str(self.install)))
    self.assertEqual((r.returncode, json.loads(r.stdout)['commit']), (0, self.commit), r.stderr)
    r = subprocess.run([sys.executable, script], capture_output=True, text=True, env=env)
    self.assertEqual(r.returncode, 2)


if __name__ == '__main__':
  unittest.main()
