"""对比 Python CLI 与 Dart CLI 的输出是否逐行一致。"""
import os
import subprocess
import sys

WS = r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter"
PY = os.path.join(WS, 'python')
DART = os.path.join(WS, 'flutter', 'packages', 'vobsplit_core')
SAMPLE = os.path.join(os.environ['TEMP'], 's2.vob')
OUT_PY = os.path.join(os.environ['TEMP'], 'c_py')
OUT_DART = os.path.join(os.environ['TEMP'], 'c_dart')


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return p.stdout


def dart_cmd():
    """Windows 上 PATH 里的 dart 常是 .bat，CreateProcess 不能直接跑。"""
    import shutil
    found = shutil.which('dart')
    if found and os.name == 'nt' and found.lower().endswith(('.bat', '.cmd')):
        return ['cmd', '/c', found]
    if found:
        return [found]
    exe = os.path.join(os.path.expanduser('~'), 'Flutter', 'flutter', 'bin',
                       'cache', 'dart-sdk', 'bin', 'dart.exe')
    return [exe]


py_out = run([sys.executable, '-m', 'vobsplit', 'split', SAMPLE, '-o', OUT_PY], PY)
dart_out = run(dart_cmd() + ['run', 'bin/vobsplit.dart', 'split', SAMPLE,
                             '-o', OUT_DART], DART)

a = py_out.replace(OUT_PY, 'OUT').splitlines()
b = dart_out.replace(OUT_DART, 'OUT').splitlines()

if a == b:
    print('两套 CLI 输出逐行一致 OK（%d 行）' % len(a))
else:
    import difflib
    diff = list(difflib.unified_diff(a, b, 'python', 'dart', lineterm=''))
    out = os.path.join(WS, 'cli_output_diff.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(diff))
    print('有差异，共 %d 行 diff，已写入 %s' % (len(diff), out))
