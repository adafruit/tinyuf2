#!/usr/bin/env python3
"""Code size of TinyUF2's bootloader per board: agentrc's code-size engine, from the agentrc the bootstrap selects
(hil-contract's scripts/agentrc.py), run with code_size_profile.py, whose PROFILE_API the engine checks.
`--help` for the commands; the engine's module docstring defines them and the profile.

  code_size.py report -b feather_stm32f405_express
  code_size.py diff -b feather_stm32f405_express [--base-branch REF] [--engine bloaty --symbols]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / 'hil-contract' / 'scripts'))
import agentrc  # noqa: E402
import code_size_profile  # noqa: E402

ENGINE = 'skills/code-size/scripts/code_size.py'


def main(argv=None):
  try:
    engine = agentrc.load_file(ENGINE)
  except ImportError as e:
    print(f'code_size.py: refused: {e}', file=sys.stderr)
    return 2
  return engine.main(code_size_profile, argv)


if __name__ == '__main__':
  sys.exit(main())
