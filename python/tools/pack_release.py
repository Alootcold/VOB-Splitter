"""把打包好的目录版 exe 压成可分发的 zip（放 GitHub Releases 用）。"""
import os
import zipfile

BASE = r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter"
DIST = os.path.join(BASE, 'python', 'dist')
OUT_DIR = os.path.join(BASE, 'release')
os.makedirs(OUT_DIR, exist_ok=True)

for name in ('vobsplit', 'vobsplit-cli'):
    src = os.path.join(DIST, name)
    if not os.path.isdir(src):
        continue
    out = os.path.join(OUT_DIR, '%s-windows-x64.zip' % name)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, _dirs, files in os.walk(src):
            for f in files:
                p = os.path.join(root, f)
                zf.write(p, os.path.join('vobsplit-%s' % name,
                                        os.path.relpath(p, src)).replace('\\', '/'))
    print('%s  %.1f MB' % (out, os.path.getsize(out) / 1048576.0))
