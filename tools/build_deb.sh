#!/usr/bin/env bash
# CRLF 自愈：这个脚本经常被从 Windows 直接拷到 Linux 上，拷过来就是 CRLF。
# bash 把 \r 当成命令的一部分 —— 空的 CRLF 行会变成「$'\r': 未找到命令」，
# set -euo pipefail\r 会变成「无效的选项名」，rm -rf "$dir"\r 还会造出带 CR 的目录名。
# 检测到 CR 就先剥掉再重跑一次。
#
# 守卫必须紧跟 shebang（整个文件的第一条可执行语句）：放在注释块后面的话，
# 中间那些空行会先被当成命令执行掉，根本等不到守卫。
# 用临时文件而不是进程替换（<(...)）：进程替换下内层 bash 和守卫会抢同一个
# fd 的内容，内层会读到 EOF 然后什么都不干。
# 行的末尾放在注释里，是为了即使这一行自己也带 \r 也不会把语法搞坏。
if [ -n "$(tr -dc '\r' < "$0" 2>/dev/null)" ]; then t="$(mktemp)"; tr -d '\r' < "$0" > "$t"; VOB_DEB_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)" bash "$t" "$@"; rc=$?; rm -f "$t"; exit $rc; fi # CRLF guard

# ---------------------------------------------------------------------------
#  把 flutter build linux 的产物打成 .deb
#
#  用法（在仓库根目录）：
#     bash tools/build_deb.sh
#
#  前置：
#     cd flutter/app && flutter pub get && flutter build linux --release
#
#  依赖：dpkg-deb（apt install dpkg-dev）
#
#  产物：
#     release/vobsplit_1.0.0_amd64.deb
#
#  原理见 docs/BUILD_LINUX_DEB.md
# ---------------------------------------------------------------------------
set -euo pipefail

APP=vobsplit
VERSION=1.0.0
ARCH=amd64
MAINTAINER="VOB Splitter contributors <vobsplit@example.com>"

HERE="${VOB_DEB_SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
ROOT="$(cd "$HERE/.." && pwd)"
APP_DIR="$ROOT/flutter/app"
BUNDLE="$APP_DIR/build/linux/x64/release/bundle"
ICON_SRC="$APP_DIR/linux/runner/resources/app_icon.png"
LICENSE_SRC="$ROOT/LICENSE"

STAGE="$ROOT/${APP}_${VERSION}_${ARCH}"
OUT="$ROOT/release/${APP}_${VERSION}_${ARCH}.deb"

# --- 前置检查 --------------------------------------------------------------
if [ ! -d "$BUNDLE" ]; then
    echo "!! 找不到 bundle：$BUNDLE" >&2
    echo "   先在 flutter/app 下跑：flutter build linux --release" >&2
    exit 1
fi
if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "!! 找不到 dpkg-deb，先装：sudo apt install dpkg-dev" >&2
    exit 1
fi
if [ ! -f "$ICON_SRC" ]; then
    echo "!! 找不到图标：$ICON_SRC" >&2
    exit 1
fi

# --- 搭文件树 --------------------------------------------------------------
rm -rf "$STAGE"
mkdir -p \
    "$STAGE/DEBIAN" \
    "$STAGE/usr/bin" \
    "$STAGE/usr/lib/$APP" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps" \
    "$STAGE/usr/share/doc/$APP"

# 1. 程序本体：整个 bundle 搬过去。
#    可执行文件靠 $ORIGIN/lib 找引擎库，所以 lib/ 必须跟着走。
cp -a "$BUNDLE"/. "$STAGE/usr/lib/$APP/"
chmod 0755 "$STAGE/usr/lib/$APP/vobsplit_gui"

# 2. 启动脚本：保证从固定路径启动 bundle 里的那个可执行文件
cat > "$STAGE/usr/bin/$APP" <<EOF
#!/bin/sh
exec /usr/lib/$APP/vobsplit_gui "\$@"
EOF
chmod 0755 "$STAGE/usr/bin/$APP"

# 3. 桌面菜单项（Icon= 的名字必须和图标文件名一致）
cat > "$STAGE/usr/share/applications/$APP.desktop" <<EOF
[Desktop Entry]
Name=VOB Splitter
Comment=DVD VOB 无损分割工具
Exec=$APP
Icon=$APP
Type=Application
Categories=AudioVideo;Video;GTK;
Terminal=false
StartupNotify=true
EOF

# 4. 图标（hicolor 按尺寸分目录）
cp "$ICON_SRC" "$STAGE/usr/share/icons/hicolor/256x256/apps/$APP.png"

# 5. 包元信息。Description 的续行以空格开头 —— Debian 靠这个区分续行
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $APP
Version: $VERSION
Section: video
Priority: optional
Architecture: $ARCH
Maintainer: $MAINTAINER
Depends: libgtk-3-0 (>= 3.22), liblzma5, libstdc++6
Description: DVD VOB 无损分割工具
 按 DVD 内置章节切开 VOB，输出是输入码流的连续字节区间，
 不重编码、不重封装。每次运行都会用 SHA-256 校验。
EOF

# 6. 文档
cp "$LICENSE_SRC" "$STAGE/usr/share/doc/$APP/copyright"
cat > "$STAGE/usr/share/doc/$APP/changelog.Debian" <<EOF
$APP ($VERSION) unstable; urgency=medium

  * 首次发布。

 -- $MAINTAINER  $(date -R)
EOF
gzip -9nf "$STAGE/usr/share/doc/$APP/changelog.Debian"

# --- 打包 ------------------------------------------------------------------
# --root-owner-group：不用 sudo 也能打出属主 root:root 的正确 deb
mkdir -p "$ROOT/release"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
rm -rf "$STAGE"

echo
echo "打包完成：$OUT"
echo
dpkg-deb -I "$OUT"
