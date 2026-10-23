#!/usr/bin/env python3
"""Code size of TinyUF2's bootloader per board: agentrc's code-size engine, from lib/agentrc at the
pin HEAD records, run with code_size_profile.py. `--help` for the commands; the engine's module
docstring defines them and the profile.

  code_size.py report -b feather_stm32f405_express
  code_size.py diff -b feather_stm32f405_express [--base-branch REF] [--engine bloaty --symbols]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / 'hil-contract' / 'scripts'))
import check_build  # noqa: E402
import code_size_profile  # noqa: E402
import hil_run_report  # noqa: E402

ENGINE = 'skills/code-size/scripts/code_size.py'


def load_engine():
  """agentrc's engine at the pin, after check_build's pin check: ImportError naming the remedy."""
  try:
    check_build.check_agentrc_pin()
  except check_build.Fail as e:
    raise ImportError(str(e)) from None
  return hil_run_report.load_agentrc(hil_run_report.AGENTRC / ENGINE, 'agentrc_code_size')


def main(argv=None):
  try:
    engine = load_engine()
  except ImportError as e:
    print(f'code_size.py: refused: {e}', file=sys.stderr)
    return 2
  return engine.main(code_size_profile, argv)


if __name__ == '__main__':
  sys.exit(main())
