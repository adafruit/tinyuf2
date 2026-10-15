#!/usr/bin/env python3
"""USB control requests to a DFU runtime interface for hil_test.py, run as its own child so the runner can
time it out, kill it and see it survive.

  usb_dfu.py --vid V --pid P --serial S --path BUS-PORT[.PORT...] string|detach

The device must be the only one with that VID, PID, serial and sysfs path, with exactly one DFU runtime
interface (class 0xFE, subclass 1, protocol 1). `string` reads that interface's string from the device
itself, not from a cache; `detach` sends DFU_DETACH (USB DFU 1.1 section 5.1) to it.
The last stdout line is JSON: {"ok": true, ...} or {"ok": false, "error"}.
"""
import argparse
import json
import sys

sys.dont_write_bytecode = True

DFU_CLASS = (0xFE, 0x01, 0x01)
DFU_DETACH = 0x00
DETACH_TIMEOUT_MS = 1000   # wDetachTimeOut; a bitWillDetach device leaves the bus by itself
CONTROL_TIMEOUT_MS = 1000


def find(vid, pid, serial, path):
  import usb.core
  hits = []
  for dev in usb.core.find(find_all=True, idVendor=vid, idProduct=pid):
    where = f'{dev.bus}-{".".join(map(str, dev.port_numbers or ()))}'
    if where == path and dev.serial_number == serial:
      hits.append(dev)
  if len(hits) != 1:
    raise RuntimeError(f'{len(hits)} devices {vid:04x}:{pid:04x} serial {serial} at {path}')
  dev = hits[0]
  itfs = [i for i in dev.get_active_configuration()
          if (i.bInterfaceClass, i.bInterfaceSubClass, i.bInterfaceProtocol) == DFU_CLASS]
  if len(itfs) != 1:
    raise RuntimeError(f'{len(itfs)} DFU runtime interfaces')
  return dev, itfs[0]


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('--vid', type=lambda s: int(s, 0), required=True)
  ap.add_argument('--pid', type=lambda s: int(s, 0), required=True)
  ap.add_argument('--serial', required=True)
  ap.add_argument('--path', required=True)
  ap.add_argument('op', choices=('string', 'detach'))
  args = ap.parse_args()
  try:
    import usb.util
    dev, itf = find(args.vid, args.pid, args.serial, args.path)
    if args.op == 'string':
      out = {'ok': True, 'interface': itf.bInterfaceNumber,
             'string': usb.util.get_string(dev, itf.iInterface) if itf.iInterface else None}
    else:
      dev.ctrl_transfer(0x21, DFU_DETACH, DETACH_TIMEOUT_MS, itf.bInterfaceNumber, None, CONTROL_TIMEOUT_MS)
      out = {'ok': True, 'interface': itf.bInterfaceNumber}
  except Exception as e:   # every failure is reported, never raised past the JSON line
    out = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
  print(json.dumps(out), flush=True)
  return 0 if out['ok'] else 1


if __name__ == '__main__':
  sys.exit(main())
