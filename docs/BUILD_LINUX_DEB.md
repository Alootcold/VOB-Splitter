# 把 Flutter Linux 版打包成 .deb

> 适用项目：VOB Splitter（Flutter 桌面端）
> 目标产物：`vobsplit_1.0.0_amd64.deb`
> 读者假设：有一台 Linux 实体机（Ubuntu 22.04 / 24.04 最省事）

---

## 0. 先说最关键的前提

**Flutter 不支持从 Windows / macOS 交叉编译 Linux 桌面版。**
在非 Linux 机器上跑 `flutter build linux` 会直接报错退出 —— 因为要链 GTK3 的系统库、
要用 Linux 的 clang/cmake。

所以这条流水线必须在 Linux 上跑。好在你有实体机：

| 方案 | 说明 |
|---|---|
| **Linux 实体机** | 最省事，直接编直接装 |
| Linux 虚拟机 | 也行 |
| WSL2 | **打包够用**（纯命令行不需要显示器），但 GUI 调试要 WSLg |

---

## 1. 一次性准备：系统依赖

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install -y \
  clang cmake ninja-build pkg-config \
  libgtk-3-dev liblzma-dev \
  git curl unzip xz-utils \
  dpkg-dev
```

各包是干什么的：

| 包 | 用途 |
|---|---|
| `clang` `cmake` `ninja-build` `pkg-config` | Flutter Linux 构建工具链 |
| `libgtk-3-dev` | GTK3 开发头文件（`linux/CMakeLists.txt` 里 `pkg_check_modules(GTK REQUIRED gtk+-3.0)` 要它） |
| `liblzma-dev` | LZMA，Flutter 引擎的 `libflutter_linux_gtk.so` 依赖它 |
| `dpkg-dev` | 提供 `dpkg-deb`（打 deb 用） |

装完检查一下：

```bash
flutter doctor -v
```

只需要 `Flutter` 和 `Linux toolchain` 两项是 ✓ 就行（Android 那堆不用管）。

---

## 2. 拉代码

```bash
git clone https://gitee.com/aloot-cold/vob-splitter.git
cd vob-splitter
```

---

## 3. 编译出 bundle

```bash
cd flutter/app
flutter pub get
flutter build linux --release
cd ../..
```

产物在 `flutter/app/build/linux/x64/release/bundle/`，结构长这样：

```
bundle/
├── vobsplit_gui          ← 可执行文件（linux/CMakeLists.txt 里的 BINARY_NAME）
├── data/
│   ├── flutter_assets/
│   └── icudtl.dat
├── lib/
│   ├── libapp.so         ← AOT 快照
│   └── libflutter_linux_gtk.so
└── resources/
    └── app_icon.png      ← 项目自己加的窗口图标（512×512 PNG）
```

### ⚠️ 一个必须记住的约束

`linux/CMakeLists.txt` 里有一行：

```cmake
set(CMAKE_INSTALL_RPATH "$ORIGIN/lib")
```

`$ORIGIN` = **可执行文件自己所在的目录**。也就是说 `vobsplit_gui` 靠
「自己旁边的 `lib/` 目录」找 Flutter 引擎的 .so。

所以：

* 打包时**整个 bundle 目录要原样搬走**，不能只挑 exe 和 data；
* 运行时**必须通过 bundle 里的那个可执行文件启动**，不能把 exe 单独拎出来跑；
* 桌面菜单里的启动项也应该指向一个固定的安装路径，由脚本负责转调。

---

## 4. deb 是什么（30 秒原理）

一个 `.deb` 就是个 **ar 归档**，里面三个成员：

```
debian-binary      ← 格式版本，就一行 "2.0\n"
control.tar.gz     ← 元信息（包名/版本/依赖）+ 安装前后脚本
data.tar.gz        ← 真正要装到系统里的文件树
```

所以手工做 deb 的全部工作量就是：**摆一棵正确的文件树 → `dpkg-deb --build`**。

---

## 5. 手搓 deb

### 5.1 文件树

```
vobsplit_1.0.0_amd64/
├── DEBIAN/
│   └── control                          ← 包元信息（不是目录权限，随便 755 也行，但别给 world-writable）
├── usr/
│   ├── bin/
│   │   └── vobsplit                     ← 启动脚本（用户在 PATH 里敲的那个）
│   ├── lib/
│   │   └── vobsplit/                    ← bundle 整个搬进来
│   │       ├── vobsplit_gui
│   │       ├── data/
│   │       ├── lib/
│   │       └── resources/
│   └── share/
│       ├── applications/
│       │   └── vobsplit.desktop         ← 桌面菜单项
│       ├── icons/hicolor/256x256/apps/
│       │   └── vobsplit.png             ← 菜单里的图标
│       └── doc/vobsplit/
│           ├── copyright
│           └── changelog.Debian.gz
```

### 5.2 control 文件

```ini
Package: vobsplit
Version: 1.0.0
Section: video
Priority: optional
Architecture: amd64
Maintainer: VOB Splitter contributors <vobsplit@example.com>
Depends: libgtk-3-0 (>= 3.22), liblzma5, libstdc++6
Description: DVD VOB 无损分割工具
 按 DVD 内置章节切开 VOB，输出是输入码流的连续字节区间，
 不重编码、不重封装。每次运行都会用 SHA-256 校验。
```

要点：

* `Description` 的**续行要以空格开头** —— Debian 控制文件靠这个区分「续行」和「新字段」。
* `Depends` 里的 `liblzma5` 别漏：漏了在没装 lzma 的干净系统上会「装得上、跑不起来」。
  运行时用 `ldd` 核对一遍更保险（见第 8 节）。

### 5.3 `/usr/bin/vobsplit` 启动脚本

```sh
#!/bin/sh
exec /usr/lib/vobsplit/vobsplit_gui "$@"
```

这一层不是多余的：它保证了**从固定路径启动 bundle 里的那个可执行文件**，
`$ORIGIN/lib` 才找得到引擎库。

### 5.4 `.desktop` 文件

```ini
[Desktop Entry]
Name=VOB Splitter
Comment=DVD VOB 无损分割工具
Exec=vobsplit
Icon=vobsplit
Type=Application
Categories=AudioVideo;Video;GTK;
Terminal=false
StartupNotify=true
```

* `Exec=` 写**不带路径**的 `vobsplit`（在 PATH 里找）；写死 bundle 内部路径的话，
  将来升级换了目录就废了。
* `Icon=` 写图标**名字**，必须跟图标文件名对得上（`vobsplit.png` ↔ `Icon=vobsplit`），
  否则菜单里是空白图标。

### 5.5 图标

Linux 用 PNG 不用 ICO。项目里 `flutter/app/linux/runner/resources/app_icon.png`
已经是 512×512 的 RGBA PNG，直接用：

```bash
cp linux/runner/resources/app_icon.png \
   "$STAGE/usr/share/icons/hicolor/256x256/apps/vobsplit.png"
```

想多给几档尺寸（hicolor 规范建议多档）：

```bash
for s in 16 32 48 64 128 256 512; do
  mkdir -p "$STAGE/usr/share/icons/hicolor/${s}x${s}/apps"
  convert linux/runner/resources/app_icon.png -resize ${s}x${s} \
    "$STAGE/usr/share/icons/hicolor/${s}x${s}/apps/vobsplit.png"
done
```

（`convert` 来自 ImageMagick：`sudo apt install imagemagick`）

### 5.6 打包

```bash
dpkg-deb --build --root-owner-group vobsplit_1.0.0_amd64 vobsplit_1.0.0_amd64.deb
```

**`--root-owner-group` 一定要加**：不用 sudo 也能打出属主为 `root:root` 的正确 deb。
不加的话属主会变成当前用户，dpkg 安装时会报权限警告。

---

## 6. 一键脚本

上面这些已经写成 `tools/build_deb.sh`（见仓库），直接跑：

```bash
cd vob-splitter
bash tools/build_deb.sh
```

脚本做这些事：

1. 检查 bundle 在不在、依赖装没装；
2. 拼出上面那棵文件树；
3. 生成 `control` / `.desktop` / 启动脚本 / 图标 / 文档；
4. `dpkg-deb --build --root-owner-group`；
5. 打完打印 `dpkg-deb -I` 的元信息。

产物落在 `release/vobsplit_1.0.0_amd64.deb`。

> 如果不想用脚本，把第 5 节的内容手工敲一遍也完全一样 —— 脚本只是把
> 「敲一遍」这件事固化下来，方便以后改版本号。

### ⚠️ 别从 Windows 拷脚本过来

脚本是 shell 脚本，**换行必须是 LF**。从 Windows 上把 `.sh` 文件拖到 Linux 上，
十有八九带的是 CRLF，于是：

```
bash tools/build_deb.sh: set: pipefail: 无效的选项名
```

bash 把 `\r` 当成了选项名的一部分。两种解法：

```bash
# 一、就地修一下
sed -i 's/\r$//' tools/build_deb.sh
# 或者
dos2unix tools/build_deb.sh

# 二、直接在 Linux 上 clone（仓库里的 .gitattributes 已经保证脚本是 LF）
git clone https://gitee.com/aloot-cold/vob-splitter.git
```

新版脚本开头带了 **CRLF 自愈**：检测到文件里有 `\r` 就先剥掉再重跑一次，
所以即使又被拷成 CRLF 也能直接跑。但 `.desktop` 文件没有自愈（它不执行），
那个由 `.gitattributes` 里的 `*.desktop text eol=lf` 兜底。

---

## 7. 验证

### 7.1 看包

```bash
dpkg-deb -I release/vobsplit_1.0.0_amd64.deb   # 元信息：包名/版本/依赖
dpkg-deb -c release/vobsplit_1.0.0_amd64.deb   # 文件清单
```

### 7.2 装 + 跑

```bash
sudo apt install ./release/vobsplit_1.0.0_amd64.deb
vobsplit
```

装完桌面菜单里应该出现「VOB Splitter」，图标是那个光盘。

卸载：

```bash
sudo apt remove vobsplit
```

### 7.3 依赖是否齐全

```bash
ldd /usr/lib/vobsplit/vobsplit_gui | grep -i "not found"
```

**没有任何输出** = 依赖齐全。有输出就照着提示把缺的包加进 `control` 的 `Depends`。

### 7.4 包体质量

```bash
sudo apt install lintian
lintian release/vobsplit_1.0.0_amd64.deb
```

---

## 8. 常见坑

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `bash build_deb.sh: 行 18: $'\r': 未找到命令` | 脚本是 **CRLF** 换行（多半是从 Windows 直接拷过来的）。空的 CRLF 行在 bash 里会被当成一条命令去执行 | `sed -i 's/\r$//' tools/build_deb.sh`（或 `dos2unix`）。新版脚本开头有 CRLF 自愈，老版本要手动处理 |
| `bash build_deb.sh: set: pipefail: 无效的选项名` | 同上，`set -euo pipefail` 行尾的 `\r` 被当成了选项名的一部分 | 同上 |
| 装得上，双击没反应 / 终端报 `error while loading shared libraries` | `Depends` 漏了 | `ldd` 看缺哪个，补进 `control` |
| 装上了，菜单里没这一项 | `.desktop` 没装进 `/usr/share/applications/` | 检查 `dpkg-deb -c` 里有没有它；装完可能要 `update-desktop-database` |
| 菜单有这一项但图标是空白 | `Icon=` 的名字和图标文件名对不上 | 两者必须一致 |
| 菜单有这一项但图标不是新图标 | 图标被 icon theme 缓存了 | 改完图标后 `sudo update-desktop-database -q` 或 `gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor` |
| 手动运行提示找不到 `libflutter_linux_gtk.so` | 只把 exe 拎出来了，bundle 没搬完整 | 整个 bundle 一起装；启动走 `/usr/lib/vobsplit/vobsplit_gui` |
| `dpkg-deb: error: requested operation requires superuser` | 用 sudo 打包导致属主是 root | 用 `--root-owner-group`，别用 sudo |
| 打包时提示找不到 `dpkg-deb` | 没装 `dpkg-dev` | `sudo apt install dpkg-dev` |

---

## 9. 备选方案：nfpm

`nfpm` 是 Go 写的单文件工具，**不用手搓目录树**，写个 yaml 就行：

```yaml
name: vobsplit
arch: amd64
platform: linux
version: 1.0.0
section: video
priority: optional
maintainer: VOB Splitter contributors <vobsplit@example.com>
description: |
  DVD VOB 无损分割工具
  按 DVD 内置章节切开 VOB，逐字节不差。
depends:
  - libgtk-3-0 (>= 3.22)
  - liblzma5
  - libstdc++6
contents:
  - src: flutter/app/build/linux/x64/release/bundle
    dst: /usr/lib/vobsplit
  - src: tools/linux/vobsplit.desktop
    dst: /usr/share/applications/vobsplit.desktop
  - src: tools/linux/vobsplit.sh
    dst: /usr/bin/vobsplit
    type: script
  - src: flutter/app/linux/runner/resources/app_icon.png
    dst: /usr/share/icons/hicolor/256x256/apps/vobsplit.png
```

```bash
nfpm pack --packager deb --target vobsplit_1.0.0_amd64.deb
```

**但要清楚它省不了什么**：nfpm 只省掉「拼目录树」这一步，
**省不掉「在 Linux 上编译」** —— bundle 还是得 Linux 上出。

---

## 10. 关于本项目的 Linux 版

`flutter/app/pubspec.yaml` 里的依赖是跨平台的：

```yaml
dependencies:
  flutter:
    sdk: flutter
  vobsplit_core:
    path: ../packages/vobsplit_core
  file_selector: ^1.0.3      # 原生目录选择器，Windows / macOS / Linux 都有
```

核心算法是纯 Dart，图形界面只用到 Flutter 和 `file_selector`，
**没有 Windows 专属的原生依赖**，所以 Linux 构建在依赖层面是通的。

不过要说明：**这个项目的 Linux 版此前没有实际编译验证过**。
第一次编出来之后建议先手动过一遍流程（选 VOB → 切分 → 看校验徽章是否为绿色），
确认没问题再拿去发版。

---

## 11. 一页速查

```bash
# --- 一次性 ---
sudo apt update
sudo apt install -y clang cmake ninja-build pkg-config libgtk-3-dev liblzma-dev dpkg-dev

# --- 每次出包 ---
cd vob-splitter
cd flutter/app && flutter pub get && flutter build linux --release && cd ../..
bash tools/build_deb.sh

# --- 验证 ---
dpkg-deb -I release/vobsplit_1.0.0_amd64.deb
sudo apt install ./release/vobsplit_1.0.0_amd64.deb
vobsplit
```
