# VOB Splitter — Flutter / Dart

```
flutter/
├─ packages/vobsplit_core/   纯 Dart 核心库（MPEG-2 PS 解析 + 章节检测 + 切分）
└─ app/                      桌面 GUI（Windows / macOS / Linux）
```

核心库不依赖 Flutter，可以用 `dart` 直接跑，也能单独发到 pub.dev。

## 核心库（纯 Dart）

```bash
cd packages/vobsplit_core
dart pub get
dart test
dart run bin/vobsplit.dart scan  "D:\VIDEO_TS"
dart run bin/vobsplit.dart split "D:\VIDEO_TS" -o "D:\Split"
```

API 见 `lib/vobsplit_core.dart`，行为与 `../../python/` 版一一对应。

## 桌面 GUI

```bash
cd app
flutter pub get
flutter run -d windows      # 或 macos / linux
```

界面分三块：

* **左侧控制栏** —— 源 → 切分方式 → 输出 → 开始
* **右侧章节表格** —— 每章的起始、时长、大小、GOP 数
* **底部日志** + 顶栏的**无损校验徽章**

设计规范见 [`../../DESIGN.md`](../../DESIGN.md)。

### 构建

| 平台 | 命令 | 额外依赖 |
|---|---|---|
| Windows | `flutter build windows` | Visual Studio 2022（含「使用 C++ 的桌面开发」） |
| macOS | `flutter build macos` | Xcode |
| Linux | `flutter build linux` | clang / cmake / ninja / GTK |

### 打成安装包（NSIS）

```bash
# 需要 NSIS 3.x（makensis.exe）
flutter build windows --release
makensis installer/vobsplit.nsi
# 或走统一入口：
python ..\..\tools\build_installers.py flutter
```

安装包装到 `$PROGRAMFILES64\VOB Splitter`，安装界面中英双语（NSIS 自带
Simplified Chinese 语言包），会生成 `uninstall.exe` 并写标准 `Uninstall`
注册表项，「应用和功能」里能正常卸载/修复。

### 测试

```bash
cd app && flutter analyze && flutter test
```
