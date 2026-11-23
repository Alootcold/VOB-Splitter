#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python 版与 Dart 版的交叉校验。

用同一个 VOB 分别跑两套实现，逐项比对输出 —— 两套实现必须行为一致。
这是「同一个算法的两个移植」最容易跑偏的地方，所以做成可重复执行的工具。

    python tools/cross_check.py                 # 用合成夹具
    python tools/cross_check.py path/to.vob     # 用真实 VOB

需要本机装了 Dart（dart run）。
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_DIR = os.path.join(ROOT, 'python')
DART_DIR = os.path.join(ROOT, 'flutter', 'packages', 'vobsplit_core')


def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    return proc.returncode, proc.stdout, proc.stderr


def make_fixture(path):
    sys.path.insert(0, os.path.join(PY_DIR, 'tests'))
    import synth
    synth.write_vob(path, [6.0, 4.0, 8.0])
    return path


def dart_cmd():
    """找到可用的 dart 执行命令。

    Windows 上 PATH 里的 dart 往往是个 .bat 包装脚本，CreateProcess 不能直接执行，
    需要包一层 cmd /c。
    """
    import shutil
    found = shutil.which('dart')
    if found:
        if os.name == 'nt' and found.lower().endswith(('.bat', '.cmd')):
            return ['cmd', '/c', found]
        return [found]
    # Flutter SDK 自带的 dart.exe
    for sdk in (os.environ.get('FLUTTER_ROOT'),):
        if sdk:
            exe = os.path.join(sdk, 'bin', 'cache', 'dart-sdk', 'bin', 'dart.exe')
            if os.path.isfile(exe):
                return [exe]
    home = os.path.expanduser('~')
    exe = os.path.join(home, 'Flutter', 'flutter', 'bin', 'cache',
                       'dart-sdk', 'bin', 'dart.exe')
    if os.path.isfile(exe):
        return [exe]
    return ['dart']


def scan_json(cmd, cwd):
    code, out, err = run(cmd, cwd)
    if code != 0:
        raise RuntimeError('%s 失败: %s' % (' '.join(cmd), err[:400]))
    start = out.index('{')
    return json.loads(out[start:])


def compare(a, b, path=''):
    """递归比较两个 JSON，返回差异描述列表。"""
    diffs = []
    if type(a) is not type(b):
        return ['%s: 类型不同 %s != %s' % (path, type(a).__name__, type(b).__name__)]
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                diffs.append('%s.%s: Python 缺失' % (path, key))
            elif key not in b:
                diffs.append('%s.%s: Dart 缺失' % (path, key))
            else:
                diffs += compare(a[key], b[key], '%s.%s' % (path, key))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append('%s: 长度不同 %d != %d' % (path, len(a), len(b)))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diffs += compare(x, y, '%s[%d]' % (path, i))
    elif isinstance(a, float) or isinstance(b, float):
        if abs(float(a) - float(b)) > 1e-6:
            diffs.append('%s: %r != %r' % (path, a, b))
    elif a != b:
        diffs.append('%s: %r != %r' % (path, a, b))
    return diffs


def main():
    tmp = tempfile.mkdtemp(prefix='vobsplit-xcheck-')
    target = sys.argv[1] if len(sys.argv) > 1 else make_fixture(
        os.path.join(tmp, 'VTS_01_1.VOB'))
    print('样本: %s (%d 字节)' % (target, os.path.getsize(target)))

    py = scan_json([sys.executable, '-m', 'vobsplit', 'scan', target, '--json'], PY_DIR)
    dart = scan_json(dart_cmd() + ['run', 'bin/vobsplit.dart', 'scan', target, '--json'],
                     DART_DIR)

    diffs = compare(py, dart)
    if diffs:
        print('\n发现 %d 处差异：' % len(diffs))
        for d in diffs[:40]:
            print('  ' + d)
        sys.exit(1)

    print('\nscan 结果完全一致：')
    print('  章节数 %d，pack %d，随机访问点 %d'
          % (len(py['chapters']), py['stats']['packs'], py['stats']['raps']))
    print('  每章的 offset / bytes / rap_count / PTS 全部相同')

    # 再比一次切分产物
    out_py = os.path.join(tmp, 'py')
    out_dart = os.path.join(tmp, 'dart')
    for out_dir, cmd, cwd in (
            (out_py, [sys.executable, '-m', 'vobsplit', 'split', target, '-o', out_py], PY_DIR),
            (out_dart, dart_cmd() + ['run', 'bin/vobsplit.dart', 'split', target,
                                     '-o', out_dart], DART_DIR)):
        code, out, err = run(cmd, cwd)
        if code != 0:
            print('切分失败: %s' % err[:400])
            sys.exit(1)

    def hashes(d):
        res = {}
        for name in sorted(os.listdir(d)):
            if name.endswith('.vob'):
                import hashlib
                h = hashlib.sha256()
                with open(os.path.join(d, name), 'rb') as fh:
                    while True:
                        b = fh.read(1 << 22)
                        if not b:
                            break
                        h.update(b)
                res[name] = h.hexdigest()
        return res

    hp, hd = hashes(out_py), hashes(out_dart)
    if hp != hd:
        print('\n切分产物哈希不一致:')
        for k in sorted(set(hp) | set(hd)):
            if hp.get(k) != hd.get(k):
                print('  %s: %s != %s' % (k, hp.get(k), hd.get(k)))
        sys.exit(1)
    print('  切分产物哈希全部一致（%d 个文件）' % len(hp))

    # manifest 对比
    def manifest(d):
        with open(os.path.join(d, 'vobsplit-manifest.json'), encoding='utf-8') as fh:
            return json.load(fh)

    diffs = compare(manifest(out_py), manifest(out_dart), 'manifest')
    if diffs:
        print('\nmanifest 差异：')
        for d in diffs[:40]:
            print('  ' + d)
        sys.exit(1)
    print('  manifest 全字段一致')
    print('\n交叉校验全部通过：Python 版与 Dart 版行为一致')


if __name__ == '__main__':
    main()
