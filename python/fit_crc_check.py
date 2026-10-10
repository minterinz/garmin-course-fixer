# -*- coding: utf-8 -*-
"""fit_crc_check.py —— 校验 FIT 文件尾部 CRC 是否与重算值一致（验证 fit_shift.py 的写回是否正确）。
用法: python fit_crc_check.py <file.fit> [more.fit ...]
"""
import struct
import sys

T = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
     0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)


def crc16(data, crc=0):
    for b in data:
        tmp = T[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ T[b & 0xF]
        tmp = T[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ T[(b >> 4) & 0xF]
    return crc & 0xFFFF


for p in sys.argv[1:]:
    d = open(p, 'rb').read()
    hdr = d[0]
    dsize = struct.unpack('<I', d[4:8])[0]
    end = hdr + dsize
    stored = int.from_bytes(d[end:end + 2], 'little') if len(d) >= end + 2 else None
    calc = crc16(d[:end])
    ok = 'OK ' if stored == calc else 'MISMATCH'
    print(f'{ok} {p}  hdr={hdr} dataEnd={end} fileSize={len(d)} stored=0x{stored:04X} calc=0x{calc:04X}')
