# VOB Splitter v1.0.0 更新日志

**按 DVD 内置章节切开 VOB，逐字节不差。**
**Cut a DVD VOB by its built-in chapters, byte for byte.**

首次公开版本。

---

## 这次更新了什么

### 1. 安装和卸载界面全部换成自绘皮肤

* 安装程序和卸载程序**都不用系统默认的那套窗口**，而是自己画的一套深色界面
  （Duilib 皮肤 + 一个自己写的 NSIS 插件），和软件本体同一套视觉：深色底 +
  青色强调色，标题条、最小化/关闭按钮、路径框、复选框、进度条、完成页全是自绘。
* 卸载界面同样是自绘的：确认 → 进行中 → 完成三页；也支持静默卸载
  （`uninstall.exe /S`）。
* 皮肤是纯 XML 布局（`skin/setup.xml`、`skin/uninstall.xml`）+ 少量自绘位图，
  想改颜色和排版不用碰 C++。

### 2. 两套独立实现，行为一致

| | 形态 | 依赖 |
|---|---|---|
| `python/` | 命令行 + 桌面 GUI | Python 3.8+，**零第三方依赖**（GUI 用标准库 Tkinter） |
| `flutter/` | 桌面 GUI + 纯 Dart 核心库 | Flutter 3.16+ / Dart 3.4+ |

两套**互不依赖**，但核心算法逐行对应、测试用例一一对应。
`tools/cross_check.py` 让两边跑同一个 VOB，逐项比对扫描结果、切分产物哈希与
清单文件。

### 3. 切分本身

* **按章节切**：DVD 的每一章都是一条独立的 MPEG-2 sequence、章首 PTS 归零，
  所以「PTS 回落」精确对应一个章边界，而且那里天然是随机访问点，可以安全切入。
* **字节级无损**：输出是输入码流的连续字节区间，不重编码、不重封装。
  每次运行都用 SHA-256 比对「源流」与「各章拼接」，结果写进清单。
* **兜底模式**：没有章节表的 VOB 可以按 `duration`（等长）或 `times`（指定时间点）切。
* **可选转 MKV**：调用 ffmpeg `-c copy` 换容器，码流载荷哈希与源一致。

### 4. 图形界面

两边同构：左侧控制栏（源 / 切分方式 / 输出），右侧章节表格 + 日志，
顶栏是状态与**无损校验**徽章。切分跑在后台线程，界面不卡。

---

## 实测数据

在一张真实 DVD（NTSC，720×576 / 25fps / MPEG-2 + 双 AC-3，无字幕，01:40:59）上：

```
源: VTS_01_1~4.VOB  3,872,296,960 字节
pack=1,890,770   非法 pack=0   视频 PES=1,733,871   随机访问点=12,638
检测到 23 章
源 SHA-256 = 67c9d715...1bff3bd3
出 SHA-256 = 67c9d715...1bff3bd3
→ 逐字节完全一致
```

每章时长与 DVD 内置章节表（PGC program map）逐项吻合，**最大偏差 0.48 秒 = 一个 GOP**。

---

## 下载

| 文件 | 说明 | SHA-256 |
|---|---|---|
| `vobsplit-win-x64-setup.exe` | Flutter 版安装包（11.8 MB，自绘界面） | `02a6dd0294613972b8cdd50fd79608da5b5dedc5a0a3705c77331952c967dff9` |
| `vobsplit-setup.exe` | Python 版安装包（英文界面，9.8 MB） | `c0b031573cf78119fbb4a694e4dddc950d3110633e6d7d3917c3b2a32cfdc74c` |
| `vobsplit-setup-zh.exe` | Python 版安装包（中文界面，9.8 MB） | `262899af1a7fb8c10351758029260c03bb292b7a8e4c400df48dd8cf0f900bcf` |
| `vobsplit-windows-x64.zip` | 免安装版（Flutter） | — |
| `vobsplit-cli-windows-x64.zip` | 命令行版（Python） | — |

源码：<https://gitee.com/aloot-cold/vob-splitter>

---

## 已知边界

* **CSS 加密盘**：码流本身是密文，本工具只切片不解密；输出与输入同为密文，
  切点判定会失效。
* **没有章节表的 VOB**：`auto` 模式检测不到边界时，工具会提示改用
  `duration` / `times`。
* **转 MKV 会丢导航包**：DVD 的 PCI/DSI 导航包装不进 Matroska 容器被丢弃，
  它与音视频码流无关，不影响播放与画质。
* **转 MKV 需要另装 ffmpeg**（可选）。VOB 本身已经是无损切好的。
* **安装的是「目录版」**：Python 版装的是 `vobsplit.exe + _internal` 目录，
  不是单文件自解压版 —— 单文件版每次运行都把程序解压到临时目录再执行，
  既不好审计，也容易成为注入目标。

---

## 许可

[MIT](LICENSE)
