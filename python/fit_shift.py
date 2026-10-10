# -*- coding: utf-8 -*-
"""FIT 课程坐标纠偏：把 FIT 里的位置字段整体做 GCJ-02 <-> WGS-84 换算（逐点），结构不变，重算 CRC。

用法:
  python fit_shift.py <in.fit> <out.fit> g2w            # 把 GCJ-02 坐标改回真 WGS-84
  python fit_shift.py <in.fit> <out.fit> w2g            # 反向：WGS-84 -> GCJ-02
  python fit_shift.py <in.fit> <out.fit> g2w --rename "新课程名"
"""
import math
import struct
import sys

A = 6378245.0
EE = 0.00669342162296594323


def _out_of_china(lat, lon):
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _tlat(x, y):
    r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    r += (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
    r += (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    return r


def _tlon(x, y):
    r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    r += (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
    r += (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3
    return r


def wgs2gcj(lat, lon):
    if _out_of_china(lat, lon):
        return lat, lon
    dlat0, dlon0 = _tlat(lon - 105, lat - 35), _tlon(lon - 105, lat - 35)
    rad = lat / 180 * math.pi
    magic = 1 - EE * math.sin(rad) ** 2
    sq = math.sqrt(magic)
    dlat = (dlat0 * 180) / ((A * (1 - EE)) / (magic * sq) * math.pi)
    dlon = (dlon0 * 180) / (A / sq * math.cos(rad) * math.pi)
    return lat + dlat, lon + dlon


def gcj2wgs(lat, lon):
    if _out_of_china(lat, lon):
        return lat, lon
    wlat, wlon = lat, lon
    for _ in range(6):
        glat, glon = wgs2gcj(wlat, wlon)
        wlat += lat - glat
        wlon += lon - glon
    return wlat, wlon


# FIT CRC-16
CRC_TABLE = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)


def fit_crc(data, crc=0):
    for b in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ CRC_TABLE[b & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc ^= tmp ^ CRC_TABLE[(b >> 4) & 0xF]
    return crc & 0xFFFF


# (global_msg, field_num) -> 名称；依据 FIT profile 与本文件的 definition 实测
POS_FIELDS = {
    (20, 0): 'record.position_lat', (20, 1): 'record.position_long',
    (32, 2): 'course_point.position_lat', (32, 3): 'course_point.position_long',
    (19, 3): 'lap.start_position_lat', (19, 4): 'lap.start_position_long',
    (19, 5): 'lap.end_position_lat', (19, 6): 'lap.end_position_long',
    (18, 43): 'session.start_position_lat', (18, 44): 'session.start_position_long',
}


def semicircle_to_deg(v):
    return v * (180.0 / 2147483648.0)


def deg_to_semicircle(d):
    return int(round(d * (2147483648.0 / 180.0)))


def main():
    src, dst, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    newname = None
    if '--rename' in sys.argv:
        newname = sys.argv[sys.argv.index('--rename') + 1]
    if mode not in ('g2w', 'w2g'):
        raise SystemExit('mode must be g2w or w2g')
    conv = gcj2wgs if mode == 'g2w' else wgs2gcj

    data = bytearray(open(src, 'rb').read())
    hdr_size = data[0]
    data_size = struct.unpack('<I', data[4:8])[0]
    data_end = hdr_size + data_size
    if data[8:12] != b'.FIT':
        raise SystemExit('not a FIT file')
    print(f'{src}: header={hdr_size} dataSize={data_size} fileSize={len(data)} mode={mode}')

    defs = {}
    pos = hdr_size
    patched = 0
    renames = 0
    while pos < data_end:
        h = data[pos]
        pos += 1
        if h & 0x80:                       # compressed timestamp header
            continue
        lmt = h & 0x0F
        if h & 0x40:                       # definition
            pos += 1
            arch = data[pos]; pos += 1
            endian = '<' if arch == 0 else '>'
            gnum = struct.unpack(endian + 'H', data[pos:pos + 2])[0]; pos += 2
            nf = data[pos]; pos += 1
            fields = []
            for _ in range(nf):
                fields.append((data[pos], data[pos + 1], data[pos + 2]))
                pos += 3
            defs[lmt] = (gnum, fields, endian)
        else:
            gnum, fields, endian = defs[lmt]
            base = pos
            off = 0
            for fn, size, bt in fields:
                if (gnum, fn) in POS_FIELDS and size == 4:
                    raw = bytes(data[base + off:base + off + 4])
                    v = int.from_bytes(raw, 'little' if endian == '<' else 'big', signed=True)
                    lat, lon = semicircle_to_deg(v), None
                    # 位置字段成对出现：偶数字段=纬度，跟随字段=经度
                    nxt = None
                    for f2, s2, b2 in fields:
                        if f2 == fn + 1 and s2 == 4:
                            nxt = f2
                    if fn in (0, 3, 5, 43) and nxt == fn + 1:
                        j = fields.index((fn, size, bt))
                        off2 = sum(s for _, s, _ in fields[:j + 1])
                        raw2 = bytes(data[base + off2:base + off2 + 4])
                        v2 = int.from_bytes(raw2, 'little' if endian == '<' else 'big', signed=True)
                        lat = semicircle_to_deg(v)
                        lon = semicircle_to_deg(v2)
                        nlat, nlon = conv(lat, lon)
                        data[base + off:base + off + 4] = deg_to_semicircle(nlat).to_bytes(4, 'little' if endian == '<' else 'big', signed=True)
                        data[base + off2:base + off2 + 4] = deg_to_semicircle(nlon).to_bytes(4, 'little' if endian == '<' else 'big', signed=True)
                        patched += 1
                elif gnum == 31 and fn == 5 and newname and bt == 0x07:
                    enc = newname.encode('utf-8')
                    if len(enc) <= size:
                        data[base + off:base + off + size] = enc + b'\x00' * (size - len(enc))
                        renames += 1
                off += size
            pos = base + off

    print(f'patched position pairs: {patched}   renamed course messages: {renames}')
    crc = fit_crc(bytes(data[:data_end]))
    data[data_end:data_end + 2] = crc.to_bytes(2, 'little')
    open(dst, 'wb').write(bytes(data))
    print(f'wrote {dst} ({len(data)} bytes, crc=0x{crc:04X})')


main()
