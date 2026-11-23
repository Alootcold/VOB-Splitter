#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接解析 PE 资源表，把 exe 里嵌入的图标抠出来。

用途：验证安装程序（setup.exe）确实带上了我们想要的图标。
比走 shell 的图标 API 更可靠——它是把资源原样读出来，不受系统缩放、
主题、缓存影响。

    python tools/peek_exe_icon.py <exe> [out.png]
"""
import io
import struct
import sys

from PIL import Image, ImageDraw

RT_ICON = 3
RT_GROUP_ICON = 14


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


class Pe:
    def __init__(self, data):
        self.d = data
        e_lfanew = u32(data, 0x3C)
        assert data[e_lfanew:e_lfanew + 4] == b'PE\0\0', '不是 PE 文件'
        coff = e_lfanew + 4
        nsec = u16(data, coff + 2)
        opt_size = u16(data, coff + 16)
        opt = coff + 20
        magic = u16(data, opt)
        self.pe32plus = (magic == 0x20B)
        dd = opt + (112 if self.pe32plus else 96)
        self.rsrc_rva = u32(data, dd + 2 * 8)
        self.rsrc_size = u32(data, dd + 2 * 8 + 4)

        self.sections = []
        sec = opt + opt_size
        for i in range(nsec):
            o = sec + i * 40
            va = u32(data, o + 12)
            vsize = u32(data, o + 8)
            rawsize = u32(data, o + 16)
            rawptr = u32(data, o + 20)
            self.sections.append((va, max(vsize, rawsize), rawptr))

    def rva_to_off(self, rva):
        for va, size, rawptr in self.sections:
            if va <= rva < va + size:
                return rawptr + (rva - va)
        raise ValueError('RVA 0x%X 不在任何节里' % rva)

    def res_dir(self, base, off):
        """返回该资源目录下的条目列表 [(name_id, is_dir, data_off)]。"""
        n_named = u16(self.d, base + off + 12)
        n_id = u16(self.d, base + off + 14)
        out = []
        eo = base + off + 16
        for i in range(n_named + n_id):
            name = u32(self.d, eo)
            data = u32(self.d, eo + 4)
            out.append((name, bool(data & 0x80000000), data & 0x7FFFFFFF))
            eo += 8
        return out

    def res_data(self, base, off):
        """返回该资源的字节内容。"""
        rva = u32(self.d, base + off)
        size = u32(self.d, base + off + 4)
        o = self.rva_to_off(rva)
        return self.d[o:o + size]


def dib_to_image(raw):
    """RT_ICON 里可能是 DIB，也可能是 PNG（Vista+ 的 256px 常压成 PNG）。"""
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return Image.open(io.BytesIO(raw)).convert('RGBA')
    assert u32(raw, 0) == 40, '未知的 RT_ICON 格式'
    width = u32(raw, 4)
    height = u32(raw, 8) // 2      # XOR + AND 两块
    bpp = u16(raw, 14)
    assert bpp == 32, '只支持 32bpp，收到 %d' % bpp
    xor_off = 40                  # BITMAPINFOHEADER 之后紧跟像素
    stride = width * 4
    px = bytearray()
    for y in range(height - 1, -1, -1):   # 存的是自下而上
        row = raw[xor_off + y * stride: xor_off + (y + 1) * stride]
        for x in range(width):
            b, g, r, a = row[x * 4:x * 4 + 4]
            px += bytes((r, g, b, a))
    return Image.frombytes('RGBA', (width, height), bytes(px))


def extract(exe):
    data = open(exe, 'rb').read()
    pe = Pe(data)
    base = pe.rva_to_off(pe.rsrc_rva)

    # 根目录 -> 类型 -> 名称 -> 语言
    icons = {}     # id -> 原始数据
    groups = []    # [(资源id, [条目])]
    for type_id, is_dir, t_off in pe.res_dir(base, 0):
        if not is_dir:
            continue
        if type_id == RT_ICON:
            for res_id, is_sub, s_off in pe.res_dir(base, t_off):
                if is_sub:
                    for lang_id, _, l_off in pe.res_dir(base, s_off):
                        icons[res_id] = pe.res_data(base, l_off)
                        break
        elif type_id == RT_GROUP_ICON:
            for res_id, is_sub, s_off in pe.res_dir(base, t_off):
                if is_sub:
                    for lang_id, _, l_off in pe.res_dir(base, s_off):
                        groups.append(pe.res_data(base, l_off))
                        break
    return groups, icons


def group_entries(blob):
    """解析 GRPICONDIR，返回 [(w, h, bitcount, bytes, res_id)]。"""
    count = u16(blob, 4)
    out = []
    for i in range(count):
        o = 6 + i * 14
        w = blob[o] or 256
        h = blob[o + 1] or 256
        bpp = u16(blob, o + 6)
        size = u32(blob, o + 8)
        rid = u16(blob, o + 12)
        out.append((w, h, bpp, size, rid))
    return out


def main():
    exe = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'exe-icon.png'
    groups, icons = extract(exe)
    print('%s: %d 个图标组, %d 个图标资源' % (exe, len(groups), len(icons)))

    imgs = []
    for gi, blob in enumerate(groups):
        entries = group_entries(blob)
        print('  组 %d:' % gi)
        for w, h, bpp, size, rid in entries:
            have = rid in icons
            print('    %4dx%-4d %2dbpp  %7d bytes  res#%-4d %s'
                  % (w, h, bpp, size, rid, 'ok' if have else '缺失'))
            if have:
                imgs.append((w, dib_to_image(icons[rid])))

    if not imgs:
        raise SystemExit('没找到图标资源')

    # 预览：浅底 + 深底各一排
    imgs.sort(key=lambda t: t[0])
    pad = 18
    width = sum(im.size[0] for _, im in imgs) + pad * (len(imgs) + 1)
    tallest = max(im.size[1] for _, im in imgs)
    sheet = Image.new('RGB', (width, tallest * 2 + pad * 3), (243, 243, 243))
    d = ImageDraw.Draw(sheet)
    x = pad
    for _, im in imgs:
        sheet.paste(im, (x, pad), im)
        d.text((x, pad + tallest + 4), str(im.size[0]), fill=(60, 60, 70))
        x += im.size[0] + pad
    d.rectangle([0, pad * 2 + tallest, width, pad * 3 + tallest * 2], fill=(20, 20, 24))
    x = pad
    for _, im in imgs:
        sheet.paste(im, (x, pad * 2 + tallest), im)
        d.text((x, pad * 2 + tallest + tallest + 4), str(im.size[0]), fill=(200, 200, 210))
        x += im.size[0] + pad
    sheet.save(out)
    print('写入 %s（%d 个尺寸）' % (out, len(imgs)))


if __name__ == '__main__':
    main()
