#!/usr/bin/env python3
"""One esptool connection for hil_test.py, run as its own child so the runner can time it out, kill it and
see it survive: connect into download mode, run the ops in order, then reset or not.

  esp_session.py --port DEV --chip CHIP --baud N --after hard-reset|no-reset OPS.json

OPS.json is a list of {"op": "read", "addr", "size", "file"} and {"op": "md5", "addr", "size"}: no write, which
is the provider's flash. A {"op": "security"} first reads the chip's flash encryption and secure boot state on the
ROM loader, before the stub runs.
The last stdout line is JSON: {"ok": true, "results": [...]} or {"ok": false, "error", "results"}.
"""
import argparse
import json
import sys

sys.dont_write_bytecode = True


def security(esp):
  """The chip's flash encryption and secure boot state from two sources, both on the ROM loader: esptool 5.2.0's
  GET_SECURITY_INFO (loader.py get_security_info: flags bit 0 SECURE_BOOT_EN, flash_crypt_cnt enabled when its count
  of 1 bits is odd) and its eFuse register reads (targets/*.py get_flash_encryption_enabled, get_secure_boot_enabled;
  on the P4 EFUSE_RD_REPEAT_DATA1_REG [20:18] SPI_BOOT_CRYPT_CNT and EFUSE_RD_REPEAT_DATA2_REG [20] SECURE_BOOT_EN)."""
  if esp.IS_STUB:
    raise RuntimeError('the chip already runs the flasher stub; its security state is read from the ROM loader')
  si = esp.get_security_info(cache=False)

  def state(on):
    return 'on' if on else 'off'
  return {'flags': si['flags'], 'flashCryptCnt': si['flash_crypt_cnt'],
          'rom': {'flashEncryption': state(bin(si['flash_crypt_cnt']).count('1') % 2),
                  'secureBoot': state(si['parsed_flags']['SECURE_BOOT_EN'])},
          'efuse': {'flashEncryption': state(esp.get_flash_encryption_enabled()),
                    'secureBoot': state(esp.get_secure_boot_enabled())}}


def run(esp, op):
  kind = op['op']
  if kind == 'read':
    data = esp.read_flash(op['addr'], op['size'])
    with open(op['file'], 'wb') as f:
      f.write(data)
    return {'size': len(data)}
  if kind == 'md5':
    return {'md5': esp.flash_md5sum(op['addr'], op['size'])}
  raise ValueError(f'unknown op {kind!r}')


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('--port', required=True)
  ap.add_argument('--chip', required=True)
  ap.add_argument('--baud', type=int, required=True)
  ap.add_argument('--after', choices=('hard-reset', 'no-reset'), required=True)
  ap.add_argument('ops')
  args = ap.parse_args()
  results, esp = [], None
  try:
    import esptool
    from esptool import cmds
    ops = json.load(open(args.ops))
    if any(op['op'] == 'security' for op in ops[1:]):
      raise ValueError('a security op comes first, before the stub runs')
    esp = cmds.detect_chip(args.port, connect_mode='default-reset')
    if esp.CHIP_NAME.lower().replace('-', '') != args.chip:
      raise RuntimeError(f'the port reaches a {esp.CHIP_NAME}, not an {args.chip}')
    if ops and ops[0]['op'] == 'security':
      results.append(dict(security(esp), op='security'))
      ops = ops[1:]
    esp = cmds.run_stub(esp)
    esp.change_baud(args.baud)
    cmds.attach_flash(esp)
    for op in ops:
      results.append(dict(run(esp, op), op=op['op']))
    if args.after == 'hard-reset':
      cmds.reset_chip(esp, 'hard-reset')
    out = {'ok': True, 'esptool': esptool.__version__, 'results': results}
  except Exception as e:   # every failure is reported, never raised past the JSON line
    out = {'ok': False, 'error': f'{type(e).__name__}: {e}', 'results': results}
  finally:
    if esp is not None:
      esp._port.close()
  print(json.dumps(out), flush=True)
  return 0 if out['ok'] else 1


if __name__ == '__main__':
  sys.exit(main())
