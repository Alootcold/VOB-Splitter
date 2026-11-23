"""验证事件循环回归测试确实能抓住「同步读盘」这个 bug。

做法：临时把 chunks() 改回同步读，跑那条测试，看它是否失败；跑完无论成败都还原。
（用 try/finally 保证一定还原，避免上次那样把文件留在临时状态。）
"""
import os
import shutil
import subprocess

CORE = r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter\flutter\packages\vobsplit_core"
p = os.path.join(CORE, 'lib', 'src', 'ps.dart')
bak = p + ".verifybak"
shutil.copy2(p, bak)

dart = os.path.join(os.path.expanduser('~'), 'Flutter', 'flutter', 'bin',
                    'cache', 'dart-sdk', 'bin', 'dart.exe')
try:
    s = open(p, encoding='utf-8').read()
    old = "          final data = await handle.read(chunkSize);"
    new = "          final data = handle.readSync(chunkSize);"
    assert old in s, 'chunks() 已经是同步读，无法验证'
    open(p, 'w', encoding='utf-8').write(s.replace(old, new, 1))

    r = subprocess.run([dart, 'test', '--plain-name', '事件循环'], cwd=CORE,
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    tail = [l for l in r.stdout.splitlines() if l.strip()][-6:]
    print('=== 改回同步读后的测试结果 ===')
    print('\n'.join(tail))
    print('exit code:', r.returncode,
          '-> 测试确实抓到了这个 bug' if r.returncode != 0 else '-> 没抓到，需要加强测试')
finally:
    shutil.copy2(bak, p)
    os.remove(bak)
    print('已还原为异步读')
    chk = [l.strip() for l in open(p, encoding='utf-8') if 'handle.read' in l]
    print('\n'.join(chk))
