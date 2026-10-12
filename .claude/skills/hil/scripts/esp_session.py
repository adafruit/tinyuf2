#!/usr/bin/env python3
"""One esptool connection for hil_test.py, run as its own child so the runner can time it out, kill it and
see it survive: connect into download mode, run the ops in order, then reset or not.

  esp_session.py --port DEV --chip CHIP --baud N --after hard-reset|no-reset OPS.json
  esp_session.py --port DEV --boot-log SECONDS

OPS.json is a list of {"op": "mac" | "security" | "flash-size"}, {"op": "expect-mac", "mac"} (stops the
session before any later op unless the chip has that MAC), {"op": "write", "addr", "file"},
{"op": "read", "addr", "size", "file"}, {"op": "md5", "addr", "size"}, {"op": "erase", "addr", "size"}.
--boot-log makes no esptool connection: an EN reset through the bridge's RTS with IO0 left high, then the UART
output for SECONDS (DevKitC-1 schematic: with DTR and RTS released EN and IO0 stay high; RTS alone pulls EN low).
The last stdout line is JSON: {"ok": true, "results": [...]} or {"ok": false, "error", "results"}.
"""
import argparse
import json
import sys

sys.dont_write_bytecode = True


def run(esp, op):
  from esptool import cmds
  kind = op['op']
  if kind in ('mac', 'expect-mac'):
    mac = ''.join(f'{b:02X}' for b in esp.read_mac('BASE_MAC'))
    if kind == 'expect-mac' and mac != op['mac']:
      raise RuntimeError(f'the port reaches MAC {mac}, not {op["mac"]}; nothing written')
    return {'mac': mac}
  if kind == 'security':
    info = esp.get_security_info()
    return {'flags': info['flags'], 'parsed': info['parsed_flags'], 'flashCryptCnt': info['flash_crypt_cnt'],
            'chipId': info['chip_id'], 'apiVersion': info['api_version']}
  if kind == 'flash-size':
    return {'flashSize': cmds.detect_flash_size(esp)}
  if kind == 'write':
    # 'keep' leaves every image header byte as built, so a read-back compares the file itself
    with open(op['file'], 'rb') as f:
      cmds.write_flash(esp, [(op['addr'], f)], flash_freq='keep', flash_mode='keep', flash_size='keep')
    return {}
  if kind == 'read':
    data = esp.read_flash(op['addr'], op['size'])
    with open(op['file'], 'wb') as f:
      f.write(data)
    return {'size': len(data)}
  if kind == 'md5':
    return {'md5': esp.flash_md5sum(op['addr'], op['size'])}
  if kind == 'erase':
    cmds.erase_region(esp, op['addr'], op['size'])
    return {}
  raise ValueError(f'unknown op {kind!r}')


def boot_log(port, seconds):
  import time
  import serial   # pyserial, esptool's own dependency
  s = serial.Serial()
  s.port, s.baudrate, s.timeout = port, 115200, 0.1
  s.dtr = s.rts = False   # set before open: opening must not move EN or IO0
  s.open()
  try:
    s.reset_input_buffer()
    s.rts = True
    time.sleep(0.1)
    s.rts = False
    out, end = b'', time.monotonic() + seconds
    while time.monotonic() < end:
      out += s.read(4096)
  finally:
    s.close()
  return out.decode('ascii', 'replace')


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('--port', required=True)
  ap.add_argument('--boot-log', type=float)
  ap.add_argument('--chip')
  ap.add_argument('--baud', type=int)
  ap.add_argument('--after', choices=('hard-reset', 'no-reset'))
  ap.add_argument('ops', nargs='?')
  args = ap.parse_args()
  if args.boot_log is not None:
    try:
      out = {'ok': True, 'results': [{'op': 'boot-log', 'text': boot_log(args.port, args.boot_log)}]}
    except Exception as e:
      out = {'ok': False, 'error': f'{type(e).__name__}: {e}', 'results': []}
    print(json.dumps(out), flush=True)
    return 0 if out['ok'] else 1
  if not (args.chip and args.baud and args.after and args.ops):
    ap.error('a session needs --chip, --baud, --after and OPS.json')
  results, esp = [], None
  try:
    import esptool
    from esptool import cmds
    ops = json.load(open(args.ops))
    esp = cmds.detect_chip(args.port, connect_mode='default-reset')
    if esp.CHIP_NAME.lower().replace('-', '') != args.chip:
      raise RuntimeError(f'the port reaches a {esp.CHIP_NAME}, not an {args.chip}')
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
