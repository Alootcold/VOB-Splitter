# 核心算法 / How it works

## 1. DVD 的码流结构

DVD 视频的 `VIDEO_TS` 目录里，正片存在 `VTS_xx_N.VOB`：

* `N` = 1..5 是**同一个标题**被切开的 5 段（每段上限 1 GiB，FAT32 的老规矩）
* `VTS_xx_0.VOB` 是盘上菜单（标题 0），不属于正片内容
* 这些文件在码流上是**连续的** —— 工具把它们当一条流处理

整条流是 MPEG-2 Program Stream：

```
┌────────────── 2048 字节 pack ──────────────┐
│ 00 00 01 BA   pack header (14B)             │
│ 00 00 01 E0   视频 PES 头                   │
│   81 C0 0A    flags: PTS+DTS, 头长 10       │
│   <PTS 5B> <DTS 5B>                         │
│ 00 00 01 B3   序列头（720x576 25fps）       │
│ 00 00 01 B8   GOP 头                        │
│ 00 00 01 00   图像头（picture_coding_type） │
│ ... 切片数据 ...                             │
└─────────────────────────────────────────────┘
```

## 2. 随机访问点（RAP）

一个 pack 是 RAP，当且仅当它是某个**带 PTS 的视频 PES** 的起点。
DVD 的 MPEG-2 每个 GOP 的视频 PES 都带 PTS，所以 GOP 边界天然可切入。

在 RAP 处切入，播放器可以从该点独立解码 —— 这就是「无损且不花屏」的前提。

## 3. 章边界：PTS 回落

这是整个工具的关键观察：

> **DVD 的每一章都是一条独立的 MPEG-2 sequence，章首会把 PTS 归零。**

所以在 RAP 序列里，一旦出现 `PTS[k] < PTS[k-1] - 阈值`（默认 1.0 秒），
就说明跨过了一个章边界 —— 而且这个点本身就是 RAP，可以直接切入。

**这不是某一张盘的特例，是 DVD 的通用结构。** 同一张盘上的实测：

```
章 1  PTS 0.367 → 217.88   章 2  PTS 0.367 → 271.04   章 3  PTS 0.367 → 272.01  ...
```

每一章都从 0.367 重新开始，章与章之间是断崖式回落。

### 全局时间轴

由此带来一个必须处理的问题：**每章的 PTS 是章内局部时间，不是全局时间**。
工具会额外累加出一条全局时间轴（章节首尾顺延），供「等长切分」「指定时间点」使用：

```
global_start[0] = 0
global_start[k] = global_start[k-1] + (章内 PTS 跨度 + 一个 GOP 间隔)
```

> 已知偏差：章内 PTS 跨度是「首 GOP 到末 GOP 的起点」，不含末个 GOP 的长度，
> 所以每章都多算了一个 GOP 间隔，全局时间比真实播放时间快约 `章数 × 0.48s`。
> 这只影响 `--interval` / `--times` 的落点（最多偏一个 GOP），不影响按章节切分的正确性。

## 4. 切分与校验

切分就是**字节级切片**：

```python
copy(source[start_offset : end_offset] -> chapter_NN.vob)
```

不经过任何编解码器，不改写 pack header，不动 PES 结构。

校验用 SHA-256：

```
SHA256(源流) == SHA256(各章按序拼接)   且   字节数相等
```

相等 ⇒ 输出的每一个字节都来自输入。

## 5. 码流常量备忘（写解析器时踩过的坑）

| 常量 | 值 | 备注 |
|---|---|---|
| picture_start_code | `00 00 01 00` | **不是 0xB2**；0xB2 是 user_data |
| user_data | `00 00 01 B2` | |
| sequence_header | `00 00 01 B3` | 新 sequence 的标志 |
| extension | `00 00 01 B5` | |
| group (GOP) header | `00 00 01 B8` | |
| pack header | `00 00 01 BA` | MPEG-2 版 14 字节 |
| 视频 PES stream id | `0xE0` | |

PES 里 5 字节时间戳（MPEG-2 版式）：

```
byte0   = '001x' | PTS[32..30] | marker
byte1-2 = PTS[29..15] | marker
byte3-4 = PTS[14..0]  | marker
```

* marker 位在 **byte0 / byte2 / byte4 的最低位**，必须为 1 —— 可以当校验位用
* `picture_coding_type` 在图像头起始码后 16 位的第 3..5 位：`(w >> 3) & 0x07`（1=I, 2=P, 3=B）
* MPEG-2 PES 头：`byte6 & 0xC0 == 0x80`；`byte8` 是 header_data_length；ES 起点 = `q + 9 + header_data_length`

## 6. 转 MKV（可选）

用 `ffmpeg -c copy` 换容器，码流载荷不变。两点注意：

* 切片起点的**音频 PES 本身不带时间戳**，直接转会报
  `Can't write packet with unknown timestamp` —— 输入端加 `-fflags +genpts` 补齐
* DVD 的 `dvd_nav_packet`（PCI/DSI 导航包）**装不进 Matroska**，用
  `-map 0:v -map 0:a?` 排除；它与音视频码流无关

验证容器转换后仍然无损：

```bash
ffmpeg -i in.vob  -map 0:v -c copy -f hash -hash sha256 -
ffmpeg -i out.mkv -map 0:v -c copy -f hash -hash sha256 -
```

两个哈希相同 ⇒ 视频 elementary stream 逐字节一致。
