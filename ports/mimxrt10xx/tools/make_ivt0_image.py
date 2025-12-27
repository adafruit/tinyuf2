#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path

# IVT header encoding (mirrors NXP ROM definitions).
IVT_MAJOR_VERSION = 0x4
IVT_MAJOR_VERSION_SHIFT = 0x4
IVT_MAJOR_VERSION_MASK = 0xF
IVT_MINOR_VERSION = 0x1
IVT_MINOR_VERSION_SHIFT = 0x0
IVT_MINOR_VERSION_MASK = 0xF

IVT_TAG_HEADER = 0xD1  # Image Vector Table
IVT_SIZE = 0x2000


def ivt_version(major: int, minor: int) -> int:
    return ((major & IVT_MAJOR_VERSION_MASK) << IVT_MAJOR_VERSION_SHIFT) | (
            (minor & IVT_MINOR_VERSION_MASK) << IVT_MINOR_VERSION_SHIFT
    )


def ivt_header(major: int, minor: int) -> int:
    return IVT_TAG_HEADER | (IVT_SIZE << 8) | (ivt_version(major, minor) << 24)


# Valid IVT headers used by NXP ROM (4.0 and 4.1).
IVT_HEADERS = {
    ivt_header(IVT_MAJOR_VERSION, 0x0),  # 0x402000D1
    ivt_header(IVT_MAJOR_VERSION, IVT_MINOR_VERSION),  # 0x412000D1
}


def find_ivt_offset(data: bytes) -> int:
    for off in range(0, len(data) - 32, 4):
        if struct.unpack_from("<I", data, off)[0] in IVT_HEADERS:
            return off
    return -1


def main() -> int:
    ap = argparse.ArgumentParser(description="Make IVT-at-offset-0 image for ROM load-image.")
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()

    data = args.input.read_bytes()
    strip = 0x1000 - 0x400
    if len(data) <= strip:
        raise SystemExit(f"input too small: {args.input}")

    data = bytearray(data[strip:])
    ivt_off = find_ivt_offset(data)
    if ivt_off < 0:
        raise SystemExit("IVT header not found")

    if ivt_off:
        data = data[ivt_off:]

    if len(data) < 32:
        raise SystemExit("truncated IVT")

    hdr, entry, rsvd1, dcd, boot_data, self_addr, csf, rsvd2 = struct.unpack_from("<8I", data, 0)

    base = self_addr  # IVT is at offset 0, so file base == IVT self address
    boot_off = boot_data - base
    if boot_off < 0 or boot_off + 16 > len(data):
        raise SystemExit("boot_data pointer out of range")

    struct.pack_into("<I", data, boot_off + 0, base)
    struct.pack_into("<I", data, boot_off + 4, len(data))

    args.output.write_bytes(data)
    print("Wrote IVT image to", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
