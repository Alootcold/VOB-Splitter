# 贡献指南 / Contributing

## 这个项目有两套实现

`python/` 与 `flutter/packages/vobsplit_core/` 是**同一套算法的两个移植**，
行为必须一致。

* 改算法 → **两边都改**，并让两边的测试用例一一对应
* 只改 UI → 改 `flutter/app/`
* 只改 CLI 参数 → 两边的 CLI 都要跟上

## 提交前必跑

```bash
# Python
cd python && python -m unittest discover -s tests -v

# Dart 核心
cd flutter/packages/vobsplit_core && dart analyze && dart test

# Flutter 桌面端
cd flutter/app && flutter analyze && flutter test

# 两套实现的行为一致性（需要本机装了 Dart）
python tools/cross_check.py            # 用合成夹具
python tools/cross_check.py path/to.vob  # 用真实 VOB
```

`cross_check.py` 会让 Python 版与 Dart 版跑同一个 VOB，逐项比对 scan 结果、
切分产物哈希、manifest 全字段 —— 两边行为必须完全一致。

## 测试怎么写

不要依赖真实光盘。用 `tests/synth.py`（Python）/ `test/synth.dart`（Dart）
里的合成器造码流 —— 它能精确控制「几章、每章多少 GOP、PTS 是否重置」，
这样测试既快又确定。

合成器要按 MPEG-2 规范生成 pack header / 视频 PES / 序列头，
改动它时注意 `docs/ALGORITHM.md` 里的常量表。

## 涉及码流的改动

先读 [`docs/ALGORITHM.md`](docs/ALGORITHM.md)。几个容易踩的坑：

* `picture_start_code` 是 `00 00 01 00`，**不是 0xB2**
* PES 里 5 字节时间戳的 marker 在 byte0 / byte2 / byte4 的最低位
* 每章的 PTS 是**章内局部时间**，全局时间轴要另外累加

## 提交信息

用祈使句写清楚做了什么，例如：

```
fix: 章内 PTS 回落判定阈值改为可配置
feat: 支持把多个 VOB 目录按标题分别切分
docs: 补充 Matroska 导航包丢失的说明
```

## 许可证

贡献的代码默认以 [MIT](LICENSE) 授权。
